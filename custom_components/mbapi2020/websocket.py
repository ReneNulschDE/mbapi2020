"""Define an object to interact with the Websocket API."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
import logging
import uuid

from aiohttp import ClientSession, WSMsgType, WSServerHandshakeError, client_exceptions

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
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
from .helper import UrlHelper as helper, Watchdog
from .oauth import Oauth
from .proto import vehicle_events_pb2

DEFAULT_WATCHDOG_TIMEOUT = 840
PING_WATCHDOG_TIMEOUT = 30
STATE_CONNECTED = "connected"
STATE_RECONNECTING = "reconnecting"

LOGGER = logging.getLogger(__name__)


class Websocket:
    """Define the websocket."""

    def __init__(self, hass, oauth, region, session_id=str(uuid.uuid4()).upper()) -> None:
        """Initialize."""
        self.oauth: Oauth = oauth
        self._hass: HomeAssistant = hass
        self.is_stopping: bool = False
        self._on_data_received: Callable[..., Awaitable] = None
        self._connection = None
        self._region = region
        self.connection_state = "unknown"
        self.is_connecting = False
        self.ha_stop_handler = None
        self._watchdog: Watchdog = Watchdog(
            self.initiatiate_connection_reset,
            topic="Connection",
            timeout_seconds=DEFAULT_WATCHDOG_TIMEOUT,
            log_events=True,
        )
        self._pingwatchdog: Watchdog = Watchdog(
            self.ping, topic="Ping", timeout_seconds=PING_WATCHDOG_TIMEOUT, log_events=False
        )
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

        if not self.ha_stop_handler:
            self.ha_stop_handler = self._hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop_handler)
            self.ha_stop_handler()

        session = async_get_clientsession(self._hass, VERIFY_SSL)

        # Tasks erstellen
        queue_task = asyncio.create_task(self._start_queue_handler())
        websocket_task = asyncio.create_task(self._start_websocket_handler(session))

        # Warten, dass Tasks laufen
        await asyncio.gather(queue_task, websocket_task)

    async def async_stop(self, now: datetime = datetime.now()):
        """Close connection."""
        LOGGER.info("async_stop start - %s", self.connection_state)
        self.is_stopping = True
        self._watchdog.cancel()
        self._pingwatchdog.cancel()
        self.connection_state = "closed"

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
            if self._connection:
                await self._connection.send_bytes(message)
            else:
                raise HomeAssistantError(
                    "MB-Websocket connection is not active. Can't execute the call. Check the homeassistant.log for more details."
                )
        except client_exceptions.ClientError as err:
            raise HomeAssistantError(
                "MB-Websocket connection is not active. Can't execute the call. Check the homeassistant.log for more details Error: %s",
                err,
            ) from err

    async def _start_queue_handler(self):
        while not self.is_stopping:
            await self._queue_handler()

    async def _queue_handler(self):
        while not self.is_stopping:
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

        while not self.is_stopping:
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
            except WSServerHandshakeError:
                raise
            except Exception as error:
                LOGGER.error("Other error %s", error)
                raise

    async def _websocket_handler(self, session: ClientSession):
        websocket_url = helper.Websocket_url(self._region)

        headers = await self._websocket_connection_headers()
        self.is_connecting = True
        LOGGER.debug("Connecting to %s", websocket_url)
        self._connection = await session.ws_connect(websocket_url, headers=headers, proxy=SYSTEM_PROXY)
        LOGGER.debug("Connected to mercedes websocket at %s", websocket_url)

        await self._watchdog.trigger()

        while not self._connection.closed:
            if self.is_stopping:
                break
            self.is_connecting = False

            LOGGER.debug("_start_websocket_handler: setting connection_state to connected.")
            self.connection_state = STATE_CONNECTED

            msg = await self._connection.receive()

            if msg.type == WSMsgType.CLOSED:
                LOGGER.debug("websocket connection is closing")
                break
            if msg.type == WSMsgType.ERROR:
                LOGGER.debug("websocket connection is closing - message type error.")
                break
            if msg.type == WSMsgType.BINARY:
                self._queue.put_nowait(msg.data)
                await self._pingwatchdog.trigger()

    async def _websocket_connection_headers(self):
        token = await self.oauth.async_get_cached_token()
        header = {
            "Authorization": token["access_token"],
            "APP-SESSION-ID": self.session_id,
            "OUTPUT-FORMAT": "PROTO",
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

        return self._get_region_header(header)

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
