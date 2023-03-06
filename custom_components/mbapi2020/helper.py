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
)


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
