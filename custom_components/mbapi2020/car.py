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
    "remoteStartTemperature",
    "serviceintervaldays",
    "serviceintervaldistance",
    "tanklevelpercent",
    "tankReserveLamp",
    "batteryState",
    "tankLevelAdBlue",
    "vehicleDataConnectionState",
    "ignitionstate",
    "oilLevel",
    "departuretime",
    "departureTimeWeekday",
    "precondatdeparture",
]

LOCATION_OPTIONS = ["positionLat", "positionLong", "positionHeading"]

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
    "tireTemperatureFrontLeft",
]

WINDOW_OPTIONS = [
    "windowstatusrearleft",
    "windowstatusrearright",
    "windowstatusfrontright",
    "windowstatusfrontleft",
    "windowStatusOverall",
    "flipWindowStatus",
]

DOOR_OPTIONS = [
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
]

ELECTRIC_OPTIONS = [
    "rangeelectric",
    "chargingactive",
    "chargingstatus",
    "chargingPower",
    "distanceElectricalReset",
    "distanceElectricalStart",
    "ecoElectricBatteryTemperature",
    "electricconsumptionstart",
    "electricconsumptionreset",
    "endofchargetime",
    "endOfChargeTimeWeekday",
    "precondActive",
    "precondNow",
    "selectedChargeProgram",
    "maxrange",
    "maxSocLowerLimit",
    "maxSoc",
    "max_soc",
    "soc",
]

BINARY_SENSOR_OPTIONS = [
    "warningwashwater",
    "warningenginelight",
    "warningbrakefluid",
    "warningcoolantlevellow",
    "parkbrakestatus",
    #'readingLampFrontRight',
    #'readingLampFrontLeft',
    "warningBrakeLiningWear",
    "warninglowbattery",
    "starterBatteryState",
    "liquidRangeCritical",
    "tankCapOpenLamp",
    "remoteStartActive",
    "engineState",
]

AUX_HEAT_OPTIONS = [
    "auxheatActive",
    "auxheatwarnings",
    "auxheatruntime",
    "auxheatstatus",
    "auxheatwarningsPush",
    "auxheattimeselection",
    "auxheattime1",
    "auxheattime2",
    "auxheattime3",
]

PRE_COND_OPTIONS = ["preconditionState", "precondimmediate"]

RemoteStart_OPTIONS = ["remoteEngine", "remoteStartEndtime", "remoteStartTemperature"]

CarAlarm_OPTIONS = [
    "lastTheftWarning",
    "towSensor",
    "theftSystemArmed",
    "carAlarm",
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
]

GeofenceEvents_OPTIONS = ["last_event_zone", "last_event_timestamp", "last_event_type"]


class Car(object):
    """Car class, stores the car values at runtime"""

    def __init__(self):
        self.licenseplate = None
        self.finorvin = None
        self._is_owner = False
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
        self.geofence_events = None
        self.entry_setup_complete = False
        self._update_listeners = set()

    @property
    def is_owner(self):
        return CarAttribute(self._is_owner, "VALID", None)

    @property
    def full_updatemessages_received(self):
        return CarAttribute(self.messages_received["f"], "VALID", None)

    @property
    def partital_updatemessages_received(self):
        return CarAttribute(self.messages_received["p"], "VALID", None)

    @property
    def last_message_received(self):
        if self._last_message_received > 0:
            return CarAttribute(datetime.fromtimestamp(int(round(self._last_message_received / 1000))), "VALID", None)

        return CarAttribute(None, "NOT_RECEIVED", None)

    @property
    def last_command_type(self):
        return CarAttribute(self._last_command_type, "VALID", self._last_command_time_stamp)

    @property
    def last_command_state(self):
        return CarAttribute(self._last_command_state, "VALID", self._last_command_time_stamp)

    @property
    def last_command_error_code(self):
        return CarAttribute(self._last_command_error_code, "VALID", self._last_command_time_stamp)

    @property
    def last_command_error_message(self):
        return CarAttribute(self._last_command_error_message, "VALID", self._last_command_time_stamp)

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


class Tires:
    """Stores the Tires values at runtime"""

    def __init__(self):
        self.name = "Tires"


class Odometer:
    """Stores the Odometer values at runtime"""

    def __init__(self):
        self.name = "Odometer"


class Features:
    """Stores the Features values at runtime"""

    def __init__(self):
        self.name = "Features"


class RcpOptions:
    """Stores the RcpOptions values at runtime"""

    def __init__(self):
        self.name = "RCP_Options"


class Windows:
    """Stores the Windows values at runtime"""

    def __init__(self):
        self.name = "Windows"


class Doors:
    """Stores the Doors values at runtime"""

    def __init__(self):
        self.name = "Doors"


class Electric:
    """Stores the Electric values at runtime"""

    def __init__(self):
        self.name = "Electric"


class Auxheat:
    """Stores the Auxheat values at runtime"""

    def __init__(self):
        self.name = "Auxheat"


class Precond:
    """Stores the Precond values at runtime"""

    def __init__(self):
        self.name = "Precond"


class BinarySensors:
    """Stores the BinarySensors values at runtime"""

    def __init__(self):
        self.name = "BinarySensors"


class RemoteStart:
    """Stores the RemoteStart values at runtime"""

    def __init__(self):
        self.name = "RemoteStart"


class CarAlarm:
    """Stores the Odometer values at runtime"""

    def __init__(self):
        self.name = "CarAlarm"


class Location:
    """Stores the Location values at runtime"""

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


class GeofenceEvents:
    """Stores the geofence violation values at runtime"""

    def __init__(self):
        self.name = "GeofenceEvents"
        self.events = []


class CarAttribute:
    """Stores the CarAttribute values at runtime"""

    def __init__(self, value, retrievalstatus, timestamp, distance_unit=None, display_value=None, unit=None):
        self.value = value
        self.retrievalstatus = retrievalstatus
        self.timestamp = timestamp
        self.distance_unit = distance_unit
        self.display_value = display_value
        self.unit = unit
