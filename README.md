# "Mercedes-Benz" custom component

![HassFest tests](https://github.com/renenulschde/mbapi2020/workflows/Validate%20with%20hassfest/badge.svg) ![Validate with HACS](https://github.com/ReneNulschDE/mbapi2020/workflows/Validate%20with%20HACS/badge.svg) ![](https://img.shields.io/github/downloads/renenulschde/mbapi2020/total) ![](https://img.shields.io/github/downloads/renenulschde/mbapi2020/latest/total)

Mercedes-Benz platform as a Custom Component for Home Assistant.


> ⚠️ **SEEKING NEW MAINTAINER** ⚠️  
> After 8+ years of development, I'm selling my last Mercedes and can no longer maintain this integration effectively. **[Looking for someone to take over →](https://github.com/ReneNulschDE/mbapi2020/issues/372)**  



IMPORTANT:

- Please login once into the Mercedes-Benz IOS or Android app before you install this component. (For North America, the app name is Mercedes Me Connect)

- Tested Countries: AT, AU, BE, CA, CH, ~~CN~~, DE, DK, ES, FI, FR, IN, IT, IR, NL, NO, NZ, PT, RO, SE, TH, UK, US

- North America: For Cars 2019 or newer only
- Thailand, India: Please use region "Europe".
- China: Is not working currently, See #339 in case you would like to help
- Smart cars data are not available after 2025-01-06
- Discussions, Feature Requests via [HA-Community Forum](https://community.home-assistant.io/t/mercedes-me-component/41911)

### Installation

- First: This is not a Home Assistant Add-On. It's a custom component.
- There are two ways to install. First you can download the folder custom_component and copy it into your Home-Assistant config folder. Second option is to install HACS (Home Assistant Custom Component Store) and select "MercedesME 2020" from the Integrations catalog.
- [How to install a custom component?](https://www.google.com/search?q=how+to+install+custom+components+home+assistant)
- [How to install HACS?](https://hacs.xyz/docs/use/)
- Restart HA after the installation
- Make sure that you refresh your browser window too
- Use the "Add Integration" in Home Assistant, Settings, Devices & Services and select "MercedesME 2020".
- Enter your Mercedes-Benz account credentials (username/password) in the integration setup
  **Important Notes:**
- consider using a dedicated Mercedes-Benz account for Home Assistant
- if MFA is enabled on your Mercedes-Benz account, authentication will fail. You must disable MFA or use a separate account without MFA.
- You will receive an email from Mercedes stating:

  - A new device has logged in
  - Device type: iOS/Mobile Safari

  This is normal and can happen also over the day, as the component sometimes has to re-login.

### How to Prevent Account Blocking

To reduce the risk of your account being blocked, please follow these recommendations:

1. **Create a separate MB user account for use with this component.**
2. **Invite the new user to the vehicle:**  
   The primary user of the vehicle can invite the new HA-MB account to access the vehicle. Up to six additional users can be invited to each vehicle.
3. **Use each account in a single environment only:**  
   Use one account exclusively in HA or in the official MB tools, but never in both simultaneously.

#### Important Notes

- Certain features, such as geofencing data, are available only to the primary user.
- If geofencing is required in your HA environment, use the primary user account in HA and the secondary accounts in the official MB apps.

---

### Optional configuration values

See Options dialog in the Integration under Home-Assistant/Configuration/Integration.

```
Excluded Cars: comma-separated list of VINs.
PIN: Security PIN to execute special services. Please use your MB mobile app to setup
Disable Capability Check: By default the component checks the capabilities of a car. Active this option to disable the capability check. (For North America)
Debug Save Messages: Enable this option to save all relevant received message into the messages folder of the component
```

## Available components

Depends on your own car or purchased Mercedes-Benz licenses.

### Binary Sensors

- warningwashwater

- warningcoolantlevellow

- warningbrakefluid

- warningenginelight

  ```
  attributes:
  warningbrakefluid, warningwashwater, warningcoolantlevellow, warninglowbattery
  ```

- parkbrakestatus

  ```
  attributes:
  preWarningBrakeLiningWear
  ```

- theftsystemarmed

  ```
  attributes:
  carAlarmLastTime, carAlarmReason, collisionAlarmTimestamp, interiorSensor, interiorProtectionStatus, interiorMonitoringLastEvent, interiorMonitoringStatus, exteriorMonitoringLastEvent, exteriorMonitoringStatus, lastParkEvent, lastTheftWarning, lastTheftWarningReason, parkEventLevel, parkEventType, theftAlarmActive, towProtectionSensorStatus, towSensor,
  ```

- tirewarninglamp

  ```
  attributes:
  tireMarkerFrontRight, tireMarkerFrontLeft,tireMarkerRearLeft, tireMarkerRearRight, tirewarningsrdk, tirewarningsprw, tireTemperatureRearLeft, tireTemperatureFrontRight,
  tireTemperatureRearRight, tireTemperatureFrontLeft
  ```

- windowsClosed

  ```
  attributes:
  windowstatusrearleft, windowstatusrearright, windowstatusfrontright, windowstatusfrontleft
  ```

- remoteStartActive

  ```
  attributes:
  remoteStartTemperature
  ```

- engineState

- chargeFlapACStatus

- Preclimate Status (Preconditioning)

  ```
  attributes:
  precondState, precondActive, precondError, precondNow, precondNowError, precondDuration, precondatdeparture, precondAtDepartureDisable, precondSeatFrontLeft, precondSeatFrontRight, precondSeatRearLeft, precondSeatRearRight, temperature_points_frontLeft, temperature_points_frontRight, temperature_points_rearLeft, temperature_points_rearRight,

  ```

- wiperHealth

  ```
  attributes:
  wiperLifetimeExceeded
  ```

### Buttons

- Flash light
- Preclimate start
- Preclimate stop

### Device Tracker

```
attributes:
positionHeading
```

### Locks

- lock

  PIN setup in MB App is required. If the pin is not set in the integration options then the lock asks for the PIN.

### Sensors

- lock

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

- Fuel Level (%)

  ```
  attributes:
  tankLevelAdBlue
  ```

- Geofencing Violation

  ```
  attributes:
  Last_event_zone
  ```

  Values:
  ENTER
  LEAVE

- odometer

  ```
  attributes:
  distanceReset, distanceStart, averageSpeedReset, averageSpeedStart, distanceZEReset, drivenTimeZEReset, drivenTimeReset, drivenTimeStart, ecoscoretotal, ecoscorefreewhl, ecoscorebonusrange, ecoscoreconst, ecoscoreaccel, gasconsumptionstart, gasconsumptionreset, gasTankRange, gasTankLevel, liquidconsumptionstart, liquidconsumptionreset, liquidRangeSkipIndication, rangeliquid, serviceintervaldays, tanklevelpercent, tankReserveLamp, batteryState, tankLevelAdBlue
  ```

- Oil Level (%)

- Range Electric

  ```
  attributes:
  chargingstatus, distanceElectricalReset, distanceElectricalStart, ecoElectricBatteryTemperature, endofchargetime, maxrange, selectedChargeProgram, precondActive [DEPRECATED], precondNow [DEPRECATED], precondDuration [DEPRECATED]

  ```

- Electric consumption start

- Electric consumption reset

- Charging power

- Starter Battery State

  ```
  Internal Name: starterBatteryState

  Values     Description_short     Description_long
  "0"        "green"               "Vehicle ok"
  "1"        "yellow"              "Battery partly charged"
  "2"        "red"                 "Vehicle not available"
  "3"        "serviceDisabled"     "Remote service disabled"
  "4"        "vehicleNotAvalable"  "Vehicle no longer available"
  ```

- tirepressureRearLeft

- tirepressureRearRight

- tirepressureFrontRight

- tirepressureFrontLeft

- State of Charge (soc)

  ```
  Internal Name: soc

  State of charge (SoC) is the level of charge of an electric battery relative to its capacity. The units of SoC are percentage points (0% = empty; 100% = full).

  attributes:
  maxSocLowerLimit, maxSoc

  ```

- Ignition state

  ```
  Internal Name: ignitionstate

  Values     Description_short     Description_long
  "0"        "lock"                "Ignition lock"
  "1"        "off"                 "Ignition off"
  "2"        "accessory"           "Ignition accessory"
  "4"        "on"                  "Ignition on"
  "5"        "start"               "Ignition start"
  ```

- Aux Heat Status

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
  auxheattime1, auxheattime2, auxheattime3, auxheattimeselection, auxheatActive, auxheatwarnings, auxheattime2, temperature_points_frontLeft, temperature_points_frontRight

  ```

- Departure Time

  ```
  Internal Name: departuretime

  Planned departure time to initiate preclimate functions

  attributes:
  departureTimeWeekday

  ```

### Diagnostic Sensors

[Diagnostic sensors](https://www.home-assistant.io/blog/2021/11/03/release-202111/#entity-categorization) are hidden by default, check the devices page to see the current values

- Car

  ```
  attributes:
  full_update_messages_received, partital_update_messages_received, last_message_received, last_command_type, last_command_state, last_command_error_code, last_command_error_message
  ```

- RCP_Features

  Sensor shows true if extended configuration like interior lighting is available. This feature requires a reauthentication in case you used a version <0.6 before (We need some more permissions...). Shows False in case reauthentication has not happened or the feature is not available for your car.

  ```
  attributes:
  rcp_supported_settings (List of all remote configuration options, I'll implement them step by step as services or buttons)
  ```

### Services

Some services require that the security PIN is created in your mobile Android/IOS app. Please store the pin to the options-dialog of the integration

- refresh_access_token:
  Refresh the API access token

- auxheat_start:
  Start the auxiliary heating of a car defined by a vin.

- auxheat_stop:
  Stop the auxiliary heating of a car defined by a vin.

- battery_max_soc_configure:
  Configure the maximum value for the state of charge of the HV battery of a car defined by a vin.

- doors_unlock:
  Unlock a car defined by a vin. PIN required.

- doors_lock:
  Lock a car defined by a vin.

- engine_start:
  Start the engine of a car defined by a vin. PIN required.

- engine_stop:
  Stop the engine of a car defined by a vin.

- preconditioning_configure_seats:
  Configure which seats should be preconditioned of a car defined by a vin.

- preheat_start:
  Start the preheating of a zero emission car defined by a vin.

- preheat_start_departure_time:
  Start the preheating of a zero emission car defined by a vin and the departure time in minutes since midnight

- preheat_stop:
  Stop the preheating of a zero emission car defined by a vin.

- send_route:
  Send a route to a car defined by a vin.

- sigpos_start:
  Start light signaling of a car defined by a vin.

- sunroof_open:
  Open the sunroof of a car defined by a vin. PIN required.

- sunroof_tilt:
  Tilt the sunroof of a car defined by a vin. PIN required.

- sunroof_close:
  Close the sunroof of a car defined by a vin.

- temperature_configure:
  Configure the target preconditioning/auxheat temperatures for zones in a car defined by a VIN.

- windows_close:
  Close the windows of a car defined by a vin.

- windows_move
  Move the windows to a given position. PIN required.

- windows_open:
  Open the windows of a car defined by a vin. PIN required.

### Switches

- AuxHeat - Start/Stop the auxiliary heating of the car
- Preclimate - Start/Stop the preclimate function of the car

### Logging

Set the logging to debug with the following settings in case of problems.

```
logger:
  default: warn
  logs:
    custom_components.mbapi2020: debug
```

### Open Items

- Find a maintainer

### Useful links

- [Forum post](https://community.home-assistant.io/t/mercedes-me-component/41911/520)

## Custom Lovelace Card

Enhance your experience with this integration by using [VEHICLE INFO CARD](https://github.com/ngocjohn/vehicle-info-card). This card is designed to work seamlessly with the integration, providing a beautiful and intuitive interface to display the data in your Home Assistant dashboard.

### Key Features

- **Seamless Integration**: Automatically pulls in data from the integration.
- **Customizable**: Easily modify the card’s appearance to fit your theme.
- **Interactive**: Includes controls to interact with the data directly from your dashboard.
- **Multilingual Support**: The card includes various translations, making it accessible in multiple languages.

[Check out the Custom Lovelace Card](https://github.com/ngocjohn/vehicle-info-card) for more details and installation instructions.
