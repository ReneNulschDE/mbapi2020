"""Constants for the MercedesME 2020 integration."""
import logging

import voluptuous as vol

from homeassistant.const import (
    LENGTH_KILOMETERS)

from homeassistant.helpers import (
    config_validation as cv,
)


MERCEDESME_COMPONENTS = [
    "sensor",
#    "lock",
    "binary_sensor",
    "device_tracker",
#    "switch"
]

CONF_ALLOWED_REGIONS = ["Europe", "North America"]
CONF_LOCALE = "locale"
CONF_COUNTRY_CODE = "country_code"
CONF_EXCLUDED_CARS = "excluded_cars"
CONF_PIN = "pin"
CONF_REGION = "region"
CONF_VIN = "vin"
CONF_TIME = "time"

DATA_CLIENT = "data_client"

DOMAIN = "mbapi2020"
LOGGER = logging.getLogger(__package__)

DEFAULT_CACHE_PATH = "custom_components/mbapi2020/messages"
DEFAULT_TOKEN_PATH = ".mercedesme-token-cache"
DEFAULT_LOCALE = "en-GB"
DEFAULT_COUNTRY_CODE = "EN"

RIS_APPLICATION_VERSION_NA = "3.0.1"
RIS_APPLICATION_VERSION = "1.6.3"
RIS_SDK_VERSION = "2.30.0"

VERIFY_SSL = True

LOGIN_BASE_URI = "https://keycloak.risingstars.daimler.com"
LOGIN_BASE_URI_NA = "https://keycloak.risingstars-amap.daimler.com"
REST_API_BASE = "https://bff-prod.risingstars.daimler.com"
REST_API_BASE_NA = "https://bff-prod.risingstars-amap.daimler.com"
WEBSOCKET_API_BASE = "wss://websocket-prod.risingstars.daimler.com/ws"
WEBSOCKET_API_BASE_NA = "wss://websocket-prod.risingstars-amap.daimler.com/ws"
WEBSOCKET_USER_AGENT = "okhttp/3.12.2"
DEFAULT_SOCKET_MIN_RETRY = 15


SERVICE_REFRESH_TOKEN_URL = "refresh_access_token"
SERVICE_DOORS_LOCK_URL = "doors_lock"
SERVICE_DOORS_UNLOCK_URL = "doors_unlock"
SERVICE_ENGINE_START = "engine_start"
SERVICE_ENGINE_STOP = "engine_stop"
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


ATTR_MB_MANUFACTURER = "Mercedes Benz"

BINARY_SENSORS = {

    "liquidRangeCritical": ["Liquid Range Critical",
                            None,
                            "binarysensors",
                            "liquidRangeCritical",
                            "value",
                            None,
                            None],

    "warningbrakefluid": ["Low Brake Fluid Warning",
                          None,
                          "binarysensors",
                          "warningbrakefluid",
                          "value",
                          None,
                          None],

    "warningwashwater": ["Low Wash Water Warning",
                         None,
                         "binarysensors",
                         "warningwashwater",
                         "value",
                         None,
                         None],

    "warningcoolantlevellow": ["Low Coolant Level Warning",
                               None,
                               "binarysensors",
                               "warningcoolantlevellow",
                               "value",
                               None,
                               None],

    "warningenginelight": ["Engine Light Warning",
                           None,
                           "binarysensors",
                           "warningenginelight",
                           "value",
                           None,
                           {
                               "warningbrakefluid",
                               "warningwashwater",
                               "warningcoolantlevellow",
                               "warninglowbattery"}],

    "parkbrakestatus": ["Park Brake Status",
                        None,
                        "binarysensors",
                        "parkbrakestatus",
                        "value",
                        None,
                        {
                            "preWarningBrakeLiningWear"}],

    "windowStatusOverall": ["Windows Closed",
                      None, "windows",
                      "windowStatusOverall",
                      "value",
                      None,
                      {
                          "windowstatusrearleft",
                          "windowstatusrearright",
                          "windowstatusfrontright",
                          "windowstatusfrontleft"}],

    "tirewarninglamp": ["Tire Warning",
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
                            "tireMarkerRearRight"
                            "tirewarningsrdk",
                            "tirewarningsprw",
                        }],
    
    "remoteStartActive": ["Remote Start Active",
                               None,
                               "binarysensors",
                               "remoteStartActive",
                               "value",
                               None,
                               None],
    
    "engineState": ["Engine State",
                               None,
                               "binarysensors",
                               "engineState",
                               "value",
                               None,
                               None]
}

DEVICE_TRACKER = {
    "tracker": ["Device Tracker", None, "location", "positionLong", "value", None,
             {
                 "positionHeading"
             }]}

SENSORS = {
#    "car":  ["Car", None, None, None, "last_message_received", None,
#             {
#                 'messages_received'
#             } 
#    ], 
    "lock": ["Lock", None, "doors", "doorlockstatusvehicle", "value", None,
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
             }],

    "rangeElectricKm": ["Range Electric", LENGTH_KILOMETERS,
                        "electric", "rangeelectric",
                        "value", None,
                        {
                            'rangeelectric',
                            'chargingactive',
                            'chargingstatus',
                            'distanceElectricalReset',
                            'distanceElectricalStart',
                            'ecoElectricBatteryTemperature',
                            'electricconsumptionstart',
                            'electricconsumptionreset',
                            'endofchargetime',
                            'precondActive',
                            'maxrange',
                            'selectedChargeProgram',
                            'soc'
                        }],

    "auxheatstatus": ["Auxheat Status", None, "auxheat", "auxheatstatus",
                      "value", "aux_heat",
                      {
                          "auxheatActive",
                          "auxheatwarnings",
                          "auxheatruntime",
                          "auxheatwarningsPush",
                          "auxheattimeselection",
                          "auxheattime1",
                          "auxheattime2",
                          "auxheattime3"}],

    "tanklevelpercent": ["Fuel Level", "%", "odometer", "tanklevelpercent",
                         "value", None,
                         {
                             "tankLevelAdBlue",
                             "gasTankLevelPercent"
                         }],

    "odometer": ["Odometer", LENGTH_KILOMETERS, "odometer", "odo",
                 "value", None,
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
                     "vehicleDataConnectionState"}],

    "car_alarm": ["Car Alarm", None, "car_alarm", "carAlarm",
                  "value", 'car_alarm',
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
                      "carAlarmReason"}],

    "starterBatteryState": ["Starter Battery State",
                            None,
                            "binarysensors",
                            "starterBatteryState",
                            "value",
                            None,
                            {}]
}
