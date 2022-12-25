"""
Switch support for Mercedes cars with Mercedes ME.

For more details about this component, please refer to the documentation at
https://github.com/ReneNulschDE/mbapi2020/
"""

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.restore_state import RestoreEntity

from . import MercedesMeEntity

from .const import (
    CONF_FT_DISABLE_CAPABILITY_CHECK,
    DOMAIN,
    SWITCHES,
    LOGGER
)

async def async_setup_entry(hass, entry, async_add_entities):
    """Setup the sensor platform."""

    data = hass.data[DOMAIN]

    if not data.client.cars:
        LOGGER.info("No Cars found.")
        return

    sensor_list = []
    for car in data.client.cars:

        for key, value in sorted(SWITCHES.items()):
            if (value[5] is None or
                    entry.options.get(CONF_FT_DISABLE_CAPABILITY_CHECK, False) is True or
                    getattr(car.features, value[5], False) is True):
                device = MercedesMESwitch(
                    hass=hass,
                    data=data,
                    internal_name = key,
                    sensor_config = value,
                    vin = car.finorvin
                    )
                LOGGER.info("Created Switch for car %s - feature %s check: %s", car.finorvin, value[5] ,getattr(car.features, value[5]))
                sensor_list.append(device)

    async_add_entities(sensor_list, True)




class MercedesMESwitch(MercedesMeEntity, SwitchEntity, RestoreEntity):
    """Representation of a Sensor."""

    async def async_turn_on(self, **kwargs):
        """Turn device component on"""
        await getattr(self._data.client, self._internal_name + "_start")(self._vin)

    async def async_turn_off(self, **kwargs):
        """Turn device component off"""
        await getattr(self._data.client, self._internal_name + "_stop")(self._vin)

    @property
    def is_on(self):
        """Return true if device is locked."""
        return self._get_car_value(self._feature_name, self._object_name, self._attrib_name, False)
