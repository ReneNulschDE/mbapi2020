"""The two smart charging objects reach the entity layer as four attributes.

Fields 276 and 277 only arrive on vehicles whose charging a provider manages,
which none of the development cars does. These tests are the only place the
split is exercised, so they pin it: which attribute reads which field, how the
most severe error is picked, and what happens to the keys proto3 drops.
"""

from __future__ import annotations

from custom_components.mbapi2020.car import ELECTRIC_OPTIONS
from custom_components.mbapi2020.const import SENSORS, SensorConfigFields as scf

from .conftest import make_client
from .fixtures.build import SYNTH_VIN, build_smart_charging_status_updates, build_vehicle_status_updates, roundtrip

_SENSOR_KEYS = (
    "smartcharginglocation",
    "smartchargingstation",
    "smartchargingstrategy",
    "smartchargingerror",
)


def _electric(**kwargs):
    """Parse a smart charging VSU message and return the Electric group."""
    client = make_client()
    client._process_vehicle_status_updates(roundtrip(build_smart_charging_status_updates(**kwargs)))
    return client.cars[SYNTH_VIN].electric


def test_the_information_object_feeds_three_separate_attributes() -> None:
    """One object on the wire, one attribute per sensor."""
    electric = _electric()

    assert electric.smartChargingLocation.value == "Home"
    assert electric.smartChargingStation.value == "Garage Wallbox"
    assert electric.smartChargingStrategy.value == "immediate"


def test_a_field_the_vehicle_omits_only_affects_its_own_sensor() -> None:
    """An empty string is dropped by proto3, and must not take the siblings down.

    A vehicle that charges at a provider without naming the station reports
    exactly this, so the station sensor reads unknown while location and
    strategy stay valid.
    """
    electric = _electric(charging_station_name=None)

    assert electric.smartChargingStation.value is None
    assert electric.smartChargingLocation.value == "Home"
    assert electric.smartChargingStrategy.value == "immediate"


def test_the_error_state_names_the_most_severe_entry_not_the_first() -> None:
    """Severity decides, and the proto numbers it the other way round.

    MAJOR_ERROR is 1 and WARNING is 3, so picking by number or by name would
    report the warning that happens to come first.
    """
    electric = _electric(
        errors=(
            ("UNAVAILABLE_WITHOUT_OPTIMIZATION", "WARNING"),
            ("UNAVAILABLE_MISSING_VEHICLE_CONNECTION", "MAJOR_ERROR"),
        )
    )

    assert electric.smartChargingError.value == "UNAVAILABLE_MISSING_VEHICLE_CONNECTION"


def test_every_reported_error_stays_reachable_with_its_severity() -> None:
    """The list is the sensor's attribute, so no error is lost to the state."""
    errors = _electric(
        errors=(
            ("UNAVAILABLE_DIRECT_CHARGING_MODE", "MINOR_ERROR"),
            ("UNAVAILABLE_WITHOUT_OPTIMIZATION", "WARNING"),
        )
    ).smartChargingErrorList.value

    assert errors == [
        {"code": "UNAVAILABLE_DIRECT_CHARGING_MODE", "severity": "MINOR_ERROR"},
        {"code": "UNAVAILABLE_WITHOUT_OPTIMIZATION", "severity": "WARNING"},
    ]


def test_the_unknown_enum_values_are_defaulted_not_dropped() -> None:
    """Both enums have their unknown value at 0, which proto3 omits.

    Without defaulting, an entry would arrive as {} and a template would need
    a different expression depending on what the vehicle sent.
    """
    electric = _electric(errors=(("UNKNOWN_CODE", "UNKNOWN_SEVERITY"),))

    assert electric.smartChargingErrorList.value == [{"code": "UNKNOWN_CODE", "severity": "UNKNOWN_SEVERITY"}]
    # An unknown severity still has to win when it is the only entry.
    assert electric.smartChargingError.value == "UNKNOWN_CODE"


def test_an_object_without_entries_leaves_the_state_unset() -> None:
    """No error reported is not an error: the sensor reads unknown.

    Reporting a made-up "none" would be a value the vehicle never sent.
    """
    electric = _electric(errors=())

    assert electric.smartChargingError.value is None
    assert electric.smartChargingErrorList.value == []


def test_a_vehicle_without_smart_charging_gets_no_attributes() -> None:
    """Without the objects on the wire, none of the five attributes is set.

    This is what keeps the four sensors off every car that is not managed by a
    provider: the handler returns None, so nothing is assigned and no entity
    is created.
    """
    client = make_client()
    client._process_vehicle_status_updates(roundtrip(build_vehicle_status_updates()))
    electric = client.cars[SYNTH_VIN].electric

    for attribute in (
        "smartChargingLocation",
        "smartChargingStation",
        "smartChargingStrategy",
        "smartChargingError",
        "smartChargingErrorList",
    ):
        assert not hasattr(electric, attribute)


def test_a_partial_update_without_the_objects_keeps_the_values() -> None:
    """The objects do not repeat in every update, and must not be wiped."""
    client = make_client()
    client._process_vehicle_status_updates(roundtrip(build_smart_charging_status_updates()))

    partial = build_smart_charging_status_updates()
    update = partial.vehicle_status_updates.vehicle_status_updates[SYNTH_VIN]
    update.full_update = False
    update.ClearField("smart_charging_information")
    update.ClearField("smart_charging_error")
    client._process_vehicle_status_updates(roundtrip(partial))

    electric = client.cars[SYNTH_VIN].electric
    assert electric.smartChargingLocation.value == "Home"
    assert electric.smartChargingError.value == "UNAVAILABLE_DIRECT_CHARGING_MODE"


def test_the_sensors_read_attributes_the_parser_produces() -> None:
    """Each sensor definition has to line up with the split above."""
    for key in _SENSOR_KEYS:
        config = SENSORS[key]
        assert config[scf.OBJECT_NAME.value] == "electric"
        assert config[scf.VALUE_FIELD_NAME.value] == "value"
        assert config[scf.ATTRIBUTE_NAME.value] in ELECTRIC_OPTIONS
        for attribute in config[scf.EXTENDED_ATTRIBUTE_LIST.value]:
            assert attribute.removeprefix("electric.") in ELECTRIC_OPTIONS


def test_the_error_list_hangs_off_the_error_sensor_and_has_none_of_its_own() -> None:
    """The list is an attribute, not a state - no sensor may read it."""
    assert SENSORS["smartchargingerror"][scf.EXTENDED_ATTRIBUTE_LIST.value] == {"electric.smartChargingErrorList"}
    assert "smartChargingErrorList" in ELECTRIC_OPTIONS
    for config in SENSORS.values():
        assert config[scf.ATTRIBUTE_NAME.value] != "smartChargingErrorList"


def test_the_sensors_are_normal_ones_with_no_state_class() -> None:
    """Normal sensors, so they stay visible and can be evaluated.

    A diagnostic entity would be kept off the dashboards. state_class has to
    stay unset all the same: every one of these states is text, and long-term
    statistics need a number.
    """
    for key in _SENSOR_KEYS:
        config = SENSORS[key]
        assert config[scf.ENTITY_CATEGORY.value] is None
        assert config[scf.STATE_CLASS.value] is None
        assert config[scf.DEVICE_CLASS.value] is None


def test_a_cleared_object_clears_the_sensors() -> None:
    """A vehicle that stops reporting values must not leave the old ones.

    proto3 drops a value whose fields are all empty, so a cleared error or a
    forgotten station name arrives as metadata with no value. That has to
    reach the sensors - unlike an update that leaves the object out, which
    keeps them.
    """
    client = make_client()
    client._process_vehicle_status_updates(roundtrip(build_smart_charging_status_updates()))

    cleared = build_smart_charging_status_updates(
        location_name=None,
        charging_station_name=None,
        charging_strategy=None,
        errors=(),
    )
    client._process_vehicle_status_updates(roundtrip(cleared))

    electric = client.cars[SYNTH_VIN].electric
    assert electric.smartChargingError.value is None
    assert electric.smartChargingErrorList.value == []
    assert electric.smartChargingLocation.value is None
    assert electric.smartChargingStrategy.value is None
