"""Synthetic protobuf builders for the offline parser tests.

Every message here is constructed in code from fabricated values. No
file in this package is a capture, and no builder reads from disk or the
network, so a test run produces the same message on every machine and no
real vehicle data is involved.

Two envelope shapes appear in the integration, and they are not the same:

VEP - ``PushMessage.vepUpdates`` carries a map of VIN -> ``VEPUpdate``,
and each ``VEPUpdate`` holds a map of attribute name ->
``VehicleAttributeStatus``. Attribute units are per-attribute enums
(distance_unit, speed_unit, ...).

VSU - ``PushMessage.vehicle_status_updates`` carries a map of VIN ->
``VehicleStatusUpdate``, whose attributes are flat named fields rather
than a map, each a typed wrapper such as ``DoubleDistanceAttribute`` with
``value``/``unit``/``display_value``.
"""

from __future__ import annotations

from custom_components.mbapi2020.proto import vehicle_events_pb2

# Deliberately obvious fake identifiers. W1NKM5BB6VU000000 keeps the
# correct 17-character VIN shape so any length validation still passes,
# and the plate is not a legal plate format. These live here rather than
# in conftest so the fixture builders do not import from the test root.
SYNTH_VIN = "W1NKM5BB6VU000000"
SYNTH_PLATE = "SYNTH-TEST-000"
SYNTH_FIN = "SYNTHFIN000000000"

# DistanceUnitH, from the generated descriptor. Spelled numerically
# because the enum lives in a transitive proto module and importing it by
# name is brittle across protobuf regeneration.
_DISTANCE_KILOMETERS = 0
_DISTANCE_MILES = 2

_EMIT_TIMESTAMP_MS = 1758000000000  # fixed, so messages are byte-stable

# WeeklyProfile.TimeProfile.Weekday and .ScheduleType, spelled numerically for
# the same reason as the distance units above: both are nested enums, and
# addressing them by name depends on the nesting path surviving regeneration.
_WEEKDAY_TUESDAY = 1
_SCHEDULE_TYPE_RECURRING = 1


def build_vep_updates(
    vin: str = SYNTH_VIN,
    *,
    sequence_number: int = 1,
    full_update: bool = True,
    odometer_display: str = "57500",
    odometer_value: float = 57500.0,
    odometer_unit: int = _DISTANCE_MILES,
) -> vehicle_events_pb2.PushMessage:
    """Build a vepUpdates message for one car, carrying an odometer attribute."""
    message = vehicle_events_pb2.PushMessage()
    message.vepUpdates.sequence_number = sequence_number

    update = message.vepUpdates.updates[vin]
    update.vin = vin
    update.full_update = full_update
    update.emit_timestamp_in_ms = _EMIT_TIMESTAMP_MS

    status = update.attributes["odometer"]
    status.display_value = odometer_display
    status.double_value = odometer_value
    status.distance_unit = odometer_unit
    return message


def build_vehicle_status_updates(
    vin: str = SYNTH_VIN,
    *,
    sequence_number: int = 2,
    overall_range_value: float = 12000.0,
    overall_range_display: str = "12000",
    overall_range_unit: int = _DISTANCE_KILOMETERS,
    electric_range: int = 480,
    tire_pressure_front_left: float = 2.5,
) -> vehicle_events_pb2.PushMessage:
    """Build a vehicle_status_updates message for one car, as VSU carries them."""
    message = vehicle_events_pb2.PushMessage()
    message.vehicle_status_updates.sequence_number = sequence_number

    update = message.vehicle_status_updates.vehicle_status_updates[vin]
    update.fin_or_vin = vin

    overall = update.overall_range
    overall.value = overall_range_value
    overall.display_value = overall_range_display
    overall.unit = overall_range_unit

    update.rangeelectric.value = electric_range
    update.tirepressure_front_left.value = tire_pressure_front_left
    return message


def build_weekly_profile_status_updates(
    vin: str = SYNTH_VIN,
    *,
    sequence_number: int = 3,
    reported_profile_count: int | None = 2,
) -> vehicle_events_pb2.PushMessage:
    """Build a VSU message carrying a weekly departure profile.

    The two entries mirror the two vehicle generations that appear in
    practice: one reports weekdays, an action list and a schedule type, the
    other only an identifier and a time. The second entry leaves hour and
    active at their proto3 defaults on purpose, because the backend then drops
    both keys and the parser has to default them itself.

    reported_profile_count set to None leaves current_number_of_time_profiles
    at zero, which is how a vehicle that reports no count at all arrives.
    """
    message = vehicle_events_pb2.PushMessage()
    message.vehicle_status_updates.sequence_number = sequence_number

    update = message.vehicle_status_updates.vehicle_status_updates[vin]
    update.fin_or_vin = vin
    update.full_update = True

    profile = update.weekly_profile.value
    profile.single_time_profile_entries_activatable = True
    profile.max_number_of_weekly_time_profile_slots = 112
    profile.max_number_of_time_profiles = 16
    profile.max_number_of_time_profiles_user = 10
    profile.current_number_of_time_profile_slots = 2
    if reported_profile_count is not None:
        profile.current_number_of_time_profiles = reported_profile_count

    full = profile.time_profiles.add()
    full.id = 1
    full.hour = 20
    full.minute = 50
    full.days.append(_WEEKDAY_TUESDAY)
    full.active = True
    full.application_identifier = 1
    full.schedule_type = _SCHEDULE_TYPE_RECURRING
    action = full.action_list.add()
    action.charging = True
    action.precond = True

    sparse = profile.time_profiles.add()
    sparse.id = 2
    sparse.minute = 5  # hour stays 0 and is dropped from the JSON
    sparse.application_identifier = 1
    return message


def roundtrip(message: vehicle_events_pb2.PushMessage) -> vehicle_events_pb2.PushMessage:
    """Serialise and re-parse, the way websocket.py does on a live frame.

    Keeping this in the helper means each test exercises the real
    encode/decode boundary rather than a hand-built object that skipped it.
    """
    decoded = vehicle_events_pb2.PushMessage()
    decoded.ParseFromString(message.SerializeToString())
    return decoded
