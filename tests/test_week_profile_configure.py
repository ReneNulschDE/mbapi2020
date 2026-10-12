"""The weekly profile command rebuilds the whole list from one change.

WEEK_PROFILE_CONFIGURE_V2 replaces the vehicle's entire profile, while the
service changes a single entry. These tests pin that translation: entries the
caller did not name have to come back unchanged, with their own application
identifier, and only the entry that changed may carry the -1 marker. Getting
that wrong deletes departure entries on a real car, which is why it is checked
down to the single field.
"""

from __future__ import annotations

import asyncio
import datetime
from typing import Any

import pytest

from custom_components.mbapi2020.client import Client
from custom_components.mbapi2020.proto import client_pb2
from homeassistant.exceptions import ServiceValidationError

from .conftest import make_client
from .fixtures.build import SYNTH_VIN, build_weekly_profile_status_updates, roundtrip

# The parameter sets the two vehicle generations report for the command. The
# CLA offers the action list and a real choice of schedule type; the others
# report neither and allow NO_SELECTION only.
_PARAMETERS_WITH_ACTIONS = [
    {"parameterName": "HOUR", "minValue": 0, "maxValue": 23},
    {"parameterName": "MINUTE", "minValue": 0, "maxValue": 59},
    {"parameterName": "ACTIVE", "allowedBools": "TRUE_AND_FALSE"},
    {"parameterName": "TIME_PROFILE_DAYS", "allowedEnums": ["MONDAY", "TUESDAY", "SUNDAY"]},
    {"parameterName": "ACTION_LIST_CHARGING", "allowedBools": "TRUE_AND_FALSE"},
    {"parameterName": "ACTION_LIST_PRECOND", "allowedBools": "TRUE_AND_FALSE"},
    {"parameterName": "ACTION_LIST_BATTERY_PRECOND", "allowedBools": "TRUE_AND_FALSE"},
    {
        "parameterName": "SCHEDULE_TYPE",
        "allowedEnums": ["RECURRING", "NON_RECURRING", "NON_RECURRING_AUTO_DELETE"],
    },
]
_PARAMETERS_PLAIN = [
    {"parameterName": "HOUR", "minValue": 0, "maxValue": 23},
    {"parameterName": "MINUTE", "minValue": 0, "maxValue": 59},
    {"parameterName": "ACTIVE", "allowedBools": "TRUE_AND_FALSE"},
    {"parameterName": "TIME_PROFILE_DAYS", "allowedEnums": ["MONDAY", "TUESDAY"]},
    {"parameterName": "SCHEDULE_TYPE", "allowedEnums": ["NO_SELECTION"]},
]


def _prepared_client(
    *,
    parameters: list[dict[str, Any]] | None = None,
    available: bool = True,
    with_profile: bool = True,
) -> tuple[Client, list[client_pb2.ClientMessage]]:
    """Return a client with one car, its capabilities, and the sent messages."""
    client = make_client()
    client._process_vehicle_status_updates(roundtrip(build_weekly_profile_status_updates(active_identifier=2)))
    car = client.cars[SYNTH_VIN]
    car.features = {"WEEK_PROFILE_CONFIGURE_V2": available}
    car.capabilities = {
        "commands": [
            {
                "commandName": "WEEK_PROFILE_CONFIGURE_V2",
                "isAvailable": available,
                "parameters": _PARAMETERS_WITH_ACTIONS if parameters is None else parameters,
            }
        ]
    }
    if not with_profile:
        car.last_full_message = None

    sent: list[client_pb2.ClientMessage] = []

    async def _capture(message) -> None:
        # Re-parse what would go on the wire, so the assertions see the message
        # the car would, not the object that was built.
        decoded = client_pb2.ClientMessage()
        decoded.ParseFromString(message.SerializeToString())
        sent.append(decoded)

    client.execute_car_command = _capture  # type: ignore[method-assign]
    return client, sent


def _call(client: Client, **kwargs) -> None:
    """Run the command, which is async while the tests are not."""
    asyncio.run(client.week_profile_configure(SYNTH_VIN, **kwargs))


def _entries(sent: list[client_pb2.ClientMessage]) -> list[Any]:
    assert len(sent) == 1
    assert sent[0].commandRequest.WhichOneof("command") == "week_profile_configure_v2"
    return list(sent[0].commandRequest.week_profile_configure_v2.time_profiles)


# --- the full-list semantics ---


def test_changing_one_entry_resends_the_other_unchanged() -> None:
    """The untouched entry keeps its values and its application identifier.

    -1 is how the vehicle tells the entry this client changed from the ones it
    passed through, so putting it on an untouched entry would mark the whole
    profile as rewritten.
    """
    client, sent = _prepared_client()

    _call(client, identifier=1, time=datetime.timedelta(hours=6, minutes=45))

    changed, untouched = _entries(sent)
    assert changed.identifier.value == 1
    assert (changed.hour.value, changed.minute.value) == (6, 45)
    assert changed.application_identifier == -1
    assert untouched.identifier.value == 2
    assert (untouched.hour.value, untouched.minute.value) == (0, 5)
    assert untouched.application_identifier == 1


def test_fields_that_are_not_named_keep_their_value() -> None:
    """Changing the time must not drop the weekdays or the actions."""
    client, sent = _prepared_client()

    _call(client, identifier=1, time=datetime.timedelta(hours=6, minutes=45))

    changed = _entries(sent)[0]
    assert list(changed.days) == [1]  # TUESDAY, as reported
    assert changed.schedule_type == 1  # RECURRING, as reported
    assert len(changed.action_list) == 1
    assert changed.action_list[0].charging.value is True
    assert changed.action_list[0].precond.value is True


def test_deleting_sends_the_identifier_only() -> None:
    """A deletion is an entry with nothing but its identifier.

    Anything else in that entry would be read as a change to it instead of as
    a removal.
    """
    client, sent = _prepared_client()

    _call(client, identifier=1, delete=True)

    removed, kept = _entries(sent)
    assert sorted(field.name for field, _ in removed.ListFields()) == [
        "application_identifier",
        "identifier",
    ]
    assert removed.identifier.value == 1
    assert removed.application_identifier == -1
    assert kept.identifier.value == 2


def test_adding_sends_no_identifier_and_keeps_the_existing_entries() -> None:
    """A new entry has no identifier; the vehicle assigns one."""
    client, sent = _prepared_client()

    _call(client, time=datetime.timedelta(hours=7), days=["monday", "sunday"], active=True)

    entries = _entries(sent)
    assert len(entries) == 3
    assert [entry.identifier.value for entry in entries[:2]] == [1, 2]
    added = entries[2]
    assert added.HasField("identifier") is False
    assert (added.hour.value, added.minute.value) == (7, 0)
    assert list(added.days) == [0, 6]
    assert added.active.value is True
    assert added.application_identifier == -1
    # Days were given, so the entry repeats - the app derives it the same way.
    assert added.schedule_type == 1


def test_actions_are_merged_into_one_entry_of_the_action_list() -> None:
    """Setting one action keeps the others the vehicle reported.

    The vehicle may report several action entries, each carrying one flag.
    They mean the same as a single entry carrying all of them.
    """
    client, sent = _prepared_client()

    _call(client, identifier=1, battery_precond=True)

    changed = _entries(sent)[0]
    assert len(changed.action_list) == 1
    assert changed.action_list[0].charging.value is True
    assert changed.action_list[0].precond.value is True
    assert changed.action_list[0].battery_precond.value is True


# --- per-car capabilities ---


def test_a_schedule_type_the_car_rejects_is_replaced_for_every_entry() -> None:
    """A car that offers no choice gets NO_SELECTION, not its reported value.

    Every entry of the command needs the field set, and the entries of such a
    car report RECURRING on the status side - a value its own command does not
    accept.
    """
    client, sent = _prepared_client(parameters=_PARAMETERS_PLAIN)

    _call(client, identifier=1, active=True)

    assert [entry.schedule_type for entry in _entries(sent)] == [0, 0]


def test_an_action_the_car_does_not_support_is_rejected() -> None:
    """Cars without the ACTION_LIST_* parameters must not be sent one."""
    client, _ = _prepared_client(parameters=_PARAMETERS_PLAIN)

    with pytest.raises(ServiceValidationError, match="charging"):
        _call(client, identifier=1, charging=True)


def test_a_schedule_type_outside_the_allowed_values_is_rejected() -> None:
    """An explicit value the car does not list is an error, not a silent swap."""
    client, _ = _prepared_client(parameters=_PARAMETERS_PLAIN)

    with pytest.raises(ServiceValidationError, match="schedule type"):
        _call(client, identifier=1, schedule_type="recurring")


def test_the_command_is_refused_when_the_car_does_not_offer_it() -> None:
    """No capability, no command."""
    client, _ = _prepared_client(available=False)

    with pytest.raises(ServiceValidationError, match="WEEK_PROFILE_CONFIGURE_V2"):
        _call(client, identifier=1, active=True)


# --- the guards that protect the existing entries ---


def test_an_unknown_profile_is_refused_instead_of_sent() -> None:
    """Without the current list the command would delete every entry.

    The profile arrives only in full updates, so this is the state right after
    a restart that has seen partial updates only.
    """
    client, sent = _prepared_client(with_profile=False)

    with pytest.raises(ServiceValidationError, match="not known yet"):
        _call(client, identifier=1, active=True)
    assert sent == []


def test_an_unknown_identifier_is_refused() -> None:
    """Changing an entry the car does not have would add one by accident."""
    client, _ = _prepared_client()

    with pytest.raises(ServiceValidationError, match="no weekly profile entry"):
        _call(client, identifier=7, active=True)


def test_deleting_without_an_identifier_is_refused() -> None:
    """There is no "delete the current entry" - it needs to be named."""
    client, _ = _prepared_client()

    with pytest.raises(ServiceValidationError, match="needs the identifier"):
        _call(client, delete=True)


def test_adding_without_a_time_is_refused() -> None:
    """An entry without a departure time has nothing to act on."""
    client, _ = _prepared_client()

    with pytest.raises(ServiceValidationError, match="needs a time"):
        _call(client, days=["monday"])


def test_the_entry_limit_of_the_car_is_respected() -> None:
    """The car reports how many entries it holds; adding past it fails."""
    client, _ = _prepared_client()
    profile = client.cars[SYNTH_VIN].last_full_message["attributes"]["weeklyProfile"]["value"]
    profile["max_number_of_time_profiles_user"] = 2

    with pytest.raises(ServiceValidationError, match="at most 2"):
        _call(client, time=datetime.timedelta(hours=7))


# --- what the integration believes afterwards ---


def test_the_sent_profile_becomes_the_new_state() -> None:
    """A second call has to build on the first, not on the superseded list.

    The vehicle confirms a change only with its next full update, which can be
    a while away. Until then the integration works from what it sent, or the
    second call would re-send the old list and undo the first change.
    """
    client, sent = _prepared_client()

    _call(client, time=datetime.timedelta(hours=7), days=["monday"])
    _call(client, identifier=1, active=True)

    assert len(sent) == 2
    assert len(_entries(sent[1:])) == 3

    electric = client.cars[SYNTH_VIN].electric
    assert len(electric.weeklyProfileTimeProfiles.value) == 3
    assert electric.weeklyProfileTimeProfiles.value[2]["time"] == "07:00"
