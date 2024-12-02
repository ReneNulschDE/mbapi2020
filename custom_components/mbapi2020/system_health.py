"""Provide info to system health."""

from __future__ import annotations

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback
from homeassistant.loader import async_get_integration

from .const import DOMAIN, REST_API_BASE
from .coordinator import MBAPI2020DataUpdateCoordinator


@callback
def async_register(hass: HomeAssistant, register: system_health.SystemHealthRegistration) -> None:
    """Register system health callbacks."""
    register.async_register_info(system_health_info)


async def system_health_info(hass: HomeAssistant):
    """Get info for the info page."""

    integration = await async_get_integration(hass, DOMAIN)

    if DOMAIN in hass.data:
        domain = hass.data[DOMAIN]
        first_coordinator: MBAPI2020DataUpdateCoordinator = None
        used_cars: int = 0

        for key in iter(domain):
            if isinstance(domain[key], MBAPI2020DataUpdateCoordinator):
                coordinator = domain[key]
                if not first_coordinator:
                    first_coordinator = coordinator

                if coordinator.client and coordinator.client.cars:
                    used_cars += len(coordinator.client.cars)

        if first_coordinator and first_coordinator.client and first_coordinator.client.websocket:
            websocket_connection_state = str(first_coordinator.client.websocket.connection_state)
        else:
            websocket_connection_state = "unknown"

        return {
            "api_endpoint_reachable": system_health.async_check_can_reach_url(hass, REST_API_BASE),
            "websocket_connection_state": websocket_connection_state,
            "cars_connected": used_cars,
            "version": integration.manifest.get("version"),
        }

    return {
        "status": "Disabled/Deleted",
        "version": integration.manifest.get("version"),
    }
