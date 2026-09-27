"""Shared fixtures for the offline parser tests.

Nothing in this package talks to Mercedes, to a websocket, or to a running
Home Assistant. Every fixture is a synthetic protobuf message built in
code (see ``fixtures/build.py``), so no captured vehicle data is needed to
run the suite and no real VIN ever reaches a log or a test report.

Client.__init__ takes hass, an aiohttp session and a ConfigEntry, and
constructs Oauth/WebApi/Websocket from them. The parsers under test touch
none of that, so make_client() reproduces the plain data attributes from
__init__ and leaves the collaborators unset. If __init__ gains an
attribute that the parsers read, this helper needs the matching line -
that is the only coupling to watch.
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from custom_components.mbapi2020.client import Client  # noqa: E402

from .fixtures.build import SYNTH_FIN, SYNTH_PLATE, SYNTH_VIN  # noqa: E402

__all__ = [
    "REPO_ROOT",
    "SYNTH_FIN",
    "SYNTH_PLATE",
    "SYNTH_VIN",
    "FakeConfigEntry",
    "make_client",
]


class FakeConfigEntry:
    """Minimal stand-in for a ConfigEntry.

    Client.excluded_cars is a read-only property that reads
    config_entry.options, so a plain object is enough.
    """

    def __init__(self, options: dict[str, Any] | None = None, data: dict[str, Any] | None = None) -> None:
        """Store the option/data mappings the parsers read."""
        self.options = options or {}
        self.data = data or {}


def make_client(
    *,
    dataload_complete: bool = True,
    excluded_cars: list[str] | None = None,
    debug_path: Path | None = None,
) -> Client:
    """Return a Client with the parse path live and the I/O collaborators absent.

    dataload_complete defaults to True because that is the branch the
    guards in client.py protect: it runs self.cars.get(vin) followed by an
    assignment, and is where a missing car used to raise.
    """
    client = Client.__new__(Client)  # bypass __init__: no hass, no session, no network

    # --- plain data attributes, mirroring Client.__init__ ---
    # No inline annotations: PEP 526 only allows them on attributes of a
    # class body or self/cls, not on a local object. The types already
    # come from Client, so they are implied.
    client.long_running_operation_active = False
    client.ignition_states = {}
    client.account_blocked = False
    client._ws_reconnect_delay = 0
    client._region = "Europe"
    client._on_dataload_complete = None
    client._dataload_complete_fired = dataload_complete
    client._dataload_fallback_handle = None
    client._coordinator_ref = None
    # rlock off so the parsers take the unthreaded branch
    client._disable_rlock = True
    client._Client__lock = None
    # Never written to: _write_debug_output is stubbed below. Held under a
    # tmp_path per test so the attribute is always present and plausible.
    client._debug_save_path = str(debug_path or Path(tempfile.gettempdir()) / "mbapi2020-offline-tests")
    client.config_entry = FakeConfigEntry(
        options={"excluded_cars": ",".join(excluded_cars or [])},
    )
    client.session_id = "OFFLINE-TEST-SESSION"
    # True so the fallback timer is never armed (it would need hass)
    client._first_vepupdates_processed = True
    client._vepupdates_timeout_seconds = 25
    client._vepupdates_time_first_message = None
    client.cars = {}

    # --- I/O that the parsers call but the tests do not exercise ---
    client._write_debug_output = lambda data, datatype: None  # type: ignore[method-assign]

    return client


@pytest.fixture
def client() -> Client:
    """Return a Client ready to parse a synthetic VEP or VSU message."""
    return make_client()
