"""Climate platform support for Mercedes cars with Mercedes ME."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ClimateEntity,
    ClimateEntityDescription,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MercedesMeEntity, MercedesMeEntityDescription, async_setup_described_platform
from .car import Car
from .const import LOGGER

_TEMPERATURE_ZONES: tuple[tuple[str, str, str, str], ...] = (
    ("front_left", "temperature_points_frontLeft", "temperature_points_frontLeftActive", "FRONT_LEFT"),
    ("front_right", "temperature_points_frontRight", "temperature_points_frontRightActive", "FRONT_RIGHT"),
    ("rear_left", "temperature_points_rearLeft", "temperature_points_rearLeftActive", "REAR_LEFT"),
    ("rear_right", "temperature_points_rearRight", "temperature_points_rearRightActive", "REAR_RIGHT"),
)


@dataclass(frozen=True, kw_only=True)
class MercedesMeClimateEntityDescription(MercedesMeEntityDescription, ClimateEntityDescription):
    """Configuration class for MercedesMe climate entities."""

    check_capability_fn: Callable[[Car], bool]


CLIMATE_DESCRIPTIONS: list[MercedesMeClimateEntityDescription] = [
    MercedesMeClimateEntityDescription(
        key="preclimate",
        translation_key="preclimate",
        icon="mdi:thermostat",
        check_capability_fn=lambda car: car.check_capabilities(
            ["ZEV_PRECONDITIONING_START", "ZEV_PRECONDITIONING_STOP", "AUXHEAT_START", "AUXHEAT_STOP", "auxHeat"]
        ),
    ),
]


class MercedesMeClimate(MercedesMeEntity, ClimateEntity):
    """Representation of the Mercedes Me cabin pre-conditioning climate entity."""

    entity_description: MercedesMeClimateEntityDescription
    # Use _attr_native_temperature_unit on HA 2026.11+ while keeping fallback for older cores.
    if hasattr(ClimateEntity, "_attr_native_temperature_unit"):
        _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    else:
        _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(self, description: MercedesMeClimateEntityDescription, vin: str, coordinator) -> None:
        """Initialize the climate entity and determine car capabilities."""
        self._expected_hvac_mode: HVACMode | None = None
        self._expected_temperature: float | None = None
        super().__init__(description.key, description, vin, coordinator)
        self._refresh_capabilities()

    def _refresh_capabilities(self) -> None:
        """Compute supported HVAC modes, features, and temperature limits for the car."""
        self._supports_zev = self._car.check_capabilities(["ZEV_PRECONDITIONING_START", "ZEV_PRECONDITIONING_STOP"])
        self._supports_auxheat = self._car.check_capabilities(["AUXHEAT_START", "AUXHEAT_STOP", "auxHeat"])
        self._supports_temperature = self._car.check_capabilities(["TEMPERATURE_CONFIGURE"])

        modes: list[HVACMode] = [HVACMode.OFF]
        if self._supports_zev:
            modes.append(HVACMode.HEAT_COOL)
        if self._supports_auxheat:
            modes.append(HVACMode.HEAT)
        self._attr_hvac_modes = modes

        features = ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        if self._supports_temperature:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE
        self._attr_supported_features = features

        temp_param = self._car.get_command_parameters("TEMPERATURE_CONFIGURE").get("TEMPERATURE_POINTS_TEMPERATURE", {})
        base_min = float(temp_param.get("minValue", 16.0))
        base_max = float(temp_param.get("maxValue", 28.0))
        actual_temp = self._actual_target_temperature()
        self._attr_min_temp = base_min
        self._attr_max_temp = max(base_max, actual_temp) if actual_temp is not None else base_max
        self._attr_target_temperature_step = float(temp_param.get("steps", 0.5) or 0.5)

    def _read_zone_state(self) -> tuple[dict[str, float], dict[str, bool]]:
        """Read valid target temperatures (in Celsius) and active flags per cabin zone."""
        temps: dict[str, float] = {}
        active_flags: dict[str, bool] = {}

        for zone_key, temp_attr, active_attr, _enum_name in _TEMPERATURE_ZONES:
            if self._is_car_attribute_valid("precond", temp_attr):
                raw_val = self._get_car_value("precond", temp_attr, "value", None)
                if raw_val is not None and not isinstance(raw_val, bool):
                    try:
                        val = float(raw_val)
                    except (TypeError, ValueError):
                        val = None
                    if val is not None:
                        unit = self._get_car_value("precond", temp_attr, "unit", None)
                        if unit == "FAHRENHEIT" and val > 40.0:
                            val = round(((val - 32.0) * 5.0 / 9.0) * 2.0) / 2.0
                        temps[zone_key] = val

            if self._is_car_attribute_valid("precond", active_attr):
                active_val = self._get_car_value("precond", active_attr, "value", None)
                if active_val is not None:
                    active_flags[zone_key] = bool(active_val)

        return temps, active_flags

    def _actual_target_temperature(self) -> float | None:
        """Return target temperature prioritizing active zones."""
        temps, active_flags = self._read_zone_state()
        if not temps:
            return None
        active_temps = [temps[zone] for zone in temps if active_flags.get(zone)]
        if active_temps:
            return active_temps[0]
        return next(iter(temps.values()))

    def _actual_hvac_mode(self) -> HVACMode:
        """Return actual HVACMode from ZEV preconditioning or auxiliary heater status."""
        if (
            self._supports_auxheat
            and self._is_car_attribute_valid("auxheat", "auxheatActive")
            and bool(self._get_car_value("auxheat", "auxheatActive", "value", False))
        ):
            return HVACMode.HEAT

        if self._supports_zev:
            precond_active = bool(
                (
                    self._is_car_attribute_valid("precond", "precondStatus")
                    and self._get_car_value("precond", "precondStatus", "value", False)
                )
                or (
                    self._is_car_attribute_valid("precond", "precondActive")
                    and self._get_car_value("precond", "precondActive", "value", False)
                )
            )
            if precond_active:
                return HVACMode.HEAT_COOL

        return HVACMode.OFF

    async def async_turn_on(self) -> None:
        """Turn cabin conditioning on using the primary mode supported by the vehicle."""
        target_mode = HVACMode.HEAT_COOL if HVACMode.HEAT_COOL in self._attr_hvac_modes else HVACMode.HEAT
        await self.async_set_hvac_mode(target_mode)

    async def async_turn_off(self) -> None:
        """Turn cabin conditioning off."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Switch cabin preconditioning or auxiliary heater mode."""
        self._assert_push_mode()
        if hvac_mode not in self._attr_hvac_modes:
            raise ServiceValidationError(f"Unsupported HVAC mode '{hvac_mode}' for this vehicle")

        previous_mode = self._attr_hvac_mode
        self._expected_hvac_mode = hvac_mode
        self._attr_hvac_mode = hvac_mode
        self._attr_hvac_action = self._mode_to_action(hvac_mode)
        self._safe_write_ha_state()

        try:
            if hvac_mode == HVACMode.HEAT:
                await self._coordinator.client.auxheat_start(self._vin)
            elif hvac_mode == HVACMode.HEAT_COOL:
                await self._coordinator.client.preheat_start_universal(self._vin)
            elif previous_mode == HVACMode.HEAT or (self._supports_auxheat and not self._supports_zev):
                await self._coordinator.client.auxheat_stop(self._vin)
            else:
                await self._coordinator.client.preheat_stop_universal(self._vin)

            self._schedule_confirmation(self._reset_expected_state)
        except Exception as err:  # noqa: BLE001 - reverts optimistic state on failure
            LOGGER.error("Error setting HVAC mode to %s: %s", hvac_mode, str(err))
            self._expected_hvac_mode = None
            self._cancel_confirmation()
            self._mercedes_me_update()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature for supported cabin zones and optional HVAC mode."""
        self._assert_push_mode()
        if ATTR_HVAC_MODE in kwargs and kwargs[ATTR_HVAC_MODE] is not None:
            await self.async_set_hvac_mode(HVACMode(kwargs[ATTR_HVAC_MODE]))

        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        if not self._supports_temperature:
            raise ServiceValidationError("TEMPERATURE_CONFIGURE is not supported by this vehicle")

        zone_param = self._car.get_command_parameters("TEMPERATURE_CONFIGURE").get("TEMPERATURE_POINTS_ZONE", {})
        allowed_enums = set(zone_param.get("allowedEnums") or ["FRONT_LEFT", "FRONT_RIGHT"])
        zone_kwargs: dict[str, float] = {}
        _, active_flags = self._read_zone_state()
        for zone_key, temp_attr, _active_attr, enum_name in _TEMPERATURE_ZONES:
            if enum_name not in allowed_enums:
                continue
            # Always update front driver/passenger when supported; update rear zones if allowed and active or already reported.
            if (
                zone_key.startswith("front")
                or active_flags.get(zone_key)
                or self._is_car_attribute_valid("precond", temp_attr)
            ):
                zone_kwargs[zone_key] = float(temp)

        if not zone_kwargs:
            zone_kwargs = {"front_left": float(temp), "front_right": float(temp)}

        self._expected_temperature = float(temp)
        self._attr_native_target_temperature = float(temp)
        self._safe_write_ha_state()

        try:
            await self._coordinator.client.temperature_configure(self._vin, **zone_kwargs)
            self._schedule_confirmation(self._reset_expected_state)
        except Exception as err:  # noqa: BLE001 - reverts optimistic state on failure
            LOGGER.error("Error setting cabin temperature to %s: %s", temp, str(err))
            self._expected_temperature = None
            self._cancel_confirmation()
            self._mercedes_me_update()

    async def _reset_expected_state(self, _) -> None:
        """Clear pending optimistic expectations after confirmation timeout."""
        self._expected_hvac_mode = None
        self._expected_temperature = None
        self._confirmation_handle = None
        self._mercedes_me_update()

    @staticmethod
    def _mode_to_action(mode: HVACMode) -> HVACAction:
        """Map active HVACMode to Home Assistant HVACAction."""
        if mode == HVACMode.HEAT:
            return HVACAction.HEATING
        if mode == HVACMode.HEAT_COOL:
            return HVACAction.PREHEATING
        return HVACAction.OFF

    def _mercedes_me_update(self) -> None:
        """Synchronize climate entity state with latest vehicle telemetry."""
        self._refresh_capabilities()
        actual_mode = self._actual_hvac_mode()
        actual_temp = self._actual_target_temperature()

        if self._expected_hvac_mode is not None:
            if actual_mode == self._expected_hvac_mode:
                self._expected_hvac_mode = None
            else:
                self._attr_hvac_mode = self._expected_hvac_mode
        if self._expected_hvac_mode is None:
            self._attr_hvac_mode = actual_mode
        self._attr_hvac_action = self._mode_to_action(self._attr_hvac_mode)

        if self._expected_temperature is not None:
            if actual_temp is not None and abs(actual_temp - self._expected_temperature) < 0.05:
                self._expected_temperature = None
            else:
                self._attr_native_target_temperature = self._expected_temperature
        if self._expected_temperature is None:
            self._attr_native_target_temperature = actual_temp

        if self._expected_hvac_mode is None and self._expected_temperature is None:
            self._cancel_confirmation()

        self._safe_write_ha_state()

    @property
    def assumed_state(self) -> bool:
        """Return True while awaiting confirmation from the vehicle."""
        return self._expected_hvac_mode is not None or self._expected_temperature is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose operability, mode, error codes, and per-zone readings."""
        attrs = dict(super().extra_state_attributes)
        temps, active_flags = self._read_zone_state()
        for zone_key, value in temps.items():
            attrs[f"{zone_key}_temperature"] = value
        for zone_key, is_active in active_flags.items():
            attrs[f"{zone_key}_active"] = is_active

        actual_temp = self._actual_target_temperature()
        if actual_temp == 30.0:
            attrs["temperature_preset"] = "high"
        elif actual_temp is not None and actual_temp <= 0.0:
            attrs["temperature_preset"] = "low"

        for attr_name, output_key in (
            ("precondOperabilityAvailable", "operability_available"),
            ("precondOperabilityState", "operability_state"),
            ("precondOperatingMode", "operating_mode"),
            ("precondError", "precond_error"),
            ("precondNowError", "precond_now_error"),
        ):
            if self._is_car_attribute_valid("precond", attr_name):
                val = self._get_car_value("precond", attr_name, "value", None)
                if val is not None:
                    attrs[output_key] = val
        return attrs


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the climate platform for Mercedes Me."""
    await async_setup_described_platform(
        hass, config_entry, async_add_entities, CLIMATE_DESCRIPTIONS, MercedesMeClimate, "climate"
    )
