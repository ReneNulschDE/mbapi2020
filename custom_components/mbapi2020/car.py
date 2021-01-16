
ODOMETER_OPTIONS = [
    "odo",
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
    "gasTankLevelPercent"
    "liquidconsumptionstart",
    "liquidconsumptionreset",
    "liquidRangeSkipIndication",
    "outsideTemperature",
    "rangeliquid",
    "serviceintervaldays",
    "tanklevelpercent",
    "tankReserveLamp",
    "batteryState",
    "tankLevelAdBlue",
    "vehicleDataConnectionState"]

LOCATION_OPTIONS = [
    "positionLat",
    "positionLong",
    "positionHeading"]

TIRE_OPTIONS = [
    "tirepressureRearLeft",
    "tirepressureRearRight",
    "tirepressureFrontRight",
    "tirepressureFrontLeft",
    "tirewarninglamp",
    "tirewarningsrdk",
    "tirewarningsprw"
    "tireMarkerFrontRight",
    "tireMarkerFrontLeft",
    "tireMarkerRearLeft",
    "tireMarkerRearRight",
    "tireWarningRollup",
    "lastTirepressureTimestamp"]

WINDOW_OPTIONS = [
    "windowstatusrearleft",
    "windowstatusrearright",
    "windowstatusfrontright",
    "windowstatusfrontleft",
    "windowStatusOverall",
    "flipWindowStatus"]

DOOR_OPTIONS = [
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
]

ELECTRIC_OPTIONS = [
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
    ]

BINARY_SENSOR_OPTIONS = [
    'warningwashwater',
    'warningenginelight',
    'warningbrakefluid',
    'warningcoolantlevellow',
    'parkbrakestatus',
    #'readingLampFrontRight',
    #'readingLampFrontLeft',
    'warningBrakeLiningWear',
    'warninglowbattery',
    'liquidRangeCritical',
    'tankCapOpenLamp']

AUX_HEAT_OPTIONS = [
    'auxheatActive',
    'auxheatwarnings',
    'auxheatruntime',
    'auxheatstatus',
    'auxheatwarningsPush',
    'auxheattimeselection',
    'auxheattime1',
    'auxheattime2',
    'auxheattime3']

PRE_COND_OPTIONS = [
    'preconditionState',
    'precondimmediate']

REMOTE_START_OPTIONS = [
    'remoteEngine',
    'remoteStartEndtime',
    'remoteStartTemperature']

CAR_ALARM_OPTIONS = [
    'lastTheftWarning',
    'towSensor',
    'theftSystemArmed',
    'carAlarm',
    'parkEventType',
    'parkEventLevel',
    'carAlarmLastTime',
    'towProtectionSensorStatus',
    'theftAlarmActive',
    'lastTheftWarningReason',
    'lastParkEvent',
    'collisionAlarmTimestamp',
    'interiorSensor',
    'carAlarmReason']


class Car(object):
    def __init__(self):
        self.licenseplate = None
        self.finorvin = None
        self.salesdesignation = None
        self.nickname = None
        self.modelyear = None
        self.colorname = None
        self.fueltype = None
        self.powerhp = None
        self.powerkw = None
        self.numberofdoors = None
        self.numberofseats = None
        self.vehicle_title = None

        self.vehicleHealthStatus = None
        self.binarysensors = None
        self.tires = None
        self.odometer = None
        self.doors = None
        self.stateofcharge = None
        self.location = None
        self.windows = None
        self.features = None
        self.auxheat = None
        self.precond = None
        self.electric = None
        self.car_alarm = None
        self._entry_setup_complete = False
        self._update_listeners =[] 

    def add_update_listener(self, listener):
        """Add a listener for update notifications."""
        self._update_listeners.append(listener)


class Tires(object):
    def __init__(self):
        self.name = "Tires"


class Odometer(object):
    def __init__(self):
        self.name = "Odometer"


class Features(object):
    def __init__(self):
        self.name = "Features"


class Windows(object):
    def __init__(self):
        self.name = "Windows"


class Doors(object):
    def __init__(self):
        self.name = "Doors"


class Electric(object):
    def __init__(self):
        self.name = "Electric"


class Auxheat(object):
    def __init__(self):
        self.name = "Auxheat"


class Precond(object):
    def __init__(self):
        self.name = "Precond"


class Binary_Sensors(object):
    def __init__(self):
        self.name = "Binary_Sensors"


class Remote_Start(object):
    def __init__(self):
        self.name = "Remote_Start"


class Car_Alarm(object):
    def __init__(self):
        self.name = "Car_Alarm"


class Location(object):
    def __init__(self, latitude=None, longitude=None, heading=None):
        self.name = "Location"
        self.latitude = None
        self.longitude = None
        self.heading = None
        if latitude is not None:
            self.latitude = latitude
        if longitude is not None:
            self.longitude = longitude
        if heading is not None:
            self.heading = heading


class CarAttribute(object):
    def __init__(self, value, retrievalstatus, timestamp, distance_unit=None, display_value=None):
        self.value = value
        self.retrievalstatus = retrievalstatus
        self.timestamp = timestamp
        self.distance_unit = distance_unit
        self.display_value = display_value