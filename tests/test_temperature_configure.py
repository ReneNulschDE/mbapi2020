"""The temperature command only sends zones the car accepts.

The car lists its zones as TEMPERATURE_POINTS_ZONE. A car with a single front
zone accepts FRONT_CENTER only, so the corner zones must not be sent to it.
0 is the Low setting and must be sent as such, and a zone whose temperature is
unknown must be left out instead of going out as 0, which would set it to Low.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from custom_components.mbapi2020.car import CarAttribute
from custom_components.mbapi2020.client import Client
from custom_components.mbapi2020.const import SERVICE_TEMPERATURE_CONFIGURE_SCHEMA
from custom_components.mbapi2020.proto import client_pb2
from homeassistant.exceptions import ServiceValidationError

from .conftest import make_client
from .fixtures.build import SYNTH_VIN, build_weekly_profile_status_updates, roundtrip

# Command zone numbers.
FL, FR, FC, RL, RR = 1, 2, 3, 4, 5


def _prepared_client(
    zones: list[str] | None, current: dict[str, float] | None = None
) -> tuple[Client, list[client_pb2.ClientMessage]]:
    """Return a client with one car that accepts the given zones."""
    client = make_client()
    client._process_vehicle_status_updates(roundtrip(build_weekly_profile_status_updates(active_identifier=2)))
    car = client.cars[SYNTH_VIN]
    car.features = {"TEMPERATURE_CONFIGURE": True}
    parameters = [{"parameterName": "TEMPERATURE_POINTS_TEMPERATURE"}]
    if zones is not None:
        parameters.append({"parameterName": "TEMPERATURE_POINTS_ZONE", "allowedEnums": zones})
    car.capabilities = {
        "commands": [{"commandName": "TEMPERATURE_CONFIGURE", "isAvailable": True, "parameters": parameters}]
    }
    for zone in ("frontLeft", "frontCenter", "frontRight", "rearLeft", "rearRight"):
        setattr(car.precond, f"temperature_points_{zone}", None)
    for zone, value in (current or {}).items():
        attribute = CarAttribute(value=value, retrievalstatus="VALID", timestamp=0, display_value=str(value), unit=None)
        setattr(car.precond, f"temperature_points_{zone}", attribute)

    sent: list[client_pb2.ClientMessage] = []

    async def _capture(message) -> None:
        decoded = client_pb2.ClientMessage()
        decoded.ParseFromString(message.SerializeToString())
        sent.append(decoded)

    client.execute_car_command = _capture  # type: ignore[method-assign]
    # The command writes a debug copy through hass; there is none in these tests.
    client._hass = SimpleNamespace(async_add_executor_job=lambda *args: None)
    return client, sent


def _points(client: Client, sent: list[client_pb2.ClientMessage], **zones) -> list[tuple[int, float]]:
    asyncio.run(client.temperature_configure(SYNTH_VIN, **zones))
    if not sent:
        return []
    assert len(sent) == 1
    return [(p.zone, p.temperature_in_celsius) for p in sent[0].commandRequest.temperature_configure.temperature_points]


def test_single_zone_car_gets_front_center_only() -> None:
    """A car with one front zone accepts FRONT_CENTER and nothing else."""
    client, sent = _prepared_client(["FRONT_CENTER"])
    assert _points(client, sent, front_center=21.5) == [(FC, 21.5)]


def test_corner_zone_on_single_zone_car_is_rejected() -> None:
    """Setting front_left on a car without that zone fails with the zones it has."""
    client, sent = _prepared_client(["FRONT_CENTER"])
    with pytest.raises(ServiceValidationError, match="front_center"):
        asyncio.run(client.temperature_configure(SYNTH_VIN, front_left=21))
    assert sent == []


def test_front_zones_are_sent_together() -> None:
    """The other front zone goes along with its current temperature."""
    client, sent = _prepared_client(["FRONT_LEFT", "FRONT_RIGHT"], {"frontLeft": 20.5, "frontRight": 22})
    assert _points(client, sent, front_left=23) == [(FL, 23.0), (FR, 22.0)]


def test_low_is_sent_as_zero() -> None:
    """0 is Low, not "no value"."""
    client, sent = _prepared_client(["FRONT_LEFT", "FRONT_RIGHT"], {"frontLeft": 20.5, "frontRight": 22})
    assert _points(client, sent, front_left=0) == [(FL, 0.0), (FR, 22.0)]


def test_zone_with_unknown_temperature_is_left_out() -> None:
    """Without a known value the zone would go out as 0 and switch to Low."""
    client, sent = _prepared_client(["FRONT_LEFT", "FRONT_RIGHT"], {"frontLeft": 20.5})
    assert _points(client, sent, front_left=23) == [(FL, 23.0)]


def test_rear_zones_only_when_one_is_given() -> None:
    """The rear row is sent only if the call sets a rear zone."""
    zones = ["FRONT_LEFT", "FRONT_RIGHT", "REAR_LEFT", "REAR_RIGHT"]
    current = {"frontLeft": 20, "frontRight": 20, "rearLeft": 19, "rearRight": 19}
    client, sent = _prepared_client(zones, current)
    assert _points(client, sent, front_right=21) == [(FL, 20.0), (FR, 21.0)]

    client, sent = _prepared_client(zones, current)
    assert _points(client, sent, rear_right=24) == [(FL, 20.0), (FR, 20.0), (RL, 19.0), (RR, 24.0)]


def test_without_zone_list_the_corner_zones_are_assumed() -> None:
    """Unknown capabilities keep the previous behaviour."""
    client, sent = _prepared_client(None, {"frontRight": 22})
    assert _points(client, sent, front_left=21) == [(FL, 21.0), (FR, 22.0)]


def test_no_zone_sends_nothing() -> None:
    """A call without any temperature changes nothing."""
    client, sent = _prepared_client(["FRONT_LEFT", "FRONT_RIGHT"])
    assert _points(client, sent) == []


def test_schema_accepts_front_center_and_low() -> None:
    """The service takes front_center and the Low/High values."""
    data = SERVICE_TEMPERATURE_CONFIGURE_SCHEMA({"vin": SYNTH_VIN, "front_center": "0", "front_left": "30"})
    assert data["front_center"] == 0
    assert data["front_left"] == 30
    assert data["rear_left"] is None
