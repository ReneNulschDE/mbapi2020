

# mercedesme2020
![HassFest tests](https://github.com/renenulschde/mbapi2020/workflows/Validate%20with%20hassfest/badge.svg) ![Validate with HACS](https://github.com/ReneNulschDE/mbapi2020/workflows/Validate%20with%20HACS/badge.svg)



MercedesME platform as a Custom Component for Home Assistant.

IMPORTANT:

* Please login once in the MercedesME IOS or Android app before you install this component. (For North America, the app name is Mercedes Me Connect)

* Tested Countries: AT, AU, BE, CA, CH, CN, DE, DK, ES, FI, FR, IN, IT, IR, NL, NO, NZ, PT, SE, TH, UK, US

* North America: For Cars 2019 or newer only
* Thailand, India: Please use region "Europe".
* China: support of China is in early stage

### Installation
* First: This is not a Home Assistant Add-On. It's a custom component.
* There are two ways to install. First you can download the folder custom_component and copy it into your Home-Assistant config folder. Second option is to install HACS (Home Assistant Custom Component Store) and select "MercedesME 2020" from the Integrations catalog.
* [How to install a custom component?](https://www.google.com/search?q=how+to+install+custom+components+home+assistant) 
* [How to install HACS?](https://hacs.xyz/docs/installation/prerequisites)
* Restart HA after the installation
* Make sure that you refresh your browser window too
* Use the "Add Integration" in Home Assistant, Settings, Devices & Services and select "MercedesME 2020".
* Use your MB-login email address. Your will receive a 6-digit code via email (valid for 15min).

### Optional configuration values

See Options dialog in the Integration under Home-Assistant/Configuration/Integration.

```
Excluded Cars: comma-separated list of VINs.
PIN: Security PIN to execute special services. Please use your MB mobile app to setup
Disable Capability Check: By default the component checks the capabilities of a car. Active this option to disable the capability check. (For North America)
Debug Save Messages: Enable this option to save all relevant received message into the messages folder of the component
```

## Available components 
Depends on your own car or purchased Mercedes Benz licenses.


### Binary Sensors

* warningwashwater
  
* warningcoolantlevellow
  
* warningbrakefluid

* warningenginelight

    ```
    attributes: 
    warningbrakefluid, warningwashwater, warningcoolantlevellow, warninglowbattery
    ```

* parkbrakestatus

    ```
    attributes: 
    preWarningBrakeLiningWear
    ```

* tirewarninglamp

    ```
    attributes: 
    tireMarkerFrontRight, tireMarkerFrontLeft,tireMarkerRearLeft, tireMarkerRearRight, tirewarningsrdk, tirewarningsprw, tireTemperatureRearLeft, tireTemperatureFrontRight,
    tireTemperatureRearRight, tireTemperatureFrontLeft
    ```

* windowsClosed
  
  ```
  attributes: 
  windowstatusrearleft, windowstatusrearright, windowstatusfrontright, windowstatusfrontleft
  ```

* remoteStartActive
  ```
  attributes: 
  remoteStartTemperature
  ```

* engineState


### Device Tracker
  
  ```
  attributes:
  positionHeading
  ```

### Locks

* lock

  PIN setup in MB App is required. If the pin is not set in the integration options then the lock asks for the PIN.


### Sensors

* lock

  ```
  attributes: 
  decklidstatus, doorStatusOverall, doorLockStatusOverall, doorlockstatusgas, doorlockstatusvehicle, doorlockstatusfrontleft,doorlockstatusfrontright, doorlockstatusrearright, doorlockstatusrearleft, doorlockstatusdecklid, doorstatusrearleft, doorstatusfrontright, doorstatusrearright, doorstatusfrontleft, rooftopstatus, sunroofstatus, engineHoodStatus
  ```

  Internal value: doorlockstatusvehicle

  Values:
  0: vehicle unlocked
  1: vehicle internal locked
  2: vehicle external locked
  3: vehicle selective unlocked

* Fuel Level (%)

  ```
  attributes: 
  tankLevelAdBlue
  ```

* Geofencing Violation

  ```
  attributes: 
  Last_event_zone
  ```
  Values:
  ENTER
  LEAVE

* odometer
  
  ```
  attributes: 
  distanceReset, distanceStart, averageSpeedReset, averageSpeedStart, distanceZEReset, drivenTimeZEReset, drivenTimeReset, drivenTimeStart, ecoscoretotal, ecoscorefreewhl, ecoscorebonusrange, ecoscoreconst, ecoscoreaccel, gasconsumptionstart, gasconsumptionreset, gasTankRange, gasTankLevel, liquidconsumptionstart, liquidconsumptionreset, liquidRangeSkipIndication, rangeliquid, serviceintervaldays, tanklevelpercent, tankReserveLamp, batteryState, tankLevelAdBlue
  ```

* Range Electric

  ```
  attributes: 
  rangeelectric, chargingstatus, chargingPower, distanceElectricalReset, distanceElectricalStart, ecoElectricBatteryTemperature,
  electricconsumptionstart, electricconsumptionreset, endofchargetime, precondActive, precondNow, maxrange, selectedChargeProgram, soc
  ```

* Starter Battery State
  ```
  Internal Name: starterBatteryState
  
  Values     Description_short     Description_long
  "0"        "green"               "Vehicle ok"
  "1"        "yellow"              "Battery partly charged"
  "2"        "red"                 "Vehicle not available"
  "3"        "serviceDisabled"     "Remote service disabled"
  "4"        "vehicleNotAvalable"  "Vehicle no longer available"
  ```

* State of Charge (soc)
  ```
  Internal Name: soc

  State of charge (SoC) is the level of charge of an electric battery relative to its capacity. The units of SoC are percentage points (0% = empty; 100% = full). 

  attributes: 
  maxSocLowerLimit, maxSoc, chargingPower

  ```

* Ignition state
  ```
  Internal Name: ignitionstate

  Values     Description_short     Description_long
  "0"        "lock"                "Ignition lock"
  "1"        "off"                 "Ignition off"
  "2"        "accessory"           "Ignition accessory"
  "4"        "on"                  "Ignition on"
  "5"        "start"               "Ignition start"
  ```

* Aux Heat Status
  ```
  Internal Name: auxheatstatus

  Values    Description
  "0"       inactive
  "1"       normal heating
  "2"       normal ventilation
  "3"       manual heating
  "4"       post heating
  "5"       post ventilation
  "6"       auto heating
  
  attributes:
  auxheattime1, auxheattime2, auxheattime3, auxheattimeselection, auxheatActive, auxheatwarnings, auxheattime2: '00:00'

  ```

* Departure Time
  ```
  Internal Name: departuretime

  Planned departure time to initiate preclimate functions

  attributes:
  departureTimeWeekday

  ```

### Diagnostic Sensors 
[Diagnostic sensors](https://www.home-assistant.io/blog/2021/11/03/release-202111/#entity-categorization) are hidden by default, check the devices page to see the current values

* Car
  ```
  attributes: 
  full_update_messages_received, partital_update_messages_received, last_message_received, last_command_type, last_command_state, last_command_error_code, last_command_error_message
  ```

* RCP_Features

  Sensor shows true if extended configuration like interior lighting is available. This feature requires a reauthentication in case you used a version <0.6 before (We need some more permissions...). Shows False in case reauthentication has not happened or the feature is not available for your car.
  ```
  attributes: 
  rcp_supported_settings (List of all remote configuration options, I'll implement them step by step as services or buttons)
  ```
### Services
Some services require that the security PIN is created in your mobile Android/IOS app. Please store the pin to the options-dialog of the integration 
* refresh_access_token:
  Refresh the API access token

* auxheat_start:
  Start the auxiliary heating of a car defined by a vin.

* auxheat_stop:
  Stop the auxiliary heating of a car defined by a vin.

* battery_max_soc_configure:
  Configure the maximum value for the state of charge of the HV battery of a car defined by a vin.

* doors_unlock:
  Unlock a car defined by a vin. PIN required.

* doors_lock:
  Lock a car defined by a vin.

* engine_start:
  Start the engine of a car defined by a vin. PIN required.

* engine_stop:
  Stop the engine of a car defined by a vin.

* preheat_start:
  Start the preheating of a zero emission car defined by a vin.

* preheat_start_departure_time:
  Start the preheating of a zero emission car defined by a vin and the departure time in minutes since midnight

* preheat_stop:
  Stop the preheating of a zero emission car defined by a vin.

* send_route:
  Send a route to a car defined by a vin.

* sigpos_start:
  Start light signaling of a car defined by a vin.

* sunroof_open:
  Open the sunroof of a car defined by a vin. PIN required.

* sunroof_close:
  Close the sunroof of a car defined by a vin.

* windows_open:
  Open the windows of a car defined by a vin. PIN required.

* windows_close:
  Close the windows of a car defined by a vin.


### Switches

* AuxHeat - Start/Stop the auxiliary heating of the car

### Logging

Set the logging to debug with the following settings in case of problems.

```
logger:
  default: warn
  logs:
    custom_components.mbapi2020: debug
```

### Open Items
* Add missing Sensors (Theft)


### Backup and Restore
* In case of problems after a restore of Home Assistant, please delete the file .mercedesme-token-cache in your HA-config folder and restart HA

### Useful links

* [Forum post](https://community.home-assistant.io/t/mercedes-me-component/41911/520)


### Attributes

* Charging Status
  
  ```
  0=CHARGING
  1=CHARGING_ENDS
  2=CHARGE_BREAK
  3=UNPLUGGED
  4=FAILURE
  5=SLOW
  6=FAST
  7=DISCHARGING
  8=NO_CHARGING
  9=SLOW_CHARGING_AFTER_REACHING_TRIP_TARGET
  10=CHARGING_AFTER_REACHING_TRIP_TARGET
  11=FAST_CHARGING_AFTER_REACHING_TRIP_TARGET
  12=UNKNOWN
  ```

* interiorProtectionStatus
  ```
  0=NOT_ACTIVE_SELECTED
  1=NOT_ACTIVE_UNSELECTED
  2=ACTIVE
  -1=UNKNOWN  
  ```

* interiorMonitoringState

  ```
  0=INM_IDLE
  1=INM_WAKE_UP
  2=INM_RECORDING
  3=INM_PICTURE_TAKEN
  4=INM_ANNOUNCE
  5=INM_UPLOADING
  6=INM_COMPLETED
  101=INM_CAMERA_BROKEN
  103=INM_MEMORY_FULL
  105=INM_PRIVACY_MODE_ACTIVE
  106=INM_PICTURE_TAKING_DISABLED
  108=INM_ACTIVE_BURSTMODE
  108=INM_PICTURE_TAKING_INTERRUPTED
  -1=UNKNOWN
  ```

* exteriorMonitoringState

  ```
  0=EXM_IDLE
  1=EXM_WAKE_UP
  2=EXM_REQUEST_SUBMITTED
  3=EXM_RECORDING
  4=EXM_ANNOUNCE
  5=EXM_UPLOADING
  6=EXM_COMPLETED
  101=EXM_AE_REQUEST_DENIED
  106=EXM_AE_INCAPABLE
  108=EXM_AE_OVERRULED
  110=EXM_AE_PLAY_PROTECTION_ACTIVE
  111=EXM_AE_PRECONDITION_MISSING
  -1=UNKNOWN
  ```

* parkEventLevel
  
  ```
  0=LOW
  1=MEDIUM
  2=HIGH
  -1=UNKNOWN
  ```

* parkEventType

  ```
  0=IDLE
  1=FRONT_LEFT
  2=FRONT_MIDDLE
  3=FRONT_RIGHT
  4=RIGHT
  5=REAR_RIGHT
  6=REAR_MIDDLE
  7=REAR_LEFT
  8=LEFT
  9=DIRECTION_UNKNOWN
  -1=UNKNOWN
  ```

* theftAlarmActive

  ```
  ?
  ```

* theftWarningReasonState

  ```
  0=NO_ALARM
  16=BASIS_ALARM
  17=DOOR_FRONT_LEFT
  18=DOOR_FRONT_RIGHT
  19=DOOR_REAR_LEFT
  20=DOOR_REAR_RIGHT
  21=HOOD
  22=DECKLID
  23=COMMON_ALM_IN
  24=PANIC
  25=GLOVEBOX
  26=CENTERBOX
  27=REARBOX
  32=SENSOR_VTA
  33=ITS
  34=ITS_SLV
  35=TPS
  36=SIREN
  37=HOLD_COM
  38=REMOTE
  42=EXT_ITS_1
  43=EXT_ITS_2
  44=EXT_ITS_3
  45=EXT_ITS_4
  ```

* towProtectionSensorStatus

  ```
  0=NOT_ACTIVE_SELECTED
  1=NOT_ACTIVE_UNSELECTED
  2=ACTIVE
  3=PROCESSING
  4=UNKNOWN
  ```
