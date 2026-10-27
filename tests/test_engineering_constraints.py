"""Raw SQL proves structural invariants cannot be bypassed outside the service."""

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from engineering_support import engineering_context as engineering_context
from engineering_support import seed_revision
from powerforge_api.db_errors import constraint_name
from powerforge_persistence import ProjectRevision

pytestmark = pytest.mark.integration


def rejects(session, sql, params, constraint) -> None:
    with pytest.raises(IntegrityError) as error, session.begin_nested():
        session.execute(text(sql), params)
    assert constraint_name(error.value) == constraint


@pytest.mark.parametrize(
    "value_type,slot,value",
    [
        ("NUMBER", "numeric_value", Decimal("0.1234567890123456789012345678901234")),
        ("INTEGER", "integer_value", 3),
        ("TEXT", "text_value", "hello"),
        ("ENUM", "text_value", "SWITCHGEAR"),
        ("BOOLEAN", "boolean_value", False),
    ],
)
def test_typed_slots_enforced_for_every_value_type(
    engineering_context, value_type, slot, value
) -> None:
    ctx = engineering_context
    eq = ctx.service.create_equipment(*ctx.ids, "BUS")
    row_id = eq.attributes[0].id
    params = {"id": row_id, "kind": value_type, "value": value}
    # Clear the row between cases; tests deliberately use a slot independent of registry metadata.
    reset = (
        "UPDATE equipment_attributes SET numeric_value=NULL, integer_value=NULL, text_value=NULL, "
        "boolean_value=NULL, information_state='NOT_POPULATED', value_type=CAST(:kind AS "
        "model_attribute_value_type) WHERE id=:id"
    )
    ctx.session.execute(text(reset), params)
    rejects(
        ctx.session,
        "UPDATE equipment_attributes SET information_state='PRESENT' WHERE id=:id",
        params,
        "ck_equipment_attributes_typed_value",
    )
    ctx.session.execute(
        text(
            f"UPDATE equipment_attributes SET information_state='PRESENT', {slot}=:value "
            f"WHERE id=:id"
        ),
        params,
    )
    assert (
        ctx.session.execute(
            text(f"SELECT {slot} FROM equipment_attributes WHERE id=:id"), params
        ).scalar_one()
        == value
    )
    other = "text_value" if slot != "text_value" else "integer_value"
    other_value = "'extra'" if other == "text_value" else "9"
    rejects(
        ctx.session,
        f"UPDATE equipment_attributes SET {other}={other_value} WHERE id=:id",
        params,
        "ck_equipment_attributes_typed_value",
    )
    rejects(
        ctx.session,
        f"UPDATE equipment_attributes SET {slot}=NULL, {other}={other_value} WHERE id=:id",
        params,
        "ck_equipment_attributes_typed_value",
    )
    for state in ["MISSING", "NOT_APPLICABLE", "NOT_POPULATED", "CONFLICTING"]:
        rejects(
            ctx.session,
            "UPDATE equipment_attributes SET information_state=CAST(:state AS "
            "model_information_state) WHERE id=:id",
            {**params, "state": state},
            "ck_equipment_attributes_typed_value",
        )
    ctx.session.rollback()


@pytest.mark.parametrize("confidence", ["-0.01", "1.01", "NaN", "Infinity", "-Infinity"])
def test_confidence_bounds(engineering_context, confidence) -> None:
    ctx = engineering_context
    eq = ctx.service.create_equipment(*ctx.ids, "BUS")
    rejects(
        ctx.session,
        "UPDATE equipment_attributes SET confidence=CAST(:value AS numeric) WHERE id=:id",
        {"value": confidence, "id": eq.attributes[0].id},
        "ck_equipment_attributes_confidence",
    )


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_numeric_rejected(engineering_context, number) -> None:
    ctx = engineering_context
    eq = ctx.service.create_equipment(*ctx.ids, "BUS")
    row = next(r for r in eq.attributes if r.attribute_key == "nominal_voltage")
    rejects(
        ctx.session,
        "UPDATE equipment_attributes SET information_state='PRESENT', "
        "numeric_value=CAST(:value AS numeric) WHERE id=:id",
        {"id": row.id, "value": number},
        "ck_equipment_attributes_finite_numeric",
    )


def test_ownership_and_identity_constraints(engineering_context) -> None:
    ctx = engineering_context
    eq = ctx.service.create_equipment(*ctx.ids, "BUS")
    other_project, other_revision = seed_revision(ctx.session)
    other = ctx.service.create_equipment(other_project, other_revision, "BUS")
    new_revision = ProjectRevision(project_id=ctx.project_id, identifier="1")
    ctx.session.add(new_revision)
    ctx.session.commit()
    params = {
        "id": eq.id,
        "other_project": other_project,
        "other_revision": other_revision,
        "other_lineage": other.lineage_id,
        "row": eq.attributes[0].id,
        "revision": new_revision.id,
    }
    for sql, constraint in [
        (
            "INSERT INTO equipment (project_id, revision_id, lineage_id, equipment_type) "
            "SELECT project_id, :other_revision, lineage_id, equipment_type "
            "FROM equipment WHERE id=:id",
            "fk_equipment_revision",
        ),
        ("UPDATE equipment SET lineage_id=:other_lineage WHERE id=:id", "fk_equipment_lineage"),
        (
            "UPDATE equipment_attributes SET revision_id=:revision WHERE id=:row",
            "fk_equipment_attributes_equipment",
        ),
        (
            "UPDATE equipment_attributes SET project_id=:other_project WHERE id=:row",
            "fk_equipment_attributes_equipment",
        ),
        (
            "INSERT INTO equipment (project_id, revision_id, lineage_id, equipment_type) "
            "SELECT project_id, revision_id, lineage_id, equipment_type FROM equipment "
            "WHERE id=:id",
            "uq_equipment_revision_lineage",
        ),
        (
            "INSERT INTO equipment_attributes (project_id, revision_id, equipment_id, "
            "attribute_key, value_type, unit) SELECT project_id, revision_id, equipment_id,"
            " attribute_key, value_type, unit FROM equipment_attributes WHERE id=:row",
            "uq_equipment_attributes_key",
        ),
    ]:
        rejects(ctx.session, sql, params, constraint)


def test_lifecycle_and_inheritance_constraints(engineering_context) -> None:
    ctx = engineering_context
    eq = ctx.service.create_equipment(*ctx.ids, "BUS")
    other_ids = seed_revision(ctx.session)
    other = ctx.service.create_equipment(*other_ids, "BUS")
    params = {
        "id": eq.id,
        "row": eq.attributes[0].id,
        "other": other.id,
        "other_row": other.attributes[0].id,
    }
    for sql, constraint in [
        (
            "UPDATE equipment SET lifecycle_status='REMOVED' WHERE id=:id",
            "ck_equipment_lifecycle_removed_at",
        ),
        ("UPDATE equipment SET removed_at=now() WHERE id=:id", "ck_equipment_lifecycle_removed_at"),
        (
            "UPDATE equipment SET removed_by=gen_random_uuid() WHERE id=:id",
            "ck_equipment_lifecycle_removed_at",
        ),
        (
            "UPDATE equipment SET inherited_from_equipment_id=id WHERE id=:id",
            "ck_equipment_inherited_not_self",
        ),
        (
            "UPDATE equipment_attributes SET inherited_from_attribute_id=id WHERE id=:row",
            "ck_equipment_attributes_inherited_not_self",
        ),
        (
            "UPDATE equipment SET inherited_from_equipment_id=:other WHERE id=:id",
            "fk_equipment_inherited_from",
        ),
        (
            "UPDATE equipment_attributes SET inherited_from_attribute_id=:other_row WHERE id=:row",
            "fk_equipment_attributes_inherited_from",
        ),
    ]:
        rejects(ctx.session, sql, params, constraint)
