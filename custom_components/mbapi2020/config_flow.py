"""Config flow for mbapi2020 integration."""

from __future__ import annotations

import asyncio
from copy import deepcopy

import aiohttp
from awesomeversion import AwesomeVersion
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, __version__ as HAVERSION
from homeassistant.core import EventOrigin, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue
from homeassistant.helpers.storage import STORAGE_DIR

from .china_oauth import (
    build_china_oauth_static_url,
    register_china_oauth_flow,
    setup_china_oauth_frontend,
    unregister_china_oauth_flow,
)
from .client import Client
from .const import (
    AUTH_METHOD_DEVICE,
    CIAM_DEVICE_USER_AUTHZ_URL_CN,
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
from .errors import (
    MbapiError,
    MBAuth2FAError,
    MBAuthError,
    MBDeviceAuthDenied,
    MBDeviceAuthTimeout,
    MBLegalTermsError,
)
from .oauth import Oauth

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
        self._device_wait_task = None
        self._device_client = None
        self._device_token_info = None
        self._device_user_code = None
        self._device_verify_url = None
        self._device_expires_minutes = "10"

    async def async_step_user(self, user_input=None):
        """Region selection step."""

        if user_input is not None:
            self._region = user_input[CONF_REGION]
            if self._region == REGION_CHINA:
                return await self.async_step_china_oauth()
            return await self.async_step_credentials()

        return self.async_show_form(step_id="user", data_schema=REGION_SCHEMA)

    def _reset_device_wait(self) -> None:
        """Reset China device-code wait state so a new login round can start."""
        if self._device_wait_task is not None and not self._device_wait_task.done():
            self._device_wait_task.cancel()
        self._device_wait_task = None
        self._device_client = None
        self._device_token_info = None
        self._device_user_code = None
        self._device_verify_url = None
        unregister_china_oauth_flow(self.hass, self.flow_id)

    def _fire_china_oauth_open_event(self, verify_url: str) -> None:
        """Ask the frontend helper to open the China login wrapper page."""
        self.hass.bus.async_fire(
            "mbapi2020_open_china_oauth",
            {"url": verify_url, "flow_id": self.flow_id},
            EventOrigin.local,
        )

    async def _async_start_china_device_login(self) -> dict:
        """Request a China device code and keep the OAuth client for polling."""
        session = async_get_clientsession(self.hass, VERIFY_SSL)
        client = Client(self.hass, session, None, region=REGION_CHINA)
        if self._reauth_mode and self._reauth_entry:
            previous_guid = self._reauth_entry.data.get("device_guid")
            if previous_guid:
                client.oauth._device_guid = previous_guid  # noqa: SLF001
        self._device_client = client

        device = await client.oauth.async_request_device_code()
        self._device_user_code = device["user_code"]
        login_url = client.oauth.china_device_verify_url(device["user_code"])
        register_china_oauth_flow(self.hass, self.flow_id, device["user_code"], login_url)
        self._device_verify_url = build_china_oauth_static_url(device["user_code"], login_url)
        self._device_expires_minutes = str(max(int(device.get("expires_in", 600)) // 60, 1))
        return device

    async def _async_wait_for_china_device_token(self, device: dict) -> dict:
        """Wait until the official Mercedes page authorizes this device."""
        assert self._device_client is not None
        return await self._device_client.oauth.async_poll_device_token(
            device["device_code"],
            int(device.get("interval", 5)),
            int(device.get("expires_in", 600)),
        )

    async def _async_finish_china_tokens(self, client: Client, token_info: dict):
        """Validate China tokens and create or update the config entry."""
        if "expires_at" not in token_info:
            token_info = Oauth._add_custom_values_to_token_info(token_info)
        token_info["china_direct"] = True
        client.oauth.token = token_info

        username = "china"
        try:
            user = await client.webapi.get_user()
        except (MBAuthError, MbapiError, aiohttp.ClientError) as error:
            LOGGER.error("China token validation via /v1/user failed: %s", error)
            return None, "china_oauth_token_invalid"

        if isinstance(user, dict):
            username = (
                user.get("email")
                or user.get("mail")
                or user.get("username")
                or user.get("userName")
                or "china"
            )

        await self.async_set_unique_id(f"{username}-{REGION_CHINA}")
        if not self._reauth_mode:
            self._abort_if_unique_id_configured()

        self._data = {
            CONF_USERNAME: username,
            CONF_REGION: REGION_CHINA,
            "token": token_info,
            "device_guid": client.oauth._device_guid,  # noqa: SLF001
            "auth_method": AUTH_METHOD_DEVICE,
        }

        if self._reauth_mode:
            self.hass.config_entries.async_update_entry(self._reauth_entry, data=self._data)
            self.hass.config_entries.async_schedule_reload(self._reauth_entry.entry_id)
            return self.async_abort(reason="reauth_successful"), None

        return self.async_create_entry(
            title=f"{username} (Region: {REGION_CHINA})",
            data=self._data,
        ), None

    async def async_step_china_oauth(self, user_input=None):
        """Official Mercedes China device-code login."""
        del user_input
        await setup_china_oauth_frontend(self.hass)
        if self._device_wait_task is not None and self._device_wait_task.done():
            try:
                self._device_token_info = self._device_wait_task.result()
            except MBDeviceAuthTimeout:
                self._reset_device_wait()
                return self.async_show_progress_done(next_step_id="china_oauth_failed")
            except MBDeviceAuthDenied:
                self._reset_device_wait()
                return self.async_show_progress_done(next_step_id="china_oauth_denied")
            except asyncio.CancelledError:
                self._reset_device_wait()
                return self.async_show_progress_done(next_step_id="china_oauth_failed")
            except (MBAuthError, MbapiError, aiohttp.ClientError) as error:
                LOGGER.error("China device-code login failed: %s", error)
                self._reset_device_wait()
                return self.async_show_progress_done(next_step_id="china_oauth_failed")

            return self.async_show_progress_done(next_step_id="china_oauth_finish")

        if self._device_wait_task is None:
            try:
                device = await self._async_start_china_device_login()
            except (MBAuthError, MbapiError, aiohttp.ClientError) as error:
                LOGGER.error("China device-code start failed: %s", error)
                self._reset_device_wait()
                return await self.async_step_china_oauth_failed()
            self._device_wait_task = self.hass.async_create_task(
                self._async_wait_for_china_device_token(device)
            )

        if self._device_verify_url:
            self._fire_china_oauth_open_event(self._device_verify_url)

        return self.async_show_progress(
            step_id="china_oauth",
            progress_action="wait_for_china_oauth",
            description_placeholders={
                "user_code": self._device_user_code or "",
                "verify_url": self._device_verify_url or CIAM_DEVICE_USER_AUTHZ_URL_CN,
                "expires_minutes": self._device_expires_minutes,
            },
            progress_task=self._device_wait_task,
        )

    async def async_step_china_oauth_denied(self, user_input=None):
        """Abort after the official page denied device authorization."""
        del user_input
        return self.async_abort(reason="china_oauth_denied")

    async def async_step_china_oauth_finish(self, user_input=None):
        """Create the config entry after the official page authorized the device."""
        del user_input
        client = self._device_client
        token_info = self._device_token_info
        try:
            if client is None or not token_info:
                return await self.async_step_china_oauth_failed()
            result, error = await self._async_finish_china_tokens(client, token_info)
            if error:
                return await self.async_step_china_oauth_failed()
            return result
        finally:
            self._reset_device_wait()

    async def async_step_china_oauth_failed(self, user_input=None):
        """Retry official China login after a timeout or error."""
        if user_input is not None:
            return await self.async_step_china_oauth()

        return self.async_show_form(step_id="china_oauth_failed")

    async def async_step_credentials(self, user_input=None):
        """Credentials step - username and password for non-China regions."""

        if user_input is not None:
            user_input[CONF_REGION] = self._region
            await self.async_set_unique_id(f"{user_input[CONF_USERNAME]}-{user_input[CONF_REGION]}")

            if not self._reauth_mode:
                self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass, VERIFY_SSL)
            client = Client(self.hass, session, None, region=user_input[CONF_REGION])
            user_input[CONF_USERNAME] = user_input[CONF_USERNAME].strip()

            try:
                token_info = await client.oauth.async_login_new(
                    user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                )
            except (MBAuthError, MbapiError) as error:
                LOGGER.error("Login error: %s", error)
                return self.async_show_form(
                    step_id="credentials", data_schema=USER_SCHEMA, errors={"base": "invalid_auth"}
                )
            except MBAuth2FAError as error:
                LOGGER.error("Login error - 2FA accounts are not supported: %s", error)
                return self.async_show_form(
                    step_id="credentials", data_schema=USER_SCHEMA, errors={"base": "2fa_required"}
                )
            except MBLegalTermsError as error:
                LOGGER.error("Login error - Legal terms not accepted: %s", error)
                return self.async_show_form(
                    step_id="credentials", data_schema=USER_SCHEMA, errors={"base": "legal_terms"}
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

        return self.async_show_form(step_id="credentials", data_schema=USER_SCHEMA)

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

        if self._region == REGION_CHINA:
            return await self.async_step_china_oauth()
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
            LOGGER.debug(
                "user_input: %s",
                {k: ("xxxx" if v else v) if k == CONF_PIN else v for k, v in user_input.items()},
            )
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
