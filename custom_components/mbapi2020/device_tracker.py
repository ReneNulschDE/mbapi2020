"""Device Tracker support for Mercedes cars with Mercedes ME.

For more details about this component, please refer to the documentation at
https://github.com/ReneNulschDE/mbapi2020/
"""

from __future__ import annotations

import logging

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import MercedesMeEntity
from .const import DEVICE_TRACKER, DOMAIN
from .coordinator import MBAPI2020DataUpdateCoordinator
from .helper import CoordinatesHelper as ch

LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the MB device tracker by config_entry."""

    coordinator: MBAPI2020DataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    if not coordinator.client.cars:
        LOGGER.info("No Cars found.")
        return

    sensor_list = []

    for car in coordinator.client.cars.values():
        for key, value in sorted(DEVICE_TRACKER.items()):
            device = MercedesMEDeviceTracker(
                internal_name=key,
                config=value,
                vin=car.finorvin,
                coordinator=coordinator,
            )
            if device.device_retrieval_status() in ["VALID", "NOT_RECEIVED"]:
                sensor_list.append(device)

    async_add_entities(sensor_list, True)


class MercedesMEDeviceTracker(MercedesMeEntity, TrackerEntity, RestoreEntity):
    """Representation of a Sensor."""

    @property
    def latitude(self) -> float | None:
        """Return latitude value of the device."""
        lat = self._get_car_value("location", "positionLat", "value", 0)
        lng = self._get_car_value("location", "positionLong", "value", 0)

        if self._use_chinese_location_data:
            lng, lat = ch.gcj02_to_wgs84(gcj_lon=lng, gcj_lat=lat)

        return lat if lat else None

    @property
    def longitude(self) -> float | None:
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
        """Return the device class of the device tracker."""
        return None
