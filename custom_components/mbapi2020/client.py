"""The MercedesME 2020 client."""

from __future__ import annotations

import datetime as dt
from datetime import datetime
import json
import logging
from pathlib import Path
import threading
import time
import traceback
from typing import Any
import uuid

from aiohttp import ClientSession
from google.protobuf.json_format import MessageToJson

from custom_components.mbapi2020.app_version import AppVersionManager
from custom_components.mbapi2020.proto import client_pb2
import custom_components.mbapi2020.proto.vehicle_commands_pb2 as pb2_commands
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import system_info
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

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
    SIGPOS_HORN_TYPES,
)
from .helper import LogHelper as loghelper
from .oauth import Oauth
from .vsu_helper import normalize_vsu_car
from .webapi import WebApi
from .websocket import Websocket

LOGGER = logging.getLogger(__name__)

DEBUG_SIMULATE_PARTIAL_UPDATES_ONLY = False
GEOFENCING_MAX_RETRIES = 1

# Fallback delay: create the entities even if not every car reported a full data set
DATALOAD_COMPLETE_FALLBACK_DELAY = 30

# Repeat interval in days per departureTimeMode, used to roll a departure that has
# already passed today forward to its next occurrence. 1 is
# DEPARTURE_TIME_MODE_ADHOC_ACTIVE, 2 is DEPARTURE_TIME_MODE_WEEKLYSET_ACTIVE (the
# command enum uses 2 for WEEKLY_DEPARTURE as well). Modes that are not listed -
# inactive, timer, intelligent departure - are left alone, because rolling one
# forward would invent a departure the car never reported.
DEPARTURE_TIME_MODE_REPEAT_DAYS: dict[int, int] = {
    1: 1,
    2: 7,
}

# The vehicle reports the schedule type of a weekly departure entry as the full
# proto enum name. Only the tail is of interest in an entity attribute.
WEEKLY_PROFILE_SCHEDULE_TYPE_PREFIX = "WEEKLY_PROFILE_SCHEDULE_TYPE_"

# Weekday labels for the active weekly profile, in the order of the proto enum
# so consecutive days can be collapsed into a range. The abbreviations are the
# aliases the command proto defines for the same enum ("the short versions are
# for json (en)coding purposes only"), which keeps the label on the wording
# Mercedes uses itself rather than inventing another one.
# What a week_profile_configure call does. Spelled out rather than implied by
# the presence of an identifier, because "change entry 2" and "add an entry"
# differ by one destroyed entry when the caller means the second and writes the
# first.
WEEK_PROFILE_OPERATIONS = ("add", "update", "delete")

# The application identifier the app sends for every entry it changed; entries
# it passes through unchanged keep the one the vehicle reported. The capability
# advertises 0-31 for the field, -1 is the marker outside that range.
WEEK_PROFILE_CHANGED_APPLICATION_IDENTIFIER = -1

WEEKLY_PROFILE_DAY_LABELS: dict[str, str] = {
    "MONDAY": "Mo",
    "TUESDAY": "Tu",
    "WEDNESDAY": "We",
    "THURSDAY": "Th",
    "FRIDAY": "Fr",
    "SATURDAY": "Sa",
    "SUNDAY": "Su",
}

# Horn/light parameters the Mercedes me app sends per signaling mode,
# as (horn_repeat, horn_type, light_type)
SIGPOS_TYPE_DEFAULTS: dict[int, tuple[int, int, int]] = {
    pb2_commands.SigPosStart.LIGHT_ONLY: (
        0,
        pb2_commands.SigPosStart.HORN_OFF,
        pb2_commands.SigPosStart.DIPPED_HEAD_LIGHT,
    ),
    pb2_commands.SigPosStart.HORN_ONLY: (
        1,
        pb2_commands.SigPosStart.HORN_LOW_VOLUME,
        pb2_commands.SigPosStart.LIGHT_OFF,
    ),
    pb2_commands.SigPosStart.LIGHT_AND_HORN: (
        1,
        pb2_commands.SigPosStart.HORN_LOW_VOLUME,
        pb2_commands.SigPosStart.WARNING_LIGHT,
    ),
    pb2_commands.SigPosStart.PANIC_ALARM: (
        0,
        pb2_commands.SigPosStart.HORN_OFF,
        pb2_commands.SigPosStart.LIGHT_OFF,
    ),
}


class Client:
    """define the client."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: ClientSession,
        config_entry: ConfigEntry,
        region: str = "",
    ) -> None:
        """Initialize the client instance."""

        self.long_running_operation_active: bool = False
        self.ignition_states: dict[str, bool] = {}
        self.account_blocked: bool = False

        self._ws_reconnect_delay = DEFAULT_SOCKET_MIN_RETRY
        self._hass = hass
        self._region = region
        self._on_dataload_complete = None
        self._dataload_complete_fired = False
        self._dataload_fallback_handle = None
        self._coordinator_ref = None
        self._disable_rlock = False
        self.__lock = None
        self._debug_save_path = self._hass.config.path(DEFAULT_CACHE_PATH)
        self.config_entry = config_entry
        self.session_id = str(uuid.uuid4()).upper()

        self._first_vepupdates_processed: bool = False
        self._vepupdates_timeout_seconds: int = 25
        self._vepupdates_time_first_message: datetime | None = None
        self.app_version = AppVersionManager(self._region)

        self.oauth: Oauth = Oauth(
            hass=self._hass,
            session=session,
            region=self._region,
            config_entry=config_entry,
            app_version=self.app_version,
        )
        self.oauth.session_id = self.session_id
        self.webapi: WebApi = WebApi(
            self._hass,
            session=session,
            oauth=self.oauth,
            region=self._region,
            app_version=self.app_version,
        )
        self.webapi.session_id = self.session_id
        self.websocket: Websocket = Websocket(
            hass=self._hass,
            oauth=self.oauth,
            region=self._region,
            session_id=self.session_id,
            ignition_states=self.ignition_states,
            app_version=self.app_version,
        )

        self.cars: dict[str, Car] = {}

    @property
    def pin(self) -> str:
        """Return the security pin of an account."""
        if self.config_entry and self.config_entry.options:
            return self.config_entry.options.get(CONF_PIN, None)
        return ""

    @property
    def excluded_cars(self):
        """Return the list of exluded/ignored VIN/FIN."""
        if self.config_entry and self.config_entry.options:
            return self.config_entry.options.get(CONF_EXCLUDED_CARS, [])
        return []

    def on_data(self, data):
        """Define a handler to fire when the data is received."""

        msg_type = data.WhichOneof("msg")

        if self.websocket and self.websocket.ws_connect_retry_counter > 0:
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

        if msg_type == "vehicle_status_updates":
            self._process_vehicle_status_updates(data)

            sequence_number = data.vehicle_status_updates.sequence_number
            LOGGER.debug("vehicle_status_updates Sequence: %s", sequence_number)
            ack_command = client_pb2.ClientMessage()
            ack_command.acknowledge_vehicle_status_updates.sequence_number = sequence_number
            return ack_command

        self._write_debug_output(data, "unk")
        LOGGER.debug("Message Type not implemented: %s", msg_type)

        return None

    async def attempt_connect(self, callback_dataload_complete, coordinator_ref=None):
        """Attempt to connect to the socket."""
        LOGGER.debug("attempt_connect")

        self._on_dataload_complete = callback_dataload_complete
        self._coordinator_ref = coordinator_ref
        await self.websocket.async_connect(self.on_data)

    def _build_car(self, received_car_data, update_mode, is_rest_data=False):
        if received_car_data.get("vin") in self.excluded_cars:
            LOGGER.debug("CAR excluded: %s", loghelper.Mask_VIN(received_car_data.get("vin")))
            return

        if received_car_data.get("vin") not in self.cars:
            LOGGER.info(
                "Flow Problem - VepUpdate for unknown car: %s",
                loghelper.Mask_VIN(received_car_data.get("vin")),
            )

            current_car = Car(received_car_data.get("vin"))
            current_car.licenseplate = received_car_data.get("vin")
            self.cars[received_car_data.get("vin")] = current_car

        car: Car = self.cars.get(received_car_data.get("vin"), Car(received_car_data.get("vin")))

        car.messages_received.update("p" if update_mode else "f")
        car.last_message_received = round(time.time() * 1000)

        if not update_mode:
            car.last_full_message = received_car_data

        # Set data collection mode based on data source
        if is_rest_data:
            car.data_collection_mode = "pull"
        else:
            car.data_collection_mode = "push"

        # For REST data, create synthetic windowStatusOverall if missing
        if (
            is_rest_data
            and received_car_data.get("attributes")
            and "windowStatusOverall" not in received_car_data["attributes"]
        ):
            self._create_synthetic_window_status_overall(received_car_data, car.finorvin)

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

        self.cars[car.finorvin] = car

    def _get_car_values(self, car_detail, vin, class_instance, options, update):
        # Define handlers for specific options and the generic case
        option_handlers = {
            "max_soc": self._get_car_values_handle_max_soc,
            "chargeflap": self._get_car_values_handle_chargeflap,
            "chargeinletcoupler": self._get_car_values_handle_chargeinletcoupler,
            "chargeinletlock": self._get_car_values_handle_chargeinletlock,
            "chargePrograms": self._get_car_values_handle_charge_programs,
            "chargingBreakClockTimer": self._get_car_values_handle_charging_break_clock_timer,
            "chargingPowerRestriction": self._get_car_values_handle_charging_power_restriction,
            "endofchargetime": self._get_car_values_handle_endofchargetime,
            "ignitionstate": self._get_car_values_handle_ignitionstate,
            "nextDepartureTime": self._get_car_values_handle_next_departure_time,
            "precondStatus": self._get_car_values_handle_precond_status,
            "temperature_points_frontLeft": self._get_car_values_handle_temperature_points,
            "temperature_points_frontRight": self._get_car_values_handle_temperature_points,
            "temperature_points_rearLeft": self._get_car_values_handle_temperature_points,
            "temperature_points_rearRight": self._get_car_values_handle_temperature_points,
            "weeklyProfileActive": self._get_car_values_handle_weekly_profile,
            "weeklyProfileLimits": self._get_car_values_handle_weekly_profile,
            "weeklyProfileRaw": self._get_car_values_handle_weekly_profile,
            "weeklyProfileTimeProfiles": self._get_car_values_handle_weekly_profile,
        }

        if car_detail is None or not car_detail.get("attributes"):
            LOGGER.debug(
                "get_car_values %s has incomplete update data – attributes not found",
                loghelper.Mask_VIN(vin),
            )
            return class_instance

        for option in options:
            # Select the specific handler or the generic handler
            handler = option_handlers.get(option, self._get_car_values_handle_generic)

            curr_status = handler(car_detail, class_instance, option, update, vin)
            if curr_status is None:
                continue

            # Set the value only if the timestamp is newer
            # curr_timestamp = float(curr_status.timestamp or 0)
            # car_value_timestamp = float(self._get_car_value(class_instance, option, "ts", 0))
            # if curr_timestamp > car_value_timestamp:
            #     setattr(class_instance, option, curr_status)
            # elif curr_timestamp < car_value_timestamp:
            #     LOGGER.warning(
            #         "get_car_values %s received older attribute data for %s. Ignoring value.",
            #         loghelper.Mask_VIN(vin),
            #         option,
            #     )
            setattr(class_instance, option, curr_status)
        return class_instance

    def _get_car_values_handle_generic(self, car_detail, class_instance, option, update, vin: str):
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

    def _get_car_values_handle_max_soc(
        self, car_detail, class_instance, option, update, vin: str, use_last_full_message: bool = False
    ):
        # Handle the case when the selected charge program changed but chargePrograms is not available in the update message.
        if not use_last_full_message:
            attributes = car_detail.get("attributes", {})
            charge_programs = attributes.get("chargePrograms")
            if not charge_programs:
                if not attributes.get("selectedChargeProgram"):
                    return None

                return self._get_car_values_handle_max_soc(
                    car_detail, class_instance, option, update, vin, use_last_full_message=True
                )
        else:
            current_car = self.cars.get(vin)
            if not current_car or not current_car.last_full_message:
                LOGGER.debug(
                    "get_car_values_handle_max_soc - No last_full_message found for car %s",
                    loghelper.Mask_VIN(vin),
                )
                return None
            car_detail = current_car.last_full_message or car_detail
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

    def _get_car_values_handle_chargeflap(self, car_detail, class_instance, option, update, vin: str):
        attributes = car_detail.get("attributes", {})
        curr = attributes.get("chargeFlaps")
        if not curr:
            return None

        charge_flaps_value = curr.get("charge_flaps", {})
        values = charge_flaps_value.get("entries", [])
        if not values:
            return None

        status = curr.get("status", "VALID")
        time_stamp = curr.get("timestamp", 0)
        value = values[0].get("position_state", None)

        if value is None:
            return None

        if value == "CHARGE_FLAPS_POSITION_STATE_OPEN":
            value = "open"
        elif value == "CHARGE_FLAPS_POSITION_STATE_CLOSED":
            value = "closed"
        elif value == "CHARGE_FLAPS_POSITION_STATE_FLAP_PRESSED":
            value = "pressed"
        elif value == "CHARGE_FLAPS_POSITION_STATE_UNKNOWN":
            value = STATE_UNKNOWN
        else:
            value = STATE_UNKNOWN
            LOGGER.debug(
                "Unknown chargeFlaps position_state value: %s. Please report this value via an github issue.", value
            )

        return CarAttribute(
            value=value,
            retrievalstatus=status,
            timestamp=time_stamp,
            display_value=None,
            unit=None,
        )

    def _get_car_values_handle_chargeinletcoupler(self, car_detail, class_instance, option, update, vin: str):
        attributes = car_detail.get("attributes", {})
        curr = attributes.get("chargeInlets")
        if not curr:
            return None

        values = curr.get("charge_inlets", {}).get("entries", [])
        if not values:
            return None

        status = curr.get("status", "VALID")
        time_stamp = curr.get("timestamp", 0)
        value = values[0].get("coupler_state", None)

        if value is None:
            return None

        if value == "CHARGE_INLETS_COUPLER_STATE_PLUGGED":
            value = "plugged"
        elif value == "CHARGE_INLETS_COUPLER_STATE_VEHICLE_PLUGGED":
            value = "vehicle plugged"
        elif value == "CHARGE_INLETS_COUPLER_STATE_VEHICLE_NOT_PLUGGED":
            value = "vehicle not plugged"
        elif value == "CHARGE_INLETS_COUPLER_STATE_DEFECT":
            value = "defect"
        elif value == "CHARGE_INLETS_COUPLER_STATE_UNKNOWN":
            value = STATE_UNKNOWN
        else:
            value = STATE_UNKNOWN
            LOGGER.debug(
                "Unknown chargeInlets coupler_state value: %s. Please report this value via an github issue.", value
            )

        return CarAttribute(
            value=value,
            retrievalstatus=status,
            timestamp=time_stamp,
            display_value=None,
            unit=None,
        )

    def _get_car_values_handle_chargeinletlock(self, car_detail, class_instance, option, update, vin: str):
        attributes = car_detail.get("attributes", {})
        curr = attributes.get("chargeInlets")
        if not curr:
            return None

        values = curr.get("charge_inlets", {}).get("entries", [])
        if not values:
            return None

        status = curr.get("status", "VALID")
        time_stamp = curr.get("timestamp", 0)
        value = values[0].get("lock_state", None)

        if value is None:
            return None

        if value == "CHARGE_INLETS_LOCK_STATE_UNLOCKED":
            value = "unlocked"
        elif value == "CHARGE_INLETS_LOCK_STATE_LOCKED":
            value = "locked"
        elif value == "CHARGE_INLETS_LOCK_STATE_LOCK_STATE_NOT_CLEAR":
            value = "state not clear"
        elif value == "CHARGE_INLETS_LOCK_STATE_NOT_AVAILABLE":
            value = "state not available"
        elif value == "CHARGE_INLETS_LOCK_STATE_UNKNOWN":
            value = STATE_UNKNOWN
        else:
            value = STATE_UNKNOWN
            LOGGER.debug(
                "Unknown chargeInlets lock_state value: %s. Please report this value via an github issue.", value
            )

        return CarAttribute(
            value=value,
            retrievalstatus=status,
            timestamp=time_stamp,
            display_value=None,
            unit=None,
        )

    def _get_car_values_handle_charge_programs(self, car_detail, class_instance, option, update, vin: str):
        attributes = car_detail.get("attributes", {})
        curr = attributes.get(option)
        if not curr:
            return None

        charge_programs_value = curr.get("charge_programs_value", {})
        value = charge_programs_value.get("charge_program_parameters", [])
        if not value:
            return None

        status = curr.get("status", "VALID")
        time_stamp = curr.get("timestamp", 0)

        return CarAttribute(
            value=value,
            retrievalstatus=status,
            timestamp=time_stamp,
            display_value=None,
            unit=None,
        )

    def _get_car_values_handle_charging_power_restriction(self, car_detail, class_instance, option, update, vin: str):
        attributes = car_detail.get("attributes", {})
        curr = attributes.get("chargingPowerRestriction")
        if not curr:
            return None

        charge_flaps_value = curr.get("charging_power_restrictions", {})
        values = charge_flaps_value.get("charging_power_restriction", [])
        if not values:
            return None

        status = curr.get("status", "VALID")
        time_stamp = curr.get("timestamp", 0)

        if len(values) == 0:
            return None

        value = ", ".join(item.replace("CHARGING_POWER_RESTRICTION_", "") for item in values)

        return CarAttribute(
            value=value,
            retrievalstatus=status,
            timestamp=time_stamp,
            display_value=None,
            unit=None,
        )

    def _get_car_values_handle_endofchargetime(self, car_detail, class_instance, option, update, vin: str):
        # Beginning with CLA 2025 charge end time is part of chargingPredictionMaxSoc

        attributes = car_detail.get("attributes", {})

        chargingPredictionMaxSoc = attributes.get("chargingPredictionMaxSoc", {})
        charging_prediction_soc = chargingPredictionMaxSoc.get("charging_prediction_soc", {})
        predicted_end_time = charging_prediction_soc.get("predicted_end_time", None)
        if predicted_end_time is not None:
            status = chargingPredictionMaxSoc.get("status", "VALID")
            time_stamp = chargingPredictionMaxSoc.get("timestamp", 0)

            if isinstance(predicted_end_time, datetime):
                value = predicted_end_time
            elif isinstance(predicted_end_time, str):
                # predicted_end_time is a google.protobuf.Timestamp, so MessageToJson
                # renders it as RFC 3339 - and appends 3, 6 or 9 fractional digits
                # whenever the backend sets nanos. A fixed "%Y-%m-%dT%H:%M:%SZ" only
                # matched whole seconds and dropped every other reading silently, which
                # left the sensor on its previous value. parse_datetime takes all of
                # them, plus an explicit offset instead of the trailing Z.
                value = dt_util.parse_datetime(predicted_end_time)
                if value is None:
                    LOGGER.warning(
                        "get_car_values_handle_endofchargetime - unparseable predicted_end_time %s for car %s",
                        predicted_end_time,
                        loghelper.Mask_VIN(vin),
                    )
            else:
                value = None
            if value is not None:
                if value.tzinfo is None:
                    # The backend always sends UTC; a timestamp without an offset
                    # would otherwise be read as local time further downstream.
                    value = value.replace(tzinfo=dt.UTC)
                return CarAttribute(
                    value=value,
                    retrievalstatus=status,
                    timestamp=time_stamp,
                    # The sensor reads display_value, and a timestamp device class
                    # needs ISO 8601 - str(datetime) would yield a space instead of
                    # the "T". The legacy branch below does the same.
                    display_value=value.isoformat(),
                    unit=None,
                )

        # if chargingPredictionMaxSoc is not available and update is false (not a full_message), we want to check if the car is >= CLA2025 and create the data structure with value unknown
        # endofchargetime is not present for these cars
        if not update and not predicted_end_time:
            current_car = self.cars.get(vin)
            if not attributes.get("endofchargetime") and not (
                current_car
                and current_car.last_full_message
                and current_car.last_full_message.get("attributes", {}).get("endofchargetime")
            ):
                return CarAttribute(
                    value=STATE_UNKNOWN,
                    retrievalstatus="VALID",
                    timestamp=datetime.now().timestamp(),
                    display_value=STATE_UNKNOWN,
                    unit=None,
                )

        # Older cars have two attributes endofchargetime and endofChargeTimeWeekday
        # endofchargetime is in minutes after midnight
        try:
            endofchargetime = attributes.get("endofchargetime", {})
            if not endofchargetime:
                return None
            time_stamp = endofchargetime.get("timestamp", 0)
            end_time_value = endofchargetime.get("int_value", None)
            status = endofchargetime.get("status", "VALID")
            if end_time_value is None and status == 3:
                return CarAttribute(
                    value=STATE_UNKNOWN,
                    retrievalstatus=status,
                    timestamp=time_stamp,
                    display_value=STATE_UNKNOWN,
                    unit=None,
                )

            if end_time_value is None:
                LOGGER.warning(
                    "get_car_values_handle_endofchargetime - endofChargeTime value is None for car %s",
                    loghelper.Mask_VIN(vin),
                )
                return None

            # endofChargeTimeWeekday is sometimes not present (or not VALID) in the update message. Full messages
            # are rare, so prefer the VALID weekday already stored on the car and fall back to the last full
            # message only when no such value exists
            end_weekday_value = self._valid_endofchargetime_weekday(attributes.get("endofChargeTimeWeekday"))
            if end_weekday_value is None:
                end_weekday_value = self._stored_endofchargetime_weekday(class_instance)
            if end_weekday_value is None:
                current_car = self.cars.get(vin)
                if not current_car or not current_car.last_full_message:
                    LOGGER.debug(
                        "get_car_values_handle_endofchargetime - No weekday and no last_full_message for car %s",
                        loghelper.Mask_VIN(vin),
                    )
                    return None
                end_weekday_value = self._valid_endofchargetime_weekday(
                    current_car.last_full_message.get("attributes", {}).get("endofChargeTimeWeekday")
                )

            # The car reports a wall clock time, so it has to be anchored in Home
            # Assistant's configured timezone, not in the one the process happens to
            # run in: HA never touches the process timezone, and container installs
            # usually run on UTC, which would shift the reading by the whole offset.
            local_tz = dt_util.DEFAULT_TIME_ZONE
            if end_weekday_value is None:
                # Wenn kein Wochentag vorhanden ist (sehr alte elek. modelle), aus end_time_value ableiten:
                # Ist die Uhrzeit bereits vergangen -> Wochentag von morgen, sonst von heute.
                now = dt.datetime.now(local_tz)
                hour = int(end_time_value) // 60
                minute = int(end_time_value) % 60
                target_dt_today = dt.datetime(now.year, now.month, now.day, hour, minute, tzinfo=local_tz)
                if target_dt_today < now:
                    end_weekday_value = (now + dt.timedelta(days=1)).weekday()
                else:
                    end_weekday_value = now.weekday()

            # Calculate the next occurrence of the given weekday and time in local timezone
            now = dt.datetime.now(local_tz)
            # Python's weekday: Monday=0
            target_weekday = float(end_weekday_value) % 7
            # Calculate days until next target_weekday
            days_ahead = (target_weekday - now.weekday()) % 7

            target_date = now + dt.timedelta(days=days_ahead)
            hour = int(end_time_value) // 60
            minute = int(end_time_value) % 60
            dt_with_time = dt.datetime(
                target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=local_tz
            )

            return CarAttribute(
                value=dt_with_time,
                retrievalstatus=status,
                timestamp=time_stamp,
                display_value=dt_with_time.isoformat(),
                unit=None,
            )
        except (AttributeError, TypeError, ValueError) as e:
            # Narrow on purpose: the payload is remote JSON, so a malformed
            # shape or an unparseable number should not abort the update, but
            # anything unexpected is better surfaced than swallowed here.
            LOGGER.error(
                "Error processing endofchargetime for car %s: %s, %s",
                loghelper.Mask_VIN(vin),
                e,
                traceback.format_exc(),
            )
            return None

    @staticmethod
    def _valid_endofchargetime_weekday(weekday_attr: dict[str, Any] | None) -> int | None:
        """Return the weekday of a raw endofChargeTimeWeekday attribute, or None when absent, not VALID or unusable."""
        if not weekday_attr or weekday_attr.get("status", "VALID") != "VALID":
            return None
        try:
            return int(weekday_attr.get("int_value"))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _stored_endofchargetime_weekday(class_instance) -> int | None:
        """Return the endofChargeTimeWeekday already stored on the car, or None when absent, not VALID or unusable."""
        stored = getattr(class_instance, "endofChargeTimeWeekday", None)
        if not isinstance(stored, CarAttribute) or stored.retrievalstatus != "VALID":
            return None
        try:
            return int(stored.value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _departure_time_mode(attributes: dict[str, Any]) -> int | None:
        """Return departureTimeMode as an int, or None when absent or unparseable.

        Guarded separately so a malformed mode cannot abort the departure-time
        reading it only refines.
        """
        attr = attributes.get("departureTimeMode") or {}
        raw = attr.get("int_value", attr.get("value"))
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    def _get_car_values_handle_next_departure_time(self, car_detail, class_instance, option, update, vin: str):
        """Combine nextDepartureTime and nextDepartureTimeWeekday into one timestamp.

        The car reports the departure as a clock time (``{"hour": 6, "minute": 45}``)
        plus a weekday enum where Monday is 0 - the same numbering Python uses. Both
        are resolved against the local timezone to the next occurrence of that
        weekday, mirroring what _get_car_values_handle_endofchargetime does.
        """
        attributes = car_detail.get("attributes", {})
        curr = attributes.get(option)
        if not curr:
            return None

        value = curr.get("value")
        if not isinstance(value, dict):
            return None

        try:
            hour = int(value.get("hour", 0))
            minute = int(value.get("minute", 0))

            # The car reports -1 when no departure time is set
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                return CarAttribute(
                    value=STATE_UNKNOWN,
                    retrievalstatus=3,
                    timestamp=curr.get("timestamp", 0),
                    display_value=STATE_UNKNOWN,
                    unit=None,
                )

            # The car reports a wall clock time, so it has to be anchored in Home
            # Assistant's configured timezone, not in the one the process happens to
            # run in: HA never touches the process timezone, and container installs
            # usually run on UTC, which would shift the reading by the whole offset.
            local_tz = dt_util.DEFAULT_TIME_ZONE
            now = dt.datetime.now(local_tz)

            weekday_attr = attributes.get("nextDepartureTimeWeekday", {})
            weekday_value = weekday_attr.get("int_value", weekday_attr.get("value"))
            if weekday_value is None:
                # No weekday reported: if the time has already passed today, the
                # next departure is tomorrow, otherwise it is still today.
                target_dt_today = dt.datetime(now.year, now.month, now.day, hour, minute, tzinfo=local_tz)
                weekday_value = (now + dt.timedelta(days=1)).weekday() if target_dt_today < now else now.weekday()

            days_ahead = (int(weekday_value) % 7 - now.weekday()) % 7
            target_date = now + dt.timedelta(days=days_ahead)
            dt_with_time = dt.datetime(
                target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=local_tz
            )

            # A recurring departure whose time has already passed today is the next
            # cycle's, not today's - a day later for a daily profile, a week for a
            # weekly one.
            if dt_with_time < now:
                repeat_days = DEPARTURE_TIME_MODE_REPEAT_DAYS.get(self._departure_time_mode(attributes))
                if repeat_days:
                    dt_with_time += dt.timedelta(days=repeat_days)

            return CarAttribute(
                value=dt_with_time,
                retrievalstatus=curr.get("status", "VALID"),
                timestamp=curr.get("timestamp", 0),
                display_value=dt_with_time.isoformat(),
                unit=None,
            )
        except (AttributeError, TypeError, ValueError) as e:
            # Narrow on purpose: the payload is remote JSON, so a malformed shape
            # or an unparseable number should not abort the update.
            LOGGER.error(
                "Error processing nextDepartureTime for car %s: %s, %s",
                loghelper.Mask_VIN(vin),
                e,
                traceback.format_exc(),
            )
            return None

    def _get_car_values_handle_charging_break_clock_timer(self, car_detail, class_instance, option, update, vin: str):
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

    @staticmethod
    def _format_weekly_time_profile(entry: dict[str, Any]) -> str:
        """Render one normalized entry as a label, e.g. "Mo-Fr 06:30".

        Consecutive days are collapsed into a range, but only from three days
        on: "Mo, Tu" reads better than "Mo-Tu" and is no longer. The time stays
        the 24-hour reading the vehicle reports; it carries no clock unit for
        this attribute, so there is nothing to switch on.

        A day the vehicle reports that this version does not know is appended
        verbatim instead of being dropped, so a new enum value shows up in the
        state rather than silently shrinking the label.
        """
        days = entry.get("days") or []
        order = list(WEEKLY_PROFILE_DAY_LABELS)
        indices = sorted({order.index(day) for day in days if day in WEEKLY_PROFILE_DAY_LABELS})

        runs: list[list[int]] = []
        for index in indices:
            if runs and index == runs[-1][1] + 1:
                runs[-1][1] = index
            else:
                runs.append([index, index])

        labels = []
        for start, end in runs:
            first = WEEKLY_PROFILE_DAY_LABELS[order[start]]
            if start == end:
                labels.append(first)
                continue
            last = WEEKLY_PROFILE_DAY_LABELS[order[end]]
            labels.append(f"{first}-{last}" if end - start > 1 else f"{first}, {last}")
        labels.extend(str(day) for day in days if day not in WEEKLY_PROFILE_DAY_LABELS)

        return f"{', '.join(labels)} {entry.get('time', '')}".strip()

    @staticmethod
    def _normalize_weekly_time_profile(entry: dict[str, Any]) -> dict[str, Any]:
        """Flatten one time profile entry of the weekly departure profile.

        Every field of the entry is a plain proto3 scalar, so the vehicle omits
        each one that carries its default: a profile at 00:30 arrives without
        "hour", an inactive one without "active", and a vehicle that does not
        support individual weekdays sends no "days" at all. Defaulting them
        here keeps a template from having to special-case a missing key per
        vehicle.
        """
        if not isinstance(entry, dict):
            return {}

        hour = int(entry.get("hour") or 0)
        minute = int(entry.get("minute") or 0)

        # action_list is a repeated message, so several entries may each carry
        # one flag. Fold them into a single mapping.
        actions = {"charging": False, "precond": False, "battery_precond": False}
        for action in entry.get("action_list") or []:
            if not isinstance(action, dict):
                continue
            for key in actions:
                if action.get(key):
                    actions[key] = True

        # NON_RECURRING is the zero value of the enum, so an omitted
        # schedule_type is indistinguishable from a one-off entry. The
        # vehicles that never report it also only allow NO_SELECTION for the
        # configure command, so calling the entry one-off would be wrong -
        # leave it empty instead of guessing.
        schedule_type = entry.get("schedule_type")
        if isinstance(schedule_type, str):
            schedule_type = schedule_type.removeprefix(WEEKLY_PROFILE_SCHEDULE_TYPE_PREFIX)

        return {
            "identifier": entry.get("id"),
            "time": f"{hour:02d}:{minute:02d}",
            "hour": hour,
            "minute": minute,
            "days": list(entry.get("days") or []),
            "active": bool(entry.get("active", False)),
            "application_identifier": entry.get("application_identifier", 0),
            "actions": actions,
            "schedule_type": schedule_type,
            "is_learned_time": bool(entry.get("is_learned_time", False)),
        }

    def _get_car_values_handle_weekly_profile(self, car_detail, class_instance, option, update, vin: str):
        """Split the weeklyProfile object into the three attributes it feeds.

        The vehicle sends the whole weekly departure profile as one nested
        object, which is of no use as a sensor state. All three attributes are
        derived from that single payload, so they share this handler - the same
        way endofchargetime and endofChargeTimeWeekday both come out of one
        value. "weeklyProfile" is the key on the wire, not one of them.

        Only the VSU shape is read. The flat VEP form (weekly_profile_value)
        nests hour/minute/active in wrapper messages and has not been observed
        on any vehicle, so a sensor is simply not created for it rather than
        parsing a shape that cannot be verified.
        """
        curr = car_detail.get("attributes", {}).get("weeklyProfile")
        if not curr:
            return None

        profile = curr.get("value")
        if not isinstance(profile, dict):
            return None

        entries = [self._normalize_weekly_time_profile(entry) for entry in profile.get("time_profiles") or []]
        status = curr.get("status", "VALID")
        time_stamp = curr.get("timestamp", 0)
        display_value = None

        if option == "weeklyProfileRaw":
            value: Any = profile
        elif option == "weeklyProfileTimeProfiles":
            value = entries
        elif option == "weeklyProfileLimits":
            value = {
                "max_time_profiles": profile.get("max_number_of_time_profiles", 0),
                "max_time_profiles_user": profile.get("max_number_of_time_profiles_user", 0),
                "max_weekly_time_profile_slots": profile.get("max_number_of_weekly_time_profile_slots", 0),
                "current_time_profile_slots": profile.get("current_number_of_time_profile_slots", 0),
                "single_entries_activatable": bool(profile.get("single_time_profile_entries_activatable", False)),
            }
        else:
            # The entry the vehicle currently follows. More than one may be
            # active - single_time_profile_entries_activatable says the vehicle
            # allows it - so the lowest identifier wins and the per-entry
            # "active" flag in weeklyProfileTimeProfiles keeps the full
            # picture. No active entry leaves the sensor unknown, which is what
            # it is: the vehicle has entries but follows none of them.
            active = [entry for entry in entries if entry.get("active")]
            value = None
            if active:
                # The identifier is a proto3 int32, so a hypothetical id 0
                # arrives as None: sort it first rather than raising.
                entry = min(active, key=lambda candidate: candidate.get("identifier") or 0)
                # The state shows the label; the identifier stays reachable as
                # the "original_value" attribute the entity adds for every
                # sensor that reads display_value.
                value = entry.get("identifier")
                display_value = self._format_weekly_time_profile(entry)

        return CarAttribute(
            value=value,
            retrievalstatus=status,
            timestamp=time_stamp,
            # Only the active entry has a display value. It stays unset for the
            # list and the limits, because extra_state_attributes prefers
            # display_value and would otherwise show it instead of the data.
            display_value=display_value,
            unit=None,
        )

    def _get_car_values_handle_ignitionstate(self, car_detail, class_instance, option, update, vin: str):
        value = self._get_car_values_handle_generic(car_detail, class_instance, option, update, vin)
        if value:
            vin = car_detail.get("vin")
            self.ignition_states[vin] = value.value == "4"
            if vin in self.excluded_cars:
                self.ignition_states[vin] = False

        return value

    def _get_car_values_handle_precond_status(self, car_detail, class_instance, option, update, vin: str):
        attributes = car_detail.get("attributes", {})

        def _attr_to_bool(attr: dict[str, Any]) -> bool:
            """Coerce legacy/VSU attribute payloads to a boolean state."""
            if not attr:
                return False

            if "bool_value" in attr:
                return bool(attr.get("bool_value"))

            raw_value = attr.get("value")
            if isinstance(raw_value, bool):
                return raw_value
            if isinstance(raw_value, int):
                return raw_value > 0
            if isinstance(raw_value, str):
                lowered = raw_value.lower()
                if lowered in ("true", "false"):
                    return lowered == "true"
                if raw_value.lstrip("-").isdigit():
                    return int(raw_value) > 0

            raw_int = attr.get("int_value")
            if raw_int is not None:
                try:
                    return int(raw_int) > 0
                except (TypeError, ValueError):
                    return False

            return False

        # Retrieve attributes with defaults to handle missing keys
        precond_now_attr = attributes.get("precondNow", {})
        precond_active_attr = attributes.get("precondActive", {})
        precond_operating_mode_attr = attributes.get("precondOperatingMode", {})
        precond_state_attr = attributes.get("precondState", {})
        precond_state_value = precond_state_attr.get("value", {}) if isinstance(precond_state_attr, dict) else {}

        # VSU reports precondNow as an enum attribute and precondState as a
        # nested message, while the legacy VEP path used plain booleans.
        precond_now_value = _attr_to_bool(precond_now_attr)
        precond_active_value = _attr_to_bool(precond_active_attr)
        precond_operating_mode_value = precond_operating_mode_attr.get("int_value", 0)
        precond_operating_mode_bool = int(precond_operating_mode_value) > 0
        precond_state_activation_value = False
        if isinstance(precond_state_value, dict):
            precond_state_activation_value = bool(precond_state_value.get("activation_state", False))

        # Calculate precondStatus
        value = (
            precond_now_value or precond_active_value or precond_operating_mode_bool or precond_state_activation_value
        )

        # Determine if any of the attributes are present
        if precond_now_attr or precond_active_attr or precond_operating_mode_attr or precond_state_attr:
            status = "VALID"
            time_stamp = max(
                int(precond_now_attr.get("timestamp", 0)),
                int(precond_active_attr.get("timestamp", 0)),
                int(precond_operating_mode_attr.get("timestamp", 0)),
                int(precond_state_attr.get("timestamp", 0)),
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

    def _get_car_values_handle_temperature_points(self, car_detail, class_instance, option: str, update, vin: str):
        curr_zone = option.replace("temperature_points_", "")
        attributes = car_detail.get("attributes", {})
        temperaturePoints = attributes.get("temperaturePoints")
        if not temperaturePoints:
            return None

        time_stamp = temperaturePoints.get("timestamp", 0)
        temperature_points_value = temperaturePoints.get("temperature_points_value", {})
        temperature_points = temperature_points_value.get("temperature_points", [])

        for point in temperature_points:
            # The zone arrives either as the legacy camelCase string ("frontRight")
            # or as the VSU Zone enum ("FRONT_RIGHT"). FRONT_LEFT is the enum default
            # (0) and is omitted by MessageToJson, so a missing zone means front left.
            point_zone = point.get("zone") or "FRONT_LEFT"
            if point_zone.replace("_", "").lower() != curr_zone.lower():
                continue

            temperature = point.get("temperature")
            if isinstance(temperature, dict):
                # VSU shape: temperature is a nested DoubleTemperatureAttribute.
                value = temperature.get("value", 0)
                display_value = temperature.get("display_value")
                unit = temperature.get("unit")
            else:
                # Legacy VEP/REST shape: temperature is a scalar.
                value = temperature if temperature is not None else 0
                display_value = point.get("temperature_display_value")
                unit = temperaturePoints.get("temperature_unit", None)

            return CarAttribute(
                value=value,
                retrievalstatus="VALID",
                timestamp=time_stamp,
                display_value=display_value,
                unit=unit,
            )

        return None

    def _create_synthetic_window_status_overall(self, car_data, vin):
        """Create a synthetic windowStatusOverall based on individual window statuses for REST data."""
        if not car_data.get("attributes"):
            return

        # Debug: Log all available window-related attributes
        # window_attrs_found = [key for key in car_data["attributes"].keys() if "window" in key.lower()]
        # if window_attrs_found:
        #     LOGGER.debug("Available window attributes for %s: %s", loghelper.Mask_VIN(vin), window_attrs_found)
        # else:
        #     LOGGER.debug("No window attributes found in REST data for %s", loghelper.Mask_VIN(vin))

        # Define main window status attributes to check
        main_window_attrs = [
            "windowstatusfrontleft",
            "windowstatusfrontright",
            "windowstatusrearleft",
            "windowstatusrearright",
        ]

        # Check individual window statuses
        window_statuses = []
        latest_timestamp = 0

        for attr_name in main_window_attrs:
            if attr_name in car_data["attributes"]:
                attr_data = car_data["attributes"][attr_name]
                value = attr_data.get("int_value", 0)
                timestamp = attr_data.get("timestamp", 0)

                # Convert timestamp to int for comparison
                try:
                    timestamp = int(timestamp) if timestamp else 0
                    latest_timestamp = max(latest_timestamp, timestamp)
                except (ValueError, TypeError):
                    pass

                # Add to window statuses if value is available
                if value is not None:
                    window_statuses.append(value)

        # Calculate overall status based on individual windows
        # If we have valid window statuses, determine overall state
        if window_statuses:
            # Assume "CLOSED" = 0, "OPEN" = 1 or similar numeric values
            # If all windows are closed (0), overall should be "CLOSED"
            # If any window is open (>0), overall should be "OPEN"
            try:
                numeric_statuses = [int(status) for status in window_statuses if status is not None]
                if numeric_statuses:
                    overall_value = "OPEN" if any(status != 2 for status in numeric_statuses) else "CLOSED"
                else:
                    overall_value = "CLOSED"  # Default to closed if no valid data
            except (ValueError, TypeError):
                # If values are not numeric, try string comparison
                overall_value = "CLOSED"
        else:
            # No individual window data available, default to CLOSED
            overall_value = "CLOSED"

        # Create the synthetic windowStatusOverall attribute
        car_data["attributes"]["windowStatusOverall"] = {
            "timestamp": str(latest_timestamp) if latest_timestamp > 0 else "0",
            "bool_value": overall_value == "CLOSED",
            "status": "VALID",  # Use same status as other synthetic attributes
            "timestamp_in_ms": str(latest_timestamp * 1000 + 223),
        }

        LOGGER.debug(
            "Created synthetic windowStatusOverall for %s: %s (based on %d individual windows)",
            loghelper.Mask_VIN(vin),
            overall_value,
            len(window_statuses),
        )

    def _get_car_value(self, class_instance, object_name, attrib_name, default_value):
        return getattr(
            getattr(class_instance, object_name, default_value),
            attrib_name,
            default_value,
        )

    def _process_rest_vep_update(self, data):
        LOGGER.debug("Start _process_rest_vep_update")

        self._write_debug_output(data, "rfu")
        # Don't understand the protobuf dict errors --> convert to json
        vep_json = json.loads(MessageToJson(data, preserving_proto_field_name=True))

        # Check if this is a nested vepUpdates structure or a direct VIN structure
        if "vepUpdates" in vep_json and "updates" in vep_json["vepUpdates"]:
            # This is a multi-car update structure
            cars = vep_json["vepUpdates"]["updates"]
            for vin in cars:
                if vin in self.excluded_cars:
                    continue
                current_car = cars.get(vin)
                if current_car:
                    self._build_car(current_car, update_mode=False, is_rest_data=True)
        else:
            # This is a single car structure
            vin = vep_json.get("vin", None)
            if not vin:
                LOGGER.debug("No VIN found in VEPUpdate data: %s", vep_json)
                return
            self._build_car(vep_json, update_mode=False, is_rest_data=True)

        if not self._first_vepupdates_processed:
            self._vepupdates_time_first_message = datetime.now()
            self._first_vepupdates_processed = True
            self._arm_dataload_complete_fallback()

        self._build_car(vep_json, update_mode=False)
        if self._dataload_complete_fired:
            current_car = self.cars.get(vin)
            if current_car:
                current_car.data_collection_mode = "pull"
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
                self._cancel_dataload_complete_fallback()

    def _process_vep_updates(self, data):
        LOGGER.debug("Start _process_vep_updates")

        self._write_debug_output(data, "vep")

        # Don't understand the protobuf dict errors --> convert to json
        vep_json = json.loads(MessageToJson(data, preserving_proto_field_name=True))
        cars = vep_json["vepUpdates"]["updates"]

        if not self._first_vepupdates_processed:
            self._vepupdates_time_first_message = datetime.now()
            self._first_vepupdates_processed = True
            self._arm_dataload_complete_fallback()

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
                    current_car.data_collection_mode = "push"
                    current_car.publish_updates()

                    # Check for newly available sensors after vep_update
                    if self._coordinator_ref:
                        self._hass.async_create_task(self._coordinator_ref.check_missing_sensors_for_vin(vin))

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
                self._cancel_dataload_complete_fallback()

    def _process_vehicle_status_updates(self, data):
        LOGGER.debug("Start _process_vehicle_status_updates")

        self._write_debug_output(data, "vsu")

        vsu_json = json.loads(MessageToJson(data, preserving_proto_field_name=True))
        cars = vsu_json.get("vehicle_status_updates", {}).get("vehicle_status_updates", {})

        if not self._first_vepupdates_processed:
            self._vepupdates_time_first_message = datetime.now()
            self._first_vepupdates_processed = True
            self._arm_dataload_complete_fallback()

        for vin, vsu_car in cars.items():
            if vin in self.excluded_cars:
                continue

            current_car = normalize_vsu_car(vsu_car)

            if DEBUG_SIMULATE_PARTIAL_UPDATES_ONLY and current_car.get("full_update", False) is True:
                current_car["full_update"] = False
                LOGGER.debug(
                    "DEBUG_SIMULATE_PARTIAL_UPDATES_ONLY mode. %s",
                    loghelper.Mask_VIN(vin),
                )

            if current_car.get("full_update") is True:
                LOGGER.debug("Full Update (VSU). %s", loghelper.Mask_VIN(vin))
                if not self._disable_rlock:
                    with self.__lock:
                        self._build_car(current_car, update_mode=False)
                else:
                    self._build_car(current_car, update_mode=False)

            else:
                LOGGER.debug("Partial Update (VSU). %s", loghelper.Mask_VIN(vin))
                if not self._disable_rlock:
                    with self.__lock:
                        self._build_car(current_car, update_mode=True)
                else:
                    self._build_car(current_car, update_mode=True)

            if self._dataload_complete_fired:
                current_car_obj = self.cars.get(vin)
                if current_car_obj:
                    current_car_obj.data_collection_mode = "push"
                    current_car_obj.publish_updates()

                    if self._coordinator_ref:
                        self._hass.async_create_task(self._coordinator_ref.check_missing_sensors_for_vin(vin))

        if not self._dataload_complete_fired:
            fire_complete_event: bool = True
            for car in self.cars.values():
                if not car.entry_setup_complete:
                    fire_complete_event = False
                LOGGER.debug(
                    "_process_vehicle_status_updates - %s - complete: %s - %s",
                    loghelper.Mask_VIN(car.finorvin),
                    car.entry_setup_complete,
                    car.messages_received,
                )
            if fire_complete_event:
                LOGGER.debug("_process_vehicle_status_updates - all completed - fire event: _on_dataload_complete")
                self._hass.async_create_task(self._on_dataload_complete())
                self._dataload_complete_fired = True
                self._cancel_dataload_complete_fallback()

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

    async def charge_program_configure(self, vin: str, program: int, max_soc: None | int = None) -> None:
        """Send the selected charge program to the car."""
        if not self._is_car_feature_available(vin, "CHARGE_PROGRAM_CONFIGURE"):
            raise ServiceValidationError(
                "Can't set the charge program. Feature CHARGE_PROGRAM_CONFIGURE not availabe for this car."
            )

        LOGGER.debug("Start charge_program_configure")
        message = client_pb2.ClientMessage()
        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        charge_programm = pb2_commands.ChargeProgramConfigure()
        charge_programm.charge_program = program
        if max_soc is not None:
            charge_programm.max_soc.value = max_soc
        else:
            try:
                current_charge_programs = getattr(self.cars.get(vin).electric, "chargePrograms", None)
                if current_charge_programs:
                    charge_programm.max_soc.value = current_charge_programs.value[program].get("max_soc")
            except (KeyError, IndexError, TypeError, AttributeError) as err:
                LOGGER.warning(
                    "charge_program_configure - Error: %s - %s",
                    err,
                    getattr(self.cars.get(vin).electric, "chargePrograms", None),
                )

        message.commandRequest.charge_program_configure.CopyFrom(charge_programm)
        LOGGER.debug(
            "charge_program_configure - vin: %s - program: %s - max_soc: %s",
            loghelper.Mask_VIN(vin),
            charge_programm.charge_program,
            charge_programm.max_soc.value,
        )
        await self.execute_car_command(message)
        LOGGER.debug("End charge_program_configure for vin %s", loghelper.Mask_VIN(vin))

    def _week_profile_state(self, vin: str) -> dict[str, Any] | None:
        """Return the weekly profile of a car as the vehicle last reported it.

        Read from the parsed attribute rather than from last_full_message: the
        vehicle reports a profile it has just changed in a *partial* update,
        and last_full_message holds full updates only. Reading it there made
        every entry added since the last full update invisible to the command,
        while the sensor was already showing it.

        None means the integration has not seen a profile at all. That matters
        because the command replaces the vehicle's whole profile: without the
        current list every entry that is not re-sent would be deleted.
        """
        current_car = self.cars.get(vin)
        if not current_car or not current_car.electric:
            return None

        profile = getattr(getattr(current_car.electric, "weeklyProfileRaw", None), "value", None)
        return profile if isinstance(profile, dict) else None

    def _week_profile_parameters(self, vin: str) -> dict[str, dict[str, Any]]:
        """Return the WEEK_PROFILE_CONFIGURE_V2 parameters the car reports, by name.

        The parameter set differs per model: a car that cannot act on an entry
        reports no ACTION_LIST_* parameter at all, and one that offers no choice
        of schedule type lists NO_SELECTION as the only allowed value. An empty
        mapping means the capabilities are unknown - the capability check may be
        switched off - and nothing is then rejected on this ground.
        """
        current_car = self.cars.get(vin)
        if not current_car:
            return {}

        for command in (current_car.capabilities or {}).get("commands") or []:
            if command.get("commandName") != "WEEK_PROFILE_CONFIGURE_V2" or not command.get("isAvailable"):
                continue
            return {
                parameter["parameterName"]: parameter
                for parameter in command.get("parameters") or []
                if parameter.get("parameterName")
            }

        return {}

    @staticmethod
    def _week_profile_schedule_type(name: str | None, days, allowed: set[str]) -> int:
        """Pick the schedule type to send for one entry.

        Derived from the day list when the entry does not carry one, the way the
        app does it: days make the entry recurring, no days make it a one-off.
        A value the car does not allow is replaced by the one it does allow,
        because every entry of the command needs the field set.
        """
        picked = name or ("RECURRING" if days else "NON_RECURRING")
        if allowed and picked not in allowed:
            picked = "NO_SELECTION" if "NO_SELECTION" in allowed else min(allowed)

        return pb2_commands.TimeProfile.ScheduleType.Value(picked)

    def _week_profile_entry_to_proto(self, target, entry: dict[str, Any], allowed: set[str], changed: bool) -> None:
        """Write one weekly profile entry into the command message.

        Both the entry that changed and the ones passed through unchanged go
        through here, so the command carries one consistent shape. Unchanged
        entries keep every value the vehicle reported, including their own
        application identifier - that is how the vehicle tells them apart from
        the one this client touched.
        """
        identifier = entry.get("id")
        if identifier is not None:
            target.identifier.value = int(identifier)

        target.hour.value = int(entry.get("hour") or 0)
        target.minute.value = int(entry.get("minute") or 0)
        target.active.value = bool(entry.get("active"))

        days = entry.get("days") or []
        try:
            for day in days:
                target.days.append(pb2_commands.TimeProfileDay.Value(day))
        except ValueError as err:
            # Dropping the day would silently rewrite the user's profile, since
            # the command replaces the whole list.
            raise ServiceValidationError(
                f"The car reports the weekday {days} for entry {identifier}, which this version does not know. "
                "The weekly profile can't be changed without rewriting that entry."
            ) from err

        for action in entry.get("action_list") or []:
            if not isinstance(action, dict):
                continue
            action_target = target.action_list.add()
            action_target.charging.value = bool(action.get("charging"))
            action_target.precond.value = bool(action.get("precond"))
            action_target.battery_precond.value = bool(action.get("battery_precond"))

        schedule_type = entry.get("schedule_type")
        if isinstance(schedule_type, str):
            schedule_type = schedule_type.removeprefix(WEEKLY_PROFILE_SCHEDULE_TYPE_PREFIX)
        target.schedule_type = self._week_profile_schedule_type(schedule_type, days, allowed)

        target.application_identifier = (
            WEEK_PROFILE_CHANGED_APPLICATION_IDENTIFIER if changed else int(entry.get("application_identifier") or 0)
        )

    async def week_profile_configure(  # noqa: C901
        self,
        vin: str,
        operation: str,
        identifier: int | None = None,
        time: datetime.timedelta | None = None,
        days: list[str] | None = None,
        active: bool | None = None,
        charging: bool | None = None,
        precond: bool | None = None,
        battery_precond: bool | None = None,
        schedule_type: str | None = None,
    ) -> None:
        """Change one entry of the weekly departure profile.

        The service changes a single entry, the command replaces the whole
        profile. So every other entry is re-sent as the vehicle last reported
        it, with its own application identifier, and only the entry that
        changed is marked with -1 - exactly what the Mercedes me app does.

        The operation says which of the three it is. "add" takes no identifier
        at all, because the vehicle assigns one - a caller that names a number
        for a new entry is in fact asking to overwrite the entry that has it,
        and that is not something to do by accident.
        """
        if operation not in WEEK_PROFILE_OPERATIONS:
            raise ServiceValidationError(
                f"Unknown weekly profile operation {operation}. Use one of {WEEK_PROFILE_OPERATIONS}."
            )
        delete = operation == "delete"

        if not self._is_car_feature_available(vin, "WEEK_PROFILE_CONFIGURE_V2"):
            raise ServiceValidationError(
                "Can't configure the weekly profile. Command WEEK_PROFILE_CONFIGURE_V2 is not available for this car."
            )

        profile = self._week_profile_state(vin)
        if profile is None:
            raise ServiceValidationError(
                "The weekly profile of this car is not known yet. It only arrives with a full update, and sending "
                "the command without it would delete every entry the car has. Please retry later."
            )

        entries = [entry for entry in profile.get("time_profiles") or [] if isinstance(entry, dict)]
        parameters = self._week_profile_parameters(vin)

        for name, value in (("CHARGING", charging), ("PRECOND", precond), ("BATTERY_PRECOND", battery_precond)):
            if value is not None and parameters and f"ACTION_LIST_{name}" not in parameters:
                raise ServiceValidationError(
                    f"This car does not support {name.lower()} as an action of a weekly profile entry."
                )

        allowed_schedule_types = set(((parameters.get("SCHEDULE_TYPE") or {}).get("allowedEnums")) or [])
        if schedule_type:
            schedule_type = schedule_type.upper()
            if allowed_schedule_types and schedule_type not in allowed_schedule_types:
                raise ServiceValidationError(
                    f"This car only accepts {sorted(allowed_schedule_types)} as the schedule type of a weekly "
                    f"profile entry, not {schedule_type}."
                )

        if operation == "add":
            if identifier is not None:
                raise ServiceValidationError(
                    f"A new weekly profile entry takes no identifier - the car assigns one, and {identifier} is the "
                    f"number of an entry that would be overwritten. Use the update operation for that."
                )
            if time is None:
                raise ServiceValidationError("Adding a weekly profile entry needs a time.")
        elif identifier is None:
            raise ServiceValidationError(
                f"The {operation} operation needs the identifier of the entry, as the Active weekly profile sensor "
                f"lists it."
            )

        known = {entry.get("id") for entry in entries}
        if identifier is not None and identifier not in known:
            # None in the set is an entry this client has just added: it goes
            # out without an identifier and only gets one when the car reports
            # the profile back, a few seconds later.
            pending = (
                " An entry that was just added is still waiting for its number from the car - retry in a moment."
                if None in known
                else ""
            )
            raise ServiceValidationError(
                f"This car has no weekly profile entry with the identifier {identifier}. Reported entries: "
                f"{sorted(entry for entry in known if entry is not None)}.{pending}"
            )

        # max_number_of_time_profiles_user is the limit for the entries a user
        # may add; vehicles that do not report it leave it at zero, and the
        # overall limit applies.
        limit = int(profile.get("max_number_of_time_profiles_user") or 0) or int(
            profile.get("max_number_of_time_profiles") or 0
        )
        if operation == "add" and limit and len(entries) >= limit:
            raise ServiceValidationError(
                f"This car holds at most {limit} weekly profile entries and already has {len(entries)}. "
                "Please delete one first."
            )

        changed: dict[str, Any] = {}
        if not delete:
            # Start from the entry as reported, so the fields the caller did not
            # name keep their value.
            changed = dict(next((entry for entry in entries if entry.get("id") == identifier), {}))
            if time is not None:
                changed["hour"] = time.seconds // 3600
                changed["minute"] = (time.seconds % 3600) // 60
            if days is not None:
                changed["days"] = [day.upper() for day in days]
            if active is not None:
                changed["active"] = active
            if schedule_type:
                changed["schedule_type"] = schedule_type
            if charging is not None or precond is not None or battery_precond is not None:
                # The vehicle may report several action entries, each carrying
                # one flag. They mean the same as one entry carrying all of
                # them, so the changed entry is written as a single one.
                actions = {"charging": False, "precond": False, "battery_precond": False}
                for action in changed.get("action_list") or []:
                    if isinstance(action, dict):
                        actions = {key: value or bool(action.get(key)) for key, value in actions.items()}
                actions.update(
                    {
                        key: value
                        for key, value in (
                            ("charging", charging),
                            ("precond", precond),
                            ("battery_precond", battery_precond),
                        )
                        if value is not None
                    }
                )
                changed["action_list"] = [actions]

        config = pb2_commands.WeekProfileConfigureV2()
        updated: list[dict[str, Any]] = []
        for entry in entries:
            # On add every reported entry is passed through - including one
            # whose id the vehicle left at zero and therefore omitted, which
            # must not be mistaken for the new entry.
            if operation == "add" or entry.get("id") != identifier:
                self._week_profile_entry_to_proto(config.time_profiles.add(), entry, allowed_schedule_types, False)
                updated.append(entry)
                continue
            if delete:
                # A deletion is an entry that carries nothing but its
                # identifier, so the vehicle drops it from the list.
                removed = config.time_profiles.add()
                removed.identifier.value = int(identifier)
                removed.application_identifier = WEEK_PROFILE_CHANGED_APPLICATION_IDENTIFIER
                continue
            self._week_profile_entry_to_proto(config.time_profiles.add(), changed, allowed_schedule_types, True)
            updated.append(changed)

        if operation == "add":
            # A new entry carries no identifier at all; the vehicle assigns one.
            self._week_profile_entry_to_proto(config.time_profiles.add(), changed, allowed_schedule_types, True)
            updated.append(changed)

        message = client_pb2.ClientMessage()
        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.week_profile_configure_v2.CopyFrom(config)

        LOGGER.debug(
            "week_profile_configure - vin: %s - operation: %s - identifier: %s - requested: %s - entries sent: %s",
            loghelper.Mask_VIN(vin),
            operation,
            identifier,
            # What the caller actually asked for. Without it a log only shows
            # that a call happened, not whether a field the car ignored was
            # ever sent.
            {
                key: value
                for key, value in (
                    ("time", str(time) if time is not None else None),
                    ("days", days),
                    ("active", active),
                    ("charging", charging),
                    ("precond", precond),
                    ("battery_precond", battery_precond),
                    ("schedule_type", schedule_type),
                )
                if value is not None
            },
            len(config.time_profiles),
        )
        await self.execute_car_command(message)

        self._week_profile_store(vin, profile, updated)
        LOGGER.debug("End week_profile_configure for vin %s", loghelper.Mask_VIN(vin))

    def _week_profile_store(self, vin: str, profile: dict[str, Any], entries: list[dict[str, Any]]) -> None:
        """Remember the profile that was just sent, and refresh the sensor.

        The vehicle reports its profile only in full updates, which can be a
        while away. Until then the next call has to build its list from what
        was sent, or it would re-send the superseded list and undo the change.
        The stored state is therefore what was asked for, not yet what the
        vehicle confirmed; the next full update replaces it either way.
        """
        current_car = self.cars.get(vin)
        if not current_car or not current_car.electric:
            # The command has already gone out at this point, so a car without
            # the parsed state must not turn into an exception on the service
            # call - it only means the sensor catches up with the next update.
            LOGGER.debug(
                "week_profile_configure - no parsed state to update for car %s",
                loghelper.Mask_VIN(vin),
            )
            return

        reported = getattr(current_car.electric, "weeklyProfileRaw", None)
        # Shaped like the attribute of a message, so the stored state goes
        # through the same normalisation as a reported one.
        detail = {
            "attributes": {
                "weeklyProfile": {
                    "value": {**profile, "time_profiles": entries},
                    "status": getattr(reported, "retrievalstatus", "VALID"),
                    "timestamp": getattr(reported, "timestamp", 0),
                }
            }
        }
        for option in (
            "weeklyProfileRaw",
            "weeklyProfileActive",
            "weeklyProfileTimeProfiles",
            "weeklyProfileLimits",
        ):
            value = self._get_car_values_handle_weekly_profile(detail, current_car.electric, option, True, vin)
            if value is not None:
                setattr(current_car.electric, option, value)
        current_car.publish_updates()

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

        if status_t1 and start_t1 is not None and stop_t1 is not None and status_t1 in ("active", "inactive"):
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

        if status_t2 and start_t2 is not None and stop_t2 is not None and status_t2 in ("active", "inactive"):
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

        if status_t3 and start_t3 is not None and stop_t3 is not None and status_t3 in ("active", "inactive"):
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

        if status_t4 and start_t4 is not None and stop_t4 is not None and status_t4 in ("active", "inactive"):
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

    async def charge_coupler_stop(self, vin: str, pin: str = ""):
        """Send the charge coupler stop command to the car."""
        LOGGER.info("Start charge_coupler_stop for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "CHARGE_COUPLER_STOP"):
            LOGGER.warning(
                "Can't stop the charge coupler for car %s. Feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        _pin = pin.strip() if pin else self.pin

        if not _pin:
            LOGGER.warning(
                "Can't stop the charge coupler for car %s. PIN not set. Please set the PIN -> Integration, Options "
                "or use the optional parameter of the service",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.charge_coupler_stop.pin = _pin

        await self.execute_car_command(message)
        LOGGER.info("End charge_coupler_stop for vin %s", loghelper.Mask_VIN(vin))

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
                with Path(target_file_name).open(mode="wb") as zf:
                    zf.write(zip_file)

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

    async def battery_max_soc_configure(self, vin: str, max_soc: int, charge_program: int | None = None):
        """Send the maxsoc configure command to the car."""
        if charge_program is None:
            # No program given: configure the program the car is currently running,
            # so that setting the target does not switch the car to another program.
            current_car = self.cars.get(vin)
            selected_program = (
                self._get_car_value(current_car.electric, "selectedChargeProgram", "value", 0) if current_car else 0
            )
            charge_program = int(selected_program) if selected_program is not None else 0

        LOGGER.info(
            "Start battery_max_soc_configure to %s for vin %s and program %s",
            max_soc,
            loghelper.Mask_VIN(vin),
            charge_program,
        )

        if (
            not self._is_car_feature_available(vin, "BATTERY_MAX_SOC_CONFIGURE")
            and not self._is_car_feature_available(vin, "CHARGING_CONFIGURE")
            and not self._is_car_feature_available(vin, "CHARGE_PROGRAM_CONFIGURE")
        ):
            LOGGER.warning(
                "Can't configure battery_max_soc for car %s. Features BATTERY_MAX_SOC_CONFIGURE, CHARGING_CONFIGURE or CHARGE_PROGRAM_CONFIGURE not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())

        if self._is_car_feature_available(vin, "CHARGING_CONFIGURE"):
            LOGGER.debug(
                "CHARGING_CONFIGURE=true for car %s. Will use ChargingConfigure.",
                loghelper.Mask_VIN(vin),
            )
            charging_config = pb2_commands.ChargingConfigure()
            charging_config.max_soc.value = max_soc
            # charging_config.charge_program = charge_program
            message.commandRequest.charging_configure.CopyFrom(charging_config)
        else:
            max_soc = max(max_soc, 50)
            charge_program_config = pb2_commands.ChargeProgramConfigure()
            charge_program_config.max_soc.value = max_soc
            charge_program_config.charge_program = charge_program
            message.commandRequest.charge_program_configure.CopyFrom(charge_program_config)

        await self.execute_car_command(message)
        LOGGER.info("End battery_max_soc_configure for vin %s", loghelper.Mask_VIN(vin))

    async def engine_start(self, vin: str, pin: str = ""):
        """Send the engine start command to the car."""
        LOGGER.info("Start engine start for vin %s", loghelper.Mask_VIN(vin))

        if pin and pin.strip():
            _pin = pin
        else:
            _pin = self.pin

        if not _pin:
            LOGGER.warning(
                "Can't start the car %s. PIN not given. Please set the PIN -> Integration, Options or use the optional parameter of the service.",
                loghelper.Mask_VIN(vin),
            )
            return

        if not self._is_car_feature_available(vin, "ENGINE_START"):
            LOGGER.warning(
                "Can't start engine for car %s. Feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.engine_start.pin = _pin

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

    async def hv_battery_start_conditioning(self, vin: str):
        """Send the hv battery conditioning start command to the car."""
        LOGGER.info("Start hv_battery_start_conditioning for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "HVBATTERY_START_CONDITIONING"):
            LOGGER.warning(
                "Can't start hv battery conditioning for car %s. Feature not available for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        hv_battery_conditioning_start = pb2_commands.HvBatteryStartConditioning()
        message.commandRequest.hv_battery_start_conditioning.CopyFrom(hv_battery_conditioning_start)

        await self.execute_car_command(message)
        LOGGER.info("End hv_battery_start_conditioning for vin %s", loghelper.Mask_VIN(vin))

    async def hv_battery_stop_conditioning(self, vin: str):
        """Send the hv battery conditioning stop command to the car."""
        LOGGER.info("Start hv_battery_stop_conditioning for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "HVBATTERY_STOP_CONDITIONING"):
            LOGGER.warning(
                "Can't stop hv battery conditioning for car %s. Feature not available for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        hv_battery_conditioning_stop = pb2_commands.HvBatteryStopConditioning()
        message.commandRequest.hv_battery_stop_conditioning.CopyFrom(hv_battery_conditioning_stop)

        await self.execute_car_command(message)
        LOGGER.info("End hv_battery_stop_conditioning for vin %s", loghelper.Mask_VIN(vin))

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

    async def sigpos_start(
        self,
        vin: str,
        *,
        sigpos_type: int = 0,
        sigpos_duration: int = 8,
        horn_repeat: int | None = None,
        horn_type: int | None = None,
        light_type: int | None = None,
    ):
        """Send a sigpos command to the car.

        sigpos_type: 0=LIGHT_ONLY, 1=HORN_ONLY, 2=LIGHT_AND_HORN, 3=PANIC_ALARM
            Which modes a car accepts is reported by the SIGPOS_TYPE command parameter
        sigpos_duration: Signaling duration in seconds. Some cars cap this value
        horn_repeat, horn_type, light_type: Derived from sigpos_type when not given
        """
        LOGGER.info("Start sigpos_start for vin %s", loghelper.Mask_VIN(vin))

        if not self._is_car_feature_available(vin, "SIGPOS_START"):
            LOGGER.warning(
                "Can't start signaling for car %s. Feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        sigpos = pb2_commands.SigPosStart
        if sigpos_type not in SIGPOS_TYPE_DEFAULTS:
            LOGGER.warning(
                "Can't start signaling for car %s. Unknown sigpos_type %s",
                loghelper.Mask_VIN(vin),
                sigpos_type,
            )
            return

        default_repeat, default_horn_type, default_light_type = SIGPOS_TYPE_DEFAULTS[sigpos_type]

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.sigpos_start.horn_repeat = default_repeat if horn_repeat is None else horn_repeat
        message.commandRequest.sigpos_start.horn_type = default_horn_type if horn_type is None else horn_type
        message.commandRequest.sigpos_start.light_type = default_light_type if light_type is None else light_type
        message.commandRequest.sigpos_start.sigpos_duration = sigpos_duration
        message.commandRequest.sigpos_start.sigpos_type = sigpos_type

        LOGGER.debug(
            "sigpos_start for vin %s - type: %s, duration: %s",
            loghelper.Mask_VIN(vin),
            sigpos.SigposType.Name(sigpos_type),
            sigpos_duration,
        )

        await self.execute_car_command(message)
        LOGGER.info("End sigpos_start for vin %s", loghelper.Mask_VIN(vin))

    async def sigpos_start_horn(self, vin: str):
        """Start acoustic signaling of the car, using the mode the car supports."""
        sigpos_type = self._preferred_horn_sigpos_type(vin)

        if sigpos_type is None:
            LOGGER.warning(
                "Can't start horn signaling for car %s. No acoustic signaling mode available for this car",
                loghelper.Mask_VIN(vin),
            )
            return

        await self.sigpos_start(vin, sigpos_type=sigpos_type)

    def _allowed_sigpos_types(self, vin: str) -> set[str]:
        """Return the SIGPOS_TYPE values the car reports for the SIGPOS_START command."""
        current_car = self.cars.get(vin)
        if not current_car:
            return set()

        for command in (current_car.capabilities or {}).get("commands") or []:
            if command.get("commandName") != "SIGPOS_START" or not command.get("isAvailable"):
                continue
            for parameter in command.get("parameters") or []:
                if parameter.get("parameterName") == "SIGPOS_TYPE":
                    return set(parameter.get("allowedEnums") or [])

        return set()

    def _preferred_horn_sigpos_type(self, vin: str) -> int | None:
        """Pick the acoustic signaling mode of the car, in the order the app prefers.

        Returns None when the car reports SIGPOS_TYPE values but none of them is
        acoustic. Falls back to the first preference when no values are reported at
        all, which is the case while the capability check is switched off.
        """
        allowed = self._allowed_sigpos_types(vin)

        if not allowed:
            LOGGER.debug(
                "No SIGPOS_TYPE capability for car %s, falling back to %s",
                loghelper.Mask_VIN(vin),
                SIGPOS_HORN_TYPES[0],
            )
            return pb2_commands.SigPosStart.SigposType.Value(SIGPOS_HORN_TYPES[0])

        for name in SIGPOS_HORN_TYPES:
            if name in allowed:
                return pb2_commands.SigPosStart.SigposType.Value(name)

        return None

    async def sunroof_open(self, vin: str, pin: str = ""):
        """Send a sunroof open command to the car."""
        LOGGER.info("Start sunroof_open for vin %s", loghelper.Mask_VIN(vin))

        if pin and pin.strip():
            _pin = pin
        else:
            _pin = self.pin

        if not _pin:
            LOGGER.warning(
                "Can't open the sunroof - car %s. PIN not given. Please set the PIN -> Integration, Options or use the optional parameter of the service.",
                loghelper.Mask_VIN(vin),
            )
            return

        if not self._is_car_feature_available(vin, "SUNROOF_OPEN"):
            LOGGER.warning(
                "Can't open the sunroof for car %s. Feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.sunroof_open.pin = _pin

        await self.execute_car_command(message)
        LOGGER.info("End sunroof_open for vin %s", loghelper.Mask_VIN(vin))

    async def sunroof_tilt(self, vin: str, pin: str = ""):
        """Send a sunroof tilt command to the car."""
        LOGGER.info("Start sunroof_tilt for vin %s", loghelper.Mask_VIN(vin))

        if pin and pin.strip():
            _pin = pin
        else:
            _pin = self.pin

        if not _pin:
            LOGGER.warning(
                "Can't tilt the sunroof - car %s. PIN not given. Please set the PIN -> Integration, Options or use the optional parameter of the service.",
                loghelper.Mask_VIN(vin),
            )
            return

        if not self._is_car_feature_available(vin, "SUNROOF_LIFT"):
            LOGGER.warning(
                "Can't tilt the sunroof for car %s. Feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.sunroof_lift.pin = _pin

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
        """Disable scheduled departure preconditioning."""
        LOGGER.info("Start preheat_stop_departure_time for vin %s", loghelper.Mask_VIN(vin))
        await self.preconditioning_configure(vin, departure_time_mode=0)
        LOGGER.info("End preheat_stop_departure_time for vin %s", loghelper.Mask_VIN(vin))

    async def preconditioning_configure(self, vin: str, departure_time_mode: int = 0, departure_time: int = 0):
        """Configure preconditioning departure time mode.

        departure_time_mode: 0=DISABLED, 1=SINGLE_DEPARTURE, 2=WEEKLY_DEPARTURE
            Note: WEEKLY_DEPARTURE (mode 2) is not supported on all car models
            (e.g., EQB supports only DISABLED and SINGLE_DEPARTURE)
        departure_time: Minutes after midnight (0-1439), only used when mode > 0
        """
        LOGGER.info(
            "Start preconditioning_configure for vin %s with mode %s", loghelper.Mask_VIN(vin), departure_time_mode
        )

        if not self._is_car_feature_available(vin, "ZEV_PRECONDITION_CONFIGURE"):
            LOGGER.warning(
                "Can't configure PreCond for car %s. Feature not available for this car",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.zev_precondition_configure.departure_time_mode = departure_time_mode
        if departure_time_mode > 0:
            message.commandRequest.zev_precondition_configure.departure_time = departure_time

        await self.execute_car_command(message)
        LOGGER.info("End preconditioning_configure for vin %s", loghelper.Mask_VIN(vin))

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
            elif getattr(car.precond, "temperature_points_frontLeft", None):
                zone_front_left.temperature_in_celsius = car.precond.temperature_points_frontLeft.value
            entry_set = True

        if front_right or rear_left or rear_right:
            zone_front_right = config.temperature_points.add()
            zone_front_right.zone = 2
            if front_right:
                zone_front_right.temperature_in_celsius = front_right
            elif getattr(car.precond, "temperature_points_frontRight", None):
                zone_front_right.temperature_in_celsius = car.precond.temperature_points_frontRight.value
            entry_set = True

        if rear_left or rear_right:
            zone_rear_left = config.temperature_points.add()
            zone_rear_left.zone = 4
            if rear_left:
                zone_rear_left.temperature_in_celsius = rear_left
            elif getattr(car.precond, "temperature_points_rearLeft", None):
                zone_rear_left.temperature_in_celsius = car.precond.temperature_points_rearLeft.value
            entry_set = True

        if rear_right or rear_left:
            zone_rear_right = config.temperature_points.add()
            zone_rear_right.zone = 5
            if rear_right:
                zone_rear_right.temperature_in_celsius = rear_right
            elif getattr(car.precond, "temperature_points_rearRight", None):
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
        self, vin: str, front_left: int, front_right: int, rear_left: int, rear_right: int, pin: str = ""
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

        if pin and pin.strip():
            _pin = pin
        else:
            _pin = self.pin

        if not _pin:
            LOGGER.warning(
                "Can't move the windows - car %s. PIN not given. Please set the PIN -> Integration, Options or use the optional parameter of the service.",
                loghelper.Mask_VIN(vin),
            )
            return

        if not self._is_car_feature_available(vin, "variableOpenableWindow"):
            LOGGER.warning(
                "Can't move windows for car %s. Feature not availabe for this car.",
                loghelper.Mask_VIN(vin),
            )
            return

        message = client_pb2.ClientMessage()

        message.commandRequest.vin = vin
        message.commandRequest.request_id = str(uuid.uuid4())
        message.commandRequest.windows_move.pin = _pin
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

            with Path(f"{path}/{datatype}{int(round(time.time() * 1000))}").open("wb") as current_file:
                current_file.write(data.SerializeToString())

            self.write_debug_json_output(MessageToJson(data, preserving_proto_field_name=True), datatype)

    def write_debug_json_output(self, data, datatype, use_dumps: bool = False):
        """Write text to files based on datatype."""
        # LOGGER.debug(self.config_entry.options)
        if self.config_entry.options.get(CONF_DEBUG_FILE_SAVE, False):
            path = self._debug_save_path
            Path(path).mkdir(parents=True, exist_ok=True)

            with Path(f"{path}/{datatype}{int(round(time.time() * 1000))}.json").open(
                "w", encoding="utf-8"
            ) as current_file:
                if use_dumps:
                    current_file.write(f"{json.dumps(data, indent=4)}")
                else:
                    current_file.write(f"{data}")

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

            if self.websocket and self.websocket.account_blocked:
                LOGGER.debug("start get_car_p2b_data_via_rest: %s", loghelper.Mask_VIN(vin))
                p2b_data = await self.webapi.get_car_p2b_data_via_rest(vin)
                self._process_rest_vep_update(p2b_data)

            if not car.has_geofencing:
                return

            if car.geofence_events is None:
                car.geofence_events = GeofenceEvents()

            LOGGER.debug("start get_car_geofencing_violations: %s", loghelper.Mask_VIN(vin))
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

    @callback
    def _arm_dataload_complete_fallback(self) -> None:
        """Start the fallback timer for the entity creation."""
        if self._dataload_fallback_handle is not None:
            return

        self._dataload_fallback_handle = async_call_later(
            self._hass, DATALOAD_COMPLETE_FALLBACK_DELAY, self._async_dataload_complete_fallback
        )

    @callback
    def _cancel_dataload_complete_fallback(self) -> None:
        """Cancel the fallback timer for the entity creation."""
        if self._dataload_fallback_handle is not None:
            self._dataload_fallback_handle()
            self._dataload_fallback_handle = None

    @callback
    def _async_dataload_complete_fallback(self, _now) -> None:
        """Create the entities when not every car reported a full data set in time."""
        self._dataload_fallback_handle = None

        if self._dataload_complete_fired:
            return

        LOGGER.debug(
            "Dataload fallback after %s seconds - fire event: _on_dataload_complete", DATALOAD_COMPLETE_FALLBACK_DELAY
        )
        self._dataload_complete_fired = True
        self._hass.async_create_task(self._on_dataload_complete())
