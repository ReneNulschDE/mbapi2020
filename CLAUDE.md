# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Home Assistant custom component integration for Mercedes-Benz vehicles. Connects to Mercedes-Benz API via OAuth2 and WebSocket to monitor and control vehicle features (charging, locks, preconditioning, etc.).

**Python:** 3.13 | **Home Assistant:** >= 2024.02.0 | **Domain:** `mbapi2020`

## Development Commands

```bash
# Setup development environment (installs dependencies + pre-commit hooks)
scripts/setup

# Run ruff formatter
ruff format custom_components/mbapi2020

# Run ruff linter
ruff check custom_components/mbapi2020

# Run pylint on integration
pylint custom_components/mbapi2020

# Validate Home Assistant manifest
# (done via GitHub Actions: hassfest.yaml, HACS_validate.yaml)
```

## Code Style

- **Line length:** 120 characters
- **Formatter:** Ruff (v0.6.8+)
- **Linting:** Ruff and PyLint
- **Type checking:** MyPy (Python 3.13)
- **Import alias conventions:** `voluptuous` as `vol`, `homeassistant.helpers.config_validation` as `cv`
- Pre-commit hooks enforce formatting and check that `USE_PROXY = True` and `VERIFY_SSL = False` are not committed

## Architecture

### Core Files

| File | Purpose |
|------|---------|
| `custom_components/mbapi2020/__init__.py` | Integration setup, async_setup_entry |
| `client.py` | Main API client - OAuth2, WebSocket, command handling |
| `car.py` | Vehicle data model with nested components (Tires, Doors, Windows, Electric, Auxheat, Precond) |
| `coordinator.py` | Home Assistant DataUpdateCoordinator |
| `oauth.py` | OAuth2 authentication with token caching |
| `websocket.py` | Real-time updates via WebSocket |
| `webapi.py` | REST API wrapper for general queries |
| `const.py` | All constants, enums, and sensor definitions |

### Entity Types

Each entity type has its own file: `sensor.py`, `binary_sensor.py`, `lock.py`, `switch.py`, `button.py`, `device_tracker.py`

All entities extend `MercedesMeEntity` base class and use the coordinator pattern.

### Protocol Buffers

The `proto/` directory contains auto-generated Python files from `.proto` definitions. Do not edit these files directly.

### Data Flow

1. `oauth.py` handles authentication and token refresh
2. `client.py` establishes WebSocket connection for real-time updates
3. `coordinator.py` manages data updates and distributes to entities
4. Vehicle state stored in `Car` objects with nested component classes

## Home Assistant Patterns

### Async Programming
- All external I/O operations must be async
- Use `asyncio.gather()` instead of awaiting in loops
- Use `hass.async_add_executor_job()` for blocking operations
- Use `asyncio.sleep()` instead of `time.sleep()`
- Use `@callback` decorator for event loop safe functions

### Error Handling
- `ConfigEntryNotReady`: Temporary setup issues (device offline, timeout)
- `ConfigEntryAuthFailed`: Authentication problems
- `ConfigEntryError`: Permanent setup issues
- `ServiceValidationError`: User input errors
- Keep try blocks minimal - process data after the try/catch
- Bare exceptions allowed only in config flows and background tasks

### Logging Guidelines
- No periods at end of messages
- No integration names/domains (added automatically)
- No sensitive data (keys, tokens, passwords)
- Use lazy logging: `_LOGGER.debug("Message with %s", variable)`
- Use debug level for non-user-facing messages

### Documentation
- File headers: `"""Integration for Mercedes-Benz vehicles."""`
- All functions/methods require docstrings
- American English, sentence case

## Key Patterns

- Config entries for per-account configuration
- Services defined in `services.yaml` with implementations in `services.py`
- PIN required for secured commands (locks, windows, engine start)
- Capability checking enabled by default (can be disabled for North America)
- Entity names use `_attr_translation_key` for translations

## Region Notes

- Tested regions: EU, NA, AU, and others (see README)
- Thailand/India: Use "Europe" region
- China: Currently not working
- North America: Cars 2019 or newer only; may need capability check disabled
