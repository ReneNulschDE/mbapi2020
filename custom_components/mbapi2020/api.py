"""Define an object to interact with the REST API."""
import json
import logging
import traceback
import uuid
from typing import Optional

from aiohttp import ClientSession, ClientTimeout
from aiohttp.client_exceptions import ClientError

from .const import (
    DISABLE_SSL_CERT_CHECK,
    REGION_CHINA,
    RIS_APPLICATION_VERSION,
    RIS_OS_VERSION,
    RIS_SDK_VERSION,
    SYSTEM_PROXY,
    WEBSOCKET_USER_AGENT,
    WEBSOCKET_USER_AGENT_CN,
    X_APPLICATIONNAME,
)
from .helper import UrlHelper as helper
from .oauth import Oauth

LOGGER = logging.getLogger(__name__)

DEFAULT_LIMIT: int = 288
DEFAULT_TIMEOUT: int = 10


class API:
    """Define the API object."""

    def __init__(self, oauth: Oauth, session: Optional[ClientSession] = None, region: str = None) -> None:
        """Initialize."""
        self._session: ClientSession = session
        self._oauth: Oauth = oauth
        self._region = region

    async def _request(
        self, method: str, endpoint: str, rcp_headers: bool = False, ignore_errors: bool = False, **kwargs
    ) -> list:
        """Make a request against the API."""

        url = f"{helper.Rest_url(self._region)}{endpoint}"
        kwargs.setdefault("headers", {})
        kwargs.setdefault("proxy", SYSTEM_PROXY)
        kwargs.setdefault("ssl", DISABLE_SSL_CERT_CHECK)

        token = await self._oauth.async_get_cached_token()

        if not rcp_headers:
            kwargs["headers"] = {
                "Authorization": f"Bearer {token['access_token']}",
                "X-SessionId": str(uuid.uuid4()),
                "X-TrackingId": str(uuid.uuid4()),
                "X-ApplicationName": X_APPLICATIONNAME,
                "ris-application-version": RIS_APPLICATION_VERSION,
                "ris-os-name": "ios",
                "ris-os-version": RIS_OS_VERSION,
                "ris-sdk-version": RIS_SDK_VERSION,
                "X-Locale": "de-DE",
                "User-Agent": WEBSOCKET_USER_AGENT,
                "Content-Type": "application/json; charset=UTF-8",
            }
        else:
            kwargs["headers"] = {
                "Authorization": f"Bearer {token['access_token']}",
                "User-Agent": WEBSOCKET_USER_AGENT,
                "Accept-Language": "de-DE;q=1.0, en-DE;q=0.9",
            }

        use_running_session = self._session and not self._session.closed

        if use_running_session:
            session = self._session
        else:
            session = ClientSession(timeout=ClientTimeout(total=DEFAULT_TIMEOUT))

        try:
            # async with session.request(method, url, proxy=proxy, ssl=False, **kwargs) as resp:
            if "url" in kwargs:
                async with session.request(method, **kwargs) as resp:
                    # resp.raise_for_status()
                    return await resp.json(content_type=None)
            else:
                async with session.request(method, url, **kwargs) as resp:
                    resp.raise_for_status()
                    return await resp.json(content_type=None)

        except ClientError as err:
            LOGGER.debug(traceback.format_exc())
            if not ignore_errors:
                raise ClientError from err
            else:
                return None
        except Exception:
            LOGGER.debug(traceback.format_exc())
        finally:
            if not use_running_session:
                await session.close()

    async def get_user_info(self) -> list:
        """Get all devices associated with an API key."""
        return await self._request("get", "/v2/vehicles")

    async def get_car_capabilities(self, vin: str) -> list:
        """Get all car capabilities associated with an vin."""
        return await self._request("get", f"/v1/vehicle/{vin}/capabilities")

    async def get_car_capabilities_commands(self, vin: str) -> list:
        """Get all car capabilities associated with an vin."""
        return await self._request("get", f"/v1/vehicle/{vin}/capabilities/commands")

    async def get_car_rcp_supported_settings(self, vin: str) -> list:
        """Get all supported car rcp options associated"""
        url = f"{helper.RCP_url(self._region)}/api/v1/vehicles/{vin}/settings"

        LOGGER.debug("get_car_rcp_supported_settings: %s", url)
        return await self._request("get", "", url=url, rcp_headers=True)

    async def get_car_rcp_settings(self, vin: str, setting: str) -> list:
        """Get all rcp setting for a car"""
        url = f"{helper.RCP_url(self._region)}/api/v1/vehicles/{vin}/settings/{setting}"

        LOGGER.debug("get_car_rcp_settings: %s", url)
        return await self._request("get", "", url=url, rcp_headers=True)

    async def send_route_to_car(
        self, vin: str, title: str, latitude: float, longitude: float, city: str, postcode: str, street: str
    ):
        """Send route to car associated by vin"""
        data = {
            "routeTitle": title,
            "routeType": "singlePOI",
            "waypoints": [
                {
                    "city": city,
                    "latitude": latitude,
                    "longitude": longitude,
                    "postalCode": postcode,
                    "street": street,
                    "title": title,
                }
            ],
        }

        return await self._request("post", f"/v1/vehicle/{vin}/route", data=json.dumps(data))

    async def get_car_geofencing_violations(self, vin: str) -> list:
        """Get all geofencing violations for a car"""
        url = f"/v1/geofencing/vehicles/{vin}/fences/violations"
        return await self._request("get", url, rcp_headers=False, ignore_errors=True)

    async def is_car_rcp_supported(self, vin: str, **kwargs) -> list:
        """return if is car rcp supported"""
        token = await self._oauth.async_get_cached_token()
        headers = {
            "Authorization": f"Bearer {token['access_token']}",
            "User-Agent": WEBSOCKET_USER_AGENT if self._region != REGION_CHINA else WEBSOCKET_USER_AGENT_CN,
        }

        kwargs.setdefault("headers", headers)
        kwargs.setdefault("proxy", SYSTEM_PROXY)
        kwargs.setdefault("ssl", DISABLE_SSL_CERT_CHECK)

        url = f"{helper.PSAG_url(self._region)}/api/app/v2/vehicles/{vin}/profileInformation"

        use_running_session = self._session and not self._session.closed

        if use_running_session:
            session = self._session
        else:
            session = ClientSession(timeout=ClientTimeout(total=DEFAULT_TIMEOUT))

        try:
            async with session.request("get", url, **kwargs) as resp:
                # async with session.request("get", url, headers=headers) as resp:
                resp_status = resp.status
                await resp.text()
                return bool(resp_status == 200)
        finally:
            if not use_running_session:
                await session.close()
