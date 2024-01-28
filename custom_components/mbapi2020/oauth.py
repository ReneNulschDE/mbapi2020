"""Define an object to interact with the REST API."""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
from typing import Optional
import urllib.parse
import uuid

from aiohttp import ClientSession
from aiohttp.client_exceptions import ClientError

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import STORAGE_DIR

from .const import (
    REGION_APAC,
    REGION_CHINA,
    REGION_EUROPE,
    REGION_NORAM,
    RIS_APPLICATION_VERSION,
    RIS_APPLICATION_VERSION_CN,
    RIS_APPLICATION_VERSION_NA,
    RIS_APPLICATION_VERSION_PA,
    RIS_OS_NAME,
    RIS_OS_VERSION,
    RIS_SDK_VERSION,
    SYSTEM_PROXY,
    TOKEN_FILE_PREFIX,
    VERIFY_SSL,
    WEBSOCKET_USER_AGENT,
    WEBSOCKET_USER_AGENT_CN,
    WEBSOCKET_USER_AGENT_PA,
    X_APPLICATIONNAME_AP,
    X_APPLICATIONNAME_CN,
    X_APPLICATIONNAME_ECE,
    X_APPLICATIONNAME_US,
)
from .helper import UrlHelper as helper

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10


class Oauth:  # pylint: disable-too-few-public-methods
    """define the client."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: Optional[ClientSession] = None,
        locale: Optional[str] = "EN",
        country_code: Optional[str] = "en-US",
        region: str = "",
        config_entry_id: str = "",
    ) -> None:
        """Initialize the OAuth instance."""
        self.token = None
        self._locale = locale
        self._country_code = country_code
        self._session: ClientSession | None = session
        self._region: str = region
        self.hass = hass
        self._config_entry_id = config_entry_id

        self.old_token_path = hass.config.path(TOKEN_FILE_PREFIX)
        self.config_entry_token_path = hass.config.path(STORAGE_DIR, f"{TOKEN_FILE_PREFIX}-{config_entry_id}")

    async def request_pin(self, email: str, nonce: str):
        """Initiate a PIN request."""
        _LOGGER.info("Start request PIN %s", email)
        url = f"{helper.Rest_url(self._region)}/v1/login"
        data = f'{{"emailOrPhoneNumber" : "{email}", "countryCode" : "{self._country_code}", "nonce" : "{nonce}"}}'
        headers = self._get_header()
        return await self._async_request("post", url, data=data, headers=headers)

    async def async_refresh_access_token(self, refresh_token: str):
        """Refresh the access token."""
        _LOGGER.info("Start async_refresh_access_token() with refresh_token")

        url = f"{helper.Login_Base_Url(self._region)}/as/token.oauth2"
        data = f"grant_type=refresh_token&refresh_token={refresh_token}"

        headers = self._get_header()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["X-Device-Id"] = str(uuid.uuid4())
        headers["X-Request-Id"] = str(uuid.uuid4())

        token_info = await self._async_request(method="post", url=url, data=data, headers=headers)

        if token_info is not None:
            if "refresh_token" not in token_info:
                token_info["refresh_token"] = refresh_token
            token_info = self._add_custom_values_to_token_info(token_info)
            self._save_token_info(token_info)
            self.token = token_info

        return token_info

    async def request_access_token(self, email: str, pin: str, nonce: str):
        """Request the access token using the Pin."""
        url = f"{helper.Login_Base_Url(self._region)}/as/token.oauth2"
        encoded_email = urllib.parse.quote_plus(email, safe="@")

        data = (
            f"client_id={helper.Login_App_Id(self._region)}&grant_type=password&username={encoded_email}&password={nonce}:{pin}"
            "&scope=openid email phone profile offline_access ciam-uid"
        )

        headers = self._get_header()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["Stage"] = "prod"
        headers["X-Device-Id"] = str(uuid.uuid4())
        headers["X-Request-Id"] = str(uuid.uuid4())

        token_info = await self._async_request("post", url, data=data, headers=headers)

        if token_info is not None:
            token_info = self._add_custom_values_to_token_info(token_info)
            self._save_token_info(token_info)
            self.token = token_info
            return token_info

        return None

    async def async_get_cached_token(self):
        """Get a cached auth token."""
        # _LOGGER.debug("Start async_get_cached_token()")
        token_info: dict[str, any]

        if self.token:
            token_info = self.token
        else:
            if not os.path.exists(self.config_entry_token_path):
                # migrate token
                _LOGGER.debug(
                    "async_get_cached_token: new token file %s not present. start token migration.",
                    self.config_entry_token_path,
                )
                if not os.path.exists(self.old_token_path):
                    _LOGGER.info(
                        "async_get_cached_token: Abort token migration - no old token file present. Reauth required"
                    )
                    return None

                _LOGGER.debug("async_get_cached_token: token migration - start copy")
                shutil.copyfile(self.old_token_path, self.config_entry_token_path)

                os.remove(self.old_token_path)

            token_file = open(self.config_entry_token_path)
            token_info_string = token_file.read()
            token_file.close()
            token_info = json.loads(token_info_string)

        if self.is_token_expired(token_info):
            _LOGGER.debug("%s token expired -> start refresh", __name__)
            if "refresh_token" not in token_info:
                _LOGGER.warning("Refresh token is missing - reauth required")
                return None
            token_info = await self.async_refresh_access_token(token_info["refresh_token"])

        self.token = token_info
        return token_info

    @classmethod
    def is_token_expired(cls, token_info) -> bool:
        """Check if the token is expired."""
        if token_info is not None:
            now = int(time.time())
            return token_info["expires_at"] - now < 60

        return True

    def _save_token_info(self, token_info):
        _LOGGER.debug("Start _save_token_info() to %s", self.config_entry_token_path)

        try:
            with open(self.config_entry_token_path, "w") as token_file:
                token_file.write(json.dumps(token_info))
                token_file.close()
        except OSError:
            _LOGGER.error("Couldn't write token cache to %s", self.config_entry_token_path)
            raise

    @classmethod
    def _add_custom_values_to_token_info(cls, token_info):
        """Store some values that aren't directly provided by a Web API response."""
        token_info["expires_at"] = int(time.time()) + token_info["expires_in"]
        return token_info

    def _get_header(self):
        header = {
            "Ris-Os-Name": RIS_OS_NAME,
            "Ris-Os-Version": RIS_OS_VERSION,
            "Ris-Sdk-Version": RIS_SDK_VERSION,
            "X-Locale": self._locale,
            "X-Trackingid": str(uuid.uuid4()),
            "X-Sessionid": str(uuid.uuid4()),
            "User-Agent": WEBSOCKET_USER_AGENT,
            "Content-Type": "application/json",
            "Accept-Language": "en-GB",
        }

        header = self._get_region_header(header)

        return header

    def _get_region_header(self, header):
        if self._region == REGION_EUROPE:
            header["X-Applicationname"] = X_APPLICATIONNAME_ECE
            header["Ris-Application-Version"] = RIS_APPLICATION_VERSION

        if self._region == REGION_NORAM:
            header["X-Applicationname"] = X_APPLICATIONNAME_US
            header["Ris-Application-Version"] = RIS_APPLICATION_VERSION_NA

        if self._region == REGION_APAC:
            header["X-Applicationname"] = X_APPLICATIONNAME_AP
            header["Ris-Application-Version"] = RIS_APPLICATION_VERSION_PA
            header["User-Agent"] = WEBSOCKET_USER_AGENT_PA

        if self._region == REGION_CHINA:
            header["X-Applicationname"] = X_APPLICATIONNAME_CN
            header["Ris-Application-Version"] = RIS_APPLICATION_VERSION_CN
            header["User-Agent"] = WEBSOCKET_USER_AGENT_CN

        return header

    async def _async_request(self, method: str, url: str, data: str = "", **kwargs):
        """Make a request against the API."""

        kwargs.setdefault("headers", {})
        kwargs.setdefault("proxy", SYSTEM_PROXY)

        if not self._session or self._session.closed:
            self._session = async_get_clientsession(self.hass, VERIFY_SSL)

        try:
            async with self._session.request(method, url, data=data, **kwargs) as resp:
                # _LOGGER.warning("ClientError requesting data from %s: %s", url, resp.json)
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except ClientError as err:
            _LOGGER.error("ClientError requesting data from %s: %s", url, err)
            raise err
        except Exception as exc:
            _LOGGER.error("Unexpected Error requesting data from %s: %s", url, exc)
