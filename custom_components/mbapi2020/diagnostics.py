"""Diagnostics support for MBAPI2020."""

from __future__ import annotations

import json
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
        data["cars"].append({loghelper.Mask_VIN(car.finorvin): json.loads(json.dumps(car, cls=MBJSONEncoder))})

    return async_redact_data(data, JSON_EXPORT_IGNORED_KEYS)
