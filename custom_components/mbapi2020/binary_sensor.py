"""
Support for Mercedes cars with Mercedes ME.

For more details about this component, please refer to the documentation at
https://github.com/ReneNulschDE/mbapipy/
"""
from homeassistant.components.binary_sensor import BinarySensorEntity

from . import MercedesMeEntity

from .const import (
    DOMAIN,
    LOGGER,
    BINARY_SENSORS
)


async def async_setup_entry(hass, entry, async_add_entities):

    data = hass.data[DOMAIN]
#    conf = hass.data[DOMAIN].config

    sensors = []
    for car in data.client.cars:

        # tire_warning_field = "tirewarninglamp"
        # if conf.get(CONF_CARS) is not None:
        #     for car_conf in conf.get(CONF_CARS):
        #         if car_conf.get(CONF_CARS_VIN) == car.finorvin:
        #             tire_warning_field = car_conf.get(
        #                 CONF_TIRE_WARNING_INDICATOR)
        #             break

        for key, value in sorted(BINARY_SENSORS.items()):
#            if key == "tirewarninglamp":
#                value[3] = tire_warning_field

#            if value[5] is None or getattr(car.features, value[5]) is True:
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


class MercedesMEBinarySensor(MercedesMeEntity, BinarySensorEntity):
    """Representation of a Sensor."""

    @property
    def is_on(self):
        """Return the state of the binary sensor."""
        if self._state == "INACTIVE":
            return False
        if self._state == "ACTIVE":
            return True

        return self._state
