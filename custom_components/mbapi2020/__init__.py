"""The MercedesME 2020 integration."""
import asyncio

import voluptuous as vol

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
    DOMAIN,
    DATA_CLIENT,
    DEFAULT_CACHE_PATH,
    MERCEDESME_COMPONENTS,
    VERIFY_SSL,
    LOGGER
)
from .car import Car
from .client import Client
from .errors import WebsocketError

CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the MercedesME 2020 component."""

    if DOMAIN not in config:
        return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Set up MercedesME 2020 from a config entry."""

    try:
        mercedes = MercedesMeContext(
            hass,
            config_entry
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
            mercedes.client.cars.append(c)


        hass.loop.create_task(mercedes.ws_connect())
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN] = mercedes



    except WebsocketError as err:
        LOGGER.error("Config entry failed: %s", err)
        raise ConfigEntryNotReady from err

    async def _async_disconnect_websocket(*_):
        await mercedes.ws_disconnect()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_disconnect_websocket)

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

    def __init__(self, hass, config_entry):
        self._config_entry = config_entry
        self._entry_setup_complete = False
        self._hass = hass
        self.client = Client(hass=hass, session=aiohttp_client.async_get_clientsession(hass), config_entry=config_entry)

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

    async def ws_disconnect(self):
        """Disconnect from the websocket."""
        await self.client.websocket.disconnect()


class MercedesMeEntity(Entity):
    """Entity class for MercedesMe devices."""

    def __init__(
        self,
        hass,
        data,
        internal_name,
        sensor_name,
        vin,
        unit,
        licenseplate,
        feature_name,
        object_name,
        attrib_name,
        extended_attributes,
        **kwargs,
    ):
        """Initialize the MercedesMe entity."""
        self._hass = hass
        self._data = data
        self._state = False
        self._name = f"{licenseplate} {sensor_name}"
        self._internal_name = internal_name
        self._internal_unit = unit
        self._sensor_name = sensor_name
        self._unit = unit
        self._vin = vin
        self._feature_name = feature_name
        self._object_name = object_name
        self._attrib_name = attrib_name
        self._licenseplate = licenseplate
        self._extended_attributes = extended_attributes
        self._kwargs = kwargs
        self._unique_id = slugify(f"{self._vin}_{self._internal_name}")
        self._car = next(car for car in self._data.client.cars
                         if car.finorvin == self._vin)

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
        return self._get_car_value(
            self._feature_name, self._object_name, "retrievalstatus", "error"
        )

    @property
    def device_info(self):
        """Return the device info."""

        return {
            "identifiers": {(DOMAIN, self._vin)}
        }

    def update(self):
        """Get the latest data and updates the states."""
        #LOGGER.("Updating %s", self._internal_name)

        self._car = next(car for car in self._data.client.cars
                         if car.finorvin == self._vin)

        new_state = self._get_car_value(
            self._feature_name, self._object_name, self._attrib_name, "error"
        )

        if new_state:
            if new_state != self._state:
                self._state = new_state
                LOGGER.debug("Updated %s %s", self._internal_name, self._state)


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

    @property
    def device_state_attributes(self):
        """Return the state attributes."""

        state = {
            "car": self._licenseplate,
            "retrievalstatus": self._get_car_value(
                self._feature_name,
                self._object_name,
                "retrievalstatus",
                "error"
            ),
        }
        if self._extended_attributes is not None:
            for attrib in self._extended_attributes:

                retrievalstatus = self._get_car_value(self._feature_name, attrib,
                                                      "retrievalstatus", "error")

                if retrievalstatus == "VALID":
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
