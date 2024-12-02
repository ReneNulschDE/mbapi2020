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
from .const import CONF_FT_DISABLE_CAPABILITY_CHECK, DOMAIN, LOGGER, BinarySensors, SensorConfigFields as scf
from .coordinator import MBAPI2020DataUpdateCoordinator


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
            if (
                value[scf.CAPABILITIES_LIST.value] is None
                or config_entry.options.get(CONF_FT_DISABLE_CAPABILITY_CHECK, False) is True
                or car.features.get(value[scf.CAPABILITIES_LIST.value], False) is True
            ):
                device = MercedesMEBinarySensor(
                    internal_name=key,
                    config=value,
                    vin=car.finorvin,
                    coordinator=coordinator,
                )
                if device.device_retrieval_status() in ["VALID", "NOT_RECEIVED", "3", 3]:
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
