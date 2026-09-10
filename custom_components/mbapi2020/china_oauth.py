"""Frontend helper for the official China device-code login."""

from __future__ import annotations

import logging
from pathlib import Path
import time
from typing import TYPE_CHECKING, Any
import urllib.parse

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

CHINA_OAUTH_OPENER_JS = "/mbapi2020/flow-opener.js"
CHINA_OAUTH_FLOW_TTL_SECONDS = 600


def _china_oauth_flows(hass: HomeAssistant) -> dict[str, dict[str, Any]]:
    """Return China device-login wrappers keyed by config flow id."""
    return hass.data.setdefault(DOMAIN, {}).setdefault("china_oauth_flows", {})


def register_china_oauth_flow(
    hass: HomeAssistant, flow_id: str, user_code: str, login_url: str
) -> None:
    """Store the official Connect-a-device URL for the wrapper page."""
    _china_oauth_flows(hass)[flow_id] = {
        "user_code": user_code,
        "login_url": login_url,
        "expires_at": time.monotonic() + CHINA_OAUTH_FLOW_TTL_SECONDS,
    }


def unregister_china_oauth_flow(hass: HomeAssistant, flow_id: str) -> None:
    """Remove a China device-login wrapper context."""
    _china_oauth_flows(hass).pop(flow_id, None)


def build_china_oauth_static_url(user_code: str, login_url: str) -> str:
    """Return the same-origin wrapper URL that shows the device code."""
    query = urllib.parse.urlencode({"user_code": user_code, "login_url": login_url})
    return f"/mbapi2020/oauth.html?{query}"


async def setup_china_oauth_frontend(hass: HomeAssistant) -> None:
    """Register the China login wrapper and the config-flow opener script."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get("china_oauth_frontend_registered"):
        return

    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                "/mbapi2020",
                str(Path(__file__).parent / "www"),
                False,
            )
        ]
    )
    frontend.add_extra_js_url(hass, CHINA_OAUTH_OPENER_JS)
    domain_data["china_oauth_frontend_registered"] = True
    _LOGGER.debug("Registered mbapi2020 China OAuth frontend helper")
