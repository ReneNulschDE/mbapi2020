"""Constants for the MercedesME 2020 integration."""
from enum import Enum
import logging

import voluptuous as vol

from homeassistant.const import (
    LENGTH_KILOMETERS,
    PERCENTAGE,
    Platform)

from homeassistant.helpers import (
    config_validation as cv,
)


MERCEDESME_COMPONENTS = [
    Platform.SENSOR,
    Platform.LOCK,
    Platform.BINARY_SENSOR,
    Platform.DEVICE_TRACKER,
    Platform.SWITCH
]

REGION_EUROPE = "Europe"
REGION_NORAM = "North America"
REGION_APAC = "Asia-Pacific"

CONF_ALLOWED_REGIONS = [REGION_EUROPE, REGION_NORAM, REGION_APAC]
CONF_LOCALE = "locale"
CONF_COUNTRY_CODE = "country_code"
CONF_EXCLUDED_CARS = "excluded_cars"
CONF_PIN = "pin"
CONF_REGION = "region"
CONF_VIN = "vin"
CONF_TIME = "time"
CONF_DEBUG_FILE_SAVE = "save_files"
CONF_FT_DISABLE_CAPABILITY_CHECK = "cap_check_disabled"

DATA_CLIENT = "data_client"

DOMAIN = "mbapi2020"
LOGGER = logging.getLogger(__package__)

DEFAULT_CACHE_PATH = "custom_components/mbapi2020/messages"
DEFAULT_TOKEN_PATH = ".mercedesme-token-cache"
DEFAULT_LOCALE = "en-GB"
DEFAULT_COUNTRY_CODE = "EN"

RIS_APPLICATION_VERSION_NA = "3.0.1"
RIS_APPLICATION_VERSION_PA = "1.6.2"
RIS_APPLICATION_VERSION = "1.6.3"
RIS_SDK_VERSION = "2.30.0"

VERIFY_SSL = True

LOGIN_APP_ID_EU = "01398c1c-dc45-4b42-882b-9f5ba9f175f1"
LOGIN_BASE_URI = "https://id.mercedes-benz.com"
LOGIN_BASE_URI_NA = "https://id.mercedes-benz.com"
LOGIN_BASE_URI_PA = "https://id.mercedes-benz.com"
REST_API_BASE = "https://bff-prod.risingstars.daimler.com"
REST_API_BASE_NA = "https://bff-prod.risingstars-amap.daimler.com"
REST_API_BASE_PA = "https://bff-prod.risingstars-amap.daimler.com"
WEBSOCKET_API_BASE = "wss://websocket-prod.risingstars.daimler.com/ws"
WEBSOCKET_API_BASE_NA = "wss://websocket-prod.risingstars-amap.daimler.com/ws"
WEBSOCKET_API_BASE_PA = "wss://websocket-prod.risingstars-amap.daimler.com/ws"
WEBSOCKET_USER_AGENT = "okhttp/3.12.2"
DEFAULT_SOCKET_MIN_RETRY = 15


SERVICE_REFRESH_TOKEN_URL = "refresh_access_token"
SERVICE_AUXHEAT_CONFIGURE = "auxheat_configure"
SERVICE_AUXHEAT_START = "auxheat_start"
SERVICE_AUXHEAT_STOP = "auxheat_stop"
SERVICE_BATTERY_MAX_SOC_CONFIGURE = "battery_max_soc_configure"
SERVICE_DOORS_LOCK_URL = "doors_lock"
SERVICE_DOORS_UNLOCK_URL = "doors_unlock"
SERVICE_ENGINE_START = "engine_start"
SERVICE_ENGINE_STOP = "engine_stop"
SERVICE_SEND_ROUTE = "send_route"
SERVICE_SIGPOS_START = "sigpos_start"
SERVICE_SUNROOF_OPEN = "sunroof_open"
SERVICE_SUNROOF_CLOSE = "sunroof_close"
SERVICE_PREHEAT_START = "preheat_start"
SERVICE_PREHEAT_START_DEPARTURE_TIME = "preheat_start_departure_time"
SERVICE_PREHEAT_STOP = "preheat_stop"
SERVICE_WINDOWS_OPEN = "windows_open"
SERVICE_WINDOWS_CLOSE = "windows_close"
SERVICE_VIN_SCHEMA = vol.Schema({vol.Required(CONF_VIN): cv.string})
SERVICE_VIN_TIME_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_VIN): cv.string,
        vol.Required(CONF_TIME): vol.All(vol.Coerce(int), vol.Range(min=0, max=1439))
    }
)
SERVICE_AUXHEAT_CONFIGURE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_VIN): cv.string,
        vol.Required("time_selection"): vol.All(vol.Coerce(int), vol.Range(min=0, max=3)),
        vol.Required("time_1"): vol.All(vol.Coerce(int), vol.Range(min=0, max=1439)),
        vol.Required("time_2"): vol.All(vol.Coerce(int), vol.Range(min=0, max=1439)),
        vol.Required("time_3"): vol.All(vol.Coerce(int), vol.Range(min=0, max=1439))
    }
)
SERVICE_PREHEAT_START_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_VIN): cv.string,
        vol.Required("type", default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=1))
    }
)
SERVICE_SEND_ROUTE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_VIN): cv.string,
        vol.Required("title"): cv.string,
        vol.Required("latitude"): cv.latitude,
        vol.Required("longitude"): cv.longitude,
        vol.Required("city"): cv.string,
        vol.Required("postcode"): cv.string,
        vol.Required("street"): cv.string,
    }
)
SERVICE_BATTERY_MAX_SOC_CONFIGURE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_VIN): cv.string,
        vol.Required("max_soc", default=100): vol.All(vol.Coerce(int), vol.In([50, 60, 70, 80, 90, 100]))
    }
)


ATTR_MB_MANUFACTURER = "Mercedes Benz"

# "internal_name":[ 0 Display_Name
#                   1 unit_of_measurement,
#                   2 object in car.py
#                   3 attribute in car.py
#                   4 value field
#                   5 unused --> None (for capabilities check in the future)
#                   6 [list of extended attributes]
#                   7 icon
#                   8 device_class
#                   9 invert boolean value - Default: False
#                   10 entity_category
# ]

BinarySensors = {

    "liquidRangeCritical":[     "Liquid Range Critical",
                                None,
                                "binarysensors",
                                "liquidRangeCritical",
                                "value",
                                None,
                                None,
                                "mdi:gas-station",
                                "problem",
                                False,
                                None],

    "warningbrakefluid": [      "Low Brake Fluid Warning",
                                None,
                                "binarysensors",
                                "warningbrakefluid",
                                "value",
                                None,
                                None,
                                "mdi:car-brake-alert",
                                "problem",
                                False,
                                None],

    "warningwashwater": [       "Low Wash Water Warning",
                                None,
                                "binarysensors",
                                "warningwashwater",
                                "value",
                                None,
                                None,
                                "mdi:wiper-wash",
                                "problem",
                                False,
                                None],

    "warningcoolantlevellow": [ "Low Coolant Level Warning",
                                None,
                                "binarysensors",
                                "warningcoolantlevellow",
                                "value",
                                None,
                                None,
                                "mdi:oil-level",
                                "problem",
                                False,
                                None],

    "warningenginelight": [     "Engine Light Warning",
                                None,
                                "binarysensors",
                                "warningenginelight",
                                "value",
                                None,
                                {
                                    "warningbrakefluid",
                                    "warningwashwater",
                                    "warningcoolantlevellow",
                                    "warninglowbattery"
                                },
                                "mdi:engine",
                                "problem",
                                False,
                                None],

    "parkbrakestatus": [        "Park Brake Status",
                                None,
                                "binarysensors",
                                "parkbrakestatus",
                                "value",
                                None,
                                {
                                    "preWarningBrakeLiningWear"
                                },
                                "mdi:car-brake-parking",
                                None,
                                True,
                                None],

    "windowStatusOverall": [    "Windows Closed",
                                None,
                                "windows",
                                "windowStatusOverall",
                                "value",
                                None,
                                {
                                    "windowstatusrearleft",
                                    "windowstatusrearright",
                                    "windowstatusfrontright",
                                    "windowstatusfrontleft"
                                },
                                "mdi:car-door",
                                None,
                                False,
                                None],

    "tirewarninglamp": [        "Tire Warning",
                                None,
                                "tires",
                                "tirewarninglamp",
                                "value",
                                None,
                                {
                                    "tirepressureRearLeft",
                                    "tirepressureRearRight",
                                    "tirepressureFrontRight",
                                    "tirepressureFrontLeft",
                                    "tireMarkerFrontRight",
                                    "tireMarkerFrontLeft",
                                    "tireMarkerRearLeft",
                                    "tireMarkerRearRight",
                                    "tirewarningsrdk",
                                    "tirewarningsprw",
                                    "tireTemperatureRearLeft",
                                    "tireTemperatureFrontRight",
                                    "tireTemperatureRearRight",
                                    "tireTemperatureFrontLeft"
                                },
                                "mdi:car-tire-alert",
                                "problem",
                                False,
                                None],

    "remoteStartActive": [      "Remote Start Active",
                                None,
                                "binarysensors",
                                "remoteStartActive",
                                "value",
                                None,
                                None,
                                "mdi:engine-outline",
                                None,
                                False,
                                None],

    "engineState": [            "Engine State",
                                None,
                                "binarysensors",
                                "engineState",
                                "value",
                                None,
                                None,
                                "mdi:engine",
                                None,
                                False,
                                None]
}

DEVICE_TRACKER = {
    "tracker": [                "Device Tracker",
                                None,
                                "location",
                                "positionLong",
                                "value",
                                None,
                                {
                                    "positionHeading"
                                },
                                None,
                                None,
                                False,
                                None]
}

SENSORS = {
    "chargingpower":  [         "Charging Power",
                                "kW",
                                "electric",
                                "chargingPower",
                                "value",
                                None,
                                {},
                                "mdi:ev-station",
                                "energy",
                                False,
                                None],
    "rcp_features":  [          "RCP Features",
                                None,
                                "rcp_options",
                                "rcp_supported",
                                "value",
                                None,
                                {
                                    "rcp_supported_settings"
                                },
                                "mdi:car",
                                None,
                                False,
                                "diagnostic"],

    "car":  [                   "Car",
                                None,
                                None,
                                "full_updatemessages_received",
                                "value",
                                None,
                                {
                                    'partital_updatemessages_received',
                                    'last_message_received',
                                    'last_command_type',
                                    'last_command_state',
                                    'last_command_error_code',
                                    'last_command_error_message',
                                    'is_owner'
                                },
                                "mdi:car",
                                None,
                                False,
                                "diagnostic"],

    "lock": [                  "Lock",
                                None,
                                "doors",
                                "doorlockstatusvehicle",
                                "value",
                                None,
                                {
                                    'decklidstatus',
                                    'doorStatusOverall',
                                    'doorLockStatusOverall',
                                    'doorlockstatusgas',
                                    'doorlockstatusvehicle',
                                    'doorlockstatusfrontleft',
                                    'doorlockstatusfrontright',
                                    'doorlockstatusrearright',
                                    'doorlockstatusrearleft',
                                    'doorlockstatusdecklid',
                                    'doorstatusrearleft',
                                    'doorstatusfrontright',
                                    'doorstatusrearright',
                                    'doorstatusfrontleft',
                                    'rooftopstatus',
                                    'sunroofstatus',
                                    'engineHoodStatus',
                                    'tankCapOpenLamp'
                                },
                                "mdi:car-key",
                                None,
                                False,
                                None],

    "rangeElectricKm": [        "Range Electric",
                                LENGTH_KILOMETERS,
                                "electric",
                                "rangeelectric",
                                "display_value",
                                None,
                                {
                                    'chargingactive',
                                    'chargingstatus',
                                    'distanceElectricalReset',
                                    'distanceElectricalStart',
                                    'ecoElectricBatteryTemperature',
                                    'electricconsumptionstart',
                                    'electricconsumptionreset',
                                    'endofchargetime',
                                    'precondActive',
                                    'precondNow',
                                    'maxrange',
                                    'selectedChargeProgram',
                                    'soc',
                                    'chargingPower'
                                },
                                "mdi:ev-station",
                                None,
                                False,
                                None],
    "soc":                  ["State of Charge",
                             PERCENTAGE,
                             "electric",
                             "soc",
                             "value",
                             None,
                             {
                                'maxSocLowerLimit',
                                'maxSoc',
                                'chargingPower'
                             },
                             "mdi:ev-station",
                             None,
                             False,
                                None],


    "auxheatstatus": [          "Auxheat Status",
                                None,
                                "auxheat",
                                "auxheatstatus",
                                "value",
                                None,
                                {
                                    "auxheatActive",
                                    "auxheatwarnings",
                                    "auxheatruntime",
                                    "auxheatwarningsPush",
                                    "auxheattimeselection",
                                    "auxheattime1",
                                    "auxheattime2",
                                    "auxheattime3"
                                },
                                "mdi:radiator",
                                None,
                                False,
                                None],

    "tanklevelpercent": [       "Fuel Level",
                                "%",
                                "odometer",
                                "tanklevelpercent",
                                "value",
                                None,
                                {
                                    "tankLevelAdBlue",
                                    "gasTankLevelPercent"
                                },
                                "mdi:gas-station",
                                None,
                                False,
                                None],

    "odometer": [               "Odometer",
                                LENGTH_KILOMETERS,
                                "odometer",
                                "odo",
                                "display_value",
                                None,
                                {
                                    "averageSpeedReset",
                                    "averageSpeedStart",
                                    "batteryState",
                                    "distanceReset",
                                    "distanceStart",
                                    "distanceZEReset",
                                    "drivenTimeZEReset",
                                    "drivenTimeReset",
                                    "drivenTimeStart",
                                    "ecoscoretotal",
                                    "ecoscorefreewhl",
                                    "ecoscorebonusrange",
                                    "ecoscoreconst",
                                    "ecoscoreaccel",
                                    "gasconsumptionstart",
                                    "gasconsumptionreset",
                                    "gasTankRange",
                                    "gasTankLevel",
                                    "liquidconsumptionstart",
                                    "liquidconsumptionreset",
                                    "liquidRangeSkipIndication",
                                    "rangeliquid",
                                    "outsideTemperature",
                                    "serviceintervaldays",
                                    "tanklevelpercent",
                                    "tankReserveLamp",
                                    "tankLevelAdBlue",
                                    "vehicleDataConnectionState"
                                },
                                "mdi:car-cruise-control",
                                None,
                                False,
                                None],

    "CarAlarm": [              "Car Alarm",
                                None,
                                "caralarm",
                                "carAlarm",
                                "value",
                                None,
                                {
                                    "lastTheftWarning",
                                    "towSensor",
                                    "theftSystemArmed",
                                    "parkEventType",
                                    "parkEventLevel",
                                    "carAlarmLastTime",
                                    "towProtectionSensorStatus",
                                    "theftAlarmActive",
                                    "lastTheftWarningReason",
                                    "lastParkEvent",
                                    "collisionAlarmTimestamp",
                                    "interiorSensor",
                                    "carAlarmReason"},
                                "mdi:alarm-light",
                                None,
                                False,
                                None],

    "starterBatteryState": [    "Starter Battery State",
                                None,
                                "binarysensors",
                                "starterBatteryState",
                                "value",
                                None,
                                {},
                                "mdi:car-battery",
                                None,
                                False,
                                None],

    "ignitionstate": [          "Ignition State",
                                None,
                                "odometer",
                                "ignitionstate",
                                "value",
                                None,
                                {},
                                "mdi:key-wireless",
                                None,
                                False,
                                None],

    "oilLevel":[                "Oil Level",
                                "%",
                                "odometer",
                                "oilLevel",
                                "value",
                                None,
                                {},
                                "mdi:oil-level",
                                None,
                                False,
                                None ]
}

LOCKS = {
    "lock": [                   "Lock",
                                None,
                                "doors",
                                "doorLockStatusOverall",
                                "value",
                                None,
                                {},
                                "mdi:lock",
                                None,
                                False,
                                None]
}

SWITCHES = {
    "auxheat": [                "AuxHeat",
                                None,
                                "auxheat",
                                "auxheatActive",
                                "value",
                                None,
                                {},
                                None,
                                None,
                                False,
                                None]
}



class SensorConfigFields(Enum):
    """Representation of a Sensor."""

# "internal_name":[ 0 Display_Name
#                   1 unit_of_measurement,
#                   2 object in car.py
#                   3 attribute in car.py
#                   4 value field
#                   5 unused --> None (for capabilities check in the future)
#                   6 [list of extended attributes]
#                   7 icon
#                   8 device_class
#                   9 invert boolean value - Default: False
#                   10 entity_category - Defaul: None
# ]
    DISPLAY_NAME = 0
    UNIT_OF_MEASUREMENT = 1
    OBJECT_NAME = 2
    ATTRIBUTE_NAME = 3
    VALUE_FIELD_NAME = 4
    CAPABILITIES_LIST = 5
    EXTENDED_ATTRIBUTE_LIST = 6
    ICON = 7
    DEVICE_CLASS = 8
    FLIP_RESULT = 9
    ENTITY_CATEGORY = 10
