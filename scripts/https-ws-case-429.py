"""Simple HTTP Server to simulate http429."""

from __future__ import annotations

import logging
import ssl
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

HTTP_SERVER_IP = "0.0.0.0"
HTTP_SERVER_PORT = 8001
LOGGER = logging.getLogger(__package__)


class MBAPI2020SimulatorServer(BaseHTTPRequestHandler):
    """Simple HTTP Server to simulate the MBAPI2020 API."""

    def do_GET(self):
        """Answer get requests."""

        parsed = urlparse(self.path)
        if parsed.path == "/v2/ws":
            self.send_response(429)
            self.send_header("Content-type", "")
            self.end_headers()
            self.wfile.write("".encode("utf-8"))
            return

    def do_POST(self):
        """Answer post requests."""
        self.do_GET()


def set_logger():
    """Set Logger properties."""

    fmt = (
        "%(asctime)s.%(msecs)03d %(levelname)s (%(threadName)s) [%(name)s] %(message)s"
    )
    LOGGER.setLevel(logging.DEBUG)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(fmt)
    handler.setFormatter(formatter)
    LOGGER.addHandler(handler)


if __name__ == "__main__":
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(
        certfile="../local/selfsigned.crt", keyfile="../local/selfsigned.key"
    )
    context.check_hostname = False

    webServer = HTTPServer((HTTP_SERVER_IP, HTTP_SERVER_PORT), MBAPI2020SimulatorServer)
    webServer.socket = context.wrap_socket(webServer.socket, server_side=True)

    set_logger()

    LOGGER.debug("Server started https://%s:%s", HTTP_SERVER_IP, HTTP_SERVER_PORT)

    webServer.serve_forever()
    webServer.server_close()

    LOGGER.debug("Server stopped.")
