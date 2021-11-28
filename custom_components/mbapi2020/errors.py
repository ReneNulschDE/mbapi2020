"""Define package errors."""

class MbapiError(Exception):
    """Define a base error."""


class WebsocketError(MbapiError):
    """Define an error related to generic websocket errors."""


class RequestError(MbapiError):
    """Define an error related to generic websocket errors."""
