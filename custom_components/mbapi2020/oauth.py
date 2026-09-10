"""Integration of optimized Mercedes Me OAuth2 LoginNew functionality."""

from __future__ import annotations

import asyncio
import base64
import contextlib
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

from custom_components.mbapi2020.errors import (
    MBAuth2FAError,
    MBAuthError,
    MBDeviceAuthDenied,
    MBDeviceAuthTimeout,
    MBLegalTermsError,
    RequestError,
)
from custom_components.mbapi2020.app_version import AppVersionManager
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import (
    AUTH_METHOD_DEVICE,
    CHINA_FATAL_REFRESH_ERRORS,
    CONF_AUTH_METHOD,
    CIAM_DEVICE_AUTH_URL_CN,
    CIAM_DEVICE_GRANT_TYPE,
    CIAM_DEVICE_SCOPE,
    CIAM_DEVICE_TOKEN_URL_CN,
    CIAM_DEVICE_USER_AUTHZ_URL_CN,
    CN_DIRECT_TOKEN_EXPIRES_SECONDS,
    CN_TOKEN_RENEW_CHECK_INTERVAL_SECONDS,
    CN_TOKEN_RENEW_LEEWAY_SECONDS,
    DEFAULT_COUNTRY_CODE,
    DEFAULT_LOCALE,
    LOGIN_APP_ID_CN,
    LOGIN_APP_ID_EU,
    REGION_CHINA,
    RIS_OS_NAME,
    RIS_OS_VERSION,
    RIS_SDK_VERSION,
    SYSTEM_PROXY,
    VERIFY_SSL,
    WEBSOCKET_USER_AGENT,
    WEBSOCKET_USER_AGENT_CN,
)
from .helper import LogHelper, UrlHelper as helper

_LOGGER = logging.getLogger(__name__)

GATEWAY_ERROR_CODES = (502, 503, 504)
LOGIN_MAX_ATTEMPTS = 3
LOGIN_RETRY_BACKOFF_SECONDS = 5


class Oauth:
    """OAuth2 class for Mercedes Me integration."""

    # OAuth2 Configuration for new login method
    CLIENT_ID = LOGIN_APP_ID_EU
    REDIRECT_URI = "rismycar://login-callback"
    SCOPE = "email profile ciam-uid phone openid offline_access"

    def __init__(
        self,
        hass: HomeAssistant,
        session: ClientSession,
        region: str,
        config_entry: ConfigEntry,
        app_version: AppVersionManager,
    ) -> None:
        """Initialize the extended OAuth instance."""
        self._session: ClientSession = session
        self._region: str = region
        self._hass = hass
        self._config_entry = config_entry
        self._app_version = app_version
        self.token = None
        self._sessionid = ""
        self._get_token_lock = asyncio.Lock()
        self._device_guid: str = (config_entry.data.get("device_guid") if config_entry else None) or str(uuid.uuid4())

        if region == REGION_CHINA:
            self.CLIENT_ID = LOGIN_APP_ID_CN

        # PKCE parameters for new login method
        self.code_verifier: str | None = None
        self.code_challenge: str | None = None
        self._renewal_task: asyncio.Task | None = None

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

        # create a fresh session with CIAM.DEVICE cookie
        device_guid = self._device_guid
        cookie_jar = aiohttp.CookieJar()
        cookie_jar.update_cookies({"CIAM.DEVICE": device_guid})
        self._session = async_create_clientsession(self._hass, verify_ssl=VERIFY_SSL, cookie_jar=cookie_jar)

        try:
            # Step 1: Get authorization URL and extract resume parameter
            resume_url = await self._get_authorization_resume()

            # Step 2: Send user agent information
            await self._send_user_agent_info()

            # Step 3: Submit username
            await self._submit_username(email)

            # Step 4: Submit password and get pre-login token
            rid = secrets.token_urlsafe(24)
            pre_login_data = await self._submit_password(email, password, rid)

            # Step 4b: Decline the passkey setup prompt if the account gets offered one
            if pre_login_data and pre_login_data.get("passkeyDemoEnabled"):
                _LOGGER.debug("Passkey setup prompt detected - declining to continue password login")
                pre_login_data = await self._disable_passkey_demo(email, password, rid)

            if pre_login_data and pre_login_data.get("result", "") != "RESUME2OIDCP":
                if pre_login_data.get("result", "") == "GOTO_LOGIN_OTP":
                    raise MBAuth2FAError("Two-factor authentication (2FA) is not supported.")

                if pre_login_data.get("result", "") == "GOTO_LOGIN_LEGAL_TEXTS":
                    home_ountry = pre_login_data.get("homeCountry", "")
                    consent_country = pre_login_data.get("consentCountry", "")
                    pre_login_data = await self._submit_legal_consent(home_ountry, consent_country)
                    if pre_login_data.get("result", "") != "RESUME2OIDCP":
                        raise MBLegalTermsError("Problem accepting legal terms during login. %s", pre_login_data)
                else:
                    raise MBAuthError("Unexpected login result: %s", pre_login_data)

            # Step 5: Resume authorization and get code
            auth_code = await self._resume_authorization(resume_url, pre_login_data["token"])

            # Step 6: Exchange code for tokens
            token_info = await self._exchange_code_for_tokens(auth_code)

            # Add custom values and save token
            token_info = self._add_custom_values_to_token_info(token_info)
            self._save_token_info(token_info)
            self.token = token_info

            self.code_verifier = None
            self.code_challenge = None

            _LOGGER.info("OAuth2 login successful")
            return token_info

        except (MBAuth2FAError, MBLegalTermsError):
            raise
        except Exception as e:
            _LOGGER.error("OAuth2 login failed: %s", e)
            raise MBAuthError(f"Login failed: {e}") from e

    def _get_mobile_safari_headers(
        self,
        accept: str = "application/json, text/plain, */*",
        include_referer: bool = True,
    ) -> dict[str, str]:
        """Build headers with mobile Safari user agent and common fields."""
        base_url = helper.Login_Base_Url(self._region)
        headers = {
            "accept": accept,
            "content-type": "application/json",
            "origin": base_url,
            "accept-language": "de-DE,de;q=0.9",
            "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_8_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.6.6 Mobile/15E148 Safari/604.1",
        }

        if include_referer:
            headers["referer"] = f"{base_url}/ciam/auth/login"

        return headers

    async def _login_request(self, method: str, url: str, step: str, **kwargs) -> tuple[int, str, str]:
        """Perform a login step request, retrying transient gateway errors.

        Returns:
            tuple: (status, final_url, body_text)

        """
        kwargs.setdefault("proxy", SYSTEM_PROXY)

        for attempt in range(1, LOGIN_MAX_ATTEMPTS + 1):
            async with self._session.request(method, url, **kwargs) as response:
                if response.status in GATEWAY_ERROR_CODES and attempt < LOGIN_MAX_ATTEMPTS:
                    _LOGGER.warning(
                        "%s failed with %s - retry %s/%s",
                        step,
                        response.status,
                        attempt,
                        LOGIN_MAX_ATTEMPTS - 1,
                    )
                else:
                    return response.status, str(response.url), await response.text()

            await asyncio.sleep(LOGIN_RETRY_BACKOFF_SECONDS * attempt)

        raise MBAuthError(f"{step} failed after {LOGIN_MAX_ATTEMPTS} attempts")

    def _extract_code_from_redirect_url(self, redirect_url: str) -> str:
        """Extract authorization code from redirect URL."""
        parsed_url = urllib.parse.urlparse(redirect_url)
        params = urllib.parse.parse_qs(parsed_url.query)
        code = params.get("code", [None])[0]

        if not code:
            raise MBAuthError("Authorization code not found in redirect URL")

        return code

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

        status, final_url, _ = await self._login_request(
            "get", auth_url, "Authorization request", params=params, headers=headers, allow_redirects=True
        )
        if status >= 400:
            raise MBAuthError(f"Authorization request failed: {status}")

        parsed_url = urllib.parse.urlparse(final_url)
        url_params = urllib.parse.parse_qs(parsed_url.query)
        resume = url_params.get("resume", [None])[0]

        if not resume:
            raise MBAuthError("Resume parameter not found in authorization response")

        return resume

    async def _send_user_agent_info(self) -> None:
        """Send user agent information."""
        headers = self._get_mobile_safari_headers(
            accept="*/*",
            include_referer=False,
        )

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
        headers = self._get_mobile_safari_headers()
        url = f"{helper.Login_Base_Url(self._region)}/ciam/auth/login/user"

        status, _, body = await self._login_request(
            "post", url, "Username submission", json={"username": email}, headers=headers
        )
        if status >= 400:
            raise MBAuthError(f"Username submission failed: {status} - {body}")

    async def _submit_password(self, email: str, password: str, rid: str) -> dict[str, Any]:
        """Submit password and get pre-login data."""
        headers = self._get_mobile_safari_headers()

        data = {
            "username": email,
            "password": password,
            "rememberMe": False,
            "rid": rid,
        }

        url = f"{helper.Login_Base_Url(self._region)}/ciam/auth/login/pass"

        status, _, body = await self._login_request("post", url, "Password submission", json=data, headers=headers)
        if status >= 400:
            raise MBAuthError(f"Password submission failed: {status} - {body}")

        return json.loads(body)

    async def _disable_passkey_demo(self, email: str, password: str, rid: str) -> dict[str, Any]:
        """Decline the passkey setup prompt and continue the login flow."""
        headers = self._get_mobile_safari_headers()

        data = {
            "username": email,
            "password": password,
            "rememberMe": False,
            "rid": rid,
            "disablePasskeyDemo": True,
        }

        url = f"{helper.Login_Base_Url(self._region)}/ciam/auth/disablePasskeyDemo"

        status, _, body = await self._login_request("post", url, "Passkey prompt skip", json=data, headers=headers)
        if status >= 400:
            raise MBAuthError(f"Passkey prompt skip failed: {status} - {body}")

        return json.loads(body)

    async def _submit_legal_consent(self, home_country: str, consent_country: str) -> dict[str, Any]:
        """Submit legal consent and get pre-login data."""
        headers = self._get_mobile_safari_headers()

        data = {
            "texts": {},
            "homeCountry": home_country,
            "consentCountry": consent_country,
        }

        url = f"{helper.Login_Base_Url(self._region)}/ciam/auth/toas/saveLoginConsent"

        async with self._session.post(url, json=data, headers=headers, proxy=SYSTEM_PROXY) as response:
            if response.status >= 400:
                error_text = await response.text()
                raise MBAuthError(f"legal_consent submission failed: {response.status} - {error_text}")

            return await response.json()

    async def _resume_authorization(self, resume_url: str, token: str) -> str:
        """Resume authorization and extract code."""
        headers = self._get_mobile_safari_headers()
        headers["accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        headers["content-type"] = "application/x-www-form-urlencoded"

        data = aiohttp.FormData({"token": token})

        try:
            async with self._session.post(
                f"{helper.Login_Base_Url(self._region)}{resume_url}",
                data=data,
                headers=headers,
                proxy=SYSTEM_PROXY,
                allow_redirects=False,
            ) as response:
                if response.status in (302, 301):
                    redirect_url = response.headers.get("location", "")
                    if redirect_url.startswith("rismycar://"):
                        return self._extract_code_from_redirect_url(redirect_url)

                raise MBAuthError(f"Unexpected response during authorization: {response.status}")

        except aiohttp.InvalidURL as e:
            # Handle custom scheme redirect
            error_str = str(e)
            if "rismycar://" in error_str:
                # Extract URL from error message
                start = error_str.find("'") + 1
                end = error_str.find("'", start)
                redirect_url = error_str[start:end]

                try:
                    return self._extract_code_from_redirect_url(redirect_url)
                except MBAuthError as extract_error:
                    raise MBAuthError("Authorization code not found in redirect URL") from extract_error

            raise MBAuthError(f"Unexpected URL error: {e}") from e

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

    async def request_access_token_with_pin(self, email: str, pin: str, nonce: str):
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
        headers["X-Device-Id"] = self._device_guid
        headers["X-Request-Id"] = str(uuid.uuid4())

        token_info = await self._async_request("post", url, data=data, headers=headers)

        if token_info is not None:
            token_info = self._add_custom_values_to_token_info(token_info)
            self._save_token_info(token_info)
            self.token = token_info
            return token_info

        return None

    async def request_pin(self, email: str, nonce: str):
        """Initiate a PIN request."""
        _LOGGER.info("Start request PIN %s", LogHelper.Mask_email(email))
        _LOGGER.debug("PIN preflight request 1")
        await self._app_version.async_refresh(self._session, force=True)
        headers = self._get_header()
        url = f"{helper.Rest_url(self._region)}/v1/config"
        await self._async_request("get", url, headers=headers)

        _LOGGER.info("PIN request")
        url = f"{helper.Rest_url(self._region)}/v1/login"
        data = json.dumps({"emailOrPhoneNumber": email, "countryCode": DEFAULT_COUNTRY_CODE, "nonce": nonce})
        headers = self._get_header()
        return await self._async_request("post", url, data=data, headers=headers)

    @staticmethod
    def china_device_verify_url(user_code: str) -> str:
        """Return the PingFederate Connect-a-device page.

        Do not append ``user_code``. Sign in first on the public Mercedes
        website, then type the code on this page.
        """
        del user_code
        return CIAM_DEVICE_USER_AUTHZ_URL_CN

    async def async_request_device_code(self) -> dict[str, Any]:
        """Start the official China OAuth device-code login."""
        if self._region != REGION_CHINA:
            raise MBAuthError("Device-code login is only available for the China region")

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": WEBSOCKET_USER_AGENT_CN,
        }
        data = urllib.parse.urlencode(
            {
                "client_id": helper.Login_App_Id(self._region),
                "scope": CIAM_DEVICE_SCOPE,
            }
        )
        async with self._session.post(
            CIAM_DEVICE_AUTH_URL_CN,
            data=data,
            headers=headers,
            proxy=SYSTEM_PROXY,
        ) as response:
            body = await response.json(content_type=None)
            if response.status >= 400 or not isinstance(body, dict) or not body.get("device_code"):
                raise MBAuthError(f"China device authorization failed: {response.status} - {body}")

            user_code = body["user_code"]
            body["verification_uri_complete"] = self.china_device_verify_url(user_code)
            _LOGGER.info(
                "China device-code login started (user_code=%s, expires_in=%s)",
                user_code,
                body.get("expires_in"),
            )
            return body

    async def async_poll_device_token(
        self,
        device_code: str,
        interval: int,
        expires_in: int,
    ) -> dict[str, Any]:
        """Poll CIAM until the official China login page authorizes this device."""
        deadline = time.monotonic() + max(int(expires_in), 30)
        poll_interval = max(int(interval), 5)
        headers = self._get_header()
        headers.update(self._ciam_token_headers())
        data = urllib.parse.urlencode(
            {
                "grant_type": CIAM_DEVICE_GRANT_TYPE,
                "device_code": device_code,
                "client_id": helper.Login_App_Id(self._region),
            }
        )

        while time.monotonic() < deadline:
            await asyncio.sleep(poll_interval)
            async with self._session.post(
                CIAM_DEVICE_TOKEN_URL_CN,
                data=data,
                headers=headers,
                proxy=SYSTEM_PROXY,
            ) as response:
                body = await response.json(content_type=None)
                if response.status < 400 and isinstance(body, dict) and body.get("access_token"):
                    token_info = self._add_custom_values_to_token_info(body)
                    token_info["china_direct"] = True
                    self._save_token_info(token_info)
                    self.token = token_info
                    _LOGGER.info("China device-code login completed")
                    return token_info

                error = body.get("error") if isinstance(body, dict) else None
                if error == "authorization_pending":
                    continue
                if error == "slow_down":
                    poll_interval += 5
                    continue
                if error in {"expired_token", "expired"}:
                    raise MBDeviceAuthTimeout("China device-code login expired")
                if error == "access_denied":
                    raise MBDeviceAuthDenied("China device-code login was denied")
                raise MBAuthError(f"China device-code token poll failed: {response.status} - {body}")

        raise MBDeviceAuthTimeout("China device-code login timed out")

    def _ciam_token_headers(self) -> dict[str, str]:
        """Headers for China PingFederate token.oauth2."""
        return {
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "Accept": "application/json",
            "User-Agent": WEBSOCKET_USER_AGENT_CN,
            "Stage": "prod",
            "X-Device-Id": self._device_guid,
            "device-uuid": self._device_guid,
            "X-Request-Id": str(uuid.uuid4()),
        }

    def _persist_token_info(
        self, token_info: dict[str, Any], previous_refresh_token: str | None = None
    ) -> dict[str, Any]:
        """Merge, persist and activate a CIAM token response."""
        previous = deepcopy(self.token) if self.token else {}
        new_refresh = token_info.get("refresh_token")
        if not new_refresh and previous_refresh_token:
            token_info["refresh_token"] = previous_refresh_token
        elif new_refresh and new_refresh != previous_refresh_token:
            _LOGGER.info("Mercedes returned a rotated refresh_token; persisting it")
        if not token_info.get("expires_in"):
            token_info["expires_in"] = CN_DIRECT_TOKEN_EXPIRES_SECONDS
        token_info = self._add_custom_values_to_token_info(token_info)
        token_info = self._preserve_china_direct_metadata(token_info, previous)
        for key in ("scope", "id_token", "token_type"):
            if not token_info.get(key) and previous.get(key):
                token_info[key] = previous[key]
        self._save_token_info(token_info)
        self.token = token_info
        self._log_china_direct_token_status(token_info, "refreshed")
        return token_info

    async def _async_refresh_china_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Refresh a China device-code token with the same client_id that issued it."""
        _LOGGER.info("Refreshing China CIAM token")
        if not self._session or self._session.closed:
            cookie_jar = aiohttp.CookieJar()
            cookie_jar.update_cookies(
                {"CIAM.DEVICE": self._device_guid},
                response_url=aiohttp.URL("https://ciam-1.mercedes-benz.com.cn/"),
            )
            self._session = async_create_clientsession(self._hass, verify_ssl=VERIFY_SSL, cookie_jar=cookie_jar)

        data = urllib.parse.urlencode(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": helper.Login_App_Id(self._region),
            }
        )
        headers = self._get_header()
        headers.update(self._ciam_token_headers())
        async with self._session.post(
            CIAM_DEVICE_TOKEN_URL_CN,
            data=data,
            headers=headers,
            proxy=SYSTEM_PROXY,
        ) as response:
            text = await response.text()
            try:
                body = json.loads(text) if text else {}
            except json.JSONDecodeError:
                body = {"error_description": text[:300]}

            if response.status < 400 and isinstance(body, dict) and body.get("access_token"):
                _LOGGER.info(
                    "China CIAM refresh succeeded (expires_in=%s, refresh_token_returned=%s)",
                    body.get("expires_in"),
                    bool(body.get("refresh_token")),
                )
                return self._persist_token_info(body, refresh_token)

            error = body.get("error") if isinstance(body, dict) else None
            description = body.get("error_description") if isinstance(body, dict) else text[:300]
            message = f"China token refresh failed: {response.status} - {error} - {description}"
            if error in CHINA_FATAL_REFRESH_ERRORS:
                err = MBAuthError(message)
                err.oauth_error = error
                raise err
            raise RequestError(message)

    async def async_refresh_access_token(self, refresh_token: str, is_retry: bool = False):
        """Refresh the access token."""
        _LOGGER.info("Start async_refresh_access_token() with refresh_token")

        if self._region == REGION_CHINA:
            return await self._async_refresh_china_access_token(refresh_token)

        _LOGGER.debug("Auth token refresh preflight request 1")
        await self._app_version.async_refresh(self._session, force=True)
        headers = self._get_header()
        url = f"{helper.Rest_url(self._region)}/v1/config"
        await self._async_request("get", url, headers=headers)

        url = f"{helper.Login_Base_Url(self._region)}/as/token.oauth2"
        data = f"grant_type=refresh_token&refresh_token={refresh_token}"

        headers = self._get_header()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["X-Device-Id"] = self._device_guid
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

    def _preserve_china_direct_metadata(self, token_info: dict, previous: dict | None) -> dict:
        """Keep the China device-code session marker across refresh_token renewals."""
        previous = previous or {}
        if previous.get("china_direct") or token_info.get("china_direct"):
            token_info["china_direct"] = True
        return token_info

    def _is_china_session_active(self) -> bool:
        """Return whether this entry belongs to the China region."""
        return bool(self._region == REGION_CHINA and self._config_entry)

    async def async_prepare_china_session(self) -> None:
        """Validate the stored token and start auto-renewal before the first API call."""
        if not self._is_china_session_active():
            return

        token_info = self.token
        if not token_info and "token" in self._config_entry.data:
            token_info = deepcopy(self._config_entry.data["token"])
        if not token_info:
            _LOGGER.warning("China session has no stored token - reauth required")
            return

        if self._config_entry.data.get(CONF_AUTH_METHOD) in {"token", AUTH_METHOD_DEVICE}:
            token_info["china_direct"] = True
        self.token = token_info
        self._log_china_direct_token_status(token_info, "prepare")

        try:
            token_info = await self._maybe_refresh_token(token_info, "prepare")
        except MBAuthError:
            return
        if token_info is not None:
            self.token = token_info

        self.async_start_renewal_watchdog()

    async def _maybe_refresh_token(self, token_info: dict | None, context: str) -> dict | None:
        """Refresh the access token when the proactive renewal window is reached."""
        if not token_info or not self.should_refresh_token(token_info):
            return token_info

        async with self._get_token_lock:
            current = self.token or token_info
            if not self.should_refresh_token(current):
                return current

            if not current.get("refresh_token"):
                _LOGGER.warning("Refresh token is missing - reauth required")
                self.start_reauth_flow()
                return None

            _LOGGER.info("Mercedes token proactive renewal triggered (%s)", context)
            try:
                refreshed = await self.async_refresh_access_token(current["refresh_token"], is_retry=False)
            except MBAuthError as err:
                oauth_error = getattr(err, "oauth_error", None)
                if self._region == REGION_CHINA and oauth_error not in CHINA_FATAL_REFRESH_ERRORS:
                    _LOGGER.warning(
                        "Token refresh failed (%s): %s; keeping current token and retrying later",
                        context,
                        err,
                    )
                    return current
                _LOGGER.error("Mercedes refresh_token rejected (%s) - starting reauth flow", context)
                self.start_reauth_flow()
                raise
            except (aiohttp.ClientError, RequestError) as err:
                _LOGGER.warning("Token refresh failed due to a transient error (%s): %s", context, err)
                return current
            return refreshed or current

    def start_reauth_flow(self) -> None:
        """Ask Home Assistant to show the reauth flow for this entry."""
        if self._config_entry is None:
            return
        try:
            self._config_entry.async_start_reauth(self._hass)
        except Exception:  # pragma: no cover - reauth must never crash callers
            _LOGGER.exception("Failed to start reauth flow")

    def async_start_renewal_watchdog(self) -> None:
        """Start a background loop that renews China tokens before they expire."""
        if not self._is_china_session_active():
            return
        if self._renewal_task and not self._renewal_task.done():
            return
        self._renewal_task = asyncio.create_task(self._renewal_watchdog_loop())

    async def async_stop_renewal_watchdog(self) -> None:
        """Stop the background token renewal loop."""
        if self._renewal_task is None:
            return
        task = self._renewal_task
        self._renewal_task = None
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _renewal_watchdog_loop(self) -> None:
        """Periodically refresh China tokens ahead of local expiry."""
        while self._is_china_session_active():
            try:
                token_info = self.token
                if not token_info and self._config_entry and "token" in self._config_entry.data:
                    token_info = deepcopy(self._config_entry.data["token"])
                if token_info:
                    refreshed = await self._maybe_refresh_token(token_info, "watchdog")
                    if refreshed is not None:
                        self.token = refreshed
            except asyncio.CancelledError:
                raise
            except MBAuthError:
                _LOGGER.error("Token renewal watchdog: refresh rejected, reauth flow started; stopping watchdog")
                self._renewal_task = None
                return
            except Exception:
                _LOGGER.exception("China token renewal watchdog failed")
            await asyncio.sleep(CN_TOKEN_RENEW_CHECK_INTERVAL_SECONDS)

    async def async_get_cached_token(self):
        """Get a cached auth token."""
        token_info: dict[str, any]

        if self.token:
            token_info = self.token
        elif self._config_entry and self._config_entry.data and "token" in self._config_entry.data:
            token_info = deepcopy(self._config_entry.data["token"])
        else:
            _LOGGER.warning("No token information - reauth required")
            return None

        if self._region == REGION_CHINA:
            token_info = await self._maybe_refresh_token(token_info, "cached")
            if token_info is None:
                return None
            self.token = token_info
            return token_info

        if self.is_token_expired(token_info):
            async with self._get_token_lock:
                if not self.is_token_expired(self.token or token_info):
                    token_info = self.token
                else:
                    _LOGGER.debug("%s token expired -> start refresh", __name__)
                    if not token_info or "refresh_token" not in token_info:
                        _LOGGER.warning("Refresh token is missing - reauth required")
                        return None

                    token_info = await self.async_refresh_access_token(token_info["refresh_token"], is_retry=False)

        self.token = token_info
        return token_info

    @classmethod
    def _china_direct_token_remaining_seconds(cls, token_info: dict | None) -> int | None:
        """Return seconds until local expiry hint, if available."""
        if not token_info:
            return None
        expires_at = token_info.get("expires_at")
        if not expires_at:
            return None
        return int(expires_at) - int(time.time())

    @classmethod
    def _log_china_direct_token_status(cls, token_info: dict | None, context: str) -> None:
        """Log China token lifetime for troubleshooting."""
        if not token_info or not token_info.get("china_direct"):
            return
        remaining = cls._china_direct_token_remaining_seconds(token_info)
        if remaining is None:
            _LOGGER.warning("China token (%s): missing expires_at", context)
            return
        if remaining < 0:
            _LOGGER.info("China token (%s): local expiry passed %s seconds ago", context, abs(remaining))
            return
        _LOGGER.info("China token (%s): local expiry in %s minutes", context, round(remaining / 60, 1))

    @classmethod
    def should_refresh_token(cls, token_info: dict | None) -> bool:
        """Return whether the access token should be renewed proactively."""
        if token_info is None:
            return True
        if token_info.get("china_direct") and not token_info.get("refresh_token"):
            return False

        expires_at = token_info.get("expires_at")
        if not expires_at:
            return True

        remaining = int(expires_at) - int(time.time())
        return remaining < CN_TOKEN_RENEW_LEEWAY_SECONDS

    @classmethod
    def is_token_expired(cls, token_info) -> bool:
        """Check if the token is expired."""
        if token_info is not None and token_info.get("china_direct"):
            return cls.should_refresh_token(token_info)
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

            # Ensure device_guid is preserved
            if self._device_guid:
                new_config_entry_data["device_guid"] = self._device_guid

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
        return self._app_version.apply_oauth_headers(header)

    async def _async_request(self, method: str, url: str, data: str = "", **kwargs):
        """Make a request against the API."""
        kwargs.setdefault("headers", {})
        kwargs.setdefault("proxy", SYSTEM_PROXY)

        if not self._session or self._session.closed:
            device_guid = self._device_guid
            cookie_jar = aiohttp.CookieJar()
            cookie_jar.update_cookies({"CIAM.DEVICE": device_guid})
            self._session = async_create_clientsession(self._hass, verify_ssl=VERIFY_SSL, cookie_jar=cookie_jar)

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
