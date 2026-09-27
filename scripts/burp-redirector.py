"""Burp Suite extension that redirects MB API traffic to a local mock server.

Pairs with scripts/https-bff.py and scripts/https-ws-case-429.py, so the
integration can be pointed at these instead of the real Mercedes backend
while developing.
"""

from burp import IBurpExtender, IHttpListener

HOST_TO = "localhost"

SERVER_PORT_MAP = {
    "bff.emea-prod.mobilesdk.mercedes-benz.com": 8002,
    "websocket.emea-prod.mobilesdk.mercedes-benz.com": 8001,
}


class BurpExtender(IBurpExtender, IHttpListener):
    """Rewrites MB API hosts to localhost so requests reach the local mocks."""

    #
    # implement IBurpExtender
    #

    def registerExtenderCallbacks(self, callbacks):
        """Register this extension and its HTTP listener with Burp."""
        # obtain an extension helpers object
        self._helpers = callbacks.getHelpers()

        # set our extension name
        callbacks.setExtensionName("MB Traffic redirector")

        # register ourselves as an HTTP listener
        callbacks.registerHttpListener(self)

    #
    # implement IHttpListener
    #

    def processHttpMessage(self, toolFlag, messageIsRequest, messageInfo):
        """Rewrite a matching request's host to its configured local port."""
        # only process requests
        if not messageIsRequest:
            return

        # get the HTTP service for the request
        httpService = messageInfo.getHttpService()

        host = httpService.getHost()

        if host in SERVER_PORT_MAP:
            messageInfo.setHttpService(
                self._helpers.buildHttpService(HOST_TO, SERVER_PORT_MAP.get(host), httpService.getProtocol())
            )
