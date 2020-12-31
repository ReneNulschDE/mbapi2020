"""Constants for the MercedesME 2020 integration."""
import logging

from homeassistant.const import (
    LENGTH_KILOMETERS)

MERCEDESME_COMPONENTS = [
    "sensor",
#    "lock",
    "binary_sensor",
    "device_tracker",
#    "switch"
]


DATA_CLIENT = "data_client"

DOMAIN = "mbapi2020"
LOGGER = logging.getLogger(__package__)

DEFAULT_CACHE_PATH = "custom_components/mbapi2020/messages"
DEFAULT_TOKEN_PATH = ".mercedesme-token-cache"


VERIFY_SSL = True

REST_API_BASE = "https://bff-prod.risingstars.daimler.com"
WEBSOCKET_API_BASE = "wss://websocket-prod.risingstars.daimler.com/ws"
DEFAULT_SOCKET_MIN_RETRY = 15


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


    "warninglowbattery": ["Low Battery Warning",
                          None,
                          "binarysensors",
                          "warninglowbattery",
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
                        }]}

DEVICE_TRACKER = {
    "tracker": ["Device Tracker", None, "location", "positionLong", "value", None,
             {
                 "positionHeading"
             }]}

SENSORS = {
    "lock": ["Lock", None, "doors", "doorLockStatusOverall", "value", None,
             {
                 "fuelLidClosed",
                 "doorStateFrontLeft",
                 "doorStateFrontRight",
                 "doorStateRearLeft",
                 "doorStateRearRight",
                 "frontLeftDoorLocked",
                 "frontRightDoorLocked",
                 "rearLeftDoorLocked",
                 "rearRightDoorLocked",
                 "frontLeftDoorClosed",
                 "frontRightDoorClosed",
                 "rearLeftDoorClosed",
                 "rearRightDoorClosed",
                 "rearRightDoorClosed",
                 "doorsClosed",
                 "trunkStateRollup",
                 "sunroofstatus",
                 "engineHoodClosed",
                 "vehicleLockState",
                 "doorLockStatusOverall",
                 "chargeCouplerDCLockStatus"}],

    "rangeElectricKm": ["Range Electric", LENGTH_KILOMETERS,
                        "electric", "rangeelectric",
                        "value", None,
                        {
                            'rangeelectric',
                            'chargingstatus',
                            'distanceElectricalReset',
                            'distanceElectricalStart',
                            'ecoElectricBatteryTemperature',
                            'electricconsumptionstart',
                            'electricconsumptionreset',
                            'endofchargetime',
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
                     "distanceReset",
                     "distanceStart",
                     "averageSpeedReset",
                     "averageSpeedStart",
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
                     "serviceintervaldays",
                     "tanklevelpercent",
                     "tankReserveLamp",
                     "batteryState",
                     "tankLevelAdBlue"}],

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
}
