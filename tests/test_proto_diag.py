"""The unknown-field scanner has to name a field the server added on its own.

When the backend fills a PushMessage oneof field our .proto does not define,
WhichOneof() returns None and MessageToJson() yields "{}" - the message is
invisible to every protobuf-level accessor, and UnknownFields() is not even
available on the upb backend. The wire scanner reads the tag off the raw bytes
instead, which is the only thing left that can say what arrived.

This happened in practice: raising the ris-sdk-version header made the backend
start sending PushMessage field 28 after every pending-command request, and
nothing but the raw dump files showed it.
"""

from __future__ import annotations

import logging

import pytest

from custom_components.mbapi2020.proto import vehicle_events_pb2
from custom_components.mbapi2020.proto_diag import (
    diagnose_proto_message,
    reset_seen_unknown_fields,
    warn_on_unknown_fields_from_bytes,
)

# PushMessage field 28, length-delimited, carrying a submessage with field 1
# set to varint 1 - captured verbatim from the EMEA and AMAP backends.
_FIELD_28 = bytes.fromhex("e201020801")


@pytest.fixture(autouse=True)
def _forget_previous_findings():
    """Each test starts with an empty dedup set."""
    reset_seen_unknown_fields()
    yield
    reset_seen_unknown_fields()


def test_an_undefined_oneof_field_is_reported_with_its_number(caplog):
    """The field number has to reach the log, not just the dump directory."""
    message = vehicle_events_pb2.PushMessage()
    message.ParseFromString(_FIELD_28)

    # precondition: protobuf itself cannot name this message
    assert message.WhichOneof("msg") is None
    assert message.ListFields() == []

    with caplog.at_level(logging.DEBUG):
        found = warn_on_unknown_fields_from_bytes(_FIELD_28, message.DESCRIPTOR, label="unhandled push message")

    assert found == 1
    assert "field=28" in caplog.text
    assert "wire=length-delimited" in caplog.text


def test_the_nested_payload_is_decoded_so_nobody_has_to_read_hex(caplog):
    """A new field's content is the interesting part; hex alone is not enough."""
    with caplog.at_level(logging.DEBUG):
        warn_on_unknown_fields_from_bytes(
            _FIELD_28, vehicle_events_pb2.PushMessage.DESCRIPTOR, label="unhandled push message"
        )

    assert "payload[2]=0801" in caplog.text
    assert "nested={1:varint=1}" in caplog.text


def test_a_repeated_finding_drops_to_debug(caplog):
    """Field 28 arrived every ~35s - the same warning must not flood the log."""
    descriptor = vehicle_events_pb2.PushMessage.DESCRIPTOR

    with caplog.at_level(logging.DEBUG):
        warn_on_unknown_fields_from_bytes(_FIELD_28, descriptor, label="unhandled push message")
        warn_on_unknown_fields_from_bytes(_FIELD_28, descriptor, label="unhandled push message")
        warn_on_unknown_fields_from_bytes(_FIELD_28, descriptor, label="unhandled push message")

    levels = [record.levelno for record in caplog.records if "field=28" in record.getMessage()]
    assert levels == [logging.WARNING, logging.DEBUG, logging.DEBUG]


def test_a_known_message_produces_no_finding(caplog):
    """The scanner must stay quiet on everything we do define."""
    message = vehicle_events_pb2.PushMessage()
    message.tracking_id = "whatever"
    raw = message.SerializeToString()

    with caplog.at_level(logging.DEBUG):
        found = warn_on_unknown_fields_from_bytes(raw, message.DESCRIPTOR, label="tracking_id")

    assert found == 0
    assert "Unknown proto field" not in caplog.text


def test_an_opaque_payload_is_not_dressed_up_as_a_submessage(caplog):
    """Only bytes that really parse as protobuf get the nested annotation."""
    # field 28, length-delimited, payload "hello" - a string, not a message
    raw = bytes([0xE2, 0x01, 0x05]) + b"hello"

    with caplog.at_level(logging.DEBUG):
        found = warn_on_unknown_fields_from_bytes(
            raw, vehicle_events_pb2.PushMessage.DESCRIPTOR, label="unhandled push message"
        )

    assert found == 1
    assert "field=28" in caplog.text
    assert "nested=" not in caplog.text


def test_diagnose_keeps_quiet_about_the_roundtrip_when_the_field_is_unknown(caplog):
    """An unknown field is preserved on reserialize, so no size mismatch is due."""
    message = vehicle_events_pb2.PushMessage()
    message.ParseFromString(_FIELD_28)

    with caplog.at_level(logging.DEBUG):
        diagnose_proto_message(message, _FIELD_28, message.DESCRIPTOR, label="unhandled push message")

    assert "field=28" in caplog.text
    assert "roundtrip size mismatch" not in caplog.text
