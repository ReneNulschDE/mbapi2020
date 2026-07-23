"""SSL context helper for the MBAPI2020 integration.

Since 2026-07-23 the Mercedes-Benz API endpoints serve a Let's Encrypt
"Generation Y" certificate chain (leaf <- YR2 <- ISRG Root YR) without the
cross-sign to ISRG Root X1. The new ISRG Root YR is not yet included in the
default trust stores, so certificate verification fails with
"unable to get local issuer certificate". Until Mercedes fixes the served
chain or the new root reaches the trust stores, the official cross-signed
root (Root YR signed by ISRG Root X1, see https://letsencrypt.org/certificates/)
shipped with this integration is added to the verification context.
"""

from __future__ import annotations

from os import environ
from pathlib import Path
import ssl

import certifi

from homeassistant.core import HomeAssistant

from .const import VERIFY_SSL

_CROSS_SIGNED_ROOT_PATH = Path(__file__).parent / "certs" / "isrg-root-yr-by-x1.pem"

_ssl_context: ssl.SSLContext | None = None


def _create_ssl_context() -> ssl.SSLContext:
    """Create a client SSL context matching Home Assistant's, extended with the cross-signed root."""
    try:
        from homeassistant.util.ssl import create_client_context  # noqa: PLC0415

        context = create_client_context()
    except ImportError:
        # Older Home Assistant without create_client_context: replicate its options
        cafile = environ.get("REQUESTS_CA_BUNDLE", certifi.where())
        context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH, cafile=cafile)
    # Same ALPN setting as Home Assistant's aiohttp client sessions
    context.set_alpn_protocols(["http/1.1"])
    context.load_verify_locations(cafile=str(_CROSS_SIGNED_ROOT_PATH))
    return context


async def async_get_ssl_context(hass: HomeAssistant) -> ssl.SSLContext | bool:
    """Return the shared SSL context, creating it in the executor on first use."""
    global _ssl_context  # noqa: PLW0603

    if not VERIFY_SSL:
        return False
    if _ssl_context is None:
        _ssl_context = await hass.async_add_executor_job(_create_ssl_context)
    return _ssl_context


def get_cached_ssl_context() -> ssl.SSLContext | bool:
    """Return the cached SSL context, falling back to aiohttp default verification."""
    if not VERIFY_SSL:
        return False
    if _ssl_context is None:
        return True
    return _ssl_context
