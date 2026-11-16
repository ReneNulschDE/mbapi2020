"""The seat preconditioning command sends only the seats it is given.

The seats are optional wrapper fields: a seat that is left out keeps its setting
on the car, and a seat set to False has to go out as an explicit, empty wrapper.
The expected bytes are the payloads that switched the seats on a real car.
"""

from __future__ import annotations

import asyncio

import pytest
import voluptuous as vol

from custom_components.mbapi2020.client import Client
from custom_components.mbapi2020.const import SERVICE_PRECONDITIONING_CONFIGURE_SEATS_SCHEMA
from custom_components.mbapi2020.proto import client_pb2
from homeassistant.exceptions import ServiceValidationError

from .conftest import make_client
from .fixtures.build import SYNTH_VIN, build_weekly_profile_status_updates, roundtrip


def _prepared_client(available: bool = True) -> tuple[Client, list[client_pb2.ClientMessage]]:
    """Return a client with one car and the list of messages it sends."""
    client = make_client()
    client._process_vehicle_status_updates(roundtrip(build_weekly_profile_status_updates(active_identifier=2)))
    client.cars[SYNTH_VIN].features = {"ZEV_PRECONDITION_CONFIGURE_SEATS": available}

    sent: list[client_pb2.ClientMessage] = []

    async def _capture(message) -> None:
        decoded = client_pb2.ClientMessage()
        decoded.ParseFromString(message.SerializeToString())
        sent.append(decoded)

    client.execute_car_command = _capture  # type: ignore[method-assign]
    return client, sent


def _seat_bytes(client: Client, sent: list[client_pb2.ClientMessage], **seats) -> bytes:
    asyncio.run(client.preconditioning_configure_seats(SYNTH_VIN, **seats))
    assert len(sent) == 1
    assert sent[0].commandRequest.WhichOneof("command") == "zev_precondition_configure_seats"
    return sent[0].commandRequest.zev_precondition_configure_seats.SerializeToString()


@pytest.mark.parametrize(
    ("seats", "expected"),
    [
        ({"front_left": True, "front_right": False}, "2a020801 3200"),
        ({"front_left": False, "front_right": True}, "2a00 32020801"),
        ({"front_left": True, "front_right": True}, "2a020801 32020801"),
        ({"front_left": False}, "2a00"),
        ({"front_left": False, "front_right": False}, "2a00 3200"),
        ({"rear_left": True, "rear_right": False}, "3a020801 4200"),
    ],
)
def test_only_the_given_seats_are_sent(seats: dict[str, bool], expected: str) -> None:
    """Each given seat is sent, False as an empty wrapper; the others are left out."""
    client, sent = _prepared_client()
    assert _seat_bytes(client, sent, **seats) == bytes.fromhex(expected.replace(" ", ""))


def test_all_four_seats_still_work() -> None:
    """Calls that pass every seat, as before, keep working."""
    client, sent = _prepared_client()
    payload = _seat_bytes(client, sent, front_left=True, front_right=False, rear_left=True, rear_right=False)
    assert payload == bytes.fromhex("2a020801 3200 3a020801 4200".replace(" ", ""))


def test_no_seat_is_rejected() -> None:
    """A call without any seat would change nothing on the car."""
    client, sent = _prepared_client()
    with pytest.raises(ServiceValidationError):
        asyncio.run(client.preconditioning_configure_seats(SYNTH_VIN))
    assert sent == []


def test_unavailable_feature_sends_nothing() -> None:
    """Cars without the command get no message."""
    client, sent = _prepared_client(available=False)
    asyncio.run(client.preconditioning_configure_seats(SYNTH_VIN, front_left=True))
    assert sent == []


def test_schema_needs_at_least_one_seat() -> None:
    """The service accepts a single seat but not an empty call."""
    assert SERVICE_PRECONDITIONING_CONFIGURE_SEATS_SCHEMA({"vin": SYNTH_VIN, "front_left": "on"}) == {
        "vin": SYNTH_VIN,
        "front_left": True,
    }
    with pytest.raises(vol.Invalid):
        SERVICE_PRECONDITIONING_CONFIGURE_SEATS_SCHEMA({"vin": SYNTH_VIN})
