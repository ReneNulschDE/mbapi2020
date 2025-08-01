"""DataUpdateCoordinator class for the MBAPI2020 Integration."""

from __future__ import annotations

import logging
from typing import Any

from awesomeversion import AwesomeVersion

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import __version__ as HAVERSION
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import async_get_platforms
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .car import Car
from .client import Client
from .const import CONF_REGION, DOMAIN, MERCEDESME_COMPONENTS, UPDATE_INTERVAL, VERIFY_SSL
from .errors import MbapiError
from .helper import LogHelper as loghelper

LOGGER = logging.getLogger(__name__)

# Version threshold for config_entry setting in options flow
# See: https://github.com/home-assistant/core/pull/127980
HA_DATACOORDINATOR_CONTEXTVAR_VERSION_THRESHOLD = "2025.07.99"


class MBAPI2020DataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """DataUpdateCoordinator class for the MBAPI2020 Integration."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize."""

        self.hass: HomeAssistant = hass
        self.config_entry: ConfigEntry = config_entry
        self.initialized: bool = False
        self.entry_setup_complete: bool = False
        session = async_get_clientsession(hass, VERIFY_SSL)

        # Find the right way to migrate old configs
        region = config_entry.data.get(CONF_REGION, None)
        if region is None:
            region = "Europe"

        self.client = Client(hass, session, config_entry, region)

        if AwesomeVersion(HAVERSION) < HA_DATACOORDINATOR_CONTEXTVAR_VERSION_THRESHOLD:
            super().__init__(hass, LOGGER, name=DOMAIN, update_interval=UPDATE_INTERVAL)
        else:
            super().__init__(hass, LOGGER, name=DOMAIN, config_entry=config_entry, update_interval=UPDATE_INTERVAL)

    async def _async_update_data(self) -> dict[str, Car]:
        """Update data via library."""

        if self.entry_setup_complete:
            try:
                for vin in self.client.cars:
                    await self.client.update_poll_states(vin)
            except Exception as err:
                raise MbapiError from err

        return {}  # self.client.cars

    @callback
    async def on_dataload_complete(self):
        """Create sensors after the web_socket initial data is complete."""
        if not self.entry_setup_complete:
            LOGGER.info("Car Load complete - start sensor creation")
            await self.hass.config_entries.async_forward_entry_setups(self.config_entry, MERCEDESME_COMPONENTS)

        self.entry_setup_complete = True
        self.client._dataload_complete_fired = True

    async def ws_connect(self):
        """Register handlers and connect to the websocket."""
        await self.client.attempt_connect(self.on_dataload_complete, self)

    @callback
    async def check_missing_sensors_for_vin(self, vin: str):
        """Check for newly available sensors after vep_updates."""
        if not self.entry_setup_complete:
            return

        from .binary_sensor import create_missing_binary_sensors_for_car
        from .sensor import create_missing_sensors_for_car

        car = self.client.cars.get(vin)
        if not car:
            return

        platforms = async_get_platforms(self.hass, "mbapi2020")
        sensor_platform = None
        binary_sensor_platform = None
        for platform in platforms:
            if platform.domain == "sensor":
                sensor_platform = platform
            elif platform.domain == "binary_sensor":
                binary_sensor_platform = platform

        total_count = 0

        if sensor_platform and hasattr(sensor_platform, "async_add_entities"):
            count = await create_missing_sensors_for_car(car, self, sensor_platform.async_add_entities)
            total_count += count

        if binary_sensor_platform and hasattr(binary_sensor_platform, "async_add_entities"):
            count = await create_missing_binary_sensors_for_car(car, self, binary_sensor_platform.async_add_entities)
            total_count += count

        if total_count > 0:
            LOGGER.info("Added %d missing sensors/binary_sensors for %s", total_count, loghelper.Mask_VIN(vin))
