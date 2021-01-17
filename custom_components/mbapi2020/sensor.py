import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_registry import async_get_registry

from homeassistant.const import (
    LENGTH_KILOMETERS,
    LENGTH_MILES)
from homeassistant.util import distance

from . import MercedesMeEntity

from .const import (
    DOMAIN,
    SENSORS
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

        for key, value in sorted(SENSORS.items()):
#            if value[5] is None or getattr(car.features, value[5]) is True:
            device = MercedesMESensor(
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
                value[6])
            if device.device_retrieval_status() in ["VALID", "NOT_RECEIVED"] :
                sensor_list.append(device)

    async_add_entities(sensor_list, True)




class MercedesMESensor(MercedesMeEntity):
    """Representation of a Sensor."""

    @property
    def state(self):
        """Return the state of the sensor."""

        if self.device_retrieval_status == "NOT_RECEIVED":
            return "NOT_RECEIVED"

        if self._unit == LENGTH_KILOMETERS and \
           not self._hass.config.units.is_metric:
            return round(
                distance.convert(int(self._state), LENGTH_KILOMETERS, LENGTH_MILES))
        else:
            return self._state


