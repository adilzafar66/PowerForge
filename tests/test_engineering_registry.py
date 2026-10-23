"""Independent approved-snapshot and malformed-registry regression coverage."""

import ast
import json
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from powerforge_engineering_model import (
    REGISTRY,
    EquipmentType,
    get_attribute_definition,
    get_equipment_definition,
    list_equipment_definitions,
    validate_registry,
)
from powerforge_engineering_model.definitions import RequirementRule
from powerforge_engineering_model.enums import AttributeValueType
from powerforge_engineering_model.errors import (
    InvalidRegistryDefinition,
    UnknownAttribute,
    UnknownEquipmentType,
)

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "docs/specs/registry/PowerForge_registry-v1_reference.json"


def test_registry_matches_independent_approved_snapshot() -> None:
    reference = json.loads(REFERENCE.read_text())
    equipment = []
    for definition in REGISTRY.equipment_types:
        item = asdict(definition)
        item.pop("requirements")
        equipment.append(item)
    rows = []
    for row in REGISTRY.requirement_rules:
        item = asdict(row)
        item.pop("condition", None)  # executable condition is additional typed metadata
        rows.append(item)
    snapshot = {
        "registry_version": REGISTRY.registry_version,
        "equipment_types": equipment,
        "unit_families": [asdict(f) for f in REGISTRY.unit_families],
        "requirement_rules": rows,
    }
    # Only normalize tuples/enums to their JSON representation; preserve all metadata/order.
    assert json.loads(json.dumps(snapshot)) == {key: reference[key] for key in snapshot}
    validate_registry()
    assert len(REGISTRY.equipment_types) == 20
    assert sum(len(e.attributes) for e in REGISTRY.equipment_types) == 296
    assert len(REGISTRY.requirement_rules) == 44
    assert sum(isinstance(r, RequirementRule) for r in REGISTRY.requirement_rules) == 41
    assert len(REGISTRY.unit_families) == 17
    assert list_equipment_definitions() is REGISTRY.equipment_types


def test_registry_semantics_and_canonical_units() -> None:
    assert get_attribute_definition("BUS", "bus_type").allowed_values == (
        "SWITCHGEAR",
        "SWITCHBOARD",
        "PANELBOARD",
        "MCC",
        "JUNCTION_BOX",
        "OTHER",
    )
    attr = get_attribute_definition("UTILITY_SOURCE", "three_phase_fault_current")
    assert attr.critical and not attr.required
    assert get_attribute_definition("LUMPED_LOAD", "rated_active_power").required
    for equipment, key, unit in [
        ("BUS", "electrode_gap", "mm"),
        ("CT", "rated_burden", "VA"),
        ("VFD", "output_short_circuit_trip_time", "ms"),
        ("OVERCURRENT_RELAY", "trip_output_operating_time", "s"),
    ]:
        assert get_attribute_definition(equipment, key).canonical_unit == unit
    assert get_attribute_definition("LV_BREAKER", "trip_rating")
    assert get_attribute_definition("LV_BREAKER", "long_time_pickup")


@pytest.mark.parametrize(
    "key", ["GENERATOR", "TRANSFORMER", "BREAKER", "SWITCHGEAR", "DISCONNECT", "bad"]
)
def test_unknown_equipment_has_domain_error(key: str) -> None:
    with pytest.raises(UnknownEquipmentType):
        get_equipment_definition(key)


def test_unknown_attribute_has_domain_error() -> None:
    with pytest.raises(UnknownAttribute):
        get_attribute_definition(EquipmentType.BUS, "made_up_attribute")


@pytest.mark.parametrize(
    "change",
    [
        {"key": "voltage-kV"},
        {"value_type": "INVALID"},
        {"canonical_unit": "furlong"},
        {"value_type": AttributeValueType.ENUM, "allowed_values": ()},
        {"allowed_values": ("INVALID",)},
        {"display_order": 99},
        {"required": "yes"},
    ],
)
def test_malformed_attribute_fails_validation(change: dict) -> None:
    equipment = REGISTRY.equipment_types[0]
    malformed = replace(equipment.attributes[0], **change)
    equipment = replace(equipment, attributes=(malformed, *equipment.attributes[1:]))
    with pytest.raises(InvalidRegistryDefinition):
        validate_registry(
            replace(REGISTRY, equipment_types=(equipment, *REGISTRY.equipment_types[1:]))
        )


def test_duplicate_attribute_and_equipment_and_version_rejected() -> None:
    equipment = REGISTRY.equipment_types[0]
    duplicate = replace(equipment, attributes=(*equipment.attributes, equipment.attributes[0]))
    for registry in [
        replace(REGISTRY, registry_version="registry-v2"),
        replace(REGISTRY, equipment_types=(equipment, *REGISTRY.equipment_types[:-1])),
        replace(REGISTRY, equipment_types=(duplicate, *REGISTRY.equipment_types[1:])),
        replace(REGISTRY, equipment_types=REGISTRY.equipment_types[:-1]),
    ]:
        with pytest.raises(InvalidRegistryDefinition):
            validate_registry(registry)


@pytest.mark.parametrize(
    "change",
    [
        {"attributes": ("does_not_exist",)},
        {"attributes": ()},
        {"attributes": ("slg_x_r", "slg_x_r")},
        {"rule_type": "INVALID"},
        {"alternative": None},
        {"equipment_type": "UNKNOWN"},
        {"condition": replace(REGISTRY.requirement_rules[0].condition, attribute="missing")},
    ],
)
def test_malformed_rule_fails_validation(change: dict) -> None:
    bad_row = replace(REGISTRY.requirement_rules[0], **change)
    rows = (bad_row, *REGISTRY.requirement_rules[1:])
    equipment = tuple(
        replace(
            e,
            requirements=tuple(
                r for r in rows if isinstance(r, RequirementRule) and r.equipment_type == e.key
            ),
        )
        for e in REGISTRY.equipment_types
    )
    with pytest.raises(InvalidRegistryDefinition):
        validate_registry(replace(REGISTRY, equipment_types=equipment, requirement_rules=rows))


def test_unit_family_rejects_unknown_default_and_incompatible_units() -> None:
    family = REGISTRY.unit_families[0]
    for malformed in [
        replace(family, default_unit="A"),
        replace(family, supported_input_units=("kV", "A")),
        replace(family, supported_input_units=("kV", "made_up")),
    ]:
        with pytest.raises(InvalidRegistryDefinition):
            validate_registry(
                replace(REGISTRY, unit_families=(malformed, *REGISTRY.unit_families[1:]))
            )


def test_domain_imports_only_standard_library_and_own_package() -> None:
    package = ROOT / "packages/engineering-model/src/powerforge_engineering_model"
    for file in package.glob("*.py"):
        for node in ast.walk(ast.parse(file.read_text())):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for module in modules:
                root = module.split(".")[0]
                assert root in sys.stdlib_module_names or root == "powerforge_engineering_model"
    # A fresh interpreter without site packages can validate the registry, without docs/XLSX access.
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-c",
            f"import sys; sys.path.insert(0, {str(package.parent)!r}); "
            "from powerforge_engineering_model import validate_registry; validate_registry()",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
