# mercedesme2020

> :warning: **This is a very early version**


MercedesME platform as a Custom Component for Home Assistant.

IMPORTANT:

* Please login once in the MercedesME IOS or Android app before you install this component.

* Works in Europe only

* Tested Countries: BE, DE, ES, FI, IT, IR, NL, NO, PT, SE, UK

* For US/CA please use this component: https://github.com/ReneNulschDE/mbapipy

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


### Device Tracker
  
  ```
  attributes:
  positionHeading
  ```

### Sensors

* lock

  ```
  attributes: 
  decklidstatus, doorStatusOverall, doorLockStatusOverall, doorlockstatusgas, doorlockstatusvehicle, doorlockstatusfrontleft,doorlockstatusfrontright, doorlockstatusrearright, doorlockstatusrearleft, doorlockstatusdecklid, doorstatusrearleft, doorstatusfrontright, doorstatusrearright, doorstatusfrontleft, rooftopstatus, sunroofstatus
  ```

  Internal value: doorlockstatusvehicle

  Values:
  0: vehicle unlocked
  1: vehicle internal locked
  2: vehicle external locked
  3: vehicle selective unlocked

* Fuel Level (%)

  `attributes: tankLevelAdBlue`

* odometer
  
  ```
  attributes: 
  distanceReset, distanceStart, averageSpeedReset, averageSpeedStart, distanceZEReset, drivenTimeZEReset, drivenTimeReset, drivenTimeStart, ecoscoretotal, ecoscorefreewhl, ecoscorebonusrange, ecoscoreconst, ecoscoreaccel, gasconsumptionstart, gasconsumptionreset, gasTankRange, gasTankLevel, liquidconsumptionstart, liquidconsumptionreset, liquidRangeSkipIndication, rangeliquid, serviceintervaldays, tanklevelpercent, tankReserveLamp, batteryState, tankLevelAdBlue
  ```

* Range Electric

  ```
  attributes: 
  rangeelectric, chargingstatus, distanceElectricalReset, distanceElectricalStart, ecoElectricBatteryTemperature, electricconsumptionstart,
  electricconsumptionreset, endofchargetime, maxrange, selectedChargeProgram, soc
  ```


### Services
Some services require that the security PIN is created in your mobile Android/IOS app. Please store the pin to the options-dialog of the integration 
* refresh_access_token:
  description: Refresh the API access token

* doors_unlock:
  description: Unlock a car defined by a vin. PIN required.

* doors_lock:
  description: Lock a car defined by a vin.

* engine_start:
  description: Start the engine of a car defined by a vin. PIN required.

* engine_stop:
  description: Stop the engine of a car defined by a vin.

* sunroof_open:
  description: Open the sunroof of a car defined by a vin. PIN required.

* sunroof_close:
  description: Close the sunroof of a car defined by a vin.

  
### Logging

Set the logging to debug with the following settings in case of problems.

```
logger:
  default: warn
  logs:
    custom_components.mbapi2020: debug
```

### Open Items
* General Error Handling
* Add missing Sensors (Theft)
* Add more car actions (Climate, ...)

### Useful links

* [Forum post](https://community.home-assistant.io/t/mercedes-me-component/41911/520)
