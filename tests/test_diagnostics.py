"""The diagnostics report must not leak the VIN or the car's position.

async_redact_data only redacts by key, so a VIN embedded in a value - an
entity ID in car.sensors, for example - passed through unmasked. The
latitude is kept but rounded to whole degrees.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from custom_components.mbapi2020.car import Car, CarAttribute, Location
from custom_components.mbapi2020.const import DOMAIN
from custom_components.mbapi2020.diagnostics import _mask_vin_serial, async_get_config_entry_diagnostics

from .conftest import SYNTH_FIN, SYNTH_VIN


def _diagnostics_for(car: Car) -> dict:
    entry = SimpleNamespace(entry_id="entry", as_dict=dict)
    client = SimpleNamespace(cars={car.finorvin: car})
    hass = SimpleNamespace(data={DOMAIN: {"entry": SimpleNamespace(client=client)}})
    return asyncio.run(async_get_config_entry_diagnostics(hass, entry))


def test_sensor_entity_ids_keep_their_key_with_the_vin_masked() -> None:
    """Entity IDs embed the lower-cased VIN; it must be masked, the list kept."""
    car = Car(SYNTH_VIN)
    car.sensors = {f"sensor.{SYNTH_VIN.lower()}_soc", f"binary_sensor.{SYNTH_VIN.lower()}_chargingactive"}

    report = _diagnostics_for(car)
    sensors = report["cars"][0]["W1NKM5BB6VUXXXXXX"]["sensors"]

    assert sensors == [
        "binary_sensor.w1nkm5bb6vuXXXXXX_chargingactive",
        "sensor.w1nkm5bb6vuXXXXXX_soc",
    ]
    assert SYNTH_VIN.lower() not in str(report).lower()


def test_fin_from_masterdata_is_masked_in_values() -> None:
    """A FIN that differs from the VIN must not leak through a value either."""
    car = Car(SYNTH_VIN)
    car.masterdata = {"fin": SYNTH_FIN}
    car.baumuster_description = f"built as {SYNTH_FIN}"

    report = _diagnostics_for(car)

    assert SYNTH_FIN.lower() not in str(report).lower()


def test_serializing_does_not_write_properties_into_the_car() -> None:
    """MBJSONEncoder used to update the object's own __dict__ with its properties."""
    car = Car(SYNTH_VIN)
    attributes_before = set(vars(car))

    _diagnostics_for(car)

    assert set(vars(car)) == attributes_before


def test_latitude_is_rounded_to_whole_degrees() -> None:
    """Covers positionLat in the parsed location and in the raw last full message."""
    car = Car(SYNTH_VIN)
    car.location = Location()
    car.location.positionLat = CarAttribute(48.737154, "VALID", 1791296971, display_value="48.737154")
    car.last_full_message = {
        "attributes": {
            "positionLat": {"double_value": 48.737154, "display_value": "48.737154", "timestamp": "1791296971"},
        },
    }

    car_report = _diagnostics_for(car)["cars"][0]["W1NKM5BB6VUXXXXXX"]

    location = car_report["location"]["positionLat"]
    assert (location["value"], location["display_value"], location["timestamp"]) == (49, "49", 1791296971)
    raw = car_report["last_full_message"]["attributes"]["positionLat"]
    assert raw == {"double_value": 49, "display_value": "49", "timestamp": "1791296971"}
    assert "737154" not in str(car_report)


def test_keys_that_only_contain_lat_are_left_alone() -> None:
    """Matching is on latitude keys, not on any key with lat in it."""
    car = Car(SYNTH_VIN)
    car.last_full_message = {"attributes": {"precondClimate": {"double_value": 21.5}, "translation": "1.5"}}

    car_report = _diagnostics_for(car)["cars"][0]["W1NKM5BB6VUXXXXXX"]

    assert car_report["last_full_message"] == car.last_full_message


def test_only_the_serial_number_of_a_vin_is_masked() -> None:
    """Positions 1-11 identify the vehicle type, 12-17 are the serial number."""
    assert _mask_vin_serial("W1NKM5BB6VU123456") == "W1NKM5BB6VUXXXXXX"
    assert _mask_vin_serial("w1nkm5bb6vu123456") == "w1nkm5bb6vuXXXXXX"
    # not a VIN: the log masking keeps less, never more
    assert _mask_vin_serial("ABC123") == "XXXXXX"
