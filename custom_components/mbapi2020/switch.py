"""Switch support for Mercedes cars with Mercedes ME.

For more details about this component, please refer to the documentation at
https://github.com/ReneNulschDE/mbapi2020/
"""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import MercedesMeEntity
from .const import CONF_FT_DISABLE_CAPABILITY_CHECK, DOMAIN, LOGGER, SWITCHES, SensorConfigFields as scf
from .coordinator import MBAPI2020DataUpdateCoordinator
from .helper import LogHelper as loghelper


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Setups the switch platform."""

    coordinator: MBAPI2020DataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    if not coordinator.client.cars:
        LOGGER.info("No Cars found.")
        return

    sensor_list = []
    for car in coordinator.client.cars.values():
        for key, value in sorted(SWITCHES.items()):
            if (
                value[scf.CAPABILITIES_LIST.value] is None
                or config_entry.options.get(CONF_FT_DISABLE_CAPABILITY_CHECK, False) is True
                or car.features.get(value[scf.CAPABILITIES_LIST.value], False) is True
            ):
                device = MercedesMESwitch(
                    internal_name=key,
                    sensor_config=value,
                    vin=car.finorvin,
                    coordinator=coordinator,
                )
                LOGGER.info(
                    "Created Switch for car %s - feature %s check: %s",
                    loghelper.Mask_VIN(car.finorvin),
                    value[5],
                    getattr(car.features, value[5]),
                )
                sensor_list.append(device)

    async_add_entities(sensor_list, True)


class MercedesMESwitch(MercedesMeEntity, SwitchEntity, RestoreEntity):
    """Representation of a Sensor."""

    async def async_turn_on(self, **kwargs):
        """Turn a device component on."""
        await getattr(self._coordinator.client, self._internal_name + "_start")(self._vin)

    async def async_turn_off(self, **kwargs):
        """Turn a device component off."""
        await getattr(self._coordinator.client, self._internal_name + "_stop")(self._vin)

    @property
    def is_on(self):
        """Return true if device is locked."""
        return self._get_car_value(self._feature_name, self._object_name, self._attrib_name, False)
