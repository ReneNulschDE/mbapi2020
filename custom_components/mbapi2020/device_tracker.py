"""
Device Tracker support for Mercedes cars with Mercedes ME.

For more details about this component, please refer to the documentation at
https://github.com/ReneNulschDE/mbapi2020/
"""
import logging
from typing import Optional

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.helpers.restore_state import RestoreEntity

from . import MercedesMeEntity
from .const import CONF_ENABLE_CHINA_GCJ_02, DEVICE_TRACKER, DOMAIN
from .helper import CoordinatesHelper as ch

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
                internal_name=key,
                sensor_config=value,
                vin=car.finorvin,
                use_chinese_location_data=config_entry.options.get(CONF_ENABLE_CHINA_GCJ_02, False),
            )
            if device.device_retrieval_status() in ["VALID", "NOT_RECEIVED"]:
                sensor_list.append(device)

    async_add_entities(sensor_list, True)


class MercedesMEDeviceTracker(MercedesMeEntity, TrackerEntity, RestoreEntity):
    """Representation of a Sensor."""

    @property
    def latitude(self) -> Optional[float]:
        """Return latitude value of the device."""
        lat = self._get_car_value("location", "positionLat", "value", 0)
        lng = self._get_car_value("location", "positionLong", "value", 0)

        if self._use_chinese_location_data:
            lng, lat = ch.gcj02_to_wgs84(gcj_lon=lng, gcj_lat=lat)

        return lat if lat else None

    @property
    def longitude(self) -> Optional[float]:
        """Return longitude value of the device."""
        lat = self._get_car_value("location", "positionLat", "value", 0)
        lng = self._get_car_value("location", "positionLong", "value", 0)

        if self._use_chinese_location_data:
            lng, lat = ch.gcj02_to_wgs84(gcj_lon=lng, gcj_lat=lat)

        return lng if lng else None

    @property
    def source_type(self):
        """Return the source type, eg gps or router, of the device."""
        return SourceType.GPS

    @property
    def device_class(self):
        return None
