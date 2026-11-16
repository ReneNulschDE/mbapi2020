"""Select platform support for Mercedes cars with Mercedes ME."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MercedesMeEntity, MercedesMeEntityDescription, async_setup_described_platform
from .car import Car
from .const import LOGGER

CHARGE_PROGRAM_ID_TO_OPTION: dict[int, str] = {
    0: "default",
    1: "instant",
    2: "home",
    3: "work",
    4: "ac_dc_standard",
    5: "ac_dc_standard_range_assist",
    6: "dc_cp_v2x_chademo",
    7: "dc_cp_v2x_iso_dynamic",
    8: "dc_cp_v2x_iso_scheduled",
    9: "ac_dc_opportunity",
    10: "ac_ev_timer",
    11: "ac_dc_din_iso_scheduled",
    12: "ac_api_remote_schedule",
    13: "ac_dc_battery_calibration",
}

CHARGE_PROGRAM_OPTION_TO_ID: dict[str, int] = {option: pid for pid, option in CHARGE_PROGRAM_ID_TO_OPTION.items()}

_ENUM_NAME_TO_OPTION: dict[str, str] = {
    "DEFAULT": "default",
    "INSTANT": "instant",
    "HOME": "home",
    "WORK": "work",
    "AC_DC_STANDARD": "ac_dc_standard",
}


@dataclass(frozen=True, kw_only=True)
class MercedesMeSelectEntityDescription(MercedesMeEntityDescription, SelectEntityDescription):
    """Configuration class for MercedesMe select entities."""

    options_fn: Callable[[Car], list[str]]
    current_option_fn: Callable[[MercedesMeSelect], str | None]
    select_option_fn: Callable[[MercedesMeSelect, str], Coroutine[Any, Any, None]]
    check_capability_fn: Callable[[Car], bool]


def _read_charge_program_id(car: Car) -> int | None:
    """Return the integer selectedChargeProgram when valid, else None."""
    electric = getattr(car, "electric", None)
    attr = getattr(electric, "selectedChargeProgram", None) if electric else None
    if attr is None or getattr(attr, "retrievalstatus", None) != "VALID":
        return None
    raw = getattr(attr, "value", None)
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _charge_program_options(car: Car) -> list[str]:
    """Return selectable charge program options supported by this vehicle."""
    features = car.features or {}
    if features.get("CHARGING_CONFIGURE") is True and features.get("CHARGE_PROGRAM_CONFIGURE") is not True:
        params = car.get_command_parameters("BATTERY_CHARGE_PROGRAM_CONFIGURE")
        allowed = (params.get("CHARGE_PROGRAM") or {}).get("allowedEnums") or []
        if allowed:
            options = [_ENUM_NAME_TO_OPTION[item] for item in allowed if item in _ENUM_NAME_TO_OPTION]
            electric = getattr(car, "electric", None)
            charge_programs_attr = getattr(electric, "chargePrograms", None) if electric else None
            charge_programs = getattr(charge_programs_attr, "value", None) if charge_programs_attr else None
            if isinstance(charge_programs, dict):
                for prog_id in sorted(charge_programs):
                    if (
                        isinstance(prog_id, int)
                        and (mapped := CHARGE_PROGRAM_ID_TO_OPTION.get(prog_id))
                        and mapped not in options
                    ):
                        options.append(mapped)
            if "ac_dc_standard" not in options:
                options.append("ac_dc_standard")
        else:
            options = ["default", "instant", "home", "work", "ac_dc_standard"]
        current_id = _read_charge_program_id(car)
        if current_id is not None and (mapped := CHARGE_PROGRAM_ID_TO_OPTION.get(current_id)) and mapped not in options:
            options.append(mapped)
        return options

    if (
        features.get("BATTERY_CHARGE_PROGRAM_CONFIGURE") is True
        and features.get("CHARGE_PROGRAM_CONFIGURE") is not True
    ):
        params = car.get_command_parameters("BATTERY_CHARGE_PROGRAM_CONFIGURE")
        allowed = (params.get("CHARGE_PROGRAM") or {}).get("allowedEnums") or []
        mapped = [_ENUM_NAME_TO_OPTION[item] for item in allowed if item in _ENUM_NAME_TO_OPTION]
        return mapped or ["default", "instant"]

    return ["default", "home", "work"]


def _current_charge_program_option(entity: MercedesMeSelect) -> str | None:
    """Return the current charge program option when valid and selectable."""
    prog_id = _read_charge_program_id(entity._car)
    if prog_id is None:
        return None
    option = CHARGE_PROGRAM_ID_TO_OPTION.get(prog_id)
    if option is None or option not in entity._attr_options:
        return None
    return option


async def _select_charge_program(entity: MercedesMeSelect, option: str) -> None:
    """Send selected charge program option to client.charge_program_configure."""
    program_id = CHARGE_PROGRAM_OPTION_TO_ID.get(option)
    if program_id is None or option not in entity.options:
        raise ServiceValidationError(f"Unsupported charge program option: {option}")
    await entity._coordinator.client.charge_program_configure(entity._vin, program_id)


SELECT_DESCRIPTIONS: list[MercedesMeSelectEntityDescription] = [
    MercedesMeSelectEntityDescription(
        key="charge_program",
        translation_key="charge_program",
        icon="mdi:ev-station",
        entity_category=EntityCategory.CONFIG,
        options_fn=_charge_program_options,
        current_option_fn=_current_charge_program_option,
        select_option_fn=_select_charge_program,
        check_capability_fn=lambda car: car.check_capabilities(
            ["CHARGING_CONFIGURE", "BATTERY_CHARGE_PROGRAM_CONFIGURE", "CHARGE_PROGRAM_CONFIGURE"]
        ),
    ),
]


class MercedesMeSelect(MercedesMeEntity, SelectEntity):
    """Representation of a Mercedes Me Select entity."""

    entity_description: MercedesMeSelectEntityDescription

    def __init__(self, description: MercedesMeSelectEntityDescription, vin: str, coordinator) -> None:
        """Initialize the select entity and its optimistic confirmation state."""
        self._expected_option: str | None = None
        super().__init__(description.key, description, vin, coordinator)
        self._attr_options = self.entity_description.options_fn(self._car)

    async def async_select_option(self, option: str) -> None:
        """Select a new option on the vehicle."""
        self._assert_push_mode()
        self._attr_options = self.entity_description.options_fn(self._car)
        if option not in self._attr_options:
            raise ServiceValidationError(f"Unsupported option '{option}' for {self.entity_description.key}")

        self._expected_option = option
        self._attr_current_option = option
        self._safe_write_ha_state()

        try:
            await self.entity_description.select_option_fn(self, option)
            self._schedule_confirmation(self._reset_expected_option)
        except ServiceValidationError:
            self._expected_option = None
            self._cancel_confirmation()
            self._mercedes_me_update()
            raise
        except Exception as err:  # noqa: BLE001 - reverts optimistic state on failure
            LOGGER.error(
                "Error selecting option '%s' for entity '%s': %s",
                option,
                self.entity_description.translation_key,
                str(err),
            )
            self._expected_option = None
            self._cancel_confirmation()
            self._mercedes_me_update()

    async def _reset_expected_option(self, _) -> None:
        """Clear optimistic expectation after confirmation duration."""
        self._expected_option = None
        self._confirmation_handle = None
        self._mercedes_me_update()

    def _mercedes_me_update(self) -> None:
        """Refresh options and current option from latest vehicle telemetry."""
        self._attr_options = self.entity_description.options_fn(self._car)
        actual = self.entity_description.current_option_fn(self)
        if self._expected_option is not None:
            if actual == self._expected_option:
                self._cancel_confirmation()
                self._expected_option = None
                self._attr_current_option = actual
            else:
                self._attr_current_option = self._expected_option
        else:
            self._attr_current_option = actual
        self._safe_write_ha_state()

    @property
    def assumed_state(self) -> bool:
        """Return True while awaiting confirmation from the vehicle."""
        return self._expected_option is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Include the raw numeric charge program identifier when available."""
        attrs = dict(super().extra_state_attributes)
        prog_id = _read_charge_program_id(self._car)
        if prog_id is not None:
            attrs["program_id"] = prog_id
        return attrs


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the select platform for Mercedes Me."""
    await async_setup_described_platform(
        hass, config_entry, async_add_entities, SELECT_DESCRIPTIONS, MercedesMeSelect, "select"
    )
