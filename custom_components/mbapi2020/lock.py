"""Lock Support for Mercedes cars with Mercedes ME.

For more details about this component, please refer to the documentation at
https://github.com/ReneNulschDE/mbapi2020/
"""

from __future__ import annotations

import asyncio

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_CODE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import MercedesMeEntity
from .const import CONF_FT_DISABLE_CAPABILITY_CHECK, CONF_PIN, DOMAIN, LOCKS, LOGGER, SensorConfigFields as scf
from .coordinator import MBAPI2020DataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the sensor platform."""

    coordinator: MBAPI2020DataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    if not coordinator.client.cars:
        LOGGER.info("No Cars found.")
        return

    sensor_list = []
    for car in coordinator.client.cars.values():
        for key, value in sorted(LOCKS.items()):
            if (
                value[scf.CAPABILITIES_LIST.value] is None
                or config_entry.options.get(CONF_FT_DISABLE_CAPABILITY_CHECK, False) is True
                or car.features.get(value[scf.CAPABILITIES_LIST.value], False) is True
            ):
                device = MercedesMELock(
                    internal_name=key,
                    config=value,
                    vin=car.finorvin,
                    coordinator=coordinator,
                )
                sensor_list.append(device)

    async_add_entities(sensor_list, True)


class MercedesMELock(MercedesMeEntity, LockEntity, RestoreEntity):
    """Representation of a Lock."""

    async def async_lock(self, **kwargs):
        """Lock the device."""
        old_state = self.is_locked
        LOGGER.debug("starting lock")
        self._attr_is_locking = True
        await self._coordinator.client.doors_lock(self._vin)
        LOGGER.debug("lock initiated")

        count = 0
        while count < 30:
            if old_state == self.is_locked:
                count += 1
                LOGGER.debug("lock running %s", count)
                await asyncio.sleep(1)
            else:
                break

        self._attr_is_locking = False
        LOGGER.debug("unlock finalized %s", count)

    async def async_unlock(self, **kwargs):
        """Unlock the device."""
        old_state = self.is_locked
        LOGGER.debug("starting unlock")
        code = kwargs.get(ATTR_CODE, "")
        pin = self._coordinator.client.config_entry.options.get(CONF_PIN, "")
        self._attr_is_unlocking = True

        if pin and pin.strip():
            await self._coordinator.client.doors_unlock_with_pin(self._vin, pin)
        elif code is None or not code.strip():
            LOGGER.error("Code required but none provided")
            self._attr_is_unlocking = False
            return
        else:
            await self._coordinator.client.doors_unlock_with_pin(self._vin, code)

        LOGGER.debug("unlock initiated")
        count = 0
        while count < 30:
            if old_state == self.is_locked:
                count += 1
                LOGGER.debug("unlock running %s", count)
                await asyncio.sleep(1)
            else:
                break
        self._attr_is_unlocking = False
        LOGGER.debug("unlock finalized %s", count)

    @property
    def is_locked(self):
        """Return true if device is locked."""

        value = self._get_car_value(self._feature_name, self._object_name, self._attrib_name, None)
        if value and int(value) == 0:
            return True

        if value and int(value) == 1:
            return False

        return None

    @property
    def code_format(self):
        """Return the required four digit code if the PIN is not set in config_entry."""

        pin = self._coordinator.client.config_entry.options.get(CONF_PIN, None)

        if pin and pin.strip():
            # Pin is set --> we don't ask for a pin
            return None

        # Pin is not set --> we ask for a pin
        return "^\\d{4}$"
