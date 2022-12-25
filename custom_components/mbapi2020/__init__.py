"""The MercedesME 2020 integration."""
import asyncio
from datetime import datetime, timedelta
import time

import aiohttp
import voluptuous as vol


from homeassistant.config_entries import ConfigEntry, SOURCE_REAUTH
from homeassistant.const import (
    LENGTH_KILOMETERS,
    LENGTH_MILES,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import aiohttp_client
import homeassistant.helpers.device_registry as dr
from homeassistant.helpers.entity import (
    Entity,
    EntityCategory
)
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.components import system_health
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from homeassistant.util import slugify

from .const import (
    ATTR_MB_MANUFACTURER,
    CONF_REGION,
    CONF_VIN,
    CONF_TIME,
    DOMAIN,
    LOGIN_BASE_URI,
    LOGGER,
    MERCEDESME_COMPONENTS,
    SERVICE_REFRESH_TOKEN_URL,
    SERVICE_AUXHEAT_CONFIGURE,
    SERVICE_AUXHEAT_START,
    SERVICE_AUXHEAT_STOP,
    SERVICE_BATTERY_MAX_SOC_CONFIGURE,
    SERVICE_DOORS_LOCK_URL,
    SERVICE_DOORS_UNLOCK_URL,
    SERVICE_ENGINE_START,
    SERVICE_ENGINE_STOP,
    SERVICE_SIGPOS_START,
    SERVICE_SEND_ROUTE,
    SERVICE_PREHEAT_START,
    SERVICE_PREHEAT_START_DEPARTURE_TIME,
    SERVICE_PREHEAT_STOP,
    SERVICE_SUNROOF_CLOSE,
    SERVICE_SUNROOF_OPEN,
    SERVICE_WINDOWS_CLOSE,
    SERVICE_WINDOWS_OPEN,
    SERVICE_AUXHEAT_CONFIGURE_SCHEMA,
    SERVICE_BATTERY_MAX_SOC_CONFIGURE_SCHEMA,
    SERVICE_PREHEAT_START_SCHEMA,
    SERVICE_SEND_ROUTE_SCHEMA,
    SERVICE_VIN_SCHEMA,
    SERVICE_VIN_TIME_SCHEMA,
    SensorConfigFields as scf

)
from .car import Car, CarAttribute, Features, RcpOptions
from .client import Client
from .errors import WebsocketError

CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)
DEBUG_ADD_FAKE_VIN = False

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the MercedesME 2020 component."""

    if DOMAIN not in config:
        return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Set up MercedesME 2020 from a config entry."""

    try:

        #Find the right way to migrate old configs
        region = config_entry.data.get(CONF_REGION, None)
        if region is None:
            region = "Europe"


        mercedes = MercedesMeContext(
            hass,
            config_entry,
            region = region
        )

        await mercedes.client.set_rlock_mode()

        try:
            token_info = await mercedes.client.oauth.async_get_cached_token()
        except aiohttp.ClientError as err:
            LOGGER.debug("Can not connect to MB OAuth API %s. Will try again.", LOGIN_BASE_URI)
            raise ConfigEntryNotReady from err

        if token_info is None:
            LOGGER.error("Authentication failed. Please reauthenticate.")
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": SOURCE_REAUTH},
                    data=config_entry,
                )
            )
            return False

        masterdata = await mercedes.client.api.get_user_info()
        mercedes.client.write_debug_json_output(masterdata, "md")

        dev_reg = dr.async_get(hass)

        for car in masterdata.get("assignedVehicles"):

            # Check if the car has a separate VIN key, if not, use the FIN.
            vin = car.get('vin')
            if vin is None:
                vin = car.get('fin')
                LOGGER.debug("VIN not found in masterdata. Used FIN %s instead.", vin)

            # Car is excluded, we do not add this
            if vin in config_entry.options.get('excluded_cars', ""):
                continue

            features = Features()

            try:
                capabilities = await mercedes.client.api.get_car_capabilities_commands(vin)
                mercedes.client.write_debug_json_output(capabilities, "ca")
                for feature in capabilities["commands"]:
                    setattr(features, feature.get("commandName"), feature.get("isAvailable"))
            except aiohttp.ClientError:
                # For some cars a HTTP401 is raised when asking for capabilities, see github issue #83
                # We just ignore the capabilities
                LOGGER.info("Capabilities not available for the car with VIN %s. Make sure you disable the capability check in the option of this component.", vin)

            dev_reg.async_get_or_create(
                config_entry_id=config_entry.entry_id,
                connections=set(),
                identifiers={(DOMAIN, vin)},
                manufacturer=ATTR_MB_MANUFACTURER,
                model=car.get('salesRelatedInformation').get('baumuster').get('baumusterDescription'),
                name=car.get('licensePlate', vin),
                sw_version=car.get('starArchitecture'),
            )

            rcp_options = RcpOptions()
            rcp_supported = await mercedes.client.api.is_car_rcp_supported(vin)
            LOGGER.debug("RCP supported for car %s: %s", vin, rcp_supported)
            setattr(rcp_options, "rcp_supported", CarAttribute(rcp_supported, "VALID", 0))
            rcp_supported = False
            if rcp_supported:
                rcp_supported_settings = await mercedes.client.api.get_car_rcp_supported_settings(vin)
                if rcp_supported_settings:
                    mercedes.client.write_debug_json_output(rcp_supported_settings, "rcs")
                    if rcp_supported_settings.get("data"):
                        if rcp_supported_settings.get("data").get("attributes"):
                            if rcp_supported_settings.get("data").get("attributes").get("supportedSettings"):
                                LOGGER.debug("RCP supported settings: %s", str(rcp_supported_settings.get("data").get("attributes").get("supportedSettings")))
                                setattr(rcp_options, "rcp_supported_settings", CarAttribute(rcp_supported_settings.get("data").get("attributes").get("supportedSettings"), "VALID", 0))

                                for setting in rcp_supported_settings.get("data").get("attributes").get("supportedSettings"):
                                    setting_result = await mercedes.client.api.get_car_rcp_settings(vin, setting)
                                    if setting_result is not None:
                                        mercedes.client.write_debug_json_output(setting_result, f"rcs_{setting}")

            current_car = Car()
            current_car.finorvin = vin
            current_car.licenseplate = car.get('licensePlate', vin)
            if not current_car.licenseplate.strip():
                current_car.licenseplate = vin
            current_car.features = features
            current_car.rcp_options = rcp_options
            current_car._last_message_received = int(round(time.time() * 1000))
            current_car._is_owner = car.get('isOwner')

            mercedes.client.cars.append(current_car)
            LOGGER.debug("Init - car added - %s", current_car.finorvin)

        handle = await mercedes.client.update_poll_states()

        if DEBUG_ADD_FAKE_VIN:
            debug_car = Car()
            debug_car.finorvin = "F123456789"
            debug_car.licenseplate = "U-DV 1234"
            debug_car._last_message_received = int(round(time.time() * 1000))
            mercedes.client.cars.append(debug_car)
            LOGGER.debug("Init - car added - %s", debug_car.finorvin)
            dev_reg = dr.async_get(hass)
            dev_reg.async_get_or_create(
                config_entry_id=config_entry.entry_id,
                connections=set(),
                identifiers={(DOMAIN, debug_car.finorvin)},
                manufacturer=ATTR_MB_MANUFACTURER,
                model="UDV 230 - Ugly Debug Vehicle",
                name=debug_car.licenseplate,
                sw_version="DEBUG",

            )


        hass.loop.create_task(mercedes.ws_connect())
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN] = mercedes


        async def refresh_access_token(call) -> None:
            await mercedes.client.oauth.async_get_cached_token()

        async def auxheat_configure(call) -> None:
            await mercedes.client.auxheat_configure(
                call.data.get(CONF_VIN),
                call.data.get("time_selection"),
                call.data.get("time_1"),
                call.data.get("time_2"),
                call.data.get("time_3")
            )

        async def auxheat_start(call) -> None:
            await mercedes.client.auxheat_start(call.data.get(CONF_VIN))

        async def auxheat_stop(call) -> None:
            await mercedes.client.auxheat_stop(call.data.get(CONF_VIN))

        async def doors_unlock(call) -> None:
            await mercedes.client.doors_unlock(call.data.get(CONF_VIN))

        async def doors_lock(call) -> None:
            await mercedes.client.doors_lock(call.data.get(CONF_VIN))

        async def engine_start(call) -> None:
            await mercedes.client.engine_start(call.data.get(CONF_VIN))

        async def engine_stop(call) -> None:
            await mercedes.client.engine_stop(call.data.get(CONF_VIN))

        async def sigpos_start(call) -> None:
            await mercedes.client.sigpos_start(call.data.get(CONF_VIN))

        async def sunroof_open(call) -> None:
            await mercedes.client.sunroof_open(call.data.get(CONF_VIN))

        async def sunroof_close(call) -> None:
            await mercedes.client.sunroof_close(call.data.get(CONF_VIN))

        async def preheat_start(call) -> None:
            if call.data.get("type", 0) == 0:
                await mercedes.client.preheat_start(call.data.get(CONF_VIN))
            else:
                await mercedes.client.preheat_start_immediate(call.data.get(CONF_VIN))

        async def preheat_start_departure_time(call) -> None:
            await mercedes.client.preheat_start_departure_time(call.data.get(CONF_VIN), call.data.get(CONF_TIME))

        async def preheat_stop(call) -> None:
            await mercedes.client.preheat_stop(call.data.get(CONF_VIN))

        async def windows_open(call) -> None:
            await mercedes.client.windows_open(call.data.get(CONF_VIN))

        async def windows_close(call) -> None:
            await mercedes.client.windows_close(call.data.get(CONF_VIN))

        async def send_route_to_car(call) -> None:
            await mercedes.client.send_route_to_car(
                call.data.get(CONF_VIN),
                call.data.get("title"),
                call.data.get("latitude"),
                call.data.get("longitude"),
                call.data.get("city"),
                call.data.get("postcode"),
                call.data.get("street"),
            )

        async def battery_max_soc_configure(call) -> None:
            await mercedes.client.battery_max_soc_configure(
                call.data.get(CONF_VIN),
                call.data.get("max_soc")
            )

        hass.services.async_register(
            DOMAIN, SERVICE_REFRESH_TOKEN_URL, refresh_access_token
        )
        hass.services.async_register(
            DOMAIN, SERVICE_AUXHEAT_CONFIGURE, auxheat_configure, schema=SERVICE_AUXHEAT_CONFIGURE_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_AUXHEAT_START, auxheat_start, schema=SERVICE_VIN_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_AUXHEAT_STOP, auxheat_stop, schema=SERVICE_VIN_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_BATTERY_MAX_SOC_CONFIGURE, battery_max_soc_configure, schema=SERVICE_BATTERY_MAX_SOC_CONFIGURE_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_DOORS_LOCK_URL, doors_lock, schema=SERVICE_VIN_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_DOORS_UNLOCK_URL, doors_unlock, schema=SERVICE_VIN_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_ENGINE_START, engine_start, schema=SERVICE_VIN_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_ENGINE_STOP, engine_stop, schema=SERVICE_VIN_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_PREHEAT_START, preheat_start, schema=SERVICE_PREHEAT_START_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_PREHEAT_START_DEPARTURE_TIME, preheat_start_departure_time, schema=SERVICE_VIN_TIME_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_PREHEAT_STOP, preheat_stop, schema=SERVICE_VIN_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_SEND_ROUTE, send_route_to_car, schema=SERVICE_SEND_ROUTE_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_SIGPOS_START, sigpos_start, schema=SERVICE_VIN_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_SUNROOF_OPEN, sunroof_open, schema=SERVICE_VIN_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_SUNROOF_CLOSE, sunroof_close, schema=SERVICE_VIN_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_WINDOWS_OPEN, windows_open, schema=SERVICE_VIN_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_WINDOWS_CLOSE, windows_close, schema=SERVICE_VIN_SCHEMA
        )

    except aiohttp.ClientError as err:
        LOGGER.warning("Can't connect to MB APIs; Retrying in background")
        raise ConfigEntryNotReady from err
    except WebsocketError as err:
        LOGGER.error("Config entry failed: %s", err)
        raise ConfigEntryNotReady from err

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    LOGGER.debug("Start unload component.")
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in MERCEDESME_COMPONENTS
            ]
        )
    )
    if unload_ok:
        if hass.data[DOMAIN]:
            del hass.data[DOMAIN]
    else:
        LOGGER.debug("unload not successful.")


    return unload_ok


class MercedesMeContext:
    """Context class for MercedesMe connections."""
    def __init__(self, hass, config_entry, region):
        self.config_entry = config_entry
        self.entry_setup_complete: bool = False
        self._hass = hass
        self._region = region
        self.client = Client(hass=hass, session=aiohttp_client.async_get_clientsession(hass), config_entry=config_entry, region=self._region)

    def on_dataload_complete(self):
        # Remove old cars from device_registry
        # device_list = async_entries_for_config_entry(self.dev_reg, self.config_entry.entry_id)
        #for device_entry in device_list:
        #    LOGGER.debug("Remove check: %s, %s", device_entry.id, list(device_entry.identifiers)[0][1])
        #    vin = list(device_entry.identifiers)[0][1]
        #    car_found = False
        #    for car in self.client.cars:
        #        if car.finorvin == vin:
        #            car_found = True
        #    if not car_found or vin in self.config_entry.options.get('excluded_cars', ""):
        #        LOGGER.info("Removing car from device registry: %s, %s", device_entry.name, vin)
        #        self.dev_reg.async_remove_device(device_entry.id)

        LOGGER.info("Car Load complete - start sensor creation")
        if not self.entry_setup_complete:
            for component in MERCEDESME_COMPONENTS:
                self._hass.async_create_task(
                    self._hass.config_entries.async_forward_entry_setup(
                        self.config_entry, component
                    )
                )

        self.entry_setup_complete = True

    async def ws_connect(self):
        """Register handlers and connect to the websocket."""
        await self.client.attempt_connect(self.on_dataload_complete)


class MercedesMeEntity(Entity):
    """Entity class for MercedesMe devices."""

    def __init__(
        self,
        hass,
        data,
        internal_name,
        sensor_config,
        vin,
        is_poll_sensor: bool = False
    ):
        """Initialize the MercedesMe entity."""
        self._hass = hass
        self._data = data
        self._vin = vin
        self._internal_name = internal_name
        self._sensor_config = sensor_config
        self._is_poll_sensor = is_poll_sensor

        self._state = None
        self._sensor_name = sensor_config[scf.DISPLAY_NAME.value]
        self._internal_unit = sensor_config[scf.UNIT_OF_MEASUREMENT.value]
        self._unit = sensor_config[scf.UNIT_OF_MEASUREMENT.value]
        self._feature_name = sensor_config[scf.OBJECT_NAME.value]
        self._object_name = sensor_config[scf.ATTRIBUTE_NAME.value]
        self._attrib_name = sensor_config[scf.VALUE_FIELD_NAME.value]
        self._extended_attributes = sensor_config[scf.EXTENDED_ATTRIBUTE_LIST.value]
        self._unique_id = slugify(f"{self._vin}_{self._internal_name}")
        self._car = next(car for car in self._data.client.cars
                         if car.finorvin == self._vin)

        self._licenseplate = self._car.licenseplate
        self._name = f"{self._licenseplate} {self._sensor_name}"

        #        conf = hass.data[DOMAIN].config
        #        if conf.get(CONF_CARS) is not None:
        #            for car_conf in conf.get(CONF_CARS):
        #                if car_conf.get(CONF_CARS_VIN) == vin:
        #                    custom_car_name = car_conf.get(CONF_NAME)
        #                    if custom_car_name != "_notset_":
        #                        self._name = f"{custom_car_name} {sensor_name}".strip()

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self) -> str:
        """Return the name of the sensor."""
        return self._unique_id

    @property
    def entity_category(self):
        """Return the entity_category of the sensor."""
        if not self._sensor_config[scf.ENTITY_CATEGORY.value] is None:
            if self._sensor_config[scf.ENTITY_CATEGORY.value] == "diagnostic":
                return EntityCategory.DIAGNOSTIC
            if self._sensor_config[scf.ENTITY_CATEGORY.value] == "config":
                return EntityCategory.CONFIG
        return None

    def device_retrieval_status(self):
        if self._sensor_name == "Car":
            return "VALID"

        return self._get_car_value(
            self._feature_name, self._object_name, "retrievalstatus", "error"
        )

    @property
    def device_info(self):
        """Return the device info."""

        return {
            "identifiers": {(DOMAIN, self._vin)}
        }

    @ property
    def device_class(self):
        return self._sensor_config[scf.DEVICE_CLASS.value]

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""

        state = {
            "car": self._licenseplate,
            "vin": self._vin,
        }

        state = self.extend_attributes(state)

        if self._attrib_name == "display_value":
            value = self._get_car_value(
                    self._feature_name,
                    self._object_name,
                    "value",
                    None
                )
            if value:
                state["original_value"] = value

        for item in["distance_unit", "retrievalstatus", "timestamp", "unit"]:
            value = self._get_car_value(
                    self._feature_name,
                    self._object_name,
                    item,
                    None
                )
            if value:
                state[item] = value if item != "timestamp" else datetime.fromtimestamp(int(value))

        if self._extended_attributes is not None:
            for attrib in self._extended_attributes:

                retrievalstatus = self._get_car_value(self._feature_name, attrib,
                                                      "retrievalstatus", "error")

                if retrievalstatus == "VALID":
                    state[attrib] = self._get_car_value(
                        self._feature_name, attrib, "display_value", None
                    )
                    if not state[attrib]:
                        state[attrib] = self._get_car_value(
                            self._feature_name, attrib, "value", "error"
                        )

                if retrievalstatus == "NOT_RECEIVED":
                    state[attrib] = "NOT_RECEIVED"
        return state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        if self._unit == LENGTH_KILOMETERS and \
           self._hass.config.units is US_CUSTOMARY_SYSTEM:
            return LENGTH_MILES
        else:
            return self._unit

    @property
    def icon(self):
        """Return the icon."""
        return self._sensor_config[scf.ICON.value]

    @property
    def should_poll(self):
        return self._is_poll_sensor


    def update(self):
        """Get the latest data and updates the states."""
        #LOGGER.("Updating %s", self._internal_name)

        #self._car = next(car for car in self._data.client.cars
        #                 if car.finorvin == self._vin)

        self._state = self._get_car_value(
            self._feature_name, self._object_name, self._attrib_name, "error"
        )

    def _get_car_value(self, feature, object_name, attrib_name, default_value):
        value = None

        if object_name:
            if not feature:
                value = getattr(
                    getattr(self._car, object_name, default_value),
                    attrib_name,
                    default_value,
                )
            else:
                value = getattr(
                    getattr(
                        getattr(self._car, feature, default_value),
                        object_name,
                        default_value,
                    ),
                    attrib_name,
                    default_value,
                )

        else:
            value = getattr(self._car, attrib_name, default_value)

        return value

    def update_callback(self):
        """Schedule a state update."""
        self.schedule_update_ha_state(True)

    async def async_added_to_hass(self):
        """Add callback after being added to hass.

        Show latest data after startup.
        """
        self._car.add_update_listener(self.update_callback)
        self.async_schedule_update_ha_state(True)

    async def async_will_remove_from_hass(self):
        """Entity being removed from hass."""
        self._car.remove_update_callback(self.update_callback)

    def extend_attributes(self, extended_attributes):


        def default_extender(extended_attributes):
            return extended_attributes

        def starterBatteryState(extended_attributes):
            extended_attributes["value_short"] = starterBatteryState_values.get(self._state,["unknown", "unknown"])[0]
            extended_attributes["value_description"] = starterBatteryState_values.get(self._state,["unknown", "unknown"])[1]
            return extended_attributes

        def ignitionstate_state(extended_attributes):
            extended_attributes["value_short"] = ignitionstate_values.get(self._state,["unknown", "unknown"])[0]
            extended_attributes["value_description"] = ignitionstate_values.get(self._state,["unknown", "unknown"])[1]
            return extended_attributes

        def auxheatstatus_state(extended_attributes):
            extended_attributes["value_short"] = auxheatstatus_values.get(self._state,["unknown", "unknown"])[0]
            extended_attributes["value_description"] = auxheatstatus_values.get(self._state,["unknown", "unknown"])[1]
            return extended_attributes

        attribut_extender ={
            "starterBatteryState": starterBatteryState,
            "ignitionstate": ignitionstate_state,
            "auxheatstatus": auxheatstatus_state,
        }

        ignitionstate_values = {
            "0" :["lock", "Ignition lock"],
            "1" :["off", "Ignition off"],
            "2" :["accessory", "Ignition accessory"],
            "4" :["on", "Ignition on"],
            "5" :["start", "Ignition start"],
        }
        starterBatteryState_values = {
            "0" :["green", "Vehicle ok"],
            "1" :["yellow", "Battery partly charged"],
            "2" :["red", "Vehicle not available"],
            "3" :["serviceDisabled", "Remote service disabled"],
            "4" :["vehicleNotAvalable", "Vehicle no longer available"],
        }

        auxheatstatus_values = {
            "0" :["inactive", "inactive"],
            "1" :["normal heating", "normal heating"],
            "2" :["normal ventilation", "normal ventilation"],
            "3" :["manual heating", "manual heating"],
            "4" :["post heating", "post heating"],
            "5" :["post ventilation", "post ventilation"],
            "6" :["auto heating", "auto heating"],
        }

        func = attribut_extender.get(self._internal_name, default_extender)
        return func(extended_attributes)
