import math

from .const import (
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
    @staticmethod
    def Mask_VIN(vin: str) -> str:
        if len(vin) > 12:
            return vin[:5] + "X" * (12 - 5 + 1) + vin[13:]
        return "X" * len(vin)


class UrlHelper:
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
        """
        Transform latitude.
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
        """
        Transform longitude.
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
        """
        Convert WGS-84 coordinates to GCJ-02 coordinates

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
        """
        Convert GCJ-02 coordinates to WGS-84 coordinates.
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
