"""Define an object to interact with the REST API."""
import asyncio
import logging
import uuid

from typing import Optional

from aiohttp import ClientSession, ClientTimeout
from aiohttp.client_exceptions import ClientError

from .const import (
    REST_API_BASE,
    REST_API_BASE_NA
)
from .errors import RequestError
from .oauth import Oauth

LOGGER = logging.getLogger(__name__)

DEFAULT_LIMIT: int = 288
DEFAULT_TIMEOUT: int = 10


class API:
    """Define the API object."""

    def __init__(
        self,
        oauth: Oauth,
        session: Optional[ClientSession] = None,
        region: str = None
    ) -> None:
        """Initialize."""
        self._session: ClientSession = session
        self._oauth: Oauth = oauth
        self._region = region

    async def _request(self, method: str, endpoint: str, **kwargs) -> list:
        """Make a request against the API."""

        url = f"{REST_API_BASE if self._region == 'Europe' else REST_API_BASE_NA}{endpoint}"

        kwargs.setdefault("headers", {})

        token = await self._oauth.async_get_cached_token()

        kwargs["headers"] = {
            "Authorization": token["access_token"],
            "X-SessionId": str(uuid.uuid4()),
            "X-TrackingId": str(uuid.uuid4()),
            "X-ApplicationName": "mycar-store-ece",
            "X-AuthMode": "KEYCLOAK",
            "ris-application-version": "1.3.1",
            "ris-os-name": "android",
            "ris-os-version": "6.0",
            "ris-sdk-version": "2.10.3",
            "X-Locale": "en-US",
            "User-Agent": "okhttp/3.12.2"
        }

        use_running_session = self._session and not self._session.closed

        if use_running_session:
            session = self._session
        else:
            session = ClientSession(timeout=ClientTimeout(total=DEFAULT_TIMEOUT))

        try:
            async with session.request(method, url, **kwargs) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except ClientError as err:
            raise RequestError(f"Error requesting data from {url}: {err}")
        finally:
            if not use_running_session:
                await session.close()

    async def get_user_info(self) -> list:
        """Get all devices associated with an API key."""
        return await self._request("get", "/v1/vehicle/self/masterdata")

    async def get_car_capabilities_commands(self, vin:str) -> list:
        return await self._request("get", f"/v1/vehicle/{vin}/capabilities/commands")

