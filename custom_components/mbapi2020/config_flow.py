"""Config flow for mbapi2020 integration."""

from __future__ import annotations

from copy import deepcopy
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
    CONF_ALLOWED_REGIONS,
    CONF_DEBUG_FILE_SAVE,
    CONF_DELETE_AUTH_FILE,
    CONF_ENABLE_CHINA_GCJ_02,
    CONF_EXCLUDED_CARS,
    CONF_FT_DISABLE_CAPABILITY_CHECK,
    CONF_OVERWRITE_PRECONDNOW,
    CONF_PIN,
    CONF_REGION,
    DOMAIN,
    LOGGER,
    REGION_CHINA,
    TOKEN_FILE_PREFIX,
    VERIFY_SSL,
)
from .errors import MbapiError, MBAuth2FAError, MBAuthError, MBLegalTermsError

AUTH_METHOD_TOKEN = "token"
AUTH_METHOD_USERPASS = "userpass"

REGION_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_REGION): vol.In(CONF_ALLOWED_REGIONS),
    }
)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

USER_SCHEMA_CHINA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
    }
)

USER_STEP_PIN = vol.Schema({vol.Required(CONF_PASSWORD): str})


# Version threshold for config_entry setting in options flow
# See: https://github.com/home-assistant/core/pull/129562
HA_OPTIONS_FLOW_VERSION_THRESHOLD = "2024.11.99"


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for mbapi2020."""

    VERSION = 1

    def __init__(self):
        """Initialize the ConfigFlow state."""
        self._reauth_entry = None
        self._data = None
        self._reauth_mode = False
        self._auth_method = AUTH_METHOD_TOKEN
        self._region = None

    async def async_step_user(self, user_input=None):
        """Region selection step."""

        if user_input is not None:
            self._region = user_input[CONF_REGION]
            return await self.async_step_credentials()

        return self.async_show_form(step_id="user", data_schema=REGION_SCHEMA)

    async def async_step_credentials(self, user_input=None):
        """Credentials step - username/password or username only for China."""

        is_china = self._region == REGION_CHINA
        schema = USER_SCHEMA_CHINA if is_china else USER_SCHEMA

        if user_input is not None:
            user_input[CONF_REGION] = self._region
            await self.async_set_unique_id(f"{user_input[CONF_USERNAME]}-{user_input[CONF_REGION]}")

            if not self._reauth_mode:
                self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass, VERIFY_SSL)
            client = Client(self.hass, session, None, region=user_input[CONF_REGION])
            user_input[CONF_USERNAME] = user_input[CONF_USERNAME].strip()

            if is_china:
                nonce = str(uuid.uuid4())
                user_input["nonce"] = nonce
                errors = {}

                try:
                    await client.oauth.request_pin(user_input[CONF_USERNAME], nonce)
                except (MBAuthError, MbapiError):
                    errors = {"base": "pinrequest_failed"}
                    return self.async_show_form(step_id="credentials", data_schema=schema, errors=errors)

                if not errors:
                    self._data = user_input
                    return await self.async_step_pin()

                LOGGER.error("Request PIN error: %s", errors)

                self._data = {
                    CONF_USERNAME: user_input[CONF_USERNAME],
                    CONF_REGION: user_input[CONF_REGION],
                    "nonce": nonce,
                }
            else:
                try:
                    token_info = await client.oauth.async_login_new(
                        user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                    )
                except (MBAuthError, MbapiError) as error:
                    LOGGER.error("Login error: %s", error)
                    return self.async_show_form(
                        step_id="credentials", data_schema=schema, errors={"base": "invalid_auth"}
                    )
                except MBAuth2FAError as error:
                    LOGGER.error("Login error - 2FA accounts are not supported: %s", error)
                    return self.async_show_form(
                        step_id="credentials", data_schema=schema, errors={"base": "2fa_required"}
                    )
                except MBLegalTermsError as error:
                    LOGGER.error("Login error - Legal terms not accepted: %s", error)
                    return self.async_show_form(
                        step_id="credentials", data_schema=schema, errors={"base": "legal_terms"}
                    )
                self._data = {
                    CONF_USERNAME: user_input[CONF_USERNAME],
                    CONF_REGION: user_input[CONF_REGION],
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                    "token": token_info,
                    "device_guid": client.oauth._device_guid,  # noqa: SLF001
                }

            if self._reauth_mode:
                self.hass.config_entries.async_update_entry(self._reauth_entry, data=self._data)
                self.hass.config_entries.async_schedule_reload(self._reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

            return self.async_create_entry(
                title=f"{self._data[CONF_USERNAME]} (Region: {self._data[CONF_REGION]})",
                data=self._data,
            )

        return self.async_show_form(step_id="credentials", data_schema=schema)

    async def async_step_pin(self, user_input=None):
        """Handle the step where the user inputs his/her station."""

        errors = {}

        if user_input is not None:
            pin = user_input[CONF_PASSWORD]
            nonce = self._data["nonce"]
            new_config_entry: config_entries.ConfigEntry = await self.async_set_unique_id(
                f"{self._data[CONF_USERNAME]}-{self._data[CONF_REGION]}"
            )
            session = async_get_clientsession(self.hass, VERIFY_SSL)

            client = Client(self.hass, session, new_config_entry, self._data[CONF_REGION])
            try:
                result = await client.oauth.request_access_token_with_pin(self._data[CONF_USERNAME], pin, nonce)
            except MbapiError as error:
                LOGGER.error("Request token error: %s", error)
                errors = {"base": "token_with_pin_request_failed"}

            if not errors:
                LOGGER.debug("Token received")
                self._data["token"] = result
                self._data["device_guid"] = client.oauth._device_guid  # noqa: SLF001

                if self._reauth_mode:
                    self.hass.config_entries.async_update_entry(self._reauth_entry, data=self._data)
                    self.hass.async_create_task(self.hass.config_entries.async_reload(self._reauth_entry.entry_id))
                    return self.async_abort(reason="reauth_successful")

                return self.async_create_entry(
                    title=f"{self._data[CONF_USERNAME]} (Region: {self._data[CONF_REGION]})",
                    data=self._data,
                )

        return self.async_show_form(step_id="pin", data_schema=USER_STEP_PIN, errors=errors)

    async def async_step_reauth(self, user_input=None):
        """Get new tokens for a config entry that can't authenticate."""

        self._reauth_mode = True
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        self._region = self._reauth_entry.data.get(CONF_REGION)

        return await self.async_step_credentials()

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
