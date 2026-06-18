"""Normalize vehicle_status_updates messages into the internal vepUpdate format."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

from .vsu_enums import VSU_ENUM_VALUE_TO_INT

LOGGER = logging.getLogger(__name__)

# Map VSU unit enum values to the legacy VEPUpdate unit field name expected by
# the generic value handler in client.py. Keeping it here avoids having to
# touch every consumer of CarAttribute.unit.
_VSU_UNIT_TO_LEGACY_KEY: dict[str, str] = {
    # DistanceUnit
    "KILOMETERS": "distance_unit",
    "MILES": "distance_unit",
    # PressureUnit
    "KPA": "pressure_unit",
    "BAR": "pressure_unit",
    "PSI": "pressure_unit",
    # SpeedUnit
    "KM_PER_HOUR": "speed_unit",
    "M_PER_HOUR": "speed_unit",
    # RatioUnit
    "PERCENT": "ratio_unit",
    # ElectricityConsumptionUnit
    "KWH_PER_100KM": "electricity_consumption_unit",
    "KWH_PER_100MI": "electricity_consumption_unit",
    "M_PER_KWH": "electricity_consumption_unit",
    "KM_PER_KWH": "electricity_consumption_unit",
    "MPGE": "electricity_consumption_unit",
    # CombustionConsumptionUnit
    "LITER_PER_100KM": "combustion_consumption_unit",
    "MPG_US": "combustion_consumption_unit",
    "MPG_UK": "combustion_consumption_unit",
    "KM_PER_LITER": "combustion_consumption_unit",
    # GasConsumptionUnit
    "KG_PER_100KM": "gas_consumption_unit",
    "KM_PER_KG": "gas_consumption_unit",
    "M_PER_KG": "gas_consumption_unit",
    # TemperatureUnit
    "CELSIUS": "temperature_unit",
    "FAHRENHEIT": "temperature_unit",
    # ClockHourUnit
    "T12H": "clock_hour_unit",
    "T24H": "clock_hour_unit",
}

# A handful of attribute keys whose snake_case form does not match the legacy
# camelCase key that car.py / specialized handlers in client.py expect.
# Only put entries here that the algorithmic conversion would get wrong.
_VSU_KEY_OVERRIDES: dict[str, str] = {
    "tire_press_meas_timestamp": "lastTirepressureTimestamp",
}

# Translate the VSU AttributeStatus enum to the legacy values that
# sensor.py / binary_sensor.py / lock.py / client.py already check for.
# The proto numeric values match the legacy ones, so we re-use them:
#   NOT_RECEIVED string -> sensor is created and shows STATE_UNKNOWN
#   3 (INVALID) -> sensor.state returns STATE_UNKNOWN; eligible in push mode
#   4 (NOT_AVAILABLE) -> sensor is not created
_VSU_STATUS_TO_LEGACY: dict[str, str | int] = {
    "VALUE_NOT_RECEIVED": "NOT_RECEIVED",
    "VALUE_INVALID": 3,
    "VALUE_NOT_AVAILABLE": 4,
}


def _snake_to_camel(name: str) -> str:
    """Convert snake_case to camelCase.

    Strings without underscores round-trip unchanged, so legacy lower-case
    concatenated keys like ``windowstatusfrontleft`` stay as-is.
    """
    parts = name.split("_")
    if len(parts) == 1:
        return parts[0]
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:] if p)


def _vsu_key_to_legacy(key: str) -> str:
    """Return the legacy attribute key for a VSU snake_case key."""
    return _VSU_KEY_OVERRIDES.get(key, _snake_to_camel(key))


def _iso_to_epoch_seconds(iso: str | None) -> int | None:
    """Parse the ISO-8601 timestamps used in VSU metadata to epoch seconds."""
    if not iso:
        return None
    try:
        # ``datetime.fromisoformat`` accepts the ``Z`` suffix only from 3.11+;
        # the integration requires 3.13 so we can rely on it.
        normalized = iso.replace("Z", "+00:00") if iso.endswith("Z") else iso
        return int(datetime.fromisoformat(normalized).astimezone(timezone.utc).timestamp())
    except ValueError:
        LOGGER.debug("Could not parse VSU timestamp %s", iso)
        return None


def _normalize_value(legacy_key: str, value: Any, legacy: dict[str, Any]) -> None:
    """Translate the VSU ``value`` payload into the legacy dict in place.

    For most attributes the generic handler in client.py picks ``value``
    first, so we can just pass it through. Complex sub-structures
    (charge flaps, charge inlets, charging power restriction) need to be
    re-nested into the shape the specialized handlers expect.
    """
    if value is None:
        return

    if legacy_key == "chargeFlaps" and isinstance(value, list):
        legacy["charge_flaps"] = {"entries": value}
        return
    if legacy_key == "chargeInlets" and isinstance(value, list):
        legacy["charge_inlets"] = {"entries": value}
        return
    if legacy_key == "chargingPowerRestriction" and isinstance(value, list):
        legacy["charging_power_restrictions"] = {"charging_power_restriction": value}
        return

    # Re-nest sub-message payloads so the specialised handlers in client.py
    # (which still read the VEP/REST shape) can pick them up unchanged.
    if legacy_key == "chargePrograms" and isinstance(value, list):
        legacy["charge_programs_value"] = {"charge_program_parameters": value}
        return
    if legacy_key == "temperaturePoints" and isinstance(value, list):
        legacy["temperature_points_value"] = {"temperature_points": value}
        return
    if legacy_key == "chargingBreakClockTimer" and isinstance(value, dict):
        legacy["chargingbreak_clocktimer_value"] = value
        return
    # All four ChargingPredictionSocObjectAttribute siblings share the same
    # inner shape; the endofchargetime handler reads ``charging_prediction_soc``.
    if legacy_key in (
        "chargingPredictionFullSoc",
        "chargingPredictionMaxSoc",
        "chargingPredictionMinSoc",
        "chargingPredictionTargetSoc",
    ) and isinstance(value, dict):
        legacy["charging_prediction_soc"] = value
        return

    # Top-level enum strings (e.g. DOORLOCKSTATUSVEHICLE_EXTERNAL_LOCKED) need
    # to round-trip to their proto integer so downstream consumers that do
    # ``int(value)`` (lock.py) or compare against 0/1/2 (binary_sensor.py)
    # keep working. Nested strings inside lists (charge_flaps entries etc.)
    # are passed through untouched because we only inspect the scalar value.
    if isinstance(value, str):
        mapped = VSU_ENUM_VALUE_TO_INT.get(value)
        if mapped is not None:
            value = mapped

    legacy["value"] = value

    # A handful of specialised handlers in client.py (endofchargetime,
    # precondStatus, …) still read the typed legacy keys instead of the
    # generic ``value``. Populate them in addition so those handlers keep
    # working without touching their internals.
    if isinstance(value, bool):
        legacy["bool_value"] = value
    elif isinstance(value, int):
        legacy["int_value"] = str(value)
    elif isinstance(value, float):
        legacy["double_value"] = value
    elif isinstance(value, str):
        stripped = value.strip()
        if stripped.lstrip("-").isdigit():
            legacy["int_value"] = stripped
        else:
            try:
                legacy["double_value"] = float(stripped)
            except ValueError:
                pass


def _normalize_attribute(key: str, vsu_attr: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """Convert one VSU attribute entry into a legacy attribute dict."""
    if not isinstance(vsu_attr, dict):
        return None

    legacy_key = _vsu_key_to_legacy(key)
    legacy: dict[str, Any] = {}

    metadata = vsu_attr.get("metadata") or {}
    epoch_seconds = _iso_to_epoch_seconds(metadata.get("timestamp"))
    if epoch_seconds is not None:
        legacy["timestamp"] = str(epoch_seconds)
        legacy["timestamp_in_ms"] = str(epoch_seconds * 1000)

    status = metadata.get("status")
    if status:
        legacy["status"] = _VSU_STATUS_TO_LEGACY.get(status, status)

    unit = vsu_attr.get("unit")
    if unit:
        # Unknown enums fall through to the proto-native ``unit`` field — the
        # generic value handler probes the legacy keys (distance_unit etc.)
        # but mislabelling a clock unit as a distance is more confusing than
        # not surfacing it at all.
        legacy_unit_key = _VSU_UNIT_TO_LEGACY_KEY.get(unit, "unit")
        legacy[legacy_unit_key] = unit

    display_value = vsu_attr.get("display_value")
    if display_value is not None:
        legacy["display_value"] = display_value

    _normalize_value(legacy_key, vsu_attr.get("value"), legacy)

    return legacy_key, legacy


def normalize_vsu_car(vsu_car: dict[str, Any]) -> dict[str, Any]:
    """Convert one car payload from a vehicle_status_updates message.

    Returned shape matches what ``Client._build_car`` consumes for VEP updates:
    ``{"vin": ..., "full_update": ..., "attributes": {...}}``.
    """
    vin = vsu_car.get("fin_or_vin")
    legacy_car: dict[str, Any] = {
        "vin": vin,
        "full_update": bool(vsu_car.get("full_update", False)),
        "attributes": {},
    }

    reserved = {"fin_or_vin", "full_update"}
    attributes: dict[str, Any] = legacy_car["attributes"]
    for key, raw in vsu_car.items():
        if key in reserved:
            continue
        normalized = _normalize_attribute(key, raw)
        if normalized is None:
            continue
        legacy_key, legacy_attr = normalized
        attributes[legacy_key] = legacy_attr

    return legacy_car
