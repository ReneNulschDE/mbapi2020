"""Support for Mercedes cars with Mercedes ME.

For more details about this component, please refer to the documentation at
https://github.com/ReneNulschDE/mbapi2020/
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import MercedesMeEntity
from .const import (
    CONF_FT_DISABLE_CAPABILITY_CHECK,
    DOMAIN,
    LOGGER,
    BinarySensors,
    DefaultValueModeType,
    SensorConfigFields as scf,
)
from .coordinator import MBAPI2020DataUpdateCoordinator


def _create_binary_sensor_if_eligible(key, config, car, coordinator):
    """Check if binary sensor should be created and return device if eligible."""
    # Skip special sensors that should not be created dynamically
    if key in ["car", "data_mode"]:
        return None

    if (
        config[scf.CAPABILITIES_LIST.value] is None
        or coordinator.config_entry.options.get(CONF_FT_DISABLE_CAPABILITY_CHECK, False)
        or car.features.get(config[scf.CAPABILITIES_LIST.value], False)
    ):
        device = MercedesMEBinarySensor(
            internal_name=key,
            config=config,
            vin=car.finorvin,
            coordinator=coordinator,
        )


        # Check eligibility
        status = device.device_retrieval_status()
        is_eligible = status in ["VALID", "NOT_RECEIVED", "3", 3] or (
            config[scf.DEFAULT_VALUE_MODE.value] is not None
            and config[scf.DEFAULT_VALUE_MODE.value] != DefaultValueModeType.NONE
            and str(status) != "4"
        )

        if is_eligible:
            return device

    return None


async def create_missing_binary_sensors_for_car(car, coordinator, async_add_entities):
    """Create missing binary sensors for a specific car."""
    from homeassistant.helpers import entity_registry as er
    
    entity_registry = er.async_get(coordinator.hass)
    missing_sensors = []

    for key, value in sorted(BinarySensors.items()):
        device = _create_binary_sensor_if_eligible(key, value, car, coordinator)
        if device and not entity_registry.async_get_entity_id("binary_sensor", DOMAIN, device.unique_id):
            missing_sensors.append(device)

    if missing_sensors:
        await async_add_entities(missing_sensors, True)
        return len(missing_sensors)
    return 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up integration from a config entry."""

    coordinator: MBAPI2020DataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    if not coordinator.client.cars:
        LOGGER.info("No Cars found.")
        return

    sensors = []
    for car in coordinator.client.cars.values():
        for key, value in sorted(BinarySensors.items()):
            device = _create_binary_sensor_if_eligible(key, value, car, coordinator)
            if device:
                sensors.append(device)

    async_add_entities(sensors, True)


class MercedesMEBinarySensor(MercedesMeEntity, BinarySensorEntity, RestoreEntity):
    """Representation of a Sensor."""

    def flip(self, state):
        """Flip the result."""
        if self._flip_result:
            return not state
        return state

    @property
    def is_on(self):
        """Return the state of the binary sensor."""

        if self._state is None:
            self.update()

        if self._state == "INACTIVE":
            return self.flip(False)
        if self._state == "ACTIVE":
            return self.flip(True)
        if self._state == "0":
            return self.flip(False)
        if self._state == "1":
            return self.flip(True)
        if self._state == "2":
            return self.flip(False)
        if self._state == 0:
            return self.flip(False)
        if self._state == 1:
            return self.flip(True)
        if self._state == 2:
            return self.flip(False)
        if self._state == "true":
            return self.flip(True)
        if self._state == "false":
            return self.flip(False)
        if self._state is False:
            return self.flip(False)
        if self._state is True:
            return self.flip(True)

        return self._state
