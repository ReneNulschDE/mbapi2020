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

# 2026-10-13T12:52:24Z, a fixed point in time so the expected sensor state can
# be written out literally.
_CHARGE_END_EPOCH_SECONDS = 1791895944


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
    active_identifier: int | None = 1,
) -> vehicle_events_pb2.PushMessage:
    """Build a VSU message carrying a weekly departure profile.

    The two entries mirror the two vehicle generations that appear in
    practice: one reports weekdays, an action list and a schedule type, the
    other only an identifier and a time. The second entry leaves hour and
    active at their proto3 defaults on purpose, because the backend then drops
    both keys and the parser has to default them itself.

    active_identifier picks which entry carries the active flag, so a test can
    activate the second one - the identifier of the active entry must not be
    read off the position in the list. None activates neither.
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
    profile.current_number_of_time_profiles = 2

    full = profile.time_profiles.add()
    full.id = 1
    full.hour = 20
    full.minute = 50
    full.days.append(_WEEKDAY_TUESDAY)
    full.application_identifier = 1
    full.schedule_type = _SCHEDULE_TYPE_RECURRING
    action = full.action_list.add()
    action.charging = True
    action.precond = True

    sparse = profile.time_profiles.add()
    sparse.id = 2
    sparse.minute = 5  # hour stays 0 and is dropped from the JSON
    sparse.application_identifier = 1

    # Set last, so an entry that is not activated keeps the proto3 default and
    # the backend drops its "active" key entirely - as the vehicles do.
    for entry in profile.time_profiles:
        if entry.id == active_identifier:
            entry.active = True
    return message


def build_smart_charging_status_updates(
    vin: str = SYNTH_VIN,
    *,
    sequence_number: int = 5,
    location_name: str | None = "Home",
    charging_station_name: str | None = "Garage Wallbox",
    charging_strategy: str | None = "immediate",
    errors: tuple[tuple[str, str], ...] | None = (("UNAVAILABLE_DIRECT_CHARGING_MODE", "MINOR_ERROR"),),
) -> vehicle_events_pb2.PushMessage:
    """Build a VSU message carrying the two smart charging objects.

    Fields 276 and 277 only reach vehicles whose charging a provider manages,
    so none of the test vehicles can produce them.

    A None for one of the three strings leaves it at its proto3 default, which
    the backend then drops from the payload - a vehicle that names no station
    looks exactly like this. errors=() keeps the object but reports nothing,
    errors=None leaves the object out altogether.
    """
    message = vehicle_events_pb2.PushMessage()
    message.vehicle_status_updates.sequence_number = sequence_number

    update = message.vehicle_status_updates.vehicle_status_updates[vin]
    update.fin_or_vin = vin
    update.full_update = True

    info = update.smart_charging_information
    if location_name is not None:
        info.value.location_name = location_name
    if charging_station_name is not None:
        info.value.charging_station_name = charging_station_name
    if charging_strategy is not None:
        info.value.charging_strategy = charging_strategy
    info.metadata.timestamp.FromJsonString("2026-10-21T08:30:00Z")

    if errors is not None:
        wrapper = update.smart_charging_error
        wrapper.metadata.timestamp.FromJsonString("2026-10-21T08:30:00Z")
        for code, severity in errors:
            entry = wrapper.value.errors.add()
            entry.code = entry.Code.Value(code)
            entry.severity = entry.Severity.Value(severity)

    return message


def roundtrip(message: vehicle_events_pb2.PushMessage) -> vehicle_events_pb2.PushMessage:
    """Serialise and re-parse, the way websocket.py does on a live frame.

    Keeping this in the helper means each test exercises the real
    encode/decode boundary rather than a hand-built object that skipped it.
    """
    decoded = vehicle_events_pb2.PushMessage()
    decoded.ParseFromString(message.SerializeToString())
    return decoded


def build_charging_prediction_status_updates(
    vin: str = SYNTH_VIN,
    *,
    sequence_number: int = 4,
    full_update: bool = False,
    predicted_end_time_seconds: int | None = _CHARGE_END_EPOCH_SECONDS,
    predicted_range: int = 425,
    with_prediction: bool = True,
    endofchargetime_minutes: int | None = None,
) -> vehicle_events_pb2.PushMessage:
    """Build a VSU message carrying the charge end time of a CLA 2025 or newer car.

    Those cars have no endofchargetime attribute; the charge end time is a
    Timestamp inside charging_prediction_max_soc. Because it is a message
    field it has explicit presence, so the three states a test needs are all
    distinguishable on the wire:

    - with_prediction and a predicted_end_time_seconds: the car is charging
      and names the time it expects to finish.
    - with_prediction and predicted_end_time_seconds None: the attribute
      arrives carrying only the range, which is what the car sends the moment
      charging ends.
    - with_prediction False: the attribute is not in the message at all, as in
      the great majority of partial updates.

    endofchargetime_minutes adds the legacy attribute next to it, the way the
    older models report both. It is a wall clock time in minutes after
    midnight, which is how the older cars express it.
    """
    message = vehicle_events_pb2.PushMessage()
    message.vehicle_status_updates.sequence_number = sequence_number

    update = message.vehicle_status_updates.vehicle_status_updates[vin]
    update.fin_or_vin = vin
    update.full_update = full_update

    # An unrelated attribute, so the message is never attribute-empty: the
    # parser discards those before any handler runs, and no real update looks
    # like that.
    update.rangeelectric.value = 263

    if with_prediction:
        prediction = update.charging_prediction_max_soc.value
        prediction.predicted_electrical_energy_range = predicted_range
        if predicted_end_time_seconds is not None:
            prediction.predicted_end_time.seconds = predicted_end_time_seconds

    if endofchargetime_minutes is not None:
        update.endofchargetime.value = endofchargetime_minutes

    return message


def build_rest_vehicleattributes(
    vin: str = SYNTH_VIN,
    *,
    full_update: bool = True,
    soc: int = 69,
    electric_range: int = 418,
    position_lat: float = 48.1,
    with_window_status: bool = False,
) -> vehicle_events_pb2.VehicleStatusUpdate:
    """Build what /v1/vehicle/{vin}/vehicleattributes answers with.

    A bare VehicleStatusUpdate, not wrapped in a PushMessage and not a
    VEPUpdate: one car, the typed VSU attribute shape, and a narrow set of
    attributes - position, ranges, soc, tank levels. The endpoint sets
    full_update even though it reports nothing about doors, windows, locks or
    charging, which is why the caller has to treat it as a partial update.

    with_window_status adds the individual window attributes, so a test can
    tell the two branches of the synthetic windowStatusOverall apart.
    """
    update = vehicle_events_pb2.VehicleStatusUpdate()
    update.fin_or_vin = vin
    update.full_update = full_update

    update.soc.value = soc
    update.soc.display_value = str(soc)
    update.rangeelectric.value = electric_range
    update.position_lat.value = position_lat
    update.tanklevelpercent.value = 73

    if with_window_status:
        update.windowstatusfrontleft.value = 2
        update.windowstatusfrontright.value = 2
        update.windowstatusrearleft.value = 2
        update.windowstatusrearright.value = 2

    return update
