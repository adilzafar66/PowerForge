"""Immutable registry metadata and infrastructure-neutral evaluator inputs."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from powerforge_engineering_model.enums import (
    AttributeValueType,
    ConditionType,
    EquipmentType,
    InformationState,
    RequirementRuleType,
    RequirementStatus,
)

type AttributeValue = Decimal | int | str | bool


@dataclass(frozen=True, slots=True)
class AttributeDefinition:
    key: str
    display_name: str
    value_type: AttributeValueType
    canonical_unit: str | None
    required: bool
    critical: bool
    allowed_values: tuple[str, ...]
    notes: str | None
    display_order: int
    requirement_group: str | None = None
    requirement_condition: str | None = None


@dataclass(frozen=True, slots=True)
class RequirementCondition:
    kind: ConditionType
    attribute: str | None = None
    values: tuple[str | bool, ...] = ()
    attributes: tuple[str, ...] = ()
    context_key: str | None = None


@dataclass(frozen=True, slots=True)
class RequirementRule:
    """One approved row. ANY_OF rows with the same rule_id form one rule."""

    equipment_type: EquipmentType
    rule_id: str
    rule_type: RequirementRuleType
    condition: RequirementCondition
    condition_description: str
    alternative: str | None
    attributes: tuple[str, ...]
    engineering_rationale: str | None
    implementation_note: str | None


@dataclass(frozen=True, slots=True)
class RequirementNotice:
    """Reference-only NONE row: not an executable requirement."""

    equipment_type: EquipmentType
    condition_description: str
    engineering_rationale: str | None
    implementation_note: str | None
    rule_id: Literal["NONE"] = "NONE"
    rule_type: Literal["NONE"] = "NONE"
    alternative: None = None
    attributes: tuple[()] = ()


@dataclass(frozen=True, slots=True)
class EquipmentDefinition:
    key: EquipmentType
    display_name: str
    source_sheet: str
    attributes: tuple[AttributeDefinition, ...]
    requirements: tuple[RequirementRule, ...] = ()


@dataclass(frozen=True, slots=True)
class UnitFamilyDefinition:
    family: str
    default_unit: str
    supported_input_units: tuple[str, ...]
    notes: str | None


@dataclass(frozen=True, slots=True)
class RegistryDefinition:
    registry_version: str
    equipment_types: tuple[EquipmentDefinition, ...]
    unit_families: tuple[UnitFamilyDefinition, ...]
    requirement_rules: tuple[RequirementRule | RequirementNotice, ...]


@dataclass(frozen=True, slots=True)
class AttributeState:
    """Values are canonical (already normalized); omitted keys are NOT_EXTRACTED."""

    information_state: InformationState
    value: AttributeValue | None = None


@dataclass(frozen=True, slots=True)
class MissingAlternative:
    alternative: str | None
    attributes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RequirementResult:
    """One result per unconditional attribute or conditional rule group."""

    rule_id: str
    status: RequirementStatus
    missing_alternatives: tuple[MissingAlternative, ...] = ()
