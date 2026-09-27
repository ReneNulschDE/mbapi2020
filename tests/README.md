# Offline parser tests

Tests for the protobuf parsing path that need no Mercedes account, no
vehicle, and no network.

## Why these exist

The debugging workflow in `scripts/` (Burp redirector, the fixture HTTPS
servers in `https-bff.py` and `https-ws-case-429.py`) works from recorded
responses, and those recordings come from a real car. That is fine for
the maintainer, who has the car, but it means a contributor cannot
reproduce a parsing bug without capturing a payload of their own - and
capturing one puts a real VIN, plate and location into a file that then
gets pasted into an issue.

The fixtures here are built in code instead. `fixtures/build.py`
constructs `vehicle_events_pb2.PushMessage` objects from fabricated
values, so the suite is self-contained and no real identifier is ever
written to disk or to a test report. The synthetic VIN keeps the correct
17-character shape so any length validation still exercises properly.

## Running

```bash
pip install -r requirements.txt   # pytest
pytest tests/
```

`Client.__init__` needs a `HomeAssistant` instance and builds
`Oauth`/`WebApi`/`Websocket` from it. The parsers under test read none of
those, so `conftest.make_client()` reproduces the plain data attributes
from `__init__` on a bare object and leaves the collaborators unset. That
is the only coupling to keep in step: if `Client.__init__` gains an
attribute that the parsers read, the helper needs the matching line and
the tests will fail with an `AttributeError` until it is added.

## What is covered

`test_parser_offline.py` - the fixtures themselves: both envelope shapes
(VEP and VSU are structured differently) survive the same
serialise/re-parse boundary `websocket.py` applies to a live frame, and
both parsers build a `Car` from them.

`test_regressions.py` - guards for defects that reached a released
integration. Each one is written to fail on the old shape, so a
regression surfaces at the specific site rather than as a downstream
symptom. The `data_collection_mode` check parses `client.py` with `ast`
instead of grepping, so a comment mentioning the same words cannot
satisfy it.
