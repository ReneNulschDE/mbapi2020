"""Define an object to interact with the REST API."""

from __future__ import annotations

import json
import logging
import ssl
import traceback
import uuid

from aiohttp import ClientSession
from aiohttp.client_exceptions import ClientError
import google.protobuf.message

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    REGION_CHINA,
    RIS_APPLICATION_VERSION,
    RIS_OS_VERSION,
    RIS_SDK_VERSION,
    SYSTEM_PROXY,
    VERIFY_SSL,
    WEBSOCKET_USER_AGENT,
    WEBSOCKET_USER_AGENT_CN,
    X_APPLICATIONNAME,
)
from .helper import UrlHelper as helper
from .oauth import Oauth
from .proto import vehicle_events_pb2

LOGGER = logging.getLogger(__name__)


class WebApi:
    """Define the API object."""

    def __init__(
        self,
        hass: HomeAssistant,
        oauth: Oauth,
        session: ClientSession,
        region: str,
    ) -> None:
        """Initialize."""
        self._session: ClientSession = session
        self._oauth: Oauth = oauth
        self._region = region
        self.hass = hass
        self.session_id = str(uuid.uuid4()).upper()

    async def _request(
        self,
        method: str,
        endpoint: str,
        rcp_headers: bool = False,
        ignore_errors: bool = False,
        return_as_json: bool = True,
        **kwargs,
    ):
        """Make a request against the API."""

        url = f"{helper.Rest_url(self._region)}{endpoint}"
        kwargs.setdefault("headers", {})
        kwargs.setdefault("proxy", SYSTEM_PROXY)

        token = await self._oauth.async_get_cached_token()

        if not rcp_headers:
            kwargs["headers"] = {
                "Authorization": f"Bearer {token['access_token']}",
                "X-SessionId": self.session_id,
                "X-TrackingId": str(uuid.uuid4()).upper(),
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

        if not self._session or self._session.closed:
            self._session = async_get_clientsession(self.hass, VERIFY_SSL)

        try:
            if "url" in kwargs:
                async with self._session.request(method, **kwargs) as resp:
                    # resp.raise_for_status()
                    if return_as_json:
                        return await resp.json(content_type=None)

                    return await resp.read()
            else:
                async with self._session.request(method, url, **kwargs) as resp:
                    if 400 <= resp.status < 500:
                        try:
                            error = await resp.text()
                            error_json = json.loads(error)
                            if error_json:
                                error_message = f"Error requesting: {url} - {resp.status} -  {error_json['code']} - {error_json['errors']}"
                            else:
                                error_message = f"Error requesting: {url} - {resp.status} - 0 - {error}"
                        except (json.JSONDecodeError, KeyError):
                            error_message = f"Error requesting: {url} - {resp.status} - 0 - {error}"

                        LOGGER.error(error_message) if not ignore_errors else LOGGER.info(error_message)
                    else:
                        resp.raise_for_status()

                    if return_as_json:
                        return await resp.json(content_type=None)

                    return await resp.read()

        except ClientError as err:
            LOGGER.debug(traceback.format_exc())
            if not ignore_errors:
                raise ClientError from err

            return []
        except Exception:
            LOGGER.debug(traceback.format_exc())

    async def get_config(self):
        """Get standard user information."""
        return await self._request("get", "/v1/config")

    async def get_user(self):
        """Get standard user information."""
        return await self._request("get", "/v1/user")

    async def get_user_info(self):
        """Get all devices associated with an API key."""
        return await self._request("get", "/v2/vehicles")

    async def get_car_capabilities(self, vin: str):
        """Get all car capabilities associated with an vin."""
        return await self._request("get", f"/v1/vehicle/{vin}/capabilities")

    async def get_car_capabilities_commands(self, vin: str):
        """Get all car capabilities associated with an vin."""
        return await self._request("get", f"/v1/vehicle/{vin}/capabilities/commands")

    async def get_car_rcp_supported_settings(self, vin: str):
        """Get all supported car rcp options associated."""
        url = f"{helper.RCP_url(self._region)}/api/v1/vehicles/{vin}/settings"

        LOGGER.debug("get_car_rcp_supported_settings: %s", url)
        return await self._request("get", "", url=url, rcp_headers=True)

    async def get_car_rcp_settings(self, vin: str, setting: str):
        """Get all rcp setting for a car."""
        url = f"{helper.RCP_url(self._region)}/api/v1/vehicles/{vin}/settings/{setting}"

        LOGGER.debug("get_car_rcp_settings: %s", url)
        return await self._request("get", "", url=url, rcp_headers=True)

    async def send_route_to_car(
        self,
        vin: str,
        title: str,
        latitude: float,
        longitude: float,
        city: str,
        postcode: str,
        street: str,
    ):
        """Send route to car associated by vin."""
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

    async def get_car_geofencing_violations(self, vin: str):
        """Get all geofencing violations for a car."""
        url = f"/v1/geofencing/vehicles/{vin}/fences/violations"
        return await self._request("get", url, rcp_headers=False, ignore_errors=True)

    async def get_fleet_info(self, company: str, fleet: str):
        """Get fleet information."""
        url = f"/v1/company/{company}/fleet/{fleet}?size=100&filter="
        return await self._request("get", url, rcp_headers=False, ignore_errors=True)

    async def is_car_rcp_supported(self, vin: str, **kwargs):
        """Return if is car rcp supported."""
        token = await self._oauth.async_get_cached_token()
        headers = {
            "Authorization": f"Bearer {token['access_token']}",
            "User-Agent": WEBSOCKET_USER_AGENT if self._region != REGION_CHINA else WEBSOCKET_USER_AGENT_CN,
        }

        kwargs.setdefault("headers", headers)
        kwargs.setdefault("proxy", SYSTEM_PROXY)

        url = f"{helper.PSAG_url(self._region)}/api/app/v2/vehicles/{vin}/profileInformation"

        if not self._session or self._session.closed:
            self._session = async_get_clientsession(self.hass, VERIFY_SSL)

        async with self._session.request("get", url, **kwargs) as resp:
            resp_status = resp.status
            await resp.text()
            return bool(resp_status == 200)

    async def download_images(self, vin: str):
        """Download the car images and store it to the components ressource folder."""
        url = f"/v1/vehicle/{vin}/topviewimage"
        return await self._request("get", url, rcp_headers=False, ignore_errors=False, return_as_json=False)

    async def get_car_p2b_data_via_rest(self, vin: str):
        """Get vehicleattributes via rest."""
        url = f"{helper.Widget_url(self._region)}/v1/vehicle/{vin}/vehicleattributes"

        try:
            data = await self._request("get", "", url=url, return_as_json=False)
            message = vehicle_events_pb2.VEPUpdate()
            message.ParseFromString(data)
        except TypeError as err:
            LOGGER.error("could not decode data (%s) from websocket: %s", data, err)
        except google.protobuf.message.DecodeError as err:
            LOGGER.error("could not decode data (%s) from websocket: %s", data, err)
        return message if message else None
