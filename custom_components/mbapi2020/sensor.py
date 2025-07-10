"""Sensor support for Mercedes cars with Mercedes ME.

For more details about this component, please refer to the documentation at
https://github.com/ReneNulschDE/mbapi2020/
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from homeassistant.components.sensor import RestoreSensor, SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNKNOWN, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MercedesMeEntity
from .const import (
    CONF_FT_DISABLE_CAPABILITY_CHECK,
    DOMAIN,
    LOGGER,
    SENSORS,
    SENSORS_POLL,
    DefaultValueModeType,
    SensorConfigFields as scf,
)
from .coordinator import MBAPI2020DataUpdateCoordinator


# Custom EntityDescription for websocket sensors
@dataclass(frozen=True, kw_only=True)
class WebsocketSensorEntityDescription(SensorEntityDescription):
    """EntityDescription for websocket sensors with value function."""

    value_fn: Callable[[Any], int | None] = None


# Websocket diagnostic sensor descriptions
WEBSOCKET_SENSORS: dict[str, WebsocketSensorEntityDescription] = {
    "websocket_online_time": WebsocketSensorEntityDescription(
        key="websocket_online_time",
        translation_key="websocket_online_time",
        name="Websocket online time today",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:clock-outline",
        value_fn=lambda ws: getattr(ws, "_online_seconds_today", 0),
    ),
    "websocket_reconnects": WebsocketSensorEntityDescription(
        key="websocket_reconnects",
        translation_key="websocket_reconnects",
        name="Websocket connections today",
        native_unit_of_measurement="connections",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:connection",
        value_fn=lambda ws: getattr(ws, "_reconnects_today", 0),
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Setups sensor platform."""

    coordinator: MBAPI2020DataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    if not coordinator.client.cars:
        LOGGER.info("No Cars found.")
        return

    sensor_list = []
    for car in coordinator.client.cars.values():
        for key, value in sorted(SENSORS.items()):
            if (
                value[scf.CAPABILITIES_LIST.value] is None
                or config_entry.options.get(CONF_FT_DISABLE_CAPABILITY_CHECK, False) is True
                or car.features.get(value[scf.CAPABILITIES_LIST.value], False) is True
            ):
                device = MercedesMESensor(
                    internal_name=key,
                    config=value,
                    vin=car.finorvin,
                    coordinator=coordinator,
                )
                if device.device_retrieval_status() in [
                    "VALID",
                    "NOT_RECEIVED",
                    "3",
                    3,
                ] or (
                    value[scf.DEFAULT_VALUE_MODE.value] is not None
                    and value[scf.DEFAULT_VALUE_MODE.value] != DefaultValueModeType.NONE
                    and str(device.device_retrieval_status()) != "4"
                ):
                    sensor_list.append(device)

        for key, value in sorted(SENSORS_POLL.items()):
            if (
                value[scf.CAPABILITIES_LIST.value] is None
                or config_entry.options.get(CONF_FT_DISABLE_CAPABILITY_CHECK, False) is True
                or car.features.get(value[scf.CAPABILITIES_LIST.value], False) is True
            ):
                device = MercedesMESensorPoll(
                    internal_name=key,
                    config=value,
                    vin=car.finorvin,
                    coordinator=coordinator,
                    should_poll=True,
                )
                if device.device_retrieval_status() in ["VALID", "NOT_RECEIVED"] or (
                    value[scf.DEFAULT_VALUE_MODE.value] is not None
                    and value[scf.DEFAULT_VALUE_MODE.value] != DefaultValueModeType.NONE
                    and str(device.device_retrieval_status()) != "4"
                ):
                    sensor_list.append(device)

    async_add_entities(sensor_list, True)

    # Clean up old websocket sensor entities with old unique_ids
    await _cleanup_old_websocket_sensors(hass, config_entry)

    # Add websocket diagnostic sensors for the integration
    websocket_sensors = [
        MercedesMEWebsocketSensor(coordinator, description) for description in WEBSOCKET_SENSORS.values()
    ]
    async_add_entities(websocket_sensors, True)


async def _cleanup_old_websocket_sensors(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Remove old websocket sensor entities with outdated unique_ids."""
    entity_registry = er.async_get(hass)

    # List of old unique_ids that need to be removed
    old_unique_ids = [
        f"{config_entry.entry_id}_ws_online_time",
        f"{config_entry.entry_id}_ws_reconnects_today",
    ]

    for old_unique_id in old_unique_ids:
        if entity_id := entity_registry.async_get_entity_id("sensor", DOMAIN, old_unique_id):
            LOGGER.info("Removing old websocket sensor entity: %s", entity_id)
            entity_registry.async_remove(entity_id)


class MercedesMESensor(MercedesMeEntity, RestoreSensor):
    """Representation of a Sensor."""

    @property
    def native_value(self) -> str | int | float | datetime | None:
        """Return the state."""
        return self.state

    @property
    def state(self):
        """Return the state of the sensor."""

        if self.device_retrieval_status() in ("NOT_RECEIVED", "4", 4):
            if self._sensor_config[scf.DEFAULT_VALUE_MODE.value]:
                if self._sensor_config[scf.DEFAULT_VALUE_MODE.value] == "Zero":
                    return 0
            return STATE_UNKNOWN

        if self.device_retrieval_status() == 3:
            if self._sensor_config[scf.DEFAULT_VALUE_MODE.value]:
                if self._sensor_config[scf.DEFAULT_VALUE_MODE.value] == "Zero":
                    return 0
                return STATE_UNKNOWN
            return STATE_UNKNOWN

        if self._internal_name == "lastParkEvent":
            if self._state:
                return datetime.fromtimestamp(int(self._state))
        elif self._internal_name == "chargingpowerkw":
            if self._state and isinstance(self._state, (int, float)):
                return round(float(self._state), 1)

        return self._state


class MercedesMESensorPoll(MercedesMeEntity, RestoreSensor):
    """Representation of a Sensor."""

    @property
    def native_value(self) -> str | int | float | datetime | None:
        """Return the state."""
        return self.state

    @property
    def state(self):
        """Return the state of the sensor."""

        if self.device_retrieval_status() == "NOT_RECEIVED":
            return STATE_UNKNOWN

        if self.device_retrieval_status() == 3:
            return STATE_UNKNOWN

        return self._state


class MercedesMEWebsocketSensor(SensorEntity):
    """Generic websocket diagnostic sensor using EntityDescription."""

    entity_description: WebsocketSensorEntityDescription

    def __init__(
        self,
        coordinator: MBAPI2020DataUpdateCoordinator,
        description: WebsocketSensorEntityDescription,
    ) -> None:
        """Initialize the websocket sensor."""
        self.entity_description = description
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"

        # Create integration device info (not car-specific)
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{coordinator.config_entry.entry_id}_integration")},
            "name": f"Mercedes ME Integration ({coordinator.config_entry.title})",
            "manufacturer": "Mercedes-Benz",
            "model": "Integration",
            "sw_version": "2020",
        }

    @property
    def native_value(self) -> int | None:
        """Return the sensor value using the description's value function."""
        ws = self._coordinator.client.websocket
        if ws and self.entity_description.value_fn:
            return self.entity_description.value_fn(ws)
        return None

    @property
    def available(self) -> bool:
        """Return if sensor is available."""
        return self._coordinator.client.websocket is not None
