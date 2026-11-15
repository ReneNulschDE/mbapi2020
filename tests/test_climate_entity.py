"""Offline tests for the native Climate (preclimate) platform."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.mbapi2020.car import Car, CarAttribute, Electric, Precond
from custom_components.mbapi2020.climate import CLIMATE_DESCRIPTIONS, MercedesMeClimate
from custom_components.mbapi2020.const import MERCEDESME_COMPONENTS
from custom_components.mbapi2020.proto import client_pb2
from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACAction, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, Platform, UnitOfTemperature
from homeassistant.exceptions import ServiceValidationError
from tests.conftest import make_client


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


def test_climate_platform_is_registered():
    """Verify Platform.CLIMATE is registered in MERCEDESME_COMPONENTS."""
    assert Platform.CLIMATE in MERCEDESME_COMPONENTS


@pytest.mark.anyio
async def test_climate_preclimate_zev_active_zones_and_temperature_configure():
    """Verify climate.preclimate handles active zones, 0.5 C step, Fahrenheit, and ZEV mode."""
    client = make_client()
    executed: list[client_pb2.ClientMessage] = []
    client.execute_car_command = AsyncMock(side_effect=lambda msg: executed.append(msg))

    car = _register_car(
        client,
        "TESTVIN_CLIMATE_ZEV",
        features={
            "ZEV_PRECONDITIONING_START": True,
            "ZEV_PRECONDITIONING_STOP": True,
            "TEMPERATURE_CONFIGURE": True,
        },
        commands=[
            {
                "commandName": "TEMPERATURE_CONFIGURE",
                "isAvailable": True,
                "parameters": [
                    {"parameterName": "TEMPERATURE_POINTS_ZONE", "allowedEnums": ["FRONT_LEFT", "FRONT_RIGHT"]},
                    {"parameterName": "TEMPERATURE_POINTS_TEMPERATURE", "minValue": 16, "maxValue": 28, "steps": 0.5},
                ],
            }
        ],
    )
    car.precond = Precond()
    car.precond.temperature_points_frontLeft = CarAttribute(20.0, "VALID", 100, "20.0", "CELSIUS")
    car.precond.temperature_points_frontLeftActive = CarAttribute(False, "VALID", 100, None, None)
    car.precond.temperature_points_frontRight = CarAttribute(22.5, "VALID", 100, "22.5", "CELSIUS")
    car.precond.temperature_points_frontRightActive = CarAttribute(True, "VALID", 100, None, None)
    car.precond.precondStatus = CarAttribute(False, "VALID", 100, "False", None)
    car.precond.precondOperabilityAvailable = CarAttribute(True, "VALID", 100, "True", None)
    car.precond.precondOperabilityState = CarAttribute(0, "VALID", 100, None, None)
    car.precond.precondOperatingMode = CarAttribute("0", "VALID", 100, None, None)
    car.precond.precondError = CarAttribute("0", "VALID", 100, None, None)

    coord = _make_coordinator(client, car.finorvin)
    clim = MercedesMeClimate(CLIMATE_DESCRIPTIONS[0], car.finorvin, coord)
    clim._mercedes_me_update()

    assert clim.hvac_modes == [HVACMode.OFF, HVACMode.HEAT_COOL]
    assert clim.native_temperature_unit == UnitOfTemperature.CELSIUS
    if hasattr(ClimateEntity, "_attr_native_temperature_unit"):
        assert "_attr_temperature_unit" not in MercedesMeClimate.__dict__
    assert clim.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE
    assert clim.min_temp == 16.0
    assert clim.max_temp == 28.0
    assert clim.target_temperature_step == 0.5
    # Prefers active front_right zone (22.5) over inactive front_left (20.0)
    assert clim.native_target_temperature == 22.5
    assert clim.hvac_mode == HVACMode.OFF
    assert clim.hvac_action == HVACAction.OFF
    assert clim.extra_state_attributes["operability_available"] is True
    assert clim.extra_state_attributes["front_right_active"] is True

    # Set fractional Celsius temperature
    await clim.async_set_temperature(**{ATTR_TEMPERATURE: 21.5})
    assert clim.native_target_temperature == 21.5
    assert clim.assumed_state is True
    assert executed[-1].commandRequest.WhichOneof("command") == "temperature_configure"
    points = executed[-1].commandRequest.temperature_configure.temperature_points
    assert [(p.zone, p.temperature_in_celsius) for p in points] == [(1, 21.5), (2, 21.5)]

    # Verify falsy-zero fix in client.temperature_configure directly
    await client.temperature_configure(car.finorvin, front_left=0)
    zero_points = executed[-1].commandRequest.temperature_configure.temperature_points
    assert zero_points[0].temperature_in_celsius == 0.0

    # Turn preclimate on
    await clim.async_turn_on()
    assert clim.hvac_mode == HVACMode.HEAT_COOL
    assert clim.hvac_action == HVACAction.PREHEATING
    assert executed[-1].commandRequest.WhichOneof("command") == "zev_preconditioning_start"

    # Fahrenheit reading normalizes cleanly
    car.precond.temperature_points_frontRight = CarAttribute(72.0, "VALID", 200, "72", "FAHRENHEIT")
    clim._expected_temperature = None
    clim._mercedes_me_update()
    assert clim.native_target_temperature == 22.0


@pytest.mark.anyio
async def test_climate_preclimate_ntg55_auxheat_only_and_pull_guard():
    """Verify NTG5.5 auxheat-only exposes HEAT without TARGET_TEMPERATURE and checks pull mode."""
    client = make_client()
    executed: list[client_pb2.ClientMessage] = []
    client.execute_car_command = AsyncMock(side_effect=lambda msg: executed.append(msg))

    ntg = _register_car(client, "TESTVIN_NTG_CLIM", features={"auxHeat": True})
    ntg.auxheat = SimpleNamespace(auxheatActive=CarAttribute(True, "VALID", 100, None, None))
    coord = _make_coordinator(client, ntg.finorvin)

    clim = MercedesMeClimate(CLIMATE_DESCRIPTIONS[0], ntg.finorvin, coord)
    clim._mercedes_me_update()

    assert clim.hvac_modes == [HVACMode.OFF, HVACMode.HEAT]
    assert not (clim.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE)
    assert clim.hvac_mode == HVACMode.HEAT
    assert clim.hvac_action == HVACAction.HEATING

    await clim.async_turn_off()
    assert executed[-1].commandRequest.WhichOneof("command") == "auxheat_stop"

    # Verify hybrid supports both HEAT_COOL and HEAT and dispatches auxheat_stop when leaving HEAT
    hybrid = _register_car(
        client,
        "TESTVIN_HYBRID_CLIM",
        features={"ZEV_PRECONDITIONING_START": True, "AUXHEAT_START": True},
    )
    hybrid.auxheat = SimpleNamespace(auxheatActive=CarAttribute(True, "VALID", 100, None, None))
    clim_hyb = MercedesMeClimate(CLIMATE_DESCRIPTIONS[0], hybrid.finorvin, coord)
    clim_hyb._mercedes_me_update()
    assert clim_hyb.hvac_modes == [HVACMode.OFF, HVACMode.HEAT_COOL, HVACMode.HEAT]
    assert clim_hyb.hvac_mode == HVACMode.HEAT
    await clim_hyb.async_turn_off()
    assert executed[-1].commandRequest.WhichOneof("command") == "auxheat_stop"

    ntg._data_collection_mode = "pull"
    with pytest.raises(ServiceValidationError):
        await clim.async_turn_on()


def test_climate_expands_max_temp_on_hi_preset() -> None:
    """Climate expands max_temp to 30.0 when vehicle reports 30.0 C (HI preset)."""
    client = make_client()
    car = _register_car(
        client,
        "TESTVIN_HI_CLIMATE",
        features={
            "ZEV_PRECONDITIONING_START": True,
            "ZEV_PRECONDITIONING_STOP": True,
            "TEMPERATURE_CONFIGURE": True,
        },
        commands=[
            {
                "commandName": "TEMPERATURE_CONFIGURE",
                "isAvailable": True,
                "parameters": [
                    {
                        "parameterName": "TEMPERATURE_POINTS_TEMPERATURE",
                        "minValue": 16.0,
                        "maxValue": 28.0,
                        "steps": 0.5,
                    },
                    {
                        "parameterName": "TEMPERATURE_POINTS_ZONE",
                        "allowedEnums": ["FRONT_LEFT", "FRONT_RIGHT"],
                    },
                ],
            },
        ],
    )
    car.precond = Precond()
    car.precond.temperature_points_frontLeft = CarAttribute(30.0, "VALID", 100, "30.0", "CELSIUS")
    car.precond.temperature_points_frontLeftActive = CarAttribute(True, "VALID", 100, None, None)

    coord = _make_coordinator(client, car.finorvin)
    clim = MercedesMeClimate(CLIMATE_DESCRIPTIONS[0], car.finorvin, coord)
    clim._mercedes_me_update()
    assert clim.native_target_temperature == 30.0
    assert clim.min_temp == 16.0
    assert clim.max_temp == 30.0
    assert clim.extra_state_attributes["temperature_preset"] == "high"
