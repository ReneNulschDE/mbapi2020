"""Offline regression tests for X244 / MB.OS diagnostic and telemetry attribute support."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

from google.protobuf.wrappers_pb2 import BoolValue, Int32Value

from custom_components.mbapi2020.binary_sensor import _create_binary_sensor_if_eligible
from custom_components.mbapi2020.car import (
    BINARY_SENSOR_OPTIONS,
    DOOR_OPTIONS,
    ELECTRIC_OPTIONS,
    LOCATION_OPTIONS,
    ODOMETER_OPTIONS,
    PRE_COND_OPTIONS,
    TIRE_OPTIONS,
    CarAttribute,
    Electric,
)
from custom_components.mbapi2020.const import SENSORS, BinarySensors, SensorConfigFields as scf
from custom_components.mbapi2020.proto import vehicle_events_pb2
from custom_components.mbapi2020.sensor import _create_sensor_if_eligible
from homeassistant.const import STATE_UNKNOWN

from .conftest import make_client
from .fixtures.build import SYNTH_VIN, build_vep_updates, roundtrip

COMPONENT_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "mbapi2020"

_TELEMETRY_SENSOR_KEYS = (
    "rangeelectricwltp",
    "overallrange",
    "gainedrangesincestartofcharging",
    "maxsocupperlimit",
    "evrangeassistdriveonsoc",
    "evrangeassistdriveontime",
    "sohcalibrationstate",
    "chargingerrordetails",
    "chargingcompatibilityerror",
    "chargingscheduleactive",
    "chargingpredictiondeparturerange",
    "chargingpredictiondeparturesoc",
    "lasttirepressuretimestamp",
    "tiresensoravailable",
    "tirewarninglevelprw",
    "oilwarninglevel",
    "filterparticleloading",
    "turnoffengineprewarning",
    "hvbatterythermalpropagationevent",
    "hybridwarnings",
    "tcuconnectionstatelowchannel",
    "sunroofevent",
    "temperatureunithu",
    "vehiclepositionerrorcode",
)

_TELEMETRY_BINARY_SENSOR_KEYS = (
    "sohcalibrationrequired",
    "precondavailable",
    "tcuthermoshutdown",
    "trackingstatehu",
)


def _make_vsu_push(sequence_number: int, *, full_update: bool = True):
    """Build a PushMessage containing one VehicleStatusUpdate for SYNTH_VIN."""
    push = vehicle_events_pb2.PushMessage()
    push.vehicle_status_updates.sequence_number = sequence_number
    vsu = push.vehicle_status_updates.vehicle_status_updates[SYNTH_VIN]
    vsu.fin_or_vin = SYNTH_VIN
    vsu.full_update = full_update
    return push, vsu


def _coord(client):
    """Return a minimal coordinator namespace for entity instantiation."""
    return SimpleNamespace(
        hass=None,
        client=client,
        config_entry=client.config_entry,
        last_update_success=True,
    )


def _stub_entity_update(entity):
    """Run synchronous entity update without a live Home Assistant instance."""
    entity.async_write_ha_state = lambda: None
    entity.update()
    return entity


def _group_options_by_name() -> dict[str, set[str]]:
    return {
        "odometer": set(ODOMETER_OPTIONS),
        "location": set(LOCATION_OPTIONS),
        "tires": set(TIRE_OPTIONS),
        "doors": set(DOOR_OPTIONS),
        "electric": set(ELECTRIC_OPTIONS),
        "binarysensors": set(BINARY_SENSOR_OPTIONS),
        "precond": set(PRE_COND_OPTIONS),
    }


def test_x244_entity_configs_match_car_options_and_translations() -> None:
    """Every X244 sensor/binary sensor aligns with Car options, None default mode, and en.json."""
    group_options = _group_options_by_name()
    en_json = json.loads((COMPONENT_DIR / "translations" / "en.json").read_text(encoding="utf-8"))
    sensor_translations = en_json["entity"]["sensor"]
    binary_translations = en_json["entity"]["binary_sensor"]

    for key in _TELEMETRY_SENSOR_KEYS:
        cfg = SENSORS[key]
        group_name = cfg[scf.OBJECT_NAME.value]
        attr_name = cfg[scf.ATTRIBUTE_NAME.value]
        assert attr_name in group_options[group_name], f"{key}: {attr_name} missing from {group_name}"
        assert cfg[scf.DEFAULT_VALUE_MODE.value] is None, f"{key} must keep DEFAULT_VALUE_MODE=None"
        for ext in cfg[scf.EXTENDED_ATTRIBUTE_LIST.value] or ():
            assert ext in group_options[group_name], f"{key}: extended {ext} missing from {group_name}"

    for key in _TELEMETRY_BINARY_SENSOR_KEYS:
        cfg = BinarySensors[key]
        group_name = cfg[scf.OBJECT_NAME.value]
        attr_name = cfg[scf.ATTRIBUTE_NAME.value]
        assert attr_name in group_options[group_name], f"{key}: {attr_name} missing from {group_name}"
        assert key in binary_translations, f"{key} missing from binary_sensor translations"

    for enum_sensor_key in (
        "sohcalibrationstate",
        "chargingerrordetails",
        "chargingcompatibilityerror",
        "tiresensoravailable",
        "tirewarninglevelprw",
        "oilwarninglevel",
        "filterparticleloading",
        "turnoffengineprewarning",
        "hvbatterythermalpropagationevent",
        "hybridwarnings",
        "tcuconnectionstatelowchannel",
        "sunroofevent",
        "temperatureunithu",
        "vehiclepositionerrorcode",
    ):
        assert "state" in sensor_translations[enum_sensor_key]


def test_energy_range_and_limits_vsu_and_vep() -> None:
    """Range WLTP, overall range, gained range, maxSoC upper limit and EV range assist parse across VSU and VEP."""
    vsu_client = make_client()
    push, vsu = _make_vsu_push(1)
    for field in (
        "range_electric_wltp",
        "overall_range",
        "gained_range_since_start_of_charging",
        "max_soc_upper_limit",
        "ev_range_assist_drive_on_s_o_c",
        "ev_range_assist_drive_on_time",
    ):
        getattr(vsu, field).metadata.timestamp.seconds = 1780591500
    vsu.range_electric_wltp.value = 510
    vsu.range_electric_wltp.unit = 1
    vsu.overall_range.value = 524.5
    vsu.overall_range.unit = 1
    vsu.gained_range_since_start_of_charging.value = 142
    vsu.gained_range_since_start_of_charging.unit = 1
    vsu.max_soc_upper_limit.value = 100
    vsu.max_soc_upper_limit.unit = 1
    vsu.ev_range_assist_drive_on_s_o_c.value = 22
    vsu.ev_range_assist_drive_on_s_o_c.unit = 1
    vsu.ev_range_assist_drive_on_time.value = 15

    vsu_client._process_vehicle_status_updates(roundtrip(push))
    elec = vsu_client.cars[SYNTH_VIN].electric
    assert elec.rangeElectricWltp.value == "510"
    assert elec.rangeElectricWltp.unit == "KILOMETERS"
    assert elec.overallRange.value == 524.5
    assert elec.gainedRangeSinceStartOfCharging.value == "142"
    assert elec.maxSocUpperLimit.value == "100"
    assert elec.maxSocUpperLimit.unit == "PERCENT"
    assert elec.evRangeAssistDriveOnSOC.value == "22"
    assert elec.evRangeAssistDriveOnTime.value == "15"

    # VEP/REST payload including nil_value status=3 and status=4 behavior
    vep_client = make_client()
    vep_push = build_vep_updates()
    attrs = vep_push.vepUpdates.updates[SYNTH_VIN].attributes
    attrs["overallRange"].double_value = 511.0
    attrs["overallRange"].distance_unit = 1
    attrs["gainedRangeSinceStartOfCharging"].int_value = 35
    attrs["gainedRangeSinceStartOfCharging"].distance_unit = 1
    attrs["maxSocUpperLimit"].int_value = 100
    attrs["maxSocUpperLimit"].ratio_unit = 1
    attrs["evRangeAssistDriveOnSOC"].nil_value = True
    attrs["evRangeAssistDriveOnSOC"].status = 3
    attrs["rangeElectricWltp"].nil_value = True
    attrs["rangeElectricWltp"].status = 4
    vep_client._process_vep_updates(roundtrip(vep_push))

    vep_car = vep_client.cars[SYNTH_VIN]
    assert vep_car.electric.overallRange.value == 511.0
    assert vep_car.electric.gainedRangeSinceStartOfCharging.value == "35"
    assert vep_car.electric.maxSocUpperLimit.value == "100"

    coord = _coord(vep_client)
    ev_soc_entity = _create_sensor_if_eligible(
        "evrangeassistdriveonsoc", SENSORS["evrangeassistdriveonsoc"], vep_car, coord
    )
    assert ev_soc_entity is not None
    assert ev_soc_entity.state == STATE_UNKNOWN
    assert _create_sensor_if_eligible("rangeelectricwltp", SENSORS["rangeelectricwltp"], vep_car, coord) is None


def test_soh_calibration_and_soc_request_vsu_and_vep() -> None:
    """SoH calibration enums and SoC calibration request normalize identically via VSU and VEP."""
    vsu_client = make_client()
    push, vsu = _make_vsu_push(2)
    for field in (
        "soh_calibration_required",
        "soh_calibration_state",
        "soh_calibration_request",
        "soh_calibration_planned",
        "soh_calibration_notifications",
        "soh_favorable_conditions",
        "soh_charge_time_extension",
        "soc_calibration_request",
    ):
        getattr(vsu, field).metadata.timestamp.seconds = 1780591500
    vsu.soh_calibration_required.value = 1
    vsu.soh_calibration_state.value = 1
    vsu.soh_calibration_request.value = 2
    vsu.soh_calibration_planned.value = 1
    vsu.soh_calibration_notifications.value = 3
    vsu.soh_favorable_conditions.value = 2
    vsu.soh_charge_time_extension.value = 45
    vsu.soc_calibration_request.value = 1

    vsu_client._process_vehicle_status_updates(roundtrip(push))
    elec = vsu_client.cars[SYNTH_VIN].electric
    assert elec.sohCalibrationRequired.value == 1
    assert elec.sohCalibrationState.value == 1
    assert elec.sohCalibrationRequest.value == 2
    assert elec.sohCalibrationPlanned.value == 1
    assert elec.sohCalibrationNotifications.value == 3
    assert elec.sohFavorableConditions.value == 2
    assert elec.sohChargeTimeExtension.value == "45"
    assert elec.socCalibrationRequest.value == 1

    req_bin = _create_binary_sensor_if_eligible(
        "sohcalibrationrequired",
        BinarySensors["sohcalibrationrequired"],
        vsu_client.cars[SYNTH_VIN],
        _coord(vsu_client),
    )
    assert req_bin is not None
    assert _stub_entity_update(req_bin).is_on is True

    # VEP/REST typed enum fields and proto3 omitted VSU default (0)
    vep_client = make_client()
    vep_push = build_vep_updates()
    attrs = vep_push.vepUpdates.updates[SYNTH_VIN].attributes
    attrs["sohCalibrationRequired"].soh_calibration_required = 0
    attrs["sohCalibrationState"].soh_calibration_state = 0
    attrs["sohCalibrationRequest"].soh_calibration_request = 0
    attrs["sohCalibrationPlanned"].soh_calibration_planned = 0
    attrs["sohCalibrationNotifications"].soh_calibration_notifications = 0
    attrs["sohFavorableConditions"].soh_favorable_conditions = 1
    attrs["sohChargeTimeExtension"].int_value = 0
    attrs["socCalibrationRequest"].soc_calibration_request = 2
    vep_client._process_vep_updates(roundtrip(vep_push))

    vep_elec = vep_client.cars[SYNTH_VIN].electric
    assert vep_elec.sohCalibrationRequired.value == 0
    assert vep_elec.sohCalibrationState.value == 0
    assert vep_elec.sohFavorableConditions.value == 1
    assert vep_elec.socCalibrationRequest.value == 2
    vep_bin = _create_binary_sensor_if_eligible(
        "sohcalibrationrequired",
        BinarySensors["sohcalibrationrequired"],
        vep_client.cars[SYNTH_VIN],
        _coord(vep_client),
    )
    assert vep_bin is not None
    assert _stub_entity_update(vep_bin).is_on is False


def test_charging_errors_schedules_and_predictions() -> None:
    """Charging errors, schedules, and departure predictions parse accurately without phantom sensors."""
    vsu_client = make_client()
    push, vsu = _make_vsu_push(3)
    for field in (
        "charging_error_details",
        "charging_stop_error_details",
        "charging_coupler_error_details",
        "charging_flap_error_details",
        "charging_compatibility_error",
        "charging_error_impossible_change_to400_v",
        "charging_error_impossible_change_to800_v",
        "charging_error_vehicle_no_support400_v",
        "charging_schedule_active",
        "charging_schedule_requested",
        "charging_prediction_departure_time",
    ):
        getattr(vsu, field).metadata.timestamp.seconds = 1780591500
    vsu.charging_error_details.value = 14
    vsu.charging_stop_error_details.value = 1
    vsu.charging_coupler_error_details.value = 3
    vsu.charging_flap_error_details.value = 2
    vsu.charging_compatibility_error.value = 6
    vsu.charging_error_impossible_change_to400_v.value = 1
    vsu.charging_error_impossible_change_to800_v.value = 1
    vsu.charging_error_vehicle_no_support400_v.value = 1
    vsu.charging_schedule_active.value.start_time.seconds = 1780600000
    vsu.charging_schedule_active.value.offline_mode = 1
    vsu.charging_schedule_active.value.use_case_id = 17
    slot = vsu.charging_schedule_active.value.schedule.add()
    slot.power_values = 11.0
    slot.duration_values = 1800
    vsu.charging_schedule_requested.value.schedule_id_status = 0
    vsu.charging_schedule_requested.value.use_case_id = 10
    vsu.charging_prediction_departure_time.value.predicted_electrical_energy_range = 365
    vsu.charging_prediction_departure_time.value.predicted_soc.CopyFrom(Int32Value(value=85))

    vsu_client._process_vehicle_status_updates(roundtrip(push))
    elec = vsu_client.cars[SYNTH_VIN].electric
    assert elec.chargingErrorDetails.value == 14
    assert elec.chargingStopErrorDetails.value == 1
    assert elec.chargingCouplerErrorDetails.value == 3
    assert elec.chargingFlapErrorDetails.value == 2
    assert elec.chargingCompatibilityError.value == 6
    assert elec.chargingErrorImpossibleChangeTo400V.value == 1
    assert elec.chargingErrorImpossibleChangeTo800V.value == 1
    assert elec.chargingErrorVehicleNoSupport400V.value == 1
    assert elec.chargingScheduleActive.value == "home_charging_plan"
    assert elec.chargingScheduleActiveDetails.value["offline_mode"] == "off"
    assert len(elec.chargingScheduleActiveDetails.value["schedule"]) == 1
    assert elec.chargingScheduleRequested.value == {
        "schedule_id_status": "initial",
        "use_case_id": "solar_charging",
    }
    assert elec.chargingPredictionDepartureTimeRange.value == 365
    assert elec.chargingPredictionDepartureTimeSoc.value == 85

    # Clearing prediction on a partial VSU update resets both to unknown instead of leaving stale values;
    # chargingScheduleRequested with omitted proto3 zero values maps to initial / smart_charging.
    clear_push, clear_vsu = _make_vsu_push(4, full_update=False)
    clear_vsu.charging_prediction_departure_time.metadata.timestamp.seconds = 1780591600
    clear_vsu.charging_schedule_requested.metadata.timestamp.seconds = 1780591600
    clear_vsu.charging_schedule_requested.value.schedule_id_status = 0
    clear_vsu.charging_schedule_requested.value.use_case_id = 0
    vsu_client._process_vehicle_status_updates(roundtrip(clear_push))
    assert vsu_client.cars[SYNTH_VIN].electric.chargingPredictionDepartureTimeRange.retrievalstatus == 3
    assert vsu_client.cars[SYNTH_VIN].electric.chargingPredictionDepartureTimeSoc.retrievalstatus == 3
    assert vsu_client.cars[SYNTH_VIN].electric.chargingScheduleRequested.value == {
        "schedule_id_status": "initial",
        "use_case_id": "smart_charging",
    }

    # Idle X244 VEP payload: typed enums normalize cleanly, empty schedule is "inactive", empty prediction creates no sensor
    vep_client = make_client()
    vep_push = build_vep_updates()
    attrs = vep_push.vepUpdates.updates[SYNTH_VIN].attributes
    attrs["chargingCompatibilityError"].charging_compatibility_error = 1
    attrs["chargingCouplerErrorDetails"].charging_coupler_error_details = 0
    attrs["chargingFlapErrorDetails"].charging_flap_error_details = 0
    attrs["chargingStopErrorDetails"].charging_stop_error_details = 0
    attrs["chargingErrorDetails"].int_value = 14
    attrs["chargingErrorImpossibleChangeTo800V"].charging_error_impossible_change_to_800v = 0
    attrs["chargingErrorVehicleNoSupport400V"].charging_error_vehicle_no_support_400v = 0
    attrs["chargingScheduleActive"].charging_schedule_active.offline_mode = 1
    attrs["chargingScheduleActive"].charging_schedule_active.schedule.add()
    attrs["chargingScheduleRequested"].charging_schedule_requested.SetInParent()
    attrs["chargingPredictionDepartureTime"].charging_prediction_departure_time.SetInParent()
    vep_client._process_vep_updates(roundtrip(vep_push))

    vep_elec = vep_client.cars[SYNTH_VIN].electric
    assert vep_elec.chargingCompatibilityError.value == 1
    assert vep_elec.chargingErrorDetails.value == "14"
    assert vep_elec.chargingScheduleActive.value == "inactive"
    assert vep_elec.chargingScheduleActiveDetails.value["schedule"] == []
    assert vep_elec.chargingScheduleRequested.value == {
        "schedule_id_status": "initial",
        "use_case_id": "smart_charging",
    }
    assert not hasattr(vep_elec, "chargingPredictionDepartureTimeRange")
    assert not hasattr(vep_elec, "chargingPredictionDepartureTimeSoc")


def test_tires_maintenance_precond_tcu_and_telemetry() -> None:
    """Tires, maintenance, precond operability, departure, weekly profile, and TCU telemetry work across VSU and VEP."""
    # --- VSU path ---
    vsu_client = make_client()
    push, vsu = _make_vsu_push(5)
    for field in (
        "tire_press_meas_timestamp",
        "tire_sensor_available",
        "tire_warning_level_prw",
        "oil_warning_level",
        "filter_particle_loading",
        "turn_off_engine_pre_warning",
        "turn_off_engine_pre_warning_time",
        "hv_battery_thermal_propagation_event",
        "hybrid_warnings",
        "tcu_connection_state_low_channel",
        "tcu_thermo_shut_down",
        "sunroof_event",
        "sunroof_event_active",
        "tracking_state_h_u",
        "temperature_unit_h_u",
        "proximity_calculation_for_vehicle_position_required",
        "vehicle_position_error_code",
        "precond_operability_state",
    ):
        getattr(vsu, field).metadata.timestamp.seconds = 1780591500

    vsu.tire_press_meas_timestamp.value = 1780591479
    vsu.tire_sensor_available.value = 1
    vsu.tire_warning_level_prw.value = 2
    vsu.oil_warning_level.value = 1
    vsu.filter_particle_loading.value = 2
    vsu.turn_off_engine_pre_warning.value = 2
    vsu.turn_off_engine_pre_warning_time.value = 120
    vsu.hv_battery_thermal_propagation_event.value = 1
    vsu.hybrid_warnings.value = 8
    vsu.tcu_connection_state_low_channel.value = 3
    vsu.tcu_thermo_shut_down.value = 0  # NOT_ACTIVE (omitted on wire, synthesized to 0) -> False
    vsu.sunroof_event.value = 3
    vsu.sunroof_event_active.value = False  # omitted on wire, defaulted by vsu_helper
    vsu.tracking_state_h_u.value = 1
    vsu.temperature_unit_h_u.value = 1
    vsu.proximity_calculation_for_vehicle_position_required.value = False
    vsu.vehicle_position_error_code.value = 5
    vsu.precond_operability_state.value.precond_available = False
    vsu.precond_operability_state.value.precond_error_state = 3

    vsu_client._process_vehicle_status_updates(roundtrip(push))
    car = vsu_client.cars[SYNTH_VIN]
    assert car.tires.lastTirepressureTimestamp.value == datetime.fromtimestamp(1780591479, tz=timezone.utc)
    assert car.tires.lastTirepressureTimestamp.display_value == "2026-06-04T16:44:39+00:00"
    assert car.tires.tireSensorAvailable.value == 1
    assert car.tires.tireWarningLevelPrw.value == 2
    assert car.odometer.oilWarningLevel.value == 1
    assert car.odometer.filterParticleLoading.value == 2
    assert car.odometer.turnOffEnginePreWarning.value == 2
    assert car.odometer.turnOffEnginePreWarningTime.value == "120"
    assert car.electric.hvBatteryThermalPropagationEvent.value == 1
    assert car.electric.hybridWarnings.value == 8
    assert car.binarysensors.tcuConnectionStateLowChannel.value == 3
    assert car.binarysensors.tcuThermoShutDown.value is False
    assert car.doors.sunroofEvent.value == 3
    assert car.doors.sunroofEventActive.value is False
    assert car.location.trackingStateHU.value == 1
    assert car.precond.temperatureUnitHU.value == 1
    assert car.location.proximityCalculationForVehiclePositionRequired.value is False
    assert car.location.vehiclePositionErrorCode.value == 5
    assert car.precond.precondOperabilityAvailable.value is False
    assert car.precond.precondOperabilityState.value == 3

    # VSU TCU thermo shutdown ACTIVE (1) -> True, VALUE_INVALID (status=3) -> is_on=None
    push_act, vsu_act = _make_vsu_push(6, full_update=False)
    vsu_act.tcu_thermo_shut_down.metadata.timestamp.seconds = 1780591600
    vsu_act.tcu_thermo_shut_down.value = 1
    vsu_client._process_vehicle_status_updates(roundtrip(push_act))
    assert vsu_client.cars[SYNTH_VIN].binarysensors.tcuThermoShutDown.value is True

    push_unk, vsu_unk = _make_vsu_push(7, full_update=False)
    vsu_unk.tcu_thermo_shut_down.metadata.timestamp.seconds = 1780591700
    vsu_unk.tcu_thermo_shut_down.metadata.status = 3  # VALUE_INVALID
    vsu_client._process_vehicle_status_updates(roundtrip(push_unk))
    tcu_bin = _create_binary_sensor_if_eligible(
        "tcuthermoshutdown", BinarySensors["tcuthermoshutdown"], vsu_client.cars[SYNTH_VIN], _coord(vsu_client)
    )
    assert tcu_bin is not None
    assert _stub_entity_update(tcu_bin).is_on is None

    # --- VEP / REST path ---
    vep_client = make_client()
    vep_push = build_vep_updates()
    attrs = vep_push.vepUpdates.updates[SYNTH_VIN].attributes
    attrs["tirePressMeasTimestamp"].int_value = 1780591479
    attrs["tiremarker"].int_value = 0
    attrs["tireSensorAvailable"].int_value = 0
    attrs["tireWarningLevelPrw"].nil_value = True
    attrs["tireWarningLevelPrw"].status = 4
    attrs["oilWarningLevel"].nil_value = True
    attrs["oilWarningLevel"].status = 4
    attrs["tcuConnectionStateLowChannel"].tcu_connection_state_low_channel = 3  # DISCONNECTED
    attrs["tcuThermoShutDown"].bool_value = False
    attrs["turnOffEnginePreWarning"].turn_off_engine_pre_warning = 0
    attrs["temperatureUnitHU"].bool_value = False
    attrs["trackingStateHU"].bool_value = True
    attrs["sunroofEventActive"].bool_value = True
    attrs["vehiclePositionErrorCode"].int_value = 5
    attrs["precondOperabilityState"].precond_operability_state.precond_available = True
    attrs["nextDepartureTime"].next_departure_time_value.hour = 7
    attrs["nextDepartureTime"].next_departure_time_value.minute = 30
    attrs["nextDepartureTimeWeekday"].int_value = 2
    wp = attrs["weeklyProfile"].weekly_profile_value
    wp.single_time_profile_entries_activatable = True
    wp.max_number_of_weekly_time_profile_slots = 112
    wp.max_number_of_time_profiles = 16
    tp = wp.time_profiles.add()
    tp.identifier = 1
    tp.hour.CopyFrom(Int32Value(value=6))
    tp.minute.CopyFrom(Int32Value(value=45))
    tp.active.CopyFrom(BoolValue(value=True))
    tp.days.append(0)  # TimeProfileDay.Mo / MONDAY
    vep_client._process_vep_updates(roundtrip(vep_push))

    vep_car = vep_client.cars[SYNTH_VIN]
    assert vep_car.tires.lastTirepressureTimestamp.display_value == "2026-06-04T16:44:39+00:00"
    assert vep_car.tires.tiremarker.value == "0"
    assert vep_car.binarysensors.tcuConnectionStateLowChannel.value == 3
    assert vep_car.binarysensors.tcuThermoShutDown.value is False
    assert vep_car.precond.temperatureUnitHU.value == 0
    assert vep_car.location.trackingStateHU.value is True
    assert vep_car.doors.sunroofEventActive.value is True
    assert vep_car.location.vehiclePositionErrorCode.value == "5"
    assert vep_car.precond.precondOperabilityAvailable.value is True
    assert vep_car.electric.nextDepartureTime.value.hour == 7
    assert vep_car.electric.nextDepartureTime.value.minute == 30
    assert vep_car.electric.weeklyProfileLimits.value["max_time_profiles"] == 16
    assert vep_car.electric.weeklyProfileActive.display_value == "Mo 06:45"

    # EV status=4 oil/PRW sensors are not created
    coord = _coord(vep_client)
    assert _create_sensor_if_eligible("oilwarninglevel", SENSORS["oilwarninglevel"], vep_car, coord) is None
    assert _create_sensor_if_eligible("tirewarninglevelprw", SENSORS["tirewarninglevelprw"], vep_car, coord) is None

    # nextDepartureTime with nil_value=True and status=3 clears to STATE_UNKNOWN
    vep_nil = build_vep_updates()
    nil_attr = vep_nil.vepUpdates.updates[SYNTH_VIN].attributes["nextDepartureTime"]
    nil_attr.nil_value = True
    nil_attr.status = 3
    vep_client._process_vep_updates(roundtrip(vep_nil))
    assert vep_client.cars[SYNTH_VIN].electric.nextDepartureTime.value == STATE_UNKNOWN
    assert vep_client.cars[SYNTH_VIN].electric.nextDepartureTime.retrievalstatus == 3


def test_legacy_vehicle_spawns_no_x244_entities() -> None:
    """Existing baseline VEP cars without X244 attributes must not create spurious entities."""
    client = make_client()
    client._process_vep_updates(roundtrip(build_vep_updates()))
    car = client.cars[SYNTH_VIN]
    coord = _coord(client)

    for key in _TELEMETRY_SENSOR_KEYS:
        assert _create_sensor_if_eligible(key, SENSORS[key], car, coord) is None, (
            f"Legacy vehicle should not spawn sensor {key}"
        )
    for key in _TELEMETRY_BINARY_SENSOR_KEYS:
        assert _create_binary_sensor_if_eligible(key, BinarySensors[key], car, coord) is None, (
            f"Legacy vehicle should not spawn binary_sensor {key}"
        )


def test_bev_and_sunroof_sensor_filtering_and_categorical_states() -> None:
    """Pure BEVs without sunroof skip ICE/hybrid/sunroof sensors; categorical sensors return strings."""
    client = make_client()
    push, vsu = _make_vsu_push(1, full_update=True)
    vsu.filter_particle_loading.metadata.timestamp.seconds = 1780591500
    vsu.hybrid_warnings.metadata.timestamp.seconds = 1780591500
    vsu.turn_off_engine_pre_warning.metadata.timestamp.seconds = 1780591500
    vsu.sunroof_event.metadata.timestamp.seconds = 1780591500
    vsu.soh_calibration_state.metadata.timestamp.seconds = 1780591500
    client._process_vehicle_status_updates(roundtrip(push))

    car = client.cars[SYNTH_VIN]
    car.vehicle_information = {
        "electricVehicleType": "BATTERY",
        "fuelTypes": ["ELECTRIC"],
        "sunroofType": None,
    }
    car.features = {"controllableSunroof": False, "variableOpenableSunroof": False}
    coord = _coord(client)

    for excluded in ("filterparticleloading", "hybridwarnings", "turnoffengineprewarning", "sunroofevent"):
        assert _create_sensor_if_eligible(excluded, SENSORS[excluded], car, coord) is None

    soh_sensor = _create_sensor_if_eligible("sohcalibrationstate", SENSORS["sohcalibrationstate"], car, coord)
    assert soh_sensor is not None
    _stub_entity_update(soh_sensor)
    assert soh_sensor.state == "0"

    # activeweeklyprofile returns 'none' when no slots exist, and 'inactive' when slots exist but none is active
    if car.electric is None:
        car.electric = Electric()
    car.electric.weeklyProfileActive = CarAttribute(None, "VALID", 1780591500)
    car.electric.weeklyProfileSlots = CarAttribute([], "VALID", 1780591500)
    wp_sensor = _create_sensor_if_eligible("activeweeklyprofile", SENSORS["activeweeklyprofile"], car, coord)
    assert wp_sensor is not None
    assert wp_sensor.state == "none"

    car.electric.weeklyProfileSlots = CarAttribute(["#1 Su 14:40 [inactive]"], "VALID", 1780591500)
    wp_sensor._state = None
    assert wp_sensor.state == "inactive"
