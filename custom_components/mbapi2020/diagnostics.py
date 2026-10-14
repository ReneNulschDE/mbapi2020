"""Diagnostics support for MBAPI2020."""

from __future__ import annotations

import json
import re
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, JSON_EXPORT_IGNORED_KEYS
from .helper import LogHelper as loghelper, MBJSONEncoder

VIN_LENGTH = 17
VIN_SERIAL_LENGTH = 6


def _mask_vin_serial(vin: str) -> str:
    """Mask the serial number (positions 12-17) of a VIN or FIN.

    Positions 1-11 (manufacturer, model series, variant, model year, plant)
    stay readable so the vehicle type can still be told from the report.
    Anything that is not a 17-character VIN falls back to Mask_VIN.
    """
    if len(vin) == VIN_LENGTH:
        return vin[:-VIN_SERIAL_LENGTH] + "X" * VIN_SERIAL_LENGTH
    return loghelper.Mask_VIN(vin)


def _is_latitude_key(key: str) -> bool:
    key = key.lower()
    return key in ("lat", "positionlat") or key.endswith("latitude")


def _round_coordinate(value: Any) -> Any:
    """Round a coordinate to whole degrees, recursing into attribute dicts and lists."""
    if isinstance(value, dict):
        return {k: _round_coordinate(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_round_coordinate(v) for v in value]
    if isinstance(value, float):
        return round(value)
    if isinstance(value, str) and "." in value:
        try:
            return str(round(float(value)))
        except ValueError:
            return value
    return value


def _round_latitudes(value: Any) -> Any:
    """Round every value stored under a latitude key so the report does not pinpoint the car."""
    if isinstance(value, dict):
        return {
            k: _round_coordinate(v) if isinstance(k, str) and _is_latitude_key(k) else _round_latitudes(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_round_latitudes(v) for v in value]
    return value


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    domain = hass.data[DOMAIN][config_entry.entry_id]

    data = {"entry": config_entry.as_dict(), "cars": []}

    for car in domain.client.cars.values():
        masked_vin = _mask_vin_serial(car.finorvin)
        car_json = json.dumps(car, cls=MBJSONEncoder)
        # Entity IDs and other values embed the VIN, which key-based redaction does not catch
        identifiers = {car.finorvin, car.masterdata.get("fin"), car.masterdata.get("vin")}
        for identifier in identifiers:
            if isinstance(identifier, str) and identifier:
                car_json = re.sub(
                    re.escape(identifier), lambda m: _mask_vin_serial(m.group(0)), car_json, flags=re.IGNORECASE
                )
        data["cars"].append({masked_vin: _round_latitudes(json.loads(car_json))})

    return async_redact_data(data, JSON_EXPORT_IGNORED_KEYS)
