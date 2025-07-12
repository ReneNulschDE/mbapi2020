"""Define an object to interact with the Websocket API."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
import logging
import ssl
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

DEFAULT_WATCHDOG_TIMEOUT = 30
DEFAULT_WATCHDOG_TIMEOUT_CARCOMMAND = 120
PING_WATCHDOG_TIMEOUT = 30
RECONNECT_WATCHDOG_TIMEOUT = 60
STATE_CONNECTED = "connected"
STATE_RECONNECTING = "reconnecting"

LOGGER = logging.getLogger(__name__)


class Websocket:
    """Define the websocket."""

    ssl_context: ssl.SSLContext | bool = VERIFY_SSL

    def __init__(
        self, hass, oauth, region, session_id=str(uuid.uuid4()).upper(), ignition_states: dict[str, bool] = {}
    ) -> None:
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
            self.initiatiate_connection_disconnect_with_reconnect,
            topic="Connection",
            timeout_seconds=DEFAULT_WATCHDOG_TIMEOUT,
            log_events=True,
        )
        self._pingwatchdog: Watchdog = Watchdog(
            self.ping, topic="Ping", timeout_seconds=PING_WATCHDOG_TIMEOUT, log_events=False
        )
        self._reconnectwatchdog: Watchdog = Watchdog(
            self.async_connect, topic="Reconnect", timeout_seconds=RECONNECT_WATCHDOG_TIMEOUT, log_events=True
        )
        self.component_reload_watcher: Watchdog = Watchdog(
            self._blocked_account_reload_check, 30, "Blocked_account_reload", False
        )
        self._queue = asyncio.Queue()
        self.session_id = session_id
        self._ignition_states: dict[str, bool] = ignition_states
        self.ws_connect_retry_counter_reseted: bool = False
        self.ws_connect_retry_counter: int = 0
        self.account_blocked: bool = False
        self.ws_blocked_connection_error_logged = False

        if isinstance(VERIFY_SSL, str):
            self.ssl_context = ssl.create_default_context(cafile=VERIFY_SSL)

    async def async_connect(self, on_data=None) -> None:
        """Connect to the socket."""

        if self.is_connecting:
            return

        async def _async_stop_handler(event):
            """Stop when Home Assistant is shutting down."""
            await self.async_stop()

        if on_data:
            self._on_data_received = on_data

        self.is_connecting = True
        self.is_stopping = False
        self._reconnectwatchdog.cancel()

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
        self.is_stopping = True
        self._watchdog.cancel()
        self._pingwatchdog.cancel()
        self.connection_state = "closed"

        if self._connection is not None:
            await self._connection.close()

    async def initiatiate_connection_disconnect_with_reconnect(self):
        """Initiate a connection disconnect."""
        if any(self._ignition_states.values()):
            LOGGER.debug(
                "initiatiate_connection_disconnect_with_reconnect canceled - Reason: ignitions_state: %s",
                [key for key, value in self._ignition_states.items() if value],
            )
            await self._watchdog.trigger()
            return

        await self._reconnectwatchdog.trigger()
        self._watchdog.timeout = DEFAULT_WATCHDOG_TIMEOUT
        await self.async_stop()

    async def ping(self):
        """Send a ping to the MB websocket servers."""
        try:
            await self._connection.ping()
            await self._pingwatchdog.trigger()
        except (client_exceptions.ClientError, ConnectionResetError):
            await self._pingwatchdog.trigger()

    async def call(self, message, car_command: bool = False):
        """Send a message to the MB websocket servers."""
        try:
            reconnect_task = None

            if not self._connection or self._connection.closed:
                reconnect_task = asyncio.create_task(self.async_connect())

            if car_command:
                self._watchdog.timeout = DEFAULT_WATCHDOG_TIMEOUT_CARCOMMAND
                await self._watchdog.trigger()

            if reconnect_task:
                for _ in range(50):
                    if not self._connection.closed:
                        break
                    await asyncio.sleep(0.1)

            await self._connection.send_bytes(message)

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

        while not self.is_stopping and not session.closed:
            LOGGER.debug("_start_websocket_handler: %s", self.oauth._config_entry.entry_id)

            try:
                await self.component_reload_watcher.trigger()
                await self._websocket_handler(session)
            except client_exceptions.ClientConnectionError as cce:
                LOGGER.error("Could not connect: %s, retry in %s seconds...", cce, retry_in)
                LOGGER.debug(cce)
                self.connection_state = STATE_RECONNECTING
                await asyncio.sleep(retry_in)
                retry_in = retry_in * 2 if retry_in < 120 else 120
                self.ws_connect_retry_counter += 1
            except ConnectionResetError as cce:
                LOGGER.info("Connection reseted: %s, retry in %s seconds...", cce, retry_in)
                LOGGER.debug(cce)
                self.connection_state = STATE_RECONNECTING
                await asyncio.sleep(retry_in)
                retry_in = retry_in * 2 if retry_in < 120 else 120
                self.ws_connect_retry_counter += 1
            except WSServerHandshakeError as error:
                if not self.ws_blocked_connection_error_logged:
                    LOGGER.error("MB-API access blocked. %s, retry in %s seconds...", error, retry_in)
                    self.ws_blocked_connection_error_logged = True
                else:
                    LOGGER.info("WSS Connection blocked: %s, retry in %s seconds...", error, retry_in)
                if "429" in str(error.code):
                    self.account_blocked = True
                self.ws_connect_retry_counter += 1
                self.connection_state = STATE_RECONNECTING
                await asyncio.sleep(retry_in)
                retry_in = 10 * self.ws_connect_retry_counter * self.ws_connect_retry_counter
            except Exception as error:
                LOGGER.error("Other error %s", error)
                raise

    async def _websocket_handler(self, session: ClientSession, **kwargs):
        websocket_url = helper.Websocket_url(self._region)

        kwargs.setdefault("proxy", SYSTEM_PROXY)
        kwargs.setdefault("ssl", self.ssl_context)
        kwargs.setdefault("headers", await self._websocket_connection_headers())

        # kwargs["headers"]["Ris-Os-Name"] = "manual_test"
        # kwargs["headers"]["X-Applicationname"] = "mycar-store-ece-watchapp"
        # kwargs["headers"]["Ris-Application-Version"] = "1.51.0 (2578)"

        self.is_connecting = True
        LOGGER.debug("Connecting to %s", websocket_url)
        self._connection = await session.ws_connect(websocket_url, **kwargs)
        LOGGER.debug("Connected to mercedes websocket at %s", websocket_url)

        await self._watchdog.trigger()

        while not self._connection.closed:
            if self.is_stopping:
                break
            self.is_connecting = False

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
                await self._watchdog.trigger()

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

    async def _blocked_account_reload_check(self):
        if self.account_blocked and self.ws_connect_retry_counter_reseted:
            self.account_blocked = False
            self.ws_connect_retry_counter_reseted = False

            LOGGER.info("Initiating component reload after account got unblocked...")
            self._hass.async_create_task(self._hass.config_entries.async_reload(self.oauth._config_entry.entry_id))

        elif self.account_blocked and not self.ws_connect_retry_counter_reseted:
            await self.component_reload_watcher.trigger()
