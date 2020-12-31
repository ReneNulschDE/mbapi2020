"""Config flow for HVV integration."""
import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_OFFSET, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import aiohttp_client
import homeassistant.helpers.config_validation as cv

from .const import (  # pylint:disable=unused-import
    DOMAIN,
    DEFAULT_CACHE_PATH,
)
from .client import Client
from .errors import MbapiError

verify_ssl = False

_LOGGER = logging.getLogger(__name__)

SCHEMA_STEP_USER = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
    }
)

SCHEMA_STEP_PIN = vol.Schema({vol.Required(CONF_PASSWORD): str})

SCHEMA_STEP_OPTIONS = vol.Schema(
    {
        vol.Required(CONF_PASSWORD): str
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HVV."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Initialize component."""

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            session = aiohttp_client.async_get_clientsession(self.hass, verify_ssl)

            client = Client(session=session, hass=self.hass)
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

            # TODO:
            # - Web Request to initiate the token send

            pin = user_input[CONF_PASSWORD]

            session = aiohttp_client.async_get_clientsession(self.hass)

            client = Client(session=session, hass=self.hass)
            try:
                result = await client.oauth.request_access_token(self.data[CONF_USERNAME], pin)
                _LOGGER.debug(result)
            except MbapiError as error:
                _LOGGER.error(f"Request Token Error: {errors}")
                errors = error

            if not errors:
                _LOGGER.debug(result)
                self.data["token"] = result
                return self.async_create_entry(title=DOMAIN, data=self.data)

        return self.async_show_form(step_id="pin", data_schema=SCHEMA_STEP_PIN, errors=errors)


# TODO: Options for Locales, excluded Cars, Car renaming
    # @staticmethod
    # @callback
    # def async_get_options_flow(config_entry):
    #     """Get options flow."""
    #     return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow handler."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry
        self.options = dict(config_entry.options)

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        errors = {}

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional("country_code", default="EN"): str,
                    vol.Optional("locale", default="de-DE"): str,
                    vol.Optional("excluded_cars", default=""): str
                }
            ),
            errors=errors,
        )
