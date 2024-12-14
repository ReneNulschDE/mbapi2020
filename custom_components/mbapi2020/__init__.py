"""The MercedesME 2020 integration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import datetime
import time
from typing import Any

import aiohttp
import voluptuous as vol

from custom_components.mbapi2020.car import Car, CarAttribute, RcpOptions
from custom_components.mbapi2020.const import (
    ATTR_MB_MANUFACTURER,
    CONF_ENABLE_CHINA_GCJ_02,
    DOMAIN,
    LOGGER,
    LOGIN_BASE_URI,
    MERCEDESME_COMPONENTS,
    UNITS,
    SensorConfigFields as scf,
)
from custom_components.mbapi2020.coordinator import MBAPI2020DataUpdateCoordinator
from custom_components.mbapi2020.errors import WebsocketError
from custom_components.mbapi2020.helper import LogHelper as loghelper
from custom_components.mbapi2020.services import setup_services
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up MBAPI2020."""
    LOGGER.debug("Start async_setup - Initializing services.")
    hass.data.setdefault(DOMAIN, {})
    setup_services(hass)

    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Set up MercedesME 2020 from a config entry."""
    LOGGER.debug("Start async_setup_entry.")

    try:
        coordinator = MBAPI2020DataUpdateCoordinator(hass, config_entry)
        hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = coordinator

        await coordinator.client.set_rlock_mode()

        try:
            token_info = await coordinator.client.oauth.async_get_cached_token()
        except aiohttp.ClientError as err:
            LOGGER.warning("Can not connect to MB OAuth API %s. Will try again.", LOGIN_BASE_URI)
            LOGGER.debug("Can not connect to MB OAuth API %s. Will try again. %s", LOGIN_BASE_URI, err)
            raise ConfigEntryNotReady from err

        if token_info is None:
            LOGGER.error("Authentication failed. Please reauthenticate.")
            raise ConfigEntryAuthFailed

        masterdata = await coordinator.client.webapi.get_user_info()
        hass.async_add_executor_job(coordinator.client.write_debug_json_output, masterdata, "md", True)

        for car in masterdata.get("assignedVehicles"):
            # Check if the car has a separate VIN key, if not, use the FIN.
            vin = car.get("vin")
            if vin is None:
                vin = car.get("fin")
                LOGGER.debug(
                    "VIN not found in masterdata. Used FIN %s instead.",
                    loghelper.Mask_VIN(vin),
                )

            # Car is excluded, we do not add this
            if vin in config_entry.options.get("excluded_cars", ""):
                continue

            features: dict[str, bool] = {}
            vehicle_information: dict = {}

            try:
                car_capabilities = await coordinator.client.webapi.get_car_capabilities(vin)
                hass.async_add_executor_job(
                    coordinator.client.write_debug_json_output,
                    car_capabilities,
                    f"cai-{loghelper.Mask_VIN(vin)}-",
                    True,
                )
                if car_capabilities and "features" in car_capabilities:
                    features.update(car_capabilities["features"])
                if car_capabilities and "vehicle" in car_capabilities:
                    vehicle_information = car_capabilities["vehicle"]
            except aiohttp.ClientError:
                # For some cars a HTTP401 is raised when asking for capabilities, see github issue #83
                LOGGER.info(
                    "Car Capabilities not available for the car with VIN %s.",
                    loghelper.Mask_VIN(vin),
                )

            try:
                capabilities = await coordinator.client.webapi.get_car_capabilities_commands(vin)
                hass.async_add_executor_job(
                    coordinator.client.write_debug_json_output,
                    capabilities,
                    f"ca-{loghelper.Mask_VIN(vin)}-",
                    True,
                )
                if capabilities:
                    for feature in capabilities.get("commands"):
                        features[feature.get("commandName")] = bool(feature.get("isAvailable"))
                        if feature.get("commandName", "") == "ZEV_PRECONDITION_CONFIGURE_SEATS":
                            capabilityInformation = feature.get("capabilityInformation", None)
                            if capabilityInformation and len(capabilityInformation) > 0:
                                features[feature.get("capabilityInformation")[0]] = bool(feature.get("isAvailable"))
            except aiohttp.ClientError:
                # For some cars a HTTP401 is raised when asking for capabilities, see github issue #83
                # We just ignore the capabilities
                LOGGER.info(
                    "Command Capabilities not available for the car with VIN %s. Make sure you disable the capability check in the option of this component.",
                    loghelper.Mask_VIN(vin),
                )

            rcp_options = RcpOptions()
            rcp_supported = False  # await coordinator.client.webapi.is_car_rcp_supported(vin)
            LOGGER.debug("RCP supported for car %s: %s", loghelper.Mask_VIN(vin), rcp_supported)
            setattr(rcp_options, "rcp_supported", CarAttribute(rcp_supported, "VALID", 0))
            # rcp_supported = False
            # if rcp_supported:
            #     rcp_supported_settings = await coordinator.client.webapi.get_car_rcp_supported_settings(vin)
            #     if rcp_supported_settings:
            #         hass.async_add_executor_job(
            #             coordinator.client.write_debug_json_output,
            #             rcp_supported_settings,
            #             "rcs",
            #         )
            #         if rcp_supported_settings.get("data"):
            #             if rcp_supported_settings.get("data").get("attributes"):
            #                 if rcp_supported_settings.get("data").get("attributes").get("supportedSettings"):
            #                     LOGGER.debug(
            #                         "RCP supported settings: %s",
            #                         str(rcp_supported_settings.get("data").get("attributes").get("supportedSettings")),
            #                     )
            #                     setattr(
            #                         rcp_options,
            #                         "rcp_supported_settings",
            #                         CarAttribute(
            #                             rcp_supported_settings.get("data").get("attributes").get("supportedSettings"),
            #                             "VALID",
            #                             0,
            #                         ),
            #                     )

            #                     for setting in (
            #                         rcp_supported_settings.get("data").get("attributes").get("supportedSettings")
            #                     ):
            #                         setting_result = await coordinator.client.webapi.get_car_rcp_settings(vin, setting)
            #                         if setting_result is not None:
            #                             hass.async_add_executor_job(
            #                                 coordinator.client.write_debug_json_output,
            #                                 setting_result,
            #                                 f"rcs_{setting}",
            #                             )

            current_car = Car(vin)
            current_car.licenseplate = car.get("licensePlate", vin)
            current_car.baumuster_description = (
                car.get("salesRelatedInformation", "").get("baumuster", "").get("baumusterDescription", "")
            )
            if not current_car.licenseplate.strip():
                current_car.licenseplate = vin
            current_car.features = features
            current_car.vehicle_information = vehicle_information
            current_car.masterdata = car
            current_car.rcp_options = rcp_options
            current_car.last_message_received = int(round(time.time() * 1000))
            current_car.is_owner = car.get("isOwner")

            coordinator.client.cars[vin] = current_car
            # await coordinator.client.update_poll_states(vin)

            LOGGER.debug("Init - car added - %s", loghelper.Mask_VIN(current_car.finorvin))

        await coordinator.async_config_entry_first_refresh()

        # !! Use case: Smart cars have no masterdata entries
        # we create the websocket to check if this channel has some data, car creation is done in the client module
        # if len(coordinator.client.cars) == 0:
        hass.loop.create_task(coordinator.ws_connect())

    except aiohttp.ClientError as err:
        LOGGER.warning("Can't connect to MB APIs; Retrying in background: %s", err)
        raise ConfigEntryNotReady from err
    except WebsocketError as err:
        LOGGER.error("Websocket error: %s", err)
        raise ConfigEntryNotReady from err

    retry_counter: int = 0
    while not coordinator.entry_setup_complete:
        # async websocket data load not complete, wait 0.5 seconds or break up after 60 checks (30sec)
        if retry_counter == 60 and coordinator.client.websocket.account_blocked:
            LOGGER.warning("Account is blocked. Reload will happen after unblock at midnight (GMT).")
            break
        if retry_counter == 60 and not coordinator.client.account_blocked:
            LOGGER.warning(
                "No car information received via websocket for this account. Check the MB website with the same account."
            )
            break

        await asyncio.sleep(0.5)
        retry_counter += 1

    return True


async def config_entry_update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Update listener, called when the config entry options are changed."""
    LOGGER.debug("Start config_entry_update async_reload")
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Unload mbapi2020 Home config entry."""
    LOGGER.debug("Start unload component.")
    unload_ok = False

    if len(hass.data[DOMAIN][config_entry.entry_id].client.cars) > 0:
        hass.data[DOMAIN][config_entry.entry_id].client.websocket._reconnectwatchdog.cancel()
        result = await hass.data[DOMAIN][config_entry.entry_id].client.websocket.async_stop()
        hass.data[DOMAIN][config_entry.entry_id].client.websocket = None
        if unload_ok := await hass.config_entries.async_unload_platforms(config_entry, MERCEDESME_COMPONENTS):
            del hass.data[DOMAIN][config_entry.entry_id]
    else:
        # No cars loaded, we destroy the config entry only
        del hass.data[DOMAIN][config_entry.entry_id]
        unload_ok = True

    LOGGER.debug("unload result: %s", unload_ok)
    return unload_ok


@dataclass(frozen=True, kw_only=True)
class MercedesMeEntityDescription(EntityDescription):
    """Configuration class for MercedesMe entities."""

    attributes: list[str] | None = None
    check_capability_fn: Callable[[Car], Callable[[], Coroutine[Any, Any, bool]]]


class MercedesMeEntity(CoordinatorEntity[MBAPI2020DataUpdateCoordinator], Entity):
    """Entity class for MercedesMe devices."""

    _attr_has_entity_name = True

    def __init__(
        self,
        internal_name: str,
        config: list | EntityDescription,
        vin: str,
        coordinator: MBAPI2020DataUpdateCoordinator,
        should_poll: bool = False,
    ) -> None:
        """Initialize the MercedesMe entity."""

        self._hass = coordinator.hass
        self._coordinator = coordinator
        self._vin = vin
        self._internal_name = internal_name
        self._sensor_config = config
        self._car = self._coordinator.client.cars[self._vin]
        self._feature_name = None
        self._object_name = None
        self._attrib_name = None

        self._flip_result = False
        self._state = None

        # Temporary workaround: If PR get's approved, all entity types should be migrated to the new config classes
        if isinstance(config, EntityDescription):
            self._attributes = config.attributes
            self.entity_description = config
        else:
            self._feature_name = config[scf.OBJECT_NAME.value]
            self._object_name = config[scf.ATTRIBUTE_NAME.value]
            self._attrib_name = config[scf.VALUE_FIELD_NAME.value]
            self._flip_result = config[scf.FLIP_RESULT.value]
            self._attr_device_class = self._sensor_config[scf.DEVICE_CLASS.value]
            self._attr_icon = self._sensor_config[scf.ICON.value]
            self._attr_state_class = self._sensor_config[scf.STATE_CLASS.value]
            self._attr_entity_category = self._sensor_config[scf.ENTITY_CATEGORY.value]
            self._attributes = self._sensor_config[scf.EXTENDED_ATTRIBUTE_LIST.value]
            self._attr_native_unit_of_measurement = self.unit_of_measurement
            self._use_chinese_location_data: bool = self._coordinator.config_entry.options.get(
                CONF_ENABLE_CHINA_GCJ_02, False
            )
            self._attr_translation_key = self._internal_name.lower()
            self._attr_name = config[scf.DISPLAY_NAME.value]
            self._name = f"{self._car.licenseplate} {config[scf.DISPLAY_NAME.value]}"

        self._attr_device_info = {"identifiers": {(DOMAIN, self._vin)}}
        self._attr_should_poll = should_poll
        self._attr_unique_id = slugify(f"{self._vin}_{self._internal_name}")

        super().__init__(coordinator)

    def device_retrieval_status(self):
        """Return the retrieval_status of the sensor."""
        if self._internal_name == "car":
            return "VALID"

        return self._get_car_value(self._feature_name, self._object_name, "retrievalstatus", "error")

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""

        state = {"car": self._car.licenseplate, "vin": self._vin}

        if self._attrib_name == "display_value":
            value = self._get_car_value(self._feature_name, self._object_name, "value", None)
            if value:
                state["original_value"] = value

        for item in ["retrievalstatus", "timestamp", "unit"]:
            value = self._get_car_value(self._feature_name, self._object_name, item, None)
            if value:
                state[item] = value if item != "timestamp" else datetime.fromtimestamp(int(value))

        if self._attributes is not None:
            for attrib in sorted(self._attributes):
                if "." in attrib:
                    object_name = attrib.split(".")[0]
                    attrib_name = attrib.split(".")[1]
                else:
                    object_name = self._feature_name
                    attrib_name = attrib
                retrievalstatus = self._get_car_value(object_name, attrib_name, "retrievalstatus", "error")

                if retrievalstatus == "VALID":
                    state[attrib_name] = self._get_car_value(object_name, attrib_name, "display_value", None)
                    if not state[attrib_name]:
                        state[attrib_name] = self._get_car_value(object_name, attrib_name, "value", "error")

                if retrievalstatus in ["NOT_RECEIVED"]:
                    state[attrib_name] = "NOT_RECEIVED"
        return state

    @property
    def device_info(self) -> DeviceInfo:
        """Device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._vin)},
            manufacturer=ATTR_MB_MANUFACTURER,
            model=self._car.baumuster_description,
            name=self._car.licenseplate,
            sw_version=f"{self._car.vehicle_information.get('headUnitSoftwareVersion', '')} - {self._car.vehicle_information.get('headUnitType', '')}",
            hw_version=f"{self._car.vehicle_information.get('starArchitecture', '')} - {self._car.vehicle_information.get('tcuType', '')}",
        )

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""

        if "unit" in self.extra_state_attributes:
            reported_unit: str = self.extra_state_attributes["unit"]
            if reported_unit.upper() in UNITS:
                return UNITS[reported_unit.upper()]

            LOGGER.warning(
                "Unknown unit %s found. Please report via issue https://www.github.com/renenulschde/mbapi2020/issues",
                reported_unit,
            )
            return reported_unit

        if isinstance(self._sensor_config, EntityDescription):
            return None
        return self._sensor_config[scf.UNIT_OF_MEASUREMENT.value]

    def update(self):
        """Get the latest data and updates the states."""
        if not self.enabled:
            return

        if isinstance(self._sensor_config, EntityDescription):
            self._mercedes_me_update()
        else:
            self._state = self._get_car_value(self._feature_name, self._object_name, self._attrib_name, "error")
            self.async_write_ha_state()

    def _mercedes_me_update(self) -> None:
        """Update Mercedes Me entity."""
        raise NotImplementedError

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

    def pushdata_update_callback(self):
        """Schedule a state update."""
        self.update()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.update()

    async def async_added_to_hass(self):
        """Add callback after being added to hass.

        Show latest data after startup.
        """
        await super().async_added_to_hass()
        if not self._attr_should_poll:
            self._car.add_update_listener(self.pushdata_update_callback)

        self.async_schedule_update_ha_state(True)
        self._handle_coordinator_update()

    async def async_will_remove_from_hass(self):
        """Entity being removed from hass."""
        await super().async_will_remove_from_hass()
        self._car.remove_update_callback(self.pushdata_update_callback)
