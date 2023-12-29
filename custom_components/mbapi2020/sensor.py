"""
Sensor support for Mercedes cars with Mercedes ME.

For more details about this component, please refer to the documentation at
https://github.com/ReneNulschDE/mbapi2020/
"""

from homeassistant.components.sensor import RestoreSensor

from . import MercedesMeEntity
from .const import (
    CONF_FT_DISABLE_CAPABILITY_CHECK,
    DOMAIN,
    LOGGER,
    SENSORS,
    SENSORS_POLL,
    DefaultValueModeType,
)
from .const import SensorConfigFields as scf


async def async_setup_entry(hass, entry, async_add_entities):
    """Setup the sensor platform."""

    data = hass.data[DOMAIN]

    if not data.client.cars:
        LOGGER.info("No Cars found.")
        return

    sensor_list = []
    for car in data.client.cars:
        for key, value in sorted(SENSORS.items()):
            if (
                value[5] is None
                or entry.options.get(CONF_FT_DISABLE_CAPABILITY_CHECK, False) is True
                or getattr(car.features, value[5], False) is True
            ):
                device = MercedesMESensor(
                    hass=hass, data=data, internal_name=key, sensor_config=value, vin=car.finorvin
                )
                if (
                    device.device_retrieval_status() in ["VALID", "NOT_RECEIVED"]
                    or value[scf.DEFAULT_VALUE_MODE.value] != DefaultValueModeType.NONE
                ):
                    sensor_list.append(device)

        for key, value in sorted(SENSORS_POLL.items()):
            if (
                value[5] is None
                or entry.options.get(CONF_FT_DISABLE_CAPABILITY_CHECK, False) is True
                or getattr(car.features, value[5], False) is True
            ):
                device = MercedesMESensorPoll(
                    hass=hass, data=data, internal_name=key, sensor_config=value, vin=car.finorvin, is_poll_sensor=True
                )
                if (
                    device.device_retrieval_status() in ["VALID", "NOT_RECEIVED"]
                    or value[scf.DEFAULT_VALUE_MODE.value] != DefaultValueModeType.NONE
                ):
                    sensor_list.append(device)

    async_add_entities(sensor_list, True)


class MercedesMESensor(MercedesMeEntity, RestoreSensor):
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

        if (last_sensor_data := await self.async_get_last_sensor_data()) is not None:
            self._state = last_sensor_data.native_value


class MercedesMESensorPoll(MercedesMeEntity, RestoreSensor):
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
        if (last_sensor_data := await self.async_get_last_sensor_data()) is not None:
            self._state = last_sensor_data.native_value

    async def async_update(self):
        """Get the latest data and updates the states."""
        LOGGER.debug("Updating %s", self._internal_name)

        # self._car = next(car for car in self._data.client.cars
        #                 if car.finorvin == self._vin)

        await self._data.client.update_poll_states(self._vin)

        self._state = self._get_car_value(self._feature_name, self._object_name, self._attrib_name, "error")
