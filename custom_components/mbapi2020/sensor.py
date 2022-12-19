"""
Sensor support for Mercedes cars with Mercedes ME.

For more details about this component, please refer to the documentation at
https://github.com/ReneNulschDE/mbapi2020/
"""
import logging

from homeassistant.helpers.restore_state import RestoreEntity

from . import MercedesMeEntity

from .const import (
    CONF_FT_DISABLE_CAPABILITY_CHECK,
    DOMAIN,
    SENSORS,
    SENSORS_POLL
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
            if (value[5] is None or
                    entry.options.get(CONF_FT_DISABLE_CAPABILITY_CHECK, False) is False or
                    getattr(car.features, value[5], False) is True):
                device = MercedesMESensor(
                    hass=hass,
                    data=data,
                    internal_name = key,
                    sensor_config = value,
                    vin = car.finorvin
                    )
                if device.device_retrieval_status() in ["VALID", "NOT_RECEIVED"] :
                    sensor_list.append(device)

        for key, value in sorted(SENSORS_POLL.items()):
            if (value[5] is None or
                    entry.options.get(CONF_FT_DISABLE_CAPABILITY_CHECK, False) is False or
                    getattr(car.features, value[5], False) is True):
                device = MercedesMESensorPoll(
                    hass=hass,
                    data=data,
                    internal_name = key,
                    sensor_config = value,
                    vin = car.finorvin,
                    is_poll_sensor = True
                    )
                if device.device_retrieval_status() in ["VALID", "NOT_RECEIVED"] :
                    sensor_list.append(device)

    async_add_entities(sensor_list, True)




class MercedesMESensor(MercedesMeEntity, RestoreEntity):
    """Representation of a Sensor."""

    @property
    def state(self):
        """Return the state of the sensor."""

        if self.device_retrieval_status() == "NOT_RECEIVED":
            return "NOT_RECEIVED"

        return self._state


    async def async_added_to_hass(self) -> None:
        """Call when entity about to be added to Home Assistant."""
        await super().async_added_to_hass()
        # __init__ will set self._state to self._initial, only override
        # if needed.
        state = await self.async_get_last_state()
        if state is not None:
            self._state = state.state

class MercedesMESensorPoll(MercedesMeEntity, RestoreEntity):
    """Representation of a Sensor."""

    @property
    def state(self):
        """Return the state of the sensor."""

        if self.device_retrieval_status() == "NOT_RECEIVED":
            return "NOT_RECEIVED"

        return self._state


    async def async_added_to_hass(self) -> None:
        """Call when entity about to be added to Home Assistant."""
        await super().async_added_to_hass()
        # __init__ will set self._state to self._initial, only override
        # if needed.
        state = await self.async_get_last_state()
        if state is not None:
            self._state = state.state

    async def async_update(self):
        """Get the latest data and updates the states."""
        LOGGER.debug("Updating %s", self._internal_name)

        #self._car = next(car for car in self._data.client.cars
        #                 if car.finorvin == self._vin)

        await self._data.client.update_poll_states(self._vin)

        self._state = self._get_car_value(
            self._feature_name, self._object_name, self._attrib_name, "error"
        )
