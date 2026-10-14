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


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    domain = hass.data[DOMAIN][config_entry.entry_id]

    data = {"entry": config_entry.as_dict(), "cars": []}

    for car in domain.client.cars.values():
        masked_vin = loghelper.Mask_VIN(car.finorvin)
        car_json = json.dumps(car, cls=MBJSONEncoder)
        # Entity IDs and other values embed the VIN, which key-based redaction does not catch
        identifiers = {car.finorvin, car.masterdata.get("fin"), car.masterdata.get("vin")}
        for identifier in identifiers:
            if isinstance(identifier, str) and identifier:
                car_json = re.sub(
                    re.escape(identifier), lambda m: loghelper.Mask_VIN(m.group(0)), car_json, flags=re.IGNORECASE
                )
        data["cars"].append({masked_vin: json.loads(car_json)})

    return async_redact_data(data, JSON_EXPORT_IGNORED_KEYS)
