"""Define an object to interact with the Websocket API."""
import asyncio
import logging
import uuid
from typing import Awaitable, Callable, Optional

import aiohttp
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send

import custom_components.mbapi2020.proto.vehicle_events_pb2 as vehicle_events_pb2

from .const import (
    DOMAIN,
    REGION_APAC,
    REGION_EUROPE,
    REGION_NORAM,
    RIS_APPLICATION_VERSION,
    RIS_APPLICATION_VERSION_NA,
    RIS_APPLICATION_VERSION_PA,
    RIS_OS_NAME,
    RIS_OS_VERSION,
    RIS_SDK_VERSION,
    VERIFY_SSL,
    WEBSOCKET_USER_AGENT,
    WEBSOCKET_USER_AGENT_PA,
)
from .helper import UrlHelper as helper
from .oauth import Oauth

DEFAULT_WATCHDOG_TIMEOUT = 300

STATE_INIT = "initializing"
STATE_CONNECTING = "connecting"
STATE_CONNECTED = "connected"
STATE_AUTH_INVALID = "auth_invalid"
STATE_AUTH_REQUIRED = "auth_required"
STATE_RECONNECTING = "reconnecting"
STATE_DISCONNECTED = "disconnected"

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
        LOGGER.info("Watchdog expired – calling %s", self._action.__name__)
        await self._action()

    async def trigger(self):
        """Trigger the watchdog."""
        # LOGGER.debug("Watchdog triggered – sleeping for %s seconds", self._timeout)

        if self._timer_task:
            self._timer_task.cancel()

        self._timer_task = self._loop.call_later(self._timeout, lambda: asyncio.create_task(self.on_expire()))


class Websocket:
    """Define the websocket."""

    def __init__(self, hass, oauth, region) -> None:
        """Initialize."""
        self.oauth: Oauth = oauth
        self._hass = hass
        self._is_stopping = False
        self._on_data_received: Callable[..., Awaitable] = None
        self._connection = None
        self._region = region
        self.connection_state = "unknown"
        self.is_connecting = False
        self._watchdog: WebsocketWatchdog = WebsocketWatchdog(self._disconnected)

    def set_connection_state(self, state):
        """Change current connection state."""
        signal = f"{DOMAIN}"
        async_dispatcher_send(self._hass, signal, state)
        self.connection_state = state

    async def async_connect(self, on_data) -> None:
        """Connect to the socket."""

        if self.is_connecting:
            return

        async def _async_stop_handler(event):
            """Stop when Home Assistant is shutting down."""
            await self.async_stop()

        self._on_data_received = on_data

        await self._watchdog.trigger()

        session = async_get_clientsession(self._hass, VERIFY_SSL)
        self.set_connection_state(STATE_CONNECTING)

        headers = await self._websocket_connection_headers()

        websocket_url = helper.Websocket_url(self._region)
        while True:
            try:
                self.is_connecting = True
                LOGGER.info("Connecting to %s", websocket_url)
                self._connection = await session.ws_connect(websocket_url, headers=headers)
            except aiohttp.client_exceptions.ClientError as exc:
                LOGGER.error("Could not connect to %s, retry in 10 seconds...", websocket_url)
                LOGGER.debug(exc)
                self.set_connection_state(STATE_RECONNECTING)
                await asyncio.sleep(10)
            else:
                self.is_connecting = False
                LOGGER.info("Connected to mercedes websocket at %s", websocket_url)
                break

        self._hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop_handler)

        asyncio.ensure_future(self._recv())

    async def async_stop(self):
        """Close connection."""
        self._is_stopping = True
        self._watchdog.cancel()
        if self._connection is not None:
            await self._connection.close()

    def _decode_message(self, res_raw):
        res = vehicle_events_pb2.PushMessage()
        res.ParseFromString(res_raw)
        return res

    async def _disconnected(self):
        self.set_connection_state(STATE_DISCONNECTED)
        if not self._is_stopping:
            asyncio.ensure_future(self.async_connect(self._on_data_received))

    async def _recv(self):
        while not self._connection.closed:
            self.set_connection_state(STATE_CONNECTED)

            try:
                data = await self._connection.receive()
            except aiohttp.client_exceptions.ClientError as err:
                LOGGER.warning("remote websocket connection closed: %s", err)
                break
            except aiohttp.client_exceptions.ConnectionResetError as cr_err:
                LOGGER.warning("remote websocket connection closed cr: %s", err)
                break

            await self._watchdog.trigger()

            if not data:
                break

            if data.type == aiohttp.WSMsgType.PING:
                LOGGER.debug("websocket connection PING ")

            if data.type == aiohttp.WSMsgType.PONG:
                LOGGER.debug("websocket connection PONG ")

            if data.type in (
                aiohttp.WSMsgType.CLOSE,
                aiohttp.WSMsgType.CLOSED,
                aiohttp.WSMsgType.CLOSING,
            ):
                LOGGER.debug("websocket connection is closing")
                break

            if data.type == aiohttp.WSMsgType.ERROR:
                LOGGER.error("websocket connection had an error")
                break

            try:
                if data.type == aiohttp.WSMsgType.BINARY:
                    message = self._decode_message(data.data)
            except TypeError as err:
                LOGGER.error("could not decode data (%s) from websocket: %s", data, err)
                break

            if message is None:
                break

            LOGGER.debug("Got notification: %s", message.WhichOneof("msg"))
            ack_message = self._on_data_received(message)
            if ack_message:
                await self.call(ack_message.SerializeToString())

        await self._disconnected()

    async def call(self, message):
        try:
            await self._connection.send_bytes(message)
        except aiohttp.client_exceptions.ClientError as err:
            LOGGER.error("remote websocket connection closed: %s", err)
            await self._disconnected()

    async def _websocket_connection_headers(self):
        token = await self.oauth.async_get_cached_token()
        header = {
            "Authorization": token["access_token"],
            "X-SessionId": str(uuid.uuid4()),
            "X-TrackingId": str(uuid.uuid4()),
            "ris-os-name": RIS_OS_NAME,
            "ris-os-version": RIS_OS_VERSION,
            "ris-sdk-version": RIS_SDK_VERSION,
            "X-Locale": "en-US",
            "User-Agent": WEBSOCKET_USER_AGENT,
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
