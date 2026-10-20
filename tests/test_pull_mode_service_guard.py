"""Services must be refused while a car is served from REST instead of the socket.

The guard in resolve_config_entry_id() compared the car's data_collection_mode
against the string "pull". That property builds a CarAttribute, and a
CarAttribute never equals a plain string, so the comparison was structurally
false and the guard never fired once. Commands were handed to a websocket that
was not delivering anything.

The guard only becomes reachable together with the REST vehicleattributes fix:
before that the pull path never ran far enough to set the mode.
"""

from __future__ import annotations

import pytest

from custom_components.mbapi2020.car import Car
from custom_components.mbapi2020.services import resolve_config_entry_id
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .fixtures.build import SYNTH_VIN


class _Client:
    def __init__(self, cars):
        self.cars = cars


class _Coordinator(DataUpdateCoordinator):
    """A coordinator that only carries a client - no hass, no refresh."""

    def __init__(self, client):
        # bypass DataUpdateCoordinator.__init__: it wants hass and a logger
        self.client = client


def _domain(mode: str, *, vin: str = SYNTH_VIN) -> dict:
    car = Car(vin)
    car.data_collection_mode = mode
    return {"entry-1": _Coordinator(_Client({vin: car}))}


def test_pull_mode_refuses_the_service() -> None:
    """The regression: this is the branch that never fired."""
    with pytest.raises(ServiceValidationError) as err:
        resolve_config_entry_id(_domain("pull"), SYNTH_VIN)

    assert "pull mode" in str(err.value)


def test_push_mode_resolves_the_entry() -> None:
    """The normal case must stay unaffected."""
    assert resolve_config_entry_id(_domain("push"), SYNTH_VIN) == "entry-1"


def test_the_attribute_itself_never_equals_the_string() -> None:
    """Pin the cause, so the .value does not get optimised away again.

    CarAttribute is a dataclass, so it has a generated __eq__; against a str it
    returns NotImplemented and Python falls back to identity, which is False.
    """
    car = Car(SYNTH_VIN)
    car.data_collection_mode = "pull"

    assert car.data_collection_mode != "pull"
    assert car.data_collection_mode.value == "pull"


def test_an_unmanaged_vin_is_still_reported() -> None:
    """The other error path has to keep working."""
    with pytest.raises(ServiceValidationError) as err:
        resolve_config_entry_id(_domain("push"), "NOT-A-MANAGED-VIN")

    assert "not managed by any coordinator" in str(err.value)


def test_a_second_coordinator_is_not_consulted_after_a_pull_mode_hit() -> None:
    """The car was found; there is no other coordinator that could serve it.

    The old code had an unreachable `continue` behind the raise, suggesting the
    search should go on. It must not: a later coordinator holding the same VIN
    would hand out an entry whose car is equally unreachable.
    """
    blocked = _domain("pull")
    blocked["entry-2"] = _Coordinator(_Client({SYNTH_VIN: Car(SYNTH_VIN)}))

    with pytest.raises(ServiceValidationError) as err:
        resolve_config_entry_id(blocked, SYNTH_VIN)

    assert "pull mode" in str(err.value)


def test_entries_that_are_not_coordinators_are_skipped() -> None:
    """hass.data[DOMAIN] holds more than coordinators."""
    domain = {"some-flag": True, "another": "value"}
    domain.update(_domain("push"))

    assert resolve_config_entry_id(domain, SYNTH_VIN) == "entry-1"
