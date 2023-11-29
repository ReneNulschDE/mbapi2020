"""
Button support for Mercedes cars with Mercedes ME.

For more details about this component, please refer to the documentation at
https://github.com/ReneNulschDE/mbapi2020/
"""
from __future__ import annotations

from homeassistant.components import persistent_notification
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MercedesMeEntity
from .const import BUTTONS, CONF_FT_DISABLE_CAPABILITY_CHECK, DOMAIN, LOGGER


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the demo button platform."""

    data = hass.data[DOMAIN]

    if not data.client.cars:
        LOGGER.info("No Cars found.")
        return

    button_list = []
    for car in data.client.cars:
        for key, value in sorted(BUTTONS.items()):
            if (
                value[5] is None
                or config_entry.options.get(CONF_FT_DISABLE_CAPABILITY_CHECK, False) is True
                or getattr(car.features, value[5], False) is True
            ):
                device = MercedesMEButton(
                    hass=hass, data=data, internal_name=key, sensor_config=value, vin=car.finorvin
                )

                button_list.append(device)

    async_add_entities(button_list, False)


class MercedesMEButton(MercedesMeEntity, ButtonEntity):
    """Representation of a Sensor."""

    async def async_press(self) -> None:
        """Send out a persistent notification."""
        service = getattr(self._data.client, self._sensor_config[3])
        await service(self._vin)
        self._state = None

    def update(self):
        """Nothing to update as buttons are stateless."""
