"""The MercedesME 2020 client."""
from __future__ import annotations

import json
import logging
from pathlib import Path
import threading
import time
import uuid

from aiohttp import ClientSession
from google.protobuf.json_format import MessageToJson

from custom_components.mbapi2020.proto import client_pb2
import custom_components.mbapi2020.proto.vehicle_commands_pb2 as pb2_commands
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import system_info
from homeassistant.helpers.event import async_call_later

from .car import (
    AUX_HEAT_OPTIONS,
    BINARY_SENSOR_OPTIONS,
    DOOR_OPTIONS,
    ELECTRIC_OPTIONS,
    LOCATION_OPTIONS,
    ODOMETER_OPTIONS,
    TIRE_OPTIONS,
    WINDOW_OPTIONS,
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
    Tires,
    Windows,
)
from .const import (
    CONF_DEBUG_FILE_SAVE,
    CONF_EXCLUDED_CARS,
    CONF_FT_DISABLE_CAPABILITY_CHECK,
    CONF_PIN,
    DEFAULT_CACHE_PATH,
    DEFAULT_COUNTRY_CODE,
    DEFAULT_LOCALE,
    DEFAULT_SOCKET_MIN_RETRY,
)
from .errors import WebsocketError
from .helper import LogHelper as loghelper
from .oauth import Oauth
from .webapi import WebApi
from .websocket import Websocket

LOGGER = logging.getLogger(__name__)

DEBUG_SIMULATE_PARTIAL_UPDATES_ONLY = False


class Client:  # pylint: disable-too-few-public-methods
    """define the client."""

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
        self._locale: str = DEFAULT_LOCALE
        self._country_code: str = DEFAULT_COUNTRY_CODE

        self.oauth: Oauth = Oauth(
            self._hass,
            session=session,
            region=self._region,
            config_entry=config_entry,
        )
        self.webapi: WebApi = WebApi(self._hass, session=session, oauth=self.oauth, region=self._region)
        self.websocket: Websocket = Websocket(self._hass, self.oauth, region=self._region)
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

    async def attempt_connect(self, callback_dataload_complete):
        """Attempt to connect to the socket (retrying later on fail)."""

        def on_data(data):
            """Define a handler to fire when the data is received."""

            msg_type = data.WhichOneof("msg")

            if msg_type == "vepUpdate":  # VEPUpdate
                LOGGER.debug("vepUpdate")
                return

            if msg_type == "vepUpdates":  # VEPUpdatesByVIN
                self._process_vep_updates(data)

                sequence_number = data.vepUpdates.sequence_number
                LOGGER.debug("vepUpdates Sequence: %s", sequence_number)
                ack_command = client_pb2.ClientMessage()
                ack_command.acknowledge_vep_updates_by_vin.sequence_number = sequence_number
                return ack_command

            if msg_type == "debugMessage":  # DebugMessage
                if data.debugMessage:
                    LOGGER.debug("debugMessage - Data: %s", data.debugMessage.message)

                return

            if msg_type == "service_status_update":
                LOGGER.debug(
                    "service_status_update - Data: %s",
                    MessageToJson(data, preserving_proto_field_name=True),
                )
                return

            if msg_type == "user_data_update":
                LOGGER.debug(
                    "user_data_update - Data: %s",
                    MessageToJson(data, preserving_proto_field_name=True),
                )
                return

            if msg_type == "user_vehicle_auth_changed_update":
                LOGGER.debug(
                    "user_vehicle_auth_changed_update - Data: %s",
                    MessageToJson(data, preserving_proto_field_name=True),
                )
                return

            if msg_type == "user_picture_update":
                LOGGER.debug(
                    "user_picture_update - Data: %s",
                    MessageToJson(data, preserving_proto_field_name=True),
                )
                return

            if msg_type == "user_pin_update":
                LOGGER.debug(
                    "user_pin_update - Data: %s",
                    MessageToJson(data, preserving_proto_field_name=True),
                )
                return

            if msg_type == "vehicle_updated":
                LOGGER.debug(
                    "vehicle_updated - Data: %s",
                    MessageToJson(data, preserving_proto_field_name=True),
                )
                return

            if msg_type == "preferred_dealer_change":
                LOGGER.debug(
                    "preferred_dealer_change - Data: %s",
                    MessageToJson(data, preserving_proto_field_name=True),
                )
                return

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
                if self._dataload_complete_fired:
                    return "aa0100"
                return

            if msg_type == "assigned_vehicles":
                self._process_assigned_vehicles(data)
                if self._dataload_complete_fired:
                    return "ba0100"
                return

            LOGGER.debug("Message Type not implemented: %s", msg_type)

        try:
            self._on_dataload_complete = callback_dataload_complete
            await self.websocket.async_connect(on_data)
        except WebsocketError as err:
            LOGGER.error("Error with the websocket connection: %s", err)
            async_call_later(
                self._hass,
                self._ws_reconnect_delay,
                self.websocket.async_connect(on_data),
            )

    def _build_car(self, received_car_data, update_mode):
        if received_car_data.get("vin") in self.excluded_cars:
            LOGGER.debug("CAR excluded: %s", loghelper.Mask_VIN(received_car_data.get("vin")))
            return

        if received_car_data.get("vin") not in self.cars:
            LOGGER.warning(
                "Flow Problem - VepUpdate for unknown car: %s",
                loghelper.Mask_VIN(received_car_data.get("vin")),
            )
            return

        car: Car = self.cars.get(received_car_data.get("vin"), Car(received_car_data.get("vin")))

        car.messages_received.update("p" if update_mode else "f")
        car._last_message_received = int(round(time.time() * 1000))

        if not update_mode:
            car._last_full_message = received_car_data

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
        # LOGGER.debug(
        #     "get_car_values %s for %s called",
        #     class_instance.name,
        #     loghelper.Mask_VIN(car_id),
        # )

        for option in options:
            if car_detail is not None:
                if not car_detail.get("attributes"):
                    LOGGER.debug(
                        "get_car_values %s has incomplete update set - attributes not found",
                        loghelper.Mask_VIN(car_id),
                    )
                    return

                curr = car_detail["attributes"].get(option)
                if curr is not None or option == "max_soc":
                    if option != "max_soc":
                        value = curr.get(
                            "value",
                            curr.get(
                                "int_value",
                                curr.get("double_value", curr.get("bool_value", 0)),
                            ),
                        )
                        status = curr.get("status", "VALID")
                        time_stamp = curr.get("timestamp", 0)
                        curr_unit = curr.get(
                            "distance_unit",
                            curr.get(
                                "ratio_unit",
                                curr.get(
                                    "clock_hour_unit",
                                    curr.get(
                                        "gas_consumption_unit",
                                        curr.get(
                                            "pressure_unit",
                                            curr.get(
                                                "electricity_consumption_unit",
                                                curr.get(
                                                    "distance_unit",
                                                    curr.get(
                                                        "combustion_consumption_unit",
                                                        curr.get("speed_unit", None),
                                                    ),
                                                ),
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        )
                        curr_display_value = curr.get("display_value", None)
                    else:
                        # special EQA/B max_soc handling
                        chargeprograms = car_detail["attributes"].get("chargePrograms")
                        if chargeprograms is not None:
                            time_stamp = chargeprograms.get("timestamp", 0)
                            charge_programs_value = chargeprograms.get("charge_programs_value")
                            if charge_programs_value is not None:
                                charge_program_parameters = charge_programs_value.get("charge_program_parameters")
                                if charge_program_parameters is not None and len(charge_program_parameters) > 0:
                                    value = charge_program_parameters[
                                        int(
                                            self._get_car_value(
                                                class_instance,
                                                "selectedChargeProgram",
                                                "value",
                                                0,
                                            )
                                        )
                                    ].get("max_soc")
                                    status = "VALID"
                                    curr_unit = "PERCENT"
                                    curr_display_value = value
                                else:
                                    # charge_program_parameters does not exists, continue with the next option
                                    continue
                            else:
                                # charge_programs_value does not exists, continue with the next option
                                continue
                        else:
                            # chargePrograms does not exists, continue with the next option
                            continue

                    curr_status = CarAttribute(
                        value,
                        status,
                        time_stamp,
                        display_value=curr_display_value,
                        unit=curr_unit,
                    )
                    # Set the value only if the timestamp is higher
                    if float(time_stamp) > float(self._get_car_value(class_instance, option, "ts", 0)):
                        setattr(class_instance, option, curr_status)
                    else:
                        LOGGER.warning(
                            "get_car_values %s older attribute %s data received. ignoring value.",
                            loghelper.Mask_VIN(car_id),
                            option,
                        )
                elif not update:
                    # Do not set status for non existing values on partial update
                    curr_status = CarAttribute(0, 4, 0)
                    setattr(class_instance, option, curr_status)
            else:
                setattr(class_instance, option, CarAttribute(0, -1, None))

        return class_instance

    def _get_car_value(self, class_instance, object_name, attrib_name, default_value):
        value = None

        value = getattr(
            getattr(class_instance, object_name, default_value),
            attrib_name,
            default_value,
        )
        return value

    def _process_vep_updates(self, data):
        LOGGER.debug("Start _process_vep_updates")

        self._write_debug_output(data, "vep")

        # Don't understand the protobuf dict errors --> convert to json
        vep_json = json.loads(MessageToJson(data, preserving_proto_field_name=True))
        cars = vep_json["vepUpdates"]["updates"]

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
            for car in self.cars.values():
                LOGGER.debug(
                    "_process_vep_updates - %s - complete: %s - %s",
                    loghelper.Mask_VIN(car.finorvin),
                    car.entry_setup_complete,
                    car.messages_received,
                )

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

            load_complete = True
            current_time = int(round(time.time() * 1000))
            for key, value in self.cars.items():
                LOGGER.debug(
                    "_process_assigned_vehicles - %s - %s - %s - %s",
                    loghelper.Mask_VIN(key),
                    value.entry_setup_complete,
                    value.messages_received,
                    current_time - value._last_message_received,
                )

                if value._last_message_received > 0 and current_time - value._last_message_received > 30000:
                    LOGGER.debug(
                        "No Full Update Message received - Force car entry setup complete for car %s",
                        loghelper.Mask_VIN(key),
                    )
                    value.entry_setup_complete = True

                if not value.entry_setup_complete:
                    load_complete = False

            if load_complete:
                self._on_dataload_complete()
                self._dataload_complete_fired = True

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
                                current_car._last_command_type = command_type
                                current_car._last_command_state = command_state
                                current_car._last_command_error_code = command_error_code
                                current_car._last_command_error_message = command_error_message
                                current_car._last_command_time_stamp = command.get("timestamp_in_ms", 0)

                                current_car.publish_updates()

    async def charge_program_configure(self, vin: str, program: int):
        """Send the selected charge program to the car."""
        if not self._is_car_feature_available(vin, "CHARGE_PROGRAM_CONFIGURE"):
            LOGGER.warning(
                "Can't set the charge program of the  car %s. VIN unknown or feature CHARGE_PROGRAM_CONFIGURE not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        LOGGER.debug("Start unlock with user provided pin")
        message = client_pb2.ClientMessage()
        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        charge_programm = pb2_commands.ChargeProgramConfigure()
        charge_programm.charge_program = program
        message.commandRequest.charge_program_configure.CopyFrom(charge_programm)

        await self.websocket.call(message.SerializeToString())
        return

    async def doors_unlock(self, vin: str, pin: str = ""):
        """Send the doors unlock command to the car."""
        if not self._is_car_feature_available(vin, "DOORS_UNLOCK"):
            LOGGER.warning(
                "Can't unlock car %s. VIN unknown or feature not availabe for this car.",
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
                "Can't unlock car %s. VIN unknown or feature not availabe for this car.",
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

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End Doors_unlock for vin %s", loghelper.Mask_VIN(vin))

    async def doors_lock(self, vin: str):
        """Send the doors lock command to the car."""
        LOGGER.info("Start Doors_lock for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "DOORS_LOCK"):
            LOGGER.warning(
                "Can't lock car %s. VIN unknown or feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.doors_lock.doors.extend([])

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End Doors_lock for vin %s", loghelper.Mask_VIN(vin))

    async def auxheat_configure(self, vin: str, time_selection: int, time_1: int, time_2: int, time_3: int):
        """Send the auxheat configure command to the car."""
        LOGGER.info("Start auxheat_configure for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "AUXHEAT_START"):
            LOGGER.warning(
                "Can't start auxheat for car %s. VIN unknown or feature not availabe for this car.",
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

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End auxheat_configure for vin %s", loghelper.Mask_VIN(vin))

    async def auxheat_start(self, vin: str):
        """Send the auxheat start command to the car."""
        LOGGER.info("Start auxheat start for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "AUXHEAT_START"):
            LOGGER.warning(
                "Can't start auxheat for car %s. VIN unknown or feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        auxheat_start = pb2_commands.AuxheatStart()
        message.commandRequest.auxheat_start.CopyFrom(auxheat_start)

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End auxheat start for vin %s", loghelper.Mask_VIN(vin))

    async def auxheat_stop(self, vin: str):
        """Send the auxheat stop command to the car."""
        LOGGER.info("Start auxheat_stop for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "AUXHEAT_STOP"):
            LOGGER.warning(
                "Can't stop auxheat for car %s. VIN unknown or feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        auxheat_stop = pb2_commands.AuxheatStop()
        message.commandRequest.auxheat_stop.CopyFrom(auxheat_stop)

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End auxheat_stop for vin %s", loghelper.Mask_VIN(vin))

    async def battery_max_soc_configure(self, vin: str, max_soc: int):
        """Send the maxsoc configure command to the car."""
        LOGGER.info(
            "Start battery_max_soc_configure to %s for vin %s",
            max_soc,
            loghelper.Mask_VIN(vin),
        )

        if not self._is_car_feature_available(vin, "BATTERY_MAX_SOC_CONFIGURE"):
            LOGGER.warning(
                "Can't configure battery_max_soc for car %s. VIN unknown or feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        charge_program_config = pb2_commands.ChargeProgramConfigure()
        charge_program_config.max_soc.value = max_soc
        message.commandRequest.charge_program_configure.CopyFrom(charge_program_config)

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End battery_max_soc_configure for vin %s", loghelper.Mask_VIN(vin))

    async def engine_start(self, vin: str):
        """Send the engine start command to the car."""
        LOGGER.info("Start engine start for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "ENGINE_START"):
            LOGGER.warning(
                "Can't start engine for car %s. VIN unknown or feature not availabe for this car.",
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

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End engine start for vin %s", loghelper.Mask_VIN(vin))

    async def engine_stop(self, vin: str):
        """Send the engine stop command to the car."""
        LOGGER.info("Start engine_stop for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "ENGINE_STOP"):
            LOGGER.warning(
                "Can't stop engine for car %s. VIN unknown or feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        engine_stop = pb2_commands.EngineStop()
        message.commandRequest.engine_stop.CopyFrom(engine_stop)

        await self.websocket.call(message.SerializeToString())
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
                "Can't start signaling for car %s. VIN unknown or feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.sigpos_start.light_type = 1
        message.commandRequest.sigpos_start.sigpos_type = 0

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End sigpos_start for vin %s", loghelper.Mask_VIN(vin))

    async def sunroof_open(self, vin: str):
        """Send a sunroof open command to the car."""
        LOGGER.info("Start sunroof_open for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "SUNROOF_OPEN"):
            LOGGER.warning(
                "Can't open the sunroof for car %s. VIN unknown or feature not availabe for this car.",
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

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End sunroof_open for vin %s", loghelper.Mask_VIN(vin))

    async def sunroof_close(self, vin: str):
        """Send a sunroof close command to the car."""
        LOGGER.info("Start sunroof_close for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "SUNROOF_CLOSE"):
            LOGGER.warning(
                "Can't close the sunroof for car %s. VIN unknown or feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        sunroof_close = pb2_commands.SunroofClose()
        message.commandRequest.sunroof_close.CopyFrom(sunroof_close)

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End sunroof_close for vin %s", loghelper.Mask_VIN(vin))

    async def preheat_start(self, vin: str):
        """Send a preconditioning start command to the car."""
        LOGGER.info("Start preheat_start for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "ZEV_PRECONDITIONING_START"):
            LOGGER.warning(
                "Can't start PreCond for car %s. VIN unknown or feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.zev_preconditioning_start.departure_time = 0
        message.commandRequest.zev_preconditioning_start.type = pb2_commands.ZEVPreconditioningType.now

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End preheat_start for vin %s", loghelper.Mask_VIN(vin))

    async def preheat_start_immediate(self, vin: str):
        """Send a preconditioning immediatestart command to the car."""
        LOGGER.info("Start preheat_start_immediate for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "ZEV_PRECONDITIONING_START"):
            LOGGER.warning(
                "Can't start PreCond for car %s. VIN unknown or feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.zev_preconditioning_start.departure_time = 0
        message.commandRequest.zev_preconditioning_start.type = pb2_commands.ZEVPreconditioningType.immediate

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End preheat_start_immediate for vin %s", loghelper.Mask_VIN(vin))

    async def preheat_start_departure_time(self, vin: str, departure_time: int):
        """Send a preconditioning start by time command to the car."""
        LOGGER.info("Start preheat_start_departure_time for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "ZEV_PRECONDITIONING_START"):
            LOGGER.warning(
                "Can't start PreCond for car %s. VIN unknown or feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.zev_preconditioning_start.departure_time = departure_time
        message.commandRequest.zev_preconditioning_start.type = pb2_commands.ZEVPreconditioningType.departure

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End preheat_start_departure_time for vin %s", loghelper.Mask_VIN(vin))

    async def preheat_stop(self, vin: str):
        """Send a preconditioning stop command to the car."""
        LOGGER.info("Start preheat_stop for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "ZEV_PRECONDITIONING_STOP"):
            LOGGER.warning(
                "Can't stop PreCond for car %s. VIN unknown or feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return
        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.zev_preconditioning_stop.type = pb2_commands.ZEVPreconditioningType.now

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End preheat_stop for vin %s", loghelper.Mask_VIN(vin))

    async def preheat_stop_departure_time(self, vin: str):
        """Send a preconditioning stop by time command to the car."""
        LOGGER.info("Start preheat_stop_departure_time for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "ZEV_PRECONDITIONING_STOP"):
            LOGGER.warning(
                "Can't stop PreCond for car %s. VIN unknown or feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return
        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.zev_preconditioning_stop.type = pb2_commands.ZEVPreconditioningType.departure

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End preheat_stop_departure_time for vin %s", loghelper.Mask_VIN(vin))

    async def windows_open(self, vin: str):
        """Send a window open command to the car."""
        LOGGER.info("Start windows_open for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "WINDOWS_OPEN"):
            LOGGER.warning(
                "Can't open the windows for car %s. VIN unknown or feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        if not self.pin:
            LOGGER.warning(
                "Can't open the windows - car %s. PIN not set. Please set the PIN -> Integration, Options",
                loghelper.Mask_VIN(vin),
            )
            return

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.windows_open.pin = self.pin

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End windows_open for vin %s", loghelper.Mask_VIN(vin))

    async def windows_close(self, vin: str):
        """Send a window close command to the car."""
        LOGGER.info("Start windows_close for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "WINDOWS_CLOSE"):
            LOGGER.warning(
                "Can't close the windows for car %s. VIN unknown or feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        windows_close = pb2_commands.WindowsClose()
        message.commandRequest.windows_close.CopyFrom(windows_close)

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End windows_close for vin %s", loghelper.Mask_VIN(vin))

    async def windows_move(self, vin: str, front_left: int, front_right: int, rear_left: int, rear_right: int):
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
                "Can't move windows for car %s. VIN unknown or feature not availabe for this car.",
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

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End windows_move for vin %s", loghelper.Mask_VIN(vin))

    def _is_car_feature_available(self, vin: str, feature: str) -> bool:
        if self.config_entry.options.get(CONF_FT_DISABLE_CAPABILITY_CHECK, False):
            return True

        current_car = self.cars.get(vin)

        if current_car:
            return current_car.features.get(feature, False)

        return False

    def _write_debug_output(self, data, datatype):
        if self.config_entry.options.get(CONF_DEBUG_FILE_SAVE, False):
            # LOGGER.debug("Start _write_debug_output")

            path = self._debug_save_path
            Path(path).mkdir(parents=True, exist_ok=True)

            current_file = open(f"{path}/{datatype}{int(round(time.time() * 1000))}", "wb")
            current_file.write(data.SerializeToString())
            current_file.close()

            self.write_debug_json_output(MessageToJson(data, preserving_proto_field_name=True), datatype)

    def write_debug_json_output(self, data, datatype):
        """Write text to files based on datatype."""
        # LOGGER.debug(self.config_entry.options)
        if self.config_entry.options.get(CONF_DEBUG_FILE_SAVE, False):
            path = self._debug_save_path
            Path(path).mkdir(parents=True, exist_ok=True)

            current_file = open(f"{path}/{datatype}{int(round(time.time() * 1000))}.json", "w")
            current_file.write(f"{data}")
            current_file.close()

    async def _set_rlock_mode(self):
        # In rare cases the ha-core system_info component runs in error when detecting the supervisor
        # See https://github.com/ReneNulschDE/mbapi2020/issues/126
        info = None
        try:
            info = await system_info.async_get_system_info(self._hass)
        except Exception:
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

            LOGGER.debug("start update_poll_states: %s", vin)

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
            else:
                car.has_geofencing = False

            # return geofencing_violotions
