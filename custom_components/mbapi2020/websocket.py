"""Define an object to interact with the Websocket API."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import contextlib  # NEW
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
    REGION_CHINA,
    REGION_EUROPE,
    REGION_NORAM,
    RIS_APPLICATION_VERSION,
    RIS_APPLICATION_VERSION_CN,
    RIS_APPLICATION_VERSION_NA,
    RIS_APPLICATION_VERSION_PA,
    RIS_OS_NAME,
    RIS_OS_VERSION,
    RIS_SDK_VERSION,
    RIS_SDK_VERSION_CN,
    SYSTEM_PROXY,
    VERIFY_SSL,
    WEBSOCKET_USER_AGENT,
    WEBSOCKET_USER_AGENT_CN,
    WEBSOCKET_USER_AGENT_PA,
    WEBSOCKET_USER_AGENT_US,
)
from .helper import LogHelper as loghelper, UrlHelper as helper, Watchdog
from .oauth import Oauth
from .proto import vehicle_events_pb2

DEFAULT_WATCHDOG_TIMEOUT = 30
DEFAULT_WATCHDOG_TIMEOUT_CARCOMMAND = 180
INITIAL_WATCHDOG_TIMEOUT = 30
PING_WATCHDOG_TIMEOUT = 32
RECONNECT_WATCHDOG_TIMEOUT = 60
STATE_CONNECTED = "connected"
STATE_RECONNECTING = "reconnecting"
INITIATE_RELOGIN_AFTER_429 = True

LOGGER = logging.getLogger(__name__)


class _PrefixAdapter(logging.LoggerAdapter):
    """Logger adapter that prefixes messages with config entry and instance ID."""

    def process(self, msg, kwargs):
        """Prepend entry_id and instance_id to log message."""
        return f"[{self.extra['entry_id']}][inst#{self.extra['instance_id']}] {msg}", kwargs


class Websocket:
    """Define the websocket."""

    _instance_counter: int = 0

    def __init__(
        self, hass, oauth, region, session_id=str(uuid.uuid4()).upper(), ignition_states: dict[str, bool] | None = None
    ) -> None:
        """Initialize."""
        Websocket._instance_counter += 1
        self._instance_id = Websocket._instance_counter

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

        if getattr(self.oauth, "_config_entry", None):
            self._LOGGER = _PrefixAdapter(
                LOGGER, {"entry_id": self.oauth._config_entry.entry_id, "instance_id": self._instance_id}
            )
        else:
            self._LOGGER = _PrefixAdapter(LOGGER, {"entry_id": "unknown", "instance_id": self._instance_id})

        self._LOGGER.info(
            "Websocket instance created (total instances created: %d, obj_id: %s)",
            Websocket._instance_counter,
            id(self),
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
        self._async_stop_call_count: int = 0
        self._connect_internal_active_count: int = 0
        self._blocked_since_time: float | None = None
        self._last_backup_reload_time: float | None = None

    async def _reconnect_attempt(self) -> None:
        """Attempt reconnection without cancelling the reconnect watchdog."""
        self._LOGGER.debug("Starting reconnect attempt")
        try:
            await self._async_connect_internal()
        except Exception as err:
            self._LOGGER.error("Reconnect attempt failed: %s (%s)", err, type(err).__name__)
        finally:
            # Re-trigger reconnect watchdog if not stopping and not connected
            if not self.is_stopping and self.connection_state != STATE_CONNECTED:
                self._LOGGER.debug("Re-triggering reconnect watchdog after failed attempt")
                await self._reconnectwatchdog.trigger()

    async def async_connect(self, on_data=None) -> None:
        """Connect to the socket."""
        # Cancel reconnect watchdog for manual connections
        self._reconnectwatchdog.cancel(graceful=True)
        await self._async_connect_internal(on_data)

    async def _async_connect_internal(self, on_data=None) -> None:
        """Internal connect method without cancelling reconnect watchdog."""
        if self.is_connecting:
            return

        self._connect_internal_active_count += 1
        self._LOGGER.debug(
            "_async_connect_internal ENTER (active_count: %d, queue_task: %s, ws_task: %s)",
            self._connect_internal_active_count,
            self._queue_task.get_name() if self._queue_task and not self._queue_task.done() else "None/done",
            self._websocket_task.get_name()
            if self._websocket_task and not self._websocket_task.done()
            else "None/done",
        )

        async def _async_stop_handler(event):
            """Stop when Home Assistant is shutting down."""
            await self.async_stop()

        if on_data:
            self._on_data_received = on_data

        self.is_connecting = True
        self.is_stopping = False

        if not self.ha_stop_handler:
            # NICHT sofort aufrufen – Rückruf behalten, nicht deregistrieren
            self.ha_stop_handler = self._hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop_handler)

        session = async_get_clientsession(self._hass, VERIFY_SSL)

        # Tasks erstellen und verwalten
        self._queue_task = asyncio.create_task(self._start_queue_handler(), name="mbapi2020.queue")
        self._websocket_task = asyncio.create_task(self._start_websocket_handler(session), name="mbapi2020.ws")

        # Warten, dass Tasks laufen - mit ordnungsgemäßer Exception-Behandlung
        try:
            await asyncio.gather(self._queue_task, self._websocket_task, return_exceptions=True)
        except Exception as e:
            self._LOGGER.debug("async_connect tasks finished with exception: %s", e)
        finally:
            self._connect_internal_active_count -= 1
            self._LOGGER.debug(
                "_async_connect_internal EXIT (remaining active: %d)", self._connect_internal_active_count
            )
            # Sicherstellen, dass Tasks ordnungsgemäß beendet werden
            await self._cleanup_tasks()

    async def async_stop(self, now: datetime = datetime.now()):
        """Close connection."""
        self._async_stop_call_count += 1
        self._LOGGER.debug(
            "async_stop called (call #%d, is_stopping_already: %s)", self._async_stop_call_count, self.is_stopping
        )
        self.is_stopping = True

        # Watchdogs anhalten (graceful: laufenden expire-Task nicht killen)
        self._pingwatchdog.cancel(graceful=True)
        self._reconnectwatchdog.cancel(graceful=True)
        self._watchdog.cancel(graceful=True)

        # Dann WebSocket-Verbindung ordentlich schließen (gegen Cancel geschützt)
        if self._connection is not None and not self._connection.closed:
            try:
                self._LOGGER.debug("Closing WebSocket connection...")
                await asyncio.shield(
                    asyncio.wait_for(
                        self._connection.close(code=1000, message=b"Client shutdown"),
                        timeout=1.0,
                    )
                )
                self._LOGGER.debug("ws.close awaited (handshake done)")
            except asyncio.TimeoutError:
                self._LOGGER.warning("WebSocket close() timed out (no server CLOSE). Proceeding with shutdown.")
            except asyncio.CancelledError:
                # Beim Shutdown nicht re-raisen
                self._LOGGER.error("WebSocket close() was cancelled by outer task; ignoring during shutdown.")
            except Exception as e:
                self._LOGGER.debug("Error closing WebSocket connection: %s", e)

        # Zustände zurücksetzen
        self._watchdog.cancel(graceful=True)
        self.connection_state = "closed"
        self._connection_start_time = None
        self._initial_timeout_used = False

        # Queue-Handler zum Beenden signalisieren
        try:
            self._queue.put_nowait(self._queue_shutdown_sentinel)
        except asyncio.QueueFull:
            self._LOGGER.warning("Queue full during shutdown, forcing queue cleanup")
            await self._cleanup_queue("async_stop:queue_full")

        # Tasks ordnungsgemäß beenden (shield + kleine Timeouts)
        await self._await_tasks_then_cleanup()

    async def initiatiate_connection_disconnect_with_reconnect(self):
        """Initiate a connection disconnect."""

        if any(self._ignition_states.values()):
            self._LOGGER.debug(
                "initiatiate_connection_disconnect_with_reconnect canceled - Reason: ignitions_state: %s",
                [loghelper.Mask_VIN(key) for key, value in self._ignition_states.items() if value],
            )
            await self._watchdog.trigger()
            return

        # Verhindere Reentrancy: weitere Trigger sofort unterbinden, aber laufenden Task nicht killen
        self.is_stopping = True
        loop = asyncio.get_running_loop()
        self._watchdog.cancel(graceful=True)
        self._reconnectwatchdog.cancel(graceful=True)

        # Graceful shutdown in separatem Task ausführen, um Self-Cancel zu vermeiden
        loop.create_task(self._graceful_shutdown_and_optionally_reconnect(), name="mbapi2020.shutdown")

    async def _graceful_shutdown_and_optionally_reconnect(self):
        try:
            await self.async_stop()
        finally:
            # Wenn direkt ein Reconnect gewollt ist, hier starten:
            await self._reconnectwatchdog.trigger()

    async def ping(self):
        """Send a ping to the MB websocket servers."""
        if self.is_stopping:
            return

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
                    if self._connection and not self._connection.closed:
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
                    self._LOGGER.debug("Queue handler received shutdown signal")
                    self._queue.task_done()
                    break

                try:
                    message = vehicle_events_pb2.PushMessage()
                    message.ParseFromString(data)
                except TypeError as err:
                    self._LOGGER.error("could not decode data (%s) from websocket: %s", data, err)
                    self._queue.task_done()
                    continue

                if message is None:
                    self._queue.task_done()
                    continue

                self._LOGGER.debug("Got notification: %s", message.WhichOneof("msg"))

                try:
                    ack_message = self._on_data_received(message)
                    if ack_message:
                        if isinstance(ack_message, str):
                            await self.call(bytes.fromhex(ack_message))
                        else:
                            await self.call(ack_message.SerializeToString())
                except Exception as err:
                    self._LOGGER.error("Error processing queue message: %s", err)

                self._queue.task_done()

            except asyncio.TimeoutError:
                # Timeout ist normal - weiter prüfen ob stopping
                continue
            except asyncio.CancelledError:
                self._LOGGER.debug("Queue handler cancelled")
                break
            except Exception as err:
                self._LOGGER.error("Unexpected error in queue handler: %s", err)
                break

        self._LOGGER.debug("Queue handler stopped")

    async def _start_websocket_handler(self, session: ClientSession):
        retry_in: int = 10

        self._LOGGER.debug(
            "_start_websocket_handler (is_stopping: %s, session.closed: %s)",
            self.is_stopping,
            session.closed,
        )

        while not self.is_stopping and not session.closed:
            try:
                await self.component_reload_watcher.trigger()
                await self._websocket_handler(session)
            except client_exceptions.ClientConnectionError as cce:  # noqa: PERF203
                self._LOGGER.error("Could not connect: %s, retry in %s seconds...", cce, retry_in)
                self._LOGGER.debug(cce)
                self.connection_state = STATE_RECONNECTING
                await asyncio.sleep(retry_in)
                retry_in = retry_in * 2 if retry_in < 120 else 120
                self.ws_connect_retry_counter += 1
            except ConnectionResetError as cce:
                self._LOGGER.info("Connection reseted: %s, retry in %s seconds...", cce, retry_in)
                self._LOGGER.debug(cce)
                self.connection_state = STATE_RECONNECTING
                await asyncio.sleep(retry_in)
                retry_in = retry_in * 2 if retry_in < 120 else 120
                self.ws_connect_retry_counter += 1
            except WSServerHandshakeError as error:
                if not self.ws_blocked_connection_error_logged:
                    self._LOGGER.info(
                        "MB-API access blocked. (First Message, expect a re-login) %s, retry in %s seconds...",
                        error,
                        retry_in,
                    )
                    self.ws_blocked_connection_error_logged = True
                else:
                    self._LOGGER.warning("WSS Connection blocked: %s, retry in %s seconds...", error, retry_in)

                if "429" in str(error.code):
                    self.account_blocked = True
                    # Setze Zeitstempel für Backup-Reload
                    if self._blocked_since_time is None:
                        self._blocked_since_time = time.time()

                    if INITIATE_RELOGIN_AFTER_429 and not self._relogin_429_done:
                        config_entry = getattr(self.oauth, "_config_entry", None)
                        if config_entry and "password" in config_entry.data:
                            password = config_entry.data["password"]
                            username = config_entry.data.get("username").strip()
                            region = config_entry.data.get("region")
                            if username and password and hasattr(self.oauth, "async_login_new"):
                                self._LOGGER.info("429 detected: Trying relogin with stored password")
                                try:
                                    token_info = await self.oauth.async_login_new(username, password)
                                    self._LOGGER.info("Relogin successful after 429")
                                    # Token im config_entry aktualisieren, falls nötig
                                    self._relogin_429_done = True
                                except Exception as relogin_err:
                                    self._LOGGER.error("Relogin after 429 failed: %s", relogin_err)
                                    self._relogin_429_done = True  # Auch bei Fehler nicht nochmal versuchen

                self.ws_connect_retry_counter += 1
                self.connection_state = STATE_RECONNECTING
                await asyncio.sleep(retry_in)
                retry_in = 10 * self.ws_connect_retry_counter * self.ws_connect_retry_counter
            except Exception as error:
                self._LOGGER.error("Other error: %s (%s)", error, type(error).__name__)
                self.connection_state = STATE_RECONNECTING
                await asyncio.sleep(retry_in)
                retry_in = retry_in * 2 if retry_in < 120 else 120
                self.ws_connect_retry_counter += 1

    async def _websocket_handler(self, session: ClientSession, **kwargs):
        websocket_url = helper.Websocket_url(self._region)

        kwargs.setdefault("proxy", SYSTEM_PROXY)
        kwargs.setdefault("headers", await self._websocket_connection_headers())

        self.is_connecting = True
        self._LOGGER.debug("Connecting to %s", websocket_url)
        self._connection = await session.ws_connect(websocket_url, **kwargs)
        self._LOGGER.debug("Connected to mercedes websocket at %s", websocket_url)

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

            # Wichtig: alle Close-Varianten sauber behandeln
            if msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
                self._LOGGER.debug("websocket connection is closing (%s)", msg.type)
                break
            if msg.type == WSMsgType.ERROR:
                self._LOGGER.debug("websocket connection is closing - message type error.")
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

        if self._region == REGION_CHINA:
            header["X-ApplicationName"] = "mycar-store-cn"
            header["ris-application-version"] = RIS_APPLICATION_VERSION_CN
            header["User-Agent"] = WEBSOCKET_USER_AGENT_CN
            header["ris-sdk-version"] = RIS_SDK_VERSION_CN

        return header

    async def _blocked_account_reload_check(self):
        if self.account_blocked and self.ws_connect_retry_counter_reseted:
            self.account_blocked = False
            self.ws_connect_retry_counter_reseted = False
            self._blocked_since_time = None
            self._last_backup_reload_time = None

            self._LOGGER.info("Initiating component reload after account got unblocked...")
            self._hass.config_entries.async_schedule_reload(self.oauth._config_entry.entry_id)

        elif self.account_blocked and not self.ws_connect_retry_counter_reseted:
            current_time = time.time()

            # Prüfe ob Backup-Reload notwendig und erlaubt ist
            if self._blocked_since_time is not None and self._should_trigger_backup_reload(current_time):
                self._LOGGER.info(
                    "Initiating scheduled backup component reload during allowed time window "
                    "(ignition mode or no message received)"
                )

                self.account_blocked = False
                self._blocked_since_time = None
                self._last_backup_reload_time = current_time
                self._hass.config_entries.async_schedule_reload(self.oauth._config_entry.entry_id)
            else:
                await self.component_reload_watcher.trigger()

    def _should_trigger_backup_reload(self, current_time: float) -> bool:
        """Prüft ob Backup-Reload ausgeführt werden soll (alle 30 Min oder garantiert nach Mitternacht GMT)."""

        # Kein Backup-Reload für China - Reauth ist dort nicht verfügbar
        if self._region == REGION_CHINA:
            return False

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

    async def _await_tasks_then_cleanup(self):
        """Warte kurz auf natürliches Ende der Tasks und räume dann auf."""
        # Warten auf _websocket_task
        if self._websocket_task and not self._websocket_task.done():
            try:
                await asyncio.shield(asyncio.wait_for(self._websocket_task, timeout=2.0))
            except asyncio.TimeoutError:
                self._LOGGER.warning("websocket task didn't finish in time, cancelling")
                if self._websocket_task:
                    self._websocket_task.cancel()
                with contextlib.suppress(Exception):
                    await self._websocket_task
            except asyncio.CancelledError:
                # Beim Shutdown ignorieren
                pass

        # Queue-Task analog
        if self._queue_task and not self._queue_task.done():
            try:
                await asyncio.shield(asyncio.wait_for(self._queue_task, timeout=2.0))
            except asyncio.TimeoutError:
                self._queue_task.cancel()
                with contextlib.suppress(Exception):
                    await self._queue_task
            except asyncio.CancelledError:
                pass

        # Queue bereinigen
        await self._cleanup_queue("_await_tasks_then_cleanup")

        # Task-Referenzen zurücksetzen
        self._queue_task = None
        self._websocket_task = None

    async def _cleanup_tasks(self):
        """Cleanup running tasks properly (Fallback)."""
        tasks_to_cancel = []

        if self._queue_task and not self._queue_task.done():
            tasks_to_cancel.append(self._queue_task)
            self._LOGGER.debug("Cancelling _queue_task")

        if self._websocket_task and not self._websocket_task.done():
            tasks_to_cancel.append(self._websocket_task)
            self._LOGGER.debug("Cancelling _websocket_task")

        if tasks_to_cancel:
            for task in tasks_to_cancel:
                task.cancel()

            # Warten auf ordnungsgemäße Beendigung mit Timeout
            try:
                await asyncio.wait_for(asyncio.gather(*tasks_to_cancel, return_exceptions=True), timeout=5.0)
            except asyncio.TimeoutError:
                self._LOGGER.warning("Some websocket tasks did not terminate within 5 seconds")

        # Queue bereinigen
        await self._cleanup_queue("_cleanup_tasks")

        # Task-Referenzen zurücksetzen
        self._queue_task = None
        self._websocket_task = None

    async def _cleanup_queue(self, caller: str = "unknown"):
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
            self._LOGGER.error("Error cleaning up queue: %s", err)

        if cleanup_count > 0:
            self._LOGGER.debug(
                "Cleaned up %d remaining queue items (caller: %s, qsize: %d)",
                cleanup_count,
                caller,
                self._queue.qsize(),
            )

    def _set_watchdog_timeout(self, timeout: int) -> None:
        """Set watchdog timeout with protection period logic."""
        if not self._initial_timeout_used or self._connection_start_time is None:
            # Not in initial timeout mode, allow any timeout change
            self._watchdog.timeout = timeout
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
