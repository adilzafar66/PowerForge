"""Structural validation of code-owned registry definitions at application startup."""

import re
from collections import defaultdict

from powerforge_engineering_model.definitions import (
    AttributeDefinition,
    RegistryDefinition,
    RequirementCondition,
    RequirementNotice,
    RequirementRule,
)
from powerforge_engineering_model.enums import (
    AttributeValueType,
    ConditionType,
    EquipmentType,
    RequirementRuleType,
)
from powerforge_engineering_model.errors import InvalidRegistryDefinition
from powerforge_engineering_model.registry_v1 import REGISTRY
from powerforge_engineering_model.units import UNITS


def _require(valid: bool, message: str) -> None:
    if not valid:
        raise InvalidRegistryDefinition(message)


def _validate_condition(
    condition: RequirementCondition,
    attributes: dict[str, AttributeDefinition],
) -> None:
    _require(isinstance(condition.kind, ConditionType), "Invalid condition kind")
    kind = condition.kind
    selector = kind in (ConditionType.ATTRIBUTE_EQUALS, ConditionType.ATTRIBUTE_IN)
    _require((condition.attribute is not None) == selector, "Invalid condition selector")
    _require(bool(condition.values) == selector, "Invalid condition values")
    _require(
        bool(condition.attributes) == (kind == ConditionType.ANY_PRESENT),
        "Invalid presence condition",
    )
    _require(
        (condition.context_key is not None) == (kind == ConditionType.EXTERNAL_CONTEXT),
        "Invalid external context condition",
    )
    if selector:
        _require(condition.attribute in attributes, "Condition references unknown attribute")
        attribute = attributes[condition.attribute]
        _require(len(condition.values) == len(set(condition.values)), "Duplicate condition values")
        if kind == ConditionType.ATTRIBUTE_EQUALS:
            _require(len(condition.values) == 1, "Equality requires exactly one value")
        for value in condition.values:
            _require(
                (
                    attribute.value_type == AttributeValueType.ENUM
                    and value in attribute.allowed_values
                )
                or (attribute.value_type == AttributeValueType.BOOLEAN and type(value) is bool),
                "Condition value incompatible with its selector",
            )
    if kind == ConditionType.ANY_PRESENT:
        _require(
            len(set(condition.attributes)) == len(condition.attributes),
            "Duplicate presence attributes",
        )
        _require(set(condition.attributes) <= attributes.keys(), "Unknown presence attribute")
    if kind == ConditionType.EXTERNAL_CONTEXT:
        _require(bool(condition.context_key), "Empty external context key")


def validate_registry(registry: RegistryDefinition = REGISTRY) -> None:
    """Fail loudly for malformed definitions; snapshot tests additionally lock exact metadata."""
    _require(registry.registry_version == "registry-v1", "Invalid registry version")
    keys = tuple(e.key for e in registry.equipment_types)
    _require(len(keys) == 20 and len(set(keys)) == 20, "Expected 20 unique equipment types")
    _require(keys == tuple(EquipmentType), "Canonical equipment keys/order differ from registry-v1")
    families = registry.unit_families
    _require(len({f.family for f in families}) == len(families), "Duplicate unit family")
    known_units: set[str] = set()
    for family in families:
        units = family.supported_input_units
        _require(bool(units) and len(set(units)) == len(units), "Invalid family units")
        _require(family.default_unit in units, "Family default is not supported")
        _require(set(units) <= UNITS.keys(), "Unsupported family unit")
        _require(len({UNITS[u].dimension for u in units}) == 1, "Incompatible family units")
        known_units.update(units)
    equipment_by_key = {e.key: e for e in registry.equipment_types}
    for equipment in registry.equipment_types:
        attrs = equipment.attributes
        _require(bool(attrs), "Equipment has no attributes")
        _require(len({a.key for a in attrs}) == len(attrs), "Duplicate attribute key")
        _require(
            tuple(a.display_order for a in attrs) == tuple(range(len(attrs))),
            "Non-deterministic attribute display order",
        )
        for attr in attrs:
            _require(
                re.fullmatch(r"[a-z][a-z0-9_]*", attr.key) is not None, "Invalid attribute key"
            )
            _require(
                isinstance(attr.value_type, AttributeValueType), "Invalid attribute value type"
            )
            _require(type(attr.required) is bool and type(attr.critical) is bool, "Invalid flags")
            _require(
                bool(attr.allowed_values) == (attr.value_type == AttributeValueType.ENUM),
                "ENUM must have choices; other types must not",
            )
            _require(
                len(set(attr.allowed_values)) == len(attr.allowed_values), "Duplicate enum value"
            )
            _require(
                all(isinstance(v, str) and bool(v) for v in attr.allowed_values),
                "Invalid enum value",
            )
            _require(
                attr.canonical_unit is None or attr.canonical_unit in known_units,
                "Unknown canonical unit",
            )
            _require(
                attr.canonical_unit is None
                or attr.value_type
                in (
                    AttributeValueType.NUMBER,
                    AttributeValueType.INTEGER,
                ),
                "Non-numeric attribute has a unit",
            )
        expected = tuple(
            row
            for row in registry.requirement_rules
            if (isinstance(row, RequirementRule) and row.equipment_type == equipment.key)
        )
        _require(equipment.requirements == expected, "Equipment requirements differ from registry")
    groups: dict[tuple[EquipmentType, str], list[RequirementRule]] = defaultdict(list)
    notices: set[EquipmentType] = set()
    for row in registry.requirement_rules:
        _require(row.equipment_type in equipment_by_key, "Unknown rule equipment")
        if isinstance(row, RequirementNotice):
            _require(row.equipment_type not in notices, "Duplicate NONE notice")
            _require(
                not equipment_by_key[row.equipment_type].requirements, "NONE conflicts with rules"
            )
            _require(
                row.rule_id == row.rule_type == "NONE"
                and not row.attributes
                and row.alternative is None,
                "Malformed NONE notice",
            )
            notices.add(row.equipment_type)
            continue
        _require(isinstance(row.rule_type, RequirementRuleType), "Invalid rule type")
        _require(bool(row.rule_id) and row.rule_id != "NONE", "Invalid rule ID")
        attrs = {a.key: a for a in equipment_by_key[row.equipment_type].attributes}
        _require(
            bool(row.attributes) and len(set(row.attributes)) == len(row.attributes),
            "Empty or duplicate rule attributes",
        )
        _require(set(row.attributes) <= attrs.keys(), "Rule references unknown attribute")
        _validate_condition(row.condition, attrs)
        if row.rule_type == RequirementRuleType.ALL_OR_NONE:
            _require(len(row.attributes) >= 2, "ALL_OR_NONE needs a group")
            _require(
                row.condition.kind == ConditionType.ANY_PRESENT
                and row.condition.attributes == row.attributes,
                "Invalid ALL_OR_NONE trigger",
            )
        groups[row.equipment_type, row.rule_id].append(row)
    for rows in groups.values():
        first = rows[0]
        _require(
            all(
                row.rule_type == first.rule_type
                and row.condition == first.condition
                and row.condition_description == first.condition_description
                for row in rows
            ),
            "Inconsistent alternative definitions",
        )
        if first.rule_type == RequirementRuleType.ANY_OF:
            _require(len(rows) >= 2, "ANY_OF requires alternatives")
            _require(all(bool(row.alternative) for row in rows), "Missing alternative label")
            _require(len({row.alternative for row in rows}) == len(rows), "Duplicate alternative")
            _require(
                len({frozenset(row.attributes) for row in rows}) == len(rows),
                "Duplicate alternative group",
            )
        else:
            _require(len(rows) == 1 and first.alternative is None, "Unexpected rule alternatives")
