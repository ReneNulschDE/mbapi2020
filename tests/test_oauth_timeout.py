"""Regression coverage for authentication preflight timeouts."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import ClientSession, ClientTimeout
import pytest

from custom_components.mbapi2020 import async_setup_entry
from custom_components.mbapi2020.app_version import AppVersionManager
from custom_components.mbapi2020.const import REGION_EUROPE
from custom_components.mbapi2020.errors import MBAuthError
from custom_components.mbapi2020.oauth import Oauth
from homeassistant.exceptions import ConfigEntryNotReady

EXPIRED_TOKEN = {"access_token": "expired-test-token", "refresh_token": "test-refresh-token", "expires_at": 0}
TOKEN_RESPONSE = {"access_token": "new-test-token", "expires_in": 3600}


def make_context(payload: dict) -> MagicMock:
    """Return a successful JSON response without network I/O."""
    response = MagicMock()
    response.status = 200
    response.json = AsyncMock(return_value=payload.copy())
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=response)
    context.__aexit__ = AsyncMock(return_value=False)
    return context


def make_oauth(session: MagicMock) -> tuple[Oauth, SimpleNamespace, SimpleNamespace]:
    """Build real OAuth logic with synthetic stored credentials."""
    hass = SimpleNamespace(data={}, config_entries=MagicMock())
    entry = SimpleNamespace(entry_id="test-entry", data={"token": EXPIRED_TOKEN.copy()})
    manager = AppVersionManager(REGION_EUROPE)
    manager.async_refresh = AsyncMock()
    oauth = Oauth(hass, session, REGION_EUROPE, entry, manager)
    return oauth, hass, entry


def make_session() -> MagicMock:
    """Provide a session that will not create a real HTTP client."""
    session = MagicMock(spec=ClientSession)
    session.closed = False
    return session


@pytest.mark.parametrize("operation", ["token", "pin"])
def test_preflight_has_bounded_timeout(operation: str) -> None:
    """Only the configuration preflight gets a 20-second total timeout."""
    session = make_session()
    session.request.side_effect = [make_context({}), make_context(TOKEN_RESPONSE)]
    oauth, _, _ = make_oauth(session)

    if operation == "token":
        result = asyncio.run(oauth.async_get_cached_token())
        assert result["access_token"] == "new-test-token"
        assert result["refresh_token"] == "test-refresh-token"
    else:
        asyncio.run(oauth.request_pin("test@example.invalid", "test-nonce"))

    assert session.request.call_count == 2
    preflight, authentication = session.request.call_args_list
    assert preflight.args[0] == "get"
    assert preflight.args[1].endswith("/v1/config")
    timeout = preflight.kwargs.get("timeout")
    assert isinstance(timeout, ClientTimeout)
    assert timeout.total == 20
    assert "timeout" not in authentication.kwargs


@pytest.mark.parametrize("stage", ["request", "json"])
def test_setup_timeout_preserves_credentials_and_allows_retry(stage: str) -> None:
    """A failed preflight becomes a setup retry and releases the token lock."""
    session = make_session()
    context = make_context({})
    error = TimeoutError("synthetic preflight timeout")
    if stage == "request":
        context.__aenter__.side_effect = error
    else:
        context.__aenter__.return_value.json.side_effect = error
    session.request.side_effect = [context, make_context({}), make_context(TOKEN_RESPONSE)]
    oauth, hass, entry = make_oauth(session)
    client = SimpleNamespace(oauth=oauth, set_rlock_mode=AsyncMock())
    coordinator = SimpleNamespace(client=client)

    async def run() -> None:
        """Exercise the setup failure and subsequent refresh in one event loop."""
        with (
            patch("custom_components.mbapi2020.MBAPI2020DataUpdateCoordinator", return_value=coordinator),
            pytest.raises(ConfigEntryNotReady) as raised,
        ):
            await async_setup_entry(hass, entry)

        assert raised.value.__cause__ is error
        assert entry.data["token"] == EXPIRED_TOKEN
        hass.config_entries.async_update_entry.assert_not_called()
        # A leaked refresh lock would prevent the second call from finishing.
        result = await asyncio.wait_for(oauth.async_get_cached_token(), timeout=1)
        assert result["access_token"] == "new-test-token"
        assert result["refresh_token"] == "test-refresh-token"
        hass.config_entries.async_update_entry.assert_called_once()

    asyncio.run(run())


def test_setup_cancellation_is_not_converted_to_retry() -> None:
    """Unloading while a preflight is pending still cancels setup."""
    session = make_session()
    context = make_context({})
    context.__aenter__.side_effect = asyncio.CancelledError
    session.request.side_effect = [context]
    oauth, hass, entry = make_oauth(session)
    coordinator = SimpleNamespace(client=SimpleNamespace(oauth=oauth, set_rlock_mode=AsyncMock()))

    with (
        patch("custom_components.mbapi2020.MBAPI2020DataUpdateCoordinator", return_value=coordinator),
        pytest.raises(asyncio.CancelledError),
    ):
        asyncio.run(async_setup_entry(hass, entry))

    assert entry.data["token"] == EXPIRED_TOKEN
    hass.config_entries.async_update_entry.assert_not_called()


def test_preflight_authentication_error_is_not_converted_to_retry() -> None:
    """An actual authentication rejection remains an authentication failure."""
    session = make_session()
    context = make_context({})
    response = context.__aenter__.return_value
    response.status = 401
    response.text = AsyncMock(return_value='{"code":"unauthorized","errors":[]}')
    session.request.side_effect = [context]
    oauth, hass, entry = make_oauth(session)
    coordinator = SimpleNamespace(client=SimpleNamespace(oauth=oauth, set_rlock_mode=AsyncMock()))

    with (
        patch("custom_components.mbapi2020.MBAPI2020DataUpdateCoordinator", return_value=coordinator),
        pytest.raises(MBAuthError),
    ):
        asyncio.run(async_setup_entry(hass, entry))

    hass.config_entries.async_update_entry.assert_not_called()
