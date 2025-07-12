"""Integration of optimized Mercedes Me OAuth2 LoginNew functionality."""

from __future__ import annotations

import asyncio
import base64
from copy import deepcopy
import hashlib
import json
import logging
import secrets
import time
from typing import Any
import urllib.parse
import uuid

import aiohttp
from aiohttp import ClientSession

from custom_components.mbapi2020.errors import MBAuthError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import (
    DEFAULT_LOCALE,
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


class Oauth:
    """OAuth2 class for Mercedes Me integration."""

    # OAuth2 Configuration for new login method
    CLIENT_ID = "62778dc4-1de3-44f4-af95-115f06a3a008"
    REDIRECT_URI = "rismycar://login-callback"
    SCOPE = "email profile ciam-uid phone openid offline_access"

    def __init__(
        self,
        hass: HomeAssistant,
        session: ClientSession,
        region: str,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the extended OAuth instance."""
        self._session: ClientSession = session
        self._region: str = region
        self._hass = hass
        self._config_entry = config_entry
        self.token = None
        self._sessionid = ""
        self._get_token_lock = asyncio.Lock()

        # PKCE parameters for new login method
        self.code_verifier: str | None = None
        self.code_challenge: str | None = None

    def _generate_pkce_parameters(self) -> tuple[str, str]:
        """Generate PKCE (Proof Key for Code Exchange) parameters for OAuth2.

        Returns:
            tuple: (code_verifier, code_challenge)

        """
        # Generate code_verifier (43-128 characters, URL-safe)
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("utf-8").rstrip("=")

        # Generate code_challenge (SHA256 hash of code_verifier, base64url encoded)
        code_challenge_bytes = hashlib.sha256(code_verifier.encode("utf-8")).digest()
        code_challenge = base64.urlsafe_b64encode(code_challenge_bytes).decode("utf-8").rstrip("=")

        _LOGGER.debug("Generated PKCE parameters for OAuth2 flow")
        return code_verifier, code_challenge

    def _ensure_pkce_parameters(self) -> None:
        """Ensure PKCE parameters are generated."""
        if not self.code_verifier or not self.code_challenge:
            self.code_verifier, self.code_challenge = self._generate_pkce_parameters()

    async def async_login_new(self, email: str, password: str) -> dict[str, Any]:
        """Perform new OAuth2 login flow with PKCE.

        Args:
            email: Mercedes Me account email
            password: Mercedes Me account password

        Returns:
            dict containing token information

        Raises:
            MBAuthError: If login fails

        """
        _LOGGER.info("Starting OAuth2 login flow")

        if not self._session or self._session.closed:
            self._session = async_create_clientsession(self._hass, VERIFY_SSL)

        try:
            # Step 1: Get authorization URL and extract resume parameter
            resume_url = await self._get_authorization_resume()

            # Step 2: Send user agent information
            await self._send_user_agent_info()

            # Step 3: Submit username
            await self._submit_username(email)

            # Step 4: Submit password and get pre-login token
            pre_login_data = await self._submit_password(email, password)

            # Step 5: Resume authorization and get code
            auth_code = await self._resume_authorization(resume_url, pre_login_data["token"])

            # Step 6: Exchange code for tokens
            token_info = await self._exchange_code_for_tokens(auth_code)

            # Add custom values and save token
            token_info = self._add_custom_values_to_token_info(token_info)
            self._save_token_info(token_info)
            self.token = token_info

            _LOGGER.info("OAuth2 login successful")
            return token_info

        except Exception as e:
            _LOGGER.error("OAuth2 login failed: %s", e)
            raise MBAuthError(f"Login failed: {e}") from e

    async def _get_authorization_resume(self) -> str:
        """Get authorization URL and extract resume parameter."""
        self._ensure_pkce_parameters()

        params = {
            "client_id": self.CLIENT_ID,
            "code_challenge": self.code_challenge,
            "code_challenge_method": "S256",
            "redirect_uri": self.REDIRECT_URI,
            "response_type": "code",
            "scope": self.SCOPE,
        }

        headers = {
            "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_8_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.6.6 Mobile/15E148 Safari/604.1",
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "de-DE,de;q=0.9",
        }

        auth_url = f"{helper.Login_Base_Url(self._region)}/as/authorization.oauth2"

        async with self._session.get(
            auth_url, params=params, headers=headers, proxy=SYSTEM_PROXY, allow_redirects=True
        ) as response:
            if response.status >= 400:
                raise MBAuthError(f"Authorization request failed: {response.status}")

            parsed_url = urllib.parse.urlparse(str(response.url))
            url_params = urllib.parse.parse_qs(parsed_url.query)
            resume = url_params.get("resume", [None])[0]

            if not resume:
                raise MBAuthError("Resume parameter not found in authorization response")

            return resume

    async def _send_user_agent_info(self) -> None:
        """Send user agent information."""
        headers = {
            "accept": "*/*",
            "content-type": "application/json",
            "origin": helper.Login_Base_Url(self._region),
            "accept-language": "de-DE,de;q=0.9",
            "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_8_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.6.6 Mobile/15E148 Safari/604.1",
        }

        data = {
            "browserName": "Mobile Safari",
            "browserVersion": "15.6.6",
            "osName": "iOS",
        }

        url = f"{helper.Login_Base_Url(self._region)}/ciam/auth/ua"

        async with self._session.post(url, json=data, headers=headers, proxy=SYSTEM_PROXY) as response:
            if response.status >= 400:
                _LOGGER.warning("User agent info submission failed: %s", response.status)

    async def _submit_username(self, email: str) -> None:
        """Submit username."""
        headers = {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "origin": helper.Login_Base_Url(self._region),
            "accept-language": "de-DE,de;q=0.9",
            "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_8_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.6.6 Mobile/15E148 Safari/604.1",
            "referer": f"{helper.Login_Base_Url(self._region)}/ciam/auth/login",
        }

        url = f"{helper.Login_Base_Url(self._region)}/ciam/auth/login/user"

        async with self._session.post(url, json={"username": email}, headers=headers, proxy=SYSTEM_PROXY) as response:
            if response.status >= 400:
                raise MBAuthError(f"Username submission failed: {response.status}")

    async def _submit_password(self, email: str, password: str) -> dict[str, Any]:
        """Submit password and get pre-login data."""
        # Generate random request ID
        rid = secrets.token_urlsafe(24)

        headers = {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "origin": helper.Login_Base_Url(self._region),
            "accept-language": "de-DE,de;q=0.9",
            "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_8_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.6.6 Mobile/15E148 Safari/604.1",
            "referer": f"{helper.Login_Base_Url(self._region)}/ciam/auth/login",
        }

        data = {
            "username": email,
            "password": password,
            "rememberMe": False,
            "rid": rid,
        }

        url = f"{helper.Login_Base_Url(self._region)}/ciam/auth/login/pass"

        async with self._session.post(url, json=data, headers=headers, proxy=SYSTEM_PROXY) as response:
            if response.status >= 400:
                error_text = await response.text()
                raise MBAuthError(f"Password submission failed: {response.status} - {error_text}")

            return await response.json()

    async def _resume_authorization(self, resume_url: str, token: str) -> str:
        """Resume authorization and extract code."""
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "content-type": "application/x-www-form-urlencoded",
            "origin": helper.Login_Base_Url(self._region),
            "accept-language": "de-DE,de;q=0.9",
            "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_8_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.6.6 Mobile/15E148 Safari/604.1",
            "referer": f"{helper.Login_Base_Url(self._region)}/ciam/auth/login",
        }

        data = aiohttp.FormData({"token": token})

        try:
            async with self._session.post(
                f"{helper.Login_Base_Url(self._region)}{resume_url}",
                data=data,
                headers=headers,
                proxy=SYSTEM_PROXY,
                allow_redirects=False,
            ) as response:
                # Handle redirect
                if response.status in [302, 301]:
                    redirect_url = response.headers.get("location", "")
                    if redirect_url.startswith("rismycar://"):
                        parsed_url = urllib.parse.urlparse(redirect_url)
                        params = urllib.parse.parse_qs(parsed_url.query)
                        code = params.get("code", [None])[0]
                        if not code:
                            raise MBAuthError("Authorization code not found in redirect")
                        return code

                raise MBAuthError(f"Unexpected response during authorization: {response.status}")

        except aiohttp.InvalidURL as e:
            # Handle custom scheme redirect
            error_str = str(e)
            if "rismycar://" in error_str:
                # Extract URL from error message
                start = error_str.find("'") + 1
                end = error_str.find("'", start)
                redirect_url = error_str[start:end]

                parsed_url = urllib.parse.urlparse(redirect_url)
                params = urllib.parse.parse_qs(parsed_url.query)
                code = params.get("code", [None])[0]
                if not code:
                    raise MBAuthError("Authorization code not found in redirect URL")
                return code
            raise MBAuthError(f"Unexpected URL error: {e}")

    async def _exchange_code_for_tokens(self, code: str) -> dict[str, Any]:
        """Exchange authorization code for access and refresh tokens."""
        if not self.code_verifier:
            raise MBAuthError("Code verifier not available for token exchange")

        headers = self._get_header()
        headers["Content-Type"] = "application/x-www-form-urlencoded"

        data = {
            "client_id": self.CLIENT_ID,
            "code": code,
            "code_verifier": self.code_verifier,
            "grant_type": "authorization_code",
            "redirect_uri": self.REDIRECT_URI,
        }

        # Convert to form data
        form_data = "&".join([f"{k}={urllib.parse.quote_plus(str(v))}" for k, v in data.items()])

        url = f"{helper.Login_Base_Url(self._region)}/as/token.oauth2"

        async with self._session.post(url, data=form_data, headers=headers, proxy=SYSTEM_PROXY) as response:
            if response.status >= 400:
                error_text = await response.text()
                raise MBAuthError(f"Token exchange failed: {response.status} - {error_text}")

            return await response.json()

    async def async_refresh_access_token(self, refresh_token: str, is_retry: bool = False):
        """Refresh the access token."""
        _LOGGER.info("Start async_refresh_access_token() with refresh_token")

        _LOGGER.debug("Auth token refresh preflight request 1")
        headers = self._get_header()
        url = f"{helper.Rest_url(self._region)}/v1/config"
        await self._async_request("get", url, headers=headers)

        url = f"{helper.Login_Base_Url(self._region)}/as/token.oauth2"
        data = f"grant_type=refresh_token&refresh_token={refresh_token}"

        headers = self._get_header()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["X-Device-Id"] = str(uuid.uuid4())
        headers["X-Request-Id"] = str(uuid.uuid4())

        token_info = None
        try:
            token_info = await self._async_request(method="post", url=url, data=data, headers=headers)

        except MBAuthError:
            if is_retry:
                if self._config_entry and self._config_entry.data:
                    new_config_entry_data = deepcopy(dict(self._config_entry.data))
                    new_config_entry_data.pop("token", None)
                    self._hass.config_entries.async_update_entry(self._config_entry, data=new_config_entry_data)
                raise

        if token_info is not None:
            if "refresh_token" not in token_info:
                token_info["refresh_token"] = refresh_token
            token_info = self._add_custom_values_to_token_info(token_info)
            self._save_token_info(token_info)
            self.token = token_info

        return token_info

    async def async_get_cached_token(self):
        """Get a cached auth token."""
        _LOGGER.debug("Start async_get_cached_token()")
        token_info: dict[str, any]

        if self.token:
            token_info = self.token
        elif self._config_entry and self._config_entry.data and "token" in self._config_entry.data:
            token_info = self._config_entry.data["token"]
        else:
            _LOGGER.warning("No token information - reauth required")
            return None

        if self.is_token_expired(token_info):
            async with self._get_token_lock:
                _LOGGER.debug("%s token expired -> start refresh", __name__)
                if not token_info or "refresh_token" not in token_info:
                    _LOGGER.warning("Refresh token is missing - reauth required")
                    return None

                token_info = await self.async_refresh_access_token(token_info["refresh_token"], is_retry=False)

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
        """Save token info."""
        if self._config_entry:
            _LOGGER.debug(
                "Start _save_token_info() to config_entry %s",
                self._config_entry.entry_id,
            )

            new_config_entry_data = deepcopy(dict(self._config_entry.data))
            new_config_entry_data["token"] = token_info
            self._hass.config_entries.async_update_entry(self._config_entry, data=new_config_entry_data)

    @classmethod
    def _add_custom_values_to_token_info(cls, token_info):
        """Add custom values to token info."""
        token_info["expires_at"] = int(time.time()) + token_info["expires_in"]
        return token_info

    def _get_header(self):
        """Get headers with Session-ID."""
        if not self._sessionid:
            self._sessionid = str(uuid.uuid4())

        header = {
            "Ris-Os-Name": RIS_OS_NAME,
            "Ris-Os-Version": RIS_OS_VERSION,
            "Ris-Sdk-Version": RIS_SDK_VERSION,
            "X-Locale": DEFAULT_LOCALE,
            "X-Trackingid": str(uuid.uuid4()),
            "X-Sessionid": self._sessionid,
            "User-Agent": WEBSOCKET_USER_AGENT,
            "Content-Type": "application/json",
            "Accept-Language": "en-GB",
        }

        return self._get_region_header(header)

    def _get_region_header(self, header):
        """Get region-specific headers."""
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
            self._session = async_create_clientsession(self._hass, VERIFY_SSL)

        async with self._session.request(method, url, data=data, **kwargs) as resp:
            if 400 <= resp.status <= 500:
                try:
                    error = await resp.text()
                    error_json = json.loads(error)
                    if error_json:
                        error_message = f"Error requesting: {url} - {error_json['code']} - {error_json['errors']}"
                    else:
                        error_message = f"Error requesting: {url} - 0 - {error}"
                except (json.JSONDecodeError, KeyError):
                    error_message = f"Error requesting: {url} - 0 - {error}"

                _LOGGER.error(error_message)
                raise MBAuthError(error_message)

            return await resp.json(content_type=None)
