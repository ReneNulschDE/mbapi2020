"""The REST vehicleattributes endpoint answers with a VehicleStatusUpdate.

It used to be parsed as the legacy VEPUpdate. Protobuf tolerates fields it
does not know, so that never raised - every attribute landed in unknown-field
storage instead, MessageToJson() returned "{}", and the handler bailed out on
the missing VIN. The pull fallback that runs while the account is blocked was
therefore delivering nothing at all, silently.

The second thing pinned here is that the fixed path must not be taken as a
full update. The endpoint reports a handful of attributes and still sets
full_update, which refers to its own subset; handing that on as a full update
lets the attribute handlers conclude from everything that is absent.
"""

from __future__ import annotations

import json

from google.protobuf.json_format import MessageToJson

from custom_components.mbapi2020.proto import vehicle_events_pb2
from custom_components.mbapi2020.vsu_helper import normalize_vsu_car

from .conftest import make_client
from .fixtures.build import SYNTH_VIN, build_rest_vehicleattributes


def _as_json(message) -> dict:
    return json.loads(MessageToJson(message, preserving_proto_field_name=True))


def _reparse(message, message_type):
    """Serialise and re-parse as another type, the way a wrong parse happens."""
    decoded = message_type()
    decoded.ParseFromString(message.SerializeToString())
    return decoded


def test_the_response_is_unreadable_as_a_vepupdate() -> None:
    """The regression anchor: the old parse type loses the whole payload."""
    wire = build_rest_vehicleattributes()

    as_vep = _reparse(wire, vehicle_events_pb2.VEPUpdate)

    # no error, no exception - just nothing left
    assert _as_json(as_vep) == {}
    assert as_vep.ListFields() == []


def test_the_response_is_complete_as_a_vehiclestatusupdate() -> None:
    """Parsed as the type it actually is, every attribute survives."""
    wire = build_rest_vehicleattributes()

    as_vsu = _reparse(wire, vehicle_events_pb2.VehicleStatusUpdate)
    payload = _as_json(as_vsu)

    assert payload["fin_or_vin"] == SYNTH_VIN
    assert payload["soc"]["value"] == "69"
    assert payload["rangeelectric"]["value"] == "418"


def test_the_attributes_reach_the_car() -> None:
    """End to end through the handler: the values show up on the car object."""
    client = make_client()

    client._process_rest_vep_update(_reparse(build_rest_vehicleattributes(), vehicle_events_pb2.VehicleStatusUpdate))

    car = client.cars[SYNTH_VIN]
    # int64 attributes arrive as strings: that is how MessageToJson renders
    # them, and the websocket VSU path produces the same shape.
    assert car.electric.soc.value == "69"
    assert car.electric.rangeelectric.value == "418"
    assert car.data_collection_mode.value == "pull"


def test_the_response_does_not_count_as_a_full_update() -> None:
    """full_update in the message covers its own subset, not the vehicle.

    last_full_message is what the attribute handlers fall back on when an
    attribute is missing. Letting a 5-attribute response become the last full
    message would make those fallbacks read a message that never carried the
    attribute they are looking for.
    """
    client = make_client()
    wire = build_rest_vehicleattributes(full_update=True)

    client._process_rest_vep_update(_reparse(wire, vehicle_events_pb2.VehicleStatusUpdate))

    car = client.cars[SYNTH_VIN]
    assert car.last_full_message is None
    assert car.messages_received["p"] == 1
    assert car.messages_received["f"] == 0


def test_no_window_data_leaves_the_overall_status_alone() -> None:
    """Without a single window reading the overall status must not be invented.

    The fallback in _create_synthetic_window_status_overall answers "closed" at
    timestamp 0 when it finds nothing, and this endpoint carries no window
    attributes at all - so it would overwrite what the websocket delivered with
    a fabricated value.
    """
    client = make_client()
    wire = build_rest_vehicleattributes()

    client._process_rest_vep_update(_reparse(wire, vehicle_events_pb2.VehicleStatusUpdate))

    # The attribute is never created, so it is not on the object at all - which
    # is exactly what leaving it alone looks like.
    assert not hasattr(client.cars[SYNTH_VIN].windows, "windowStatusOverall")


def test_real_window_data_still_produces_an_overall_status() -> None:
    """The guard must not disable the feature where it has something to work with."""
    payload = normalize_vsu_car(
        _as_json(
            _reparse(build_rest_vehicleattributes(with_window_status=True), vehicle_events_pb2.VehicleStatusUpdate)
        )
    )
    client = make_client()

    client._create_synthetic_window_status_overall(payload, SYNTH_VIN)

    assert "windowStatusOverall" in payload["attributes"]
    assert payload["attributes"]["windowStatusOverall"]["bool_value"] is True


def test_the_guard_keeps_quiet_without_window_data() -> None:
    """Same helper, no window attributes: nothing is added."""
    payload = normalize_vsu_car(
        _as_json(_reparse(build_rest_vehicleattributes(), vehicle_events_pb2.VehicleStatusUpdate))
    )
    client = make_client()

    client._create_synthetic_window_status_overall(payload, SYNTH_VIN)

    assert "windowStatusOverall" not in payload["attributes"]


def test_an_excluded_car_is_skipped() -> None:
    """The VIN filter has to apply to the pull path as well."""
    client = make_client(excluded_cars=[SYNTH_VIN])
    wire = build_rest_vehicleattributes()

    client._process_rest_vep_update(_reparse(wire, vehicle_events_pb2.VehicleStatusUpdate))

    assert SYNTH_VIN not in client.cars
