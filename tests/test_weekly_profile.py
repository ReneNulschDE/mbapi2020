"""The weekly departure profile reaches the entity layer intact.

The vehicle sends the whole profile as one nested object. The parser splits
it into three car attributes - the number of entries, the entries themselves
and the vehicle's capacity limits - so these tests pin that split and the
defaulting of the fields proto3 drops when they carry their zero value.
"""

from __future__ import annotations

from custom_components.mbapi2020.car import ELECTRIC_OPTIONS
from custom_components.mbapi2020.const import SENSORS, SensorConfigFields as scf

from .conftest import make_client
from .fixtures.build import SYNTH_VIN, build_weekly_profile_status_updates, roundtrip


def _electric(**kwargs):
    """Parse a weekly-profile VSU message and return the Electric group."""
    client = make_client()
    client._process_vehicle_status_updates(roundtrip(build_weekly_profile_status_updates(**kwargs)))
    return client.cars[SYNTH_VIN].electric


def test_profile_count_is_the_sensor_state() -> None:
    """The weeklyProfile attribute carries the number of configured entries."""
    assert _electric().weeklyProfile.value == 2


def test_profile_count_falls_back_to_the_list_length() -> None:
    """A vehicle that omits the count must not report zero entries.

    current_number_of_time_profiles is a proto3 int32, so a vehicle that
    leaves it at zero sends no key at all - while still sending the entries.
    """
    assert _electric(reported_profile_count=None).weeklyProfile.value == 2


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

    assert client.cars[SYNTH_VIN].electric.weeklyProfile.value == 2


def test_sensor_definition_matches_the_parsed_attributes() -> None:
    """The sensor reads attributes the parser actually produces."""
    config = SENSORS["weeklyprofile"]

    assert config[scf.ATTRIBUTE_NAME.value] == "weeklyProfile"
    assert config[scf.OBJECT_NAME.value] == "electric"
    for option in ("weeklyProfile", "weeklyProfileTimeProfiles", "weeklyProfileLimits"):
        assert option in ELECTRIC_OPTIONS
    for attribute in config[scf.EXTENDED_ATTRIBUTE_LIST.value]:
        assert attribute.removeprefix("electric.") in ELECTRIC_OPTIONS
