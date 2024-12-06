"""The MercedesME 2020 client."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import json
import logging
from pathlib import Path
import threading
import time
import uuid

from aiohttp import ClientSession, WSServerHandshakeError
from google.protobuf.json_format import MessageToJson

from custom_components.mbapi2020.proto import client_pb2
import custom_components.mbapi2020.proto.vehicle_commands_pb2 as pb2_commands
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import system_info

from .car import (
    AUX_HEAT_OPTIONS,
    BINARY_SENSOR_OPTIONS,
    DOOR_OPTIONS,
    ELECTRIC_OPTIONS,
    LOCATION_OPTIONS,
    ODOMETER_OPTIONS,
    PRE_COND_OPTIONS,
    TIRE_OPTIONS,
    WINDOW_OPTIONS,
    WIPER_OPTIONS,
    Auxheat,
    BinarySensors,
    Car,
    CarAlarm,
    CarAlarm_OPTIONS,
    CarAttribute,
    Doors,
    Electric,
    GeofenceEvents,
    Location,
    Odometer,
    Precond,
    Tires,
    Windows,
    Wipers,
)
from .const import (
    CONF_DEBUG_FILE_SAVE,
    CONF_EXCLUDED_CARS,
    CONF_FT_DISABLE_CAPABILITY_CHECK,
    CONF_PIN,
    DEFAULT_CACHE_PATH,
    DEFAULT_DOWNLOAD_PATH,
    DEFAULT_SOCKET_MIN_RETRY,
)
from .helper import LogHelper as loghelper
from .oauth import Oauth
from .webapi import WebApi
from .websocket import Websocket

LOGGER = logging.getLogger(__name__)

DEBUG_SIMULATE_PARTIAL_UPDATES_ONLY = False
GEOFENCING_MAX_RETRIES = 2


class Client:
    """define the client."""

    long_running_operation_active: bool = False
    ignition_states: dict[str, bool] = {}

    def __init__(
        self,
        hass: HomeAssistant,
        session: ClientSession,
        config_entry: ConfigEntry,
        region: str = "",
    ) -> None:
        """Initialize the client instance."""

        self._ws_reconnect_delay = DEFAULT_SOCKET_MIN_RETRY
        self._hass = hass
        self._region = region
        self._on_dataload_complete = None
        self._dataload_complete_fired = False
        self._disable_rlock = False
        self.__lock = None
        self._debug_save_path = self._hass.config.path(DEFAULT_CACHE_PATH)
        self.config_entry = config_entry
        self.session_id = str(uuid.uuid4()).upper()

        self._first_vepupdates_processed: bool = False
        self._vepupdates_timeout_seconds: int = 30

        self.oauth: Oauth = Oauth(
            hass=self._hass,
            session=session,
            region=self._region,
            config_entry=config_entry,
        )
        self.oauth.session_id = self.session_id
        self.webapi: WebApi = WebApi(self._hass, session=session, oauth=self.oauth, region=self._region)
        self.webapi.session_id = self.session_id
        self.websocket: Websocket = Websocket(
            hass=self._hass,
            oauth=self.oauth,
            region=self._region,
            session_id=self.session_id,
            ignition_states=self.ignition_states,
        )

        self.cars: dict[str, Car] = {}

    @property
    def pin(self) -> str:
        """Return the security pin of an account."""
        if self.config_entry:
            if self.config_entry.options:
                return self.config_entry.options.get(CONF_PIN, None)
        return ""

    @property
    def excluded_cars(self):
        """Return the list of exluded/ignored VIN/FIN."""
        if self.config_entry:
            if self.config_entry.options:
                return self.config_entry.options.get(CONF_EXCLUDED_CARS, [])
        return []

    def on_data(self, data):
        """Define a handler to fire when the data is received."""

        msg_type = data.WhichOneof("msg")

        if self.websocket.ws_connect_retry_counter > 0:
            self.websocket.ws_connect_retry_counter = 0
            self.websocket.ws_connect_retry_counter_reseted = True

        if msg_type == "vepUpdate":  # VEPUpdate
            LOGGER.debug("vepUpdate")
            return None

        if msg_type == "vepUpdates":  # VEPUpdatesByVIN
            self._process_vep_updates(data)

            sequence_number = data.vepUpdates.sequence_number
            LOGGER.debug("vepUpdates Sequence: %s", sequence_number)
            ack_command = client_pb2.ClientMessage()
            ack_command.acknowledge_vep_updates_by_vin.sequence_number = sequence_number
            return ack_command

        if msg_type == "debugMessage":  # DebugMessage
            self._write_debug_output(data, "deb")
            if data.debugMessage:
                LOGGER.debug("debugMessage - Data: %s", data.debugMessage.message)

            return None

        if msg_type == "service_status_updates":
            self._write_debug_output(data, "ssu")
            sequence_number = data.service_status_updates.sequence_number
            LOGGER.debug("service_status_update Sequence: %s", sequence_number)
            ack_command = client_pb2.ClientMessage()
            ack_command.acknowledge_service_status_update.sequence_number = sequence_number
            return ack_command

        if msg_type == "user_data_update":
            self._write_debug_output(data, "udu")
            sequence_number = data.user_data_update.sequence_number
            LOGGER.debug("user_data_update Sequence: %s", sequence_number)
            ack_command = client_pb2.ClientMessage()
            ack_command.acknowledge_user_data_update.sequence_number = sequence_number
            return ack_command

        if msg_type == "user_vehicle_auth_changed_update":
            LOGGER.debug(
                "user_vehicle_auth_changed_update - Data: %s",
                MessageToJson(data, preserving_proto_field_name=True),
            )
            return None

        if msg_type == "user_picture_update":
            self._write_debug_output(data, "upu")
            sequence_number = data.user_picture_update.sequence_number
            LOGGER.debug("user_picture_update Sequence: %s", sequence_number)
            ack_command = client_pb2.ClientMessage()
            ack_command.acknowledge_user_picture_update.sequence_number = sequence_number
            return ack_command

        if msg_type == "user_pin_update":
            self._write_debug_output(data, "pin")
            sequence_number = data.user_pin_update.sequence_number
            LOGGER.debug("user_pin_update Sequence: %s", sequence_number)
            ack_command = client_pb2.ClientMessage()
            ack_command.acknowledge_user_pin_update.sequence_number = sequence_number
            return ack_command

        if msg_type == "vehicle_updated":
            self._write_debug_output(data, "vup")
            sequence_number = data.vehicle_updated.sequence_number
            LOGGER.debug("vehicle_updated Sequence: %s", sequence_number)
            ack_command = client_pb2.ClientMessage()
            ack_command.acknowledge_vehicle_updated.sequence_number = sequence_number
            return ack_command

        if msg_type == "preferred_dealer_change":
            self._write_debug_output(data, "pdc")
            sequence_number = data.preferred_dealer_change.sequence_number
            LOGGER.debug("preferred_dealer_change Sequence: %s", sequence_number)
            ack_command = client_pb2.ClientMessage()
            ack_command.acknowledge_preferred_dealer_change.sequence_number = sequence_number
            return ack_command

        if msg_type == "apptwin_command_status_updates_by_vin":
            LOGGER.debug(
                "apptwin_command_status_updates_by_vin - Data: %s",
                MessageToJson(data, preserving_proto_field_name=True),
            )

            self._process_apptwin_command_status_updates_by_vin(data)

            sequence_number = data.apptwin_command_status_updates_by_vin.sequence_number
            LOGGER.debug("apptwin_command_status_updates_by_vin: %s", sequence_number)
            ack_command = client_pb2.ClientMessage()
            ack_command.acknowledge_apptwin_command_status_update_by_vin.sequence_number = sequence_number
            return ack_command

        if msg_type == "apptwin_pending_command_request":
            self._process_assigned_vehicles(data)
            return "aa0100"

        if msg_type == "assigned_vehicles":
            self._write_debug_output(data, "asv")
            self._process_assigned_vehicles(data)
            return "ba0100"

        if msg_type == "data_change_event":
            self._write_debug_output(data, "dce")
            sequence_number = data.data_change_event.sequence_number
            LOGGER.debug("data_change_event: %s", sequence_number)
            ack_command = client_pb2.ClientMessage()
            ack_command.acknowledge_data_change_event.sequence_number = sequence_number
            return ack_command

        self._write_debug_output(data, "unk")
        LOGGER.debug("Message Type not implemented: %s", msg_type)

        return None

    async def attempt_connect(self, callback_dataload_complete):
        """Attempt to connect to the socket (retrying later on fail)."""
        LOGGER.debug("attempt_connect")
        stop_retry_loop: bool = False

        self._on_dataload_complete = callback_dataload_complete
        while not stop_retry_loop and not self.websocket.is_stopping:
            try:
                if self.websocket.ws_connect_retry_counter == 0:
                    await self.websocket.async_connect(self.on_data)
                else:
                    wait_time = (
                        self._ws_reconnect_delay
                        * self.websocket.ws_connect_retry_counter
                        * self.websocket.ws_connect_retry_counter
                    )
                    LOGGER.debug(
                        "Websocket reconnect handler loop - round %s - waiting %s sec",
                        self.websocket.ws_connect_retry_counter,
                        wait_time,
                    )
                    await asyncio.sleep(wait_time)

                    await self.websocket.component_reload_watcher.trigger()

                    await self.websocket.async_connect(self.on_data)
            except WSServerHandshakeError as err:
                if self.websocket.is_stopping:
                    stop_retry_loop = True
                    break
                LOGGER.error(
                    "Error with the websocket connection (retry counter: %s): %s - %s",
                    self.websocket.ws_connect_retry_counter,
                    err.code,
                    err.message,
                )
                self.websocket.ws_connect_retry_counter += 1
            except Exception as err:
                if self.websocket.is_stopping:
                    stop_retry_loop = True
                    break

                LOGGER.error(
                    "Unkown error with the websocket connection (retry counter: %s): %s",
                    self.websocket.ws_connect_retry_counter,
                    err,
                    exc_info=err,
                )
                self.websocket.ws_connect_retry_counter += 1
            if self.websocket.is_stopping:
                LOGGER.info("Client WS Handler loop - stopping")
                stop_retry_loop = True
                break

            LOGGER.info(
                "Client WS Handler loop - loop end round %s",
                self.websocket.ws_connect_retry_counter - 1,
            )

    def _build_car(self, received_car_data, update_mode):
        if received_car_data.get("vin") in self.excluded_cars:
            LOGGER.debug("CAR excluded: %s", loghelper.Mask_VIN(received_car_data.get("vin")))
            return

        if received_car_data.get("vin") not in self.cars:
            LOGGER.info(
                "Flow Problem - VepUpdate for unknown car. Looks like we found a Smart: %s",
                loghelper.Mask_VIN(received_car_data.get("vin")),
            )

            current_car = Car(received_car_data.get("vin"))
            current_car.licenseplate = received_car_data.get("vin")
            self.cars[received_car_data.get("vin")] = current_car

        car: Car = self.cars.get(received_car_data.get("vin"), Car(received_car_data.get("vin")))

        car.messages_received.update("p" if update_mode else "f")
        car.last_message_received = int(round(time.time() * 1000))

        if not update_mode:
            car.last_full_message = received_car_data

        car.odometer = self._get_car_values(
            received_car_data,
            car.finorvin,
            Odometer() if not car.odometer else car.odometer,
            ODOMETER_OPTIONS,
            update_mode,
        )

        car.tires = self._get_car_values(
            received_car_data,
            car.finorvin,
            Tires() if not car.tires else car.tires,
            TIRE_OPTIONS,
            update_mode,
        )

        car.wipers = self._get_car_values(
            received_car_data,
            car.finorvin,
            Wipers() if not car.wipers else car.wipers,
            WIPER_OPTIONS,
            update_mode,
        )

        car.doors = self._get_car_values(
            received_car_data,
            car.finorvin,
            Doors() if not car.doors else car.doors,
            DOOR_OPTIONS,
            update_mode,
        )

        car.location = self._get_car_values(
            received_car_data,
            car.finorvin,
            Location() if not car.location else car.location,
            LOCATION_OPTIONS,
            update_mode,
        )

        car.binarysensors = self._get_car_values(
            received_car_data,
            car.finorvin,
            BinarySensors() if not car.binarysensors else car.binarysensors,
            BINARY_SENSOR_OPTIONS,
            update_mode,
        )

        car.windows = self._get_car_values(
            received_car_data,
            car.finorvin,
            Windows() if not car.windows else car.windows,
            WINDOW_OPTIONS,
            update_mode,
        )

        car.electric = self._get_car_values(
            received_car_data,
            car.finorvin,
            Electric() if not car.electric else car.electric,
            ELECTRIC_OPTIONS,
            update_mode,
        )

        car.auxheat = self._get_car_values(
            received_car_data,
            car.finorvin,
            Auxheat() if not car.auxheat else car.auxheat,
            AUX_HEAT_OPTIONS,
            update_mode,
        )

        car.precond = self._get_car_values(
            received_car_data,
            car.finorvin,
            Precond() if not car.precond else car.precond,
            PRE_COND_OPTIONS,
            update_mode,
        )

        car.caralarm = self._get_car_values(
            received_car_data,
            car.finorvin,
            CarAlarm() if not car.caralarm else car.caralarm,
            CarAlarm_OPTIONS,
            update_mode,
        )

        if not update_mode:
            car.entry_setup_complete = True

        # Nimm jedes car (item) aus self.cars ausser es ist das aktuelle dann nimm car
        self.cars[car.finorvin] = car

    def _get_car_values(self, car_detail, car_id, class_instance, options, update):
        # Define handlers for specific options and the generic case
        option_handlers = {
            "max_soc": self._get_car_values_handle_max_soc,
            "chargingBreakClockTimer": self._get_car_values_handle_charging_break_clock_timer,
            "ignitionstate": self._get_car_values_handle_ignitionstate,
            "precondStatus": self._get_car_values_handle_precond_status,
            "temperature_points_frontLeft": self._get_car_values_handle_temperature_points,
            "temperature_points_frontRight": self._get_car_values_handle_temperature_points,
            "temperature_points_rearLeft": self._get_car_values_handle_temperature_points,
            "temperature_points_rearRight": self._get_car_values_handle_temperature_points,
        }

        if car_detail is None or not car_detail.get("attributes"):
            LOGGER.debug(
                "get_car_values %s has incomplete update data – attributes not found",
                loghelper.Mask_VIN(car_id),
            )
            return class_instance

        for option in options:
            # Select the specific handler or the generic handler
            handler = option_handlers.get(option, self._get_car_values_handle_generic)

            curr_status = handler(car_detail, class_instance, option, update)
            if curr_status is None:
                continue

            # Set the value only if the timestamp is newer
            curr_timestamp = float(curr_status.timestamp or 0)
            car_value_timestamp = float(self._get_car_value(class_instance, option, "ts", 0))
            if curr_timestamp > car_value_timestamp:
                setattr(class_instance, option, curr_status)
            elif curr_timestamp < car_value_timestamp:
                LOGGER.warning(
                    "get_car_values %s received older attribute data for %s. Ignoring value.",
                    loghelper.Mask_VIN(car_id),
                    option,
                )

        return class_instance

    def _get_car_values_handle_generic(self, car_detail, class_instance, option, update):
        curr = car_detail.get("attributes", {}).get(option)
        if curr:
            # Simplify value extraction by checking for existing keys
            value = next(
                (curr[key] for key in ("value", "int_value", "double_value", "bool_value") if key in curr),
                0,
            )
            status = curr.get("status", "VALID")
            time_stamp = curr.get("timestamp", 0)
            curr_display_value = curr.get("display_value")

            unit_keys = [
                "distance_unit",
                "ratio_unit",
                "clock_hour_unit",
                "gas_consumption_unit",
                "pressure_unit",
                "electricity_consumption_unit",
                "combustion_consumption_unit",
                "speed_unit",
            ]
            unit = next((curr[key] for key in unit_keys if key in curr), None)

            return CarAttribute(
                value=value,
                retrievalstatus=status,
                timestamp=time_stamp,
                display_value=curr_display_value,
                unit=unit,
            )

        if not update:
            # Set status for non-existing values when no update occurs
            return CarAttribute(0, 4, 0)

        return None

    def _get_car_values_handle_max_soc(self, car_detail, class_instance, option, update):
        # special EQA/B max_soc handling
        attributes = car_detail.get("attributes", {})
        charge_programs = attributes.get("chargePrograms")
        if not charge_programs:
            return None

        time_stamp = charge_programs.get("timestamp", 0)
        charge_programs_value = charge_programs.get("charge_programs_value", {})
        charge_program_parameters = charge_programs_value.get("charge_program_parameters", [])

        selected_program_index = int(self._get_car_value(class_instance, "selectedChargeProgram", "value", 0))

        # Ensure the selected index is within bounds
        if 0 <= selected_program_index < len(charge_program_parameters):
            program_parameters = charge_program_parameters[selected_program_index]
            max_soc = program_parameters.get("max_soc")
            if max_soc is not None:
                return CarAttribute(
                    value=max_soc,
                    retrievalstatus="VALID",
                    timestamp=time_stamp,
                    display_value=max_soc,
                    unit="PERCENT",
                )

        return None

    def _get_car_values_handle_charging_break_clock_timer(self, car_detail, class_instance, option, update):
        attributes = car_detail.get("attributes", {})
        curr = attributes.get(option)
        if not curr:
            return None

        charging_timer_value = curr.get("chargingbreak_clocktimer_value", {})
        value = charging_timer_value.get("chargingbreak_clocktimer_entry")
        if value is None:
            return None

        status = curr.get("status", "VALID")
        time_stamp = curr.get("timestamp", 0)
        curr_display_value = curr.get("display_value")

        return CarAttribute(
            value=value,
            retrievalstatus=status,
            timestamp=time_stamp,
            display_value=curr_display_value,
            unit=None,
        )

    def _get_car_values_handle_ignitionstate(self, car_detail, class_instance, option, update):
        value = self._get_car_values_handle_generic(car_detail, class_instance, option, update)
        if value:
            vin = car_detail.get("vin")

            self.ignition_states[vin] = value.value == "4"

        return value

    def _get_car_values_handle_precond_status(self, car_detail, class_instance, option, update):
        attributes = car_detail.get("attributes", {})

        # Retrieve attributes with defaults to handle missing keys
        precond_now_attr = attributes.get("precondNow", {})
        precond_active_attr = attributes.get("precondActive", {})
        precond_operating_mode_attr = attributes.get("precondOperatingMode", {})

        # Extract values and convert to boolean where necessary
        precond_now_value = precond_now_attr.get("bool_value", False)
        precond_active_value = precond_active_attr.get("bool_value", False)
        precond_operating_mode_value = precond_operating_mode_attr.get("int_value", 0)
        precond_operating_mode_bool = int(precond_operating_mode_value) > 0

        # Calculate precondStatus
        value = precond_now_value or precond_active_value or precond_operating_mode_bool

        # Determine if any of the attributes are present
        if precond_now_attr or precond_active_attr or precond_operating_mode_attr:
            status = "VALID"
            time_stamp = max(
                int(precond_now_attr.get("timestamp", 0)),
                int(precond_active_attr.get("timestamp", 0)),
                int(precond_operating_mode_attr.get("timestamp", 0)),
            )
            return CarAttribute(
                value=value,
                retrievalstatus=status,
                timestamp=time_stamp,
                display_value=str(value),
                unit=None,
            )

        if not update:
            # Set status for non-existing values when no update occurs
            return CarAttribute(False, 4, 0)

        return None

    def _get_car_values_handle_temperature_points(self, car_detail, class_instance, option: str, update):
        curr_zone = option.replace("temperature_points_", "")
        attributes = car_detail.get("attributes", {})
        temperaturePoints = attributes.get("temperaturePoints")
        if not temperaturePoints:
            return None

        time_stamp = temperaturePoints.get("timestamp", 0)
        temperature_points_value = temperaturePoints.get("temperature_points_value", {})
        temperature_points = temperature_points_value.get("temperature_points", [])

        for point in temperature_points:
            if point.get("zone", "") == curr_zone:
                return CarAttribute(
                    value=point.get("temperature", 0),
                    retrievalstatus="VALID",
                    timestamp=time_stamp,
                    display_value=point.get("temperature_display_value"),
                    unit=temperaturePoints.get("temperature_unit", None),
                )

        return None

    def _get_car_value(self, class_instance, object_name, attrib_name, default_value):
        return getattr(
            getattr(class_instance, object_name, default_value),
            attrib_name,
            default_value,
        )

    def _process_vep_updates(self, data):
        LOGGER.debug("Start _process_vep_updates")

        self._write_debug_output(data, "vep")

        # Don't understand the protobuf dict errors --> convert to json
        vep_json = json.loads(MessageToJson(data, preserving_proto_field_name=True))
        cars = vep_json["vepUpdates"]["updates"]

        if not self._first_vepupdates_processed:
            self._vepupdates_time_first_message = datetime.now()
            self._first_vepupdates_processed = True

        for vin in cars:
            if vin in self.excluded_cars:
                continue

            current_car = cars.get(vin)

            if DEBUG_SIMULATE_PARTIAL_UPDATES_ONLY and current_car.get("full_update", False) is True:
                current_car["full_update"] = False
                LOGGER.debug(
                    "DEBUG_SIMULATE_PARTIAL_UPDATES_ONLY mode. %s",
                    loghelper.Mask_VIN(vin),
                )

            if current_car.get("full_update") is True:
                LOGGER.debug("Full Update. %s", loghelper.Mask_VIN(vin))
                if not self._disable_rlock:
                    with self.__lock:
                        self._build_car(current_car, update_mode=False)
                else:
                    self._build_car(current_car, update_mode=False)

            else:
                LOGGER.debug("Partial Update. %s", loghelper.Mask_VIN(vin))
                if not self._disable_rlock:
                    with self.__lock:
                        self._build_car(current_car, update_mode=True)
                else:
                    self._build_car(current_car, update_mode=True)

            if self._dataload_complete_fired:
                current_car = self.cars.get(vin)

                if current_car:
                    current_car.publish_updates()

        if not self._dataload_complete_fired:
            fire_complete_event: bool = True
            for car in self.cars.values():
                if not car.entry_setup_complete:
                    fire_complete_event = False
                LOGGER.debug(
                    "_process_vep_updates - %s - complete: %s - %s",
                    loghelper.Mask_VIN(car.finorvin),
                    car.entry_setup_complete,
                    car.messages_received,
                )
            if fire_complete_event:
                LOGGER.debug("_process_vep_updates - all completed - fire event: _on_dataload_complete")
                self._hass.async_create_task(self._on_dataload_complete())
                self._dataload_complete_fired = True

        if not self._dataload_complete_fired and (datetime.now() - self._vepupdates_time_first_message) > timedelta(
            seconds=self._vepupdates_timeout_seconds
        ):
            LOGGER.debug(
                "_process_vep_updates - not all data received, timeout reached - fire event: _on_dataload_complete"
            )
            self._hass.async_create_task(self._on_dataload_complete())
            self._dataload_complete_fired = True

    def _process_assigned_vehicles(self, data):
        if not self._dataload_complete_fired:
            LOGGER.debug("Start _process_assigned_vehicles")

            # self._write_debug_output(data, "asv")

            if not self._disable_rlock:
                with self.__lock:
                    for vin in data.assigned_vehicles.vins:
                        if vin in self.excluded_cars:
                            continue

                        _car = self.cars.get(vin)

                        if _car is None:
                            current_car = Car(vin)
                            current_car.licenseplate = vin
                            self.cars[vin] = current_car
            else:
                for vin in data.assigned_vehicles.vins:
                    if vin in self.excluded_cars:
                        continue

                    _car = self.cars.get(vin)

                    if _car is None:
                        current_car = Car(vin)
                        current_car.licenseplate = vin
                        self.cars[vin] = current_car

            current_time = int(round(time.time() * 1000))
            for key, value in self.cars.items():
                LOGGER.debug(
                    "_process_assigned_vehicles - %s - %s - %s - %s",
                    loghelper.Mask_VIN(key),
                    value.entry_setup_complete,
                    value.messages_received,
                    current_time - value.last_message_received.value.timestamp(),
                )

    def _process_apptwin_command_status_updates_by_vin(self, data):
        LOGGER.debug("Start _process_assigned_vehicles")

        # Don't understand the protobuf dict errors --> convert to json
        apptwin_json = json.loads(MessageToJson(data, preserving_proto_field_name=True))

        self._write_debug_output(data, "acr")

        if apptwin_json["apptwin_command_status_updates_by_vin"]:
            if apptwin_json["apptwin_command_status_updates_by_vin"]["updates_by_vin"]:
                car = list(apptwin_json["apptwin_command_status_updates_by_vin"]["updates_by_vin"].keys())[0]
                car = apptwin_json["apptwin_command_status_updates_by_vin"]["updates_by_vin"][car]
                vin = car.get("vin", None)
                if vin:
                    if car["updates_by_pid"]:
                        command = list(car["updates_by_pid"].keys())[0]
                        command = car["updates_by_pid"][command]
                        if command:
                            command_type = command.get("type")
                            command_state = command.get("state")
                            command_error_code = ""
                            command_error_message = ""
                            if command.get("errors"):
                                for err in command["errors"]:
                                    command_error_code = err.get("code")
                                    command_error_message = err.get("message")
                                    LOGGER.warning(
                                        "Car action: %s failed. error_code: %s, error_message: %s",
                                        command_type,
                                        command_error_code,
                                        command_error_message,
                                    )

                            current_car = self.cars.get(vin)

                            if current_car:
                                current_car.last_command_type = command_type
                                current_car.last_command_state = command_state
                                current_car.last_command_error_code = command_error_code
                                current_car.last_command_error_message = command_error_message
                                current_car.last_command_time_stamp = command.get("timestamp_in_ms", 0)

                                current_car.publish_updates()

    async def charge_program_configure(self, vin: str, program: int):
        """Send the selected charge program to the car."""
        if not self._is_car_feature_available(vin, "CHARGE_PROGRAM_CONFIGURE"):
            LOGGER.warning(
                "Can't set the charge program of the  car %s. Feature CHARGE_PROGRAM_CONFIGURE not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        LOGGER.debug("Start charge_program_configure")
        message = client_pb2.ClientMessage()
        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        charge_programm = pb2_commands.ChargeProgramConfigure()
        charge_programm.charge_program = program
        message.commandRequest.charge_program_configure.CopyFrom(charge_programm)

        await self.execute_car_command(message)
        return

    async def charging_break_clocktimer_configure(
        self,
        vin: str,
        status_t1: str,
        start_t1: datetime.timedelta,
        stop_t1: datetime.timedelta,
        status_t2: str,
        start_t2: datetime.timedelta,
        stop_t2: datetime.timedelta,
        status_t3: str,
        start_t3: datetime.timedelta,
        stop_t3: datetime.timedelta,
        status_t4: str,
        start_t4: datetime.timedelta,
        stop_t4: datetime.timedelta,
    ) -> None:
        """Send the charging_break_clocktimer_configure command to the car."""
        if not self._is_car_feature_available(vin, "chargingClockTimer"):
            LOGGER.warning(
                "Can't send charging_break_clocktimer_configure for car %s. Feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        config = pb2_commands.ChargingBreakClocktimerConfigure()
        entry_set: bool = False

        if status_t1 and start_t1 and stop_t1 and status_t1 in ("active", "inactive"):
            t1 = config.chargingbreak_clocktimer_configure_entry.add()
            t1.timerId = 1
            if status_t1 == "active":
                t1.action = pb2_commands.ChargingBreakClockTimerEntryStatus.ACTIVE
            else:
                t1.action = pb2_commands.ChargingBreakClockTimerEntryStatus.INACTIVE

            t1.startTimeHour = start_t1.seconds // 3600
            t1.startTimeMinute = (start_t1.seconds % 3600) // 60
            t1.endTimeHour = stop_t1.seconds // 3600
            t1.endTimeMinute = (stop_t1.seconds % 3600) // 60
            entry_set = True

        if status_t2 and start_t2 and stop_t2 and status_t2 in ("active", "inactive"):
            t2 = config.chargingbreak_clocktimer_configure_entry.add()
            t2.timerId = 2
            if status_t2 == "active":
                t2.action = pb2_commands.ChargingBreakClockTimerEntryStatus.ACTIVE
            else:
                t2.action = pb2_commands.ChargingBreakClockTimerEntryStatus.INACTIVE

            t2.startTimeHour = start_t2.seconds // 3600
            t2.startTimeMinute = (start_t2.seconds % 3600) // 60
            t2.endTimeHour = stop_t2.seconds // 3600
            t2.endTimeMinute = (stop_t2.seconds % 3600) // 60
            entry_set = True

        if status_t3 and start_t3 and stop_t3 and status_t3 in ("active", "inactive"):
            t3 = config.chargingbreak_clocktimer_configure_entry.add()
            t3.timerId = 3
            if status_t3 == "active":
                t3.action = pb2_commands.ChargingBreakClockTimerEntryStatus.ACTIVE
            else:
                t3.action = pb2_commands.ChargingBreakClockTimerEntryStatus.INACTIVE

            t3.startTimeHour = start_t3.seconds // 3600
            t3.startTimeMinute = (start_t3.seconds % 3600) // 60
            t3.endTimeHour = stop_t3.seconds // 3600
            t3.endTimeMinute = (stop_t3.seconds % 3600) // 60
            entry_set = True

        if status_t4 and start_t4 and stop_t4 and status_t4 in ("active", "inactive"):
            t4 = config.chargingbreak_clocktimer_configure_entry.add()
            t4.timerId = 4
            if status_t4 == "active":
                t4.action = pb2_commands.ChargingBreakClockTimerEntryStatus.ACTIVE
            else:
                t4.action = pb2_commands.ChargingBreakClockTimerEntryStatus.INACTIVE

            t4.startTimeHour = start_t4.seconds // 3600
            t4.startTimeMinute = (start_t4.seconds % 3600) // 60
            t4.endTimeHour = stop_t4.seconds // 3600
            t4.endTimeMinute = (stop_t4.seconds % 3600) // 60
            entry_set = True

        if entry_set:
            message.commandRequest.chargingbreak_clocktimer_configure.CopyFrom(config)
            await self.execute_car_command(message)
            LOGGER.info(
                "End charging_break_clocktimer_configure for vin %s",
                loghelper.Mask_VIN(vin),
            )
        else:
            LOGGER.info(
                "End charging_break_clocktimer_configure for vin %s - No actions",
                loghelper.Mask_VIN(vin),
            )

        return

    async def doors_unlock(self, vin: str, pin: str = ""):
        """Send the doors unlock command to the car."""
        if not self._is_car_feature_available(vin, "DOORS_UNLOCK"):
            LOGGER.warning(
                "Can't unlock car %s. Feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        if pin and pin.strip():
            LOGGER.debug("Start unlock with user provided pin")
            await self.doors_unlock_with_pin(vin, pin)
            return

        if not self.pin:
            LOGGER.warning(
                "Can't unlock car %s. PIN not set. Please set the PIN -> Integration, Options ",
                loghelper.Mask_VIN(vin),
            )
            return

        await self.doors_unlock_with_pin(vin, self.pin)

    async def doors_unlock_with_pin(self, vin: str, pin: str):
        """Send the doors unlock command to the car."""
        LOGGER.info("Start Doors_unlock_with_pin for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "DOORS_UNLOCK"):
            LOGGER.warning(
                "Can't unlock car %s. Feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        if not pin:
            LOGGER.warning("Can't unlock car %s. Pin is required.", loghelper.Mask_VIN(vin))
            return

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.doors_unlock.pin = pin

        await self.execute_car_command(message)
        LOGGER.info("End Doors_unlock for vin %s", loghelper.Mask_VIN(vin))

    async def doors_lock(self, vin: str):
        """Send the doors lock command to the car."""
        LOGGER.info("Start Doors_lock for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "DOORS_LOCK"):
            LOGGER.warning(
                "Can't lock car %s. Feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.doors_lock.doors.extend([])

        await self.execute_car_command(message)
        LOGGER.info("End Doors_lock for vin %s", loghelper.Mask_VIN(vin))

    async def download_images(self, vin: str):
        """Download the car related images."""
        LOGGER.info("Start download_images for vin %s", loghelper.Mask_VIN(vin))

        download_path = self._hass.config.path(DEFAULT_DOWNLOAD_PATH)
        target_file_name = Path(download_path, f"{vin}.zip")
        zip_file = await self.webapi.download_images(vin)
        if zip_file:
            Path(download_path).mkdir(parents=True, exist_ok=True)

            def save_images() -> None:
                with Path.open(target_file_name, mode="wb") as zf:
                    zf.write(zip_file)
                    zf.close()

            try:
                await self._hass.async_add_executor_job(save_images)
            except OSError as err:
                LOGGER.error("Can't write %s: %s", target_file_name, err)

        LOGGER.info("End download_images for vin %s", loghelper.Mask_VIN(vin))

    async def auxheat_configure(self, vin: str, time_selection: int, time_1: int, time_2: int, time_3: int):
        """Send the auxheat configure command to the car."""
        LOGGER.info("Start auxheat_configure for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, feature_list=["AUXHEAT_CONFIGURE", "auxHeat"]):
            LOGGER.warning(
                "Can't start auxheat_configure for car %s. Feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        auxheat_configure = pb2_commands.AuxheatConfigure()
        auxheat_configure.time_selection = time_selection
        auxheat_configure.time_1 = time_1
        auxheat_configure.time_2 = time_2
        auxheat_configure.time_3 = time_3
        message.commandRequest.auxheat_configure.CopyFrom(auxheat_configure)

        await self.execute_car_command(message)
        LOGGER.info("End auxheat_configure for vin %s", loghelper.Mask_VIN(vin))

    async def auxheat_start(self, vin: str):
        """Send the auxheat start command to the car."""
        LOGGER.info("Start auxheat start for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, feature_list=["AUXHEAT_START", "auxHeat"]):
            LOGGER.warning(
                "Can't start auxheat for car %s. Feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        auxheat_start = pb2_commands.AuxheatStart()
        message.commandRequest.auxheat_start.CopyFrom(auxheat_start)

        await self.execute_car_command(message)
        LOGGER.info("End auxheat start for vin %s", loghelper.Mask_VIN(vin))

    async def auxheat_stop(self, vin: str):
        """Send the auxheat stop command to the car."""
        LOGGER.info("Start auxheat_stop for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, feature_list=["AUXHEAT_STOP", "auxHeat"]):
            LOGGER.warning(
                "Can't stop auxheat for car %s. Feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        auxheat_stop = pb2_commands.AuxheatStop()
        message.commandRequest.auxheat_stop.CopyFrom(auxheat_stop)

        await self.execute_car_command(message)
        LOGGER.info("End auxheat_stop for vin %s", loghelper.Mask_VIN(vin))

    async def battery_max_soc_configure(self, vin: str, max_soc: int, charge_program: int = 0):
        """Send the maxsoc configure command to the car."""
        LOGGER.info(
            "Start battery_max_soc_configure to %s for vin %s and program %s",
            max_soc,
            loghelper.Mask_VIN(vin),
            charge_program,
        )

        if not self._is_car_feature_available(vin, "BATTERY_MAX_SOC_CONFIGURE"):
            LOGGER.warning(
                "Can't configure battery_max_soc for car %s. Feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        charge_program_config = pb2_commands.ChargeProgramConfigure()
        charge_program_config.max_soc.value = max_soc
        charge_program_config.charge_program = charge_program
        message.commandRequest.charge_program_configure.CopyFrom(charge_program_config)

        await self.execute_car_command(message)
        LOGGER.info("End battery_max_soc_configure for vin %s", loghelper.Mask_VIN(vin))

    async def engine_start(self, vin: str):
        """Send the engine start command to the car."""
        LOGGER.info("Start engine start for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "ENGINE_START"):
            LOGGER.warning(
                "Can't start engine for car %s. Feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        if not self.pin:
            LOGGER.warning(
                "Can't start the car %s. PIN not set. Please set the PIN -> Integration, Options ",
                loghelper.Mask_VIN(vin),
            )
            return

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.engine_start.pin = self.pin

        await self.execute_car_command(message)
        LOGGER.info("End engine start for vin %s", loghelper.Mask_VIN(vin))

    async def engine_stop(self, vin: str):
        """Send the engine stop command to the car."""
        LOGGER.info("Start engine_stop for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "ENGINE_STOP"):
            LOGGER.warning(
                "Can't stop engine for car %s. Feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        engine_stop = pb2_commands.EngineStop()
        message.commandRequest.engine_stop.CopyFrom(engine_stop)

        await self.execute_car_command(message)
        LOGGER.info("End engine_stop for vin %s", loghelper.Mask_VIN(vin))

    async def send_route_to_car(
        self,
        vin: str,
        title: str,
        latitude: float,
        longitude: float,
        city: str,
        postcode: str,
        street: str,
    ):
        """Send a route target to the car."""
        LOGGER.info("Start send_route_to_car for vin %s", loghelper.Mask_VIN(vin))

        await self.webapi.send_route_to_car(vin, title, latitude, longitude, city, postcode, street)

        LOGGER.info("End send_route_to_car for vin %s", loghelper.Mask_VIN(vin))

    async def sigpos_start(self, vin: str):
        """Send a sigpos command to the car."""
        LOGGER.info("Start sigpos_start for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "SIGPOS_START"):
            LOGGER.warning(
                "Can't start signaling for car %s. Feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.sigpos_start.light_type = 1
        message.commandRequest.sigpos_start.sigpos_type = 0

        await self.execute_car_command(message)
        LOGGER.info("End sigpos_start for vin %s", loghelper.Mask_VIN(vin))

    async def sunroof_open(self, vin: str):
        """Send a sunroof open command to the car."""
        LOGGER.info("Start sunroof_open for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "SUNROOF_OPEN"):
            LOGGER.warning(
                "Can't open the sunroof for car %s. Feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        if not self.pin:
            LOGGER.warning(
                "Can't open the sunroof - car %s. PIN not set. Please set the PIN -> Integration, Options ",
                loghelper.Mask_VIN(vin),
            )
            return

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.sunroof_open.pin = self.pin

        await self.execute_car_command(message)
        LOGGER.info("End sunroof_open for vin %s", loghelper.Mask_VIN(vin))

    async def sunroof_tilt(self, vin: str):
        """Send a sunroof tilt command to the car."""
        LOGGER.info("Start sunroof_tilt for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "SUNROOF_LIFT"):
            LOGGER.warning(
                "Can't tilt the sunroof for car %s. Feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        if not self.pin:
            LOGGER.warning(
                "Can't tilt the sunroof - car %s. PIN not set. Please set the PIN -> Integration, Options ",
                loghelper.Mask_VIN(vin),
            )
            return

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.sunroof_lift.pin = self.pin

        await self.execute_car_command(message)
        LOGGER.info("End sunroof_tilt for vin %s", loghelper.Mask_VIN(vin))

    async def sunroof_close(self, vin: str):
        """Send a sunroof close command to the car."""
        LOGGER.info("Start sunroof_close for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "SUNROOF_CLOSE"):
            LOGGER.warning(
                "Can't close the sunroof for car %s. Feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        sunroof_close = pb2_commands.SunroofClose()
        message.commandRequest.sunroof_close.CopyFrom(sunroof_close)

        await self.execute_car_command(message)
        LOGGER.info("End sunroof_close for vin %s", loghelper.Mask_VIN(vin))

    async def preconditioning_configure_seats(
        self,
        vin: str,
        front_left: bool,
        front_right: bool,
        rear_left: bool,
        rear_right: bool,
    ):
        """Send a preconditioning seat configuration command to the car."""
        LOGGER.info("Start preconditioning_configure_seats for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "ZEV_PRECONDITION_CONFIGURE_SEATS"):
            LOGGER.warning(
                "Can't configure seats for PreCond for car %s. Feature %s not availabe for this car.",
                loghelper.Mask_VIN(vin),
                "ZEV_PRECONDITION_CONFIGURE_SEATS",
            )
            return
        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.zev_precondition_configure_seats.front_left = front_left
        message.commandRequest.zev_precondition_configure_seats.front_right = front_right
        message.commandRequest.zev_precondition_configure_seats.rear_left = rear_left
        message.commandRequest.zev_precondition_configure_seats.rear_right = rear_right

        await self.execute_car_command(message)
        LOGGER.info("End preconditioning_configure_seats for vin %s", loghelper.Mask_VIN(vin))

    async def preheat_start(self, vin: str):
        """Send a preconditioning start command to the car."""
        LOGGER.info("Start preheat_start for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "ZEV_PRECONDITIONING_START"):
            LOGGER.warning(
                "Can't start PreCond for car %s. Feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.zev_preconditioning_start.departure_time = 0
        message.commandRequest.zev_preconditioning_start.type = pb2_commands.ZEVPreconditioningType.now

        await self.execute_car_command(message)
        LOGGER.info("End preheat_start for vin %s", loghelper.Mask_VIN(vin))

    async def preheat_start_immediate(self, vin: str):
        """Send a preconditioning immediatestart command to the car."""
        LOGGER.info("Start preheat_start_immediate for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "ZEV_PRECONDITIONING_START"):
            LOGGER.warning(
                "Can't start PreCond for car %s. Feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.zev_preconditioning_start.departure_time = 0
        message.commandRequest.zev_preconditioning_start.type = pb2_commands.ZEVPreconditioningType.immediate

        await self.execute_car_command(message)
        LOGGER.info("End preheat_start_immediate for vin %s", loghelper.Mask_VIN(vin))

    async def preheat_start_universal(self, vin: str) -> None:
        """Turn on preheat universally for any car model."""
        if self._is_car_feature_available(vin, "precondNow"):
            await self.preheat_start(vin)
        else:
            await self.preheat_start_immediate(vin)

    async def preheat_start_departure_time(self, vin: str, departure_time: int):
        """Send a preconditioning start by time command to the car."""
        LOGGER.info("Start preheat_start_departure_time for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "ZEV_PRECONDITIONING_START"):
            LOGGER.warning(
                "Can't start PreCond for car %s. Feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.zev_preconditioning_start.departure_time = departure_time
        message.commandRequest.zev_preconditioning_start.type = pb2_commands.ZEVPreconditioningType.departure

        await self.execute_car_command(message)
        LOGGER.info("End preheat_start_departure_time for vin %s", loghelper.Mask_VIN(vin))

    async def preheat_stop(self, vin: str):
        """Send a preconditioning stop command to the car."""
        LOGGER.info("Start preheat_stop for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "ZEV_PRECONDITIONING_STOP"):
            LOGGER.warning(
                "Can't stop PreCond for car %s. Feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return
        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.zev_preconditioning_stop.type = pb2_commands.ZEVPreconditioningType.now

        await self.execute_car_command(message)
        LOGGER.info("End preheat_stop for vin %s", loghelper.Mask_VIN(vin))

    async def preheat_stop_departure_time(self, vin: str):
        """Send a preconditioning stop by time command to the car."""
        LOGGER.info("Start preheat_stop_departure_time for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "ZEV_PRECONDITIONING_STOP"):
            LOGGER.warning(
                "Can't stop PreCond for car %s. Feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return
        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.zev_preconditioning_stop.type = pb2_commands.ZEVPreconditioningType.departure

        await self.execute_car_command(message)
        LOGGER.info("End preheat_stop_departure_time for vin %s", loghelper.Mask_VIN(vin))

    async def temperature_configure(
        self,
        vin: str,
        front_left: int | None = None,
        front_right: int | None = None,
        rear_left: int | None = None,
        rear_right: int | None = None,
    ):
        """Send a temperature_configure  command to the car."""
        LOGGER.info("Start temperature_configure for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "TEMPERATURE_CONFIGURE"):
            LOGGER.warning(
                "Can't configure the temperature zones for car %s. Feature %s not availabe for this car.",
                loghelper.Mask_VIN(vin),
                "TEMPERATURE_CONFIGURE",
            )
            return
        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())

        config = pb2_commands.TemperatureConfigure()
        entry_set: bool = False

        car = self.cars.get(vin)

        if front_left or front_right or rear_left or rear_right:
            zone_front_left = config.temperature_points.add()
            zone_front_left.zone = 1
            if front_left:
                zone_front_left.temperature_in_celsius = front_left
            elif car.precond.temperature_points_frontLeft:
                zone_front_left.temperature_in_celsius = car.precond.temperature_points_frontLeft.value
            entry_set = True

        if front_right or rear_left or rear_right:
            zone_front_right = config.temperature_points.add()
            zone_front_right.zone = 2
            if front_right:
                zone_front_right.temperature_in_celsius = front_right
            elif car.precond.temperature_points_frontRight:
                zone_front_right.temperature_in_celsius = car.precond.temperature_points_frontRight.value
            entry_set = True

        if rear_left or rear_right:
            zone_rear_left = config.temperature_points.add()
            zone_rear_left.zone = 4
            if rear_left:
                zone_rear_left.temperature_in_celsius = rear_left
            elif car.precond.temperature_points_rearLeft:
                zone_rear_left.temperature_in_celsius = car.precond.temperature_points_rearLeft.value
            entry_set = True

        if rear_right or rear_left:
            zone_rear_right = config.temperature_points.add()
            zone_rear_right.zone = 5
            if rear_right:
                zone_rear_right.temperature_in_celsius = rear_right
            elif car.precond.temperature_points_rearRight:
                zone_rear_right.temperature_in_celsius = car.precond.temperature_points_rearRight.value
            entry_set = True

        if entry_set:
            message.commandRequest.temperature_configure.CopyFrom(config)
            self._hass.async_add_executor_job(
                self.write_debug_json_output,
                MessageToJson(message, preserving_proto_field_name=True),
                "out_temperature_",
                False,
            )
            await self.execute_car_command(message)
            LOGGER.info("End temperature_configure for vin %s", loghelper.Mask_VIN(vin))
        else:
            LOGGER.info(
                "End temperature_configure for vin %s - No actions",
                loghelper.Mask_VIN(vin),
            )

    async def windows_open(self, vin: str, pin: str = ""):
        """Send a window open command to the car."""
        LOGGER.info("Start windows_open for vin %s", loghelper.Mask_VIN(vin))

        _pin: str = None

        if not self._is_car_feature_available(vin, "WINDOWS_OPEN"):
            LOGGER.warning(
                "Can't open the windows for car %s. Feature not marked as available for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        if pin and pin.strip():
            _pin = pin
        else:
            _pin = self.pin

        if not _pin:
            LOGGER.warning(
                "Can't open the windows - car %s. PIN not given. Please set the PIN -> Integration, Options or use the optional parameter of the service.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.windows_open.pin = _pin

        await self.execute_car_command(message)
        LOGGER.info("End windows_open for vin %s", loghelper.Mask_VIN(vin))

    async def windows_close(self, vin: str):
        """Send a window close command to the car."""
        LOGGER.info("Start windows_close for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "WINDOWS_CLOSE"):
            LOGGER.warning(
                "Can't close the windows for car %s. Feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        windows_close = pb2_commands.WindowsClose()
        message.commandRequest.windows_close.CopyFrom(windows_close)

        await self.execute_car_command(message)
        LOGGER.info("End windows_close for vin %s", loghelper.Mask_VIN(vin))

    async def windows_move(
        self,
        vin: str,
        front_left: int,
        front_right: int,
        rear_left: int,
        rear_right: int,
    ):
        """Send the windows move command to the car."""
        LOGGER.info(
            "Start windows_move for vin %s, fl-%s, fr-%s, rl-%s, rr-%s",
            loghelper.Mask_VIN(vin),
            front_left,
            front_right,
            rear_left,
            rear_right,
        )

        if not self._is_car_feature_available(vin, "variableOpenableWindow"):
            LOGGER.warning(
                "Can't move windows for car %s. Feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.windows_move.pin = self.pin
        if front_left is not None:
            if front_left == 0:
                message.commandRequest.windows_move.front_left.SetInParent()
            else:
                message.commandRequest.windows_move.front_left.value = front_left
        if front_right is not None:
            if front_right == 0:
                message.commandRequest.windows_move.front_right.SetInParent()
            else:
                message.commandRequest.windows_move.front_right.value = front_right
        if rear_left is not None:
            if rear_left == 0:
                message.commandRequest.windows_move.rear_left.SetInParent()
            else:
                message.commandRequest.windows_move.rear_left.value = rear_left
        if rear_right is not None:
            if rear_right == 0:
                message.commandRequest.windows_move.rear_right.SetInParent()
            else:
                message.commandRequest.windows_move.rear_right.value = rear_right

        await self.execute_car_command(message)
        LOGGER.info("End windows_move for vin %s", loghelper.Mask_VIN(vin))

    async def execute_car_command(self, message):
        """Execute a car command."""
        LOGGER.debug("execute_car_command - ws-connection: %s", self.websocket.connection_state)
        await self.websocket.call(message.SerializeToString(), car_command=True)

    def _is_car_feature_available(self, vin: str, feature: str = "", feature_list=None) -> bool:
        if self.config_entry.options.get(CONF_FT_DISABLE_CAPABILITY_CHECK, False):
            return True

        current_car = self.cars.get(vin)

        if current_car:
            if feature_list:
                return current_car.check_capabilities(feature_list)

            if feature:
                return current_car.features.get(feature, False)

        return False

    def _write_debug_output(self, data, datatype):
        if self.config_entry.options.get(CONF_DEBUG_FILE_SAVE, False):
            self._hass.async_add_executor_job(self.__write_debug_output, data, datatype)

    def __write_debug_output(self, data, datatype):
        if self.config_entry.options.get(CONF_DEBUG_FILE_SAVE, False):
            # LOGGER.debug("Start _write_debug_output")

            path = self._debug_save_path
            Path(path).mkdir(parents=True, exist_ok=True)

            current_file = Path.open(f"{path}/{datatype}{int(round(time.time() * 1000))}", "wb")
            current_file.write(data.SerializeToString())
            current_file.close()

            self.write_debug_json_output(MessageToJson(data, preserving_proto_field_name=True), datatype)

    def write_debug_json_output(self, data, datatype, use_dumps: bool = False):
        """Write text to files based on datatype."""
        # LOGGER.debug(self.config_entry.options)
        if self.config_entry.options.get(CONF_DEBUG_FILE_SAVE, False):
            path = self._debug_save_path
            Path(path).mkdir(parents=True, exist_ok=True)

            current_file = Path.open(f"{path}/{datatype}{int(round(time.time() * 1000))}.json", "w")
            if use_dumps:
                current_file.write(f"{json.dumps(data, indent=4)}")
            else:
                current_file.write(f"{data}")
            current_file.close()

    async def set_rlock_mode(self):
        """Set thread locking mode on init."""
        # In rare cases the ha-core system_info component runs in error when detecting the supervisor
        # See https://github.com/ReneNulschDE/mbapi2020/issues/126
        info = None
        try:
            info = await system_info.async_get_system_info(self._hass)
        except AttributeError:
            LOGGER.debug("WSL detection not possible. Error in HA-Core get_system_info. Force rlock mode.")

        if info and "WSL" not in str(info.get("os_version")):
            self._disable_rlock = False
            self.__lock = threading.RLock()
            LOGGER.debug("WSL not detected - running in rlock mode")
        else:
            self._disable_rlock = True
            self.__lock = None
            LOGGER.debug("WSL detected - rlock mode disabled")

        return info

    async def update_poll_states(self, vin: str):
        """Update the values for poll states, currently geofencing only."""

        if vin in self.cars:
            car = self.cars[vin]

            if not car.has_geofencing:
                return

            LOGGER.debug("start update_poll_states: %s", loghelper.Mask_VIN(vin))

            if car.geofence_events is None:
                car.geofence_events = GeofenceEvents()

            geofencing_violotions = await self.webapi.get_car_geofencing_violations(car.finorvin)
            if geofencing_violotions and len(geofencing_violotions) > 0:
                car.geofence_events.last_event_type = CarAttribute(
                    geofencing_violotions[-1].get("type"),
                    "VALID",
                    geofencing_violotions[-1].get("time"),
                )
                car.geofence_events.last_event_timestamp = CarAttribute(
                    geofencing_violotions[-1].get("time"),
                    "VALID",
                    geofencing_violotions[-1].get("time"),
                )
                car.geofence_events.last_event_zone = CarAttribute(
                    geofencing_violotions[-1].get("snapshot").get("name"),
                    "VALID",
                    geofencing_violotions[-1].get("time"),
                )
                car.has_geofencing = True
                car.geo_fencing_retry_counter = 0
            else:
                if car.geo_fencing_retry_counter >= GEOFENCING_MAX_RETRIES:
                    car.has_geofencing = False
                car.geo_fencing_retry_counter = car.geo_fencing_retry_counter + 1
