"""The diagnostics report must not leak the VIN through values.

async_redact_data only redacts by key, so a VIN embedded in a value - an
entity ID in car.sensors, for example - passed through unmasked.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from custom_components.mbapi2020.car import Car
from custom_components.mbapi2020.const import DOMAIN
from custom_components.mbapi2020.diagnostics import async_get_config_entry_diagnostics
from custom_components.mbapi2020.helper import LogHelper as loghelper

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
    masked_vin = loghelper.Mask_VIN(SYNTH_VIN)
    sensors = report["cars"][0][masked_vin]["sensors"]

    assert sensors == [
        f"binary_sensor.{loghelper.Mask_VIN(SYNTH_VIN.lower())}_chargingactive",
        f"sensor.{loghelper.Mask_VIN(SYNTH_VIN.lower())}_soc",
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
