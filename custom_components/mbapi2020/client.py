"""The MercedesME 2020 client."""
import json
import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from aiohttp import ClientSession
from google.protobuf.json_format import MessageToJson
from homeassistant.core import HomeAssistant
from homeassistant.helpers import system_info
from homeassistant.helpers.event import async_call_later

import custom_components.mbapi2020.proto.client_pb2 as client_pb2
import custom_components.mbapi2020.proto.vehicle_commands_pb2 as pb2_commands

from .api import API
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
    CONF_COUNTRY_CODE,
    CONF_DEBUG_FILE_SAVE,
    CONF_EXCLUDED_CARS,
    CONF_FT_DISABLE_CAPABILITY_CHECK,
    CONF_LOCALE,
    CONF_PIN,
    DEFAULT_CACHE_PATH,
    DEFAULT_COUNTRY_CODE,
    DEFAULT_LOCALE,
    DEFAULT_SOCKET_MIN_RETRY,
    DEFAULT_TOKEN_PATH,
)
from .errors import WebsocketError
from .oauth import Oauth
from .websocket import Websocket

LOGGER = logging.getLogger(__name__)

DEBUG_SIMULATE_PARTIAL_UPDATES_ONLY = False


class Client:  # pylint: disable-too-few-public-methods
    """define the client."""

    def __init__(
        self,
        *,
        session: Optional[ClientSession] = None,
        hass: Optional[HomeAssistant] = None,
        config_entry=None,
        cache_path: Optional[str] = None,
        region: str = None,
    ) -> None:
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

        if self.config_entry:
            if self.config_entry.options:
                self._country_code = self.config_entry.options.get(CONF_COUNTRY_CODE, DEFAULT_COUNTRY_CODE)
                self._locale = self.config_entry.options.get(CONF_LOCALE, DEFAULT_LOCALE)

        self.oauth: Oauth = Oauth(
            session=session,
            locale=self._locale,
            country_code=self._country_code,
            cache_path=self._hass.config.path(DEFAULT_TOKEN_PATH),
            region=self._region,
        )
        self.api: API = API(session=session, oauth=self.oauth, region=self._region)
        self.websocket: Websocket = Websocket(self._hass, self.oauth, region=self._region)
        self.cars = []

    @property
    def pin(self) -> str:
        if self.config_entry:
            if self.config_entry.options:
                return self.config_entry.options.get(CONF_PIN, None)
        return None

    @property
    def excluded_cars(self):
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
                LOGGER.debug("service_status_update - Data: %s", MessageToJson(data, preserving_proto_field_name=True))
                return

            if msg_type == "user_data_update":
                LOGGER.debug("user_data_update - Data: %s", MessageToJson(data, preserving_proto_field_name=True))
                return

            if msg_type == "user_vehicle_auth_changed_update":
                LOGGER.debug(
                    "user_vehicle_auth_changed_update - Data: %s", MessageToJson(data, preserving_proto_field_name=True)
                )
                return

            if msg_type == "user_picture_update":
                LOGGER.debug("user_picture_update - Data: %s", MessageToJson(data, preserving_proto_field_name=True))
                return

            if msg_type == "user_pin_update":
                LOGGER.debug("user_pin_update - Data: %s", MessageToJson(data, preserving_proto_field_name=True))
                return

            if msg_type == "vehicle_updated":
                LOGGER.debug("vehicle_updated - Data: %s", MessageToJson(data, preserving_proto_field_name=True))
                return

            if msg_type == "preferred_dealer_change":
                LOGGER.debug(
                    "preferred_dealer_change - Data: %s", MessageToJson(data, preserving_proto_field_name=True)
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
                return

            if msg_type == "assigned_vehicles":
                self._process_assigned_vehicles(data)
                return

            if msg_type == "service_status_updates":
                LOGGER.debug("service_status_updates - Data: %s", MessageToJson(data, preserving_proto_field_name=True))
                self._write_debug_output(data, "ssu")
                return

            LOGGER.debug("Message Type not implemented: %s", msg_type)

        try:
            self._on_dataload_complete = callback_dataload_complete
            await self.websocket.async_connect(on_data)
        except (WebsocketError) as err:
            LOGGER.error("Error with the websocket connection: %s", err)
            self._ws_reconnect_delay = self._ws_reconnect_delay
            async_call_later(self._hass, self._ws_reconnect_delay, self.websocket.async_connect(on_data))

    def _build_car(self, received_car_data, update_mode):

        if received_car_data.get("vin") in self.excluded_cars:
            LOGGER.debug("CAR excluded: %s", received_car_data.get("vin"))
            return

        car = self._get_car(received_car_data.get("vin"))

        car.messages_received.update("p" if update_mode else "f")
        car._last_message_received = int(round(time.time() * 1000))

        car.odometer = self._get_car_values(
            received_car_data,
            car.finorvin,
            Odometer() if not car.odometer else car.odometer,
            ODOMETER_OPTIONS,
            update_mode,
        )

        car.tires = self._get_car_values(
            received_car_data, car.finorvin, Tires() if not car.tires else car.tires, TIRE_OPTIONS, update_mode
        )

        car.doors = self._get_car_values(
            received_car_data, car.finorvin, Doors() if not car.doors else car.doors, DOOR_OPTIONS, update_mode
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
            received_car_data, car.finorvin, Windows() if not car.windows else car.windows, WINDOW_OPTIONS, update_mode
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

        # _LOGGER.debug("_get_cars - Feature Check: aux_heat:%s ", {car.features.aux_heat})
        # if car.features.aux_heat:
        #     car.auxheat = self._get_car_values(
        #         api_result, car.finorvin, Auxheat(), AUX_HEAT_OPTIONS, update_mode)

        # _LOGGER.debug("_get_cars - Feature Check: charging_clima_control:%s ", {car.features.charging_clima_control})
        # if car.features.charging_clima_control:
        #     car.precond = self._get_car_values(
        #         api_result, car.finorvin, Precond(), PRE_COND_OPTIONS, update_mode)

        # _LOGGER.debug("_get_cars - Feature Check: remote_engine_start:%s ", {car.features.remote_engine_start})
        # if car.features.remote_engine_start:
        #     car.RemoteStart = self._get_car_values(
        #         api_result, car.finorvin, RemoteStart(), RemoteStart_OPTIONS, update_mode)

        # _LOGGER.debug("_get_cars - Feature Check: CarAlarm:%s ", {car.features.CarAlarm})
        # if car.features.CarAlarm:
        #     car.CarAlarm = self._get_car_values(
        #         api_result, car.finorvin, CarAlarm(), CarAlarm_OPTIONS, update_mode)

        if not update_mode:
            car.entry_setup_complete = True

        # Nimm jedes car (item) aus self.cars ausser es ist das aktuelle dann nimm car
        self.cars = [car if item.finorvin == car.finorvin else item for item in self.cars]

    def _get_car_values(self, car_detail, car_id, class_instance, options, update):
        LOGGER.debug("get_car_values %s for %s called", class_instance.name, car_id)

        for option in options:
            if car_detail is not None:
                if not car_detail.get("attributes"):
                    LOGGER.debug("get_car_values %s has incomplete update set - attributes not found", car_id)
                    return

                curr = car_detail["attributes"].get(option)
                if curr is not None:
                    value = curr.get(
                        "value", curr.get("int_value", curr.get("double_value", curr.get("bool_value", -1)))
                    )
                    status = curr.get("status", "VALID")
                    time_stamp = curr.get("timestamp", 0)
                    curr_status = CarAttribute(
                        value,
                        status,
                        time_stamp,
                        distance_unit=curr.get("distance_unit", None),
                        display_value=curr.get("display_value", None),
                        unit=curr.get(
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
                                                        "combustion_consumption_unit", curr.get("speed_unit", None)
                                                    ),
                                                ),
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    )
                    # Set the value only if the timestamp is higher
                    if float(time_stamp) > float(self._get_car_value(class_instance, option, "ts", 0)):
                        setattr(class_instance, option, curr_status)
                    else:
                        LOGGER.warning(
                            "get_car_values %s older attribute %s data received. ignoring value.", car_id, option
                        )
                else:
                    # Do not set status for non existing values on partial update
                    if not update:
                        curr_status = CarAttribute(0, 4, 0)
                        setattr(class_instance, option, curr_status)
            else:
                setattr(class_instance, option, CarAttribute(-1, -1, None))

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
                LOGGER.debug("DEBUG_SIMULATE_PARTIAL_UPDATES_ONLY mode. %s", vin)

            if current_car.get("full_update") is True:
                LOGGER.debug("Full Update. %s", vin)
                if not self._disable_rlock:
                    with self.__lock:
                        self._build_car(current_car, update_mode=False)
                else:
                    self._build_car(current_car, update_mode=False)

            else:
                LOGGER.debug("Partial Update. %s", vin)
                if not self._disable_rlock:
                    with self.__lock:
                        self._build_car(current_car, update_mode=True)
                else:
                    self._build_car(current_car, update_mode=True)

            if self._dataload_complete_fired:
                current_car = self._get_car(vin)

                if current_car:
                    current_car.publish_updates()

        if not self._dataload_complete_fired:
            for car in self.cars:
                LOGGER.debug(
                    "_process_vep_updates - %s - complete: %s - %s",
                    car.finorvin,
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

                        _car = self._get_car(vin)

                        if _car is None:
                            current_car = Car()
                            current_car.finorvin = vin
                            current_car.licenseplate = vin
                            self.cars.append(current_car)
            else:
                for vin in data.assigned_vehicles.vins:

                    if vin in self.excluded_cars:
                        continue

                    _car = self._get_car(vin)

                    if _car is None:
                        current_car = Car()
                        current_car.finorvin = vin
                        current_car.licenseplate = vin
                        self.cars.append(current_car)

            load_complete = True
            current_time = int(round(time.time() * 1000))
            for car in self.cars:
                LOGGER.debug(
                    "_process_assigned_vehicles - %s - %s - %s - %s",
                    car.finorvin,
                    car.entry_setup_complete,
                    car.messages_received,
                    current_time - car._last_message_received,
                )

                if car._last_message_received > 0 and current_time - car._last_message_received > 30000:
                    LOGGER.debug(
                        "No Full Update Message received - Force car entry setup complete for car %s", car.finorvin
                    )
                    car.entry_setup_complete = True

                if not car.entry_setup_complete:
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

                            current_car = self._get_car(vin)

                            if current_car:
                                current_car._last_command_type = command_type
                                current_car._last_command_state = command_state
                                current_car._last_command_error_code = command_error_code
                                current_car._last_command_error_message = command_error_message
                                current_car._last_command_time_stamp = command.get("timestamp_in_ms", 0)

                                current_car.publish_updates()

    async def doors_unlock(self, vin: str):

        if not self.is_car_feature_available(vin, "DOORS_UNLOCK"):
            LOGGER.warning("Can't unlock car %s. VIN unknown or feature not availabe for this car.", vin)
            return

        if self.pin is None:
            LOGGER.warning("Can't unlock car %s. PIN not set. Please set the PIN -> Integration, Options ", vin)
            return

        await self.doors_unlock_with_pin(vin, self.pin)

    async def doors_unlock_with_pin(self, vin: str, pin: str):
        LOGGER.info("Start Doors_unlock_with_pin for vin %s", vin)

        if not self.is_car_feature_available(vin, "DOORS_UNLOCK"):
            LOGGER.warning("Can't unlock car %s. VIN unknown or feature not availabe for this car.", vin)
            return

        message = client_pb2.ClientMessage()

        if not pin:
            LOGGER.warning("Can't unlock car %s. Pin is required.", vin)
            return

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.doors_unlock.pin = pin

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End Doors_unlock for vin %s", vin)

    async def doors_lock(self, vin: str):
        LOGGER.info("Start Doors_lock for vin %s", vin)

        if not self.is_car_feature_available(vin, "DOORS_LOCK"):
            LOGGER.warning("Can't lock car %s. VIN unknown or feature not availabe for this car.", vin)
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.doors_lock.doors.extend([])

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End Doors_lock for vin %s", vin)

    async def auxheat_configure(self, vin: str, time_selection: int, time_1: int, time_2: int, time_3: int):
        LOGGER.info("Start auxheat_configure for vin %s", vin)

        if not self.is_car_feature_available(vin, "AUXHEAT_START"):
            LOGGER.warning("Can't start auxheat for car %s. VIN unknown or feature not availabe for this car.", vin)
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
        LOGGER.info("End auxheat_configure for vin %s", vin)

    async def auxheat_start(self, vin: str):
        LOGGER.info("Start auxheat start for vin %s", vin)

        if not self.is_car_feature_available(vin, "AUXHEAT_START"):
            LOGGER.warning("Can't start auxheat for car %s. VIN unknown or feature not availabe for this car.", vin)
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        auxheat_start = pb2_commands.AuxheatStart()
        message.commandRequest.auxheat_start.CopyFrom(auxheat_start)

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End auxheat start for vin %s", vin)

    async def auxheat_stop(self, vin: str):
        LOGGER.info("Start auxheat_stop for vin %s", vin)

        if not self.is_car_feature_available(vin, "AUXHEAT_STOP"):
            LOGGER.warning("Can't stop auxheat for car %s. VIN unknown or feature not availabe for this car.", vin)
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        auxheat_stop = pb2_commands.AuxheatStop()
        message.commandRequest.auxheat_stop.CopyFrom(auxheat_stop)

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End auxheat_stop for vin %s", vin)

    async def battery_max_soc_configure(self, vin: str, max_soc: int):
        LOGGER.info("Start battery_max_soc_configure to %s for vin %s", max_soc, vin)

        if not self.is_car_feature_available(vin, "BATTERY_MAX_SOC_CONFIGURE"):
            LOGGER.warning(
                "Can't configure battery_max_soc for car %s. VIN unknown or feature not availabe for this car.", vin
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        charge_program_config = pb2_commands.ChargeProgramConfigure()
        charge_program_config.max_soc.value = max_soc
        message.commandRequest.charge_program_configure.CopyFrom(charge_program_config)

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End battery_max_soc_configure for vin %s", vin)

    async def engine_start(self, vin: str):
        LOGGER.info("Start engine start for vin %s", vin)

        if not self.is_car_feature_available(vin, "ENGINE_START"):
            LOGGER.warning("Can't start engine for car %s. VIN unknown or feature not availabe for this car.", vin)
            return

        message = client_pb2.ClientMessage()

        if self.pin is None:
            LOGGER.warning("Can't start the car %s. PIN not set. Please set the PIN -> Integration, Options ", vin)
            return

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.engine_start.pin = self.pin

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End engine start for vin %s", vin)

    async def engine_stop(self, vin: str):
        LOGGER.info("Start engine_stop for vin %s", vin)

        if not self.is_car_feature_available(vin, "ENGINE_STOP"):
            LOGGER.warning("Can't stop engine for car %s. VIN unknown or feature not availabe for this car.", vin)
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        engine_stop = pb2_commands.EngineStop()
        message.commandRequest.engine_stop.CopyFrom(engine_stop)

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End engine_stop for vin %s", vin)

    async def send_route_to_car(
        self, vin: str, title: str, latitude: float, longitude: float, city: str, postcode: str, street: str
    ):
        LOGGER.info("Start send_route_to_car for vin %s", vin)

        await self.api.send_route_to_car(vin, title, latitude, longitude, city, postcode, street)

        LOGGER.info("End send_route_to_car for vin %s", vin)

    async def sigpos_start(self, vin: str):
        LOGGER.info("Start sigpos_start for vin %s", vin)

        if not self.is_car_feature_available(vin, "SIGPOS_START"):
            LOGGER.warning("Can't start signaling for car %s. VIN unknown or feature not availabe for this car.", vin)
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.sigpos_start.light_type = 1
        message.commandRequest.sigpos_start.sigpos_type = 0

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End sigpos_start for vin %s", vin)

    async def sunroof_open(self, vin: str):
        LOGGER.info("Start sunroof_open for vin %s", vin)

        if not self.is_car_feature_available(vin, "SUNROOF_OPEN"):
            LOGGER.warning("Can't open the sunroof for car %s. VIN unknown or feature not availabe for this car.", vin)
            return

        message = client_pb2.ClientMessage()

        if self.pin is None:
            LOGGER.warning(
                "Can't open the sunroof - car %s. PIN not set. Please set the PIN -> Integration, Options ", vin
            )
            return

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.sunroof_open.pin = self.pin

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End sunroof_open for vin %s", vin)

    async def sunroof_close(self, vin: str):
        LOGGER.info("Start sunroof_close for vin %s", vin)

        if not self.is_car_feature_available(vin, "SUNROOF_CLOSE"):
            LOGGER.warning("Can't close the sunroof for car %s. VIN unknown or feature not availabe for this car.", vin)
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        sunroof_close = pb2_commands.SunroofClose()
        message.commandRequest.sunroof_close.CopyFrom(sunroof_close)

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End sunroof_close for vin %s", vin)

    async def preheat_start(self, vin: str):
        LOGGER.info("Start preheat_start for vin %s", vin)

        if not self.is_car_feature_available(vin, "ZEV_PRECONDITIONING_START"):
            LOGGER.warning("Can't start PreCond for car %s. VIN unknown or feature not availabe for this car.", vin)
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.zev_preconditioning_start.departure_time = 0
        message.commandRequest.zev_preconditioning_start.type = pb2_commands.ZEVPreconditioningType.now

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End preheat_start for vin %s", vin)

    async def preheat_start_immediate(self, vin: str):
        LOGGER.info("Start preheat_start_immediate for vin %s", vin)

        if not self.is_car_feature_available(vin, "ZEV_PRECONDITIONING_START"):
            LOGGER.warning("Can't start PreCond for car %s. VIN unknown or feature not availabe for this car.", vin)
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.zev_preconditioning_start.departure_time = 0
        message.commandRequest.zev_preconditioning_start.type = pb2_commands.ZEVPreconditioningType.immediate

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End preheat_start_immediate for vin %s", vin)

    async def preheat_start_departure_time(self, vin: str, departure_time: int):
        LOGGER.info("Start preheat_start_departure_time for vin %s", vin)

        if not self.is_car_feature_available(vin, "ZEV_PRECONDITIONING_START"):
            LOGGER.warning("Can't start PreCond for car %s. VIN unknown or feature not availabe for this car.", vin)
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.zev_preconditioning_start.departure_time = departure_time
        message.commandRequest.zev_preconditioning_start.type = pb2_commands.ZEVPreconditioningType.departure

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End preheat_start_departure_time for vin %s", vin)

    async def preheat_stop(self, vin: str):
        LOGGER.info("Start preheat_stop for vin %s", vin)

        if not self.is_car_feature_available(vin, "ZEV_PRECONDITIONING_STOP"):
            LOGGER.warning("Can't stop PreCond for car %s. VIN unknown or feature not availabe for this car.", vin)
            return
        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.zev_preconditioning_stop.type = pb2_commands.ZEVPreconditioningType.now

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End preheat_stop for vin %s", vin)

    async def windows_open(self, vin: str):
        LOGGER.info("Start windows_open for vin %s", vin)

        if not self.is_car_feature_available(vin, "WINDOWS_OPEN"):
            LOGGER.warning("Can't open the windows for car %s. VIN unknown or feature not availabe for this car.", vin)
            return

        message = client_pb2.ClientMessage()

        if self.pin is None:
            LOGGER.warning(
                "Can't open the windows - car %s. PIN not set. Please set the PIN -> Integration, Options", vin
            )
            return

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.windows_open.pin = self.pin

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End windows_open for vin %s", vin)

    async def windows_close(self, vin: str):
        LOGGER.info("Start windows_close for vin %s", vin)

        if not self.is_car_feature_available(vin, "WINDOWS_CLOSE"):
            LOGGER.warning("Can't close the windows for car %s. VIN unknown or feature not availabe for this car.", vin)
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        windows_close = pb2_commands.WindowsClose()
        message.commandRequest.windows_close.CopyFrom(windows_close)

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End windows_close for vin %s", vin)

    def is_car_feature_available(self, vin: str, feature: str) -> bool:

        if self.config_entry.options.get(CONF_FT_DISABLE_CAPABILITY_CHECK, False):
            return True

        current_car = self._get_car(vin)

        if current_car:
            return getattr(current_car.features, feature, False)

        return False

    def _write_debug_output(self, data, datatype):

        if self.config_entry.options.get(CONF_DEBUG_FILE_SAVE, False):
            LOGGER.debug("Start _write_debug_output")

            path = self._debug_save_path
            Path(path).mkdir(parents=True, exist_ok=True)

            current_file = open(f"{path}/{datatype}{int(round(time.time() * 1000))}", "wb")
            current_file.write(data.SerializeToString())
            current_file.close()

            self.write_debug_json_output(MessageToJson(data, preserving_proto_field_name=True), datatype)

    def write_debug_json_output(self, data, datatype):

        # LOGGER.debug(self.config_entry.options)
        if self.config_entry.options.get(CONF_DEBUG_FILE_SAVE, False):
            path = self._debug_save_path
            Path(path).mkdir(parents=True, exist_ok=True)

            current_file = open(f"{path}/{datatype}{int(round(time.time() * 1000))}.json", "w")
            current_file.write(f"{data}")
            current_file.close()

    def _get_car(self, vin: str):
        for car in self.cars:
            if car.finorvin == vin:
                return car

    async def set_rlock_mode(self):
        info = await system_info.async_get_system_info(self._hass)

        if not "WSL" in info.get("os_version"):
            self._disable_rlock = False
            self.__lock = threading.RLock()
            LOGGER.debug("WSL not detected - running in rlock mode")
        else:
            self._disable_rlock = True
            self.__lock = None
            LOGGER.debug("WSL detected - rlock mode disabled")

        return info

    async def update_poll_states(self, vin: str = None):

        LOGGER.debug("start update_poll_states")
        for car in self.cars:

            if car.geofence_events is None:
                car.geofence_events = GeofenceEvents()

            if not vin is None:
                if not car.finorvin == vin:
                    continue

            geofencing_violotions = await self.api.get_car_geofencing_violations(car.finorvin)
            if geofencing_violotions:
                if len(geofencing_violotions) > 0:
                    car.geofence_events.last_event_type = CarAttribute(
                        geofencing_violotions[-1].get("type"), "VALID", geofencing_violotions[-1].get("time")
                    )
                    car.geofence_events.last_event_timestamp = CarAttribute(
                        geofencing_violotions[-1].get("time"), "VALID", geofencing_violotions[-1].get("time")
                    )
                    car.geofence_events.last_event_zone = CarAttribute(
                        geofencing_violotions[-1].get("snapshot").get("name"),
                        "VALID",
                        geofencing_violotions[-1].get("time"),
                    )
