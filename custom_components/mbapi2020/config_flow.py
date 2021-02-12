"""Config flow for HVV integration."""
import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_OFFSET, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import aiohttp_client
import homeassistant.helpers.config_validation as cv

from .const import (  # pylint:disable=unused-import
    CONF_ALLOWED_REGIONS,
    CONF_COUNTRY_CODE,
    CONF_DEBUG_FILE_SAVE,
    CONF_EXCLUDED_CARS,
    CONF_FT_DISABLE_CAPABILITY_CHECK,
    CONF_LOCALE,
    CONF_PIN,
    CONF_REGION,
    DOMAIN,
    DEFAULT_CACHE_PATH,
    DEFAULT_LOCALE,
    DEFAULT_COUNTRY_CODE,
    VERIFY_SSL
)
from .client import Client
from .errors import MbapiError

_LOGGER = logging.getLogger(__name__)

SCHEMA_STEP_USER = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_REGION): vol.In(CONF_ALLOWED_REGIONS)
    }
)

SCHEMA_STEP_PIN = vol.Schema({vol.Required(CONF_PASSWORD): str})


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for mbapi2020."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Initialize component."""


    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            session = aiohttp_client.async_get_clientsession(self.hass, VERIFY_SSL)

            client = Client(session=session, hass=self.hass, region=user_input[CONF_REGION])
            try:
                result = await client.oauth.request_pin(user_input[CONF_USERNAME])
            except MbapiError as error:
                errors = error                

            if not errors:
                self.data = user_input
                return await self.async_step_pin()
            else:
                _LOGGER.error(f"Request Pin Error: {errors}")

        return self.async_show_form(
            step_id="user", data_schema=SCHEMA_STEP_USER, errors= "Error unknow" #errors
        )

    async def async_step_pin(self, user_input=None):
        """Handle the step where the user inputs his/her station."""

        errors = {}

        if user_input is not None:

            pin = user_input[CONF_PASSWORD]

            session = aiohttp_client.async_get_clientsession(self.hass, VERIFY_SSL)

            client = Client(session=session, hass=self.hass, region=self.data[CONF_REGION])
            try:
                result = await client.oauth.request_access_token(self.data[CONF_USERNAME], pin)
            except MbapiError as error:
                _LOGGER.error(f"Request Token Error: {errors}")
                errors = error

            if not errors:
                _LOGGER.debug("token received")
                self.data["token"] = result
                return self.async_create_entry(title=DOMAIN, data=self.data)

        return self.async_show_form(step_id="pin", data_schema=SCHEMA_STEP_PIN, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get options flow."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow handler."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry
        self.options = dict(config_entry.options)

    async def async_step_init(self, user_input=None):
        """Manage the options."""

        if user_input is not None:
            if user_input[CONF_PIN] == "0":
                user_input[CONF_PIN] = ""
            self.options.update(user_input)
            return self.async_create_entry(title=DOMAIN, data=self.options)

        options = self.config_entry.options
        country_code = options.get(CONF_COUNTRY_CODE, DEFAULT_COUNTRY_CODE)
        locale = options.get(CONF_LOCALE, DEFAULT_LOCALE)
        excluded_cars = options.get(CONF_EXCLUDED_CARS, "")
        pin = options.get(CONF_PIN,"")
        cap_check_disabled = options.get(CONF_FT_DISABLE_CAPABILITY_CHECK, False)
        save_debug_files = options.get(CONF_DEBUG_FILE_SAVE, False)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_COUNTRY_CODE, default=country_code): str,
                    vol.Optional(CONF_LOCALE, default=locale): str,
                    vol.Optional(CONF_EXCLUDED_CARS, default=excluded_cars): str,
                    vol.Optional(CONF_PIN, default=pin): str,
                    vol.Optional(CONF_FT_DISABLE_CAPABILITY_CHECK, default=cap_check_disabled): bool,
                    vol.Optional(CONF_DEBUG_FILE_SAVE, default=save_debug_files): bool
                }
            )
        )
