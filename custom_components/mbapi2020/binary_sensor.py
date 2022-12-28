"""
Support for Mercedes cars with Mercedes ME.

For more details about this component, please refer to the documentation at
https://github.com/ReneNulschDE/mbapi2020/
"""

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.restore_state import RestoreEntity

from . import MercedesMeEntity
from .const import CONF_FT_DISABLE_CAPABILITY_CHECK, DOMAIN, LOGGER, BinarySensors


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up integration from a config entry."""

    data = hass.data[DOMAIN]

    if not data.client.cars:
        LOGGER.info("No Cars found.")
        return

    sensors = []
    for car in data.client.cars:

        for key, value in sorted(BinarySensors.items()):
            if (
                value[5] is None
                or entry.options.get(CONF_FT_DISABLE_CAPABILITY_CHECK, False) is False
                or getattr(car.features, value[5], False) is True
            ):
                device = MercedesMEBinarySensor(
                    hass=hass, data=data, internal_name=key, sensor_config=value, vin=car.finorvin
                )
                if device.device_retrieval_status() in ["VALID", "NOT_RECEIVED"]:
                    sensors.append(device)

    async_add_entities(sensors, True)


class MercedesMEBinarySensor(MercedesMeEntity, BinarySensorEntity, RestoreEntity):
    """Representation of a Sensor."""

    @property
    def is_on(self):
        """Return the state of the binary sensor."""

        if self._state is None:
            self.update()

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
        if self._state == "true":
            return True
        if self._state == "false":
            return False
        if self._state is False:
            return False
        if self._state is True:
            return True

        return self._state
