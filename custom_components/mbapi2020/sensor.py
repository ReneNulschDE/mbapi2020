"""Sensor support for Mercedes cars with Mercedes ME.

For more details about this component, please refer to the documentation at
https://github.com/ReneNulschDE/mbapi2020/
"""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import RestoreSensor
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNKNOWN
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


def _create_sensor_if_eligible(key, config, car, coordinator, should_poll=False, initial_setup=False):
    """Check if sensor should be created and return device if eligible."""
    # Skip special sensors during dynamic loading, but allow during initial setup
    if key in ["car", "data_mode"] and not initial_setup:
        return None

    if (
        config[scf.CAPABILITIES_LIST.value] is None
        or coordinator.config_entry.options.get(CONF_FT_DISABLE_CAPABILITY_CHECK, False)
        or car.features.get(config[scf.CAPABILITIES_LIST.value], False)
    ):
        device_class = MercedesMESensorPoll if should_poll else MercedesMESensor
        device = device_class(
            internal_name=key,
            config=config,
            vin=car.finorvin,
            coordinator=coordinator,
            should_poll=should_poll,
        )

        # Check eligibility
        status = device.device_retrieval_status()
        is_eligible = False

        if should_poll:
            is_eligible = status in ["VALID", "NOT_RECEIVED"] or (
                config[scf.DEFAULT_VALUE_MODE.value] is not None
                and config[scf.DEFAULT_VALUE_MODE.value] != DefaultValueModeType.NONE
                and str(status) not in ["4", "error"]
            )
        else:
            is_eligible = status in ["VALID", "NOT_RECEIVED", "3", 3] or (
                config[scf.DEFAULT_VALUE_MODE.value] is not None
                and config[scf.DEFAULT_VALUE_MODE.value] != DefaultValueModeType.NONE
                and str(status) not in ["4", "error"]
            )

        if is_eligible:
            return device

    return None


async def create_missing_sensors_for_car(car, coordinator, async_add_entities):
    """Create missing sensors for a specific car."""

    missing_sensors = []

    # Helper function to check and add eligible devices
    def _check_and_add_device(device, car, sensor_type="sensor"):
        if device:
            if f"sensor.{device.unique_id}" not in car.sensors:
                missing_sensors.append(device)
                LOGGER.debug("Sensor added: %s, %s", device._name, f"sensor.{device.unique_id}")

    # Process regular sensors
    for key, value in sorted(SENSORS.items()):
        device = _create_sensor_if_eligible(key, value, car, coordinator, False)
        _check_and_add_device(device, car)

    # Process polling sensors
    for key, value in sorted(SENSORS_POLL.items()):
        device = _create_sensor_if_eligible(key, value, car, coordinator, True)
        _check_and_add_device(device, car)

    if missing_sensors:
        await async_add_entities(missing_sensors, True)
        return len(missing_sensors)
    return 0


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
            device = _create_sensor_if_eligible(key, value, car, coordinator, False, initial_setup=True)
            if device:
                sensor_list.append(device)

        for key, value in sorted(SENSORS_POLL.items()):
            device = _create_sensor_if_eligible(key, value, car, coordinator, True, initial_setup=True)
            if device:
                sensor_list.append(device)

    async_add_entities(sensor_list, True)


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
        elif self._internal_name == "chargingpowerecolimit":
            if self._state and int(self._state) <= 0:
                return None
            return self._state
        elif self._internal_name == "chargingpowerkw":
            if self._state and isinstance(self._state, (int, float)):
                return round(float(self._state), 1)
            if self._state and self._state == "error":
                return STATE_UNKNOWN

        return self._state

    async def async_added_to_hass(self):
        """Add callback after being added to hass."""

        self._car.add_sensor(f"sensor.{self._attr_unique_id}")
        await super().async_added_to_hass()

    async def async_will_remove_from_hass(self):
        """Entity being removed from hass."""

        self._car.remove_sensor(f"sensor.{self._attr_unique_id}")
        await super().async_will_remove_from_hass()


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

    async def async_added_to_hass(self):
        """Add callback after being added to hass."""

        self._car.add_sensor(f"sensor.{self._attr_unique_id}")
        await super().async_added_to_hass()

    async def async_will_remove_from_hass(self):
        """Entity being removed from hass."""

        self._car.remove_sensor(f"sensor.{self._attr_unique_id}")
        await super().async_will_remove_from_hass()
