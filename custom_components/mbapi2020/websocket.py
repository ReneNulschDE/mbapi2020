"""Define an object to interact with the Websocket API."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import logging
from typing import Optional
import uuid

from aiohttp import ClientSession, WSMsgType, client_exceptions

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    REGION_APAC,
    REGION_EUROPE,
    REGION_NORAM,
    RIS_APPLICATION_VERSION,
    RIS_APPLICATION_VERSION_NA,
    RIS_APPLICATION_VERSION_PA,
    RIS_OS_NAME,
    RIS_OS_VERSION,
    RIS_SDK_VERSION,
    SYSTEM_PROXY,
    VERIFY_SSL,
    WEBSOCKET_USER_AGENT,
    WEBSOCKET_USER_AGENT_PA,
)
from .errors import WebsocketError
from .helper import UrlHelper as helper
from .oauth import Oauth
from .proto import vehicle_events_pb2

DEFAULT_WATCHDOG_TIMEOUT = 720
STATE_CONNECTED = "connected"
STATE_RECONNECTING = "reconnecting"

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
        LOGGER.debug("Watchdog expired – calling %s", self._action.__name__)
        await self._action()

    async def trigger(self):
        """Trigger the watchdog."""
        LOGGER.debug("Watchdog trigger")
        if self._timer_task:
            self._timer_task.cancel()

        self._timer_task = self._loop.call_later(self._timeout, lambda: asyncio.create_task(self.on_expire()))


class WebsocketPingWatcher:
    """Define a watchdog to ping the websocket connection at intervals."""

    def __init__(
        self,
        action: Callable[..., Awaitable],
        *,
        timeout_seconds: int = 30,
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
        await self._action()

    async def trigger(self):
        """Trigger the watchdog."""
        if self._timer_task:
            self._timer_task.cancel()

        self._timer_task = self._loop.call_later(self._timeout, lambda: asyncio.create_task(self.on_expire()))


class Websocket:
    """Define the websocket."""

    def __init__(self, hass, oauth, region, session_id=str(uuid.uuid4()).upper()) -> None:
        """Initialize."""
        self.oauth: Oauth = oauth
        self._hass: HomeAssistant = hass
        self._is_stopping: bool = False
        self._on_data_received: Callable[..., Awaitable] = None
        self._connection = None
        self._region = region
        self.connection_state = "unknown"
        self.is_connecting = False
        self._watchdog: WebsocketWatchdog = WebsocketWatchdog(self.initiatiate_connection_reset)
        self._pingwatchdog: WebsocketPingWatcher = WebsocketPingWatcher(self.ping)
        self._queue = asyncio.Queue()
        self.session_id = session_id

    async def async_connect(self, on_data) -> None:
        """Connect to the socket."""

        if self.is_connecting:
            return

        async def _async_stop_handler(event):
            """Stop when Home Assistant is shutting down."""
            await self.async_stop()

        self._on_data_received = on_data
        self.is_connecting = True

        self._hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop_handler)
        session = async_get_clientsession(self._hass, VERIFY_SSL)

        # Tasks erstellen
        queue_task = asyncio.create_task(self._start_queue_handler())
        websocket_task = asyncio.create_task(self._start_websocket_handler(session))

        # Warten, dass Tasks laufen
        await asyncio.gather(queue_task, websocket_task)

    async def async_stop(self):
        """Close connection."""
        self._is_stopping = True
        self._watchdog.cancel()
        self._pingwatchdog.cancel()
        if self._connection is not None:
            await self._connection.close()

    async def initiatiate_connection_reset(self):
        """Initiate a connection reset."""
        self._pingwatchdog.cancel()
        if self._connection is not None:
            await self._connection.close()

    async def ping(self):
        """Send a ping to the MB websocket servers."""
        try:
            await self._connection.ping()
            await self._pingwatchdog.trigger()
        except (client_exceptions.ClientError, ConnectionResetError):
            await self._pingwatchdog.trigger()

    async def call(self, message):
        """Send a message to the MB websocket servers."""
        try:
            await self._connection.send_bytes(message)
        except client_exceptions.ClientError as err:
            LOGGER.error("remote websocket connection closed: %s", err)

    async def _start_queue_handler(self):
        while not self._is_stopping:
            await self._queue_handler()

    async def _queue_handler(self):
        while not self._is_stopping:
            data = await self._queue.get()

            try:
                message = vehicle_events_pb2.PushMessage()
                message.ParseFromString(data)
            except TypeError as err:
                LOGGER.error("could not decode data (%s) from websocket: %s", data, err)
                break

            if message is None:
                break
            LOGGER.debug("Got notification: %s", message.WhichOneof("msg"))
            ack_message = self._on_data_received(message)
            if ack_message:
                if isinstance(ack_message, str):
                    await self.call(bytes.fromhex(ack_message))
                else:
                    await self.call(ack_message.SerializeToString())

            self._queue.task_done()

    async def _start_websocket_handler(self, session: ClientSession):
        retry_in: int = 10

        while not self._is_stopping:
            LOGGER.debug("_start_websocket_handler: %s", self.oauth._config_entry.entry_id)

            try:
                await self._websocket_handler(session)
            except client_exceptions.ClientConnectionError as cce:
                LOGGER.error("Could not connect: %s, retry in %s seconds...", cce, retry_in)
                LOGGER.debug(cce)
                self.connection_state = STATE_RECONNECTING
                await asyncio.sleep(retry_in)
                retry_in = retry_in * 2 if retry_in < 120 else 120
            except ConnectionResetError as cce:
                LOGGER.info("Connection reseted: %s, retry in %s seconds...", cce, retry_in)
                LOGGER.debug(cce)
                self.connection_state = STATE_RECONNECTING
                await asyncio.sleep(retry_in)
                retry_in = retry_in * 2 if retry_in < 120 else 120
            except Exception as error:
                LOGGER.error("Other error %s", error)
                raise WebsocketError from error

    async def _websocket_handler(self, session: ClientSession):
        websocket_url = helper.Websocket_url(self._region)

        headers = await self._websocket_connection_headers()
        self.is_connecting = True
        LOGGER.info("Connecting to %s", websocket_url)
        self._connection = await session.ws_connect(websocket_url, headers=headers, proxy=SYSTEM_PROXY)
        LOGGER.info("Connected to mercedes websocket at %s", websocket_url)

        await self._watchdog.trigger()

        while not self._connection.closed:
            self.is_connecting = False
            msg = await self._connection.receive()

            self.connection_state = STATE_CONNECTED

            if msg.type == WSMsgType.CLOSED:
                LOGGER.info("websocket connection is closing")
                break
            elif msg.type == WSMsgType.ERROR:
                LOGGER.info("websocket connection is closing - message type error.")
                break
            elif msg.type == WSMsgType.BINARY:
                self._queue.put_nowait(msg.data)
                # await self._watchdog.trigger()
                await self._pingwatchdog.trigger()

    async def _websocket_connection_headers(self):
        token = await self.oauth.async_get_cached_token()
        header = {
            "Authorization": token["access_token"],
            "X-SessionId": self.session_id,
            "X-TrackingId": str(uuid.uuid4()).upper(),
            "RIS-OS-Name": RIS_OS_NAME,
            "RIS-OS-Version": RIS_OS_VERSION,
            "ris-websocket-type": "ios-native",
            "RIS-SDK-Version": RIS_SDK_VERSION,
            "X-Locale": "de-DE",
            "User-Agent": WEBSOCKET_USER_AGENT,
            "Accept-Language": " de-DE,de;q=0.9",
        }

        header = self._get_region_header(header)

        return header

    def _get_region_header(self, header) -> list:
        if self._region == REGION_EUROPE:
            header["X-ApplicationName"] = "mycar-store-ece"
            header["ris-application-version"] = RIS_APPLICATION_VERSION

        if self._region == REGION_NORAM:
            header["X-ApplicationName"] = "mycar-store-us"
            header["ris-application-version"] = RIS_APPLICATION_VERSION_NA

        if self._region == REGION_APAC:
            header["X-ApplicationName"] = "mycar-store-ap"
            header["ris-application-version"] = RIS_APPLICATION_VERSION_PA
            header["User-Agent"] = WEBSOCKET_USER_AGENT_PA

        return header
