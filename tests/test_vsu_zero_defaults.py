"""Tests for VSU proto3 default 0/False synthesis and binary_sensor None handling."""

from __future__ import annotations

from types import SimpleNamespace

from google.protobuf.json_format import MessageToDict

from custom_components.mbapi2020.binary_sensor import MercedesMEBinarySensor
from custom_components.mbapi2020.car import BinarySensors as CarBinarySensors, Car, CarAttribute
from custom_components.mbapi2020.const import BinarySensors
from custom_components.mbapi2020.proto import vehicle_events_pb2
from custom_components.mbapi2020.vsu_helper import normalize_vsu_car

from .conftest import make_client
from .fixtures.build import SYNTH_VIN


def test_normalize_vsu_car_preserves_timestamped_proto3_zero_and_false_defaults() -> None:
    """Proto3 omits default 0/False scalars on the wire; timestamped VSU entries synthesize them."""
    vsu = vehicle_events_pb2.VehicleStatusUpdate()
    vsu.fin_or_vin = SYNTH_VIN
    vsu.full_update = True
    vsu.soh_calibration_state.metadata.timestamp.seconds = 1780591500
    vsu.soh_calibration_required.metadata.timestamp.seconds = 1780591500
    vsu.sunroof_event_active.metadata.timestamp.seconds = 1780591500
    vsu.tracking_state_h_u.metadata.timestamp.seconds = 1780591500
    vsu.temperature_unit_h_u.metadata.timestamp.seconds = 1780591500
    vsu.charging_error_details.metadata.timestamp.seconds = 1780591500
    vsu.hv_battery_precond_duration.metadata.timestamp.seconds = 1780591500

    synthetic = normalize_vsu_car(MessageToDict(vsu, preserving_proto_field_name=True))
    attrs = synthetic["attributes"]

    assert attrs["sohCalibrationState"]["value"] == 0
    assert attrs["sohCalibrationRequired"]["value"] == 0
    assert attrs["sunroofEventActive"]["value"] is False
    assert attrs["trackingStateHU"]["value"] == 0
    assert attrs["temperatureUnitHU"]["value"] == 0
    assert attrs["chargingErrorDetails"]["value"] == 0
    assert attrs["hvBatteryPrecondDuration"]["value"] == 0
    # Untimestamped attributes remain absent
    assert "oilWarningLevel" not in attrs


def test_binary_sensor_is_on_returns_none_without_recursion_when_state_is_none() -> None:
    """MercedesMEBinarySensor.is_on returns None instead of recursing into super().is_on."""
    client = make_client()
    car = Car(SYNTH_VIN)
    car.binarysensors = CarBinarySensors()
    car.binarysensors.parkbrakestatus = CarAttribute(None, "VALID", 1780591500)
    client.cars[SYNTH_VIN] = car
    coord = SimpleNamespace(
        hass=None,
        client=client,
        config_entry=client.config_entry,
        last_update_success=True,
    )
    bs = MercedesMEBinarySensor(
        internal_name="parkbrakestatus",
        config=BinarySensors["parkbrakestatus"],
        vin=SYNTH_VIN,
        coordinator=coord,
    )
    bs._state = None
    assert bs.is_on is None
