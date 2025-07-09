"""Sensor support for Mercedes cars with Mercedes ME.

For more details about this component, please refer to the documentation at
https://github.com/ReneNulschDE/mbapi2020/
"""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import RestoreSensor, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNKNOWN, EntityCategory
from homeassistant.core import HomeAssistant
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
    async_add_entities([MercedesMEWebsocketOnlineSensor(coordinator)], True)
    async_add_entities([MercedesMEWebsocketReconnectsSensor(coordinator)], True)


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


class MercedesMEWebsocketOnlineSensor(SensorEntity):
    """Sensor für die Online-Zeit der Websocket-Connection pro Tag."""

    def __init__(self, coordinator):
        self._coordinator = coordinator
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_name = "Websocket online today"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_ws_online_time"
        self._attr_native_unit_of_measurement = "s"

    @property
    def native_value(self):
        ws = self._coordinator.client.websocket
        return getattr(ws, "_online_seconds_today", 0)


class MercedesMEWebsocketReconnectsSensor(SensorEntity):
    """Sensor für die Anzahl der Websocket-Initialisierungen pro Tag."""

    def __init__(self, coordinator):
        self._coordinator = coordinator
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_name = "Websocket connections today"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_ws_reconnects_today"
        self._attr_native_unit_of_measurement = "x"

    @property
    def native_value(self):
        ws = self._coordinator.client.websocket
        return getattr(ws, "_reconnects_today", 0)
