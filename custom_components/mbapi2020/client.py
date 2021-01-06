import asyncio
import json
import logging
import time

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
    DEFAULT_LOCALE,
    DEFAULT_COUNTRY_CODE,
    DEFAULT_CACHE_PATH,
    DEFAULT_TOKEN_PATH,
    DEFAULT_SOCKET_MIN_RETRY,
)

import custom_components.mbapi2020.proto.client_pb2 as client_pb2
import custom_components.mbapi2020.proto.vehicle_events_pb2 as vehicle_events_pb2

LOGGER = logging.getLogger(__name__)

WRITE_DEBUG_OUTPUT = False

class Client: # pylint: disable-too-few-public-methods
    """ define the client. """
    def __init__(
        self,
        *,
        session: Optional[ClientSession] = None,
        hass: Optional[HomeAssistant] = None,
        config_entry = None,
        cache_path: Optional[str] = None
    ) -> None:
        self._ws_reconnect_delay = DEFAULT_SOCKET_MIN_RETRY
        self._hass = hass
        self._on_dataload_complete = None
        self._dataload_complete_fired = False
        self.__lock = RLock()
        self._debug_save_path = self._hass.config.path(DEFAULT_CACHE_PATH)
        self._config_entry = config_entry
        self._locale: str = DEFAULT_LOCALE
        self._country_code: str = DEFAULT_COUNTRY_CODE
        self._excluded_cars: str = ""

        if self._config_entry:
            if self._config_entry.options:
                self._country_code = self._config_entry.options.get(CONF_COUNTRY_CODE, DEFAULT_COUNTRY_CODE)
                self._locale = self._config_entry.options.get(CONF_LOCALE, DEFAULT_LOCALE)
                self._excluded_cars = self._config_entry.options.get(CONF_EXCLUDED_CARS, "")

        self.oauth: Oauth = Oauth(session=session, locale=self._locale, country_code=self._country_code, cache_path=self._hass.config.path(DEFAULT_TOKEN_PATH))
        self.api: API = API(session=session, oauth=self.oauth)
        self.websocket: Websocket = Websocket(self.oauth)
        self.cars = []


        LOGGER.debug(self._debug_save_path)

    async def _attempt_connect(self, callback_dataload_complete):
        """Attempt to connect to the socket (retrying later on fail)."""

        def on_connect():
            """Define a handler to fire when the websocket is connected."""
            LOGGER.debug("Connected to websocket")

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

                    if data.debugMessage.message == "app twin actor has stopped":
                        LOGGER.info("Websocket connection closed by server try to reconnect.")
                        async_call_later(self._hass, self._ws_reconnect_delay, connect)

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
                return

            if (msg_type == "apptwin_pending_command_request"):
                LOGGER.debug(f"apptwin_pending_command_request - Data: {MessageToJson(data, preserving_proto_field_name=True)}")
                return

            if (msg_type == "assigned_vehicles"):
                LOGGER.debug("assigned_vehicles")
                
                self._process_assigned_vehicles(data)
                
                return

            LOGGER.debug(f"Message Type not implemented - {msg_type}")

        def on_disconnect():
            """Define a handler to fire when the websocket is disconnected."""
            LOGGER.debug("Disconnected from websocket")

        async def connect(timestamp=None):
            """Connect."""
            await self.oauth.async_get_cached_token()
            await self.websocket.connect(on_data, on_connect, on_disconnect)

        try:
            self._on_dataload_complete = callback_dataload_complete
            await connect()
        except (WebsocketError, TypeError) as err:
            LOGGER.error("Error with the websocket connection: %s", err)
            self._ws_reconnect_delay = self._ws_reconnect_delay
            async_call_later(self._hass, self._ws_reconnect_delay, connect)

    def _build_car(self, c, update_mode):

        if c.get("vin") in self._excluded_cars:
            LOGGER.debug(f"CAR {c.get('vin')} is excluded.")
            return

        car = next((item for item in self.cars if c.get("vin") == item.finorvin), None)

        car.odometer = self._get_car_values(
            c, car.finorvin, Odometer() if not update_mode else car.odometer, ODOMETER_OPTIONS, update_mode)

        car.tires = self._get_car_values(
            c, car.finorvin, Tires() if not update_mode else car.tires, TIRE_OPTIONS, update_mode)

        car.doors = self._get_car_values(
            c, car.finorvin, Doors() if not update_mode else car.doors, DOOR_OPTIONS, update_mode)

        car.location = self._get_car_values(
            c, car.finorvin,
            Location() if not update_mode else car.location, LOCATION_OPTIONS, update_mode)

        car.binarysensors = self._get_car_values(
            c, car.finorvin,
            Binary_Sensors() if not update_mode else car.binarysensors, BINARY_SENSOR_OPTIONS, update_mode)

        car.windows = self._get_car_values(
            c, car.finorvin, Windows() if not update_mode else car.windows, WINDOW_OPTIONS, update_mode)

        car.electric = self._get_car_values(
            c, car.finorvin, Electric() if not update_mode else car.electric, ELECTRIC_OPTIONS, update_mode)

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

        car._entry_setup_complete = True
        
        self.cars = [car if item.finorvin == car.finorvin else item for item in self.cars]
        
        #_car = next((item for item in self.cars if car.finorvin == item.finorvin), None)
        #if _car is None:                                
        #    self.cars.append(car)


    def _get_car_values(self, car_detail, car_id, classInstance, options, update):
        LOGGER.debug("get_car_values %s for %s called",
                      classInstance.name, car_id)

        for option in options:
            if car_detail is not None:
                if not car_detail["attributes"]:
                    LOGGER.debug(f"get_car_values {car_id} has incomplete update set - attributes not found %s called")
                    return

                curr = car_detail["attributes"].get(option)
                if curr is not None:
                    value = curr.get("value",curr.get("int_value",curr.get("double_value",curr.get("bool_value",curr.get("nil_value",-1)))))
                    status = curr.get("status", "VALID")
                    ts = curr.get("timestamp")
                    curr_status = CarAttribute(
                        value,
                        status,
                        ts,
                        distance_unit= curr.get("distance_unit", None),
                        display_value= curr.get("display_value", None)
                    )
                    setattr(classInstance, option, curr_status)
                else:
                    # Do not set status for non existing values on partial update
                    if not update:
                        curr_status = CarAttribute(0, 4, 0)
                        setattr(classInstance, option, curr_status)
            else:
                setattr(classInstance, option, CarAttribute(-1, -1, None))

        return classInstance

    def _process_vep_updates(self, data):
        LOGGER.debug(f"Start _process_vep_updates")

        self._write_debug_output(data, "vep")

        # Don't understand the protobuf dict errors --> convert to json 
        js = json.loads(MessageToJson(data, preserving_proto_field_name=True))
        cars = js["vepUpdates"]["updates"]

        for vin in cars:
            
            if vin in self._excluded_cars:
                continue

            c = cars.get(vin)
            if (c.get("full_update") == True):
                if not c.get("attributes"):
                    LOGGER.debug(f"Full Update - without attributes. {vin}")
                    continue

                LOGGER.debug(f"Full Update. {vin}")
                with self.__lock:
                    self._build_car(c, update_mode=False)
            else:
                LOGGER.debug(f"Partial Update. {vin}")
                if self._dataload_complete_fired:
                    with self.__lock:
                        self._build_car(c, update_mode=True)

        if not self._dataload_complete_fired:
            for car in self.cars:
                LOGGER.debug(f"_process_vep_updates - {car.finorvin} - {car._entry_setup_complete}")

    def _process_assigned_vehicles(self, data):

        if not self._dataload_complete_fired:
            LOGGER.debug(f"Start _process_assigned_vehicles")

            #self._write_debug_output(data, "asv")

            with self.__lock:
                for vin in data.assigned_vehicles.vins:

                    if vin in self._excluded_cars:
                        continue

                    _car = next((car for car in self.cars
                                    if car.finorvin == vin), None)
                    if _car is None:
                        c = Car()
                        c.finorvin = vin
                        self.cars.append(c)
            
            load_complete = True
            for car in self.cars:
                LOGGER.debug(f"_process_assigned_vehicles - {car.finorvin} - {car._entry_setup_complete}")
                if not car._entry_setup_complete:
                    load_complete = False

            if load_complete:
                self._on_dataload_complete()
                self._dataload_complete_fired = True

    def _write_debug_output(self, data, datatype):
        LOGGER.debug(f"Start _write_debug_output")

        path = self._debug_save_path
        Path(path).mkdir(parents=True, exist_ok=True)

        if WRITE_DEBUG_OUTPUT:
            f = open(f"{path}/{datatype}{int(round(time.time() * 1000))}" , "wb")
            f.write(data.SerializeToString())
            f.close()

            self._write_debug_json_output(MessageToJson(data, preserving_proto_field_name=True), datatype)

    def _write_debug_json_output(self, data, datatype):

        path = self._debug_save_path
        Path(path).mkdir(parents=True, exist_ok=True)

        if WRITE_DEBUG_OUTPUT:
            f = open(f"{path}/{datatype}{int(round(time.time() * 1000))}.json" , "w")
            f.write(f"{data}")
            f.close()
