# mercedesme2020

* > :warning: **This is a very early version**


MercedesME platform as a Custom Component for Home Assistant.

IMPORTANT:

* > :warning: **Home Assistant Core V.0.110 or higher required**

* Please login once in the MercedesME IOS or Android app before you install this component.

* Tested Countries: BE, DE, ES, FI, IT, NL, NO, PT, SE, UK

## Configuration

Use the "Add Integration" in Home Assistant and select "MercedesME 2020".

## Optional configuration values

See Options dialog in the Integration section.

```
Excluded Cars: comma-separated list of VINs.

```

## Available components (depends on your own car or purchased licenses)


## Binary Sensors

* warningwashwater
  
* warningcoolantlevellow
  
* warningbrakefluid

* warningenginelight

    `attributes: warningbrakefluid, warningwashwater, warningcoolantlevellow, warninglowbattery`

* parkbrakestatus

    `attributes: preWarningBrakeLiningWear`

* tirewarninglamp

    ```attributes: tirepressureRearLeft, tirepressureRearRight, tirepressureFrontRight, tirepressureFrontLeft, tireMarkerFrontRight, tireMarkerFrontLeft,tireMarkerRearLeft, tireMarkerRearRight, tirewarningsrdk, tirewarningsprw```

* windowsClosed
  
    `attributes: windowstatusrearleft, windowstatusrearright, windowstatusfrontright, windowstatusfrontleft`


## Device Tracker
  
    ```attributes: positionHeading```

## Sensors

* lock

  ```attributes: decklidstatus, doorStatusOverall, doorLockStatusOverall, doorlockstatusgas, doorlockstatusvehicle, doorlockstatusfrontleft,doorlockstatusfrontright, doorlockstatusrearright, doorlockstatusrearleft, doorlockstatusdecklid, doorstatusrearleft, doorstatusfrontright, doorstatusrearright, doorstatusfrontleft, rooftopstatus, sunroofstatus```

Internal value: doorlockstatusvehicle

Values:
0: vehicle unlocked
1: vehicle internal locked
2: vehicle external locked
3: vehicle selective unlocked


* Fuel Level (%)

  `attributes: tankLevelAdBlue`

* odometer
  
  ```attributes: distanceReset, distanceStart, averageSpeedReset, averageSpeedStart, distanceZEReset, drivenTimeZEReset, drivenTimeReset, drivenTimeStart, ecoscoretotal, ecoscorefreewhl, ecoscorebonusrange, ecoscoreconst, ecoscoreaccel, gasconsumptionstart, gasconsumptionreset, gasTankRange, gasTankLevel, liquidconsumptionstart, liquidconsumptionreset, liquidRangeSkipIndication, rangeliquid, serviceintervaldays, tanklevelpercent, tankReserveLamp, batteryState, tankLevelAdBlue```

* Range Electric

  `attributes: rangeelectric, chargingstatus, distanceElectricalReset, distanceElectricalStart, ecoElectricBatteryTemperature, electricconsumptionstart,
  electricconsumptionreset, endofchargetime, maxrange, selectedChargeProgram, soc`



  
# Logging

Set the logging to debug with the following settings in case of problems.

```
logger:
  default: warn
  logs:
    custom_components.mbapi2020: debug
```

# Notes

* Tested Countries: BE, DE, ES, FI, IT, NL, NO, PT, SE, UK

# Open Items
* Web-Socket reconnect
* General Error Handling
* Add missing Sensors (Lock, Electric, Theft)
* Add car actions (Open/Close, Climate, ...)

# Useful links

* [Forum post](https://community.home-assistant.io/t/mercedes-me-component/41911/520)
