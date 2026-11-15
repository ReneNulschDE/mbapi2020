# "Mercedes-Benz" custom component

![HassFest tests](https://github.com/renenulschde/mbapi2020/workflows/Validate%20with%20hassfest/badge.svg) ![Validate with HACS](https://github.com/ReneNulschDE/mbapi2020/workflows/Validate%20with%20HACS/badge.svg) ![](https://img.shields.io/github/downloads/renenulschde/mbapi2020/total) ![](https://img.shields.io/github/downloads/renenulschde/mbapi2020/latest/total)

Mercedes-Benz platform as a Custom Component for Home Assistant.

IMPORTANT:

- Please login once into the Mercedes-Benz IOS or Android app before you install this component. (For North America, the app name is Mercedes Me Connect)

- Tested Countries: AT, AU, BE, CA, CH, ~~CN~~, DE, DK, ES, FI, FR, IN, IT, IR, NL, NO, NZ, PT, RO, SE, TH, UK, US

- North America: For Cars built 2019 or newer only
- Thailand, India: Please use the region "Europe".
- Mexico, Brazil,...: Please use the region "APAC"
- China: Is not working currently (captcha).
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
- Sound horn
- Preclimate start
- Preclimate stop
- HV battery conditioning start (capability `HVBATTERY_START_CONDITIONING`)
- HV battery conditioning stop (capability `HVBATTERY_STOP_CONDITIONING`)
- Ventilate windows (capability `WINDOWS_VENTILATE`; PIN required in integration options)

### Climate

- `Pre-entry climate` (`climate.preclimate`): unified cabin climate control when `ZEV_PRECONDITIONING_START`/`STOP`, `AUXHEAT_START`/`STOP`, or `auxHeat` is supported. Exposes `HEAT_COOL` (ZEV preconditioning), `HEAT` (auxiliary heater), target temperature control when `TEMPERATURE_CONFIGURE` is available (using dynamic limits/steps and active zones `temperature_points_*Active`), and diagnostic attributes (`operability_available`, `operability_state`, `operating_mode`, `precond_error`, `precond_now_error`, plus per-zone readings).

### Covers

- `Windows` (`cover.windows`) and per-window covers (`window_front_left`, `window_front_right`, `window_rear_left`, `window_rear_right`). Position slider (`SET_POSITION`) is enabled only when `WINDOWS_MOVE` is supported by the vehicle.

### Device Tracker

```
attributes:
positionHeading
```

### Numbers

- `Target state of charge` (`number.max_soc`): slider entity backed by `CHARGING_CONFIGURE`, `BATTERY_MAX_SOC_CONFIGURE`, or `CHARGE_PROGRAM_CONFIGURE`. Automatically applies command capability bounds (`minValue`/`maxValue`/`steps`) intersected with vehicle `maxSocLowerLimit` / `maxSocUpperLimit`.

### Selects

- `Charge program` (`select.charge_program`): active charging program selector (`selectedChargeProgram`) exposing options valid for the vehicle (`default`, `home`, `work`, plus `instant` and `ac_dc_standard` when supported by `BATTERY_CHARGE_PROGRAM_CONFIGURE` or `CHARGING_CONFIGURE`).

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

- Charging Power Limit

  ```
  attributes:
  chargingPowerRestriction
  ```

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

- Smart Charging

  Four sensors for cars whose charging is managed by a provider. A car without that
  setup never sends the data, and the sensors are then not created at all.

  ```
  Internal Names: smartcharginglocation, smartchargingstation, smartchargingstrategy, smartchargingerror
  ```

  - Smart Charging Location - the charging location the car reports, e.g. `Home`
  - Smart Charging Station - the charging station at that location
  - Smart Charging Strategy - the charging strategy in use, e.g. `immediate`.
    Free text set by the backend, so other values can appear at any time.
  - Smart Charging Error - the most severe error the car currently reports, `unknown` when there is none

  ```
  Values of Smart Charging Error:
  UNKNOWN_CODE
  UNAVAILABLE_WITHOUT_OPTIMIZATION
  UNAVAILABLE_DIRECT_CHARGING_MODE
  UNAVAILABLE_MISSING_VEHICLE_CONNECTION

  attributes:
  smartChargingErrorList
  ```

  The car can report more than one error at once. The state names the most severe of them -
  `MAJOR_ERROR` before `MINOR_ERROR` before `WARNING` - while `smartChargingErrorList` keeps all
  of them with their severity:

  ```yaml
  smartChargingErrorList:
    - code: UNAVAILABLE_MISSING_VEHICLE_CONNECTION
      severity: MAJOR_ERROR
    - code: UNAVAILABLE_WITHOUT_OPTIMIZATION
      severity: WARNING
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

- `Active weekly profile` (`activeweeklyprofile`): current departure schedule label with `weeklyProfileTimeProfiles`, `weeklyProfileLimits`, and readable `weeklyProfileSlots` attributes.
- `Charging timers` (`chargingtimers`): unified summary of active/inactive charging timers combining modern `chargingTimer` (`CHARGING_CLOCK_TIMER_CONFIGURE`) and legacy `chargingBreakClockTimer` into normalized `chargingTimerSlots`.
- `HV battery conditioning state` (`hvbatteryprecondstate`): HV battery thermal conditioning state (`hvBatteryPrecondState`) with `hvBatteryPrecondActive`, `hvBatteryPrecondAvailability`, and `hvBatteryPrecondDuration` attributes when reported by the vehicle.
- Additional capability/signal-gated diagnostic & telemetry sensors (created only when the vehicle reports non-missing values): `rangeelectricwltp`, `overallrange`, `gainedrangesincestartofcharging`, `maxsocupperlimit`, `evrangeassistdriveonsoc`, `evrangeassistdriveontime`, `sohcalibrationstate`, `chargingerrordetails`, `chargingcompatibilityerror`, `chargingscheduleactive`, `chargingpredictiondeparturerange`, `chargingpredictiondeparturesoc`, `lasttirepressuretimestamp`, `tiresensoravailable`, `tirewarninglevelprw`, `oilwarninglevel`, `filterparticleloading`, `turnoffengineprewarning`, `hvbatterythermalpropagationevent`, `hybridwarnings`, `tcuconnectionstatelowchannel`, `sunroofevent`, `temperatureunithu`.

### Services

Some services require that the security PIN is created in your mobile Android/IOS app. Please store the pin to the options-dialog of the integration

- refresh_access_token:
  Refresh the API access token

- auxheat_start:
  Start the auxiliary heating of a car defined by a vin.

- auxheat_stop:
  Stop the auxiliary heating of a car defined by a vin.

- battery_max_soc_configure:
  Configure the maximum value for the state of charge of the HV battery of a car defined by a vin. Dispatches `ChargingConfigure`, `BatteryMaxSocConfigure`, or `ChargeProgramConfigure` depending on vehicle capabilities. If no charge program is given on `CHARGE_PROGRAM_CONFIGURE` cars, the program the car is currently running is configured.

- charge_program_configure:
  Select the active charging program (`program`: 0=Default, 1=Instant, 2=Home, 3=Work, 4=AC/DC standard) and optional `max_soc`. Supports `CHARGE_PROGRAM_CONFIGURE`, `BATTERY_CHARGE_PROGRAM_CONFIGURE`, and `CHARGING_CONFIGURE`.

- charge_coupler_stop:
  Stop the running charging session and release the charge coupler of a car defined by a vin. PIN required.

- doors_unlock:
  Unlock a car defined by a vin. PIN required.

- doors_lock:
  Lock a car defined by a vin.

- engine_start:
  Start the engine of a car defined by a vin. PIN required.

- engine_stop:
  Stop the engine of a car defined by a vin.

- hv_battery_start_conditioning:
  Start high-voltage battery thermal preconditioning on supported EVs (`HVBATTERY_START_CONDITIONING`).

- hv_battery_stop_conditioning:
  Stop high-voltage battery thermal preconditioning on supported EVs (`HVBATTERY_STOP_CONDITIONING`).

- preconditioning_configure_seats:
  Configure which seats should be preconditioned of a car defined by a vin.

- preheat_start:
  Start the preheating of a zero emission car defined by a vin.

- preheat_start_departure_time:
  Start the preheating of a zero emission car defined by a vin and the departure time in minutes since midnight

- preheat_stop:
  Stop the preheating of a zero emission car defined by a vin.

- preheat_stop_departure_time:
  Disable scheduled departure preconditioning of a zero emission car defined by a vin.

- preconditioning_configure:
  Configure the departure time preconditioning mode (disabled, single, or weekly) of a zero emission car defined by a vin.

- send_route:
  Send a route to a car defined by a vin.

- sigpos_start:
  Start light and/or acoustic signaling of a car defined by a vin. The optional `sigpos_type` selects the
  mode (0=LIGHT_ONLY, 1=HORN_ONLY, 2=LIGHT_AND_HORN, 3=PANIC_ALARM), `sigpos_duration` the duration in
  seconds. Which modes a car accepts is reported by the SIGPOS_TYPE command capability - most cars support
  only a subset.

- sunroof_open:
  Open the sunroof of a car defined by a vin. PIN required.

- sunroof_tilt:
  Tilt the sunroof of a car defined by a vin. PIN required.

- sunroof_close:
  Close the sunroof of a car defined by a vin.

- temperature_configure:
  Configure the target preconditioning/auxheat temperatures for zones in a car defined by a VIN.

- week_profile_configure:
  Add, change or delete one entry of the weekly departure profile of a car defined by a vin. `operation` is
  `add`, `update` or `delete`. `add` takes no `identifier` - the car assigns one - and needs a `time`;
  `update` and `delete` need the `identifier` of the entry as the `Active weekly profile` sensor lists it.
  The car replaces its whole profile on every call, so the entries that are not named are re-sent
  unchanged - which also means the service needs a full update of the profile first and refuses the call
  until it has one. Which options a car accepts differs by model: only some accept `charging`, `precond`
  and `battery_precond` per entry or a `schedule_type` other than `no_selection`, and the call is rejected
  with an explanation when the car does not.

- windows_close:
  Close the windows of a car defined by a vin.

- windows_move
  Move the windows to a given position. PIN required.

- windows_open:
  Open the windows of a car defined by a vin. PIN required.

- windows_ventilate:
  Set the windows into ventilation position on a car defined by a vin (`WINDOWS_VENTILATE`). PIN required.

### Switches

- `AuxHeat` (`switch.auxheat`) - Start/Stop the auxiliary heating of the car
- `Preclimate` (`switch.precond`) - Start/Stop the preclimate function of the car
- `HV battery conditioning` (`switch.hv_battery_conditioning`) - Start/Stop HV battery thermal conditioning (`HVBATTERY_START_CONDITIONING`/`HVBATTERY_STOP_CONDITIONING`); uses `assumed_state` when `hvBatteryPrecondState` telemetry is not reported

### Vehicle Generation Compatibility Matrix

| Feature / Area | NTG5.5 / Legacy | MBUX (NTG6 / NTG7) | MB.OS (GEN20x / e.g. X244) |
| --- | --- | --- | --- |
| Charge target (`number.max_soc` / `battery_max_soc_configure`) | `CHARGE_PROGRAM_CONFIGURE` (when EV/PHEV) or `BATTERY_MAX_SOC_CONFIGURE` | `CHARGE_PROGRAM_CONFIGURE` (`50-100`, `chargePrograms` per program) | `CHARGING_CONFIGURE` + `BATTERY_MAX_SOC_CONFIGURE` (uses `electric.maxSoc`, `maxSocLowerLimit`/`UpperLimit`) |
| Charge program (`select.charge_program` / `charge_program_configure`) | `CHARGE_PROGRAM_CONFIGURE` (`0, 2, 3`) or `BATTERY_CHARGE_PROGRAM_CONFIGURE` (`0, 1`) | `CHARGE_PROGRAM_CONFIGURE` (`default`, `home`, `work`) | `CHARGING_CONFIGURE` + `BATTERY_CHARGE_PROGRAM_CONFIGURE` (supports `default`, `instant`, `home`, `work`, `ac_dc_standard` (`4`)) |
| Charging timers (`sensor.chargingtimers` / `charging_break_clocktimer_configure`) | `chargingBreakClockTimer` (break clock timer list) | `chargingBreakClockTimer` (`ChargingBreakClockTimerConfigure`) | `chargingTimer` (`CHARGING_CLOCK_TIMER_CONFIGURE` / `ClockTimerConfigure`) normalized into `chargingTimerSlots` |
| HV battery conditioning | Usually unavailable | On select EQ models (`HVBATTERY_START/STOP_CONDITIONING`) | `HVBATTERY_START/STOP_CONDITIONING` (`button`, `switch.hv_battery_conditioning`, `sensor.hvbatteryprecondstate`) |
| Windows control | `WINDOWS_OPEN` / `WINDOWS_CLOSE` (some models `WINDOWS_MOVE`) | `WINDOWS_MOVE` slider cover + `WINDOWS_VENTILATE` | `WINDOWS_OPEN` / `WINDOWS_CLOSE` + `WINDOWS_VENTILATE` button (`WINDOWS_MOVE=false` hides position slider) |
| Cabin preconditioning (`climate.preclimate`) | `auxHeat` / `AUXHEAT_*` (`HEAT`) and/or `ZEV_*` (`HEAT_COOL`) | `ZEV_*` (`HEAT_COOL`) + `TEMPERATURE_CONFIGURE` | `ZEV_*` (`HEAT_COOL`) + `TEMPERATURE_CONFIGURE` (`0.5 C` steps) + `precondOperabilityState` |
| Battery SoH & smart charging | Usually unavailable | Partial prediction / charge flap status on EQ | Extended SoH calibration, charging predictions/schedules, `hvBatterySoH`, inlet coupler locks |

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
