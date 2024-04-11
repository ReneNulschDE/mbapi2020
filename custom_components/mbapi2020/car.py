"""Define the objects to store care data."""

from __future__ import annotations

import collections
from dataclasses import dataclass
from datetime import datetime
from typing import Any

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
    "chargeFlapDCStatus",
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
    "electricRatioStart",
    "electricRatioOverall",
    "endofchargetime",
    "endofChargeTimeWeekday",
    "precondActive",
    "precondDuration",
    "precondState",
    "precondatdeparture",
    "precondNow",
    "precondNowError",
    "precondAtDepartureDisable",
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
    "carAlarm",
    "carAlarmLastTime",
    "carAlarmReason",
    "collisionAlarmTimestamp",
    "interiorSensor",
    "lastParkEvent",
    "lastTheftWarning",
    "lastTheftWarningReason",
    "parkEventLevel",
    "parkEventType",
    "theftAlarmActive",
    "theftSystemArmed",
    "towProtectionSensorStatus",
    "towSensor",
    "interiorProtectionSensorStatus",
    "exteriorProtectionSensorStatus",
]

GeofenceEvents_OPTIONS = ["last_event_zone", "last_event_timestamp", "last_event_type"]


class Car:
    """Car class, stores the car values at runtime."""

    features: dict[str, bool]
    geofence_events: GeofenceEvents
    baumuster_description: str = ""
    has_geofencing: bool = True
    geo_fencing_retry_counter: int = 0

    def __init__(self, vin: str):
        """Initialize the Car instance."""
        self.finorvin = vin

        self.licenseplate = ""
        self._is_owner = False
        self.messages_received = collections.Counter(f=0, p=0)
        self._last_message_received = 0
        self._last_command_type = ""
        self._last_command_state = ""
        self._last_command_error_code = ""
        self._last_command_error_message = ""
        self._last_command_time_stamp = 0
        self._last_full_message = None

        self.binarysensors = None
        self.tires = None
        self.odometer = None
        self.doors = None
        self.location = None
        self.windows = None
        self.rcp_options = None
        self.auxheat = None
        self.precond = None
        self.electric = None
        self.caralarm = None
        self.last_full_message = None
        self.geofence_events = GeofenceEvents()
        self.features = {}
        self.masterdata: dict[str, Any] = {}
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


@dataclass(init=False)
class Tires:
    """Stores the Tires values at runtime."""

    name: str = "Tires"


@dataclass(init=False)
class Odometer:
    """Stores the Odometer values at runtime."""

    name: str = "Odometer"


@dataclass(init=False)
class RcpOptions:
    """Stores the RcpOptions values at runtime."""

    name: str = "RCP_Options"


@dataclass(init=False)
class Windows:
    """Stores the Windows values at runtime."""

    name: str = "Windows"


@dataclass(init=False)
class Doors:
    """Stores the Doors values at runtime."""

    name: str = "Doors"


@dataclass(init=False)
class Electric:
    """Stores the Electric values at runtime."""

    name: str = "Electric"


@dataclass(init=False)
class Auxheat:
    """Stores the Auxheat values at runtime."""

    name: str = "Auxheat"


@dataclass(init=False)
class Precond:
    """Stores the Precond values at runtime."""

    name = "Precond"


@dataclass(init=False)
class BinarySensors:
    """Stores the BinarySensors values at runtime."""

    name: str = "BinarySensors"


@dataclass(init=False)
class RemoteStart:
    """Stores the RemoteStart values at runtime."""

    name: str = "RemoteStart"


@dataclass(init=False)
class CarAlarm:
    """Stores the CarAlarm values at runtime."""

    name: str = "CarAlarm"


@dataclass(init=False)
class Location:
    """Stores the Location values at runtime."""

    name: str = "Location"


@dataclass(init=False)
class GeofenceEvents:
    """Stores the geofence violation values at runtime."""

    last_event_type: CarAttribute | None = None
    last_event_timestamp: CarAttribute | None = None
    last_event_zone: CarAttribute | None = None
    name: str = "GeofenceEvents"
    events = []


@dataclass(init=False)
class CarAttribute:
    """Stores the CarAttribute values at runtime."""

    def __init__(self, value, retrievalstatus, timestamp, display_value=None, unit=None):
        """Initialize the instance."""
        self.value = value
        self.retrievalstatus = retrievalstatus
        self.timestamp = timestamp
        self.display_value = display_value
        self.unit = unit
