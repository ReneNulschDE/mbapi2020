"""Number platform support for Mercedes cars with Mercedes ME."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MercedesMeEntity, MercedesMeEntityDescription, async_setup_described_platform
from .car import Car
from .const import LOGGER


@dataclass(frozen=True, kw_only=True)
class MercedesMeNumberEntityDescription(MercedesMeEntityDescription, NumberEntityDescription):
    """Configuration class for MercedesMe number entities."""

    value_fn: Callable[[MercedesMeNumber], float | None]
    set_value_fn: Callable[[MercedesMeNumber, float], Coroutine[Any, Any, None]]
    limits_fn: Callable[[Car], tuple[float, float, float]]
    check_capability_fn: Callable[[Car], bool]


def _read_valid_float(car: Car, feature: str, attr_name: str) -> float | None:
    """Return a parsed float when the given car electric attribute is valid."""
    feature_obj = getattr(car, feature, None)
    attr = getattr(feature_obj, attr_name, None) if feature_obj else None
    if attr is None or getattr(attr, "retrievalstatus", None) != "VALID":
        return None
    raw = getattr(attr, "value", None)
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _read_max_soc(entity: MercedesMeNumber) -> float | None:
    """Read target max SoC across MB.OS (maxSoc) and MBUX (max_soc) attributes."""
    car = entity._car
    use_program_soc = bool(
        car.features.get("CHARGE_PROGRAM_CONFIGURE") is True
        or (not car.features.get("CHARGING_CONFIGURE") and not car.features.get("BATTERY_MAX_SOC_CONFIGURE"))
    )
    order = ("max_soc", "maxSoc") if use_program_soc else ("maxSoc", "max_soc")
    for attr_name in order:
        value = _read_valid_float(car, "electric", attr_name)
        if value is not None:
            return value
    return None


def _max_soc_limits(car: Car) -> tuple[float, float, float]:
    """Compute (min_value, max_value, step) matching client.battery_max_soc_configure."""
    features = car.features or {}
    if features.get("CHARGING_CONFIGURE") is True:
        params = car.get_command_parameters("CHARGING_CONFIGURE")
        param = params.get("MAX_SOC") or params.get("CHARGING_MAX_SOC") or {}
        default_min, default_max, default_step = 0.0, 100.0, 1.0
        command_floor = 0.0
    elif features.get("BATTERY_MAX_SOC_CONFIGURE") is True and features.get("CHARGE_PROGRAM_CONFIGURE") is not True:
        params = car.get_command_parameters("BATTERY_MAX_SOC_CONFIGURE")
        param = params.get("MAX_SOC") or {}
        default_min, default_max, default_step = 50.0, 100.0, 10.0
        command_floor = 50.0
    else:
        params = car.get_command_parameters("CHARGE_PROGRAM_CONFIGURE")
        param = params.get("MAX_SOC") or {}
        default_min, default_max, default_step = 50.0, 100.0, 10.0
        command_floor = 50.0

    min_val = float(param.get("minValue", default_min))
    max_val = float(param.get("maxValue", default_max))
    step_val = float(param.get("steps", default_step) or default_step)
    min_val = max(min_val, command_floor)

    lower_limit = _read_valid_float(car, "electric", "maxSocLowerLimit")
    upper_limit = _read_valid_float(car, "electric", "maxSocUpperLimit")
    effective_min = max(min_val, lower_limit) if lower_limit is not None else min_val
    effective_max = min(max_val, upper_limit) if upper_limit is not None else max_val
    if effective_min <= effective_max:
        return effective_min, effective_max, step_val
    return min_val, max_val, step_val


NUMBER_DESCRIPTIONS: list[MercedesMeNumberEntityDescription] = [
    MercedesMeNumberEntityDescription(
        key="max_soc",
        translation_key="max_soc",
        icon="mdi:battery-charging-high",
        device_class=NumberDeviceClass.BATTERY,
        mode=NumberMode.SLIDER,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.CONFIG,
        value_fn=_read_max_soc,
        limits_fn=_max_soc_limits,
        set_value_fn=lambda self, value: self._coordinator.client.battery_max_soc_configure(
            self._vin, int(round(value))
        ),
        check_capability_fn=lambda car: car.check_capabilities(
            ["CHARGING_CONFIGURE", "BATTERY_MAX_SOC_CONFIGURE", "CHARGE_PROGRAM_CONFIGURE"]
        ),
    ),
]


class MercedesMeNumber(MercedesMeEntity, NumberEntity):
    """Representation of a Mercedes Me Number entity."""

    entity_description: MercedesMeNumberEntityDescription

    def __init__(self, description: MercedesMeNumberEntityDescription, vin: str, coordinator) -> None:
        """Initialize the number entity and its optimistic confirmation state."""
        self._expected_value: float | None = None
        super().__init__(description.key, description, vin, coordinator)
        self._refresh_limits()

    def _refresh_limits(self) -> None:
        """Refresh dynamic slider bounds and step from vehicle capabilities and limits."""
        min_val, max_val, step_val = self.entity_description.limits_fn(self._car)
        self._attr_native_min_value = min_val
        self._attr_native_max_value = max_val
        self._attr_native_step = step_val

    async def async_set_native_value(self, value: float) -> None:
        """Set a new numeric target on the vehicle."""
        self._assert_push_mode()
        target = float(int(round(value)))
        self._expected_value = target
        self._attr_native_value = target
        self._safe_write_ha_state()

        try:
            await self.entity_description.set_value_fn(self, target)
            self._schedule_confirmation(self._reset_expected_value)
        except ServiceValidationError:
            self._expected_value = None
            self._cancel_confirmation()
            self._mercedes_me_update()
            raise
        except Exception as err:  # noqa: BLE001 - reverts optimistic state on failure
            LOGGER.error(
                "Error setting value %s for entity '%s': %s",
                target,
                self.entity_description.translation_key,
                str(err),
            )
            self._expected_value = None
            self._cancel_confirmation()
            self._mercedes_me_update()

    async def _reset_expected_value(self, _) -> None:
        """Clear pending optimistic expectation once the confirmation timeout expires."""
        self._expected_value = None
        self._confirmation_handle = None
        self._mercedes_me_update()

    def _mercedes_me_update(self) -> None:
        """Update number state and bounds from latest vehicle telemetry."""
        self._refresh_limits()
        actual = self.entity_description.value_fn(self)
        if self._expected_value is not None:
            if actual is not None and abs(actual - self._expected_value) < 0.5:
                self._cancel_confirmation()
                self._expected_value = None
                self._attr_native_value = actual
            else:
                self._attr_native_value = self._expected_value
        else:
            self._attr_native_value = actual
        self._safe_write_ha_state()

    @property
    def assumed_state(self) -> bool:
        """Return True while awaiting vehicle confirmation."""
        return self._expected_value is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return base attributes plus valid max SoC limit metadata."""
        attrs = dict(super().extra_state_attributes)
        for src_attr, out_key in (
            ("maxSocLowerLimit", "max_soc_lower_limit"),
            ("maxSocUpperLimit", "max_soc_upper_limit"),
        ):
            val = _read_valid_float(self._car, "electric", src_attr)
            if val is not None:
                attrs[out_key] = int(val) if val.is_integer() else val
        return attrs


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the number platform for Mercedes Me."""
    await async_setup_described_platform(
        hass, config_entry, async_add_entities, NUMBER_DESCRIPTIONS, MercedesMeNumber, "number"
    )
