"""Generate custom_components/mbapi2020/vsu_enums.py from the generated protos.

Run it from the repository root after regenerating the *_pb2.py files:

    python scripts/generate_vsu_enums.py

The table maps the enum value names that a vehicle_status_updates message
carries to their proto number, because the consumers compare numbers.

Rules:
- Only the enum types listed in _ENUM_TYPES are included. A new attribute enum
  has to be added there; new or renamed values of a listed enum are picked up
  automatically.
- Only upper-case names with an underscore are kept. Bare tokens such as
  ACTIVE or OPEN appear in many enums with different numbers.
- Names in _BLOCKLIST are left out because a consumer compares the string.
- A name that has different numbers in two listed enums is dropped, so the
  lookup stays unambiguous.
"""

from __future__ import annotations

import collections
import importlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "custom_components" / "mbapi2020" / "vsu_enums.py"

_PROTO_MODULES = ("vehicle_events_pb2", "vehicle_commands_pb2", "vehicleapi_pb2", "protos_pb2")

# client.py reads the weekly profile schedule type as a string.
_BLOCKLIST = frozenset({"NON_RECURRING", "NON_RECURRING_AUTO_DELETE"})

_ENUM_TYPES = (
    "proto.AmgStageModeState",
    "proto.AssystOilQuantity",
    "proto.AssystOilWarning",
    "proto.AttributeStatus",
    "proto.AuxheatConfigure.Selection",
    "proto.Auxheatstatus",
    "proto.Auxheattimeselection",
    "proto.Auxheatwarning",
    "proto.BatteryHealth",
    "proto.CalibrationRequest",
    "proto.ChargeCouplerLockStatus",
    "proto.ChargeCouplerStatus",
    "proto.ChargeFlapStatus",
    "proto.ChargeFlapsPositionState",
    "proto.ChargeInletsEntry.ChargeInletsCouplerState",
    "proto.ChargeInletsEntry.ChargeInletsLockState",
    "proto.ChargeOptConfigure.Tariff.Rate",
    "proto.ChargeProgram",
    "proto.ChargeProgramConfigure.ChargeProgram",
    "proto.ChargingCompatibilityError",
    "proto.ChargingConfigure.Action",
    "proto.ChargingConfigure.DcChargingProfile",
    "proto.ChargingConfigure.SohCalibrationActivation",
    "proto.ChargingErrorDetails",
    "proto.ChargingFlapErrorDetails",
    "proto.ChargingMode",
    "proto.ChargingPowerControl.ChargingStatusForPowerControl",
    "proto.ChargingPowerRestriction",
    "proto.ChargingScheduleActive.ChargingScheduleActiveOfflineMode",
    "proto.ChargingScheduleActive.ChargingScheduleActiveUseCaseId",
    "proto.ChargingScheduleRequested.ChargingScheduleUseCaseId",
    "proto.ChargingScheduleUseCaseId",
    "proto.ChargingStopErrorDetails",
    "proto.ChargingTimerEntry.ChargingTimerAction",
    "proto.Chargingstatus",
    "proto.ChildPresenceDetectionOccupancyStatus",
    "proto.ChildPresenceDetectionWarningLastEvent",
    "proto.ChildPresenceDetectionWarningLevel",
    "proto.DcChargingProfile",
    "proto.DepartureTimeMode",
    "proto.Door",
    "proto.DoorStatusOverall",
    "proto.Doorlockstatus",
    "proto.Doorlockstatusvehicle",
    "proto.Doorstatus",
    "proto.Doorstatusgas",
    "proto.DriveType",
    "proto.DrivingMode",
    "proto.EmergencyPowerSupply",
    "proto.EngineHoodStatus",
    "proto.EngineState",
    "proto.EvsePairingState",
    "proto.ExteriorMonitoringStatus",
    "proto.FilterParticleLoading",
    "proto.FlipWindowStatus",
    "proto.HvBatteryPrecondAvailability",
    "proto.HvBatteryPrecondStatesCharging",
    "proto.HvBatteryPrecondStatesDischarging",
    "proto.HvBatteryThermalPropagationEvent",
    "proto.HybridWarnings",
    "proto.Ignitionstate",
    "proto.InteriorMonitoringStatus",
    "proto.InteriorProtectionActivationStatus",
    "proto.InteriorProtectionSelectionStatus",
    "proto.KeyActivationState",
    "proto.KeylineActivationStates",
    "proto.LanguageHU",
    "proto.LastTheftWarningReason",
    "proto.MainCategory",
    "proto.Method",
    "proto.OilWarningLevel",
    "proto.OperatingSystemName",
    "proto.PanicAlarmActive",
    "proto.ParkCollisionActivationStatus",
    "proto.ParkCollisionInactiveReason",
    "proto.ParkCollisionPictureTransferStatus",
    "proto.ParkCollisionSelectionStatus",
    "proto.ParkEventLevel",
    "proto.ParkEventPictureSelectionStatus",
    "proto.ParkEventPictureTransmissionStatus",
    "proto.ParkEventSensorStatus",
    "proto.ParkEventType",
    "proto.Parkbrakestatus",
    "proto.PerformanceLimitationModeStatus",
    "proto.PetMode.Info.Level",
    "proto.PetMode.Info.Type",
    "proto.PetMode.Status",
    "proto.PictureRecordingStatus",
    "proto.PictureTransferSelectionStatus",
    "proto.PrecondError",
    "proto.PrecondNow",
    "proto.PrecondOperabilityState.PrecondErrorState",
    "proto.PrecondOperatingMode",
    "proto.PrecondSeat",
    "proto.PrecondStateType",
    "proto.Precondatdeparture",
    "proto.ProtectionActivationStatus",
    "proto.ProtectionSensorStatus",
    "proto.RangeSkipIndication",
    "proto.RemoteSeatBalletConfigure.PresetPosition",
    "proto.ResubscribeToAppTwinResponse.ResubscribeResult",
    "proto.Rooftopstatus",
    "proto.Scope",
    "proto.SeatballetPositionState",
    "proto.SelectedChargeProgram",
    "proto.SigPosStart.HornType",
    "proto.SigPosStart.LightType",
    "proto.SigPosStart.SigposType",
    "proto.SmartCharging",
    "proto.SmartChargingAtDeparture",
    "proto.SocCalibrationRequest",
    "proto.SohCalibrationNotifications",
    "proto.SohCalibrationPlanned",
    "proto.SohCalibrationRequest",
    "proto.SohCalibrationRequired",
    "proto.SohCalibrationState",
    "proto.SohFavorableConditions",
    "proto.SpecificCategory",
    "proto.SpeedUnitFromIC",
    "proto.StarterBatteryState",
    "proto.Status",
    "proto.SubCategory",
    "proto.SubscriptionErrorType",
    "proto.SunroofEvent",
    "proto.SunroofStatusBlind",
    "proto.Sunroofstatus",
    "proto.TcuConnectionStateLowChannel",
    "proto.TcuThermoShutDown",
    "proto.TemperatureConfigure.TemperaturePoint.Zone",
    "proto.TemperatureUnitHU",
    "proto.TimeFormatHU",
    "proto.TimeProfile.ScheduleType",
    "proto.TireMarker",
    "proto.TireSensorAvailable",
    "proto.TireWarningLevelPrw",
    "proto.Tirewarninglamp",
    "proto.Tirewarningsprw",
    "proto.Tirewarningsrdk",
    "proto.TowProtectionActivationStatus",
    "proto.TowProtectionSelectionStatus",
    "proto.TrackingStateHu",
    "proto.TurnOffEnginePreWarning",
    "proto.UpdateStatus",
    "proto.VVRTimeProfile.WeeklyProfileScheduleType",
    "proto.VehicleAttributeStatus.ChargingCouplerErrorDetails",
    "proto.VehicleAttributeStatus.ChargingErrorImpossibleChangeTo400V",
    "proto.VehicleAttributeStatus.ChargingErrorImpossibleChangeTo800V",
    "proto.VehicleAttributeStatus.ChargingErrorVehicleNoSupport400V",
    "proto.VehicleAttributeStatus.ClockHourUnit",
    "proto.VehicleAttributeStatus.CombustionConsumptionUnit",
    "proto.VehicleAttributeStatus.DistanceUnit",
    "proto.VehicleAttributeStatus.ElectricityConsumptionUnit",
    "proto.VehicleAttributeStatus.GasConsumptionUnit",
    "proto.VehicleAttributeStatus.PressureUnit",
    "proto.VehicleAttributeStatus.RatioUnit",
    "proto.VehicleAttributeStatus.SpeedDistanceUnit",
    "proto.VehicleAttributeStatus.SpeedUnit",
    "proto.VehicleAttributeStatus.TcuConnectionStateLowChannelStatus",
    "proto.VehicleAttributeStatus.TemperatureUnit",
    "proto.VehicleDataConnectionState",
    "proto.VehicleHealthStatus",
    "proto.VehiclePositionErrorCode",
    "proto.VehicleTheftAlarmInactiveReason",
    "proto.Warningwashwater",
    "proto.Weekday",
    "proto.WeeklyProfile.TimeProfile.ScheduleType",
    "proto.WindowStatusBlind",
    "proto.WindowStatusOverall",
    "proto.Windowstatus",
    "proto.ZEVPreconditioningConfigure.DepartureTimeMode",
    "proto.ZEVPreconditioningType",
)

_HEADER = '''"""Mapping from VSU enum value names to their proto number.

Generated by scripts/generate_vsu_enums.py - do not edit by hand. Rerun the
script after regenerating the protos; the rules are described there.
"""

from __future__ import annotations

VSU_ENUM_VALUE_TO_INT: dict[str, int] = {
'''


def _all_enums() -> dict[str, object]:
    """Return every enum descriptor of the proto modules by full name."""
    enums: dict[str, object] = {}

    def walk(descriptor) -> None:
        for enum in descriptor.enum_types:
            enums[enum.full_name] = enum
        for nested in descriptor.nested_types:
            walk(nested)

    for name in _PROTO_MODULES:
        module = importlib.import_module("custom_components.mbapi2020.proto." + name)
        for enum in module.DESCRIPTOR.enum_types_by_name.values():
            enums[enum.full_name] = enum
        for message in module.DESCRIPTOR.message_types_by_name.values():
            walk(message)
    return enums


def build_table() -> dict[str, int]:
    """Build the name to number table from the listed enum types."""
    enums = _all_enums()
    unknown = [name for name in _ENUM_TYPES if name not in enums]
    if unknown:
        raise SystemExit(f"Enum types not found in the protos (renamed or removed?): {unknown}")

    numbers: dict[str, set[int]] = collections.defaultdict(set)
    for name in _ENUM_TYPES:
        for value in enums[name].values:
            if "_" in value.name and value.name.isupper() and value.name not in _BLOCKLIST:
                numbers[value.name].add(value.number)

    return {name: next(iter(found)) for name, found in sorted(numbers.items()) if len(found) == 1}


def render(table: dict[str, int]) -> str:
    """Render the vsu_enums.py source."""
    lines = [f'    "{name}": {number},\n' for name, number in table.items()]
    return _HEADER + "".join(lines) + "}\n"


def main() -> None:
    """Write vsu_enums.py."""
    sys.path.insert(0, str(ROOT))
    TARGET.write_text(render(build_table()), encoding="utf-8")


if __name__ == "__main__":
    main()
