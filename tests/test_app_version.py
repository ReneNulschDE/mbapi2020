"""Regression coverage for optional app-version HTTP lookups."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from aiohttp import ClientSession, ClientTimeout
import pytest

from custom_components.mbapi2020.app_version import AppVersionManager
from custom_components.mbapi2020.const import REGION_EUROPE

CONFIG_PAYLOAD = {
    "forceUpdate": {
        "status": "FORCE",
        "storeUrl": "https://apps.apple.com/de/app/mercedes-benz/id123456789",
    },
}
STORE_PAYLOAD = {"results": [{"version": "999.0.0"}]}


def make_session() -> MagicMock:
    """Provide successful config and App Store responses without network I/O."""
    session = MagicMock(spec=ClientSession)
    contexts = []
    for payload in (CONFIG_PAYLOAD, STORE_PAYLOAD):
        response = MagicMock()
        response.status = 200
        response.json = AsyncMock(return_value=payload)
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=response)
        context.__aexit__ = AsyncMock(return_value=False)
        contexts.append(context)
    session.get.side_effect = contexts
    return session


def test_version_lookup_has_bounded_requests() -> None:
    """Successful lookups use a short total timeout for both HTTP requests."""
    manager = AppVersionManager(REGION_EUROPE)
    session = make_session()

    assert asyncio.run(manager.async_refresh(session, force=True)) is True
    assert manager.application_version == "999.0.0"
    assert session.get.call_count == 2
    for call in session.get.call_args_list:
        timeout = call.kwargs.get("timeout")
        assert isinstance(timeout, ClientTimeout)
        assert timeout.total == 10


@pytest.mark.parametrize("endpoint", ["config", "app_store"])
@pytest.mark.parametrize("stage", ["request", "json"])
def test_timeout_preserves_current_version(endpoint: str, stage: str) -> None:
    """A total timeout is optional metadata failure, not an authentication failure."""
    manager = AppVersionManager(REGION_EUROPE)
    original_version = manager.application_version
    session = make_session()
    contexts = list(session.get.side_effect)
    context = contexts[0 if endpoint == "config" else 1]
    if stage == "request":
        context.__aenter__.side_effect = TimeoutError
    else:
        context.__aenter__.return_value.json.side_effect = TimeoutError
    session.get.side_effect = contexts

    assert asyncio.run(manager.async_refresh(session, force=True)) is False
    assert manager.application_version == original_version
    assert session.get.call_count == (1 if endpoint == "config" else 2)

    # A later successful refresh must still acquire the manager's lock and update.
    assert asyncio.run(manager.async_refresh(make_session(), force=True)) is True
    assert manager.application_version == "999.0.0"


@pytest.mark.parametrize("endpoint", ["config", "app_store"])
def test_cancellation_is_not_swallowed(endpoint: str) -> None:
    """Unloading the integration can still cancel a pending version lookup."""
    manager = AppVersionManager(REGION_EUROPE)
    session = make_session()
    contexts = list(session.get.side_effect)
    context = contexts[0 if endpoint == "config" else 1]
    context.__aenter__.side_effect = asyncio.CancelledError
    session.get.side_effect = contexts

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(manager.async_refresh(session, force=True))
