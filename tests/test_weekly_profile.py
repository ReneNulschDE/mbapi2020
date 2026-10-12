"""The weekly departure profile reaches the entity layer intact.

The vehicle sends the whole profile as one nested object. The parser splits
it into three car attributes - the active entry, the entries themselves and
the vehicle's capacity limits - so these tests pin that split and the
defaulting of the fields proto3 drops when they carry their zero value.
"""

from __future__ import annotations

from custom_components.mbapi2020.car import ELECTRIC_OPTIONS
from custom_components.mbapi2020.const import SENSORS, SensorConfigFields as scf
from homeassistant.const import EntityCategory

from .conftest import make_client
from .fixtures.build import SYNTH_VIN, build_weekly_profile_status_updates, roundtrip


def _electric(**kwargs):
    """Parse a weekly-profile VSU message and return the Electric group."""
    client = make_client()
    client._process_vehicle_status_updates(roundtrip(build_weekly_profile_status_updates(**kwargs)))
    return client.cars[SYNTH_VIN].electric


def test_the_active_entry_identifier_is_the_sensor_state() -> None:
    """The state names the entry the vehicle currently follows."""
    assert _electric().weeklyProfileActive.value == 1


def test_the_active_entry_is_found_by_its_flag_not_its_position() -> None:
    """Activating the second entry must move the state to its identifier.

    The first entry is the active one in the default fixture, so a handler
    that simply took time_profiles[0] would pass that case by accident.
    """
    assert _electric(active_identifier=2).weeklyProfileActive.value == 2


def test_no_active_entry_leaves_the_state_unset() -> None:
    """Entries without an active one must not fall back to the first.

    Several captured vehicles report their entries with no active flag at
    all. The sensor then has to read unknown rather than name an entry the
    vehicle is not following.
    """
    electric = _electric(active_identifier=None)

    assert electric.weeklyProfileActive.value is None
    assert len(electric.weeklyProfileTimeProfiles.value) == 2


def test_entries_are_flattened_for_templating() -> None:
    """Each entry arrives as a flat dict with a ready-made time string."""
    profiles = _electric().weeklyProfileTimeProfiles.value

    assert [entry["identifier"] for entry in profiles] == [1, 2]
    first = profiles[0]
    assert first["time"] == "20:50"
    assert first["hour"] == 20
    assert first["minute"] == 50
    assert first["days"] == ["TUESDAY"]
    assert first["active"] is True
    assert profiles[1]["active"] is False
    assert first["actions"] == {"charging": True, "precond": True, "battery_precond": False}
    assert first["schedule_type"] == "RECURRING"


def test_omitted_scalars_are_defaulted_not_dropped() -> None:
    """The sparse entry keeps every key, with the proto3 defaults filled in.

    A departure at 00:05 arrives without "hour" and an inactive entry without
    "active". Both have to be present in the attribute, otherwise a template
    would need a different expression per vehicle.
    """
    sparse = _electric().weeklyProfileTimeProfiles.value[1]

    assert sparse["time"] == "00:05"
    assert sparse["hour"] == 0
    assert sparse["active"] is False
    assert sparse["days"] == []
    assert sparse["actions"] == {"charging": False, "precond": False, "battery_precond": False}
    # NON_RECURRING is the zero value of the enum, so an omitted schedule type
    # cannot be told apart from a one-off entry: it stays empty rather than
    # claiming the entry runs once.
    assert sparse["schedule_type"] is None


def test_capacity_limits_are_exposed() -> None:
    """The limits decide how many entries a configure command may send."""
    assert _electric().weeklyProfileLimits.value == {
        "max_time_profiles": 16,
        "max_time_profiles_user": 10,
        "max_weekly_time_profile_slots": 112,
        "current_time_profile_slots": 2,
        "single_entries_activatable": True,
    }


def test_a_message_without_the_profile_leaves_the_attributes_untouched() -> None:
    """A partial update that omits weeklyProfile must not wipe a good value.

    The profile only ever arrives in full updates, so every partial update in
    between reaches the handler with no payload at all.
    """
    client = make_client()
    client._process_vehicle_status_updates(roundtrip(build_weekly_profile_status_updates()))

    partial = build_weekly_profile_status_updates()
    update = partial.vehicle_status_updates.vehicle_status_updates[SYNTH_VIN]
    update.full_update = False
    update.ClearField("weekly_profile")
    client._process_vehicle_status_updates(roundtrip(partial))

    assert client.cars[SYNTH_VIN].electric.weeklyProfileActive.value == 1


def test_sensor_definition_matches_the_parsed_attributes() -> None:
    """The sensor reads attributes the parser actually produces."""
    config = SENSORS["activeweeklyprofile"]

    assert config[scf.ATTRIBUTE_NAME.value] == "weeklyProfileActive"
    assert config[scf.OBJECT_NAME.value] == "electric"
    for option in ("weeklyProfileActive", "weeklyProfileTimeProfiles", "weeklyProfileLimits"):
        assert option in ELECTRIC_OPTIONS
    for attribute in config[scf.EXTENDED_ATTRIBUTE_LIST.value]:
        assert attribute.removeprefix("electric.") in ELECTRIC_OPTIONS


def test_the_sensor_is_diagnostic_and_keeps_out_of_the_statistics() -> None:
    """Vehicle configuration, so no dashboard tile and no long-term statistic.

    A state_class would make the recorder derive statistics from an entry
    identifier, which is a label and not a measurement.
    """
    config = SENSORS["activeweeklyprofile"]

    assert config[scf.ENTITY_CATEGORY.value] is EntityCategory.DIAGNOSTIC
    assert config[scf.STATE_CLASS.value] is None
