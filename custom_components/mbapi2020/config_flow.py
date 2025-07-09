"""Config flow for mbapi2020 integration."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
import uuid

from awesomeversion import AwesomeVersion
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, __version__ as HAVERSION
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue
from homeassistant.helpers.storage import STORAGE_DIR

from .client import Client
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_ALLOWED_REGIONS,
    CONF_DEBUG_FILE_SAVE,
    CONF_DELETE_AUTH_FILE,
    CONF_ENABLE_CHINA_GCJ_02,
    CONF_EXCLUDED_CARS,
    CONF_FT_DISABLE_CAPABILITY_CHECK,
    CONF_OVERWRITE_PRECONDNOW,
    CONF_PIN,
    CONF_REFRESH_TOKEN,
    CONF_REGION,
    DOMAIN,
    LOGGER,
    TOKEN_FILE_PREFIX,
    VERIFY_SSL,
)
from .errors import MbapiError, MBAuthError

AUTH_METHOD_TOKEN = "token"
AUTH_METHOD_USERPASS = "userpass"

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_REGION): vol.In(CONF_ALLOWED_REGIONS),
    }
)

# Version threshold for config_entry setting in options flow
# See: https://github.com/home-assistant/core/pull/129562
HA_OPTIONS_FLOW_VERSION_THRESHOLD = "2024.11.99"


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for mbapi2020."""

    VERSION = 1

    def __init__(self):
        self._reauth_entry = None
        self._data = None
        self._reauth_mode = False
        self._auth_method = AUTH_METHOD_TOKEN

    async def async_step_user(self, user_input=None):
        """Username/Password-Flow."""

        if user_input is not None:
            new_config_entry: config_entries.ConfigEntry = await self.async_set_unique_id(
                f"{user_input[CONF_USERNAME]}-{user_input[CONF_REGION]}"
            )

            if not self._reauth_mode:
                self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass, VERIFY_SSL)
            client = Client(self.hass, session, None, region=user_input[CONF_REGION])
            try:
                token_info = await client.oauth.async_login_new(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
            except (MBAuthError, MbapiError) as error:
                LOGGER.error("Login error: %s", error)
                return self.async_show_form(step_id="user", data_schema=USER_SCHEMA, errors={"base": "invalid_auth"})
            # Token speichern und Entry anlegen
            self._data = {
                CONF_USERNAME: user_input[CONF_USERNAME],
                CONF_REGION: user_input[CONF_REGION],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
                "token": token_info,
            }

            if self._reauth_mode:
                self.hass.config_entries.async_update_entry(self._reauth_entry, data=self._data)
                self.hass.config_entries.async_schedule_reload(self._reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

            return self.async_create_entry(
                title=f"{self._data[CONF_USERNAME]} (Region: {self._data[CONF_REGION]})",
                data=self._data,
            )
        return self.async_show_form(step_id="user", data_schema=USER_SCHEMA)

    async def async_step_reauth(self, user_input=None):
        """Get new tokens for a config entry that can't authenticate."""

        self._reauth_mode = True

        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])

        return self.async_show_form(step_id="user", data_schema=USER_SCHEMA)

    # async def async_step_reconfigure(self, user_input=None):
    #     """Get new tokens for a config entry that can't authenticate."""
    #     self._reauth_mode = True
    #     self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
    #     return self.async_show_form(step_id="user", data_schema=SCHEMA_STEP_AUTH_SELECT)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get options flow."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow handler."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize MBAI2020 options flow."""
        self.options = dict(config_entry.options)
        # See: https://github.com/home-assistant/core/pull/129562
        if AwesomeVersion(HAVERSION) < HA_OPTIONS_FLOW_VERSION_THRESHOLD:
            self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""

        if user_input is not None:
            LOGGER.debug("user_input: %s", user_input)
            if user_input[CONF_DELETE_AUTH_FILE] is True:
                auth_file = self.hass.config.path(STORAGE_DIR, f"{TOKEN_FILE_PREFIX}-{self.config_entry.entry_id}")
                LOGGER.warning("DELETE Auth Information requested %s", auth_file)
                new_config_entry_data = deepcopy(dict(self.config_entry.data))
                new_config_entry_data["token"] = None
                changed = self.hass.config_entries.async_update_entry(self.config_entry, data=new_config_entry_data)

                LOGGER.debug("%s Creating restart_required issue", DOMAIN)
                async_create_issue(
                    hass=self.hass,
                    domain=DOMAIN,
                    issue_id="restart_required_auth_deleted",
                    is_fixable=True,
                    issue_domain=DOMAIN,
                    severity=IssueSeverity.WARNING,
                    translation_key="restart_required",
                    translation_placeholders={
                        "name": DOMAIN,
                    },
                )

            self.options.update(user_input)
            changed = self.hass.config_entries.async_update_entry(
                self.config_entry,
                options=user_input,
            )
            if changed:
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title=DOMAIN, data=self.options)

        excluded_cars = self.options.get(CONF_EXCLUDED_CARS, "")
        pin = self.options.get(CONF_PIN, "")
        cap_check_disabled = self.options.get(CONF_FT_DISABLE_CAPABILITY_CHECK, False)
        save_debug_files = self.options.get(CONF_DEBUG_FILE_SAVE, False)
        enable_china_gcj_02 = self.options.get(CONF_ENABLE_CHINA_GCJ_02, False)
        overwrite_cap_precondnow = self.options.get(CONF_OVERWRITE_PRECONDNOW, False)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_EXCLUDED_CARS, default="", description={"suggested_value": excluded_cars}): str,
                    vol.Optional(CONF_PIN, default="", description={"suggested_value": pin}): str,
                    vol.Optional(CONF_FT_DISABLE_CAPABILITY_CHECK, default=cap_check_disabled): bool,
                    vol.Optional(CONF_DEBUG_FILE_SAVE, default=save_debug_files): bool,
                    vol.Optional(CONF_DELETE_AUTH_FILE, default=False): bool,
                    vol.Optional(CONF_ENABLE_CHINA_GCJ_02, default=enable_china_gcj_02): bool,
                    vol.Optional(CONF_OVERWRITE_PRECONDNOW, default=overwrite_cap_precondnow): bool,
                }
            ),
        )
