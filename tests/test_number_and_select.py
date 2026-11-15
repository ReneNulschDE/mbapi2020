"""Offline tests for native Number (max_soc) and Select (charge_program) platforms."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.mbapi2020 import async_setup_described_platform
from custom_components.mbapi2020.car import Car, CarAttribute, Electric, Precond
from custom_components.mbapi2020.const import DOMAIN, MERCEDESME_COMPONENTS
from custom_components.mbapi2020.number import NUMBER_DESCRIPTIONS, MercedesMeNumber
from custom_components.mbapi2020.proto import client_pb2, vehicle_events_pb2
from custom_components.mbapi2020.select import SELECT_DESCRIPTIONS, MercedesMeSelect
from homeassistant.const import Platform
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


def test_number_and_select_platforms_are_registered():
    """Verify Platform.NUMBER and Platform.SELECT are registered in MERCEDESME_COMPONENTS."""
    assert Platform.NUMBER in MERCEDESME_COMPONENTS
    assert Platform.SELECT in MERCEDESME_COMPONENTS


@pytest.mark.anyio
async def test_number_max_soc_mbos_limits_and_optimistic_update():
    """Verify MB.OS X244 max_soc slider respects CHARGING_CONFIGURE + maxSocLowerLimit/UpperLimit."""
    client = make_client()
    commands = [
        {
            "commandName": "CHARGING_CONFIGURE",
            "isAvailable": True,
            "parameters": [{"parameterName": "MAX_SOC", "minValue": 0, "maxValue": 100, "steps": 1}],
        },
        {
            "commandName": "BATTERY_MAX_SOC_CONFIGURE",
            "isAvailable": True,
            "parameters": [{"parameterName": "MAX_SOC", "minValue": 50, "maxValue": 100, "steps": 10}],
        },
    ]
    car = _register_car(
        client,
        "TESTVIN_MBOS_NUM",
        features={"CHARGING_CONFIGURE": True, "BATTERY_MAX_SOC_CONFIGURE": True, "CHARGE_PROGRAM_CONFIGURE": False},
        commands=commands,
    )
    car.electric.maxSoc = CarAttribute("80", "VALID", 100, "80", "PERCENT")
    car.electric.maxSocLowerLimit = CarAttribute("30", "VALID", 100, "30", "PERCENT")
    car.electric.maxSocUpperLimit = CarAttribute("100", "VALID", 100, "100", "PERCENT")

    executed: list[client_pb2.ClientMessage] = []
    client.execute_car_command = AsyncMock(side_effect=lambda msg: executed.append(msg))
    coord = _make_coordinator(client, car.finorvin)

    num = MercedesMeNumber(NUMBER_DESCRIPTIONS[0], car.finorvin, coord)
    num._mercedes_me_update()

    assert num.native_min_value == 30.0
    assert num.native_max_value == 100.0
    assert num.native_step == 1.0
    assert num.native_value == 80.0
    assert num.assumed_state is False
    assert num.extra_state_attributes["max_soc_lower_limit"] == 30
    assert num.extra_state_attributes["max_soc_upper_limit"] == 100

    await num.async_set_native_value(90.0)
    assert num.native_value == 90.0
    assert num.assumed_state is True
    assert len(executed) == 1
    assert executed[0].commandRequest.WhichOneof("command") == "charging_configure"
    assert executed[0].commandRequest.charging_configure.max_soc.value == 90

    # Stale poll does not clobber optimistic state; matching update clears assumed_state
    num._mercedes_me_update()
    assert num.native_value == 90.0
    assert num.assumed_state is True

    car.electric.maxSoc = CarAttribute("90", "VALID", 200, "90", "PERCENT")
    num._mercedes_me_update()
    assert num.native_value == 90.0
    assert num.assumed_state is False

    # Pull mode guard
    car._data_collection_mode = "pull"
    with pytest.raises(ServiceValidationError):
        await num.async_set_native_value(80.0)


@pytest.mark.anyio
async def test_number_max_soc_mbux_and_legacy_ice_filtering():
    """Verify MBUX CHARGE_PROGRAM_CONFIGURE step/floor and legacy ICE filtering."""
    client = make_client()
    mbux = _register_car(
        client,
        "TESTVIN_MBUX_NUM",
        features={"CHARGE_PROGRAM_CONFIGURE": True},
        commands=[
            {
                "commandName": "CHARGE_PROGRAM_CONFIGURE",
                "isAvailable": True,
                "parameters": [{"parameterName": "MAX_SOC", "minValue": 50, "maxValue": 100, "steps": 10}],
            }
        ],
    )
    mbux.electric.max_soc = CarAttribute(70, "VALID", 100, "70", "PERCENT")
    mbux.electric.selectedChargeProgram = CarAttribute(2, "VALID", 100, None, None)

    ice = _register_car(client, "TESTVIN_NTG_ICE", features={"AUXHEAT_START": True}, commands=[])
    assert ice.finorvin in client.cars

    coord = _make_coordinator(client, mbux.finorvin)
    coord.hass = SimpleNamespace(data={DOMAIN: {"test_entry": coord}})
    added: list = []
    await async_setup_described_platform(
        coord.hass, coord.config_entry, added.extend, NUMBER_DESCRIPTIONS, MercedesMeNumber, "number"
    )
    assert [e._vin for e in added] == ["TESTVIN_MBUX_NUM"]

    added[0]._mercedes_me_update()
    assert added[0].native_min_value == 50.0
    assert added[0].native_step == 10.0
    assert added[0].native_value == 70.0


@pytest.mark.anyio
async def test_select_charge_program_across_generations():
    """Verify charge_program options and dispatch across MB.OS, battery-only, and MBUX."""
    client = make_client()
    executed: list[client_pb2.ClientMessage] = []
    client.execute_car_command = AsyncMock(side_effect=lambda msg: executed.append(msg))

    # MB.OS X244: CHARGING_CONFIGURE + selectedChargeProgram="4"
    mbos = _register_car(
        client,
        "TESTVIN_MBOS_SEL",
        features={"CHARGING_CONFIGURE": True, "CHARGE_PROGRAM_CONFIGURE": False},
        commands=[],
    )
    mbos.electric.selectedChargeProgram = CarAttribute("4", "VALID", 100, None, None)
    coord = _make_coordinator(client, mbos.finorvin)

    sel_mbos = MercedesMeSelect(SELECT_DESCRIPTIONS[0], mbos.finorvin, coord)
    sel_mbos._mercedes_me_update()
    assert sel_mbos.options == ["default", "instant", "home", "work", "ac_dc_standard"]
    assert sel_mbos.current_option == "ac_dc_standard"
    assert sel_mbos.extra_state_attributes["program_id"] == 4

    await sel_mbos.async_select_option("home")
    assert sel_mbos.current_option == "home"
    assert sel_mbos.assumed_state is True
    assert executed[-1].commandRequest.WhichOneof("command") == "charging_configure"
    assert executed[-1].commandRequest.charging_configure.charging_program.value == 2

    # Battery-only: BATTERY_CHARGE_PROGRAM_CONFIGURE
    bat = _register_car(
        client,
        "TESTVIN_BAT_SEL",
        features={"BATTERY_CHARGE_PROGRAM_CONFIGURE": True},
        commands=[
            {
                "commandName": "BATTERY_CHARGE_PROGRAM_CONFIGURE",
                "isAvailable": True,
                "parameters": [{"parameterName": "CHARGE_PROGRAM", "allowedEnums": ["DEFAULT", "INSTANT"]}],
            }
        ],
    )
    bat.electric.selectedChargeProgram = CarAttribute(1, "VALID", 100, None, None)
    sel_bat = MercedesMeSelect(SELECT_DESCRIPTIONS[0], bat.finorvin, coord)
    sel_bat._mercedes_me_update()
    assert sel_bat.options == ["default", "instant"]
    assert sel_bat.current_option == "instant"
    with pytest.raises(ServiceValidationError):
        await sel_bat.async_select_option("home")

    # MBUX legacy: CHARGE_PROGRAM_CONFIGURE -> default, home, work only
    mbux = _register_car(
        client,
        "TESTVIN_MBUX_SEL",
        features={"CHARGE_PROGRAM_CONFIGURE": True},
        commands=[],
    )
    mbux.electric.selectedChargeProgram = CarAttribute(2, "VALID", 100, None, None)
    sel_mbux = MercedesMeSelect(SELECT_DESCRIPTIONS[0], mbux.finorvin, coord)
    sel_mbux._mercedes_me_update()
    assert sel_mbux.options == ["default", "home", "work"]
    assert sel_mbux.current_option == "home"

    # Pull mode check
    mbux._data_collection_mode = "pull"
    with pytest.raises(ServiceValidationError):
        await sel_mbux.async_select_option("work")


def test_select_respects_battery_charge_program_allowed_enums_with_active_option() -> None:
    """Select narrows options when BATTERY_CHARGE_PROGRAM_CONFIGURE restricts enums while keeping current option."""
    client = make_client()
    car = _register_car(
        client,
        "TESTVIN_BAT_ENUMS",
        features={
            "CHARGING_CONFIGURE": True,
            "BATTERY_CHARGE_PROGRAM_CONFIGURE": True,
            "CHARGE_PROGRAM_CONFIGURE": False,
        },
        commands=[
            {
                "commandName": "BATTERY_CHARGE_PROGRAM_CONFIGURE",
                "isAvailable": True,
                "parameters": [
                    {
                        "parameterName": "CHARGE_PROGRAM",
                        "allowedEnums": ["DEFAULT", "INSTANT"],
                    }
                ],
            },
        ],
    )
    _send_vep(
        client,
        car.finorvin,
        selectedChargeProgram=vehicle_events_pb2.VehicleAttributeStatus(status=0, timestamp=100, int_value=4),
    )

    coord = _make_coordinator(client, car.finorvin)
    sel = MercedesMeSelect(SELECT_DESCRIPTIONS[0], car.finorvin, coord)
    sel._mercedes_me_update()
    assert sel.options == ["default", "instant", "ac_dc_standard"]
    assert sel.current_option == "ac_dc_standard"
