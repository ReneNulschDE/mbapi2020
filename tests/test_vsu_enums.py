"""The VSU enum lookup has to agree with the generated protos.

vsu_enums.py maps the enum value names a vehicle_status_updates message
carries to their proto integer, because downstream consumers compare against
numbers. The file is generated, and the last regeneration of the protos moved
two values without it being noticed - a silently wrong number there turns into
a sensor showing the wrong state, with nothing in the log.
"""

from __future__ import annotations

import collections
import importlib

from custom_components.mbapi2020.vsu_enums import VSU_ENUM_VALUE_TO_INT

# The modules whose enums can appear as a value name on the wire. Commands are
# included because the table is also hit by attributes that mirror a command
# enum, and the status side must win where both define a name.
_PROTO_MODULES = ("vehicle_events_pb2", "vehicle_commands_pb2", "vehicleapi_pb2", "protos_pb2")


def _numbers_by_name() -> dict[str, set[int]]:
    """Collect every enum value name of the protos with the numbers it has."""
    found: dict[str, set[int]] = collections.defaultdict(set)

    def walk(descriptor) -> None:
        for enum in descriptor.enum_types:
            for value in enum.values:
                found[value.name].add(value.number)
        for nested in descriptor.nested_types:
            walk(nested)

    for name in _PROTO_MODULES:
        module = importlib.import_module("custom_components.mbapi2020.proto." + name)
        for enum in module.DESCRIPTOR.enum_types_by_name.values():
            for value in enum.values:
                found[value.name].add(value.number)
        for message in module.DESCRIPTOR.message_types_by_name.values():
            walk(message)

    return found


def test_every_mapped_name_exists_in_the_protos() -> None:
    """A name that no proto defines any more can never be looked up."""
    found = _numbers_by_name()

    assert sorted(name for name in VSU_ENUM_VALUE_TO_INT if name not in found) == []


def test_every_mapped_number_is_one_the_protos_give_that_name() -> None:
    """The number has to be one the protos actually assign to the name.

    This is the check that was missing: after a proto update
    SPECIFIC_CATEGORY_PRECONDITIONING_BUTTON moved from 1 to 265 and
    SUB_CATEGORY_BATTERY_CONDITIONING from 1 to 155, while the table kept the
    old numbers.
    """
    found = _numbers_by_name()

    mismatched = {
        name: (number, sorted(found[name]))
        for name, number in VSU_ENUM_VALUE_TO_INT.items()
        if name in found and number not in found[name]
    }

    assert mismatched == {}
