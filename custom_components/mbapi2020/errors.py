"""Define package errors."""

class MbapiError(Exception):
    """Define a base error."""

    pass

class WebsocketError(MbapiError):
    """Define an error related to generic websocket errors."""

    pass

class RequestError(MbapiError):
    """Define an error related to generic websocket errors."""

    pass