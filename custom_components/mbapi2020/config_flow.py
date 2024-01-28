"""Config flow for mbapi2020 integration."""
from __future__ import annotations

import os
import uuid

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import STORAGE_DIR

from .client import Client
from .const import (
    CONF_ALLOWED_REGIONS,
    CONF_COUNTRY_CODE,
    CONF_DEBUG_FILE_SAVE,
    CONF_DELETE_AUTH_FILE,
    CONF_ENABLE_CHINA_GCJ_02,
    CONF_EXCLUDED_CARS,
    CONF_FT_DISABLE_CAPABILITY_CHECK,
    CONF_LOCALE,
    CONF_PIN,
    CONF_REGION,
    DEFAULT_COUNTRY_CODE,
    DEFAULT_LOCALE,
    DOMAIN,
    LOGGER,
    TOKEN_FILE_PREFIX,
    VERIFY_SSL,
)
from .errors import MbapiError

SCHEMA_STEP_USER = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_REGION): vol.In(CONF_ALLOWED_REGIONS),
    }
)

SCHEMA_STEP_PIN = vol.Schema({vol.Required(CONF_PASSWORD): str})


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for mbapi2020."""

    VERSION = 1

    def __init__(self):
        """Initialize component."""
        self._existing_entry = None
        self.data = None
        self.reauth_mode = False

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            new_config_entry: config_entries.ConfigEntry = await self.async_set_unique_id(
                f"{user_input[CONF_USERNAME]}"
            )

            if not self.reauth_mode:
                self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass, VERIFY_SSL)
            nonce = str(uuid.uuid4())
            user_input["nonce"] = nonce

            LOGGER.warning(new_config_entry.as_dict())
            client = Client(self.hass, session, new_config_entry, region=user_input[CONF_REGION])
            try:
                await client.oauth.request_pin(user_input[CONF_USERNAME], nonce)
            except MbapiError as error:
                errors = error

            if not errors:
                self.data = user_input
                return await self.async_step_pin()

            LOGGER.error("Request PIN error: %s", errors)

        return self.async_show_form(step_id="user", data_schema=SCHEMA_STEP_USER, errors={"Unknown error": str(errors)})

    async def async_step_pin(self, user_input=None):
        """Handle the step where the user inputs his/her station."""

        errors = {}

        if user_input is not None:
            pin = user_input[CONF_PASSWORD]
            nonce = self.data["nonce"]
            session = async_get_clientsession(self.hass, VERIFY_SSL)

            client = Client(self.hass, session, None, self.data[CONF_REGION])
            try:
                result = await client.oauth.request_access_token(self.data[CONF_USERNAME], pin, nonce)
            except MbapiError as error:
                LOGGER.error("Request token error: %s", errors)
                errors = error

            if not errors:
                LOGGER.debug("Token received")
                self.data["token"] = result

                if self.reauth_mode:
                    self.hass.async_create_task(self.hass.config_entries.async_reload(self._existing_entry.entry_id))
                    return self.async_abort(reason="reauth_successful")

                return self.async_create_entry(title=DOMAIN, data=self.data)

        return self.async_show_form(step_id="pin", data_schema=SCHEMA_STEP_PIN, errors=errors)

    async def async_step_reauth(self, user_input=None):
        """Get new tokens for a config entry that can't authenticate."""

        self.reauth_mode = True
        self._existing_entry = user_input

        return self.async_show_form(step_id="user", data_schema=SCHEMA_STEP_USER)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get options flow."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow handler."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry: ConfigEntry = config_entry
        self.options = dict(config_entry.options)

    async def async_step_init(self, user_input=None):
        """Manage the options."""

        if user_input is not None:
            if user_input[CONF_DELETE_AUTH_FILE] is True:
                auth_file = self.hass.config.path(STORAGE_DIR, f"{TOKEN_FILE_PREFIX}-{self.config_entry.entry_id}")
                LOGGER.warning("DELETE Auth File requested %s", auth_file)
                if os.path.isfile(auth_file):
                    os.remove(auth_file)

            if user_input[CONF_PIN] == "0":
                user_input[CONF_PIN] = ""
            self.options.update(user_input)
            return self.async_create_entry(title=DOMAIN, data=self.options)

        options = self.config_entry.options
        country_code = options.get(CONF_COUNTRY_CODE, DEFAULT_COUNTRY_CODE)
        locale = options.get(CONF_LOCALE, DEFAULT_LOCALE)
        excluded_cars = options.get(CONF_EXCLUDED_CARS, "")
        pin = options.get(CONF_PIN, "")
        cap_check_disabled = options.get(CONF_FT_DISABLE_CAPABILITY_CHECK, False)
        save_debug_files = options.get(CONF_DEBUG_FILE_SAVE, False)
        enable_china_gcj_02 = options.get(CONF_ENABLE_CHINA_GCJ_02, False)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_COUNTRY_CODE, default=country_code): str,
                    vol.Optional(CONF_LOCALE, default=locale): str,
                    vol.Optional(CONF_EXCLUDED_CARS, default=excluded_cars): str,
                    vol.Optional(CONF_PIN, default=pin): str,
                    vol.Optional(CONF_FT_DISABLE_CAPABILITY_CHECK, default=cap_check_disabled): bool,
                    vol.Optional(CONF_DEBUG_FILE_SAVE, default=save_debug_files): bool,
                    vol.Optional(CONF_DELETE_AUTH_FILE, default=False): bool,
                    vol.Optional(CONF_ENABLE_CHINA_GCJ_02, default=enable_china_gcj_02): bool,
                }
            ),
        )
