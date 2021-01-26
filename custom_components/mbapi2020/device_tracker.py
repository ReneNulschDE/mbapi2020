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
                hass=hass,
                data=data,
                internal_name = key,
                sensor_config = value,
                vin = car.finorvin
                )
            if device.device_retrieval_status() in ["VALID", "NOT_RECEIVED"] :
                sensor_list.append(device)


    async_add_entities(sensor_list, True)


class MercedesMEDeviceTracker(MercedesMeEntity, TrackerEntity, RestoreEntity):

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

    @ property
    def device_class(self):
        return None

