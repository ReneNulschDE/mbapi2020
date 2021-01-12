"""Define an object to interact with the Websocket API."""
import logging
import uuid

from typing import Awaitable, Callable, Optional

import asyncio
import aiohttp

from aiohttp.client_exceptions import ClientConnectionError, ClientOSError

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send

from homeassistant.const import (
    EVENT_HOMEASSISTANT_STOP
)

import custom_components.mbapi2020.proto.vehicle_events_pb2 as vehicle_events_pb2

from .const import (
    DOMAIN,
    RIS_APPLICATION_VERSION,
    RIS_SDK_VERSION,
    VERIFY_SSL,
    WEBSOCKET_API_BASE,
    WEBSOCKET_USER_AGENT
)
from .oauth import Oauth

HEARTBEAT_INTERVAL = 20
HEARTBEAT_TIMEOUT = 5

STATE_INIT = "initializing"
STATE_CONNECTING = "connecting"
STATE_CONNECTED = "connected"
STATE_AUTH_INVALID = "auth_invalid"
STATE_AUTH_REQUIRED = "auth_required"
STATE_RECONNECTING = "reconnecting"
STATE_DISCONNECTED = "disconnected"

LOGGER = logging.getLogger(__name__)


class Websocket:
    """Define the websocket."""

    def __init__(self, hass, oauth) -> None:
        """Initialize."""
        self.oauth: Oauth = oauth
        self._hass = hass
        self._is_stopping = False
        self._on_data_received: Callable[..., Awaitable] = None
        self._connection = None
        self.connection_state = "unknown"

    def set_connection_state(self, state):
        """Change current connection state."""
        signal = f"{DOMAIN}"
        async_dispatcher_send(self._hass, signal, state)
        self.connection_state = state


    async def async_connect(self, on_data) -> None:
        """Connect to the socket."""

        async def _async_stop_handler(event):
            """Stop when Home Assistant is shutting down."""
            await self.async_stop()

        self._on_data_received = on_data

        session = async_get_clientsession(self._hass, VERIFY_SSL)
        self.set_connection_state(STATE_CONNECTING)

        headers = await self._websocket_connection_headers()

        while True:
            try:
                LOGGER.info("Connecting to %s", WEBSOCKET_API_BASE)
                self._connection = await session.ws_connect(WEBSOCKET_API_BASE, headers=headers)
            except aiohttp.client_exceptions.ClientError:
                LOGGER.error("Could not connect to %s, retry in 10 seconds...", WEBSOCKET_API_BASE)
                self.set_connection_state(STATE_RECONNECTING)
                await asyncio.sleep(10)
            else:
                LOGGER.info("Connected to mercedes websocket at %s", WEBSOCKET_API_BASE)
                break


        self._hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop_handler)

        asyncio.ensure_future(self._recv())


    async def async_stop(self):
        """Close connection."""
        self._is_stopping = True
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
                LOGGER.error("remote websocket connection closed: %s", err)
                break

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

            LOGGER.debug("Got notification: %s", message.WhichOneof('msg'))
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
        return {
            "Authorization": token["access_token"],
            "X-SessionId": str(uuid.uuid4()),
            "X-TrackingId": str(uuid.uuid4()),
            "X-ApplicationName": "mycar-store-ece",
            "ris-application-version": RIS_APPLICATION_VERSION,
            "ris-os-name": "android",
            "ris-os-version": "6.0",
            "ris-sdk-version": RIS_SDK_VERSION,
            "X-Locale": "en-US",
            "User-Agent": WEBSOCKET_USER_AGENT
        }
