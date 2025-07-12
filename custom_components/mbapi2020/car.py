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
    "chargeFlapACStatus",
]

ELECTRIC_OPTIONS = [
    "rangeelectric",
    "chargeCouplerACStatus",
    "chargeCouplerDCStatus",
    "chargeCouplerACLockStatus",
    "chargeCouplerDCLockStatus",
    "chargingactive",
    "chargingBreakClockTimer",
    "chargingstatus",
    "chargingPower",
    "departureTimeMode",
    "distanceElectricalReset",
    "distanceElectricalStart",
    "distanceZEReset",
    "distanceZEStart",
    "ecoElectricBatteryTemperature",
    "electricconsumptionstart",
    "electricconsumptionreset",
    "electricRatioStart",
    "electricRatioOverall",
    "endofchargetime",
    "endofChargeTimeWeekday",
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

WIPER_OPTIONS = ["wiperLifetimeExceeded", "wiperHealthPercent"]

PRE_COND_OPTIONS = [
    "precondStatus",
    "precondOperatingMode",
    "precondState",
    "precondActive",
    "precondError",
    "precondNow",
    "precondNowError",
    "precondDuration",
    "precondatdeparture",
    "precondAtDepartureDisable",
    "precondSeatFrontLeft",
    "precondSeatFrontRight",
    "precondSeatRearLeft",
    "precondSeatRearRight",
    "temperature_points_frontLeft",
    "temperature_points_frontRight",
    "temperature_points_rearLeft",
    "temperature_points_rearRight",
]

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

    baumuster_description: str = ""
    features: dict[str, bool]
    geofence_events: GeofenceEvents
    geo_fencing_retry_counter: int = 0
    has_geofencing: bool = True
    vehicle_information: dict = {}

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
        self.last_command_time_stamp = 0

        self.binarysensors = None
        self.tires = None
        self.wipers = None
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
        """Get/set if the account is owner of the car."""
        return CarAttribute(self._is_owner, "VALID", None)

    @is_owner.setter
    def is_owner(self, value: bool):
        self._is_owner = value

    @property
    def full_updatemessages_received(self):
        """Get number of received full updates messages."""
        return CarAttribute(self.messages_received["f"], "VALID", None)

    @property
    def partital_updatemessages_received(self):
        """Get number of received partial updates messages."""
        return CarAttribute(self.messages_received["p"], "VALID", None)

    @property
    def last_message_received(self):
        """Get/Set last message received."""
        if self._last_message_received > 0:
            return CarAttribute(datetime.fromtimestamp(int(round(self._last_message_received / 1000))), "VALID", None)

        return CarAttribute(None, "NOT_RECEIVED", None)

    @last_message_received.setter
    def last_message_received(self, value):
        self._last_message_received = value

    @property
    def last_command_type(self):
        """Get/Set last command type."""
        return CarAttribute(self._last_command_type, "VALID", self.last_command_time_stamp)

    @last_command_type.setter
    def last_command_type(self, value):
        self._last_command_type = value

    @property
    def last_command_state(self):
        """Get/Set last command state."""
        return CarAttribute(self._last_command_state, "VALID", self.last_command_time_stamp)

    @last_command_state.setter
    def last_command_state(self, value):
        self._last_command_state = value

    @property
    def last_command_error_code(self):
        """Get/Set last command error code."""
        return CarAttribute(self._last_command_error_code, "VALID", self.last_command_time_stamp)

    @last_command_error_code.setter
    def last_command_error_code(self, value):
        self._last_command_error_code = value

    @property
    def last_command_error_message(self):
        """Get/Set last command error message."""
        return CarAttribute(self._last_command_error_message, "VALID", self.last_command_time_stamp)

    @last_command_error_message.setter
    def last_command_error_message(self, value):
        self._last_command_error_message = value

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

    def check_capabilities(self, required_capabilities: list[str]) -> bool:
        """Check if the car has the required capabilities."""
        return any(self.features.get(capability) is True for capability in required_capabilities)


@dataclass(init=False)
class Tires:
    """Stores the Tires values at runtime."""

    name: str = "Tires"


@dataclass(init=False)
class Wipers:
    """Stores the Wiper values at runtime."""

    name: str = "Wipers"


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
    """Stores the Precondining values at runtime."""

    name: str = "Precond"


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
