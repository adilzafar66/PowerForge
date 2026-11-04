"""Registry-derived prompt metadata. Never reads a reference workbook or evaluates requirements."""

from collections.abc import Iterable

from powerforge_engineering_model.registry import (
    get_equipment_definition,
    list_equipment_definitions,
    supported_input_units,
)
from powerforge_engineering_model.registry_v1 import REGISTRY
from powerforge_extraction.identities import canonical_json, identity_hash

CONTEXT_VERSION = "engineering-registry-context-v1"
MAX_CONTEXT_BYTES = 96 * 1024


def equipment_catalog() -> dict:
    """All registered types, with no speculative classification-based exclusions."""
    return {
        "context_version": CONTEXT_VERSION,
        "registry_version": REGISTRY.registry_version,
        "equipment_types": [
            {"key": equipment.key.value, "display_name": equipment.display_name}
            for equipment in sorted(list_equipment_definitions(), key=lambda item: item.key)
        ],
    }


def attribute_context(equipment_types: Iterable[str]) -> dict:
    """Known type subsets only; empty context still permits raw isolated observations."""
    definitions = [get_equipment_definition(key) for key in sorted(set(equipment_types))]
    result = {
        "context_version": CONTEXT_VERSION,
        "registry_version": REGISTRY.registry_version,
        "type_catalog": equipment_catalog()["equipment_types"],
        "equipment_types": [
            {
                "key": equipment.key.value,
                "display_name": equipment.display_name,
                "attributes": [
                    {
                        "key": attribute.key,
                        "display_name": attribute.display_name,
                        "value_type": attribute.value_type.value,
                        "canonical_unit": attribute.canonical_unit,
                        "supported_input_units": list(
                            supported_input_units(equipment.key, attribute.key)
                        ),
                        "allowed_values": list(attribute.allowed_values),
                        "notes": attribute.notes,
                    }
                    for attribute in sorted(equipment.attributes, key=lambda item: item.key)
                ],
            }
            for equipment in definitions
        ],
    }
    if len(canonical_json(result).encode()) > MAX_CONTEXT_BYTES:
        raise ValueError("Registry context exceeds its versioned input bound")
    return result


def registry_projection_hash() -> str:
    """Identity of the complete metadata projection actually used by engineering extraction."""
    return identity_hash(attribute_context(item.key for item in list_equipment_definitions()))
