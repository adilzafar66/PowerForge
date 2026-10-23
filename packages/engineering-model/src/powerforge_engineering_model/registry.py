"""Public lookup and value normalization boundary for registry-v1."""

from powerforge_engineering_model.definitions import (
    AttributeDefinition,
    AttributeValue,
    EquipmentDefinition,
)
from powerforge_engineering_model.enums import AttributeValueType, EquipmentType
from powerforge_engineering_model.errors import (
    IncompatibleUnit,
    InvalidAttributeValue,
    InvalidEnumValue,
    UnknownAttribute,
    UnknownEquipmentType,
)
from powerforge_engineering_model.registry_v1 import REGISTRY
from powerforge_engineering_model.units import (
    UnitSemanticContext,
    as_decimal,
    get_unit,
    normalize_value,
)


def list_equipment_definitions() -> tuple[EquipmentDefinition, ...]:
    return REGISTRY.equipment_types


def get_equipment_definition(equipment_type: EquipmentType | str) -> EquipmentDefinition:
    for equipment in REGISTRY.equipment_types:
        if equipment.key == equipment_type:
            return equipment
    raise UnknownEquipmentType(f"Unknown equipment type: {equipment_type!r}")


def get_attribute_definition(
    equipment_type: EquipmentType | str,
    attribute_key: str,
) -> AttributeDefinition:
    for attribute in get_equipment_definition(equipment_type).attributes:
        if attribute.key == attribute_key:
            return attribute
    raise UnknownAttribute(f"Unknown attribute {attribute_key!r} for {equipment_type}")


def _semantic_context(
    equipment_type: EquipmentType | str,
    attribute_key: str,
) -> UnitSemanticContext | None:
    if attribute_key == "rated_active_power":
        if equipment_type == EquipmentType.INDUCTION_MOTOR:
            return UnitSemanticContext.MOTOR_ACTIVE_POWER
        if equipment_type == EquipmentType.VFD:
            return UnitSemanticContext.VFD_ACTIVE_POWER
    if (
        equipment_type == EquipmentType.TWO_WINDING_TRANSFORMER
        and attribute_key == "temperature_rise"
    ):
        return UnitSemanticContext.TEMPERATURE_DIFFERENCE
    return None


def supported_input_units(
    equipment_type: EquipmentType | str,
    attribute_key: str,
) -> tuple[str, ...]:
    attribute = get_attribute_definition(equipment_type, attribute_key)
    if attribute.canonical_unit is None:
        return ()
    for family in REGISTRY.unit_families:
        if attribute.canonical_unit in family.supported_input_units:
            return tuple(
                unit
                for unit in family.supported_input_units
                if unit != "hp"
                or _semantic_context(equipment_type, attribute_key)
                in (
                    UnitSemanticContext.MOTOR_ACTIVE_POWER,
                    UnitSemanticContext.VFD_ACTIVE_POWER,
                )
            )
    return ()  # Startup validation rejects missing unit-family definitions.


def normalize_attribute_value(
    equipment_type: EquipmentType | str,
    attribute_key: str,
    value: object,
    input_unit: str | None = None,
) -> AttributeValue:
    """Validate a value; omitted input unit means the attribute's canonical unit."""
    attribute = get_attribute_definition(equipment_type, attribute_key)
    unit = attribute.canonical_unit if input_unit is None else input_unit
    if attribute.value_type in (AttributeValueType.NUMBER, AttributeValueType.INTEGER):
        normalized = normalize_value(
            value,
            unit,
            attribute.canonical_unit,
            semantic_context=_semantic_context(equipment_type, attribute_key),
        )
        number = as_decimal(normalized)
        if attribute.value_type == AttributeValueType.INTEGER:
            if number != number.to_integral_value():
                raise InvalidAttributeValue(f"{attribute_key} requires an integer")
            return int(number)
        return number
    if unit is not None:
        get_unit(unit)
        raise IncompatibleUnit(f"{attribute_key} is unitless")
    if attribute.value_type == AttributeValueType.BOOLEAN:
        if type(value) is not bool:
            raise InvalidAttributeValue(f"{attribute_key} requires a boolean")
        return value
    if not isinstance(value, str):
        raise InvalidAttributeValue(f"{attribute_key} requires text")
    if attribute.value_type == AttributeValueType.ENUM and value not in attribute.allowed_values:
        raise InvalidEnumValue(f"Invalid value {value!r} for {attribute_key}")
    return value
