"""Cover support for Mercedes cars with Mercedes ME."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityDescription,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later

from . import MercedesMeEntity, MercedesMeEntityDescription
from .car import Car
from .const import CONF_FT_DISABLE_CAPABILITY_CHECK, DOMAIN, LOGGER, STATE_CONFIRMATION_DURATION
from .coordinator import MBAPI2020DataUpdateCoordinator
from .helper import LogHelper as loghelper

# Positions for the individual windows, based on the proto enum Windowstatus:
# 0 INTERMEDIATE, 1 COMPLETELY_OPENED, 2 COMPLETELY_CLOSED, 3 AIRING_POSITION,
# 4 INTERMEDIATE_AIRING_POSITION, 5 RUNNING
# RUNNING is deliberately absent: it means the window is moving and carries no
# direction, so any position would be a guess. The entity reports unknown until
# the car sends the status it settled on.
WINDOW_STATUS_POSITIONS: dict[int, int] = {0: 50, 1: 100, 2: 0, 3: 10, 4: 50}

# Positions for the window summary, based on the proto enum WindowStatusOverall:
# 0 OPEN, 1 CLOSED, 2 COMPLETELY_OPEN, 3 AIRING, 4 RUNNING
# Note the numbering differs from the individual windows above, and RUNNING is
# absent here for the same reason
WINDOW_STATUS_OVERALL_POSITIONS: dict[int, int] = {0: 50, 1: 0, 2: 100, 3: 10}

# Retrieval status values that indicate the car did not report a usable value
WINDOW_STATUS_INVALID_RETRIEVAL_STATUS = {3, "3", 4, "4", "NOT_RECEIVED", "error"}


@dataclass(frozen=True, kw_only=True)
class MercedesMeCoverEntityDescription(MercedesMeEntityDescription, CoverEntityDescription):
    """Configuration class for MercedesMe cover entities."""

    status_attribute: str
    position_args_fn: Callable[[int], dict[str, int | None]]


def _all_windows_position_args(position: int) -> dict[str, int | None]:
    return {
        "front_left": position,
        "front_right": position,
        "rear_left": position,
        "rear_right": position,
    }


WINDOW_COVER_DESCRIPTIONS: list[MercedesMeCoverEntityDescription] = [
    MercedesMeCoverEntityDescription(
        key="windows",
        translation_key="windows",
        device_class=CoverDeviceClass.WINDOW,
        status_attribute="windowStatusOverall",
        position_args_fn=_all_windows_position_args,
        check_capability_fn=lambda car: car.check_capabilities(
            ["WINDOWS_OPEN", "WINDOWS_CLOSE", "variableOpenableWindow"]
        ),
    ),
    MercedesMeCoverEntityDescription(
        key="window_front_left",
        translation_key="window_front_left",
        device_class=CoverDeviceClass.WINDOW,
        status_attribute="windowstatusfrontleft",
        position_args_fn=lambda position: {
            "front_left": position,
            "front_right": None,
            "rear_left": None,
            "rear_right": None,
        },
        check_capability_fn=lambda car: car.check_capabilities(["variableOpenableWindow"]),
    ),
    MercedesMeCoverEntityDescription(
        key="window_front_right",
        translation_key="window_front_right",
        device_class=CoverDeviceClass.WINDOW,
        status_attribute="windowstatusfrontright",
        position_args_fn=lambda position: {
            "front_left": None,
            "front_right": position,
            "rear_left": None,
            "rear_right": None,
        },
        check_capability_fn=lambda car: car.check_capabilities(["variableOpenableWindow"]),
    ),
    MercedesMeCoverEntityDescription(
        key="window_rear_left",
        translation_key="window_rear_left",
        device_class=CoverDeviceClass.WINDOW,
        status_attribute="windowstatusrearleft",
        position_args_fn=lambda position: {
            "front_left": None,
            "front_right": None,
            "rear_left": position,
            "rear_right": None,
        },
        check_capability_fn=lambda car: car.check_capabilities(["variableOpenableWindow"]),
    ),
    MercedesMeCoverEntityDescription(
        key="window_rear_right",
        translation_key="window_rear_right",
        device_class=CoverDeviceClass.WINDOW,
        status_attribute="windowstatusrearright",
        position_args_fn=lambda position: {
            "front_left": None,
            "front_right": None,
            "rear_left": None,
            "rear_right": position,
        },
        check_capability_fn=lambda car: car.check_capabilities(["variableOpenableWindow"]),
    ),
]


def _status_to_position(status: Any, *, overall: bool = False) -> int | None:
    """Translate a reported window status into a cover position."""
    if status is None:
        return None

    # The REST fallback builds a synthetic windowStatusOverall where True means
    # that all windows are closed
    if isinstance(status, bool):
        return 0 if status else 100

    if isinstance(status, str):
        normalized = status.strip().upper()
        if normalized == "CLOSED":
            return 0
        if normalized == "OPEN":
            return 100

    positions = WINDOW_STATUS_OVERALL_POSITIONS if overall else WINDOW_STATUS_POSITIONS
    try:
        return positions.get(int(status))
    except (TypeError, ValueError):
        return None


class MercedesMeCover(MercedesMeEntity, CoverEntity):
    """Representation of a Mercedes Me cover."""

    entity_description: MercedesMeCoverEntityDescription

    def __init__(self, description: MercedesMeCoverEntityDescription, vin: str, coordinator) -> None:
        """Initialize the cover."""
        self._expected_position: int | None = None
        self._confirmation_handle = None
        self._skip_capability_check = coordinator.config_entry.options.get(CONF_FT_DISABLE_CAPABILITY_CHECK, False)

        super().__init__(description.key, description, vin, coordinator)

    @property
    def supported_features(self) -> CoverEntityFeature:
        """Return the supported features."""
        features = CoverEntityFeature(0)
        supports_variable_window = (
            self._skip_capability_check or self._car.features.get("variableOpenableWindow") is True
        )

        if self.entity_description.key == "windows":
            if (
                self._skip_capability_check
                or self._car.features.get("WINDOWS_OPEN") is True
                or supports_variable_window
            ):
                features |= CoverEntityFeature.OPEN
            if (
                self._skip_capability_check
                or self._car.features.get("WINDOWS_CLOSE") is True
                or supports_variable_window
            ):
                features |= CoverEntityFeature.CLOSE
        else:
            features |= CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

        if supports_variable_window:
            features |= CoverEntityFeature.SET_POSITION

        return features

    @property
    def current_cover_position(self) -> int | None:
        """Return current position of cover."""
        if self._expected_position is not None:
            return self._expected_position

        return _status_to_position(self._window_status, overall=self._is_overall_cover)

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed."""
        if self._expected_position is not None:
            return self._expected_position == 0

        current_position = _status_to_position(self._window_status, overall=self._is_overall_cover)
        return None if current_position is None else current_position == 0

    @property
    def is_opening(self) -> bool | None:
        """Return if the cover is opening."""
        if self._expected_position is not None:
            current_position = _status_to_position(self._window_status, overall=self._is_overall_cover)
            if current_position is not None:
                return self._expected_position > current_position

        return None

    @property
    def is_closing(self) -> bool | None:
        """Return if the cover is closing."""
        if self._expected_position is not None:
            current_position = _status_to_position(self._window_status, overall=self._is_overall_cover)
            if current_position is not None:
                return self._expected_position < current_position

        return None

    @property
    def _window_status(self) -> Any:
        status_attribute = self.entity_description.status_attribute
        retrieval_status = self._get_car_value("windows", status_attribute, "retrievalstatus", "error")
        if retrieval_status in WINDOW_STATUS_INVALID_RETRIEVAL_STATUS:
            return None

        return self._get_car_value("windows", status_attribute, "value", None)

    @property
    def _is_overall_cover(self) -> bool:
        return self.entity_description.status_attribute == "windowStatusOverall"

    @property
    def _has_configured_pin(self) -> bool:
        return bool(self._coordinator.client.pin)

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        self._raise_if_pin_required()

        if self.entity_description.key == "windows" and (
            self._skip_capability_check or self._car.features.get("WINDOWS_OPEN") is True
        ):
            await self._coordinator.client.windows_open(self._vin)
            self._set_expected_position(100)
            return

        await self._async_set_position(100)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close cover."""
        if self.entity_description.key == "windows" and (
            self._skip_capability_check or self._car.features.get("WINDOWS_CLOSE") is True
        ):
            await self._coordinator.client.windows_close(self._vin)
            self._set_expected_position(0)
            return

        await self._async_set_position(0)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        await self._async_set_position(kwargs[ATTR_POSITION])

    async def _async_set_position(self, position: int) -> None:
        """Move the configured window or windows to a specific position."""
        self._raise_if_pin_required()

        if not self._skip_capability_check and self._car.features.get("variableOpenableWindow") is not True:
            LOGGER.warning(
                "Can't move windows for car %s. Feature not available for this car.",
                loghelper.Mask_VIN(self._vin),
            )
            return

        position_args = self.entity_description.position_args_fn(position)
        await self._coordinator.client.windows_move(
            self._vin,
            position_args["front_left"],
            position_args["front_right"],
            position_args["rear_left"],
            position_args["rear_right"],
        )
        self._set_expected_position(position)

    def _raise_if_pin_required(self) -> None:
        """Raise when the requested window command needs a configured PIN."""
        if self._has_configured_pin:
            return

        raise ServiceValidationError("Security PIN is required to open or move windows")

    def _set_expected_position(self, position: int) -> None:
        """Set expected position until the car reports the new status."""
        self._expected_position = position

        if self._confirmation_handle:
            self._confirmation_handle()

        self._confirmation_handle = async_call_later(
            self.hass, STATE_CONFIRMATION_DURATION, self._reset_expected_position
        )
        self.async_write_ha_state()

    async def _reset_expected_position(self, _):
        """Reset the expected position after confirmation duration."""
        self._expected_position = None
        self._confirmation_handle = None
        self.async_write_ha_state()

    def _mercedes_me_update(self) -> None:
        """Update Mercedes Me entity."""
        if self._expected_position is not None:
            actual_position = _status_to_position(self._window_status, overall=self._is_overall_cover)
            if actual_position == self._expected_position:
                if self._confirmation_handle:
                    self._confirmation_handle()
                    self._confirmation_handle = None
                self._expected_position = None

        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the cover platform for Mercedes Me."""

    coordinator: MBAPI2020DataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    skip_capability_check: bool = config_entry.options.get(CONF_FT_DISABLE_CAPABILITY_CHECK, False)

    if not coordinator.client.cars:
        LOGGER.info("No Cars found.")
        return

    def check_capability(car: Car, description: MercedesMeCoverEntityDescription) -> bool:
        """Check if the car supports the necessary capability for the cover description."""
        if skip_capability_check or description.check_capability_fn(car):
            return True

        vin_masked = loghelper.Mask_VIN(car.finorvin)
        LOGGER.debug(
            "Skipping cover '%s' for VIN '%s' due to lack of required capability",
            description.key,
            vin_masked,
        )
        return False

    entities: list[MercedesMeCover] = [
        MercedesMeCover(description, car.finorvin, coordinator)
        for car in coordinator.client.cars.values()
        for description in WINDOW_COVER_DESCRIPTIONS
        if check_capability(car, description)
    ]

    async_add_entities(entities)
