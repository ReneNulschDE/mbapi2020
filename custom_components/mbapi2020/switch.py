"""Switch support for Mercedes cars with Mercedes ME.

For more details about this component, please refer to the documentation at
https://github.com/ReneNulschDE/mbapi2020/
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from config.custom_components.mbapi2020 import MercedesMeEntity, MercedesMeEntityConfig
from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_FT_DISABLE_CAPABILITY_CHECK,
    DOMAIN,
    LOGGER,
    STATE_CONFIRMATION_DURATION,
)
from .coordinator import MBAPI2020DataUpdateCoordinator
from .helper import LogHelper as loghelper, check_capabilities


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switch platform for Mercedes ME."""

    coordinator: MBAPI2020DataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]

    if not coordinator.client.cars:
        LOGGER.info("No cars found during the switch creation process")
        return

    entities: list[MercedesMESwitch] = []
    skip_capability_check = config_entry.options.get(
        CONF_FT_DISABLE_CAPABILITY_CHECK, False
    )

    for car in coordinator.client.cars.values():
        car_vin_masked = loghelper.Mask_VIN(car.finorvin)

        for config in SWITCH_CONFIGS:
            capability_check = getattr(config, "capability_check", None)
            if capability_check is None:
                LOGGER.error(
                    "Missing capability check for switch config '%s'. Skipping",
                    config.id,
                )
                continue

            if not skip_capability_check and not capability_check(car):
                LOGGER.debug(
                    "Car '%s' does not support feature '%s'. Skipping",
                    car_vin_masked,
                    config.id,
                )
                continue

            try:
                entity = MercedesMESwitch(
                    config=config, vin=car.finorvin, coordinator=coordinator
                )
                entities.append(entity)
                LOGGER.debug(
                    "Created switch entity for car '%s': Internal Name='%s', Entity Name='%s'",
                    car_vin_masked,
                    config.id,
                    config.entity_name,
                )
            except Exception as e:
                LOGGER.error(
                    "Error creating switch entity '%s' for car '%s': %s",
                    config.id,
                    car_vin_masked,
                    str(e),
                )

    async_add_entities(entities)


class SwitchTurnOn(Protocol):
    """Protocol for a callable that asynchronously turns on a MercedesME switch."""

    async def __call__(self, **kwargs) -> None:
        """Asynchronously turn on the switch."""


class SwitchTurnOff(Protocol):
    """Protocol for a callable that asynchronously turns off a MercedesME switch."""

    async def __call__(self, **kwargs) -> None:
        """Asynchronously turn off the switch."""


class SwitchIsOn(Protocol):
    """Protocol for a callable that checks if a MercedesME switch is on."""

    def __call__(self) -> bool:
        """Check if the switch is currently on."""


@dataclass(frozen=True)
class MercedesMeSwitchConfig(MercedesMeEntityConfig):
    """Configuration class for MercedesMe switch entities."""

    turn_on: SwitchTurnOn | None = None
    turn_off: SwitchTurnOff | None = None
    is_on: SwitchIsOn | None = None

    def __post_init__(self):
        """Post-initialization checks to ensure required fields are set."""
        if self.capability_check is None:
            raise ValueError(f"capability_check is required for {self.__class__.__name__}")
        if self.turn_on is None:
            raise ValueError(f"turn_on is required for {self.__class__.__name__}")
        if self.turn_off is None:
            raise ValueError(f"turn_off is required for {self.__class__.__name__}")

    def __repr__(self) -> str:
        """Return a string representation of the MercedesMeSwitchEntityConfig instance."""
        return (
            f"{self.__class__.__name__}("
            f"internal_name={self.id!r}, "
            f"entity_name={self.entity_name!r}, "
            f"feature_name={self.feature_name!r}, "
            f"object_name={self.object_name!r}, "
            f"attribute_name={self.attribute_name!r}, "
            f"capability_check={self.capability_check!r}, "
            f"attributes={self.attributes!r}, "
            f"device_class={self.device_class!r}, "
            f"icon={self.icon!r}, "
            f"entity_category={self.entity_category!r}, "
            f"turn_on={self.turn_on!r}, "
            f"turn_off={self.turn_off!r}, "
            f"is_on={self.is_on!r})"
        )


class MercedesMESwitch(MercedesMeEntity, SwitchEntity, RestoreEntity):
    """Representation of a Mercedes Me Switch."""

    def __init__(self, config: MercedesMeSwitchConfig, vin, coordinator) -> None:
        """Initialize the switch with methods for handling on/off commands."""
        self._turn_on_method = config.turn_on
        self._turn_off_method = config.turn_off
        self._is_on_method = config.is_on

        # Initialize command tracking variables
        self._expected_state = None  # True for on, False for off, or None
        self._state_confirmation_duration = STATE_CONFIRMATION_DURATION
        self._confirmation_handle = None

        super().__init__(config.id, config, vin, coordinator)

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

        # Execute the appropriate method based on the desired state
        if state:
            await self._turn_on_method(self, **kwargs)
        else:
            await self._turn_off_method(self, **kwargs)

        # Cancel previous confirmation if any
        if self._confirmation_handle:
            self._confirmation_handle()

        # Schedule state reset after confirmation duration
        self._confirmation_handle = async_call_later(
            self.hass, self._state_confirmation_duration, self._reset_expected_state
        )

        # Update the UI
        self.async_write_ha_state()

    async def _reset_expected_state(self, _):
        """Reset the expected state after confirmation duration and update the state."""
        self._expected_state = None
        self._confirmation_handle = None
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return True if the device is on."""
        actual_state = self._get_actual_state()

        if self._expected_state is not None:
            if actual_state == self._expected_state:
                # Expected state reached, cancel confirmation duration
                if self._confirmation_handle:
                    self._confirmation_handle()
                    self._confirmation_handle = None
                self._expected_state = None
            else:
                # Return expected state during the confirmation duration
                return self._expected_state

        return actual_state

    def _get_actual_state(self) -> bool:
        """Return the actual state of the device."""
        if self._is_on_method:
            return self._is_on_method()
        return self._default_is_on()

    def _default_is_on(self) -> bool:
        """Provide default implementation for determining the 'on' state."""
        return self._get_car_value(
            self._feature_name,
            self._object_name,
            self._attrib_name,
            default_value=False,
        )

    @property
    def assumed_state(self) -> bool:
        """Return True if the state is being assumed during the confirmation duration."""
        return self._expected_state is not None

SWITCH_CONFIGS: list[MercedesMeSwitchConfig] = [
    MercedesMeSwitchConfig(
        id="pre_entry_climate_control",
        entity_name="Pre-entry climate control",
        feature_name="precond",
        object_name="precondStatus",
        attribute_name="value",
        icon="mdi:hvac",
        device_class=SwitchDeviceClass.SWITCH,
        turn_on=lambda self, **kwargs: self._coordinator.client.preheat_start_universal(self._vin),
        turn_off=lambda self, **kwargs: self._coordinator.client.preheat_stop(self._vin),
        capability_check=lambda car: check_capabilities(
            car, ["ZEV_PRECONDITIONING_START", "ZEV_PRECONDITIONING_STOP"]
        ),
    ),
    MercedesMeSwitchConfig(
        id="auxheat",
        entity_name="Auxiliary Heating",
        feature_name="auxheat",
        object_name="auxheatActive",
        attribute_name="value",
        icon="mdi:hvac",
        device_class=SwitchDeviceClass.SWITCH,
        turn_on=lambda self, **kwargs: self._coordinator.client.auxheat_start(self._vin),
        turn_off=lambda self, **kwargs: self._coordinator.client.auxheat_stop(self._vin),
        capability_check=lambda car: check_capabilities(
            car, ["AUXHEAT_START", "AUXHEAT_STOP"]
        ),
    ),
]
