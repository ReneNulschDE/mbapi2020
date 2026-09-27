"""The fixture builders produce messages the parsers actually accept.

These are the baseline tests: if they fail, the synthetic data is wrong
and any regression result below is meaningless. They also pin the two
envelope shapes, since VEP and VSU do not share a structure.
"""

from __future__ import annotations

from google.protobuf.json_format import MessageToJson

from custom_components.mbapi2020.proto import vehicle_events_pb2

from .conftest import make_client
from .fixtures.build import SYNTH_VIN, build_vehicle_status_updates, build_vep_updates, roundtrip


def test_vep_fixture_survives_binary_roundtrip() -> None:
    """A built message re-parses as the same oneof kind, through the real codec."""
    message = roundtrip(build_vep_updates())

    assert message.WhichOneof("msg") == "vepUpdates"
    assert SYNTH_VIN in message.vepUpdates.updates

    odometer = message.vepUpdates.updates[SYNTH_VIN].attributes["odometer"]
    assert odometer.display_value == "57500"
    assert odometer.double_value == 57500.0


def test_vep_fixture_is_serialisable_to_json() -> None:
    """The same message converts to JSON, as write_debug_json_output does."""
    payload = MessageToJson(build_vep_updates(), preserving_proto_field_name=True)

    assert SYNTH_VIN in payload
    assert "odometer" in payload


def test_vep_updates_parser_registers_the_car() -> None:
    """The VEP parser builds a Car and records its attributes."""
    client = make_client()

    client._process_vep_updates(build_vep_updates())

    assert SYNTH_VIN in client.cars
    car = client.cars[SYNTH_VIN]
    assert car.odometer is not None
    assert car.odometer.name == "Odometer"


def test_vehicle_status_updates_fixture_survives_roundtrip() -> None:
    """The VSU envelope is a different shape, and it round-trips too."""
    message = roundtrip(build_vehicle_status_updates())

    assert message.WhichOneof("msg") == "vehicle_status_updates"
    update = message.vehicle_status_updates.vehicle_status_updates[SYNTH_VIN]
    assert update.overall_range.value == 12000.0
    assert update.overall_range.display_value == "12000"
    assert update.rangeelectric.value == 480


def test_vehicle_status_updates_parser_registers_the_car() -> None:
    """The VSU parser builds a Car and records its grouped attributes.

    VSU groups values differently from VEP: the payload is flat named
    fields, and _build_car folds them into Car groups such as `tires`.
    """
    client = make_client()

    client._process_vehicle_status_updates(build_vehicle_status_updates())

    assert SYNTH_VIN in client.cars
    car = client.cars[SYNTH_VIN]
    assert car.tires is not None
    assert car.tires.tirepressureFrontLeft is not None


def test_fixture_car_uses_synthetic_identifiers_only() -> None:
    """Guard: the fixtures must never carry a real VIN, plate or coordinates."""
    message = build_vep_updates()
    payload = MessageToJson(message, preserving_proto_field_name=True)

    assert SYNTH_VIN.startswith("W1NKM5BB6VU")
    assert SYNTH_VIN.endswith("000000")
    # No coordinate fields are populated by any builder.
    for forbidden in ("positionLat", "positionLong", "latitude", "longitude"):
        assert forbidden not in payload


def test_push_message_oneof_kinds_are_distinct() -> None:
    """The two builders select different oneof arms, so they are not aliases."""
    vep = build_vep_updates()
    vsu = build_vehicle_status_updates()

    assert vep.WhichOneof("msg") != vsu.WhichOneof("msg")
    assert isinstance(vep, vehicle_events_pb2.PushMessage)
