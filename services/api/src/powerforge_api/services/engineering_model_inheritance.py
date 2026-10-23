"""Transactional Phase 5C cloning of revision-scoped equipment snapshots."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from powerforge_api.exceptions import ModelInheritanceConflict
from powerforge_engineering_model import (
    AttributeDefinition,
    AttributeValueType,
    InformationState,
    LifecycleStatus,
    VerificationState,
    get_equipment_definition,
    normalize_attribute_value,
)
from powerforge_engineering_model.errors import EngineeringModelError
from powerforge_persistence import ProjectRevision
from powerforge_persistence.engineering import Equipment, EquipmentAttribute

VALUE_SLOTS = ("numeric_value", "integer_value", "text_value", "boolean_value")
SLOT_BY_TYPE = {
    AttributeValueType.NUMBER: "numeric_value",
    AttributeValueType.INTEGER: "integer_value",
    AttributeValueType.TEXT: "text_value",
    AttributeValueType.ENUM: "text_value",
    AttributeValueType.BOOLEAN: "boolean_value",
}


def _untouched_placeholder(row: EquipmentAttribute) -> bool:
    return (
        row.information_state == InformationState.NOT_EXTRACTED
        and row.verification_state == VerificationState.UNVERIFIED
        and row.origin is None
        and row.confidence is None
        and all(getattr(row, slot) is None for slot in VALUE_SLOTS)
    )


def _fresh_attribute(
    equipment: Equipment,
    definition: AttributeDefinition,
    actor_id: UUID | None,
) -> EquipmentAttribute:
    return EquipmentAttribute(
        project_id=equipment.project_id,
        revision_id=equipment.revision_id,
        equipment_id=equipment.id,
        attribute_key=definition.key,
        value_type=definition.value_type,
        unit=definition.canonical_unit,
        information_state=InformationState.NOT_EXTRACTED,
        verification_state=VerificationState.UNVERIFIED,
        origin=None,
        confidence=None,
        inherited_from_attribute_id=None,
        created_by=actor_id,
        updated_by=actor_id,
    )


def _compatible_source_attribute(
    equipment: Equipment,
    row: EquipmentAttribute,
    definition: AttributeDefinition | None,
) -> bool:
    if (
        definition is None
        or row.value_type != definition.value_type
        or row.unit != definition.canonical_unit
    ):
        return False
    populated = [slot for slot in VALUE_SLOTS if getattr(row, slot) is not None]
    if row.information_state == InformationState.PRESENT:
        expected_slot = SLOT_BY_TYPE[definition.value_type]
        if populated != [expected_slot]:
            return False
        if definition.value_type == AttributeValueType.ENUM:
            return row.text_value in definition.allowed_values
        try:
            normalize_attribute_value(
                equipment.equipment_type,
                row.attribute_key,
                getattr(row, expected_slot),
            )
        except EngineeringModelError:
            return False
    elif populated:
        return False
    return True


def _cloned_attribute(
    source: EquipmentAttribute,
    equipment: Equipment,
    actor_id: UUID | None,
) -> EquipmentAttribute:
    return EquipmentAttribute(
        project_id=equipment.project_id,
        revision_id=equipment.revision_id,
        equipment_id=equipment.id,
        attribute_key=source.attribute_key,
        value_type=source.value_type,
        numeric_value=source.numeric_value,
        integer_value=source.integer_value,
        text_value=source.text_value,
        boolean_value=source.boolean_value,
        unit=source.unit,
        information_state=source.information_state,
        verification_state=source.verification_state,
        origin=source.origin,
        confidence=source.confidence,
        inherited_from_attribute_id=source.id,
        created_by=actor_id,
        updated_by=actor_id,
    )


def copy_active_engineering_model(
    session: Session,
    source: ProjectRevision,
    target: ProjectRevision,
    *,
    actor_id: UUID | None = None,
) -> int:
    """Clone the active model into ``target`` without committing.

    The caller owns project -> source revision locks and the surrounding revision-
    creation transaction. Registry evolution is conservative: meaningful data is
    never coerced or discarded.
    """
    if (
        source.project_id != target.project_id
        or target.based_on_revision_id != source.id
        or source.id == target.id
    ):
        raise ModelInheritanceConflict(
            "Model inheritance source must be the target revision's selected base"
        )

    sources = list(
        session.scalars(
            select(Equipment)
            .where(
                Equipment.project_id == source.project_id,
                Equipment.revision_id == source.id,
                Equipment.lifecycle_status == LifecycleStatus.ACTIVE,
            )
            .options(selectinload(Equipment.attributes))
            .order_by(Equipment.created_at, Equipment.id)
        ).all()
    )
    for source_equipment in sources:
        try:
            current = get_equipment_definition(source_equipment.equipment_type)
        except EngineeringModelError as exc:
            raise ModelInheritanceConflict(
                f"Cannot inherit equipment {source_equipment.id}: unknown equipment type"
            ) from exc
        definitions = {attribute.key: attribute for attribute in current.attributes}
        compatible: list[EquipmentAttribute] = []
        conflicts: list[str] = []
        for row in source_equipment.attributes:
            definition = definitions.get(row.attribute_key)
            if _compatible_source_attribute(source_equipment, row, definition):
                compatible.append(row)
            elif not _untouched_placeholder(row):
                conflicts.append(row.attribute_key)
        if conflicts:
            keys = ", ".join(sorted(conflicts))
            raise ModelInheritanceConflict(
                f"Cannot inherit equipment {source_equipment.id}; incompatible meaningful "
                f"attributes: {keys}"
            )

        destination = Equipment(
            project_id=target.project_id,
            revision_id=target.id,
            lineage_id=source_equipment.lineage_id,
            equipment_type=source_equipment.equipment_type,
            tag=source_equipment.tag,
            name=source_equipment.name,
            description=source_equipment.description,
            lifecycle_status=LifecycleStatus.ACTIVE,
            origin=source_equipment.origin,
            verification_state=source_equipment.verification_state,
            inherited_from_equipment_id=source_equipment.id,
            created_by=actor_id,
            updated_by=actor_id,
            removed_at=None,
            removed_by=None,
        )
        session.add(destination)
        session.flush()
        inherited_keys = {row.attribute_key for row in compatible}
        destination.attributes = [
            *[_cloned_attribute(row, destination, actor_id) for row in compatible],
            *[
                _fresh_attribute(destination, definition, actor_id)
                for definition in current.attributes
                if definition.key not in inherited_keys
            ],
        ]
    session.flush()
    return len(sources)
