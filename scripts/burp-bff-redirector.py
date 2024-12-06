from burp import IBurpExtender, IHttpListener

HOST_FROM = "bff.emea-prod.mobilesdk.mercedes-benz.com"
HOST_TO = "localhost"


class BurpExtender(IBurpExtender, IHttpListener):
    #
    # implement IBurpExtender
    #

    def registerExtenderCallbacks(self, callbacks):
        # obtain an extension helpers object
        self._helpers = callbacks.getHelpers()

        # set our extension name
        callbacks.setExtensionName("BFF Traffic redirector")

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

        # if the host is HOST_FROM, change it to HOST_TO
        if HOST_FROM == httpService.getHost():
            messageInfo.setHttpService(self._helpers.buildHttpService(HOST_TO, 8002, httpService.getProtocol()))
