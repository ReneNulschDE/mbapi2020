"""Services for the Blink integration."""
from __future__ import annotations

from homeassistant.core import HomeAssistant

from .const import (
    CONF_PIN,
    CONF_TIME,
    CONF_VIN,
    DOMAIN,
    LOGGER,
    SERVICE_AUXHEAT_CONFIGURE,
    SERVICE_AUXHEAT_CONFIGURE_SCHEMA,
    SERVICE_AUXHEAT_START,
    SERVICE_AUXHEAT_STOP,
    SERVICE_BATTERY_MAX_SOC_CONFIGURE,
    SERVICE_BATTERY_MAX_SOC_CONFIGURE_SCHEMA,
    SERVICE_DOORS_LOCK_URL,
    SERVICE_DOORS_UNLOCK_URL,
    SERVICE_ENGINE_START,
    SERVICE_ENGINE_STOP,
    SERVICE_PREHEAT_START,
    SERVICE_PREHEAT_START_DEPARTURE_TIME,
    SERVICE_PREHEAT_START_SCHEMA,
    SERVICE_PREHEAT_STOP,
    SERVICE_PREHEAT_STOP_DEPARTURE_TIME,
    SERVICE_REFRESH_TOKEN_URL,
    SERVICE_SEND_ROUTE,
    SERVICE_SEND_ROUTE_SCHEMA,
    SERVICE_SIGPOS_START,
    SERVICE_SUNROOF_CLOSE,
    SERVICE_SUNROOF_OPEN,
    SERVICE_VIN_PIN_SCHEMA,
    SERVICE_VIN_SCHEMA,
    SERVICE_VIN_TIME_SCHEMA,
    SERVICE_WINDOWS_CLOSE,
    SERVICE_WINDOWS_OPEN,
)


def setup_services(hass: HomeAssistant) -> None:
    """Set up the services for the MBAPI2020 integration."""

    async def refresh_access_token(call) -> None:
        await hass.data[DOMAIN].client.oauth.async_get_cached_token()

    async def auxheat_configure(call) -> None:
        await hass.data[DOMAIN].client.auxheat_configure(
            call.data.get(CONF_VIN),
            call.data.get("time_selection"),
            call.data.get("time_1"),
            call.data.get("time_2"),
            call.data.get("time_3"),
        )

    async def auxheat_start(call) -> None:
        await hass.data[DOMAIN].client.auxheat_start(call.data.get(CONF_VIN))

    async def auxheat_stop(call) -> None:
        await hass.data[DOMAIN].client.auxheat_stop(call.data.get(CONF_VIN))

    async def doors_unlock(call) -> None:
        await hass.data[DOMAIN].client.doors_unlock(call.data.get(CONF_VIN), call.data.get(CONF_PIN))

    async def doors_lock(call) -> None:
        await hass.data[DOMAIN].client.doors_lock(call.data.get(CONF_VIN))

    async def engine_start(call) -> None:
        await hass.data[DOMAIN].client.engine_start(call.data.get(CONF_VIN))

    async def engine_stop(call) -> None:
        await hass.data[DOMAIN].client.engine_stop(call.data.get(CONF_VIN))

    async def sigpos_start(call) -> None:
        await hass.data[DOMAIN].client.sigpos_start(call.data.get(CONF_VIN))

    async def sunroof_open(call) -> None:
        await hass.data[DOMAIN].client.sunroof_open(call.data.get(CONF_VIN))

    async def sunroof_close(call) -> None:
        await hass.data[DOMAIN].client.sunroof_close(call.data.get(CONF_VIN))

    async def preheat_start(call) -> None:
        if call.data.get("type", 0) == 0:
            await hass.data[DOMAIN].client.preheat_start(call.data.get(CONF_VIN))
        else:
            await hass.data[DOMAIN].client.preheat_start_immediate(call.data.get(CONF_VIN))

    async def preheat_start_departure_time(call) -> None:
        await hass.data[DOMAIN].client.preheat_start_departure_time(call.data.get(CONF_VIN), call.data.get(CONF_TIME))

    async def preheat_stop(call) -> None:
        await hass.data[DOMAIN].client.preheat_stop(call.data.get(CONF_VIN))

    async def preheat_stop_departure_time(call) -> None:
        await hass.data[DOMAIN].client.preheat_stop_departure_time(call.data.get(CONF_VIN))

    async def windows_open(call) -> None:
        await hass.data[DOMAIN].client.windows_open(call.data.get(CONF_VIN))

    async def windows_close(call) -> None:
        await hass.data[DOMAIN].client.windows_close(call.data.get(CONF_VIN))

    async def send_route_to_car(call) -> None:
        await hass.data[DOMAIN].client.send_route_to_car(
            call.data.get(CONF_VIN),
            call.data.get("title"),
            call.data.get("latitude"),
            call.data.get("longitude"),
            call.data.get("city"),
            call.data.get("postcode"),
            call.data.get("street"),
        )

    async def battery_max_soc_configure(call) -> None:
        await hass.data[DOMAIN].client.battery_max_soc_configure(call.data.get(CONF_VIN), call.data.get("max_soc"))

    # Register all the above services
    service_mapping = [
        (SERVICE_REFRESH_TOKEN_URL, refresh_access_token, None),
        (
            SERVICE_AUXHEAT_CONFIGURE,
            auxheat_configure,
            SERVICE_AUXHEAT_CONFIGURE_SCHEMA,
        ),
        (SERVICE_AUXHEAT_START, auxheat_start, SERVICE_VIN_SCHEMA),
        (SERVICE_AUXHEAT_STOP, auxheat_stop, SERVICE_VIN_SCHEMA),
        (
            SERVICE_BATTERY_MAX_SOC_CONFIGURE,
            battery_max_soc_configure,
            SERVICE_BATTERY_MAX_SOC_CONFIGURE_SCHEMA,
        ),
        (SERVICE_DOORS_LOCK_URL, doors_lock, SERVICE_VIN_SCHEMA),
        (SERVICE_DOORS_UNLOCK_URL, doors_unlock, SERVICE_VIN_PIN_SCHEMA),
        (SERVICE_ENGINE_START, engine_start, SERVICE_VIN_SCHEMA),
        (SERVICE_ENGINE_STOP, engine_stop, SERVICE_VIN_SCHEMA),
        (SERVICE_PREHEAT_START, preheat_start, SERVICE_PREHEAT_START_SCHEMA),
        (
            SERVICE_PREHEAT_START_DEPARTURE_TIME,
            preheat_start_departure_time,
            SERVICE_VIN_TIME_SCHEMA,
        ),
        (SERVICE_PREHEAT_STOP, preheat_stop, SERVICE_VIN_SCHEMA),
        (
            SERVICE_PREHEAT_STOP_DEPARTURE_TIME,
            preheat_stop_departure_time,
            SERVICE_VIN_SCHEMA,
        ),
        (SERVICE_SEND_ROUTE, send_route_to_car, SERVICE_SEND_ROUTE_SCHEMA),
        (SERVICE_SIGPOS_START, sigpos_start, SERVICE_VIN_SCHEMA),
        (SERVICE_SUNROOF_OPEN, sunroof_open, SERVICE_VIN_SCHEMA),
        (SERVICE_SUNROOF_CLOSE, sunroof_close, SERVICE_VIN_SCHEMA),
        (SERVICE_WINDOWS_OPEN, windows_open, SERVICE_VIN_SCHEMA),
        (SERVICE_WINDOWS_CLOSE, windows_close, SERVICE_VIN_SCHEMA),
    ]

    for service_name, service_handler, schema in service_mapping:
        hass.services.async_register(DOMAIN, service_name, service_handler, schema=schema)


def remove_services(hass: HomeAssistant) -> None:
    """Remove the services for the MBAPI2020 integration."""

    LOGGER.debug("Start unload component. Services")
    hass.services.async_remove(DOMAIN, SERVICE_REFRESH_TOKEN_URL)
    hass.services.async_remove(DOMAIN, SERVICE_AUXHEAT_CONFIGURE)
    hass.services.async_remove(DOMAIN, SERVICE_AUXHEAT_START)
    hass.services.async_remove(DOMAIN, SERVICE_AUXHEAT_STOP)
    hass.services.async_remove(DOMAIN, SERVICE_BATTERY_MAX_SOC_CONFIGURE)
    hass.services.async_remove(DOMAIN, SERVICE_DOORS_LOCK_URL)
    hass.services.async_remove(DOMAIN, SERVICE_DOORS_UNLOCK_URL)
    hass.services.async_remove(DOMAIN, SERVICE_ENGINE_START)
    hass.services.async_remove(DOMAIN, SERVICE_ENGINE_STOP)
    hass.services.async_remove(DOMAIN, SERVICE_PREHEAT_START)
    hass.services.async_remove(DOMAIN, SERVICE_PREHEAT_START_DEPARTURE_TIME)
    hass.services.async_remove(DOMAIN, SERVICE_PREHEAT_STOP)
    hass.services.async_remove(DOMAIN, SERVICE_PREHEAT_STOP_DEPARTURE_TIME)
    hass.services.async_remove(DOMAIN, SERVICE_SEND_ROUTE)
    hass.services.async_remove(DOMAIN, SERVICE_SIGPOS_START)
    hass.services.async_remove(DOMAIN, SERVICE_SUNROOF_OPEN)
    hass.services.async_remove(DOMAIN, SERVICE_SUNROOF_CLOSE)
    hass.services.async_remove(DOMAIN, SERVICE_WINDOWS_OPEN)
    hass.services.async_remove(DOMAIN, SERVICE_WINDOWS_CLOSE)
