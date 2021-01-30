import logging

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_registry import async_get_registry
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.const import (
    ATTR_CODE,
)

from . import MercedesMeEntity

from .const import (
    CONF_PIN,
    DOMAIN,
    LOCKS,
    Sensor_Config_Fields as scf
)

LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Setup the sensor platform."""

    data = hass.data[DOMAIN]

    if not data.client.cars:
        LOGGER.info("No Cars found.")
        return

    sensor_list = []
    for car in data.client.cars:

        for key, value in sorted(LOCKS.items()):
#            if value[5] is None or getattr(car.features, value[5]) is True:
            device = MercedesMELock(
                hass=hass,
                data=data,
                internal_name = key,
                sensor_config = value,
                vin = car.finorvin
                )
            sensor_list.append(device)

    async_add_entities(sensor_list, True)




class MercedesMELock(MercedesMeEntity, LockEntity, RestoreEntity):
    """Representation of a Sensor."""

    async def async_lock(self, **kwargs):
        """Lock the device."""
        await self._data.client.doors_lock(self._vin)

    async def async_unlock(self, **kwargs):
        """Unlock the device."""
        code = kwargs.get(ATTR_CODE, None)
        pin = self._data.client._config_entry.options.get(CONF_PIN, None)

        if pin and pin.strip():
            await self._data.client.doors_unlock_with_pin(self._vin, pin)

        if code is None:
            LOGGER.error("Code required but none provided")
        else:
            await self._data.client.doors_unlock_with_pin(self._vin, code)




    @property
    def is_locked(self):
        """Return true if device is locked."""

        value = self._get_car_value(self._feature_name , self._object_name, self._attrib_name, None)
        if value and int(value) == 0:
            return True

        return False

    @property
    def code_format(self):
        """Return the required for digit code if the PIN is not set in config_entry."""

        pin = self._data.client._config_entry.options.get(CONF_PIN, None)

        if pin and pin.strip():
            # Pin is set --> we don't ask for a pin
            return None

        # Pin is set --> we don't ask for a pin
        return "^\\d{%s}$" % 4
