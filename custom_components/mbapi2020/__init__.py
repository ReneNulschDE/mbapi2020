"""The MercedesME 2020 integration."""
import asyncio
import time

import voluptuous as vol

from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STOP,
    LENGTH_KILOMETERS,
    LENGTH_MILES,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import (
    aiohttp_client,
    config_validation as cv,
    discovery
)
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_call_later
from homeassistant.util import slugify

from .const import (
    ATTR_MB_MANUFACTURER,
    CONF_REGION,
    CONF_VIN,
    CONF_TIME,
    DOMAIN,
    DATA_CLIENT,
    DEFAULT_CACHE_PATH,
    LOGGER,
    MERCEDESME_COMPONENTS,
    SERVICE_REFRESH_TOKEN_URL,
    SERVICE_DOORS_LOCK_URL,
    SERVICE_DOORS_UNLOCK_URL,
    SERVICE_ENGINE_START,
    SERVICE_ENGINE_STOP,
    SERVICE_PREHEAT_START,
    SERVICE_PREHEAT_START_DEPARTURE_TIME,
    SERVICE_PREHEAT_STOP,
    SERVICE_SUNROOF_CLOSE,
    SERVICE_SUNROOF_OPEN,
    SERVICE_WINDOWS_CLOSE,
    SERVICE_WINDOWS_OPEN,
    SERVICE_VIN_SCHEMA,
    SERVICE_VIN_TIME_SCHEMA,
    VERIFY_SSL,
    Sensor_Config_Fields as scf

)
from .car import Car
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

        # Todo: Find the right way to migrate old configs
        region = config_entry.data.get(CONF_REGION, None)
        if region is None:
            region = "Europe"

        mercedes = MercedesMeContext(
            hass,
            config_entry,
            region=region
        )

        masterdata = await mercedes.client.api.get_user_info()
        mercedes.client._write_debug_json_output(masterdata, "md")
        for car in masterdata:

            # Car is excluded, we do not add this
            if car.get('fin') in config_entry.options.get('excluded_cars', ""):
                continue

            dev_reg = await hass.helpers.device_registry.async_get_registry()
            dev_reg.async_get_or_create(
                config_entry_id=config_entry.entry_id,
                connections=set(),
                identifiers={(DOMAIN, car.get('fin'))},
                manufacturer=ATTR_MB_MANUFACTURER,
                model=car.get('salesRelatedInformation').get('baumuster').get('baumusterDescription'),
                name=car.get('licensePlate', car.get('fin')),
                sw_version=car.get('starArchitecture'),

            )

            c = Car()
            c.finorvin = car.get('fin')
            c.licenseplate = car.get('licensePlate', car.get('fin'))
            c._last_message_received = int(round(time.time() * 1000))
            mercedes.client.cars.append(c)
            LOGGER.debug("Init - car added - %s", c.finorvin)


        if DEBUG_ADD_FAKE_VIN:
            c = Car()
            c.finorvin = "F123456789"
            c.licenseplate = "U-DV 1234"
            c._last_message_received = int(round(time.time() * 1000))
            mercedes.client.cars.append(c)
            LOGGER.debug("Init - car added - %s", c.finorvin)
            dev_reg = await hass.helpers.device_registry.async_get_registry()
            dev_reg.async_get_or_create(
                config_entry_id=config_entry.entry_id,
                connections=set(),
                identifiers={(DOMAIN, c.finorvin)},
                manufacturer=ATTR_MB_MANUFACTURER,
                model="UDV 230 - Ugly Debug Vehicle",
                name=c.licenseplate,
                sw_version="DEBUG",

            )


        hass.loop.create_task(mercedes.ws_connect())
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN] = mercedes

        async def refresh_access_token(call) -> None:
            await mercedes.client.oauth.async_get_cached_token()

        async def doors_unlock(call) -> None:
            await mercedes.client.doors_unlock(call.data.get(CONF_VIN))

        async def doors_lock(call) -> None:
            await mercedes.client.doors_lock(call.data.get(CONF_VIN))

        async def engine_start(call) -> None:
            await mercedes.client.engine_start(call.data.get(CONF_VIN))

        async def engine_stop(call) -> None:
            await mercedes.client.engine_stop(call.data.get(CONF_VIN))

        async def sunroof_open(call) -> None:
            await mercedes.client.sunroof_open(call.data.get(CONF_VIN))

        async def sunroof_close(call) -> None:
            await mercedes.client.sunroof_close(call.data.get(CONF_VIN))

        async def preheat_start(call) -> None:
            await mercedes.client.preheat_start(call.data.get(CONF_VIN))

        async def preheat_start_departure_time(call) -> None:
            await mercedes.client.preheat_start_departure_time(call.data.get(CONF_VIN), call.data.get(CONF_TIME))
            
        async def preheat_stop(call) -> None:
            await mercedes.client.preheat_stop(call.data.get(CONF_VIN))

        async def windows_open(call) -> None:
            await mercedes.client.windows_open(call.data.get(CONF_VIN))

        async def windows_close(call) -> None:
            await mercedes.client.windows_close(call.data.get(CONF_VIN))

        hass.services.async_register(
            DOMAIN, SERVICE_REFRESH_TOKEN_URL, refresh_access_token
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
            DOMAIN, SERVICE_PREHEAT_START, preheat_start, schema=SERVICE_VIN_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_PREHEAT_START_DEPARTURE_TIME, preheat_start_departure_time, schema=SERVICE_VIN_TIME_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_PREHEAT_STOP, preheat_stop, schema=SERVICE_VIN_SCHEMA
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


    except WebsocketError as err:
        LOGGER.error("Config entry failed: %s", err)
        raise ConfigEntryNotReady from err

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
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
            hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class MercedesMeContext:

    def __init__(self, hass, config_entry, region):
        self._config_entry = config_entry
        self._entry_setup_complete: bool = False
        self._hass = hass
        self._region = region
        self.client = Client(hass=hass, session=aiohttp_client.async_get_clientsession(hass), config_entry=config_entry, region=self._region)

    def on_dataload_complete(self):
        LOGGER.info("Car Load complete - start sensor creation")

        if not self._entry_setup_complete:
            for component in MERCEDESME_COMPONENTS:
                self._hass.async_create_task(
                    self._hass.config_entries.async_forward_entry_setup(
                        self._config_entry, component
                    )
                )

        self._entry_setup_complete = True

    async def ws_connect(self):
        """Register handlers and connect to the websocket."""
        await self.client._attempt_connect(self.on_dataload_complete)


class MercedesMeEntity(Entity):
    """Entity class for MercedesMe devices."""

    def __init__(
        self,
        hass,
        data,
        internal_name,
        sensor_config,
        vin
    ):
        """Initialize the MercedesMe entity."""
        self._hass = hass
        self._data = data
        self._vin = vin
        self._internal_name = internal_name
        self._sensor_config = sensor_config

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
    def device_state_attributes(self):
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
           not self._hass.config.units.is_metric:
            return LENGTH_MILES
        else:
            return self._unit

    @property
    def icon(self):
        """Return the icon."""
        return self._sensor_config[scf.ICON.value] 

    @property
    def should_poll(self):
        return False


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


        attribut_extender ={
            "starterBatteryState": starterBatteryState,
            "ignitionstate": ignitionstate_state
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

        func = attribut_extender.get(self._internal_name, default_extender)
        return func(extended_attributes)



   
