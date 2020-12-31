# mercedesme2020

* > :warning: **This is an very early version**


MercedesME platform as a Custom Component for Home Assistant.

IMPORTANT:

* > :warning: **Home Assistant Core V.0.110 or higher required**

* Please login once in the MercedesME IOS or Android app before you install this component.

* Tested Countries: Germany, Finland

## Configuration

Use the "Add Integration" in Home Assistant and select "MercedesME 2020".

## Optional configuration values

```
None

```

# Available components (depended on your own car)


## Binary Sensors

* warningwashwater
  
* warningcoolantlevellow
  
* warningbrakefluid

* warningenginelight

    `attributes: warningbrakefluid, warningwashwater, warningcoolantlevellow, warninglowbattery`

* parkbrakestatus

    `attributes: preWarningBrakeLiningWear`

* tirewarninglamp

    `attributes: tirepressureRearLeft, tirepressureRearRight, tirepressureFrontRight, tirepressureFrontLeft, tireMarkerFrontRight, tireMarkerFrontLeft,
    tireMarkerRearLeft, tireMarkerRearRight, tirewarningsrdk, tirewarningsprw`

* windowsClosed
  
    `attributes: windowstatusrearleft, windowstatusrearright, windowstatusfrontright, windowstatusfrontleft`


## Sensors

* lock

  `attributes: doorStateFrontLeft, doorStateFrontRight, doorStateRearLeft, doorStateRearRight, frontLeftDoorLocked, frontRightDoorLocked, rearLeftDoorLocked, rearRightDoorLocked, frontLeftDoorClosed, frontRightDoorClosed, rearLeftDoorClosed, rearRightDoorClosed, rearRightDoorClosed, doorsClosed, trunkStateRollup, sunroofstatus, fuelLidClosed, engineHoodClosed`

* Fuel Level (%)

  `attributes: tankLevelAdBlue`

* odometer
  
  `attributes: distanceReset, distanceStart, averageSpeedReset, averageSpeedStart, distanceZEReset, drivenTimeZEReset, drivenTimeReset, drivenTimeStart, ecoscoretotal, ecoscorefreewhl, ecoscorebonusrange, ecoscoreconst, ecoscoreaccel, gasconsumptionstart, gasconsumptionreset, gasTankRange, gasTankLevel, liquidconsumptionstart, liquidconsumptionreset, liquidRangeSkipIndication, rangeliquid, serviceintervaldays, tanklevelpercent, tankReserveLamp, batteryState, tankLevelAdBlue`

* Range Electric

  `attributes: tbd`


  
# Logging

Set the logging to debug with the following settings in case of problems.

```
logger:
  default: warn
  logs:
    custom_components.mbapi2020: debug
```

# Notes

* Tested countries: DE, FI

# Open Items
* Web-Socket reconnect
* General Error Handling
* Add missing Sensors (Lock, Electric, Theft)
* Add car actions (Open/Close, Climate, ...)

# Useful links

* [Forum post](https://community.home-assistant.io/t/mercedes-me-component/41911/520)
