"""Manual revision-scoped equipment authoring with atomic topology lifecycle cascades."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from powerforge_api.db_errors import integrity_guard
from powerforge_api.exceptions import (
    EquipmentAttributeNotFound,
    EquipmentNotFound,
    EquipmentRemoved,
    EquipmentTypeChangeConflict,
    InconsistentEquipment,
    InvalidEquipmentAttributeState,
    ProjectError,
    ProjectNotFound,
    RevisionNotFound,
)
from powerforge_api.services.revision_writes import lock_writable_revision
from powerforge_api.services.terminal_profiles import reconcile_terminals
from powerforge_api.services.topology_support import (
    set_equipment_topology_lifecycle,
    topology_constraint_errors,
    validate_topology_consistency,
)
from powerforge_engineering_model import (
    AttributeDefinition,
    AttributeValueType,
    EquipmentType,
    InformationState,
    LifecycleStatus,
    ValueOrigin,
    VerificationState,
    get_attribute_definition,
    get_equipment_definition,
    normalize_attribute_value,
)
from powerforge_engineering_model.errors import EngineeringModelError, InvalidAttributeValue
from powerforge_persistence import Project, ProjectRevision
from powerforge_persistence.engineering import Equipment, EquipmentAttribute, EquipmentLineage

VALUE_SLOTS = ("numeric_value", "integer_value", "text_value", "boolean_value")
SLOT_BY_TYPE = {
    AttributeValueType.NUMBER: "numeric_value",
    AttributeValueType.INTEGER: "integer_value",
    AttributeValueType.TEXT: "text_value",
    AttributeValueType.ENUM: "text_value",
    AttributeValueType.BOOLEAN: "boolean_value",
}


class _Unset(Enum):
    VALUE = "unset"


UNSET = _Unset.VALUE


def _constraint_errors() -> dict[str, ProjectError]:
    """Only known invariants get a meaningful service error; unknown ones stay generic."""
    return {
        **topology_constraint_errors(),
        "fk_equipment_revision": RevisionNotFound("Revision not found in this project"),
        "fk_equipment_lineage": InconsistentEquipment("Equipment lineage ownership is invalid"),
        "uq_equipment_revision_lineage": InconsistentEquipment(
            "Lineage already exists in revision"
        ),
        "fk_equipment_attributes_equipment": EquipmentNotFound(
            "Equipment not found in this revision"
        ),
        "uq_equipment_attributes_key": InconsistentEquipment("Duplicate canonical attribute"),
        "ck_equipment_attributes_typed_value": InvalidEquipmentAttributeState(
            "Invalid typed value slots"
        ),
        "ck_equipment_attributes_confidence": InvalidEquipmentAttributeState("Invalid confidence"),
        "ck_equipment_attributes_finite_numeric": InvalidEquipmentAttributeState(
            "Non-finite value"
        ),
        "ck_equipment_lifecycle_removed_at": InconsistentEquipment("Invalid removal state"),
        "ck_equipment_inherited_not_self": InconsistentEquipment("Equipment cannot inherit itself"),
        "ck_equipment_attributes_inherited_not_self": InconsistentEquipment(
            "Attribute cannot inherit itself"
        ),
        "fk_equipment_inherited_from": InconsistentEquipment(
            "Invalid equipment inheritance reference"
        ),
        "fk_equipment_attributes_inherited_from": InconsistentEquipment(
            "Invalid attribute inheritance reference"
        ),
    }


def validate_equipment_consistency(equipment: Equipment) -> None:
    """Detect missing/extra or corrupted canonical rows without repairing or hiding them."""
    try:
        definition = get_equipment_definition(equipment.equipment_type)
        attributes = {row.attribute_key: row for row in equipment.attributes}
        if len(attributes) != len(equipment.attributes) or set(attributes) != {
            attr.key for attr in definition.attributes
        }:
            raise InconsistentEquipment("Equipment attributes do not match its registry definition")
        for attr in definition.attributes:
            row = attributes[attr.key]
            if (row.project_id, row.revision_id, row.equipment_id) != (
                equipment.project_id,
                equipment.revision_id,
                equipment.id,
            ):
                raise InconsistentEquipment("Attribute ownership does not match equipment")
            if row.value_type != attr.value_type or row.unit != attr.canonical_unit:
                raise InconsistentEquipment(f"Registry metadata mismatch for {attr.key}")
            populated = [slot for slot in VALUE_SLOTS if getattr(row, slot) is not None]
            if row.information_state == InformationState.PRESENT:
                slot = SLOT_BY_TYPE[attr.value_type]
                if populated != [slot]:
                    raise InconsistentEquipment(f"Invalid typed value slots for {attr.key}")
                normalize_attribute_value(equipment.equipment_type, attr.key, getattr(row, slot))
            elif populated:
                raise InconsistentEquipment(f"Non-PRESENT attribute {attr.key} contains a value")
    except EngineeringModelError as exc:
        raise InconsistentEquipment("Persisted values do not match registry-v1") from exc


def _materialize(
    equipment: Equipment, definition: AttributeDefinition, actor_id: UUID | None
) -> EquipmentAttribute:
    return EquipmentAttribute(
        project_id=equipment.project_id,
        revision_id=equipment.revision_id,
        equipment_id=equipment.id,
        attribute_key=definition.key,
        value_type=definition.value_type,
        unit=definition.canonical_unit,
        information_state=InformationState.NOT_POPULATED,
        verification_state=VerificationState.UNVERIFIED,
        origin=None,
        confidence=None,
        inherited_from_attribute_id=None,
        created_by=actor_id,
        updated_by=actor_id,
    )


def _untouched(row: EquipmentAttribute) -> bool:
    """Snapshot ancestry does not make an empty placeholder meaningful data."""
    return (
        row.information_state == InformationState.NOT_POPULATED
        and row.verification_state == VerificationState.UNVERIFIED
        and row.origin is None
        and row.confidence is None
        and all(getattr(row, slot) is None for slot in VALUE_SLOTS)
    )


class EngineeringModelService:
    """Owns commits and rolls back the session on every failed mutation, like document services.

    Use a dedicated session per unit of work. Returned ORM rows belong to that session.
    commit=False participates in the editor's outer transaction and flushes only.
    """

    def __init__(self, session: Session, *, commit: bool = True) -> None:
        self.session = session
        self._commit = commit

    @contextmanager
    def _mutation(
        self, project_id: UUID, revision_id: UUID, operation: str
    ) -> Iterator[ProjectRevision]:
        try:
            with integrity_guard(self.session, _constraint_errors(), operation=operation):
                revision = lock_writable_revision(self.session, project_id, revision_id)
                yield revision
                self.session.flush()
                if self._commit:
                    self.session.commit()
        except BaseException:
            self.session.rollback()
            raise

    def _require_context(self, project_id: UUID, revision_id: UUID) -> None:
        if self.session.get(Project, project_id) is None:
            raise ProjectNotFound(f"Project {project_id} not found")
        if (
            self.session.scalar(
                select(ProjectRevision.id).where(
                    ProjectRevision.id == revision_id,
                    ProjectRevision.project_id == project_id,
                )
            )
            is None
        ):
            raise RevisionNotFound(f"Revision {revision_id} not found")

    def _equipment(self, project_id: UUID, revision_id: UUID, equipment_id: UUID) -> Equipment:
        equipment = self.session.scalar(
            select(Equipment)
            .where(
                Equipment.project_id == project_id,
                Equipment.revision_id == revision_id,
                Equipment.id == equipment_id,
            )
            .options(selectinload(Equipment.attributes))
            .execution_options(populate_existing=True)
        )
        if equipment is None:
            raise EquipmentNotFound(f"Equipment {equipment_id} not found in this revision")
        validate_equipment_consistency(equipment)
        return equipment

    @staticmethod
    def _assert_active(equipment: Equipment) -> None:
        if equipment.lifecycle_status == LifecycleStatus.REMOVED:
            raise EquipmentRemoved("Restore equipment before editing it")

    @staticmethod
    def _metadata_value(name: str, value: object) -> None:
        if value is not None and not isinstance(value, str):
            raise InvalidAttributeValue(f"{name} must be text or null")

    def create_equipment(
        self,
        project_id: UUID,
        revision_id: UUID,
        equipment_type: EquipmentType | str,
        *,
        tag: str | None = None,
        name: str | None = None,
        description: str | None = None,
        actor_id: UUID | None = None,
    ) -> Equipment:
        with self._mutation(project_id, revision_id, "create_equipment") as revision:
            definition = get_equipment_definition(equipment_type)
            for key, value in (("tag", tag), ("name", name), ("description", description)):
                self._metadata_value(key, value)
            lineage = EquipmentLineage(project_id=project_id, created_by=actor_id)
            self.session.add(lineage)
            self.session.flush()
            equipment = Equipment(
                project_id=project_id,
                revision_id=revision_id,
                lineage_id=lineage.id,
                equipment_type=definition.key.value,
                tag=tag,
                name=name,
                description=description,
                lifecycle_status=LifecycleStatus.ACTIVE,
                origin=ValueOrigin.MANUAL,
                verification_state=VerificationState.ENGINEER_REVIEWED,
                inherited_from_equipment_id=None,
                created_by=actor_id,
                updated_by=actor_id,
            )
            self.session.add(equipment)
            self.session.flush()
            equipment.attributes = [
                _materialize(equipment, attr, actor_id) for attr in definition.attributes
            ]
            reconcile_terminals(self.session, equipment, actor_id)
            validate_equipment_consistency(equipment)
            revision.updated_at = datetime.now(UTC)
        return self.get_equipment(project_id, revision_id, equipment.id)

    def get_equipment(self, project_id: UUID, revision_id: UUID, equipment_id: UUID) -> Equipment:
        self._require_context(project_id, revision_id)
        return self._equipment(project_id, revision_id, equipment_id)

    def list_equipment(
        self,
        project_id: UUID,
        revision_id: UUID,
        *,
        lifecycle_status: LifecycleStatus | None = LifecycleStatus.ACTIVE,
        equipment_type: EquipmentType | str | None = None,
        search: str | None = None,
    ) -> list[Equipment]:
        self._require_context(project_id, revision_id)
        stmt = select(Equipment).where(
            Equipment.project_id == project_id, Equipment.revision_id == revision_id
        )
        if lifecycle_status is not None:
            if not isinstance(lifecycle_status, LifecycleStatus):
                raise InvalidAttributeValue("Invalid lifecycle filter")
            stmt = stmt.where(Equipment.lifecycle_status == lifecycle_status)
        if equipment_type is not None:
            stmt = stmt.where(
                Equipment.equipment_type == get_equipment_definition(equipment_type).key.value
            )
        if search is not None and search.strip():
            # Literal substring search: user '%' and '_' are not SQL wildcards.
            term = search.strip()
            stmt = stmt.where(
                or_(
                    Equipment.tag.icontains(term, autoescape=True),
                    Equipment.name.icontains(term, autoescape=True),
                    Equipment.description.icontains(term, autoescape=True),
                )
            )
        return list(self.session.scalars(stmt.order_by(Equipment.created_at, Equipment.id)).all())

    def get_equipment_attributes(
        self, project_id: UUID, revision_id: UUID, equipment_id: UUID
    ) -> list[EquipmentAttribute]:
        equipment = self.get_equipment(project_id, revision_id, equipment_id)
        rows = {row.attribute_key: row for row in equipment.attributes}
        return [
            rows[attr.key] for attr in get_equipment_definition(equipment.equipment_type).attributes
        ]

    def update_equipment(
        self,
        project_id: UUID,
        revision_id: UUID,
        equipment_id: UUID,
        *,
        tag: str | None | _Unset = UNSET,
        name: str | None | _Unset = UNSET,
        description: str | None | _Unset = UNSET,
        equipment_type: EquipmentType | str | _Unset = UNSET,
        actor_id: UUID | None = None,
    ) -> Equipment:
        with self._mutation(project_id, revision_id, "update_equipment") as revision:
            equipment = self._equipment(project_id, revision_id, equipment_id)
            self._assert_active(equipment)
            if equipment_type is not UNSET:
                self._change_type(equipment, equipment_type, actor_id)
            for key, value in (("tag", tag), ("name", name), ("description", description)):
                if value is not UNSET:
                    self._metadata_value(key, value)
                    setattr(equipment, key, value)
            equipment.updated_at = revision.updated_at = datetime.now(UTC)
            equipment.updated_by = actor_id
            equipment.origin = ValueOrigin.MANUAL
            equipment.verification_state = VerificationState.ENGINEER_REVIEWED
            validate_equipment_consistency(equipment)
        return self.get_equipment(project_id, revision_id, equipment_id)

    def _change_type(
        self, equipment: Equipment, destination: EquipmentType | str, actor_id: UUID | None
    ) -> None:
        old = get_equipment_definition(equipment.equipment_type)
        new = get_equipment_definition(destination)
        if old.key == new.key:
            return
        reconcile_terminals(self.session, equipment, actor_id, destination=new.key)
        definitions = {attr.key: attr for attr in new.attributes}
        keep, discard, conflicts = [], [], []
        for row in equipment.attributes:
            attr = definitions.get(row.attribute_key)
            compatible = (
                attr is not None
                and attr.value_type == row.value_type
                and attr.canonical_unit == row.unit
            )
            if (
                compatible
                and row.value_type == AttributeValueType.ENUM
                and row.information_state == InformationState.PRESENT
            ):
                compatible = row.text_value in attr.allowed_values
            if compatible:
                keep.append(row)
            elif _untouched(row):
                discard.append(row)
            else:
                conflicts.append(row.attribute_key)
        if conflicts:
            raise EquipmentTypeChangeConflict(
                "Type change would discard meaningful attributes: " + ", ".join(sorted(conflicts))
            )
        # Attribute conflicts are checked before replacement. Profile changes share this
        # transaction and roll back on conflict. Flush deletes before reusing a unique key.
        for row in discard:
            self.session.delete(row)
        self.session.flush()
        kept_keys = {row.attribute_key for row in keep}
        equipment.equipment_type = new.key.value
        equipment.attributes = keep + [
            _materialize(equipment, attr, actor_id)
            for attr in new.attributes
            if attr.key not in kept_keys
        ]

    def set_attribute(
        self,
        project_id: UUID,
        revision_id: UUID,
        equipment_id: UUID,
        attribute_key: str,
        information_state: InformationState,
        *,
        value: object = None,
        input_unit: str | None = None,
        actor_id: UUID | None = None,
    ) -> EquipmentAttribute:
        with self._mutation(project_id, revision_id, "set_equipment_attribute") as revision:
            equipment = self._equipment(project_id, revision_id, equipment_id)
            self._assert_active(equipment)
            definition = get_attribute_definition(equipment.equipment_type, attribute_key)
            if not isinstance(information_state, InformationState) or information_state not in (
                InformationState.PRESENT,
                InformationState.NOT_POPULATED,
                InformationState.MISSING,
                InformationState.NOT_APPLICABLE,
            ):
                raise InvalidEquipmentAttributeState("State is not available for manual editing")
            normalized = None
            if information_state == InformationState.PRESENT:
                normalized = normalize_attribute_value(
                    equipment.equipment_type, attribute_key, value, input_unit
                )
                if (
                    definition.value_type == AttributeValueType.INTEGER
                    and not -(2**63) <= normalized < 2**63
                ):
                    raise InvalidAttributeValue("Integer exceeds the supported storage range")
            elif value is not None or input_unit is not None:
                raise InvalidEquipmentAttributeState(
                    "State-only edits cannot supply a value or input unit"
                )
            row = next(
                (row for row in equipment.attributes if row.attribute_key == attribute_key), None
            )
            if row is None:
                raise EquipmentAttributeNotFound("Materialized attribute not found")
            for slot in VALUE_SLOTS:
                setattr(row, slot, None)
            if information_state == InformationState.PRESENT:
                setattr(row, SLOT_BY_TYPE[definition.value_type], normalized)
            row.value_type = definition.value_type
            row.unit = definition.canonical_unit
            row.information_state = information_state
            empty = information_state == InformationState.NOT_POPULATED
            row.origin = None if empty else ValueOrigin.MANUAL
            row.verification_state = (
                VerificationState.UNVERIFIED if empty else VerificationState.ENGINEER_REVIEWED
            )
            row.confidence = None
            row.updated_at = equipment.updated_at = revision.updated_at = datetime.now(UTC)
            row.updated_by = equipment.updated_by = actor_id
            validate_equipment_consistency(equipment)
        return next(
            row
            for row in self.get_equipment_attributes(project_id, revision_id, equipment_id)
            if row.attribute_key == attribute_key
        )

    def remove_equipment(
        self,
        project_id: UUID,
        revision_id: UUID,
        equipment_id: UUID,
        *,
        actor_id: UUID | None = None,
    ) -> Equipment:
        return self._set_lifecycle(
            project_id, revision_id, equipment_id, LifecycleStatus.REMOVED, actor_id
        )

    def restore_equipment(
        self,
        project_id: UUID,
        revision_id: UUID,
        equipment_id: UUID,
        *,
        actor_id: UUID | None = None,
    ) -> Equipment:
        return self._set_lifecycle(
            project_id, revision_id, equipment_id, LifecycleStatus.ACTIVE, actor_id
        )

    def _set_lifecycle(
        self,
        project_id: UUID,
        revision_id: UUID,
        equipment_id: UUID,
        status: LifecycleStatus,
        actor_id: UUID | None,
    ) -> Equipment:
        with self._mutation(project_id, revision_id, "set_equipment_lifecycle") as revision:
            equipment = self._equipment(project_id, revision_id, equipment_id)
            validate_topology_consistency(self.session, project_id, revision_id)
            if equipment.lifecycle_status != status:
                now = datetime.now(UTC)
                equipment.lifecycle_status = status
                equipment.removed_at = now if status == LifecycleStatus.REMOVED else None
                equipment.removed_by = actor_id if status == LifecycleStatus.REMOVED else None
                equipment.updated_at = revision.updated_at = now
                equipment.updated_by = actor_id
                set_equipment_topology_lifecycle(self.session, equipment, status, actor_id)
                self.session.flush()
                validate_topology_consistency(self.session, project_id, revision_id)
        return self.get_equipment(project_id, revision_id, equipment_id)
