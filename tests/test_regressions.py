"""Regression guards for defects that reached a released integration.

Each test here corresponds to a bug that was reachable in normal
operation. They are written to fail loudly on the old shape rather than
to assert an implementation detail, so a refactor that keeps the
behaviour does not break them.

The VEP/VSU parser tests in test_parser_offline.py establish that the
synthetic fixtures are sound; these assume that.
"""

from __future__ import annotations

import ast

import pytest

from custom_components.mbapi2020.car import Car

from .conftest import REPO_ROOT, SYNTH_VIN, make_client
from .fixtures.build import build_vep_updates

COMPONENT = REPO_ROOT / "custom_components" / "mbapi2020"


# --- 1. an untracked VIN must not raise when the dataload is complete ---


def test_vep_update_does_not_raise_when_the_lookup_misses() -> None:
    """A missing entry from self.cars must be skipped, not dereferenced.

    The dataload-complete branch did ``current_car = self.cars.get(vin)``
    and then assigned to ``current_car.data_collection_mode`` before
    consulting the guard, so a lookup returning None raised
    AttributeError part-way through the method.

    The lookup does not normally miss here, because _build_car has just
    registered the car. It does miss for an excluded car and while unload
    is clearing state, neither of which needs a real vehicle to model -
    so _build_car is stubbed out to make the lookup miss.
    """
    client = make_client(dataload_complete=True)
    client._build_car = lambda *args, **kwargs: None  # type: ignore[method-assign]

    # Must not raise. If the guard regresses this is where it surfaces.
    client._process_vep_updates(build_vep_updates())

    assert client.cars == {}


def test_pull_path_does_not_raise_for_vin_removed_after_build() -> None:
    """The same guard, reached through _process_rest_vep_update.

    That method builds the car first and then re-reads it from self.cars
    under the dataload-complete branch, so the dereference and the lookup
    are separated. A car that is not in the dict must still be handled.
    """
    client = make_client(dataload_complete=True)
    client.cars.clear()

    # Force the post-build lookup to miss, as it would for an excluded car
    # or while unload is clearing state.
    client._build_car = lambda *args, **kwargs: None  # type: ignore[method-assign]

    client._process_rest_vep_update(build_vep_updates())

    assert client.cars == {}


# --- 2. a listener may add or remove callbacks while being notified ---


def test_publish_updates_tolerates_a_listener_that_registers_another() -> None:
    """Mutating the listener set from inside a callback must not raise.

    The set was iterated directly, and a callback that creates an entity
    adds itself, which Python rejects with "Set changed size during
    iteration". Iterating a snapshot takes effect from the next update.
    """
    car = Car(SYNTH_VIN)
    called: list[str] = []

    def first() -> None:
        called.append("first")
        car.add_update_listener(lambda: called.append("late"))

    car.add_update_listener(first)

    car.publish_updates()  # must not raise
    assert called == ["first"], "the late listener must not run in the same pass"

    # Iterating a snapshot means a listener added during the pass takes
    # effect from the next one, not from the remainder of this one.
    car.publish_updates()
    assert called == ["first", "first", "late"]


def test_publish_updates_tolerates_a_listener_that_removes_itself() -> None:
    """Removal from inside a callback is the same hazard in the other direction."""

    class SelfRemoving:
        def __init__(self) -> None:
            self.count = 0

        def __call__(self) -> None:
            self.count += 1
            car.remove_update_callback(self)

    car = Car(SYNTH_VIN)
    remover = SelfRemoving()
    car.add_update_listener(remover)

    car.publish_updates()  # must not raise
    car.publish_updates()
    assert remover.count == 1


# --- 3. data_collection_mode is only ever assigned on a real Car ---


def _data_collection_sites() -> list[tuple[int, bool, str]]:
    """Return (lineno, guard_precedes_deref, mode) for each assignment.

    Parsed rather than grepped, so the check cannot be satisfied by a
    comment or a string that happens to contain the same words.
    """
    tree = ast.parse((COMPONENT / "client.py").read_text(encoding="utf-8"))
    sites: list[tuple[int, bool, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = ast.unparse(node.test)
        if "dataload_complete_fired" not in test or "not " in test:
            continue
        body = ast.unparse(ast.Module(body=node.body, type_ignores=[]))
        if "data_collection_mode" not in body:
            continue
        guarded = body.index("if current_car") < body.index("data_collection_mode")
        mode = "pull" if '"pull"' in body else "push"
        sites.append((node.lineno, guarded, mode))

    return sites


def test_client_has_data_collection_mode_sites() -> None:
    """Sanity check: the helper above really did find the sites."""
    assert _data_collection_sites(), "no data_collection_mode sites found - the guard test would be vacuous"


@pytest.mark.parametrize(("lineno", "guarded", "mode"), _data_collection_sites(), ids=lambda v: str(v))
def test_data_collection_mode_is_assigned_only_after_the_guard(lineno: int, guarded: bool, mode: str) -> None:
    """Every assignment must sit inside `if current_car:`.

    The dereference before the guard was the defect, and both the pull
    and the push paths had it.
    """
    assert guarded, f"line {lineno}: data_collection_mode ({mode}) is assigned before the None guard"


# --- 4. optional masterdata nests are walked defensively ---


def test_baumuster_description_survives_missing_and_null_nesting() -> None:
    """SalesRelatedInformation may be absent, null, or empty.

    The original chain defaulted a missing level to a string and then
    called .get() on it, so a car with no sales information raised
    AttributeError during setup.
    """
    source = (COMPONENT / "__init__.py").read_text(encoding="utf-8")
    assert '.get("salesRelatedInformation", "").get(' not in source, (
        "the unguarded .get(...) chain is back; walk the dicts with `or {}` instead"
    )

    def baumuster(car: dict) -> str:
        sales_information = car.get("salesRelatedInformation") or {}
        baumuster_data = sales_information.get("baumuster") or {}
        return baumuster_data.get("baumusterDescription", "")

    assert baumuster({}) == ""
    assert baumuster({"salesRelatedInformation": None}) == ""
    assert baumuster({"salesRelatedInformation": {}}) == ""
    assert baumuster({"salesRelatedInformation": {"baumuster": {}}}) == ""
    assert baumuster({"salesRelatedInformation": {"baumuster": {"baumusterDescription": "GLC 200"}}}) == "GLC 200"


# --- 5. setup-time NameError and unsubstituted messages ---


def test_capabilities_is_bound_before_the_try_that_may_fail() -> None:
    """Capabilities is assigned after the try, so it must be pre-bound.

    When the command-capabilities request raised, the assignment never
    ran and the later `current_car.capabilities = capabilities` raised
    NameError instead.
    """
    source = (COMPONENT / "__init__.py").read_text(encoding="utf-8")
    assert "capabilities = None" in source, (
        "capabilities is not pre-bound; a failed capabilities request raises NameError"
    )


def test_webapi_has_no_unused_ssl_import() -> None:
    """`import ssl` was never referenced and was flagged by ruff as F401."""
    source = (COMPONENT / "webapi.py").read_text(encoding="utf-8")
    assert "\nimport ssl" not in source


def test_oauth_errors_do_not_pass_printf_placeholders() -> None:
    """The two login errors passed "%s" to an exception that never formats.

    The result was the literal text 'Unexpected login result: %s' with
    the payload unrendered in args, so the diagnostic never showed the
    value that caused it.
    """
    source = (COMPONENT / "oauth.py").read_text(encoding="utf-8")
    for message in (
        "Problem accepting legal terms during login. %s",
        "Unexpected login result: %s",
    ):
        assert message not in source, f"unsubstituted %s remains: {message!r}"


def test_shutdown_task_is_held_in_a_reference() -> None:
    """loop.create_task() result was discarded, so GC could collect it mid-flight."""
    source = (COMPONENT / "websocket.py").read_text(encoding="utf-8")
    assert "self._shutdown_task = loop.create_task(" in source, (
        "the shutdown task is not stored; keep a reference so it cannot be collected"
    )
    assert "loop.create_task(self._graceful_shutdown" not in source, (
        "the shutdown task is still created without being stored"
    )
