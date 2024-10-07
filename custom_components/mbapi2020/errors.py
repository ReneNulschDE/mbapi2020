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
