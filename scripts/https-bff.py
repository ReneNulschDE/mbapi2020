from http.server import HTTPServer, SimpleHTTPRequestHandler
import logging
import os
from pathlib import Path
import ssl
import sys

LOGGER = logging.getLogger(__package__)


class SecureHTTPRequestHandler(SimpleHTTPRequestHandler):
    """Überschreibt die Methode, um das Basisverzeichnis anzupassen."""

    def translate_path(self, path):
        """Basisverzeichnis für Dateien."""
        base_directory = "../local"

        # Anhängen von ".json", wenn der Path keine Dateiendung enthält
        if not Path(path).suffix:  # Kein "." in der Datei
            path += ".json"

        # Normalisierung des Pfads
        path = super().translate_path(path)

        # Ersetzen des Basisverzeichnisses durch das angegebene
        relative_path = os.path.relpath(path, Path.cwd())
        LOGGER.debug("request %s", Path(base_directory) / relative_path)
        return Path(base_directory) / relative_path


def set_logger():
    """Set Logger properties."""

    fmt = "%(asctime)s.%(msecs)03d %(levelname)s (%(threadName)s) [%(name)s] %(message)s"
    LOGGER.setLevel(logging.DEBUG)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(fmt)
    handler.setFormatter(formatter)
    LOGGER.addHandler(handler)


def start_server(host="127.0.0.1", port=8002, certfile="../local/selfsigned.crt", keyfile="../local/selfsigned.key"):
    """HTTPS-Server mit dem spezifizierten Handler."""
    httpd = HTTPServer((host, port), SecureHTTPRequestHandler)

    # SSL-Kontext erstellen
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(certfile=certfile, keyfile=keyfile)

    # Socket mit SSL-Kontext umschließen
    httpd.socket = ssl_context.wrap_socket(httpd.socket, server_side=True)

    LOGGER.debug("HTTPS-Server gestartet auf https://%s:%s", host, port)
    LOGGER.debug("Daten werden aus dem Verzeichnis ../local geladen.")
    httpd.serve_forever()


if __name__ == "__main__":
    start_server()
