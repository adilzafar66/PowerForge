from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from engineering_support import engineering_context as engineering_context
from engineering_support import seed_revision
from powerforge_api.exceptions import (
    ArchivedProject,
    CancelledProject,
    EquipmentNotFound,
    EquipmentRemoved,
    EquipmentTypeChangeConflict,
    InconsistentEquipment,
    InvalidEquipmentAttributeState,
    RevisionNotFound,
    RevisionReadOnly,
)
from powerforge_api.services import engineering_model_service as service_module
from powerforge_api.services.engineering_model_service import (
    VALUE_SLOTS,
    validate_equipment_consistency,
)
from powerforge_engineering_model import (
    EquipmentType,
    InformationState,
    LifecycleStatus,
    ValueOrigin,
    VerificationState,
    get_equipment_definition,
)
from powerforge_engineering_model.errors import (
    InvalidAttributeValue,
    InvalidEnumValue,
    UnknownAttribute,
    UnknownEquipmentType,
)
from powerforge_persistence import Project, ProjectRevision
from powerforge_persistence.engineering import Equipment, EquipmentAttribute, EquipmentLineage
from powerforge_project import ProjectStatus, RevisionStatus

pytestmark = pytest.mark.integration


def snapshot(equipment: Equipment) -> tuple:
    return (
        equipment.equipment_type,
        equipment.tag,
        tuple(
            sorted(
                (
                    r.attribute_key,
                    r.id,
                    r.value_type,
                    r.unit,
                    r.information_state,
                    r.verification_state,
                    r.origin,
                    r.confidence,
                    r.numeric_value,
                    r.integer_value,
                    r.text_value,
                    r.boolean_value,
                    r.created_by,
                    r.updated_by,
                    r.created_at,
                    r.updated_at,
                )
                for r in equipment.attributes
            )
        ),
    )


@pytest.mark.parametrize("equipment_type", list(EquipmentType))
def test_creation_materializes_exact_registry_and_defaults(
    engineering_context, equipment_type
) -> None:
    ctx = engineering_context
    actor = uuid4()
    equipment = ctx.service.create_equipment(*ctx.ids, equipment_type, tag="DUP", actor_id=actor)
    assert equipment.project_id == ctx.project_id and equipment.revision_id == ctx.revision_id
    lineage = ctx.session.get(EquipmentLineage, equipment.lineage_id)
    assert lineage.project_id == ctx.project_id and lineage.created_by == actor
    assert equipment.lifecycle_status == LifecycleStatus.ACTIVE
    assert equipment.origin == ValueOrigin.MANUAL
    assert equipment.verification_state == VerificationState.ENGINEER_REVIEWED
    assert equipment.inherited_from_equipment_id is None
    assert equipment.created_by == equipment.updated_by == actor
    attributes = ctx.service.get_equipment_attributes(*ctx.ids, equipment.id)
    expected = get_equipment_definition(equipment_type).attributes
    assert len(attributes) == len(expected)
    for row, definition in zip(attributes, expected, strict=True):
        assert (row.attribute_key, row.value_type, row.unit) == (
            definition.key,
            definition.value_type,
            definition.canonical_unit,
        )
        assert row.information_state == InformationState.NOT_POPULATED
        assert row.verification_state == VerificationState.UNVERIFIED
        assert row.origin is row.confidence is row.inherited_from_attribute_id is None
        assert row.created_by == row.updated_by == actor
        assert all(getattr(row, slot) is None for slot in VALUE_SLOTS)
    validate_equipment_consistency(equipment)


def test_duplicate_tags_allowed_and_lineages_are_independent(engineering_context) -> None:
    ctx = engineering_context
    a = ctx.service.create_equipment(*ctx.ids, "BUS", tag="BUS1")
    b = ctx.service.create_equipment(*ctx.ids, "BUS", tag="BUS1")
    assert a.lineage_id != b.lineage_id and a.id != b.id
    assert len(ctx.service.list_equipment(*ctx.ids)) == 2


def test_creation_rolls_back_partial_materialization(engineering_context, monkeypatch) -> None:
    ctx = engineering_context
    original = service_module._materialize
    calls = 0

    def fail(equipment, definition, actor):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("injected materialization failure")
        return original(equipment, definition, actor)

    monkeypatch.setattr(service_module, "_materialize", fail)
    with pytest.raises(RuntimeError):
        ctx.service.create_equipment(*ctx.ids, "BUS")
    for model in [EquipmentLineage, Equipment, EquipmentAttribute]:
        assert (
            ctx.session.scalar(
                select(func.count()).select_from(model).where(model.project_id == ctx.project_id)
            )
            == 0
        )
    with pytest.raises(UnknownEquipmentType):
        ctx.service.create_equipment(*ctx.ids, "BREAKER")


@pytest.mark.parametrize(
    "equipment_type,key,value,unit,slot,expected",
    [
        ("BUS", "nominal_voltage", 600, "V", "numeric_value", Decimal("0.6")),
        ("CT", "rated_burden", "0.01", "kVA", "numeric_value", Decimal(10)),
        ("VFD", "output_short_circuit_trip_time", "0.01", "s", "numeric_value", Decimal(10)),
        ("BUS", "phase_count", 3, None, "integer_value", 3),
        ("BUS", "manufacturer", "Acme", None, "text_value", "Acme"),
        ("BUS", "bus_type", "SWITCHGEAR", None, "text_value", "SWITCHGEAR"),
        ("BUS", "series_rating_applicable", False, None, "boolean_value", False),
    ],
)
def test_present_values_normalize_and_persist_in_correct_slots(
    engineering_context, equipment_type, key, value, unit, slot, expected
) -> None:
    ctx = engineering_context
    equipment = ctx.service.create_equipment(*ctx.ids, equipment_type)
    actor = uuid4()
    row = ctx.service.set_attribute(
        *ctx.ids,
        equipment.id,
        key,
        InformationState.PRESENT,
        value=value,
        input_unit=unit,
        actor_id=actor,
    )
    ctx.session.expire_all()
    row = ctx.session.get(EquipmentAttribute, row.id)
    assert getattr(row, slot) == expected
    if slot == "numeric_value":
        assert isinstance(row.numeric_value, Decimal)
    assert all(getattr(row, other) is None for other in VALUE_SLOTS if other != slot)
    assert (
        row.origin == ValueOrigin.MANUAL
        and row.verification_state == VerificationState.ENGINEER_REVIEWED
    )
    assert row.confidence is None and row.updated_by == actor


@pytest.mark.parametrize("state", [InformationState.MISSING, InformationState.NOT_APPLICABLE])
def test_manual_state_only_clears_value_keeps_canonical_unit(engineering_context, state) -> None:
    ctx = engineering_context
    eq = ctx.service.create_equipment(*ctx.ids, "BUS")
    ctx.service.set_attribute(
        *ctx.ids, eq.id, "nominal_voltage", InformationState.PRESENT, value=600, input_unit="V"
    )
    row = ctx.service.set_attribute(*ctx.ids, eq.id, "nominal_voltage", state)
    assert row.information_state == state and row.unit == "kV"
    assert all(getattr(row, slot) is None for slot in VALUE_SLOTS)
    assert (
        row.origin == ValueOrigin.MANUAL
        and row.verification_state == VerificationState.ENGINEER_REVIEWED
    )
    assert row.confidence is None
    with pytest.raises(InvalidEquipmentAttributeState):
        ctx.service.set_attribute(*ctx.ids, eq.id, "nominal_voltage", state, value=0)


def test_manual_edit_validation_and_metadata_allowlist(engineering_context) -> None:
    ctx = engineering_context
    eq = ctx.service.create_equipment(*ctx.ids, "BUS")
    for state in [
        "NOT_EXTRACTED",
        "UNKNOWN",
        InformationState.CONFLICTING,
        "ENGINEER_VERIFIED",
    ]:
        with pytest.raises(InvalidEquipmentAttributeState):
            ctx.service.set_attribute(*ctx.ids, eq.id, "nominal_voltage", state)
    for key, value, error in [
        ("nominal_voltage", None, InvalidAttributeValue),
        ("bus_type", "WRONG", InvalidEnumValue),
        ("phase_count", 1.5, InvalidAttributeValue),
        ("missing_key", 1, UnknownAttribute),
    ]:
        with pytest.raises(error):
            ctx.service.set_attribute(*ctx.ids, eq.id, key, InformationState.PRESENT, value=value)
    for forbidden in [
        "origin",
        "verification_state",
        "confidence",
        "value_type",
        "inherited_from_attribute_id",
    ]:
        with pytest.raises(TypeError):
            ctx.service.set_attribute(
                *ctx.ids,
                eq.id,
                "nominal_voltage",
                InformationState.PRESENT,
                value=1,
                **{forbidden: "forged"},
            )
    for forbidden in [
        "lineage_id",
        "origin",
        "verification_state",
        "inherited_from_equipment_id",
        "created_by",
    ]:
        with pytest.raises(TypeError):
            ctx.service.update_equipment(*ctx.ids, eq.id, **{forbidden: "forged"})
    ctx.service.update_equipment(*ctx.ids, eq.id, tag="tag", name="Name", description="Description")
    updated = ctx.service.update_equipment(*ctx.ids, eq.id, tag=None)
    assert updated.tag is None and updated.name == "Name" and updated.description == "Description"


def test_ownership_checks_reads_and_all_mutations(engineering_context) -> None:
    ctx = engineering_context
    eq = ctx.service.create_equipment(*ctx.ids, "BUS")
    other_project, other_revision = seed_revision(ctx.session)
    for ids, error in [
        ((other_project, other_revision), EquipmentNotFound),
        ((ctx.project_id, other_revision), RevisionNotFound),
    ]:
        for method in [
            ctx.service.get_equipment,
            ctx.service.get_equipment_attributes,
            ctx.service.update_equipment,
            ctx.service.remove_equipment,
            ctx.service.restore_equipment,
        ]:
            with pytest.raises(error):
                method(*ids, eq.id)
        with pytest.raises(error):
            ctx.service.set_attribute(
                *ids, eq.id, "nominal_voltage", InformationState.PRESENT, value=1
            )
    assert ctx.service.list_equipment(other_project, other_revision) == []


@pytest.mark.parametrize("project_status", list(ProjectStatus))
@pytest.mark.parametrize("revision_status", list(RevisionStatus))
def test_mutability_for_every_write_and_read_access(
    engineering_context, project_status, revision_status
) -> None:
    ctx = engineering_context
    eq = ctx.service.create_equipment(*ctx.ids, "BUS")
    equipment_id = eq.id
    project = ctx.session.get(Project, ctx.project_id)
    revision = ctx.session.get(ProjectRevision, ctx.revision_id)
    project.status = project_status
    revision.status = revision_status
    ctx.session.commit()
    expected = {
        ProjectStatus.ARCHIVED: ArchivedProject,
        ProjectStatus.CANCELLED: CancelledProject,
    }.get(project_status)
    if expected is None and revision_status == RevisionStatus.SUPERSEDED:
        expected = RevisionReadOnly
    operations = [
        lambda: ctx.service.create_equipment(*ctx.ids, "CT"),
        lambda: ctx.service.update_equipment(*ctx.ids, equipment_id, name="Edited"),
        lambda: ctx.service.set_attribute(
            *ctx.ids, equipment_id, "nominal_voltage", InformationState.PRESENT, value=1
        ),
        lambda: ctx.service.remove_equipment(*ctx.ids, equipment_id),
        lambda: ctx.service.restore_equipment(*ctx.ids, equipment_id),
    ]
    for operation in operations:
        if expected:
            with pytest.raises(expected):
                operation()
        else:
            operation()
    assert ctx.service.get_equipment(*ctx.ids, equipment_id).id == equipment_id
    assert ctx.service.list_equipment(*ctx.ids)


def test_remove_restore_idempotent_and_preserve_values(engineering_context) -> None:
    ctx = engineering_context
    eq = ctx.service.create_equipment(*ctx.ids, "BUS")
    ctx.service.set_attribute(*ctx.ids, eq.id, "nominal_voltage", InformationState.PRESENT, value=1)
    before = snapshot(eq)
    actor = uuid4()
    removed = ctx.service.remove_equipment(*ctx.ids, eq.id, actor_id=actor)
    at = removed.removed_at
    assert removed.removed_by == actor and at is not None
    removed = ctx.service.remove_equipment(*ctx.ids, eq.id, actor_id=uuid4())
    assert removed.removed_by == actor and removed.removed_at == at
    assert ctx.service.list_equipment(*ctx.ids) == []
    assert len(ctx.service.list_equipment(*ctx.ids, lifecycle_status=LifecycleStatus.REMOVED)) == 1
    assert len(ctx.service.list_equipment(*ctx.ids, lifecycle_status=None)) == 1
    with pytest.raises(EquipmentRemoved):
        ctx.service.update_equipment(*ctx.ids, eq.id, name="No")
    restored = ctx.service.restore_equipment(*ctx.ids, eq.id)
    timestamp = restored.updated_at
    restored = ctx.service.restore_equipment(*ctx.ids, eq.id)
    assert restored.updated_at == timestamp and restored.removed_at is restored.removed_by is None
    assert snapshot(restored) == before


def test_type_change_preserves_compatible_rows_and_materializes_destination(
    engineering_context,
) -> None:
    ctx = engineering_context
    eq = ctx.service.create_equipment(*ctx.ids, "BUS")
    manufacturer = ctx.service.set_attribute(
        *ctx.ids, eq.id, "manufacturer", InformationState.PRESENT, value="Acme"
    )
    preserved_id = manufacturer.id
    old = {a.attribute_key: a.id for a in eq.attributes}
    changed = ctx.service.update_equipment(*ctx.ids, eq.id, equipment_type="LV_BREAKER")
    assert changed.equipment_type == "LV_BREAKER"
    rows = {r.attribute_key: r for r in changed.attributes}
    assert set(rows) == {a.key for a in get_equipment_definition("LV_BREAKER").attributes}
    assert rows["manufacturer"].id == preserved_id and rows["manufacturer"].text_value == "Acme"
    assert ctx.session.get(EquipmentAttribute, old["bus_type"]) is None
    assert rows["trip_rating"].information_state == InformationState.NOT_POPULATED
    assert rows["trip_rating"].verification_state == VerificationState.UNVERIFIED


@pytest.mark.parametrize(
    "state",
    [
        InformationState.PRESENT,
        InformationState.MISSING,
        InformationState.NOT_APPLICABLE,
        InformationState.CONFLICTING,
    ],
)
def test_type_change_rejects_all_meaningful_old_only_states_atomically(
    engineering_context, state
) -> None:
    ctx = engineering_context
    eq = ctx.service.create_equipment(*ctx.ids, "BUS", tag="unchanged")
    row = next(r for r in eq.attributes if r.attribute_key == "nominal_voltage")
    if state == InformationState.CONFLICTING:
        row.information_state = state
        ctx.session.commit()  # exercise persisted future system state without adding a manual path
    else:
        ctx.service.set_attribute(
            *ctx.ids,
            eq.id,
            row.attribute_key,
            state,
            value=1 if state == InformationState.PRESENT else None,
        )
    before = snapshot(eq)
    with pytest.raises(EquipmentTypeChangeConflict):
        ctx.service.update_equipment(*ctx.ids, eq.id, equipment_type="LV_BREAKER", tag="changed")
    assert snapshot(ctx.service.get_equipment(*ctx.ids, eq.id)) == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("origin", ValueOrigin.IMPORTED),
        ("confidence", Decimal("0.5")),
        ("verification_state", VerificationState.ENGINEER_REVIEWED),
    ],
)
def test_not_extracted_with_nondefault_provenance_is_not_discardable(
    engineering_context, field, value
) -> None:
    ctx = engineering_context
    eq = ctx.service.create_equipment(*ctx.ids, "BUS")
    row = next(r for r in eq.attributes if r.attribute_key == "bus_type")
    setattr(row, field, value)
    ctx.session.commit()
    with pytest.raises(EquipmentTypeChangeConflict):
        ctx.service.update_equipment(*ctx.ids, eq.id, equipment_type="LV_BREAKER")


def test_type_change_cannot_reinterpret_units_or_invalid_enum(engineering_context) -> None:
    ctx = engineering_context
    eq = ctx.service.create_equipment(*ctx.ids, "SYNCHRONOUS_GENERATOR")
    ctx.service.set_attribute(
        *ctx.ids, eq.id, "zero_sequence_reactance", InformationState.PRESENT, value=1
    )
    with pytest.raises(EquipmentTypeChangeConflict):
        ctx.service.update_equipment(*ctx.ids, eq.id, equipment_type="UTILITY_SOURCE")
    eq = ctx.service.create_equipment(*ctx.ids, "LV_BREAKER")
    ctx.service.set_attribute(*ctx.ids, eq.id, "standard", InformationState.PRESENT, value="ANSI")
    ctx.service.set_attribute(
        *ctx.ids, eq.id, "breaker_type", InformationState.PRESENT, value="MCCB"
    )
    with pytest.raises(EquipmentTypeChangeConflict):
        ctx.service.update_equipment(*ctx.ids, eq.id, equipment_type="HV_BREAKER")
    ctx.service.set_attribute(*ctx.ids, eq.id, "breaker_type", InformationState.MISSING)
    changed = ctx.service.update_equipment(*ctx.ids, eq.id, equipment_type="HV_BREAKER")
    assert next(r for r in changed.attributes if r.attribute_key == "standard").text_value == "ANSI"


@pytest.mark.parametrize(
    "mutation", ["unit = 'A'", "value_type = 'INTEGER'", "attribute_key = 'invented'"]
)
def test_corrupted_registry_metadata_is_detected_before_writes(
    engineering_context, mutation
) -> None:
    ctx = engineering_context
    eq = ctx.service.create_equipment(*ctx.ids, "BUS")
    ctx.session.execute(
        text(
            f"UPDATE equipment_attributes SET {mutation} "
            "WHERE equipment_id = :id AND attribute_key = 'nominal_voltage'"
        ),
        {"id": eq.id},
    )
    ctx.session.commit()
    with pytest.raises(InconsistentEquipment):
        ctx.service.update_equipment(*ctx.ids, eq.id, name="must not update")


def test_type_change_replaces_untouched_same_key_with_different_unit(engineering_context) -> None:
    ctx = engineering_context
    eq = ctx.service.create_equipment(*ctx.ids, "SYNCHRONOUS_GENERATOR")
    old_id = next(r.id for r in eq.attributes if r.attribute_key == "zero_sequence_reactance")
    changed = ctx.service.update_equipment(*ctx.ids, eq.id, equipment_type="UTILITY_SOURCE")
    row = next(r for r in changed.attributes if r.attribute_key == "zero_sequence_reactance")
    assert row.id != old_id and row.unit == "Ω"
    assert row.information_state == InformationState.NOT_POPULATED
    assert ctx.session.get(EquipmentAttribute, old_id) is None


def test_type_change_failure_after_deletes_rolls_back_everything(
    engineering_context, monkeypatch
) -> None:
    ctx = engineering_context
    eq = ctx.service.create_equipment(*ctx.ids, "BUS", tag="Original")
    before = snapshot(eq)

    def fail(*args):
        raise RuntimeError("injected failure after incompatible rows were deleted")

    monkeypatch.setattr(service_module, "_materialize", fail)
    with pytest.raises(RuntimeError):
        ctx.service.update_equipment(*ctx.ids, eq.id, equipment_type="LV_BREAKER", tag="Changed")
    assert snapshot(ctx.service.get_equipment(*ctx.ids, eq.id)) == before


def test_manual_edit_replaces_prior_provenance_and_rejects_wrong_units(engineering_context) -> None:
    from powerforge_engineering_model.errors import IncompatibleUnit

    ctx = engineering_context
    eq = ctx.service.create_equipment(*ctx.ids, "BUS")
    row = ctx.service.set_attribute(
        *ctx.ids, eq.id, "nominal_voltage", InformationState.PRESENT, value=1
    )
    row.origin = ValueOrigin.IMPORTED
    row.verification_state = VerificationState.ENGINEER_VERIFIED
    row.confidence = Decimal("0.9")
    ctx.session.commit()
    with pytest.raises(IncompatibleUnit):
        ctx.service.set_attribute(
            *ctx.ids, eq.id, "nominal_voltage", InformationState.PRESENT, value=1, input_unit="A"
        )
    row = ctx.service.set_attribute(
        *ctx.ids, eq.id, "nominal_voltage", InformationState.PRESENT, value=600, input_unit="V"
    )
    assert row.origin == ValueOrigin.MANUAL
    assert row.verification_state == VerificationState.ENGINEER_REVIEWED
    assert row.confidence is None


@pytest.mark.parametrize(
    "corruption,expected",
    [
        ("typed_value", InvalidEquipmentAttributeState),
        ("unknown_constraint", service_module.ProjectError),
    ],
)
def test_commit_integrity_failure_is_translated_and_rolls_back_all_rows(
    engineering_context, corruption, expected
) -> None:
    from sqlalchemy import event

    from powerforge_api.exceptions import UnexpectedIntegrityError

    ctx = engineering_context

    def corrupt_before_flush(session, *rest):
        for obj in session.new:
            if isinstance(obj, EquipmentAttribute):
                if corruption == "typed_value":
                    obj.numeric_value = Decimal(1)
                else:
                    obj.attribute_key = None
                break

    event.listen(ctx.session, "before_flush", corrupt_before_flush)
    try:
        with pytest.raises(expected) as raised:
            ctx.service.create_equipment(*ctx.ids, "BUS")
        if corruption == "unknown_constraint":
            assert isinstance(raised.value, UnexpectedIntegrityError)
            assert raised.value.message == "An unexpected database integrity error occurred"
    finally:
        event.remove(ctx.session, "before_flush", corrupt_before_flush)
    for model in [EquipmentLineage, Equipment, EquipmentAttribute]:
        assert (
            ctx.session.scalar(
                select(func.count()).select_from(model).where(model.project_id == ctx.project_id)
            )
            == 0
        )


def test_invalid_persisted_enum_is_detected(engineering_context) -> None:
    ctx = engineering_context
    eq = ctx.service.create_equipment(*ctx.ids, "BUS")
    ctx.session.execute(
        text(
            "UPDATE equipment_attributes SET information_state='PRESENT', text_value='INVENTED' "
            "WHERE equipment_id=:id AND attribute_key='bus_type'"
        ),
        {"id": eq.id},
    )
    ctx.session.commit()
    with pytest.raises(InconsistentEquipment):
        ctx.service.get_equipment(*ctx.ids, eq.id)
