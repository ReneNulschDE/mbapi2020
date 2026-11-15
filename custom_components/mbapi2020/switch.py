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
from homeassistant.helpers.restore_state import RestoreEntity

from . import MercedesMeEntity, MercedesMeEntityDescription, async_setup_described_platform
from .const import LOGGER


@dataclass(frozen=True, kw_only=True)
class MercedesMeSwitchEntityDescription(MercedesMeEntityDescription, SwitchEntityDescription):
    """Configuration class for MercedesMe switch entities."""

    is_on_fn: Callable[[MercedesMeSwitch], Callable[[], Coroutine[Any, Any, bool]]]
    turn_on_fn: Callable[[MercedesMeSwitch], Callable[[], Coroutine[Any, Any, None]]]
    turn_off_fn: Callable[[MercedesMeSwitch], Callable[[], Coroutine[Any, Any, None]]]
    has_state_fn: Callable[[MercedesMeSwitch], bool] | None = None
    attributes_fn: Callable[[MercedesMeSwitch], dict[str, Any]] | None = None


SWITCH_DESCRIPTIONS: list[MercedesMeSwitchEntityDescription] = [
    MercedesMeSwitchEntityDescription(
        key="precond",
        translation_key="precond",
        icon="mdi:hvac",
        is_on_fn=lambda self: self._get_car_value("precond", "precondStatus", "value", default_value=False),
        turn_on_fn=lambda self, **kwargs: self._coordinator.client.preheat_start_universal(self._vin),
        turn_off_fn=lambda self, **kwargs: self._coordinator.client.preheat_stop_universal(self._vin),
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
    MercedesMeSwitchEntityDescription(
        key="hv_battery_conditioning",
        translation_key="hv_battery_conditioning",
        icon="mdi:battery-heart-variant",
        is_on_fn=lambda self: bool(
            self._get_car_value("electric", "hvBatteryPrecondActive", "value", default_value=False)
        ),
        has_state_fn=lambda self: self._is_car_attribute_valid("electric", "hvBatteryPrecondActive"),
        attributes_fn=lambda self: _hv_battery_attributes(self),
        turn_on_fn=lambda self, **kwargs: self._coordinator.client.hv_battery_start_conditioning(self._vin),
        turn_off_fn=lambda self, **kwargs: self._coordinator.client.hv_battery_stop_conditioning(self._vin),
        check_capability_fn=lambda car: car.check_capabilities(
            ["HVBATTERY_START_CONDITIONING", "HVBATTERY_STOP_CONDITIONING"]
        ),
    ),
]


def _hv_battery_attributes(entity: MercedesMeSwitch) -> dict[str, Any]:
    """Return telemetry attributes for HV battery conditioning when available."""
    attrs: dict[str, Any] = {}
    for attr_name, output_key in (
        ("hvBatteryPrecondState", "state"),
        ("hvBatteryPrecondAvailability", "availability"),
        ("hvBatteryPrecondDuration", "duration"),
    ):
        if entity._is_car_attribute_valid("electric", attr_name):
            val = entity._get_car_value("electric", attr_name, "display_value", None)
            if val is None or val == "":
                val = entity._get_car_value("electric", attr_name, "value", None)
            if val is not None:
                attrs[output_key] = val
    return attrs


class MercedesMeSwitch(MercedesMeEntity, SwitchEntity, RestoreEntity):
    """Representation of a Mercedes Me Switch."""

    def __init__(self, description: MercedesMeSwitchEntityDescription, vin, coordinator) -> None:
        """Initialize the switch with methods for handling on/off commands."""

        # Initialize command tracking variables
        self._expected_state = None  # True for on, False for off, or None
        super().__init__(description.key, description, vin, coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return base attributes merged with switch-specific telemetry attributes."""
        attrs = dict(super().extra_state_attributes)
        if self.entity_description.attributes_fn is not None:
            attrs.update(self.entity_description.attributes_fn(self))
        return attrs

    async def async_turn_on(self, **kwargs: dict) -> None:
        """Turn the device component on."""
        await self._async_handle_state_change(state=True, **kwargs)

    async def async_turn_off(self, **kwargs: dict) -> None:
        """Turn the device component off."""
        await self._async_handle_state_change(state=False, **kwargs)

    async def _async_handle_state_change(self, state: bool, **kwargs) -> None:
        """Handle changing the device state and manage confirmation duration."""
        self._assert_push_mode()
        self._expected_state = state

        try:
            # Execute the appropriate method and handle any exceptions
            if state:
                await self.entity_description.turn_on_fn(self, **kwargs)
            else:
                await self.entity_description.turn_off_fn(self, **kwargs)

            self._schedule_confirmation(self._reset_expected_state)

        except Exception as e:  # noqa: BLE001 - also performs the optimistic-state cleanup below; a
            # narrower catch would let an unexpected error leave the switch stuck
            # Log the error and reset state if needed
            LOGGER.error(
                "Error changing state to %s for entity '%s': %s",
                "on" if state else "off",
                self.entity_description.translation_key,
                str(e),
            )
            self._expected_state = None
            self._cancel_confirmation()
            self._safe_write_ha_state()

    async def _reset_expected_state(self, _):
        """Reset the expected state after confirmation duration and update the state."""
        self._attr_is_on = not self._expected_state
        self._expected_state = None
        self._confirmation_handle = None
        self._safe_write_ha_state()

    def _mercedes_me_update(self) -> None:
        """Update Mercedes Me entity."""
        try:
            actual_state = self.entity_description.is_on_fn(self)
        except Exception as e:  # noqa: BLE001 - a failure to read state marks the entity unavailable,
            # which is better than propagating into the update loop
            LOGGER.error("Error getting actual state for %s: %s", self.name, str(e))
            self._attr_available = False
            return

        if self._expected_state is not None:
            if actual_state == self._expected_state:
                self._cancel_confirmation()
                self._expected_state = None
            else:
                # Return expected state during the confirmation duration
                self._attr_is_on = self._expected_state
        else:
            self._attr_is_on = actual_state
        self._safe_write_ha_state()

    @property
    def assumed_state(self) -> bool:
        """Return True if the state is assumed or telemetry is unavailable."""
        if self._expected_state is not None:
            return True
        if self.entity_description.has_state_fn is not None:
            return not self.entity_description.has_state_fn(self)
        return False


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the switch platform for Mercedes Me."""
    await async_setup_described_platform(
        hass, config_entry, async_add_entities, SWITCH_DESCRIPTIONS, MercedesMeSwitch, "switch"
    )
