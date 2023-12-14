"""Constants for the MercedesME 2020 integration."""
import logging
from enum import Enum

import voluptuous as vol
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    Platform,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfMass,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfVolume,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity import EntityCategory

MERCEDESME_COMPONENTS = [
    Platform.SENSOR,
    Platform.LOCK,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.DEVICE_TRACKER,
    Platform.SWITCH,
]

REGION_EUROPE = "Europe"
REGION_NORAM = "North America"
REGION_APAC = "Asia-Pacific"
REGION_CHINA = "China"

CONF_ALLOWED_REGIONS = [REGION_EUROPE, REGION_NORAM, REGION_APAC, REGION_CHINA]
CONF_LOCALE = "locale"
CONF_COUNTRY_CODE = "country_code"
CONF_EXCLUDED_CARS = "excluded_cars"
CONF_PIN = "pin"
CONF_REGION = "region"
CONF_VIN = "vin"
CONF_TIME = "time"
CONF_DEBUG_FILE_SAVE = "save_files"
CONF_FT_DISABLE_CAPABILITY_CHECK = "cap_check_disabled"
CONF_DELETE_AUTH_FILE = "delete_auth_file"
CONF_ENABLE_CHINA_GCJ_02 = "enable_china_gcj_02"

DATA_CLIENT = "data_client"

DOMAIN = "mbapi2020"
LOGGER = logging.getLogger(__package__)

DEFAULT_CACHE_PATH = "custom_components/mbapi2020/messages"
DEFAULT_TOKEN_PATH = ".mercedesme-token-cache"
DEFAULT_LOCALE = "en-GB"
DEFAULT_COUNTRY_CODE = "EN"

RIS_APPLICATION_VERSION_NA = "3.39.0"
RIS_APPLICATION_VERSION_CN = "1.39.0"
RIS_APPLICATION_VERSION_PA = "1.39.1"
RIS_APPLICATION_VERSION = "1.39.0 (2066)"
RIS_SDK_VERSION = "2.109.0"
RIS_SDK_VERSION_CN = "2.109.0"
RIS_OS_VERSION = "16.5"
RIS_OS_NAME = "ios"
X_APPLICATIONNAME = "mycar-store-ece"
X_APPLICATIONNAME_ECE = "mycar-store-ece"
X_APPLICATIONNAME_CN = "mycar-store-cn"
X_APPLICATIONNAME_US = "mycar-store-us"
X_APPLICATIONNAME_AP = "mycar-store-ap"

VERIFY_SSL = True
DISABLE_SSL_CERT_CHECK = VERIFY_SSL
SYSTEM_PROXY = None
PROXIES = {}
# SYSTEM_PROXY = "http://192.168.178.61:8080"
# PROXIES = {
#    "https": SYSTEM_PROXY,
# }


LOGIN_APP_ID = "01398c1c-dc45-4b42-882b-9f5ba9f175f1"
LOGIN_APP_ID_EU = "01398c1c-dc45-4b42-882b-9f5ba9f175f1"
LOGIN_APP_ID_CN = "3f36efb1-f84b-4402-b5a2-68a118fec33e"
LOGIN_BASE_URI = "https://id.mercedes-benz.com"
LOGIN_BASE_URI_CN = "https://ciam-1.mercedes-benz.com.cn"
LOGIN_BASE_URI_NA = "https://id.mercedes-benz.com"
LOGIN_BASE_URI_PA = "https://id.mercedes-benz.com"
PSAG_BASE_URI = "https://psag.query.api.dvb.corpinter.net"
PSAG_BASE_URI_CN = "https://psag.query.api.dvb.corpinter.net.cn"
RCP_BASE_URI = "https://rcp-rs.query.api.dvb.corpinter.net"
RCP_BASE_URI_CN = "https://rcp-rs.query.api.dvb.corpinter.net.cn"
REST_API_BASE = "https://bff.emea-prod.mobilesdk.mercedes-benz.com"
REST_API_BASE_CN = "https://bff.cn-prod.mobilesdk.mercedes-benz.com"
REST_API_BASE_NA = "https://bff.amap-prod.mobilesdk.mercedes-benz.com"
REST_API_BASE_PA = "https://bff.amap-prod.mobilesdk.mercedes-benz.com"
WEBSOCKET_API_BASE = "wss://websocket.emea-prod.mobilesdk.mercedes-benz.com/ws"
WEBSOCKET_API_BASE_NA = "wss://websocket.amap-prod.mobilesdk.mercedes-benz.com/ws"
WEBSOCKET_API_BASE_PA = "wss://websocket.amap-prod.mobilesdk.mercedes-benz.com/ws"
WEBSOCKET_API_BASE_CN = "wss://websocket.cn-prod.mobilesdk.mercedes-benz.com/ws"
WEBSOCKET_USER_AGENT = "MyCar/1.39.0 (com.daimler.ris.mercedesme.ece.ios; build:2066; iOS 17.2.0) Alamofire/5.4.0"
WEBSOCKET_USER_AGENT_CN = "MyStarCN/1.39.0 (com.daimler.ris.mercedesme.cn.ios; build:1758; iOS 16.3.1) Alamofire/5.4.0"
WEBSOCKET_USER_AGENT_PA = "mycar-store-ap v1.39.0, android 8.0.0, SDK 2.84.3"
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
SERVICE_PREHEAT_STOP_DEPARTURE_TIME = "preheat_stop_departure_time"
SERVICE_PREHEAT_STOP = "preheat_stop"
SERVICE_WINDOWS_OPEN = "windows_open"
SERVICE_WINDOWS_CLOSE = "windows_close"
SERVICE_VIN_SCHEMA = vol.Schema({vol.Required(CONF_VIN): cv.string})
SERVICE_VIN_TIME_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_VIN): cv.string,
        vol.Required(CONF_TIME): vol.All(vol.Coerce(int), vol.Range(min=0, max=1439)),
    }
)
SERVICE_AUXHEAT_CONFIGURE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_VIN): cv.string,
        vol.Required("time_selection"): vol.All(vol.Coerce(int), vol.Range(min=0, max=3)),
        vol.Required("time_1"): vol.All(vol.Coerce(int), vol.Range(min=0, max=1439)),
        vol.Required("time_2"): vol.All(vol.Coerce(int), vol.Range(min=0, max=1439)),
        vol.Required("time_3"): vol.All(vol.Coerce(int), vol.Range(min=0, max=1439)),
    }
)
SERVICE_PREHEAT_START_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_VIN): cv.string,
        vol.Required("type", default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=1)),
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
        vol.Required("max_soc", default=100): vol.All(vol.Coerce(int), vol.In([50, 60, 70, 80, 90, 100])),
    }
)
SERVICE_VIN_PIN_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_VIN): cv.string,
        vol.Optional(CONF_PIN): cv.string,
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
#                   11 Default Value Mode (for now: None, 0)
# ]

BinarySensors = {
    "liquidRangeCritical": [
        "Liquid Range Critical",
        None,  # Deprecated: DO NOT USE
        "binarysensors",
        "liquidRangeCritical",
        "value",
        None,
        None,
        "mdi:gas-station",
        "problem",
        False,
        None,
        None,
        None,
    ],
    "warningbrakefluid": [
        "Low Brake Fluid Warning",
        None,  # Deprecated: DO NOT USE
        "binarysensors",
        "warningbrakefluid",
        "value",
        None,
        None,
        "mdi:car-brake-alert",
        "problem",
        False,
        None,
        None,
        None,
    ],
    "warningwashwater": [
        "Low Wash Water Warning",
        None,  # Deprecated: DO NOT USE
        "binarysensors",
        "warningwashwater",
        "value",
        None,
        None,
        "mdi:wiper-wash",
        "problem",
        False,
        None,
        None,
        None,
    ],
    "warningcoolantlevellow": [
        "Low Coolant Level Warning",
        None,  # Deprecated: DO NOT USE
        "binarysensors",
        "warningcoolantlevellow",
        "value",
        None,
        None,
        "mdi:oil-level",
        "problem",
        False,
        None,
        None,
        None,
    ],
    "warningenginelight": [
        "Engine Light Warning",
        None,  # Deprecated: DO NOT USE
        "binarysensors",
        "warningenginelight",
        "value",
        None,
        {
            "warningbrakefluid",
            "warningwashwater",
            "warningcoolantlevellow",
            "warninglowbattery",
        },
        "mdi:engine",
        "problem",
        False,
        None,
        None,
        None,
    ],
    "parkbrakestatus": [
        "Park Brake Status",
        None,  # Deprecated: DO NOT USE
        "binarysensors",
        "parkbrakestatus",
        "value",
        None,
        {"preWarningBrakeLiningWear"},
        "mdi:car-brake-parking",
        None,
        True,
        None,
        None,
        None,
    ],
    "windowStatusOverall": [
        "Windows Closed",
        None,  # Deprecated: DO NOT USE
        "windows",
        "windowStatusOverall",
        "value",
        None,
        {
            "windowstatusrearleft",
            "windowstatusrearright",
            "windowstatusfrontright",
            "windowstatusfrontleft",
            "windowstatusrearleftblind",
            "windowstatusrearrightblind",
            "windowstatusfrontrightblind",
            "windowstatusfrontleftblind",
        },
        "mdi:car-door",
        None,
        False,
        None,
        None,
        None,
    ],
    "tirewarninglamp": [
        "Tire Warning",
        None,  # Deprecated: DO NOT USE
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
            "tireTemperatureFrontLeft",
        },
        "mdi:car-tire-alert",
        "problem",
        False,
        None,
        None,
        None,
    ],
    "remoteStartActive": [
        "Remote Start Active",
        None,  # Deprecated: DO NOT USE
        "binarysensors",
        "remoteStartActive",
        "value",
        None,
        {"remoteStartTemperature"},
        "mdi:engine-outline",
        None,
        False,
        None,
        None,
        None,
    ],
    "engineState": [
        "Engine State",
        None,  # Deprecated: DO NOT USE
        "binarysensors",
        "engineState",
        "value",
        None,
        None,
        "mdi:engine",
        None,
        False,
        None,
        None,
        None,
    ],
}

BUTTONS = {
    "btn_preheat_start_now": [
        "Preclimate start",
        None,  # Deprecated: DO NOT USE
        None,
        "preheat_start",
        None,
        "ZEV_PRECONDITIONING_START",
        None,
        "mdi:hvac",
        None,
        False,
        None,
        None,
        None,
    ],
    "btn_preheat_stop_now": [
        "Preclimate stop",
        None,  # Deprecated: DO NOT USE
        None,
        "preheat_stop",
        None,
        "ZEV_PRECONDITIONING_STOP",
        None,
        "mdi:hvac",
        None,
        False,
        None,
        None,
        None,
    ],
}


DEVICE_TRACKER = {
    "tracker": [
        "Device Tracker",
        None,  # Deprecated: DO NOT USE
        "location",
        "positionLong",
        "value",
        None,
        {"positionHeading"},
        None,
        None,
        False,
        None,
        None,
        None,
    ]
}

SENSORS = {
    "chargingpowerkw": [
        "Charging Power",
        "kW",  # Deprecated: DO NOT USE
        "electric",
        "chargingPower",
        "value",
        None,
        {},
        None,  # "mdi:ev-station",
        SensorDeviceClass.POWER,
        False,
        None,
        SensorStateClass.MEASUREMENT,
        None,
    ],
    "rcp_features": [
        "RCP Features",
        None,  # Deprecated: DO NOT USE
        "rcp_options",
        "rcp_supported",
        "value",
        None,
        {"rcp_supported_settings"},
        "mdi:car",
        None,
        False,
        EntityCategory.DIAGNOSTIC,
        None,
        None,
    ],
    "car": [
        "Car",
        None,  # Deprecated: DO NOT USE
        None,
        "full_updatemessages_received",
        "value",
        None,
        {
            "partital_updatemessages_received",
            "last_message_received",
            "last_command_type",
            "last_command_state",
            "last_command_error_code",
            "last_command_error_message",
            "is_owner",
        },
        "mdi:car",
        None,
        False,
        EntityCategory.DIAGNOSTIC,
        None,
        None,
    ],
    "departuretime": [
        "Departure time",
        None,  # Deprecated: DO NOT USE
        "odometer",
        "departuretime",
        "display_value",
        None,
        {"departureTimeWeekday"},
        "mdi:clock-out",
        None,
        False,
        None,
        None,
        None,
    ],
    "lock": [
        "Lock",
        None,  # Deprecated: DO NOT USE
        "doors",
        "doorlockstatusvehicle",
        "value",
        None,
        {
            "decklidstatus",
            "doorStatusOverall",
            "doorLockStatusOverall",
            "doorlockstatusgas",
            "doorlockstatusvehicle",
            "doorlockstatusfrontleft",
            "doorlockstatusfrontright",
            "doorlockstatusrearright",
            "doorlockstatusrearleft",
            "doorlockstatusdecklid",
            "doorstatusrearleft",
            "doorstatusfrontright",
            "doorstatusrearright",
            "doorstatusfrontleft",
            "rooftopstatus",
            "sunroofstatus",
            "engineHoodStatus",
            "tankCapOpenLamp",
        },
        "mdi:car-key",
        None,
        False,
        None,
        None,
        None,
    ],
    "rangeElectricKm": [
        "Range Electric",
        None,  # Deprecated: DO NOT USE
        "electric",
        "rangeelectric",
        "display_value",
        None,
        {
            "chargingactive",
            "chargingstatus",
            "distanceElectricalReset",
            "distanceElectricalStart",
            "ecoElectricBatteryTemperature",
            "electricconsumptionstart",
            "electricconsumptionreset",
            "endofchargetime",
            "endofChargeTimeWeekday",
            "precondActive",
            "precondNow",
            "precondDuration",
            "maxrange",
            "selectedChargeProgram",
            "soc",
            "chargingPower",
        },
        "mdi:ev-station",
        SensorDeviceClass.DISTANCE,
        False,
        None,
        SensorStateClass.MEASUREMENT,
        None,
    ],
    "electricconsumptionstart": [
        "Electric consumption start",
        None,  # Deprecated: DO NOT USE,
        "electric",
        "electricconsumptionstart",
        "display_value",
        None,
        {},
        "mdi:ev-station",
        None,
        False,
        None,
        SensorStateClass.MEASUREMENT,
        None,
    ],
    "electricconsumptionreset": [
        "Electric consumption reset",
        None,  # Deprecated: DO NOT USE
        "electric",
        "electricconsumptionreset",
        "display_value",
        None,
        {},
        "mdi:ev-station",
        None,
        False,
        None,
        SensorStateClass.MEASUREMENT,
        None,
    ],
    "soc": [
        "State of Charge",
        None,  # Deprecated: DO NOT USE
        "electric",
        "soc",
        "value",
        None,
        {"maxSocLowerLimit", "maxSoc", "max_soc", "selectedChargeProgram"},
        None,
        SensorDeviceClass.BATTERY,
        False,
        None,
        SensorStateClass.MEASUREMENT,
        None,
    ],
    "max_soc": [
        "Max State of Charge",
        None,  # Deprecated: DO NOT USE
        "electric",
        "max_soc",
        "value",
        None,
        {"selectedChargeProgram"},
        None,
        None,
        False,
        None,
        SensorStateClass.MEASUREMENT,
        None,
    ],
    "auxheatstatus": [
        "Auxheat Status",
        None,  # Deprecated: DO NOT USE
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
            "auxheattime3",
        },
        "mdi:radiator",
        None,
        False,
        None,
        None,
        None,
    ],
    "tanklevelpercent": [
        "Fuel Level",
        None,  # Deprecated: DO NOT USE
        "odometer",
        "tanklevelpercent",
        "value",
        None,
        {"tankLevelAdBlue", "gasTankLevelPercent"},
        "mdi:gas-station",
        SensorDeviceClass.POWER_FACTOR,
        False,
        None,
        SensorStateClass.MEASUREMENT,
        None,
    ],
    "odometer": [
        "Odometer",
        None,  # Deprecated: DO NOT USE,
        "odometer",
        "odo",
        "display_value",
        None,
        {
            "gasconsumptionstart",
            "gasconsumptionreset",
            "gasTankRange",
            "gasTankLevel",
            "liquidRangeSkipIndication",
            "outsideTemperature",
            "serviceintervaldays",
            "serviceintervaldistance",
            "tankReserveLamp",
            "tankLevelAdBlue",
            "vehicleDataConnectionState",
            "remoteStartTemperature",
        },
        "mdi:car-cruise-control",
        SensorDeviceClass.DISTANCE,
        False,
        None,
        SensorStateClass.MEASUREMENT,
        None,
    ],
    "averageSpeedStart": [
        "Average speed start",
        None,  # Deprecated: DO NOT USE
        "odometer",
        "averageSpeedStart",
        "display_value",
        None,
        {},
        None,  # "mdi:car-cruise-control",
        SensorDeviceClass.SPEED,
        False,
        None,
        SensorStateClass.MEASUREMENT,
        None,
    ],
    "averageSpeedReset": [
        "Average speed reset",
        None,  # Deprecated: DO NOT USE,
        "odometer",
        "averageSpeedReset",
        "display_value",
        None,
        {},
        None,  # "mdi:car-cruise-control",
        SensorDeviceClass.SPEED,
        False,
        None,
        SensorStateClass.MEASUREMENT,
        None,
    ],
    "distanceReset": [
        "Distance reset",
        None,  # Deprecated: DO NOT USE,
        "odometer",
        "distanceReset",
        "display_value",
        None,
        {"drivenTimeReset"},
        "mdi:map-marker-distance",
        None,
        False,
        None,
        SensorStateClass.MEASUREMENT,
        None,
    ],
    "distanceStart": [
        "Distance start",
        None,  # Deprecated: DO NOT USE,
        "odometer",
        "distanceStart",
        "display_value",
        None,
        {"drivenTimeStart"},
        "mdi:map-marker-distance",
        None,
        False,
        None,
        SensorStateClass.MEASUREMENT,
        None,
    ],
    "distanceZEReset": [
        "Distance zero-emission reset",
        None,  # Deprecated: DO NOT USE,
        "odometer",
        "distanceZEReset",
        "display_value",
        None,
        {"drivenTimeZEReset"},
        "mdi:map-marker-distance",
        None,
        False,
        None,
        SensorStateClass.MEASUREMENT,
        None,
    ],
    "ecoscoretotal": [
        "Eco score total",
        None,  # Deprecated: DO NOT USE
        "odometer",
        "ecoscoretotal",
        "display_value",
        None,
        {},
        "mdi:leaf",
        None,
        False,
        None,
        SensorStateClass.MEASUREMENT,
        None,
    ],
    "ecoscorefreewhl": [
        "Eco score free wheel",
        None,  # Deprecated: DO NOT USE
        "odometer",
        "ecoscorefreewhl",
        "display_value",
        None,
        {},
        "mdi:leaf",
        None,
        False,
        None,
        SensorStateClass.MEASUREMENT,
        None,
    ],
    "ecoscorebonusrange": [
        "Eco score bonus range",
        None,  # Deprecated: DO NOT USE,
        "odometer",
        "ecoscorebonusrange",
        "display_value",
        None,
        {},
        "mdi:leaf",
        None,
        False,
        None,
        SensorStateClass.MEASUREMENT,
        None,
    ],
    "ecoscoreconst": [
        "Eco score constant",
        None,  # Deprecated: DO NOT USE
        "odometer",
        "ecoscoreconst",
        "display_value",
        None,
        {},
        "mdi:leaf",
        None,
        False,
        None,
        SensorStateClass.MEASUREMENT,
        None,
    ],
    "ecoscoreaccel": [
        "Eco score acceleration",
        None,  # Deprecated: DO NOT USE
        "odometer",
        "ecoscoreaccel",
        "display_value",
        None,
        {},
        "mdi:leaf",
        None,
        False,
        None,
        SensorStateClass.MEASUREMENT,
        None,
    ],
    "liquidconsumptionstart": [
        "Liquid consumption start",
        None,  # Deprecated: DO NOT USE
        "odometer",
        "liquidconsumptionstart",
        "display_value",
        None,
        {},
        "mdi:fuel",
        None,
        False,
        None,
        SensorStateClass.MEASUREMENT,
        None,
    ],
    "liquidconsumptionreset": [
        "Liquid consumption reset",
        None,  # Deprecated: DO NOT USE
        "odometer",
        "liquidconsumptionreset",
        "display_value",
        None,
        {},
        "mdi:fuel",
        None,
        False,
        None,
        SensorStateClass.MEASUREMENT,
        None,
    ],
    "rangeliquid": [
        "Range liquid",
        None,  # Deprecated: DO NOT USE,
        "odometer",
        "rangeliquid",
        "display_value",
        None,
        {},
        "mdi:gas-station",
        SensorDeviceClass.DISTANCE,
        False,
        None,
        SensorStateClass.MEASUREMENT,
        None,
    ],
    "CarAlarm": [
        "Car Alarm",
        None,  # Deprecated: DO NOT USE
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
            "carAlarmReason",
        },
        "mdi:alarm-light",
        None,
        False,
        None,
        None,
        None,
    ],
    "starterBatteryState": [
        "Starter Battery State",
        None,  # Deprecated: DO NOT USE
        "binarysensors",
        "starterBatteryState",
        "value",
        None,
        {},
        "mdi:car-battery",
        None,
        False,
        None,
        None,
        None,
    ],
    "ignitionstate": [
        "Ignition State",
        None,  # Deprecated: DO NOT USE
        "odometer",
        "ignitionstate",
        "value",
        None,
        {},
        "mdi:key-wireless",
        None,
        False,
        None,
        None,
        None,
    ],
    # "oilLevel": [
    #     "Oil Level",
    #     None,  # Deprecated: DO NOT USE
    #     "odometer",
    #     "oilLevel",
    #     "value",
    #     None,
    #     {},
    #     "mdi:oil-level",
    #     SensorDeviceClass.POWER_FACTOR,
    #     False,
    #     None,
    #     SensorStateClass.MEASUREMENT,
    # ],
    "tirepressureRearLeft": [
        "Tire pressure rear left",
        None,  # Deprecated: DO NOT USE
        "tires",
        "tirepressureRearLeft",
        "display_value",
        None,
        {},
        None,
        SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        False,
        None,
        SensorStateClass.MEASUREMENT,
        None,
    ],
    "tirepressureRearRight": [
        "Tire pressure rear right",
        None,  # Deprecated: DO NOT USE
        "tires",
        "tirepressureRearRight",
        "display_value",
        None,
        {},
        None,
        SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        False,
        None,
        SensorStateClass.MEASUREMENT,
        None,
    ],
    "tirepressureFrontRight": [
        "Tire pressure front right",
        None,  # Deprecated: DO NOT USE
        "tires",
        "tirepressureFrontRight",
        "display_value",
        None,
        {},
        None,
        SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        False,
        None,
        SensorStateClass.MEASUREMENT,
        None,
    ],
    "tirepressureFrontLeft": [
        "Tire pressure front left",
        None,  # Deprecated: DO NOT USE
        "tires",
        "tirepressureFrontLeft",
        "display_value",
        None,
        {},
        None,
        SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        False,
        None,
        SensorStateClass.MEASUREMENT,
        None,
    ],
}

LOCKS = {
    "lock": [
        "Lock",
        None,  # Deprecated: DO NOT USE
        "doors",
        "doorLockStatusOverall",
        "value",
        None,
        {},
        None,
        None,
        False,
        None,
        None,
        None,
    ],
}

SWITCHES = {
    "auxheat": [
        "AuxHeat",
        None,  # Deprecated: DO NOT USE
        "auxheat",
        "auxheatActive",
        "value",
        "AUXHEAT_START",
        {},
        None,
        None,
        False,
        None,
        None,
        None,
    ],
}

SENSORS_POLL = {
    "geofencing_violation": [
        "Geofencing Violation",
        None,  # Deprecated: DO NOT USE
        "geofence_events",
        "last_event_type",
        "value",
        None,
        {"last_event_zone"},
        "mdi:map-marker-radius",
        None,
        False,
        None,
        None,
        None,
    ],
}

UNITS = {
    "BAR": UnitOfPressure.BAR,
    "CELSIUS": UnitOfTemperature.CELSIUS,
    "FAHRENHEIT": UnitOfTemperature.FAHRENHEIT,
    "KG_PER_100KM": UnitOfMass.KILOGRAMS + "/100" + UnitOfLength.KILOMETERS,
    "KILOMETERS": UnitOfLength.KILOMETERS,
    "KM_PER_HOUR": UnitOfSpeed.KILOMETERS_PER_HOUR,
    "KM_PER_KWH": UnitOfLength.KILOMETERS + "/" + UnitOfEnergy.KILO_WATT_HOUR,
    "KM_PER_LITER": UnitOfLength.KILOMETERS + "/" + UnitOfVolume.LITERS,
    "KPA": UnitOfPressure.KPA,
    "KWH_PER_100KM": UnitOfEnergy.KILO_WATT_HOUR + "/100" + UnitOfLength.KILOMETERS,
    "KWH_PER_100MI": UnitOfEnergy.KILO_WATT_HOUR + "/100" + UnitOfLength.MILES,
    "LITER_PER_100KM": UnitOfVolume.LITERS + "/100" + UnitOfLength.KILOMETERS,
    "M_PER_HOUR": UnitOfSpeed.MILES_PER_HOUR,
    "M_PER_KWH": "mpkWh",
    "MILES": UnitOfLength.MILES,
    "MPG_UK": "mpg",
    "MPG_US": "mpg",
    "MPGE": "mpge",
    "PERCENT": PERCENTAGE,
    "PSI": UnitOfPressure.PSI,
    "T24H": "",
    "T12H": "",
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
    #                   10 entity_category - Default: None
    #                   11 state_class - Default: None
    #                   12 default_value_mode - Default: None
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
    STATE_CLASS = 11
    DEFAULT_VALUE_MODE = 12
