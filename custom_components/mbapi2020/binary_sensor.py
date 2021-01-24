"""
Support for Mercedes cars with Mercedes ME.

For more details about this component, please refer to the documentation at
https://github.com/ReneNulschDE/mbapi2020/
"""

import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.restore_state import RestoreEntity

from . import MercedesMeEntity

from .const import (
    DOMAIN,
    BINARY_SENSORS
)

LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):

    data = hass.data[DOMAIN]
#    conf = hass.data[DOMAIN].config

    sensors = []
    for car in data.client.cars:

        for key, value in sorted(BINARY_SENSORS.items()):
            device = MercedesMEBinarySensor(
                hass,
                data,
                key,
                value[0],
                car.finorvin,
                value[1],
                car.licenseplate,
                value[2],
                value[3],
                value[4],
                value[6],
            )
            if device.device_retrieval_status() in ["VALID", "NOT_RECEIVED"] :
                sensors.append(device)

    async_add_entities(sensors, True)


class MercedesMEBinarySensor(MercedesMeEntity, BinarySensorEntity, RestoreEntity):
    """Representation of a Sensor."""

    @property
    def is_on(self):
        """Return the state of the binary sensor."""
        if self._state == "INACTIVE":
            return False
        if self._state == "ACTIVE":
            return True
        if self._state == "0":
            return False
        if self._state == "1":
            return True
        if self._state == 0:
            return False
        if self._state == 1:
            return True
        if self._state == False:
            return False
        if self._state == True:
            return True

        return self._state
