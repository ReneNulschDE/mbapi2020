"""Define the objects to store care data."""
import collections
from datetime import datetime

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
    "gasTankLevelPercent",
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
    "vehicleDataConnectionState",
    "ignitionstate",
    "oilLevel"]

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
    "tirewarningsprw",
    "tireMarkerFrontRight",
    "tireMarkerFrontLeft",
    "tireMarkerRearLeft",
    "tireMarkerRearRight",
    "tireWarningRollup",
    "lastTirepressureTimestamp",
    "tireTemperatureRearLeft",
    "tireTemperatureFrontRight",
    "tireTemperatureRearRight",
    "tireTemperatureFrontLeft"]

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
    'engineHoodStatus'
]

ELECTRIC_OPTIONS = [
    'rangeelectric',
    'chargingactive',
    'chargingstatus',
    'chargingPower',
    'distanceElectricalReset',
    'distanceElectricalStart',
    'ecoElectricBatteryTemperature',
    'electricconsumptionstart',
    'electricconsumptionreset',
    'endofchargetime',
    'precondActive',
    'precondNow',
    'maxrange',
    'maxSocLowerLimit',
    'maxSoc',
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
    'starterBatteryState',
    'liquidRangeCritical',
    'tankCapOpenLamp',
    'remoteStartActive',
    'engineState']

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

RemoteStart_OPTIONS = [
    'remoteEngine',
    'remoteStartEndtime',
    'remoteStartTemperature']

CarAlarm_OPTIONS = [
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
        self.messages_received = collections.Counter(f=0, p=0)
        self._last_message_received = 0
        self._last_command_type = ""
        self._last_command_state = ""
        self._last_command_error_code = ""
        self._last_command_error_message = ""
        self._last_command_time_stamp = 0

        self.binarysensors = None
        self.tires = None
        self.odometer = None
        self.doors = None
        self.location = None
        self.windows = None
        self.features = None
        self.rcp_options = None
        self.auxheat = None
        self.precond = None
        self.electric = None
        self.caralarm = None
        self.entry_setup_complete = False
        self._update_listeners = set()

    @property
    def full_updatemessages_received(self):
        return CarAttribute(
            self.messages_received["f"], "VALID", None)

    @property
    def partital_updatemessages_received(self):
        return CarAttribute(
            self.messages_received["p"], "VALID", None)

    @property
    def last_message_received(self):
        if self._last_message_received > 0:
            return CarAttribute(datetime.fromtimestamp(int(round(self._last_message_received / 1000))),
                "VALID",
                None)

        return CarAttribute(None, "NOT_RECEIVED", None)

    @property
    def last_command_type(self):
        return CarAttribute(
            self._last_command_type, "VALID", self.last_command_time_stamp)

    @property
    def last_command_state(self):
        return CarAttribute(
            self._last_command_state, "VALID", self.last_command_time_stamp)

    @property
    def last_command_error_code(self):
        return CarAttribute(
            self._last_command_error_code, "VALID", self.last_command_time_stamp)

    @property
    def last_command_error_message(self):
        return CarAttribute(
            self._last_command_error_message, "VALID", self.last_command_time_stamp)


    def add_update_listener(self, listener):
        """Add a listener for update notifications."""
        self._update_listeners.add(listener)

    def remove_update_callback(self, listener):
        """Remove a listener for update notifications."""
        self._update_listeners.discard(listener)

    def publish_updates(self):
        """Schedule call all registered callbacks."""
        for callback in self._update_listeners:
            callback()

class Tires(object):
    def __init__(self):
        self.name = "Tires"


class Odometer(object):
    def __init__(self):
        self.name = "Odometer"


class Features(object):
    def __init__(self):
        self.name = "Features"


class RcpOptions():
    def __init__(self):
        self.name = "RCP_Options"


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


class BinarySensors(object):
    def __init__(self):
        self.name = "BinarySensors"


class RemoteStart(object):
    def __init__(self):
        self.name = "RemoteStart"


class CarAlarm(object):
    def __init__(self):
        self.name = "CarAlarm"


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
    def __init__(self, value, retrievalstatus, timestamp, distance_unit=None, display_value=None, unit=None):
        self.value = value
        self.retrievalstatus = retrievalstatus
        self.timestamp = timestamp
        self.distance_unit = distance_unit
        self.display_value = display_value
        self.unit = unit
