"""Define package errors."""

from __future__ import annotations

from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError


class MbapiError(HomeAssistantError):
    """Define a base error."""


class WebsocketError(MbapiError):
    """Define an error related to generic websocket errors."""


class RequestError(MbapiError):
    """Define an error related to generic websocket errors."""


class MBAuthError(ConfigEntryAuthFailed):
    """Define an error related to authentication."""

    oauth_error: str | None = None


class MBAuth2FAError(ConfigEntryAuthFailed):
    """Define an error related to two-factor authentication (2FA)."""


class MBLegalTermsError(ConfigEntryAuthFailed):
    """Define an error related to acceptance of legal terms."""


class MBDeviceAuthTimeout(MbapiError):
    """Define an error when the China device-code login expires."""


class MBDeviceAuthDenied(MbapiError):
    """Define an error when the user denies the China device-code login."""
