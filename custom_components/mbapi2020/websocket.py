"""Define an object to interact with the Websocket API."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
import logging
import time
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
    WEBSOCKET_USER_AGENT_US,
)
from .helper import LogHelper as loghelper, UrlHelper as helper, Watchdog
from .oauth import Oauth
from .proto import vehicle_events_pb2

DEFAULT_WATCHDOG_TIMEOUT = 30
DEFAULT_WATCHDOG_TIMEOUT_CARCOMMAND = 180
INITIAL_WATCHDOG_TIMEOUT = 60  # 5 minutes
WATCHDOG_PROTECTION_PERIOD = 10
PING_WATCHDOG_TIMEOUT = 30
RECONNECT_WATCHDOG_TIMEOUT = 30
STATE_CONNECTED = "connected"
STATE_RECONNECTING = "reconnecting"

LOGGER = logging.getLogger(__name__)


class Websocket:
    """Define the websocket."""

    def __init__(
        self, hass, oauth, region, session_id=str(uuid.uuid4()).upper(), ignition_states: dict[str, bool] | None = None
    ) -> None:
        """Initialize."""
        if ignition_states is None:
            ignition_states = {}
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
            timeout_seconds=INITIAL_WATCHDOG_TIMEOUT,
            log_events=True,
        )
        self._pingwatchdog: Watchdog = Watchdog(
            self.ping, topic="Ping", timeout_seconds=PING_WATCHDOG_TIMEOUT, log_events=False
        )
        self._reconnectwatchdog: Watchdog = Watchdog(
            self._reconnect_attempt, topic="Reconnect", timeout_seconds=RECONNECT_WATCHDOG_TIMEOUT, log_events=True
        )
        self.component_reload_watcher: Watchdog = Watchdog(
            self._blocked_account_reload_check, 30, "Blocked_account_reload", False
        )
        self._queue = asyncio.Queue()
        self._queue_shutdown_sentinel = object()  # Sentinel für graceful shutdown
        self.session_id = session_id
        self._ignition_states: dict[str, bool] = ignition_states
        self.ws_connect_retry_counter_reseted: bool = False
        self.ws_connect_retry_counter: int = 0
        self.account_blocked: bool = False
        self.ws_blocked_connection_error_logged = False
        self._connection_start_time: float | None = None
        self._initial_timeout_used: bool = False

        self._queue_task: asyncio.Task = None
        self._websocket_task: asyncio.Task = None
        self._relogin_429_done: bool = False
        self._blocked_since_time: float | None = None
        self._last_backup_reload_time: float | None = None

    async def _reconnect_attempt(self) -> None:
        """Attempt reconnection without cancelling the reconnect watchdog."""
        LOGGER.debug("Starting reconnect attempt")
        await self._async_connect_internal()

    async def async_connect(self, on_data=None) -> None:
        """Connect to the socket."""
        # Cancel reconnect watchdog for manual connections
        self._reconnectwatchdog.cancel()
        await self._async_connect_internal(on_data)

    async def _async_connect_internal(self, on_data=None) -> None:
        """Internal connect method without cancelling reconnect watchdog."""
        if self.is_connecting:
            return

        async def _async_stop_handler(event):
            """Stop when Home Assistant is shutting down."""
            await self.async_stop()

        if on_data:
            self._on_data_received = on_data

        self.is_connecting = True
        self.is_stopping = False

        if not self.ha_stop_handler:
            self.ha_stop_handler = self._hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop_handler)
            self.ha_stop_handler()

        session = async_get_clientsession(self._hass, VERIFY_SSL)

        # Tasks erstellen und verwalten
        self._queue_task = asyncio.create_task(self._start_queue_handler())
        self._websocket_task = asyncio.create_task(self._start_websocket_handler(session))

        # Warten, dass Tasks laufen - mit ordnungsgemäßer Exception-Behandlung
        try:
            await asyncio.gather(self._queue_task, self._websocket_task, return_exceptions=True)
        except Exception as e:
            LOGGER.debug("async_connect tasks finished with exception: %s", e)
        finally:
            # Sicherstellen, dass Tasks ordnungsgemäß beendet werden
            await self._cleanup_tasks()

    async def async_stop(self, now: datetime = datetime.now()):
        """Close connection."""
        self.is_stopping = True

        # First stop ping watchdog to prevent new pings
        self._pingwatchdog.cancel()

        # Then close WebSocket connection properly with close code
        if self._connection is not None and not self._connection.closed:
            try:
                await self._connection.close(code=1000, message=b"Client shutdown")
            except Exception as e:
                LOGGER.debug("Error closing WebSocket connection: %s", e)

        # Stop main watchdog after connection is closed
        self._watchdog.cancel()
        self.connection_state = "closed"
        # Reset initial timeout state on stop - next connection will use 5min timeout again
        self._connection_start_time = None
        self._initial_timeout_used = False

        # Signal queue handler to stop gracefully
        try:
            self._queue.put_nowait(self._queue_shutdown_sentinel)
        except asyncio.QueueFull:
            LOGGER.warning("Queue full during shutdown, forcing queue cleanup")
            await self._cleanup_queue()

        # Tasks ordnungsgemäß beenden
        await self._cleanup_tasks()

    async def initiatiate_connection_disconnect_with_reconnect(self):
        """Initiate a connection disconnect."""
        # LOGGER.debug(
        #     "ignitions_state: %s, %s",
        #     self.oauth._config_entry.entry_id,
        #     json.dumps(self._ignition_states),
        # )
        if any(self._ignition_states.values()):
            LOGGER.debug(
                "initiatiate_connection_disconnect_with_reconnect canceled - Reason: ignitions_state: %s",
                [loghelper.Mask_VIN(key) for key, value in self._ignition_states.items() if value],
            )
            await self._watchdog.trigger()
            return

        # Prevent race condition: Cancel connection watchdog first to avoid multiple triggers
        self._watchdog.cancel()
        await self._reconnectwatchdog.trigger()
        self._reset_watchdog_timeout()
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
                self._set_watchdog_timeout(DEFAULT_WATCHDOG_TIMEOUT_CARCOMMAND)
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
        """Start the queue handler - entry point for the task."""
        await self._queue_handler()

    async def _queue_handler(self):
        while not self.is_stopping:
            try:
                # Timeout für graceful shutdown
                data = await asyncio.wait_for(self._queue.get(), timeout=1.0)

                # Check for shutdown sentinel
                if data is self._queue_shutdown_sentinel:
                    LOGGER.debug("Queue handler received shutdown signal")
                    self._queue.task_done()
                    break

                try:
                    message = vehicle_events_pb2.PushMessage()
                    message.ParseFromString(data)
                except TypeError as err:
                    LOGGER.error("could not decode data (%s) from websocket: %s", data, err)
                    self._queue.task_done()
                    continue

                if message is None:
                    self._queue.task_done()
                    continue

                LOGGER.debug("Got notification: %s", message.WhichOneof("msg"))

                try:
                    ack_message = self._on_data_received(message)
                    if ack_message:
                        if isinstance(ack_message, str):
                            await self.call(bytes.fromhex(ack_message))
                        else:
                            await self.call(ack_message.SerializeToString())
                except Exception as err:
                    LOGGER.error("Error processing queue message: %s", err)

                self._queue.task_done()

            except asyncio.TimeoutError:
                # Timeout ist normal - weiter prüfen ob stopping
                continue
            except asyncio.CancelledError:
                LOGGER.debug("Queue handler cancelled")
                break
            except Exception as err:
                LOGGER.error("Unexpected error in queue handler: %s", err)
                break

        LOGGER.debug("Queue handler stopped")

    async def _start_websocket_handler(self, session: ClientSession):
        retry_in: int = 10

        LOGGER.debug(
            "_start_websocket_handler: %s (is_stopping: %s, session.closed: %s)",
            self.oauth._config_entry.entry_id,
            self.is_stopping,
            session.closed,
        )

        while not self.is_stopping and not session.closed:
            try:
                await self.component_reload_watcher.trigger()
                await self._websocket_handler(session)
            except client_exceptions.ClientConnectionError as cce:  # noqa: PERF203
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
                    LOGGER.info(
                        "MB-API access blocked. (First Message, expect a re-login) %s, retry in %s seconds...",
                        error,
                        retry_in,
                    )
                    self.ws_blocked_connection_error_logged = True
                else:
                    LOGGER.warning("WSS Connection blocked: %s, retry in %s seconds...", error, retry_in)

                if "429" in str(error.code):
                    self.account_blocked = True
                    # Setze Zeitstempel für Backup-Reload
                    if self._blocked_since_time is None:
                        import time

                        self._blocked_since_time = time.time()

                    if not self._relogin_429_done:
                        config_entry = getattr(self.oauth, "_config_entry", None)
                        if config_entry and "password" in config_entry.data:
                            password = config_entry.data["password"]
                            username = config_entry.data.get("username")
                            region = config_entry.data.get("region")
                            if username and password and hasattr(self.oauth, "async_login_new"):
                                LOGGER.info(
                                    "429 detected: Trying relogin with stored password for config_entry: %s",
                                    config_entry.entry_id,
                                )
                                try:
                                    token_info = await self.oauth.async_login_new(username, password)
                                    LOGGER.info(
                                        "Relogin successful after 429 for config entry %s", config_entry.entry_id
                                    )
                                    # Token im config_entry aktualisieren, falls nötig
                                    self._relogin_429_done = True
                                except Exception as relogin_err:
                                    LOGGER.error("Relogin after 429 failed: %s", relogin_err)
                                    self._relogin_429_done = True  # Auch bei Fehler nicht nochmal versuchen

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
        kwargs.setdefault("headers", await self._websocket_connection_headers())

        self.is_connecting = True
        LOGGER.debug("Connecting to %s", websocket_url)
        self._connection = await session.ws_connect(websocket_url, **kwargs)
        LOGGER.debug("Connected to mercedes websocket at %s", websocket_url)

        # Always reset to initial timeout for each new connection (including reconnects)
        self._connection_start_time = asyncio.get_event_loop().time()
        self._initial_timeout_used = True
        self._watchdog.timeout = INITIAL_WATCHDOG_TIMEOUT

        await self._watchdog.trigger()

        while not self._connection.closed:
            if self.is_stopping:
                break
            self.is_connecting = False

            self.connection_state = STATE_CONNECTED
            # Reset blocked timestamp wenn Verbindung erfolgreich ist
            if self._blocked_since_time is not None:
                self._blocked_since_time = None

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
            "ris-os-name": RIS_OS_NAME,
            "ris-os-version": RIS_OS_VERSION,
            # "ris-websocket-type": "ios-native",
            "ris-sdk-version": RIS_SDK_VERSION,
            "X-Locale": "de-DE",
            "User-Agent": WEBSOCKET_USER_AGENT,
            # "Accept-Language": " de-DE,de;q=0.9",
        }

        return self._get_region_header(header)

    def _get_region_header(self, header) -> list:
        if self._region == REGION_EUROPE:
            header["X-ApplicationName"] = "mycar-store-ece"
            header["ris-application-version"] = RIS_APPLICATION_VERSION

        if self._region == REGION_NORAM:
            header["X-ApplicationName"] = "mycar-store-us"
            header["ris-application-version"] = RIS_APPLICATION_VERSION_NA
            header["User-Agent"] = WEBSOCKET_USER_AGENT_US
            header["X-Locale"] = "en-US"
            header["Accept-Encoding"] = "gzip"
            header["Sec-WebSocket-Extensions"] = "permessage-deflate"

        if self._region == REGION_APAC:
            header["X-ApplicationName"] = "mycar-store-ap"
            header["ris-application-version"] = RIS_APPLICATION_VERSION_PA
            header["User-Agent"] = WEBSOCKET_USER_AGENT_PA

        return header

    async def _blocked_account_reload_check(self):
        if self.account_blocked and self.ws_connect_retry_counter_reseted:
            self.account_blocked = False
            self.ws_connect_retry_counter_reseted = False
            self._blocked_since_time = None
            self._last_backup_reload_time = None

            LOGGER.info("Initiating component reload after account got unblocked...")
            self._hass.config_entries.async_schedule_reload(self.oauth._config_entry.entry_id)

        elif self.account_blocked and not self.ws_connect_retry_counter_reseted:
            current_time = time.time()

            # Prüfe ob Backup-Reload notwendig und erlaubt ist
            if self._blocked_since_time is not None and self._should_trigger_backup_reload(current_time):
                LOGGER.info(
                    "Initiating scheduled backup component reload during allowed time window "
                    "(ignition mode or no message received) - config_entry: %s",
                    self.oauth._config_entry.entry_id,
                )

                self.account_blocked = False
                self._blocked_since_time = None
                self._last_backup_reload_time = current_time
                self._hass.config_entries.async_schedule_reload(self.oauth._config_entry.entry_id)
            else:
                await self.component_reload_watcher.trigger()

    def _should_trigger_backup_reload(self, current_time: float) -> bool:
        """Prüft ob Backup-Reload ausgeführt werden soll (alle 30 Min oder garantiert nach Mitternacht GMT)."""
        from datetime import datetime, timezone

        # Mindestens 5 Minuten blockiert sein
        if current_time - self._blocked_since_time < 300:
            return False

        # Aktuelle Zeit in GMT
        now_utc = datetime.fromtimestamp(current_time, tz=timezone.utc)

        # GARANTIERT nach Mitternacht GMT (00:00 - 00:30 Zeitfenster)
        if now_utc.hour == 0 and now_utc.minute <= 30:
            # Prüfe ob schon heute nach Mitternacht ein Reload gemacht wurde
            if self._last_backup_reload_time is not None:
                last_reload_utc = datetime.fromtimestamp(self._last_backup_reload_time, tz=timezone.utc)
                # Wenn der letzte Reload heute nach Mitternacht war, nicht nochmal
                if (
                    last_reload_utc.date() == now_utc.date()
                    and last_reload_utc.hour == 0
                    and last_reload_utc.minute <= 30
                ):
                    return False
            return True

        # Alle 30 Minuten, aber nur wenn mindestens 30 Min seit letztem Reload
        if self._last_backup_reload_time is not None:
            if current_time - self._last_backup_reload_time < 1800:  # 30 * 60 = 1800 Sekunden
                return False

        # 30-Minuten-Intervalle (:00, :30) mit 5-Minuten-Fenster
        if now_utc.minute <= 5 or (25 <= now_utc.minute <= 35):
            return True

        return False

    async def _cleanup_tasks(self):
        """Cleanup running tasks properly."""
        tasks_to_cancel = []

        if self._queue_task and not self._queue_task.done():
            tasks_to_cancel.append(self._queue_task)
            LOGGER.debug("Cancelling _queue_task")

        if self._websocket_task and not self._websocket_task.done():
            tasks_to_cancel.append(self._websocket_task)
            LOGGER.debug("Cancelling _websocket_task")

        if tasks_to_cancel:
            for task in tasks_to_cancel:
                task.cancel()

            # Warten auf ordnungsgemäße Beendigung mit Timeout
            try:
                await asyncio.wait_for(asyncio.gather(*tasks_to_cancel, return_exceptions=True), timeout=5.0)
            except asyncio.TimeoutError:
                LOGGER.warning("Some websocket tasks did not terminate within 5 seconds")

        # Queue bereinigen
        await self._cleanup_queue()

        # Task-Referenzen zurücksetzen
        self._queue_task = None
        self._websocket_task = None

    async def _cleanup_queue(self):
        """Cleanup remaining queue items."""
        cleanup_count = 0
        try:
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                    cleanup_count += 1
                except asyncio.QueueEmpty:
                    break
        except Exception as err:
            LOGGER.error("Error cleaning up queue: %s", err)

        if cleanup_count > 0:
            LOGGER.debug("Cleaned up %d remaining queue items", cleanup_count)

    def _set_watchdog_timeout(self, timeout: int) -> None:
        """Set watchdog timeout with protection period logic."""
        if not self._initial_timeout_used or self._connection_start_time is None:
            # Not in initial timeout mode, allow any timeout change
            self._watchdog.timeout = timeout
            return

        current_time = asyncio.get_event_loop().time()
        connection_duration = current_time - self._connection_start_time

        # During protection period (first 4:30), don't allow timeout changes
        if connection_duration < WATCHDOG_PROTECTION_PERIOD:
            LOGGER.debug(
                "Watchdog timeout change blocked during protection period (%.1fs elapsed)", connection_duration
            )
            return

        # After protection period, allow timeout changes and switch to default behavior
        self._watchdog.timeout = timeout
        # Reset to normal behavior after protection period (regardless of timeout value)
        self._initial_timeout_used = False
        self._connection_start_time = None

    def _reset_watchdog_timeout(self) -> None:
        """Reset watchdog timeout to default and clear initial timeout state."""
        self._watchdog.timeout = DEFAULT_WATCHDOG_TIMEOUT
        self._initial_timeout_used = False
        self._connection_start_time = None
