import logging
from typing import Optional

from homeassistant.components.device_tracker import SOURCE_TYPE_GPS
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import slugify

from . import MercedesMeEntity

from .const import (
    DEVICE_TRACKER,
    DOMAIN,
)

LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the MB device tracker by config_entry."""

    data = hass.data[DOMAIN]

    if not data.client.cars:
        LOGGER.info("No Cars found.")
        return

    sensor_list = []


    for car in data.client.cars:
        for key, value in sorted(DEVICE_TRACKER.items()):
#            if value[5] is None or getattr(car.features, value[5]) is True:
            device = MercedesMEDeviceTracker(
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


class MercedesMEDeviceTracker(TrackerEntity, RestoreEntity):

    """A class representing a Mercedes ME device tracker."""
    def __init__(
        self,
        hass,
        data,
        internal_name,
        sensor_name,
        vin,
        unit,
        licenseplate,
        feature_name,
        object_name,
        attrib_name,
        extended_attributes,
        **kwargs,
    ):
        """Initialize the MercedesMe entity."""
        self._hass = hass
        self._data = data
        self._state = False
        self._name = f"{licenseplate} {sensor_name}"
        self._internal_name = internal_name
        self._internal_unit = unit
        self._sensor_name = sensor_name
        self._unit = unit
        self._vin = vin
        self._feature_name = feature_name
        self._object_name = object_name
        self._attrib_name = attrib_name
        self._licenseplate = licenseplate
        self._extended_attributes = extended_attributes
        self._kwargs = kwargs
        self._unique_id = slugify(f"{self._vin}_{self._internal_name}")
        self._car = next(car for car in self._data.client.cars
                         if car.finorvin == self._vin)

#        conf = hass.data[DOMAIN].config
#        if conf.get(CONF_CARS) is not None:
#            for car_conf in conf.get(CONF_CARS):
#                if car_conf.get(CONF_CARS_VIN) == vin:
#                    custom_car_name = car_conf.get(CONF_NAME)
#                    if custom_car_name != "_notset_":
#                        self._name = f"{custom_car_name} {sensor_name}".strip()

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name


    @property
    def unique_id(self) -> str:
        """Return the name of the sensor."""
        return self._unique_id

    def device_retrieval_status(self):
        return self._get_car_value(
            self._feature_name, self._object_name, "retrievalstatus", "error"
        )

    @property
    def device_info(self):
        """Return the device info."""

        return {
            "identifiers": {(DOMAIN, self._vin)}
        }

    def update(self):
        """Get the latest data and updates the states."""
        LOGGER.debug("Updating %s", self._internal_name)

        self._car = next(car for car in self._data.client.cars
                         if car.finorvin == self._vin)

        self._state = self._get_car_value(
            self._feature_name, self._object_name, self._attrib_name, "error"
        )

        LOGGER.debug("Updated %s %s", self._internal_name, self._state)

    
    def _get_car_value(self, feature, object_name, attrib_name, default_value):
        value = None

        if object_name:
            if not feature:
                value = getattr(
                    getattr(self._car, object_name, default_value),
                    attrib_name,
                    default_value,
                )
            else:
                value = getattr(
                    getattr(
                        getattr(self._car, feature, default_value),
                        object_name,
                        default_value,
                    ),
                    attrib_name,
                    default_value,
                )

        else:
            value = getattr(self._car, attrib_name, default_value)

        return value

    @property
    def device_state_attributes(self):
        """Return the state attributes."""

        state = {
            "car": self._licenseplate,
            "vin": self._vin,
            "retrievalstatus": self._get_car_value(
                self._feature_name,
                self._object_name,
                "retrievalstatus",
                "error"
            ),
        }
        if self._extended_attributes is not None:
            for attrib in self._extended_attributes:

                retrievalstatus = self._get_car_value(self._feature_name, attrib,
                                                      "retrievalstatus", "error")

                if retrievalstatus == "VALID":
                    state[attrib] = self._get_car_value(
                        self._feature_name, attrib, "value", "error"
                    )

                if retrievalstatus == "NOT_RECEIVED":
                    state[attrib] = "NOT_RECEIVED"
        return state


    @property
    def latitude(self) -> Optional[float]:
        """Return latitude value of the device."""
        location = self._get_car_value("location", "positionLat", "value", 0)
        return location if location else None

    @property
    def longitude(self) -> Optional[float]:
        """Return longitude value of the device."""
        location = self._get_car_value("location", "positionLong", "value", 0)
        return location if location else None

    @property
    def source_type(self):
        """Return the source type, eg gps or router, of the device."""
        return SOURCE_TYPE_GPS

    @property
    def should_poll(self):
        return False
 
    def update_callback(self):
        """Schedule a state update."""
        self.schedule_update_ha_state(True)

    async def async_added_to_hass(self):
        """Add callback after being added to hass.

        Show latest data after startup.
        """
        self._car.add_update_listener(self.update_callback)
