"""Helper functions for MBAPI2020 integration."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Awaitable, Callable
import datetime
from enum import Enum
import inspect
import json
import math

from .const import (
    JSON_EXPORT_IGNORED_KEYS,
    LOGGER,
    LOGIN_APP_ID_CN,
    LOGIN_APP_ID_EU,
    LOGIN_BASE_URI,
    LOGIN_BASE_URI_CN,
    PSAG_BASE_URI,
    PSAG_BASE_URI_CN,
    RCP_BASE_URI,
    RCP_BASE_URI_CN,
    REGION_APAC,
    REGION_CHINA,
    REGION_EUROPE,
    REGION_NORAM,
    REST_API_BASE,
    REST_API_BASE_CN,
    REST_API_BASE_NA,
    REST_API_BASE_PA,
    WEBSOCKET_API_BASE,
    WEBSOCKET_API_BASE_CN,
    WEBSOCKET_API_BASE_NA,
)


class LogHelper:
    """Helper functions for MBAPI2020 logging."""

    @staticmethod
    def Mask_VIN(vin: str) -> str:
        if len(vin) > 12:
            return vin[:5] + "X" * (12 - 5 + 1) + vin[13:]
        return "X" * len(vin)

    @staticmethod
    def Mask_email(email: str) -> str:
        if len(email) > 7:
            return email[:2] + "X" * (6 - 2 + 1) + email[7:]
        return "x" * len(email)


class UrlHelper:
    """Helper functions for MBAPI2020 url handling."""

    @staticmethod
    def Rest_url(region: str) -> str:
        match region:
            case current if current == REGION_APAC:
                return REST_API_BASE_PA
            case current if current == REGION_CHINA:
                return REST_API_BASE_CN
            case current if current == REGION_NORAM:
                return REST_API_BASE_NA
            case current if current == REGION_EUROPE:
                return REST_API_BASE

    @staticmethod
    def Websocket_url(region: str) -> str:
        match region:
            case current if current == REGION_APAC:
                return WEBSOCKET_API_BASE_NA
            case current if current == REGION_CHINA:
                return WEBSOCKET_API_BASE_CN
            case current if current == REGION_NORAM:
                return WEBSOCKET_API_BASE_NA
            case current if current == REGION_EUROPE:
                return WEBSOCKET_API_BASE

    @staticmethod
    def Device_code_confirm_url(region: str, device_code: str) -> str:
        """Return a formatted url to confirm a device code auth."""
        base64_code = base64.b64encode(device_code).decode("ascii")
        env = "emea"
        match region:
            case current if current == REGION_APAC:
                env = "amap"
            case current if current == REGION_CHINA:
                env = "cn"
            case current if current == REGION_NORAM:
                env = "amap"

        return (
            f"https://link.{env}-prod.mobilesdk.mercedes-benz.com/device-login?userCode={base64_code}&deviceType=watch"
        )

    @staticmethod
    def RCP_url(region: str) -> str:
        match region:
            case current if current == REGION_CHINA:
                return RCP_BASE_URI_CN
            case _:
                return RCP_BASE_URI

    @staticmethod
    def PSAG_url(region: str) -> str:
        match region:
            case current if current == REGION_CHINA:
                return PSAG_BASE_URI_CN
            case _:
                return PSAG_BASE_URI

    @staticmethod
    def Login_App_Id(region: str) -> str:
        match region:
            case current if current == REGION_CHINA:
                return LOGIN_APP_ID_CN
            case _:
                return LOGIN_APP_ID_EU

    @staticmethod
    def Login_Base_Url(region: str) -> str:
        match region:
            case current if current == REGION_CHINA:
                return LOGIN_BASE_URI_CN
            case _:
                return LOGIN_BASE_URI


class CoordinatesHelper:
    @staticmethod
    def _transform_lat(lon, lat):
        ret = -100.0 + 2.0 * lon + 3.0 * lat + 0.2 * lat * lat + 0.1 * lon * lat + 0.2 * math.sqrt(abs(lon))
        ret += (20.0 * math.sin(6.0 * lon * math.pi) + 20.0 * math.sin(2.0 * lon * math.pi)) * 2.0 / 3.0
        ret += (20.0 * math.sin(lat * math.pi) + 40.0 * math.sin(lat / 3.0 * math.pi)) * 2.0 / 3.0
        ret += (160.0 * math.sin(lat / 12.0 * math.pi) + 320 * math.sin(lat * math.pi / 30.0)) * 2.0 / 3.0
        return ret

    @staticmethod
    def _transform_lon(lon, lat):
        ret = 300.0 + lon + 2.0 * lat + 0.1 * lon * lon + 0.1 * lon * lat + 0.1 * math.sqrt(abs(lon))
        ret += (20.0 * math.sin(6.0 * lon * math.pi) + 20.0 * math.sin(2.0 * lon * math.pi)) * 2.0 / 3.0
        ret += (20.0 * math.sin(lon * math.pi) + 40.0 * math.sin(lon / 3.0 * math.pi)) * 2.0 / 3.0
        ret += (150.0 * math.sin(lon / 12.0 * math.pi) + 300.0 * math.sin(lon / 30.0 * math.pi)) * 2.0 / 3.0
        return ret

    @staticmethod
    def _transform_lat_gcj02(x, y):
        """Transform latitude.

        :param x: Longitude
        :param y: Latitude
        :return: Transformed latitude
        """

        ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(math.fabs(x))
        ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
        ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
        ret += (160.0 * math.sin(y / 12.0 * math.pi) + 320 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
        return ret

    @staticmethod
    def _transform_lon_gcj02(x, y):
        """Transform longitude.

        :param x: Longitude
        :param y: Latitude
        :return: Transformed longitude
        """
        ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(math.fabs(x))
        ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
        ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
        ret += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
        return ret

    @staticmethod
    def wgs84_to_gcj02(lon, lat):
        """Convert WGS-84 coordinates to GCJ-02 coordinates.

        :param lon: WGS-84 longitude
        :param lat: WGS-84 latitude
        :return: GCJ-02 longitude and latitude
        """
        a = 6378245.0  # Major axis
        ee = 0.00669342162296594323  # Flattening

        dlat = CoordinatesHelper._transform_lat(lon - 105.0, lat - 35.0)
        dlon = CoordinatesHelper._transform_lon(lon - 105.0, lat - 35.0)
        radlat = lat / 180.0 * math.pi
        magic = math.sin(radlat)
        magic = 1 - ee * magic * magic
        sqrtmagic = math.sqrt(magic)
        dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * math.pi)
        dlon = (dlon * 180.0) / (a / sqrtmagic * math.cos(radlat) * math.pi)
        mglat = lat + dlat
        mglon = lon + dlon
        return mglon, mglat

    @staticmethod
    def gcj02_to_wgs84(gcj_lon, gcj_lat):
        """Convert GCJ-02 coordinates to WGS-84 coordinates.

        :param gcj_lon: GCJ-02 longitude
        :param gcj_lat: GCJ-02 latitude
        :return: WGS-84 longitude and latitude
        """
        EARTH_RADIUS = 6378137.0
        EE = 0.00669342162296594323

        dlat = CoordinatesHelper._transform_lat_gcj02(gcj_lon - 105.0, gcj_lat - 35.0)
        dlon = CoordinatesHelper._transform_lon_gcj02(gcj_lon - 105.0, gcj_lat - 35.0)
        rad_lat = gcj_lat / 180.0 * math.pi
        magic = math.sin(rad_lat)
        magic = 1 - EE * magic * magic
        sqrt_magic = math.sqrt(magic)
        dlat = (dlat * 180.0) / ((EARTH_RADIUS * (1 - EE)) / (magic * sqrt_magic) * math.pi)
        dlon = (dlon * 180.0) / (EARTH_RADIUS / sqrt_magic * math.cos(rad_lat) * math.pi)
        wgs_lat = gcj_lat - dlat
        wgs_lon = gcj_lon - dlon
        return wgs_lon, wgs_lat


def get_class_property_names(obj: object):
    """Return the names of all properties of a class."""
    return [p[0] for p in inspect.getmembers(type(obj), inspect.isdatadescriptor) if not p[0].startswith("_")]


class MBJSONEncoder(json.JSONEncoder):
    """JSON Encoder that handles data classes, properties and additional data types."""

    def default(self, o) -> str | dict:  # noqa: D102
        if isinstance(o, (datetime.datetime, datetime.date, datetime.time)):
            return o.isoformat()
        if not isinstance(o, Enum) and hasattr(o, "__dict__") and isinstance(o.__dict__, dict):
            retval: dict = o.__dict__
            retval.update({p: getattr(o, p) for p in get_class_property_names(o)})
            return {k: v for k, v in retval.items() if k not in JSON_EXPORT_IGNORED_KEYS}
        return str(o)


class Watchdog:
    """Define a watchdog to run actions at intervals."""

    def __init__(self, action: Callable[..., Awaitable], timeout_seconds: int, topic: str, log_events: bool = False):
        """Initialize."""
        self._action: Callable[..., Awaitable] = action
        self._loop = asyncio.get_event_loop()
        self._timer_task: asyncio.TimerHandle | None = None
        self._topic: str = topic
        self._log_events: bool = log_events
        self.timeout: int = timeout_seconds

    def cancel(self):
        """Cancel the watchdog."""
        if self._timer_task:
            self._timer_task.cancel()
            self._timer_task = None

    async def on_expire(self):
        """Log and act when the watchdog expires."""
        if self._log_events:
            LOGGER.debug("%s Watchdog expired – calling %s", self._topic, self._action.__name__)
        await self._action()

    async def trigger(self):
        """Trigger the watchdog."""
        # if self._log_events:
        #     LOGGER.debug("%s Watchdog trigger", self._topic)
        if self._timer_task:
            self._timer_task.cancel()

        self._timer_task = self._loop.call_later(self.timeout, lambda: asyncio.create_task(self.on_expire()))
