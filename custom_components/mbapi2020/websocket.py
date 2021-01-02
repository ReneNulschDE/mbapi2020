"""Define an object to interact with the Websocket API."""
import aiohttp
import asyncio
import logging
import uuid

from typing import Awaitable, Callable, Optional

from aiohttp.client_exceptions import ClientConnectionError, ClientOSError

import custom_components.mbapi2020.proto.vehicle_events_pb2 as vehicle_events_pb2

from .const import (
    WEBSOCKET_API_BASE
)
from .errors import WebsocketError

DEFAULT_WATCHDOG_TIMEOUT = 900

LOGGER = logging.getLogger(__name__)

class WebsocketWatchdog:
    """Define a watchdog to kick the websocket connection at intervals."""

    def __init__(
        self,
        action: Callable[..., Awaitable],
        *,
        timeout_seconds: int = DEFAULT_WATCHDOG_TIMEOUT,
    ):
        """Initialize."""
        self._action: Callable[..., Awaitable] = action
        self._loop = asyncio.get_event_loop()
        self._timer_task: Optional[asyncio.TimerHandle] = None
        self._timeout: int = timeout_seconds

    def cancel(self):
        """Cancel the watchdog."""
        if self._timer_task:
            self._timer_task.cancel()
            self._timer_task = None

    async def on_expire(self):
        """Log and act when the watchdog expires."""
        _LOGGER.info("Watchdog expired – calling %s", self._action.__name__)
        await self._action()

    async def trigger(self):
        """Trigger the watchdog."""
        _LOGGER.info("Watchdog triggered – sleeping for %s seconds", self._timeout)

        if self._timer_task:
            self._timer_task.cancel()

        self._timer_task = self._loop.call_later(
            self._timeout, lambda: asyncio.create_task(self.on_expire())
        )


class Websocket:
    """Define the websocket."""

    def __init__(self, oauth) -> None:
        """Initialize."""
        self.oauth = oauth
        self.session: ClientSession() = None
        self.listening = False

    async def connect(self, on_data, on_connect, on_disconnect) -> None:
        """Connect to the socket."""

        token = await self.oauth.async_get_cached_token()
        headers = {
            "Authorization": token["access_token"],
            "X-SessionId": str(uuid.uuid4()),
            "X-TrackingId": str(uuid.uuid4()),
            "X-ApplicationName": "mycar-store-ece",
            "ris-application-version": "1.3.1",
            "ris-os-name": "android",
            "ris-os-version": "6.0",
            "ris-sdk-version": "2.10.3",
            "X-Locale": "en-US",
            "User-Agent": "okhttp/3.12.2"
        }

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(
                WEBSOCKET_API_BASE, headers=headers
            ) as s:

                self.listening = True
                while self.listening:
                    res_raw = await s.receive_bytes()
                    res = self.wrap_notification(res_raw)
                    LOGGER.debug("Got notification: %s", res.WhichOneof('msg'))

                    ack_message = on_data(res)

                    if (ack_message):
                        await s.send_bytes(ack_message.SerializeToString())


    def wrap_notification(self, res_raw):
        res = vehicle_events_pb2.PushMessage()
        res.ParseFromString(res_raw)
        return res

    async def disconnect(self) -> None:
        """Disconnect from the socket."""
        self.listening = False

    async def reconnect(self) -> None:
        """Reconnect the websocket connection."""
        await self.disconnect()
        await asyncio.sleep(1)
        await self.connect()