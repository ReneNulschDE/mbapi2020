import asyncio
import json
import logging
import time
import uuid

from aiohttp import ClientSession
from multiprocessing import RLock
from pathlib import Path
from typing import Optional

from google.protobuf.json_format import MessageToJson

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    callback,
    HomeAssistant
)
from homeassistant.helpers.event import async_call_later

from .car import *

from .api import API
from .errors import WebsocketError
from .oauth import Oauth
from .websocket import Websocket

from .const import (
    CONF_COUNTRY_CODE,
    CONF_EXCLUDED_CARS,
    CONF_LOCALE,
    CONF_PIN,
    DEFAULT_LOCALE,
    DEFAULT_COUNTRY_CODE,
    DEFAULT_CACHE_PATH,
    DEFAULT_TOKEN_PATH,
    DEFAULT_SOCKET_MIN_RETRY,
)

import custom_components.mbapi2020.proto.client_pb2 as client_pb2
import custom_components.mbapi2020.proto.vehicle_events_pb2 as vehicle_events_pb2
import custom_components.mbapi2020.proto.vehicle_commands_pb2 as pb2_commands

LOGGER = logging.getLogger(__name__)

DEBUG_SIMULATE_PARTIAL_UPDATES_ONLY = False
WRITE_DEBUG_OUTPUT = False

class Client: # pylint: disable-too-few-public-methods
    """ define the client. """
    def __init__(
        self,
        *,
        session: Optional[ClientSession] = None,
        hass: Optional[HomeAssistant] = None,
        config_entry = None,
        cache_path: Optional[str] = None,
        region: str = None
    ) -> None:
        self._ws_reconnect_delay = DEFAULT_SOCKET_MIN_RETRY
        self._hass = hass
        self._region = region
        self._on_dataload_complete = None
        self._dataload_complete_fired = False
        self.__lock = RLock()
        self._debug_save_path = self._hass.config.path(DEFAULT_CACHE_PATH)
        self._config_entry = config_entry
        self._locale: str = DEFAULT_LOCALE
        self._country_code: str = DEFAULT_COUNTRY_CODE

        if self._config_entry:
            if self._config_entry.options:
                self._country_code = self._config_entry.options.get(CONF_COUNTRY_CODE, DEFAULT_COUNTRY_CODE)
                self._locale = self._config_entry.options.get(CONF_LOCALE, DEFAULT_LOCALE)
                

        self.oauth: Oauth = Oauth(session=session, locale=self._locale, country_code=self._country_code, cache_path=self._hass.config.path(DEFAULT_TOKEN_PATH), region=self._region)
        self.api: API = API(session=session, oauth=self.oauth, region=self._region)
        self.websocket: Websocket = Websocket(self._hass, self.oauth, region=self._region)
        self.cars = []

    @property 
    def pin(self) -> str:
        if self._config_entry:
            if self._config_entry.options:
                return self._config_entry.options.get(CONF_PIN, None)
        return None

    @property 
    def excluded_cars(self):
        if self._config_entry:
            if self._config_entry.options:
                return self._config_entry.options.get(CONF_EXCLUDED_CARS, [])
        return []

    async def _attempt_connect(self, callback_dataload_complete):
        """Attempt to connect to the socket (retrying later on fail)."""

        def on_data(data):
            """Define a handler to fire when the data is received."""

            msg_type = data.WhichOneof('msg')
            
            if (msg_type == "vepUpdate"): #VEPUpdate
                LOGGER.debug("vepUpdate")
                return

            if (msg_type == "vepUpdates"): #VEPUpdatesByVIN

                self._process_vep_updates(data)

                sequence_number = data.vepUpdates.sequence_number
                LOGGER.debug(f"vepUpdates Sequence: {sequence_number}")
                ack_command = client_pb2.ClientMessage()
                ack_command.acknowledge_vep_updates_by_vin.sequence_number = sequence_number
                return ack_command

            if (msg_type == "debugMessage"): #DebugMessage
                
                if data.debugMessage:
                    LOGGER.debug(f"debugMessage - Data: {data.debugMessage.message}")

                return

            if (msg_type == "service_status_update"):
                LOGGER.debug(f"service_status_update - Data: {MessageToJson(data, preserving_proto_field_name=True)}")
                return

            if (msg_type == "user_data_update"):
                LOGGER.debug(f"user_data_update - Data: {MessageToJson(data, preserving_proto_field_name=True)}")
                return

            if (msg_type == "user_vehicle_auth_changed_update"):
                LOGGER.debug(f"user_vehicle_auth_changed_update - Data: {MessageToJson(data, preserving_proto_field_name=True)}")
                return

            if (msg_type == "user_picture_update"):
                LOGGER.debug(f"user_picture_update - Data: {MessageToJson(data, preserving_proto_field_name=True)}")
                return

            if (msg_type == "user_pin_update"):
                LOGGER.debug(f"user_pin_update - Data: {MessageToJson(data, preserving_proto_field_name=True)}")
                return

            if (msg_type == "vehicle_updated"):
                LOGGER.debug(f"vehicle_updated - Data: {MessageToJson(data, preserving_proto_field_name=True)}")
                return

            if (msg_type == "preferred_dealer_change"):
                LOGGER.debug(f"preferred_dealer_change - Data: {MessageToJson(data, preserving_proto_field_name=True)}")
                return

            if (msg_type == "apptwin_command_status_updates_by_vin"):
                LOGGER.debug(f"apptwin_command_status_updates_by_vin - Data: {MessageToJson(data, preserving_proto_field_name=True)}")
                
                self._process_apptwin_command_status_updates_by_vin(data)

                sequence_number = data.apptwin_command_status_updates_by_vin.sequence_number
                LOGGER.debug("apptwin_command_status_updates_by_vin: %s", sequence_number)
                ack_command = client_pb2.ClientMessage()
                ack_command.acknowledge_apptwin_command_status_update_by_vin.sequence_number = sequence_number
                return ack_command


            if (msg_type == "apptwin_pending_command_request"):
                #LOGGER.debug(f"apptwin_pending_command_request - Data: {MessageToJson(data, preserving_proto_field_name=True)}")
                return

            if (msg_type == "assigned_vehicles"):
                #LOGGER.debug("assigned_vehicles")
                
                self._process_assigned_vehicles(data)
                
                return

            LOGGER.debug(f"Message Type not implemented - {msg_type}")

        try:
            self._on_dataload_complete = callback_dataload_complete
            await self.websocket.async_connect(on_data)
        except (WebsocketError) as err:
            LOGGER.error("Error with the websocket connection: %s", err)
            self._ws_reconnect_delay = self._ws_reconnect_delay
            async_call_later(self._hass, self._ws_reconnect_delay, self.websocket.async_connect(on_data))


    def _build_car(self, c, update_mode):

        if c.get("vin") in self.excluded_cars:
            LOGGER.debug(f"CAR {c.get('vin')} is excluded.")
            return

        car = next((item for item in self.cars if c.get("vin") == item.finorvin), None)

        car._messages_received.update("p" if update_mode else "f")
        car._last_message_received = int(round(time.time() * 1000))

        car.odometer = self._get_car_values(
            c, car.finorvin, Odometer() if not car.odometer else car.odometer, ODOMETER_OPTIONS, update_mode)

        car.tires = self._get_car_values(
            c, car.finorvin, Tires() if not car.tires else car.tires, TIRE_OPTIONS, update_mode)

        car.doors = self._get_car_values(
            c, car.finorvin, Doors() if not car.doors else car.doors, DOOR_OPTIONS, update_mode)

        car.location = self._get_car_values(
            c, car.finorvin,
            Location() if not car.location else car.location, LOCATION_OPTIONS, update_mode)

        car.binarysensors = self._get_car_values(
            c, car.finorvin,
            Binary_Sensors() if not car.binarysensors else car.binarysensors, BINARY_SENSOR_OPTIONS, update_mode)

        car.windows = self._get_car_values(
            c, car.finorvin, Windows() if not car.windows else car.windows, WINDOW_OPTIONS, update_mode)

        car.electric = self._get_car_values(
            c, car.finorvin, Electric() if not car.electric else car.electric, ELECTRIC_OPTIONS, update_mode)

        car.auxheat = self._get_car_values(
            c, car.finorvin, Auxheat() if not car.auxheat else car.auxheat, AUX_HEAT_OPTIONS, update_mode)

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
        #     car.remote_start = self._get_car_values(
        #         api_result, car.finorvin, Remote_Start(), REMOTE_START_OPTIONS, update_mode)

        # _LOGGER.debug("_get_cars - Feature Check: car_alarm:%s ", {car.features.car_alarm})
        # if car.features.car_alarm:
        #     car.car_alarm = self._get_car_values(
        #         api_result, car.finorvin, Car_Alarm(), CAR_ALARM_OPTIONS, update_mode)

        if not update_mode:
            car._entry_setup_complete = True

        # Nimm jedes car (item) aus self.cars ausser es ist das aktuelle dann nimm car         
        self.cars = [car if item.finorvin == car.finorvin else item for item in self.cars]
        


    def _get_car_values(self, car_detail, car_id, classInstance, options, update):
        LOGGER.debug("get_car_values %s for %s called",
                      classInstance.name, car_id)

        for option in options:
            if car_detail is not None:
                if not car_detail.get("attributes"):
                    LOGGER.debug(f"get_car_values {car_id} has incomplete update set - attributes not found")
                    return

                curr = car_detail["attributes"].get(option)
                if curr is not None:
                    value = curr.get("value",curr.get("int_value",curr.get("double_value",curr.get("bool_value",-1))))
                    status = curr.get("status", "VALID")
                    ts = curr.get("timestamp", 0)
                    curr_status = CarAttribute(
                        value,
                        status,
                        ts,
                        distance_unit= curr.get("distance_unit", None),
                        display_value= curr.get("display_value", None),
                        unit = curr.get("distance_unit",
                            curr.get("ratio_unit",
                                curr.get("clock_hour_unit",
                                    curr.get("gas_consumption_unit",
                                        curr.get("pressure_unit",
                                            curr.get("electricity_consumption_unit",
                                                curr.get("distance_unit",
                                                    curr.get("combustion_consumption_unit", None))))))))
                    )
                    # Set the value only if the timestamp is higher
                    if float(ts) > float(self._get_car_value(classInstance, option, "ts", 0)):
                        setattr(classInstance, option, curr_status)
                    else:
                        LOGGER.warn("get_car_values %s older attribute %s data received. ignoring value.", car_id, option)
                else:
                    # Do not set status for non existing values on partial update
                    if not update:
                        curr_status = CarAttribute(0, 4, 0)
                        setattr(classInstance, option, curr_status)
            else:
                setattr(classInstance, option, CarAttribute(-1, -1, None))

        return classInstance

    def _get_car_value(self, class_instance, object_name, attrib_name, default_value):
        value = None

        value = getattr(
                    getattr(class_instance, object_name, default_value),
                        attrib_name,
                        default_value,
        )
        return value


    def _process_vep_updates(self, data):
        LOGGER.debug(f"Start _process_vep_updates")

        self._write_debug_output(data, "vep")

        # Don't understand the protobuf dict errors --> convert to json 
        js = json.loads(MessageToJson(data, preserving_proto_field_name=True))
        cars = js["vepUpdates"]["updates"]

        for vin in cars:
            
            if vin in self.excluded_cars:
                continue

            c = cars.get(vin)

            if DEBUG_SIMULATE_PARTIAL_UPDATES_ONLY and c.get("full_update", False) == True:
                c["full_update"] = False
                LOGGER.debug(f"DEBUG_SIMULATE_PARTIAL_UPDATES_ONLY mode. {vin}")

            if (c.get("full_update") == True):
                LOGGER.debug(f"Full Update. {vin}")
                with self.__lock:
                    self._build_car(c, update_mode=False)
            else:
                LOGGER.debug(f"Partial Update. {vin}")
                with self.__lock:
                    self._build_car(c, update_mode=True)

            
            if self._dataload_complete_fired:
                current_car = next(car for car in self.cars
                                   if car.finorvin == vin)
                if current_car:
                    current_car.publish_updates()


        if not self._dataload_complete_fired:
            for car in self.cars:
                LOGGER.debug(f"_process_vep_updates - {car.finorvin} - complete: {car._entry_setup_complete} - {car._messages_received}")


    def _process_assigned_vehicles(self, data):

        if not self._dataload_complete_fired:
            LOGGER.debug(f"Start _process_assigned_vehicles")

            #self._write_debug_output(data, "asv")

            with self.__lock:
                for vin in data.assigned_vehicles.vins:

                    if vin in self.excluded_cars:
                        continue

                    _car = next((car for car in self.cars
                                    if car.finorvin == vin), None)
                    if _car is None:
                        c = Car()
                        c.finorvin = vin
                        c.licenseplate = vin
                        self.cars.append(c)
            
            load_complete = True
            current_time =  int(round(time.time() * 1000))
            for car in self.cars:
                LOGGER.debug(f"_process_assigned_vehicles - {car.finorvin} - {car._entry_setup_complete} - {car._messages_received} - {current_time - car._last_message_received} ")

                if car._last_message_received > 0 and current_time - car._last_message_received > 30000:
                    LOGGER.debug("No Full Update Message received - Force car entry setup complete for car %s", car.finorvin)
                    car._entry_setup_complete = True

                if not car._entry_setup_complete:
                    load_complete = False

            if load_complete:
                self._on_dataload_complete()
                self._dataload_complete_fired = True


    def _process_apptwin_command_status_updates_by_vin(self, data):
        LOGGER.debug(f"Start _process_assigned_vehicles")

        # Don't understand the protobuf dict errors --> convert to json 
        js = json.loads(MessageToJson(data, preserving_proto_field_name=True))

        self._write_debug_output(data, "acr")

        if js["apptwin_command_status_updates_by_vin"]:
            if js["apptwin_command_status_updates_by_vin"]["updates_by_vin"]:
                
                car = list(js["apptwin_command_status_updates_by_vin"]["updates_by_vin"].keys())[0]
                car = js["apptwin_command_status_updates_by_vin"]["updates_by_vin"][car]
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
                                    LOGGER.warn("Car action: %s failed. error_code: %s, error_message: %s",
                                                command_type,
                                                command_error_code,
                                                command_error_message)
                            
                            current_car = next(car for car in self.cars
                                   if car.finorvin == vin)
                            if current_car:
                                current_car._last_command_type = command_type
                                current_car._last_command_state = command_state
                                current_car._last_command_error_code = command_error_code
                                current_car._last_command_error_message = command_error_message
                                current_car._last_command_time_stamp = command.get("timestamp_in_ms",0)

                                current_car.publish_updates()


    async def doors_unlock(self, vin: str):
        message = client_pb2.ClientMessage()

        if self.pin is None:
            LOGGER.warn(f"Can't unlock car {vin}. PIN not set. Please set the PIN -> Integration, Options ")
            return

        await self.doors_unlock_with_pin(vin, self.pin)


    async def doors_unlock_with_pin(self, vin: str, pin: str):
        LOGGER.info("Start Doors_unlock_with_pin for vin %s", vin)
        message = client_pb2.ClientMessage()

        if not pin:
            LOGGER.warn(f"Can't unlock car {vin}. Pin is required.")
            return

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.doors_unlock.pin = pin

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End Doors_unlock for vin %s", vin)


    async def doors_lock(self, vin: str):
        LOGGER.info("Start Doors_lock for vin %s", vin)
        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.doors_lock.doors.extend([])

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End Doors_lock for vin %s", vin)

    async def auxheat_start(self, vin: str):
        LOGGER.info("Start auxheat start for vin %s", vin)
        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        auxheat_start = pb2_commands.AuxheatStart()
        message.commandRequest.auxheat_start.CopyFrom(auxheat_start)

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End auxheat start for vin %s", vin)

    async def auxheat_stop(self, vin: str):
        LOGGER.info("Start auxheat_stop for vin %s", vin)
        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        auxheat_stop = pb2_commands.AuxheatStop()
        message.commandRequest.auxheat_stop.CopyFrom(auxheat_stop)

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End auxheat_stop for vin %s", vin)

    async def engine_start(self, vin: str):
        LOGGER.info("Start engine start for vin %s", vin)
        message = client_pb2.ClientMessage()

        if self.pin is None:
            LOGGER.warn(f"Can't start the car {vin}. PIN not set. Please set the PIN -> Integration, Options ")
            return

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.engine_start.pin = self.pin

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End engine start for vin %s", vin)

    async def engine_stop(self, vin: str):
        LOGGER.info("Start engine_stop for vin %s", vin)
        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        engine_stop = pb2_commands.EngineStop()
        message.commandRequest.engine_stop.CopyFrom(engine_stop)

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End engine_stop for vin %s", vin)

    async def sunroof_open(self, vin: str):
        LOGGER.info("Start sunroof_open for vin %s", vin)
        message = client_pb2.ClientMessage()

        if self.pin is None:
            LOGGER.warn(f"Can't open the sunroof - car {vin}. PIN not set. Please set the PIN -> Integration, Options ")
            return

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.sunroof_open.pin = self.pin

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End sunroof_open for vin %s", vin)

    async def sunroof_close(self, vin: str):
        LOGGER.info("Start sunroof_close for vin %s", vin)
        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        sunroof_close = pb2_commands.SunroofClose()
        message.commandRequest.sunroof_close.CopyFrom(sunroof_close)

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End sunroof_close for vin %s", vin)

    async def preheat_start(self, vin: str):
        LOGGER.info("Start preheat_start for vin %s", vin)
        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.zev_preconditioning_start.departure_time = 0
        message.commandRequest.zev_preconditioning_start.type = pb2_commands.ZEVPreconditioningType.now

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End preheat_start for vin %s", vin)

    async def preheat_start_departure_time(self, vin: str, departure_time: int):
        LOGGER.info("Start preheat_start_departure_time for vin %s", vin)
        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.zev_preconditioning_start.departure_time = departure_time
        message.commandRequest.zev_preconditioning_start.type = pb2_commands.ZEVPreconditioningType.departure

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End preheat_start_departure_time for vin %s", vin)

    async def preheat_stop(self, vin: str):
        LOGGER.info("Start preheat_stop for vin %s", vin)
        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.zev_preconditioning_stop.type = pb2_commands.ZEVPreconditioningType.now

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End preheat_stop for vin %s", vin)

    async def windows_open(self, vin: str):
        LOGGER.info("Start windows_open for vin %s", vin)
        message = client_pb2.ClientMessage()

        if self.pin is None:
            LOGGER.warn(f"Can't open the windows - car {vin}. PIN not set. Please set the PIN -> Integration, Options ")
            return

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.windows_open.pin = self.pin

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End windows_open for vin %s", vin)

    async def windows_close(self, vin: str):
        LOGGER.info("Start windows_close for vin %s", vin)
        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        windows_close = pb2_commands.WindowsClose()
        message.commandRequest.windows_close.CopyFrom(windows_close)

        await self.websocket.call(message.SerializeToString())
        LOGGER.info("End windows_close for vin %s", vin)

    def _write_debug_output(self, data, datatype):

        if WRITE_DEBUG_OUTPUT:
            LOGGER.debug(f"Start _write_debug_output")

            path = self._debug_save_path
            Path(path).mkdir(parents=True, exist_ok=True)

            f = open(f"{path}/{datatype}{int(round(time.time() * 1000))}" , "wb")
            f.write(data.SerializeToString())
            f.close()

            self._write_debug_json_output(MessageToJson(data, preserving_proto_field_name=True), datatype)


    def _write_debug_json_output(self, data, datatype):

        if WRITE_DEBUG_OUTPUT:
            path = self._debug_save_path
            Path(path).mkdir(parents=True, exist_ok=True)

            f = open(f"{path}/{datatype}{int(round(time.time() * 1000))}.json" , "w")
            f.write(f"{data}")
            f.close()
