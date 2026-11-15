"""Offline tests for HV battery conditioning switch/buttons, ventilate windows button, and charging timers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.mbapi2020.button import MercedesMEButton
from custom_components.mbapi2020.car import ELECTRIC_OPTIONS, Car, Electric, Precond
from custom_components.mbapi2020.const import BUTTONS, CONF_PIN, SENSORS, SensorConfigFields as scf
from custom_components.mbapi2020.proto import client_pb2, vehicle_events_pb2
from custom_components.mbapi2020.switch import SWITCH_DESCRIPTIONS, MercedesMeSwitch
from homeassistant.exceptions import ServiceValidationError
from tests.conftest import make_client
from tests.fixtures.build import build_vep_updates, roundtrip


def _make_coordinator(client, vin: str):
    """Build a minimal coordinator stub backed by an offline Client."""
    entry = getattr(client, "config_entry", None) or SimpleNamespace(entry_id="test_entry", options={})
    if not hasattr(entry, "entry_id"):
        entry = SimpleNamespace(entry_id="test_entry", options=getattr(entry, "options", {}))
    return SimpleNamespace(
        client=client,
        config_entry=entry,
        hass=None,
        last_update_success=True,
    )


def _register_car(client, vin: str, *, features: dict[str, bool], commands: list[dict] | None = None) -> Car:
    """Create and attach a Car with explicit features and /commands payload."""
    car = Car(vin)
    car.licenseplate = "TEST-X244"
    car.baumuster_description = "Test Vehicle"
    car.electric = Electric()
    car.precond = Precond()
    car.entry_setup_complete = True
    car.features = dict(features)
    if commands is not None:
        car.capabilities = {"commands": commands, "features": dict(features)}
    client.cars[vin] = car
    return car


def _send_vep(client, vin: str, **attrs: vehicle_events_pb2.VehicleAttributeStatus) -> None:
    """Feed a synthetic VEPUpdate through client._process_vep_updates."""
    push = build_vep_updates(vin=vin, full_update=False)
    update = push.vepUpdates.updates[vin]
    for key, val in attrs.items():
        update.attributes[key].CopyFrom(val)
    client._process_vep_updates(roundtrip(push))


def test_hv_battery_and_timer_definitions_are_registered():
    """Verify HV battery conditioning and timer sensors/buttons are registered in const.py."""
    for attr_name in (
        "chargingTimers",
        "chargingTimerSlots",
        "hvBatteryPrecondActive",
        "hvBatteryPrecondState",
        "weeklyProfileSlots",
    ):
        assert attr_name in ELECTRIC_OPTIONS

    assert "chargingtimers" in SENSORS
    assert SENSORS["chargingtimers"][scf.DEFAULT_VALUE_MODE.value] is None
    assert "hvbatteryprecondstate" in SENSORS
    assert SENSORS["hvbatteryprecondstate"][scf.DEFAULT_VALUE_MODE.value] is None
    assert "electric.weeklyProfileSlots" in SENSORS["activeweeklyprofile"][scf.EXTENDED_ATTRIBUTE_LIST.value]

    for btn_key in ("btn_hv_battery_start_conditioning", "btn_hv_battery_stop_conditioning", "btn_windows_ventilate"):
        assert btn_key in BUTTONS


@pytest.mark.anyio
async def test_buttons_and_hv_battery_switch_telemetry():
    """Verify ventilate PIN guard, HV battery switch telemetry + assumed_state fallback."""
    client = make_client()
    executed: list[client_pb2.ClientMessage] = []
    client.execute_car_command = AsyncMock(side_effect=lambda msg: executed.append(msg))
    car = _register_car(
        client,
        "TESTVIN_BTN_SW",
        features={
            "HVBATTERY_START_CONDITIONING": True,
            "HVBATTERY_STOP_CONDITIONING": True,
            "WINDOWS_VENTILATE": True,
        },
    )
    coord = _make_coordinator(client, car.finorvin)

    btn_vent = MercedesMEButton("btn_windows_ventilate", BUTTONS["btn_windows_ventilate"], car.finorvin, coord)
    with pytest.raises(ServiceValidationError, match="PIN"):
        await btn_vent.async_press()
    assert not executed

    client.config_entry = SimpleNamespace(entry_id="test_entry", options={CONF_PIN: "1234"})
    await btn_vent.async_press()
    assert executed[-1].commandRequest.WhichOneof("command") == "windows_ventilate"
    assert executed[-1].commandRequest.windows_ventilate.pin == "1234"

    hv_desc = next(d for d in SWITCH_DESCRIPTIONS if d.key == "hv_battery_conditioning")
    sw = MercedesMeSwitch(hv_desc, car.finorvin, coord)
    sw._mercedes_me_update()
    # Absent telemetry => assumed_state True
    assert sw.is_on is False
    assert sw.assumed_state is True

    # Feed VEP update for hvBatteryPrecondState, availability, and duration
    _send_vep(
        client,
        car.finorvin,
        hvBatteryPrecondState=vehicle_events_pb2.VehicleAttributeStatus(
            status=0,
            timestamp=1_780_000_001,
            hv_battery_precond_state=vehicle_events_pb2.HvBatteryPrecondState(
                charging=vehicle_events_pb2.HvBatteryPrecondStatesCharging.CHARGING_HEATING_ACTIVE,
                discharging=vehicle_events_pb2.HvBatteryPrecondStatesDischarging.DISCHARGING_INACTIVE,
            ),
        ),
        hvBatteryPrecondAvailability=vehicle_events_pb2.VehicleAttributeStatus(
            status=0,
            timestamp=1_780_000_001,
            display_value="FULLY_AVAILABLE",
            hv_battery_precond_availability=vehicle_events_pb2.HV_BATTERY_PRECOND_AVAILABILITY_FULLY_AVAILABLE,
        ),
        hvBatteryPrecondDuration=vehicle_events_pb2.VehicleAttributeStatus(
            status=0,
            timestamp=1_780_000_001,
            int_value=15,
            display_value="15",
        ),
    )
    assert car.electric.hvBatteryPrecondActive.value is True
    assert car.electric.hvBatteryPrecondState.value == "charging_heating_active"
    sw._mercedes_me_update()
    assert sw.is_on is True
    assert sw.assumed_state is False
    assert sw.extra_state_attributes["state"] == "charging_heating_active"
    assert sw.extra_state_attributes["availability"] == "FULLY_AVAILABLE"
    assert sw.extra_state_attributes["duration"] == "15"

    # Discharging cooling also marks active
    _send_vep(
        client,
        car.finorvin,
        hvBatteryPrecondState=vehicle_events_pb2.VehicleAttributeStatus(
            status=0,
            timestamp=1_780_000_002,
            hv_battery_precond_state=vehicle_events_pb2.HvBatteryPrecondState(
                charging=vehicle_events_pb2.HvBatteryPrecondStatesCharging.CHARGING_HEATING_INACTIVE,
                discharging=vehicle_events_pb2.HvBatteryPrecondStatesDischarging.DISCHARGING_COOLING_ACTIVE,
            ),
        ),
    )
    assert car.electric.hvBatteryPrecondActive.value is True
    assert car.electric.hvBatteryPrecondState.value == "discharging_cooling_active"

    await sw.async_turn_off()
    assert executed[-1].commandRequest.WhichOneof("command") == "hv_battery_stop_conditioning"

    car._data_collection_mode = "pull"
    with pytest.raises(ServiceValidationError):
        await sw.async_turn_on()


def test_weekly_profile_slots_and_modern_plus_legacy_charging_timers():
    """Verify weeklyProfileSlots and unified chargingTimers across MB.OS and legacy shapes."""
    client = make_client()

    # Case A: MB.OS modern chargingTimer + weeklyProfile
    mbos = _register_car(client, "TESTVIN_TIMERS_MBOS", features={"CHARGING_CLOCK_TIMER_CONFIGURE": True})
    wp_status = vehicle_events_pb2.VehicleAttributeStatus(status=0, timestamp=100)
    wp_entry1 = wp_status.weekly_profile_value.time_profiles.add()
    wp_entry1.identifier = 1
    wp_entry1.hour.value = 6
    wp_entry1.minute.value = 30
    wp_entry1.active.value = True
    wp_entry1.days.extend([0, 1, 2, 3, 4])
    wp_entry1.action_list.add(charging=True, precond=True)
    wp_entry2 = wp_status.weekly_profile_value.time_profiles.add()
    wp_entry2.identifier = 2
    wp_entry2.hour.value = 9
    wp_entry2.minute.value = 0
    wp_entry2.active.value = False
    wp_entry2.days.extend([6])

    ct_status = vehicle_events_pb2.VehicleAttributeStatus(status=0, timestamp=100)
    ct1 = ct_status.charging_timer.entries.add()
    ct1.timerId = 1
    ct1.action = 2  # CHARGING_TIMER_ACTION_ACTIVE
    ct1.start_time_hour = 22
    ct1.start_time_min = 0
    ct1.end_time_hour = 6
    ct1.end_time_min = 0
    ct1.day.extend([0, 1, 2, 3, 4])  # Mo-Fr

    ct2 = ct_status.charging_timer.entries.add()
    ct2.timerId = 2
    ct2.action = 3  # CHARGING_TIMER_ACTION_DELETED -> excluded from slots

    _send_vep(client, mbos.finorvin, weeklyProfile=wp_status, chargingTimer=ct_status)

    assert mbos.electric.weeklyProfileSlots.value == [
        "#1 Mo-Fr 06:30 [active: charging, precond]",
        "#2 Su 09:00 [inactive]",
    ]
    assert mbos.electric.chargingTimers.value == "Mo-Fr 22:00-06:00"
    assert mbos.electric.chargingTimers.display_value == "Mo-Fr 22:00-06:00"
    assert mbos.electric.chargingTimerSlots.value == [
        {
            "timer_id": 1,
            "status": "active",
            "active": True,
            "start_time": "22:00",
            "end_time": "06:00",
            "days": ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"],
            "label": "Mo-Fr 22:00-06:00",
        }
    ]

    # Partial update without timers leaves chargingTimers intact
    _send_vep(
        client,
        mbos.finorvin,
        soc=vehicle_events_pb2.VehicleAttributeStatus(status=0, timestamp=200, int_value=82),
    )
    assert mbos.electric.chargingTimers.value == "Mo-Fr 22:00-06:00"

    # Case B: Legacy chargingBreakClockTimer normalized into chargingTimers + chargingTimerSlots
    legacy = _register_car(client, "TESTVIN_TIMERS_LEGACY", features={})
    bt_status = vehicle_events_pb2.VehicleAttributeStatus(status=0, timestamp=100)
    bt1 = bt_status.chargingbreak_clocktimer_value.chargingbreak_clocktimer_entry.add()
    bt1.timerId = 1
    bt1.status = 2  # ACTIVE
    bt1.startTimeHour = 23
    bt1.startTimeMinute = 30
    bt1.endTimeHour = 5
    bt1.endTimeMinute = 15
    bt2 = bt_status.chargingbreak_clocktimer_value.chargingbreak_clocktimer_entry.add()
    bt2.timerId = 2
    bt2.status = 1  # INACTIVE
    bt2.startTimeHour = 12
    bt2.startTimeMinute = 0
    bt2.endTimeHour = 14
    bt2.endTimeMinute = 0

    _send_vep(client, legacy.finorvin, chargingBreakClockTimer=bt_status)
    assert legacy.electric.chargingTimers.value == "23:30-05:15"
    assert len(legacy.electric.chargingTimerSlots.value) == 2
    assert legacy.electric.chargingTimerSlots.value[0]["active"] is True
    assert legacy.electric.chargingTimerSlots.value[1]["status"] == "inactive"
    assert legacy.electric.chargingBreakClockTimer.value is not None

    # Case C: ICE car with neither chargingTimer nor hvBatteryPrecondState exposes neither
    ice = _register_car(client, "TESTVIN_TIMERS_ICE", features={})
    _send_vep(
        client,
        ice.finorvin,
        odo=vehicle_events_pb2.VehicleAttributeStatus(status=0, timestamp=100, int_value=12345),
    )
    assert getattr(ice.electric, "chargingTimers", None) is None
    assert getattr(ice.electric, "hvBatteryPrecondState", None) is None
