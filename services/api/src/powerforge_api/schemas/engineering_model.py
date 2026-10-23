"""Read-only registry API contracts; forms consume the canonical domain metadata."""

from pydantic import BaseModel, ConfigDict

from powerforge_engineering_model.definitions import (
    RequirementNotice,
    RequirementRule,
    UnitFamilyDefinition,
)
from powerforge_engineering_model.enums import AttributeValueType, EquipmentType


class AttributeDefinitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    display_name: str
    value_type: AttributeValueType
    canonical_unit: str | None
    required: bool
    critical: bool
    allowed_values: tuple[str, ...]
    notes: str | None
    display_order: int
    requirement_group: str | None
    requirement_condition: str | None
    supported_input_units: tuple[str, ...] = ()


class EquipmentDefinitionResponse(BaseModel):
    key: EquipmentType
    display_name: str
    attributes: tuple[AttributeDefinitionResponse, ...]
    requirements: tuple[RequirementRule, ...]


class RegistryResponse(BaseModel):
    registry_version: str
    equipment_types: tuple[EquipmentDefinitionResponse, ...]
    requirement_rules: tuple[RequirementRule | RequirementNotice, ...]
    unit_families: tuple[UnitFamilyDefinition, ...]
