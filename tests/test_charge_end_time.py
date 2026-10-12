"""The charge end time follows the car, including when the car stops predicting one.

CLA 2025 and newer cars have no endofchargetime attribute. Their charge end
time is a Timestamp inside charging_prediction_max_soc, and when charging ends
the car keeps sending that attribute but drops the Timestamp from it. Being a
message field it has explicit presence, so that is a statement and not an
elided proto3 default - the sensor has to follow it rather than keep showing a
charge end time that has already passed.

The distinction these tests pin is between the attribute arriving without the
timestamp and the attribute not arriving at all: only the first says anything.
"""

from __future__ import annotations

from custom_components.mbapi2020.client import Client
from homeassistant.const import STATE_UNKNOWN

from .conftest import make_client
from .fixtures.build import SYNTH_VIN, build_charging_prediction_status_updates, roundtrip


def _client_with(*messages) -> Client:
    """Feed a sequence of VSU messages to one client, in order."""
    client = make_client()
    for message in messages:
        client._process_vehicle_status_updates(roundtrip(message))
    return client


def _end_of_charge(client: Client):
    return client.cars[SYNTH_VIN].electric.endofchargetime


def test_the_predicted_end_time_becomes_the_sensor_state() -> None:
    """A prediction in the message is reported as an aware ISO 8601 timestamp."""
    attribute = _end_of_charge(_client_with(build_charging_prediction_status_updates()))

    assert attribute.display_value == "2026-10-13T12:52:24+00:00"
    assert attribute.value.tzinfo is not None


def test_a_partial_update_that_drops_the_prediction_clears_the_state() -> None:
    """The regression: charging ends on a partial update, and the state has to follow.

    The car sends charging_prediction_max_soc with only the range left in it
    in the same partial update that reports CHARGINGSTATUS_NO_CHARGING. Full
    updates can be hours apart, so waiting for one left the sensor pointing at
    a charge end time in the future that the car had already abandoned.
    """
    client = _client_with(
        build_charging_prediction_status_updates(),
        build_charging_prediction_status_updates(full_update=False, predicted_end_time_seconds=None),
    )

    assert _end_of_charge(client).display_value == STATE_UNKNOWN


def test_a_partial_update_without_the_attribute_keeps_the_state() -> None:
    """Most partial updates do not mention the attribute, and say nothing about it.

    Resetting on those would wipe a perfectly good prediction on the next
    unrelated message about the doors or the odometer.
    """
    client = _client_with(
        build_charging_prediction_status_updates(),
        build_charging_prediction_status_updates(full_update=False, with_prediction=False),
    )

    assert _end_of_charge(client).display_value == "2026-10-13T12:52:24+00:00"


def test_a_full_update_without_the_attribute_still_creates_the_entity() -> None:
    """A full update that mentions neither attribute means the car reports no charge end time.

    The entity has to exist all the same, so a car that never sends either
    attribute does not silently lack the sensor.
    """
    client = _client_with(
        build_charging_prediction_status_updates(full_update=True, with_prediction=False),
    )

    assert _end_of_charge(client).display_value == STATE_UNKNOWN


def test_the_legacy_attribute_wins_over_an_empty_prediction() -> None:
    """Older cars send an empty charging_prediction_max_soc next to endofchargetime.

    Their value comes from the legacy minutes-after-midnight attribute, so the
    empty prediction must not reset them to unknown.
    """
    client = _client_with(
        build_charging_prediction_status_updates(
            full_update=True,
            predicted_end_time_seconds=None,
            endofchargetime_minutes=18 * 60 + 30,
        ),
    )
    attribute = _end_of_charge(client)

    assert attribute.display_value != STATE_UNKNOWN
    # The legacy attribute is a wall clock time, anchored in the timezone Home
    # Assistant is configured for, so the offset depends on that setting and
    # only the local time itself can be asserted.
    assert (attribute.value.hour, attribute.value.minute) == (18, 30)
    assert attribute.value.tzinfo is not None
