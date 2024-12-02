"""Button support for Mercedes cars with Mercedes ME.

For more details about this component, please refer to the documentation at
https://github.com/ReneNulschDE/mbapi2020/
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MercedesMeEntity
from .const import BUTTONS, CONF_FT_DISABLE_CAPABILITY_CHECK, DOMAIN, LOGGER, SensorConfigFields as scf
from .coordinator import MBAPI2020DataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the demo button platform."""

    coordinator: MBAPI2020DataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    if not coordinator.client.cars:
        LOGGER.info("No Cars found.")
        return

    button_list = []
    for car in coordinator.client.cars.values():
        for key, value in sorted(BUTTONS.items()):
            if (
                value[scf.CAPABILITIES_LIST.value] is None
                or config_entry.options.get(CONF_FT_DISABLE_CAPABILITY_CHECK, False) is True
                or car.features.get(value[scf.CAPABILITIES_LIST.value], False) is True
            ):
                device = MercedesMEButton(
                    internal_name=key,
                    config=value,
                    vin=car.finorvin,
                    coordinator=coordinator,
                )

                button_list.append(device)

    async_add_entities(button_list, False)


class MercedesMEButton(MercedesMeEntity, ButtonEntity):
    """Representation of a Sensor."""

    async def async_press(self) -> None:
        """Send out a persistent notification."""
        service = getattr(self._coordinator.client, self._sensor_config[3])
        await service(self._vin)
        self._state = None

    def update(self):
        """Nothing to update as buttons are stateless."""
