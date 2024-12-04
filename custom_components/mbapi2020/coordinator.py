"""DataUpdateCoordinator class for the MBAPI2020 Integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .car import Car
from .client import Client
from .const import CONF_REGION, DOMAIN, MERCEDESME_COMPONENTS, UPDATE_INTERVAL, VERIFY_SSL
from .errors import MbapiError

LOGGER = logging.getLogger(__name__)


class MBAPI2020DataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """DataUpdateCoordinator class for the MBAPI2020 Integration."""

    initialized: bool = False
    entry_setup_complete: bool = False

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize."""

        self.hass: HomeAssistant = hass
        self.config_entry: ConfigEntry = config_entry
        session = async_get_clientsession(hass, VERIFY_SSL)

        # Find the right way to migrate old configs
        region = config_entry.data.get(CONF_REGION, None)
        if region is None:
            region = "Europe"

        self.client = Client(hass, session, config_entry, region)

        super().__init__(hass, LOGGER, name=DOMAIN, update_interval=UPDATE_INTERVAL)

    async def _async_update_data(self) -> dict[str, Car]:
        """Update data via library."""
        try:
            for vin in self.client.cars:
                await self.client.update_poll_states(vin)
        except Exception as err:
            raise MbapiError from err

        return {}  # self.client.cars

    @callback
    async def on_dataload_complete(self):
        """Create sensors after the web_socket initial data is complete."""
        LOGGER.info("Car Load complete - start sensor creation")
        if not self.entry_setup_complete:
            await self.hass.config_entries.async_forward_entry_setups(self.config_entry, MERCEDESME_COMPONENTS)

        self.entry_setup_complete = True

    async def ws_connect(self):
        """Register handlers and connect to the websocket."""
        await self.client.attempt_connect(self.on_dataload_complete)
