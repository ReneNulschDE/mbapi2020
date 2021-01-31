

# mercedesme2020
[![HassFest tests](https://github.com/renenulschde/mbapi2020/workflows/Validate%20with%20hassfest/badge.svg)](https://developers.home-assistant.io/blog/2020/04/16/hassfest)![Validate with HACS](https://github.com/ReneNulschDE/mbapi2020/workflows/Validate%20with%20HACS/badge.svg)


MercedesME platform as a Custom Component for Home Assistant.

IMPORTANT:

* Please login once in the MercedesME IOS or Android app before you install this component. (For North America, the app name is Mercedes Me Connect)

* Tested Countries: BE, CA, DE, ES, FI, IT, IR, NL, NO, PT, SE, UK, US

* North America: For Cars 2019 or newer only

### Installation
* First: This is not a Home Assistant Add-On. It's a custom component.
* There are two ways to install. First you can download the folder custom_component and copy it into your Home-Assistant config folder. Second option is to install HACS (Home Assistant Custom Component Store) and add this repo as a custom repository. (HACS, Integrations, three dots in the upper right corner, ...)
* [How to install a custom component?](https://www.google.com/search?q=how+to+install+custom+components+home+assistant) 
* [How to install HACS?](https://hacs.xyz/docs/installation/prerequisites)
### Configuration

Use the "Add Integration" in Home Assistant and select "MercedesME 2020".

### Optional configuration values

See Options dialog in the Integration under Home-Assistant/Configuration/Integration.

```
Excluded Cars: comma-separated list of VINs.
PIN: Security PIN to execute special services. Please use your MB mobile app to setup
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
    tirepressureRearLeft, tirepressureRearRight, tirepressureFrontRight, tirepressureFrontLeft, tireMarkerFrontRight, tireMarkerFrontLeft,tireMarkerRearLeft, tireMarkerRearRight, tirewarningsrdk, tirewarningsprw
    ```

* windowsClosed
  
  ```
  attributes: 
  windowstatusrearleft, windowstatusrearright, windowstatusfrontright, windowstatusfrontleft
  ```

* remoteStartActive

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

* odometer
  
  ```
  attributes: 
  distanceReset, distanceStart, averageSpeedReset, averageSpeedStart, distanceZEReset, drivenTimeZEReset, drivenTimeReset, drivenTimeStart, ecoscoretotal, ecoscorefreewhl, ecoscorebonusrange, ecoscoreconst, ecoscoreaccel, gasconsumptionstart, gasconsumptionreset, gasTankRange, gasTankLevel, liquidconsumptionstart, liquidconsumptionreset, liquidRangeSkipIndication, rangeliquid, serviceintervaldays, tanklevelpercent, tankReserveLamp, batteryState, tankLevelAdBlue
  ```

* Range Electric

  ```
  attributes: 
  rangeelectric, chargingstatus, distanceElectricalReset, distanceElectricalStart, ecoElectricBatteryTemperature, electricconsumptionstart,
  electricconsumptionreset, endofchargetime, precondActive, maxrange, selectedChargeProgram, soc
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

* Car
  ```
  attributes: 
  full_update_messages_received, partital_update_messages_received, last_message_received, last_command_type, last_command_state, last_command_error_code, last_command_error_message
  ```

* Oil Level in percent
  ```
  attributes: 
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


### Services
Some services require that the security PIN is created in your mobile Android/IOS app. Please store the pin to the options-dialog of the integration 
* refresh_access_token:
  Refresh the API access token

* auxheat_start:
  Start the auxiliary heating  of a car defined by a vin.

* auxheat_stop:
  Stop the auxiliary heating  of a car defined by a vin.

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

### Useful links

* [Forum post](https://community.home-assistant.io/t/mercedes-me-component/41911/520)
