from burp import IBurpExtender, IHttpListener

HOST_TO = "localhost"

SERVER_PORT_MAP = {
    "bff.emea-prod.mobilesdk.mercedes-benz.com": 8002,
    "websocket.emea-prod.mobilesdk.mercedes-benz.com": 8001,
}


class BurpExtender(IBurpExtender, IHttpListener):
    #
    # implement IBurpExtender
    #

    def registerExtenderCallbacks(self, callbacks):
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
