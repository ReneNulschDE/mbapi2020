"""Switch support for Mercedes cars with Mercedes ME.

For more details about this component, please refer to the documentation at
https://github.com/ReneNulschDE/mbapi2020/
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.restore_state import RestoreEntity

from . import MercedesMeEntity, MercedesMeEntityDescription
from .car import Car
from .const import CONF_FT_DISABLE_CAPABILITY_CHECK, DOMAIN, LOGGER, STATE_CONFIRMATION_DURATION
from .coordinator import MBAPI2020DataUpdateCoordinator
from .helper import LogHelper as loghelper


@dataclass(frozen=True, kw_only=True)
class MercedesMeSwitchEntityDescription(MercedesMeEntityDescription, SwitchEntityDescription):
    """Configuration class for MercedesMe switch entities."""

    is_on_fn: Callable[[MercedesMeSwitch], Callable[[], Coroutine[Any, Any, bool]]]
    turn_on_fn: Callable[[MercedesMeSwitch], Callable[[], Coroutine[Any, Any, None]]]
    turn_off_fn: Callable[[MercedesMeSwitch], Callable[[], Coroutine[Any, Any, None]]]


SWITCH_DESCRIPTIONS: list[MercedesMeSwitchEntityDescription] = [
    MercedesMeSwitchEntityDescription(
        key="precond",
        translation_key="precond",
        icon="mdi:hvac",
        is_on_fn=lambda self: self._get_car_value("precond", "precondStatus", "value", default_value=False),
        turn_on_fn=lambda self, **kwargs: self._coordinator.client.preheat_start_universal(self._vin),
        turn_off_fn=lambda self, **kwargs: self._coordinator.client.preheat_stop(self._vin),
        check_capability_fn=lambda car: car.check_capabilities(
            ["ZEV_PRECONDITIONING_START", "ZEV_PRECONDITIONING_STOP"]
        ),
    ),
    MercedesMeSwitchEntityDescription(
        key="auxheat",
        translation_key="auxheat",
        icon="mdi:hvac",
        is_on_fn=lambda self: self._get_car_value("auxheat", "auxheatActive", "value", default_value=False),
        turn_on_fn=lambda self, **kwargs: self._coordinator.client.auxheat_start(self._vin),
        turn_off_fn=lambda self, **kwargs: self._coordinator.client.auxheat_stop(self._vin),
        check_capability_fn=lambda car: car.check_capabilities(["AUXHEAT_START", "AUXHEAT_STOP", "auxHeat"]),
    ),
]


class MercedesMeSwitch(MercedesMeEntity, SwitchEntity, RestoreEntity):
    """Representation of a Mercedes Me Switch."""

    def __init__(self, description: MercedesMeSwitchEntityDescription, vin, coordinator) -> None:
        """Initialize the switch with methods for handling on/off commands."""

        # Initialize command tracking variables
        self._expected_state = None  # True for on, False for off, or None
        self._state_confirmation_duration = STATE_CONFIRMATION_DURATION
        self._confirmation_handle = None

        super().__init__(description.key, description, vin, coordinator)

    async def async_turn_on(self, **kwargs: dict) -> None:
        """Turn the device component on."""
        await self._async_handle_state_change(state=True, **kwargs)

    async def async_turn_off(self, **kwargs: dict) -> None:
        """Turn the device component off."""
        await self._async_handle_state_change(state=False, **kwargs)

    async def _async_handle_state_change(self, state: bool, **kwargs) -> None:
        """Handle changing the device state and manage confirmation duration."""
        # Set the expected state based on the desired state
        self._expected_state = state

        try:
            # Execute the appropriate method and handle any exceptions
            if state:
                await self.entity_description.turn_on_fn(self, **kwargs)
            else:
                await self.entity_description.turn_off_fn(self, **kwargs)

            # Cancel any existing confirmation handle
            if self._confirmation_handle:
                self._confirmation_handle()

            # Schedule state reset after confirmation duration
            self._confirmation_handle = async_call_later(
                self.hass, self._state_confirmation_duration, self._reset_expected_state
            )

        except Exception as e:
            # Log the error and reset state if needed
            LOGGER.error(
                "Error changing state to %s for entity '%s': %s",
                "on" if state else "off",
                self.entity_description.translation_key,
                str(e),
            )
            self._expected_state = None
            if self._confirmation_handle:
                self._confirmation_handle()
                self._confirmation_handle = None
            self.async_write_ha_state()

    async def _reset_expected_state(self, _):
        """Reset the expected state after confirmation duration and update the state."""
        self._attr_is_on = not self._expected_state
        self._expected_state = None
        self._confirmation_handle = None
        self.async_write_ha_state()

    def _mercedes_me_update(self) -> None:
        """Update Mercedes Me entity."""
        try:
            actual_state = self.entity_description.is_on_fn(self)
        except Exception as e:
            LOGGER.error("Error getting actual state for %s: %s", self.name, str(e))
            self._attr_available = False
            return

        if self._expected_state is not None:
            if actual_state == self._expected_state:
                # Expected state reached, cancel confirmation duration
                if self._confirmation_handle:
                    self._confirmation_handle()
                    self._confirmation_handle = None
                self._expected_state = None
            else:
                # Return expected state during the confirmation duration
                self._attr_is_on = self._expected_state
        else:
            self._attr_is_on = actual_state
        self.async_write_ha_state()

    @property
    def assumed_state(self) -> bool:
        """Return True if the state is assumed."""
        return self._expected_state is not None


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the switch platform for Mercedes Me."""

    coordinator: MBAPI2020DataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    skip_capability_check: bool = config_entry.options.get(CONF_FT_DISABLE_CAPABILITY_CHECK, False)

    def check_capability(car: Car, description: MercedesMeSwitchEntityDescription) -> bool:
        """Check if the car supports the necessary capability for the given feature description."""
        if not skip_capability_check and not description.check_capability_fn(car):
            vin_masked = loghelper.Mask_VIN(car.finorvin)
            LOGGER.debug(
                "Skipping feature '%s' for VIN '%s' due to lack of required capability", description.key, vin_masked
            )
            return False
        return True

    def create_entity(description: MercedesMeSwitchEntityDescription, car: Car) -> MercedesMeSwitch | None:
        """Create a MercedesMeSwitch entity for the car based on the given description."""
        vin_masked = loghelper.Mask_VIN(car.finorvin)
        try:
            entity = MercedesMeSwitch(description, car.finorvin, coordinator)
            LOGGER.debug("Created switch entity for VIN: '%s', feature: '%s'", vin_masked, description.key)
        except Exception:
            LOGGER.error(
                "Error creating switch entity for VIN: '%s', feature: '%s'. Exception:",
                vin_masked,
                description.key,
                exc_info=True,
            )
            return None
        else:
            return entity

    entities: list[MercedesMeSwitch] = [
        entity
        for car in coordinator.client.cars.values()  # Iterate over all cars
        for description in SWITCH_DESCRIPTIONS  # Iterate over all feature descriptions
        if check_capability(car, description)  # Check if the car supports the feature
        and (entity := create_entity(description, car))  # Create the entity if possible
    ]

    async_add_entities(entities)
