"""Runtime app-version handling for Mercedes mobile SDK requests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import re
import time
from urllib.parse import urlencode
import uuid
from typing import Any

from aiohttp import ClientError, ClientSession

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
    RIS_SDK_VERSION_CN,
    SYSTEM_PROXY,
    WEBSOCKET_USER_AGENT,
    WEBSOCKET_USER_AGENT_CN,
)
from .helper import UrlHelper as helper

LOGGER = logging.getLogger(__name__)

APP_VERSION_CHECK_INTERVAL_SECONDS = 21600
UPDATE_REQUIRED_STATUSES = {"FORCE", "INFORM_ALWAYS"}
APP_STORE_COUNTRY_BY_REGION = {
    REGION_APAC: "au",
    REGION_CHINA: "cn",
    REGION_EUROPE: "de",
    REGION_NORAM: "us",
}
APP_STORE_ID_PATTERN = re.compile(r"/id(\d+)")


@dataclass(slots=True)
class RegionAppProfile:
    """Static per-region mobile app request profile."""

    application_name: str
    default_version: str
    sdk_version: str
    oauth_user_agent: str
    webapi_user_agent: str
    websocket_user_agent_template: str | None = None
    websocket_user_agent_static: str | None = None


def _build_region_profile(region: str) -> RegionAppProfile:
    """Return the default request profile for a region."""
    match region:
        case current if current == REGION_NORAM:
            return RegionAppProfile(
                application_name="mycar-store-us",
                default_version=RIS_APPLICATION_VERSION_NA,
                sdk_version=RIS_SDK_VERSION,
                oauth_user_agent=WEBSOCKET_USER_AGENT,
                webapi_user_agent=WEBSOCKET_USER_AGENT,
                websocket_user_agent_template=(
                    f"mycar-store-us v{{version}}, {RIS_OS_NAME} {RIS_OS_VERSION}, SDK {RIS_SDK_VERSION}"
                ),
            )
        case current if current == REGION_APAC:
            return RegionAppProfile(
                application_name="mycar-store-ap",
                default_version=RIS_APPLICATION_VERSION_PA,
                sdk_version=RIS_SDK_VERSION,
                oauth_user_agent=(
                    f"mycar-store-ap {RIS_APPLICATION_VERSION_PA}, {RIS_OS_NAME} {RIS_OS_VERSION}, SDK {RIS_SDK_VERSION}"
                ),
                webapi_user_agent=WEBSOCKET_USER_AGENT,
                websocket_user_agent_template=(
                    f"mycar-store-ap {{version}}, {RIS_OS_NAME} {RIS_OS_VERSION}, SDK {RIS_SDK_VERSION}"
                ),
            )
        case current if current == REGION_CHINA:
            return RegionAppProfile(
                application_name="mycar-store-cn",
                default_version=RIS_APPLICATION_VERSION_CN,
                sdk_version=RIS_SDK_VERSION_CN,
                oauth_user_agent=WEBSOCKET_USER_AGENT_CN,
                webapi_user_agent=WEBSOCKET_USER_AGENT_CN,
                websocket_user_agent_static=WEBSOCKET_USER_AGENT_CN,
            )
        case _:
            return RegionAppProfile(
                application_name="mycar-store-ece",
                default_version=RIS_APPLICATION_VERSION,
                sdk_version=RIS_SDK_VERSION,
                oauth_user_agent=WEBSOCKET_USER_AGENT,
                webapi_user_agent=WEBSOCKET_USER_AGENT,
                websocket_user_agent_static=WEBSOCKET_USER_AGENT,
            )


class AppVersionManager:
    """Resolve and cache app-version requirements from the BFF config endpoint."""

    def __init__(self, region: str) -> None:
        """Initialize the manager."""
        self._region = region
        self._profile = _build_region_profile(region)
        self._application_version = self._profile.default_version
        self._last_check_monotonic = 0.0
        self._lock = asyncio.Lock()

    @property
    def application_name(self) -> str:
        """Return the request application name."""
        return self._profile.application_name

    @property
    def application_version(self) -> str:
        """Return the current request application version."""
        return self._application_version

    @property
    def sdk_version(self) -> str:
        """Return the SDK version for the region."""
        return self._profile.sdk_version

    def oauth_user_agent(self) -> str:
        """Return the user agent used for OAuth/config calls."""
        if self._region == REGION_APAC:
            return f"mycar-store-ap {self._application_version}, {RIS_OS_NAME} {RIS_OS_VERSION}, SDK {RIS_SDK_VERSION}"
        return self._profile.oauth_user_agent

    def webapi_user_agent(self) -> str:
        """Return the user agent used for REST API calls."""
        return self._profile.webapi_user_agent

    def websocket_user_agent(self) -> str:
        """Return the user agent used for websocket calls."""
        if self._profile.websocket_user_agent_template:
            return self._profile.websocket_user_agent_template.format(version=self._application_version)
        return self._profile.websocket_user_agent_static or self._profile.webapi_user_agent

    async def async_refresh(self, session: ClientSession, force: bool = False) -> bool:
        """Refresh the application version from the config endpoint when needed."""
        if not force and (time.monotonic() - self._last_check_monotonic) < APP_VERSION_CHECK_INTERVAL_SECONDS:
            return False

        async with self._lock:
            if not force and (time.monotonic() - self._last_check_monotonic) < APP_VERSION_CHECK_INTERVAL_SECONDS:
                return False

            config = await self._fetch_remote_config(session)
            self._last_check_monotonic = time.monotonic()
            if not isinstance(config, dict):
                return False

            force_update = config.get("forceUpdate")
            if not isinstance(force_update, dict):
                return False

            status = force_update.get("status")
            if status not in UPDATE_REQUIRED_STATUSES:
                return False

            new_version = await self._lookup_app_store_version(session, force_update.get("storeUrl"))
            if not new_version:
                LOGGER.warning(
                    (
                        "Mercedes app config requested status %s for %s, but no newer version could be "
                        "resolved from the App Store fallback."
                    ),
                    status,
                    self._region,
                )
                return False
            if new_version == self._application_version:
                return False

            LOGGER.info(
                "Updating Mercedes app version for %s from %s to %s based on /v1/config status %s.",
                self._region,
                self._application_version,
                new_version,
                status,
            )
            self._application_version = new_version
            return True

    async def _fetch_remote_config(self, session: ClientSession) -> dict[str, Any] | None:
        """Fetch the remote application config."""
        headers = {
            "Ris-Os-Name": RIS_OS_NAME,
            "Ris-Os-Version": RIS_OS_VERSION,
            "Ris-Sdk-Version": self.sdk_version,
            "Ris-Application-Version": self._application_version,
            "X-Applicationname": self.application_name,
            "X-Locale": DEFAULT_LOCALE,
            "X-Trackingid": str(uuid.uuid4()),
            "X-Sessionid": str(uuid.uuid4()),
            "User-Agent": self.oauth_user_agent(),
            "Content-Type": "application/json",
            "Accept-Language": DEFAULT_LOCALE,
        }
        url = f"{helper.Rest_url(self._region)}/v1/config"

        try:
            async with session.get(url, headers=headers, proxy=SYSTEM_PROXY) as response:
                if response.status >= 400:
                    LOGGER.debug(
                        "Skipping app-version refresh for %s, config returned HTTP %s",
                        self._region,
                        response.status,
                    )
                    return None
                return await response.json(content_type=None)
        except (ClientError, ValueError) as err:
            LOGGER.debug("Failed to refresh Mercedes app version for %s: %s", self._region, err)
            return None

    async def _lookup_app_store_version(self, session: ClientSession, store_url: Any) -> str | None:
        """Look up the latest App Store version from a Mercedes-provided store URL."""
        if not isinstance(store_url, str):
            return None

        match = APP_STORE_ID_PATTERN.search(store_url)
        if not match:
            LOGGER.debug("Could not extract App Store ID from %s", store_url)
            return None

        params = {"id": match.group(1)}
        if country := APP_STORE_COUNTRY_BY_REGION.get(self._region):
            params["country"] = country

        url = f"https://itunes.apple.com/lookup?{urlencode(params)}"

        try:
            async with session.get(url, proxy=SYSTEM_PROXY) as response:
                if response.status >= 400:
                    LOGGER.debug(
                        "App Store lookup for %s returned HTTP %s",
                        self._region,
                        response.status,
                    )
                    return None

                payload = await response.json(content_type=None)
        except (ClientError, ValueError) as err:
            LOGGER.debug("Failed App Store lookup for %s: %s", self._region, err)
            return None

        results = payload.get("results")
        if not isinstance(results, list) or not results:
            return None

        version = results[0].get("version")
        return version if isinstance(version, str) else None

    def apply_oauth_headers(self, header: dict[str, str]) -> dict[str, str]:
        """Apply region-specific OAuth request headers."""
        header["X-Applicationname"] = self.application_name
        header["Ris-Application-Version"] = self._application_version
        header["Ris-Sdk-Version"] = self.sdk_version
        header["User-Agent"] = self.oauth_user_agent()
        return header

    def apply_webapi_headers(self, header: dict[str, str]) -> dict[str, str]:
        """Apply region-specific REST API headers."""
        header["X-ApplicationName"] = self.application_name
        header["ris-application-version"] = self._application_version
        header["ris-sdk-version"] = self.sdk_version
        header["User-Agent"] = self.webapi_user_agent()
        return header

    def apply_websocket_headers(self, header: dict[str, str]) -> dict[str, str]:
        """Apply region-specific websocket headers."""
        header["X-ApplicationName"] = self.application_name
        header["ris-application-version"] = self._application_version
        header["ris-sdk-version"] = self.sdk_version
        header["User-Agent"] = self.websocket_user_agent()
        if self._region == REGION_NORAM:
            header["X-Locale"] = "en-US"
            header["Accept-Encoding"] = "gzip"
            header["Sec-WebSocket-Extensions"] = "permessage-deflate"
        return header
