"""Detect gaps in the local .proto definitions against incoming wire payloads."""

from __future__ import annotations

from collections.abc import Iterator
import logging
import os

from google.protobuf import descriptor_pb2

LOGGER = logging.getLogger(__name__)

_WIRE_TYPES = {0: "varint", 1: "fixed64", 2: "length-delimited", 5: "fixed32"}


def _probe_unknown_fields_api() -> bool:
    """Verify that UnknownFields() is actually callable on a real message.

    The C++/upb backend protobuf >= 4 ships by default removed UnknownFields().
    Setting PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python before HA starts is
    *meant* to restore it but doesn't always — newer protobuf releases ship
    without the pure-Python module at all. So we probe the actual API instead
    of trusting the env var.
    """
    probe = descriptor_pb2.FileDescriptorProto()
    try:
        probe.UnknownFields()  # raises on upb, returns empty set on pure-python
    except (AttributeError, NotImplementedError):
        return False
    except Exception as err:  # noqa: BLE001 - diagnostic must not crash the pipeline
        LOGGER.debug("UnknownFields() probe raised %s; assuming unavailable", err)
        return False
    return True


_DEEP_SCAN_ENABLED = _probe_unknown_fields_api()

LOGGER.debug(
    "proto_diag startup: PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=%s, UnknownFields() callable=%s",
    os.environ.get("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "<unset>"),
    _DEEP_SCAN_ENABLED,
)


def deep_scan_enabled() -> bool:
    """Return True if the per-field unknown-field walker can run."""
    return _DEEP_SCAN_ENABLED


def warn_on_roundtrip_mismatch(message, raw_bytes: bytes, label: str) -> None:
    """Compare reserialized size against the raw wire bytes.

    A mismatch implies the parser dropped information — typically because a
    field is missing from the local .proto, or its type does not match the
    wire type the server uses. Always runs; no backend requirement.
    """
    try:
        rebuilt_len = len(message.SerializeToString())
    except Exception as err:  # noqa: BLE001 - diagnostic must not crash the pipeline
        LOGGER.debug("Roundtrip serialize failed for %s: %s", label, err)
        return

    raw_len = len(raw_bytes)
    if rebuilt_len != raw_len:
        LOGGER.warning(
            "Proto roundtrip size mismatch for %s: raw=%d reserialized=%d delta=%d — "
            "local .proto definition likely incomplete",
            label,
            raw_len,
            rebuilt_len,
            rebuilt_len - raw_len,
        )


def _iter_unknown_fields(message, path: str) -> Iterator[tuple[str, int, str]]:
    """Walk message recursively, yielding (path, field_number, wire_type)."""
    here = path or message.DESCRIPTOR.full_name

    try:
        unknown = message.UnknownFields()
    except (AttributeError, NotImplementedError):
        # upb / C++ backend — silently skip; warn_on_unknown_fields() already
        # gates on deep_scan_enabled() so we won't get here in practice.
        return

    for field in unknown:
        yield (
            here,
            field.field_number,
            _WIRE_TYPES.get(field.wire_type, str(field.wire_type)),
        )

    for descriptor, value in message.ListFields():
        if descriptor.type != descriptor.TYPE_MESSAGE:
            continue
        sub = f"{here}.{descriptor.name}"
        if descriptor.label == descriptor.LABEL_REPEATED:
            mt = descriptor.message_type
            if mt and mt.GetOptions().map_entry:
                for key, val in value.items():
                    yield from _iter_unknown_fields(val, f"{sub}[{key!r}]")
            else:
                for i, item in enumerate(value):
                    yield from _iter_unknown_fields(item, f"{sub}[{i}]")
        else:
            yield from _iter_unknown_fields(value, sub)


def warn_on_unknown_fields(message, *, label: str) -> None:
    """Log one warning per unknown field. No-op unless deep scan is enabled."""
    if not _DEEP_SCAN_ENABLED:
        return
    for path, num, wire in _iter_unknown_fields(message, ""):
        LOGGER.warning(
            "Unknown proto field in %s: %s field=%d wire=%s — .proto definition incomplete",
            label,
            path,
            num,
            wire,
        )


# --- Wire-format scanner -------------------------------------------------
#
# Backend-independent fallback that walks the raw wire bytes and reports any
# tag whose field number is not in the local descriptor. Works on upb, pure
# Python, and C++ backends because it never calls a protobuf API beyond
# DESCRIPTOR introspection.


def _decode_varint(buf: bytes, pos: int) -> tuple[int, int]:
    """Decode a protobuf varint starting at ``pos``; return (value, new_pos)."""
    result = 0
    shift = 0
    while pos < len(buf):
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return result, pos
        shift += 7
        if shift >= 64:
            raise ValueError("varint too long")
    raise ValueError("varint truncated")


def _iter_unknown_fields_wire(raw: bytes, descriptor, path: str) -> Iterator[tuple[str, int, str, bytes | int | None]]:
    """Walk ``raw`` bytes against ``descriptor``; yield (path, field_number, wire_type, sample)."""
    pos = 0
    end = len(raw)
    fields_by_number = {f.number: f for f in descriptor.fields} if descriptor else {}

    while pos < end:
        try:
            tag, pos = _decode_varint(raw, pos)
        except ValueError:
            return
        field_number = tag >> 3
        wire_type = tag & 0x7

        payload: bytes | None = None
        scalar_sample: int | None = None
        if wire_type == 0:  # varint
            try:
                scalar_sample, pos = _decode_varint(raw, pos)
            except ValueError:
                return
        elif wire_type == 1:  # fixed64
            pos += 8
        elif wire_type == 2:  # length-delimited
            try:
                length, pos = _decode_varint(raw, pos)
            except ValueError:
                return
            payload = raw[pos : pos + length]
            pos += length
        elif wire_type == 5:  # fixed32
            pos += 4
        else:
            # groups (3/4) are obsolete in proto3 — bail out instead of guessing
            return

        field = fields_by_number.get(field_number)
        if field is None:
            sample = payload if payload is not None else scalar_sample
            yield (
                path or descriptor.full_name,
                field_number,
                _WIRE_TYPES.get(wire_type, str(wire_type)),
                sample,
            )
            continue

        if (
            wire_type == 2
            and payload is not None
            and field.type == field.TYPE_MESSAGE
            and field.message_type is not None
        ):
            sub_path = f"{path}.{field.name}" if path else f"{descriptor.full_name}.{field.name}"
            yield from _iter_unknown_fields_wire(payload, field.message_type, sub_path)


def _format_sample(sample: bytes | int | None) -> str:
    if sample is None:
        return ""
    if isinstance(sample, int):
        return f" value={sample}"
    # length-delimited — show hex (limited to a reasonable length so logs stay readable)
    truncated = sample[:64]
    suffix = "…" if len(sample) > 64 else ""
    return f" payload[{len(sample)}]={truncated.hex()}{suffix}"


def warn_on_unknown_fields_from_bytes(raw: bytes, descriptor, *, label: str) -> int:
    """Backend-independent unknown-field scanner; returns number of unknowns found."""
    found = 0
    try:
        for path, num, wire, sample in _iter_unknown_fields_wire(raw, descriptor, ""):
            LOGGER.warning(
                "Unknown proto field in %s: %s field=%d wire=%s%s — .proto definition incomplete",
                label,
                path,
                num,
                wire,
                _format_sample(sample),
            )
            found += 1
    except Exception as err:  # noqa: BLE001 - diagnostic must not crash the pipeline
        LOGGER.debug("Wire-format scan failed for %s: %s", label, err)
    return found


def diagnose_proto_message(message, raw_bytes: bytes, descriptor, *, label: str) -> None:
    """Run scanner + roundtrip together; roundtrip stays DEBUG when scanner is clean.

    Rationale: a roundtrip size mismatch without an unknown-field finding is
    almost always proto3 default-omission (server sends ``value: 0`` explicitly,
    re-serialization drops it). That's cosmetic — surfacing it as WARNING just
    adds noise once the descriptor is actually complete.
    """
    unknowns = warn_on_unknown_fields_from_bytes(raw_bytes, descriptor, label=label)

    try:
        rebuilt_len = len(message.SerializeToString())
    except Exception as err:  # noqa: BLE001 - diagnostic must not crash the pipeline
        LOGGER.debug("Roundtrip serialize failed for %s: %s", label, err)
        return

    raw_len = len(raw_bytes)
    if rebuilt_len == raw_len:
        return

    level = logging.WARNING if unknowns else logging.DEBUG
    cause = "local .proto definition likely incomplete" if unknowns else "likely proto3 default-omission"
    LOGGER.log(
        level,
        "Proto roundtrip size mismatch for %s: raw=%d reserialized=%d delta=%d — %s",
        label,
        raw_len,
        rebuilt_len,
        rebuilt_len - raw_len,
        cause,
    )


def log_diagnostic_status() -> None:
    """Log once at integration startup so the user knows which mode is active."""
    if _DEEP_SCAN_ENABLED:
        LOGGER.info("Proto diagnostic deep scan enabled (pure-Python protobuf backend)")
    else:
        LOGGER.debug(
            "Proto diagnostic deep scan disabled — set "
            "PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python before HA start to enable "
            "per-field unknown-field detection"
        )
