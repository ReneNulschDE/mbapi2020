"""Define an object to interact with the REST API."""
import json
import logging
import time
import urllib.parse
import uuid
from typing import Optional

from aiohttp import ClientSession, ClientTimeout
from aiohttp.client_exceptions import ClientError

from .const import (
    DISABLE_SSL_CERT_CHECK,
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
        *,
        session: Optional[ClientSession] = None,
        locale: Optional[str] = "EN",
        country_code: Optional[str] = "en-US",
        cache_path: Optional[str] = None,
        region: str = None,
    ) -> None:
        self.token = None
        self._locale = locale
        self._country_code = country_code
        self._session: ClientSession = session
        self._region: str = region
        self.cache_path = cache_path
        self._session_id = ""

    async def request_pin(self, email: str, nonce: str):
        _LOGGER.info("Start request PIN %s", email)
        headers = self._get_header()

        _LOGGER.info("PIN preflight request 1")
        url = f"{helper.Rest_url(self._region)}/v1/config"
        r = await self._async_request("get", url, headers=headers)
        _LOGGER.info("PIN preflight request 2")
        url = f"{helper.Rest_url(self._region)}/v3/agreements?addressCountry=DE"
        r = await self._async_request("get", url, headers=headers)

        url = f"{helper.Rest_url(self._region)}/v1/login"
        data = f'{{"emailOrPhoneNumber" : "{email}", "countryCode" : "{self._country_code}", "nonce" : "{nonce}"}}'
        return await self._async_request("post", url, data=data, headers=headers)

    async def async_refresh_access_token(self, refresh_token: str):
        _LOGGER.info("Start async_refresh_access_token() with refresh_token")

        url = f"{helper.Login_Base_Url(self._region)}/as/token.oauth2"
        data = f"grant_type=refresh_token&refresh_token={refresh_token}"

        headers = self._get_header()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["X-Device-Id"] = str(uuid.uuid4())
        headers["X-Request-Id"] = str(uuid.uuid4())

        token_info = await self._async_request(
            method="post", url=url, data=data, headers=headers
        )

        if token_info is not None:
            if "refresh_token" not in token_info:
                token_info["refresh_token"] = refresh_token
            token_info = self._add_custom_values_to_token_info(token_info)
            self._save_token_info(token_info)
            self.token = token_info

        return token_info

    async def request_access_token(self, email: str, pin: str, nonce: str):
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
        """Gets a cached auth token"""
        _LOGGER.debug("Start async_get_cached_token()")
        token_info = None
        if self.cache_path:
            try:
                token_file = open(self.cache_path)
                token_info_string = token_file.read()
                token_file.close()
                token_info = json.loads(token_info_string)

                if self.is_token_expired(token_info):
                    _LOGGER.debug("%s token expired -> start refresh", __name__)
                    if "refresh_token" not in token_info:
                        _LOGGER.warning("Refresh token is missing - reauth required")
                        return None
                    token_info = await self.async_refresh_access_token(
                        token_info["refresh_token"]
                    )

            except IOError:
                pass
        self.token = token_info
        return token_info

    @classmethod
    def is_token_expired(cls, token_info):
        if token_info is not None:
            now = int(time.time())
            return token_info["expires_at"] - now < 60

        return True

    def _save_token_info(self, token_info):
        _LOGGER.debug("Start _save_token_info() to %s", self.cache_path)
        if self.cache_path:
            try:
                with open(self.cache_path, "w") as token_file:
                    token_file.write(json.dumps(token_info))
                    token_file.close()
            except IOError:
                _LOGGER.error("Couldn't write token cache to %s", self.cache_path)

    @classmethod
    def _add_custom_values_to_token_info(cls, token_info):
        """
        Store some values that aren't directly provided by a Web API
        response.
        """
        token_info["expires_at"] = int(time.time()) + token_info["expires_in"]
        return token_info

    def _get_header(self) -> list:
        if not self._session_id:
            self._session_id = str(uuid.uuid4())

        header = {
            "Ris-Os-Name": RIS_OS_NAME,
            "Ris-Os-Version": RIS_OS_VERSION,
            "Ris-Sdk-Version": RIS_SDK_VERSION,
            "X-Locale": self._locale,
            "X-Trackingid": str(uuid.uuid4()),
            "X-Sessionid": self._session_id,
            "User-Agent": WEBSOCKET_USER_AGENT,
            "Content-Type": "application/json",
        }

        header = self._get_region_header(header)

        return header

    def _get_region_header(self, header) -> list:
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

    async def _async_request(
        self, method: str, url: str, data: str = "", **kwargs
    ) -> list:
        """Make a request against the API."""

        kwargs.setdefault("headers", {})
        kwargs.setdefault("proxy", SYSTEM_PROXY)
        kwargs.setdefault("ssl", DISABLE_SSL_CERT_CHECK)

        use_running_session = self._session and not self._session.closed

        if use_running_session:
            session = self._session
        else:
            session = ClientSession(timeout=ClientTimeout(total=DEFAULT_TIMEOUT))

        try:
            async with session.request(method, url, data=data, **kwargs) as resp:
                # _LOGGER.warning("ClientError requesting data from %s: %s", url, resp.json)
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except ClientError as err:
            _LOGGER.error("ClientError requesting data from %s: %s", url, err)
            raise err
        except Exception as exc:
            _LOGGER.error("Unexpected Error requesting data from %s: %s", url, exc)
        finally:
            if not use_running_session:
                await session.close()
