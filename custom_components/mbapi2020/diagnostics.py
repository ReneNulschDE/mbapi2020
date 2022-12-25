"""Diagnostics support for MBAPI2020."""
from __future__ import annotations
import json
from json import JSONEncoder
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    domain = hass.data[DOMAIN]

    data = {
        "entry": entry.as_dict(),
        "cars" : json.dumps(domain.client.cars, indent=4, cls=MBAPIEncoder)
    }

    return async_redact_data(data, ("pin", "access_token", "refresh_token", "username", "unique_id", "nounce"))


class MBAPIEncoder(JSONEncoder):
    """Custom JSON Encoder for MBAPI2020."""

    def default(self, o):
        if isinstance(o, set):
            return list(o)
        return o.__dict__
