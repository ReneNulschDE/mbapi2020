"""Offline regression tests for MB.OS (STAR3.5 / X244) command routing and compatibility fixes."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import json
from pathlib import Path
from types import SimpleNamespace

from google.protobuf.wrappers_pb2 import BoolValue
import pytest
import yaml

from custom_components.mbapi2020 import const as mb_const
from custom_components.mbapi2020.car import BINARY_SENSOR_OPTIONS, ELECTRIC_OPTIONS, PRE_COND_OPTIONS, Car
from custom_components.mbapi2020.const import (
    CONF_FT_DISABLE_CAPABILITY_CHECK,
    CONF_PIN,
    CONF_VIN,
    DOMAIN,
    SENSORS,
    SERVICE_BATTERY_MAX_SOC_CONFIGURE_SCHEMA,
    SERVICE_CHARGING_BREAK_CLOCKTIMER_CONFIGURE_SCHEMA,
    SERVICE_HV_BATTERY_START_CONDITIONING,
    SERVICE_HV_BATTERY_STOP_CONDITIONING,
    SERVICE_VIN_CHARGE_PROGRAM_SCHEMA,
    SERVICE_WINDOWS_VENTILATE,
    BinarySensors,
    SensorConfigFields as scf,
)
from custom_components.mbapi2020.cover import WINDOW_COVER_DESCRIPTIONS, MercedesMeCover
from custom_components.mbapi2020.proto import vehicle_commands_pb2 as pb2_commands, vehicle_events_pb2
from custom_components.mbapi2020.services import remove_services, setup_services
from homeassistant.components.cover import CoverEntityFeature
from homeassistant.exceptions import ServiceValidationError

from .conftest import SYNTH_VIN, make_client
from .fixtures.build import build_vep_updates, roundtrip

COMPONENT_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "mbapi2020"


def _make_command_client(
    *, features: dict[str, bool] | None = None, disable_cap_check: bool = False, pin: str = "1234"
):
    """Return a client with a single car and a command recorder."""
    client = make_client()
    client.config_entry.options = {CONF_PIN: pin}
    if disable_cap_check:
        client.config_entry.options[CONF_FT_DISABLE_CAPABILITY_CHECK] = True
    client._process_vep_updates(roundtrip(build_vep_updates()))
    client.cars[SYNTH_VIN].features = dict(features or {})

    sent: list[vehicle_events_pb2.ClientMessage] = []

    async def _capture(message: vehicle_events_pb2.ClientMessage) -> None:
        sent.append(message)

    client.execute_car_command = _capture  # type: ignore[method-assign]
    return client, sent


def _make_vsu_push(sequence_number: int, *, full_update: bool = True):
    """Build a PushMessage containing one VehicleStatusUpdate for SYNTH_VIN."""
    push = vehicle_events_pb2.PushMessage()
    push.vehicle_status_updates.sequence_number = sequence_number
    vsu = push.vehicle_status_updates.vehicle_status_updates[SYNTH_VIN]
    vsu.fin_or_vin = SYNTH_VIN
    vsu.full_update = full_update
    return push, vsu


def _make_cover(client, key: str = "windows") -> MercedesMeCover:
    """Instantiate one cover entity against a stubbed coordinator."""
    description = next(item for item in WINDOW_COVER_DESCRIPTIONS if item.key == key)
    coordinator = SimpleNamespace(
        hass=None,
        client=client,
        config_entry=client.config_entry,
        last_update_success=True,
    )
    return MercedesMeCover(description, SYNTH_VIN, coordinator)


def test_hv_battery_and_ventilate_services_registered_and_defined_in_yaml() -> None:
    """Phase 1 services must be registered, unloaded cleanly, and match services.yaml/translations."""
    registered: dict[str, tuple[object, object]] = {}
    removed: list[str] = []

    hass = SimpleNamespace(
        data={DOMAIN: {}},
        services=SimpleNamespace(
            async_register=lambda dom, name, handler, schema=None: registered.setdefault(name, (handler, schema)),
            async_remove=lambda dom, name: removed.append(name),
        ),
    )

    setup_services(hass)  # type: ignore[arg-type]
    assert SERVICE_HV_BATTERY_START_CONDITIONING in registered
    assert SERVICE_HV_BATTERY_STOP_CONDITIONING in registered
    assert SERVICE_WINDOWS_VENTILATE in registered

    remove_services(hass)  # type: ignore[arg-type]
    assert SERVICE_HV_BATTERY_START_CONDITIONING in removed
    assert SERVICE_HV_BATTERY_STOP_CONDITIONING in removed
    assert SERVICE_WINDOWS_VENTILATE in removed

    services_yaml = yaml.safe_load((COMPONENT_DIR / "services.yaml").read_text(encoding="utf-8"))
    assert "hv_battery_stop_conditioning" in services_yaml
    assert "hv_battery_stop_conditioninge_stop" not in services_yaml
    assert "windows_ventilate" in services_yaml

    en_json = json.loads((COMPONENT_DIR / "translations" / "en.json").read_text(encoding="utf-8"))
    assert "hv_battery_start_conditioning" in en_json["services"]
    assert "hv_battery_stop_conditioning" in en_json["services"]
    assert "windows_ventilate" in en_json["services"]


def test_hv_battery_conditioning_commands_serialize_expected_proto() -> None:
    """Start/stop HV battery conditioning emit their respective CommandRequest oneofs."""
    client, sent = _make_command_client(
        features={"HVBATTERY_START_CONDITIONING": True, "HVBATTERY_STOP_CONDITIONING": True}
    )

    asyncio.run(client.hv_battery_start_conditioning(SYNTH_VIN))
    asyncio.run(client.hv_battery_stop_conditioning(SYNTH_VIN))

    assert len(sent) == 2
    assert sent[0].commandRequest.WhichOneof("command") == "hv_battery_start_conditioning"
    assert sent[1].commandRequest.WhichOneof("command") == "hv_battery_stop_conditioning"


def test_charge_program_configure_supports_legacy_modern_and_instant() -> None:
    """charge_program_configure picks the protobuf command matching the vehicle capabilities."""
    # Legacy vehicle: valid program + clamps max_soc < 50 to 50
    legacy_client, legacy_sent = _make_command_client(features={"CHARGE_PROGRAM_CONFIGURE": True})
    asyncio.run(legacy_client.charge_program_configure(SYNTH_VIN, 2, 80))
    assert legacy_sent[0].commandRequest.WhichOneof("command") == "charge_program_configure"
    assert legacy_sent[0].commandRequest.charge_program_configure.charge_program == 2
    assert legacy_sent[0].commandRequest.charge_program_configure.max_soc.value == 80
    asyncio.run(legacy_client.charge_program_configure(SYNTH_VIN, 0, 30))
    assert legacy_sent[1].commandRequest.WhichOneof("command") == "charge_program_configure"
    assert legacy_sent[1].commandRequest.charge_program_configure.max_soc.value == 50
    asyncio.run(legacy_client.charge_program_configure(SYNTH_VIN, 0, 40))
    assert legacy_sent[2].commandRequest.charge_program_configure.max_soc.value == 50
    with pytest.raises(ServiceValidationError):
        asyncio.run(legacy_client.charge_program_configure(SYNTH_VIN, 1, 80))

    # Modern CHARGING_CONFIGURE vehicle (even with disable_cap_check=True) preserves max_soc=30
    modern_client, modern_sent = _make_command_client(
        features={"CHARGE_PROGRAM_CONFIGURE": False, "CHARGING_CONFIGURE": True},
        disable_cap_check=True,
    )
    asyncio.run(modern_client.charge_program_configure(SYNTH_VIN, 0, 30))
    assert modern_sent[0].commandRequest.WhichOneof("command") == "charging_configure"
    assert modern_sent[0].commandRequest.charging_configure.charging_program.value == 0
    assert modern_sent[0].commandRequest.charging_configure.max_soc.value == 30

    # Instant-only BATTERY_CHARGE_PROGRAM_CONFIGURE fallback
    instant_client, instant_sent = _make_command_client(features={"BATTERY_CHARGE_PROGRAM_CONFIGURE": True})
    asyncio.run(instant_client.charge_program_configure(SYNTH_VIN, 1))
    assert instant_sent[0].commandRequest.WhichOneof("command") == "battery_charge_program"
    assert instant_sent[0].commandRequest.battery_charge_program.charge_program == 1
    with pytest.raises(ServiceValidationError):
        asyncio.run(instant_client.charge_program_configure(SYNTH_VIN, 2))

    # Schema allows 0/2/3 + 30% SoC, and rejects 1 and out-of-range program IDs
    parsed = SERVICE_VIN_CHARGE_PROGRAM_SCHEMA({CONF_VIN: SYNTH_VIN, "charge_program": 2, "max_soc": 30})
    assert parsed["charge_program"] == 2
    assert parsed["max_soc"] == 30
    for invalid_program in (1, 4):
        with pytest.raises(mb_const.vol.Invalid):
            SERVICE_VIN_CHARGE_PROGRAM_SCHEMA({CONF_VIN: SYNTH_VIN, "charge_program": invalid_program})

    # YAML/translation selectors stay at 0/2/3
    services_yaml = yaml.safe_load((COMPONENT_DIR / "services.yaml").read_text(encoding="utf-8"))
    assert services_yaml["charge_program_configure"]["fields"]["charge_program"]["selector"]["select"]["options"] == [
        "0",
        "2",
        "3",
    ]
    assert services_yaml["battery_max_soc_configure"]["fields"]["charge_program"]["selector"]["select"]["options"] == [
        "0",
        "2",
        "3",
    ]
    en_json = json.loads((COMPONENT_DIR / "translations" / "en.json").read_text(encoding="utf-8"))
    assert list(en_json["selector"]["charge_program"]["options"]) == ["0", "2", "3"]


def test_battery_max_soc_configure_respects_explicit_program_and_standalone_fallback() -> None:
    """battery_max_soc_configure honors explicit programs, preserves omitted behavior, and handles standalone."""
    # CHARGING_CONFIGURE car reporting selectedChargeProgram=4
    client, sent = _make_command_client(features={"CHARGING_CONFIGURE": True})
    client.cars[SYNTH_VIN].electric.selectedChargeProgram = SimpleNamespace(value=4)

    # Omitted charge_program -> do not set charging_program field (CLA 2025/X244 compatibility)
    asyncio.run(client.battery_max_soc_configure(SYNTH_VIN, 80))
    assert sent[0].commandRequest.WhichOneof("command") == "charging_configure"
    assert sent[0].commandRequest.charging_configure.max_soc.value == 80
    assert not sent[0].commandRequest.charging_configure.HasField("charging_program")

    # Explicit charge_program -> forward it in charging_configure
    asyncio.run(client.battery_max_soc_configure(SYNTH_VIN, 90, charge_program=2))
    assert sent[1].commandRequest.WhichOneof("command") == "charging_configure"
    assert sent[1].commandRequest.charging_configure.max_soc.value == 90
    assert sent[1].commandRequest.charging_configure.HasField("charging_program")
    assert sent[1].commandRequest.charging_configure.charging_program.value == 2

    # Standalone BATTERY_MAX_SOC_CONFIGURE without CHARGING_CONFIGURE or CHARGE_PROGRAM_CONFIGURE
    standalone_client, standalone_sent = _make_command_client(features={"BATTERY_MAX_SOC_CONFIGURE": True})
    asyncio.run(standalone_client.battery_max_soc_configure(SYNTH_VIN, 70))
    assert standalone_sent[0].commandRequest.WhichOneof("command") == "battery_max_soc"
    assert standalone_sent[0].commandRequest.battery_max_soc.max_soc == 70

    # Legacy car with disable_cap_check=True must not switch to ChargingConfigure
    legacy_client, legacy_sent = _make_command_client(
        features={"CHARGE_PROGRAM_CONFIGURE": True, "CHARGING_CONFIGURE": False},
        disable_cap_check=True,
    )
    asyncio.run(legacy_client.battery_max_soc_configure(SYNTH_VIN, 80, charge_program=0))
    assert legacy_sent[0].commandRequest.WhichOneof("command") == "charge_program_configure"
    assert legacy_sent[0].commandRequest.charge_program_configure.max_soc.value == 80

    # Legacy car currently on program 1 (Instant): omitting charge_program must raise instead of switching to 0
    legacy_client.cars[SYNTH_VIN].electric.selectedChargeProgram = SimpleNamespace(value=1)
    with pytest.raises(ServiceValidationError):
        asyncio.run(legacy_client.battery_max_soc_configure(SYNTH_VIN, 80))
    assert len(legacy_sent) == 1

    # Schema allows 0/2/3 and rejects 1 and 4
    parsed = SERVICE_BATTERY_MAX_SOC_CONFIGURE_SCHEMA({CONF_VIN: SYNTH_VIN, "max_soc": 80, "charge_program": 2})
    assert parsed["charge_program"] == 2
    for invalid_program in (1, 4):
        with pytest.raises(mb_const.vol.Invalid):
            SERVICE_BATTERY_MAX_SOC_CONFIGURE_SCHEMA(
                {CONF_VIN: SYNTH_VIN, "max_soc": 80, "charge_program": invalid_program}
            )


def test_windows_move_capability_cover_and_ventilate() -> None:
    """Explicit WINDOWS_MOVE=False gates window positioning without breaking HTTP-401 fallback or ventilate."""
    car = Car(SYNTH_VIN)
    car.features = {"WINDOWS_MOVE": False, "variableOpenableWindow": True}
    assert car.can_move_windows() is False
    car.features = {"variableOpenableWindow": True}
    assert car.can_move_windows() is True
    car.features = {"WINDOWS_MOVE": True, "variableOpenableWindow": False}
    assert car.can_move_windows() is True

    # X244 capability set: OPEN/CLOSE/VENTILATE supported, WINDOWS_MOVE disabled
    x244_features = {
        "WINDOWS_OPEN": True,
        "WINDOWS_CLOSE": True,
        "WINDOWS_VENTILATE": True,
        "WINDOWS_MOVE": False,
        "variableOpenableWindow": True,
    }
    client, sent = _make_command_client(features=x244_features)
    enabled_keys = [desc.key for desc in WINDOW_COVER_DESCRIPTIONS if desc.check_capability_fn(client.cars[SYNTH_VIN])]
    assert enabled_keys == ["windows"]

    overall_cover = _make_cover(client, "windows")
    assert overall_cover.supported_features & CoverEntityFeature.OPEN
    assert overall_cover.supported_features & CoverEntityFeature.CLOSE
    assert not (overall_cover.supported_features & CoverEntityFeature.SET_POSITION)

    asyncio.run(overall_cover.async_set_cover_position(position=40))
    asyncio.run(client.windows_move(SYNTH_VIN, 40, 40, 40, 40))
    assert sent == []

    # windows_ventilate sends CommandRequest.windows_ventilate
    asyncio.run(client.windows_ventilate(SYNTH_VIN))
    assert len(sent) == 1
    assert sent[0].commandRequest.WhichOneof("command") == "windows_ventilate"
    assert sent[0].commandRequest.windows_ventilate.pin == "1234"

    # Legacy 401 fallback: no WINDOWS_MOVE key + variableOpenableWindow=True still enables SET_POSITION and windows_move
    legacy_client, legacy_sent = _make_command_client(features={"variableOpenableWindow": True})
    legacy_keys = [
        desc.key for desc in WINDOW_COVER_DESCRIPTIONS if desc.check_capability_fn(legacy_client.cars[SYNTH_VIN])
    ]
    assert len(legacy_keys) == 5
    legacy_cover = _make_cover(legacy_client, "windows")
    assert legacy_cover.supported_features & CoverEntityFeature.SET_POSITION
    asyncio.run(legacy_client.windows_move(SYNTH_VIN, 50, None, 0, None))
    assert legacy_sent[0].commandRequest.WhichOneof("command") == "windows_move"
    assert legacy_sent[0].commandRequest.windows_move.front_left.value == 50
    assert legacy_sent[0].commandRequest.windows_move.HasField("rear_left")
    assert legacy_sent[0].commandRequest.windows_move.rear_left.value == 0


def test_charging_clock_timer_configure_modern_and_legacy() -> None:
    """Modern cars use ClockTimerConfigure (1..7, days, delete); legacy cars keep ChargingBreakClocktimerConfigure."""
    modern_client, modern_sent = _make_command_client(
        features={"chargingClockTimer": False, "CHARGING_CLOCK_TIMER_CONFIGURE": True},
        disable_cap_check=True,
    )
    asyncio.run(
        modern_client.charging_break_clocktimer_configure(
            SYNTH_VIN,
            "active",
            timedelta(hours=22, minutes=15),
            timedelta(hours=6, minutes=30),
            days_t1=["monday", "friday"],
            status_t5="delete",
        )
    )
    assert len(modern_sent) == 1
    assert modern_sent[0].commandRequest.WhichOneof("command") == "clock_timer_configure"
    entries = modern_sent[0].commandRequest.clock_timer_configure.clock_timer_configure_entry
    assert len(entries) == 2
    assert entries[0].timer_id == 1
    assert entries[0].action == pb2_commands.ClockTimerConfigureEntry.Action.ACTIVATE
    assert entries[0].start_time_hour == 22
    assert entries[0].start_time_min == 15
    assert entries[0].end_time_hour == 6
    assert entries[0].end_time_min == 30
    assert list(entries[0].days) == [
        pb2_commands.ClockTimerConfigureEntry.Day.MONDAY,
        pb2_commands.ClockTimerConfigureEntry.Day.FRIDAY,
    ]
    assert entries[1].timer_id == 5
    assert entries[1].action == pb2_commands.ClockTimerConfigureEntry.Action.DELETE
    assert list(entries[1].days) == []

    # When days_timer_N is omitted, preserve the timer's current days from VSU charging_timer
    timer_push, timer_vsu = _make_vsu_push(15, full_update=False)
    existing_t2 = timer_vsu.charging_timer.value.add()
    existing_t2.timerId = 2
    existing_t2.action = vehicle_events_pb2.ChargingTimerEntry.CHARGING_TIMER_ACTION_ACTIVE
    existing_t2.start_time_hour = 23
    existing_t2.start_time_min = 0
    existing_t2.end_time_hour = 7
    existing_t2.end_time_min = 0
    existing_t2.day.extend([0, 2, 4])  # Mo, We, Fr
    modern_client._process_vehicle_status_updates(roundtrip(timer_push))

    asyncio.run(
        modern_client.charging_break_clocktimer_configure(
            SYNTH_VIN,
            status_t2="inactive",
            start_t2=timedelta(hours=23, minutes=0),
            stop_t2=timedelta(hours=7, minutes=0),
        )
    )
    assert len(modern_sent) == 2
    t2_entries = modern_sent[1].commandRequest.clock_timer_configure.clock_timer_configure_entry
    assert len(t2_entries) == 1
    assert t2_entries[0].timer_id == 2
    assert t2_entries[0].action == pb2_commands.ClockTimerConfigureEntry.Action.DEACTIVATE
    assert list(t2_entries[0].days) == [
        pb2_commands.ClockTimerConfigureEntry.Day.MONDAY,
        pb2_commands.ClockTimerConfigureEntry.Day.WEDNESDAY,
        pb2_commands.ClockTimerConfigureEntry.Day.FRIDAY,
    ]

    # Schema validates timer 5 + days_timer_1 + delete action
    validated = SERVICE_CHARGING_BREAK_CLOCKTIMER_CONFIGURE_SCHEMA(
        {
            CONF_VIN: SYNTH_VIN,
            "status_timer_1": "delete",
            "days_timer_1": ["monday", "tuesday"],
            "status_timer_5": "active",
            "starttime_timer_5": "08:00:00",
            "stoptime_timer_5": "09:30:00",
        }
    )
    assert validated["status_timer_5"] == "active"

    # Legacy car continues emitting ChargingBreakClocktimerConfigure
    legacy_client, legacy_sent = _make_command_client(features={"chargingClockTimer": True})
    asyncio.run(
        legacy_client.charging_break_clocktimer_configure(
            SYNTH_VIN,
            "inactive",
            timedelta(hours=1),
            timedelta(hours=2),
        )
    )
    assert legacy_sent[0].commandRequest.WhichOneof("command") == "chargingbreak_clocktimer_configure"
    legacy_entries = legacy_sent[
        0
    ].commandRequest.chargingbreak_clocktimer_configure.chargingbreak_clocktimer_configure_entry
    assert len(legacy_entries) == 1
    assert legacy_entries[0].timerId == 1
    assert legacy_entries[0].action == pb2_commands.ChargingBreakClockTimerEntryStatus.INACTIVE


def test_warning_brake_lining_wear_maps_from_vsu_and_rest() -> None:
    """Warningbrakeliningwear maps to Car.binarysensors.warningBrakeLiningWear and parkbrakestatus attributes."""
    assert "warningBrakeLiningWear" in BINARY_SENSOR_OPTIONS
    assert "warningBrakeLiningWear" in BinarySensors["parkbrakestatus"][scf.EXTENDED_ATTRIBUTE_LIST.value]

    # VSU wire update path
    vsu_client = make_client()
    push, vsu = _make_vsu_push(10, full_update=True)
    vsu.warningbrakeliningwear.value = True
    vsu_client._process_vehicle_status_updates(roundtrip(push))
    assert vsu_client.cars[SYNTH_VIN].binarysensors.warningBrakeLiningWear.value is True

    # VEP/REST attribute key path (lowercase key)
    vep_client = make_client()
    vep_push = build_vep_updates()
    attr = vep_push.vepUpdates.updates[SYNTH_VIN].attributes["warningbrakeliningwear"]
    attr.bool_value = True
    vep_client._process_vep_updates(roundtrip(vep_push))
    assert vep_client.cars[SYNTH_VIN].binarysensors.warningBrakeLiningWear.value is True


def test_charging_prediction_range_preserved_alongside_end_time() -> None:
    """predicted_electrical_energy_range populates chargingPredictionMaxSocRange without altering endofchargetime."""
    assert "chargingPredictionMaxSocRange" in ELECTRIC_OPTIONS
    assert "chargingPredictionMaxSocRange" in SENSORS["rangeElectricKm"][scf.EXTENDED_ATTRIBUTE_LIST.value]
    assert SENSORS["chargingpredictionmaxsocrange"][scf.ATTRIBUTE_NAME.value] == "chargingPredictionMaxSocRange"

    # Full VSU carrying both predicted_end_time and predicted_electrical_energy_range
    client = make_client()
    push, vsu = _make_vsu_push(20, full_update=True)
    vsu.charging_prediction_max_soc.value.predicted_end_time.seconds = 1791895944
    vsu.charging_prediction_max_soc.value.predicted_electrical_energy_range = 528
    client._process_vehicle_status_updates(roundtrip(push))

    electric = client.cars[SYNTH_VIN].electric
    assert electric.endofchargetime.value is not None
    assert electric.chargingPredictionMaxSocRange.value == 528
    assert electric.chargingPredictionMaxSocRange.unit == "KILOMETERS"

    # Partial update without chargingPredictionMaxSoc must not wipe predicted range
    partial, partial_vsu = _make_vsu_push(21, full_update=False)
    partial_vsu.soc.value = 80
    client._process_vehicle_status_updates(roundtrip(partial))
    assert client.cars[SYNTH_VIN].electric.chargingPredictionMaxSocRange.value == 528

    # Older car sending empty chargingPredictionMaxSoc must not synthesize predicted range
    older_client = make_client()
    older_push = build_vep_updates()
    older_push.vepUpdates.updates[SYNTH_VIN].attributes[
        "chargingPredictionMaxSoc"
    ].charging_prediction_soc.SetInParent()
    older_client._process_vep_updates(roundtrip(older_push))
    assert not hasattr(older_client.cars[SYNTH_VIN].electric, "chargingPredictionMaxSocRange")


def test_temperature_points_active_preserved_across_vsu_and_vep() -> None:
    """temperature_points[].active reaches precond.temperature_points_<zone>Active for both VSU and VEP."""
    assert "temperature_points_frontCenter" in PRE_COND_OPTIONS
    for zone_attr in (
        "temperature_points_frontLeftActive",
        "temperature_points_frontRightActive",
        "temperature_points_rearLeftActive",
        "temperature_points_rearRightActive",
    ):
        assert zone_attr in PRE_COND_OPTIONS
        assert zone_attr in BinarySensors["preclimateStatus"][scf.EXTENDED_ATTRIBUTE_LIST.value]

    # VSU path: FRONT_LEFT active=True, FRONT_RIGHT active=False (omitted on wire, defaulted in vsu_helper)
    vsu_client = make_client()
    push, vsu = _make_vsu_push(30, full_update=True)
    p_fl = vsu.temperature_points.value.add()
    p_fl.zone = p_fl.FRONT_LEFT
    p_fl.temperature.value = 22.5
    p_fl.active = True
    p_fr = vsu.temperature_points.value.add()
    p_fr.zone = p_fr.FRONT_RIGHT
    p_fr.temperature.value = 20.0
    p_fr.active = False
    vsu_client._process_vehicle_status_updates(roundtrip(push))

    precond = vsu_client.cars[SYNTH_VIN].precond
    assert precond.temperature_points_frontLeft.value == 22.5
    assert precond.temperature_points_frontLeftActive.value is True
    assert precond.temperature_points_frontRight.value == 20.0
    assert precond.temperature_points_frontRightActive.value is False

    # VEP path: BoolValue preserves explicit True/False while unset stays absent
    vep_client = make_client()
    vep_push = build_vep_updates()
    tp_attr = vep_push.vepUpdates.updates[SYNTH_VIN].attributes["temperaturePoints"].temperature_points_value
    fl = tp_attr.temperature_points.add()
    fl.zone = "frontLeft"
    fl.temperature = 21.0
    fl.active.CopyFrom(BoolValue(value=True))
    rl = tp_attr.temperature_points.add()
    rl.zone = "rearLeft"
    rl.temperature = 19.0
    vep_client._process_vep_updates(roundtrip(vep_push))

    vep_precond = vep_client.cars[SYNTH_VIN].precond
    assert vep_precond.temperature_points_frontLeft.value == 21.0
    assert vep_precond.temperature_points_frontLeftActive.value is True
    assert vep_precond.temperature_points_rearLeft.value == 19.0
    assert not hasattr(vep_precond, "temperature_points_rearLeftActive")
