"""Phase 5C revision metadata and engineering-model inheritance."""

from __future__ import annotations

import uuid
from dataclasses import replace
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.orm import selectinload

from powerforge_api.db import get_engine, get_session_factory
from powerforge_api.main import app
from powerforge_api.schemas.projects import RevisionCreate, RevisionUpdate
from powerforge_api.services import engineering_model_inheritance, revision_service
from powerforge_api.services.engineering_model_service import EngineeringModelService
from powerforge_document_model import DocumentOrigin
from powerforge_document_processing.models import Document, RevisionDocument
from powerforge_engineering_model import (
    AttributeDefinition,
    AttributeValueType,
    InformationState,
    LifecycleStatus,
    ValueOrigin,
    VerificationState,
    get_equipment_definition,
)
from powerforge_persistence import Project, ProjectRevision
from powerforge_persistence.engineering import Equipment, EquipmentAttribute
from powerforge_project import ProjectStatus, RevisionStatus

client = TestClient(app)


@pytest.mark.parametrize("value", [True, False, 1.0, 1.5, "1"])
@pytest.mark.parametrize("schema", [RevisionCreate, RevisionUpdate])
def test_system_phase_count_rejects_coercive_inputs(value, schema) -> None:
    data = {"system_phase_count": value}
    if schema is RevisionCreate:
        data["identifier"] = "strict-phase-count"
    with pytest.raises(ValidationError):
        schema(**data)


@pytest.mark.parametrize("value", [1, 3, None])
@pytest.mark.parametrize("schema", [RevisionCreate, RevisionUpdate])
def test_system_phase_count_accepts_strict_integer_values(value, schema) -> None:
    data = {"system_phase_count": value}
    if schema is RevisionCreate:
        data["identifier"] = "strict-phase-count"
    assert schema(**data).system_phase_count == value


@pytest.fixture
def require_db() -> None:
    import os

    if os.environ.get("RUN_INTEGRATION") != "1":
        pytest.skip("Set RUN_INTEGRATION=1 to run live database tests.")
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))


def _project() -> str:
    response = client.post(
        "/api/projects",
        json={
            "project_number": f"P5C-{uuid.uuid4().hex[:10]}",
            "project_name": "Phase 5C",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _revision(project_id: str, identifier: str, **values):
    return client.post(
        f"/api/projects/{project_id}/revisions",
        json={"identifier": identifier, **values},
    )


def _equipment(revision_id: str) -> list[Equipment]:
    with get_session_factory()() as session:
        rows = session.scalars(
            select(Equipment)
            .where(Equipment.revision_id == uuid.UUID(revision_id))
            .options(selectinload(Equipment.attributes))
            .order_by(Equipment.tag)
        ).all()
        session.expunge_all()
        return list(rows)


def _revision_count(project_id: str) -> int:
    with get_session_factory()() as session:
        return session.scalar(
            select(func.count())
            .select_from(ProjectRevision)
            .where(ProjectRevision.project_id == uuid.UUID(project_id))
        )


def _seed_document(project_id: str, revision_id: str) -> None:
    with get_session_factory()() as session:
        document_id = uuid.uuid4()
        session.add(
            Document(
                id=document_id,
                project_id=uuid.UUID(project_id),
                original_filename="base.pdf",
                storage_key=f"projects/{project_id}/documents/{document_id}/original.pdf",
                mime_type="application/pdf",
                file_extension=".pdf",
                size_bytes=10,
                sha256="5" * 64,
            )
        )
        session.add(
            RevisionDocument(
                project_id=uuid.UUID(project_id),
                revision_id=uuid.UUID(revision_id),
                document_id=document_id,
                origin=DocumentOrigin.UPLOADED,
            )
        )
        session.commit()


@pytest.fixture
def model_base(require_db: None) -> dict[str, object]:
    project_id = _project()
    base = _revision(
        project_id,
        "0",
        activate=True,
        system_frequency="60",
        system_phase_count=3,
    ).json()
    with get_session_factory()() as session:
        service = EngineeringModelService(session)
        bus = service.create_equipment(
            uuid.UUID(project_id), uuid.UUID(base["id"]), "BUS", tag="BUS-1", name="Main"
        )
        for key, value, unit in [
            ("manufacturer", "Acme", None),
            ("bus_type", "SWITCHGEAR", None),
            ("nominal_voltage", 600, "V"),
            ("phase_count", 3, None),
            ("series_rating_applicable", False, None),
        ]:
            service.set_attribute(
                uuid.UUID(project_id),
                uuid.UUID(base["id"]),
                bus.id,
                key,
                InformationState.PRESENT,
                value=value,
                input_unit=unit,
            )
        service.set_attribute(
            uuid.UUID(project_id),
            uuid.UUID(base["id"]),
            bus.id,
            "enclosure_type",
            InformationState.MISSING,
        )
        removed = service.create_equipment(
            uuid.UUID(project_id), uuid.UUID(base["id"]), "CT", tag="CT-REMOVED"
        )
        service.remove_equipment(uuid.UUID(project_id), uuid.UUID(base["id"]), removed.id)
        bus = service.get_equipment(uuid.UUID(project_id), uuid.UUID(base["id"]), bus.id)
        bus.origin = ValueOrigin.IMPORTED
        bus.verification_state = VerificationState.ENGINEER_VERIFIED
        nominal = next(row for row in bus.attributes if row.attribute_key == "nominal_voltage")
        nominal.origin = ValueOrigin.IMPORTED
        nominal.verification_state = VerificationState.AI_EXTRACTED
        nominal.confidence = Decimal("0.73")
        session.commit()
        bus_id = bus.id
        removed_id = removed.id
    _seed_document(project_id, base["id"])
    return {
        "project_id": project_id,
        "base": base,
        "bus_id": bus_id,
        "removed_id": removed_id,
    }


@pytest.mark.integration
@pytest.mark.parametrize(
    "documents,model,expected_documents,expected_equipment",
    [(True, True, 1, 1), (True, False, 1, 0), (False, True, 0, 1), (False, False, 0, 0)],
)
def test_document_and_model_carry_forward_are_independent(
    model_base, documents, model, expected_documents, expected_equipment
) -> None:
    response = _revision(
        model_base["project_id"],
        f"matrix-{documents}-{model}-{uuid.uuid4().hex[:4]}",
        carry_forward_documents=documents,
        carry_forward_model=model,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["inherited_document_count"] == expected_documents
    assert body["inherited_model_equipment_count"] == expected_equipment
    assert len(_equipment(body["id"])) == expected_equipment


@pytest.mark.integration
def test_default_clone_preserves_semantics_and_excludes_removed(model_base) -> None:
    response = _revision(model_base["project_id"], "1", carry_forward_documents=False)
    assert response.status_code == 201, response.text
    child = response.json()
    assert child["inherited_model_equipment_count"] == 1
    assert child["system_frequency"] == "60"
    assert child["system_phase_count"] == 3

    [source] = [row for row in _equipment(model_base["base"]["id"]) if row.tag == "BUS-1"]
    [destination] = _equipment(child["id"])
    assert destination.id != source.id
    assert destination.lineage_id == source.lineage_id
    assert destination.inherited_from_equipment_id == source.id
    assert destination.lifecycle_status == LifecycleStatus.ACTIVE
    assert destination.origin == ValueOrigin.IMPORTED
    assert destination.verification_state == VerificationState.ENGINEER_VERIFIED
    assert (destination.tag, destination.name, destination.description) == (
        source.tag,
        source.name,
        source.description,
    )
    source_attributes = {row.attribute_key: row for row in source.attributes}
    destination_attributes = {row.attribute_key: row for row in destination.attributes}
    assert set(destination_attributes) == set(source_attributes)
    for key, inherited in destination_attributes.items():
        original = source_attributes[key]
        assert inherited.id != original.id
        assert inherited.inherited_from_attribute_id == original.id
        assert inherited.value_type == original.value_type
        assert inherited.unit == original.unit
        assert inherited.information_state == original.information_state
        assert inherited.verification_state == original.verification_state
        assert inherited.origin == original.origin
        assert inherited.confidence == original.confidence
        inherited_values = tuple(
            getattr(inherited, slot) for slot in engineering_model_inheritance.VALUE_SLOTS
        )
        original_values = tuple(
            getattr(original, slot) for slot in engineering_model_inheritance.VALUE_SLOTS
        )
        assert inherited_values == original_values


@pytest.mark.integration
def test_cloned_snapshots_are_independent(model_base) -> None:
    child = _revision(model_base["project_id"], "1").json()
    [destination] = _equipment(child["id"])
    ids = (uuid.UUID(model_base["project_id"]), uuid.UUID(child["id"]))
    with get_session_factory()() as session:
        service = EngineeringModelService(session)
        service.update_equipment(*ids, destination.id, tag="CHILD")
        service.set_attribute(
            *ids,
            destination.id,
            "nominal_voltage",
            InformationState.PRESENT,
            value=12.47,
            input_unit="kV",
        )
        service.remove_equipment(*ids, destination.id)
        service.restore_equipment(*ids, destination.id)
    [source] = [row for row in _equipment(model_base["base"]["id"]) if row.tag == "BUS-1"]
    assert source.tag == "BUS-1"
    voltage = next(row for row in source.attributes if row.attribute_key == "nominal_voltage")
    assert voltage.numeric_value == Decimal("0.6")

    source_ids = (uuid.UUID(model_base["project_id"]), uuid.UUID(model_base["base"]["id"]))
    with get_session_factory()() as session:
        EngineeringModelService(session).update_equipment(
            *source_ids, source.id, name="Source changed"
        )
    [destination] = _equipment(child["id"])
    assert destination.name == "Main"
    assert destination.tag == "CHILD"


@pytest.mark.integration
@pytest.mark.parametrize(
    "carry_value,has_base,expected",
    [
        ("omitted", True, 1),
        (None, True, 1),
        (True, True, 1),
        (False, True, 0),
        ("omitted", False, 0),
        (None, False, 0),
        (False, False, 0),
    ],
)
def test_carry_forward_model_resolution(require_db, carry_value, has_base, expected) -> None:
    project_id = _project()
    base = _revision(project_id, "0", activate=has_base).json()
    if has_base:
        with get_session_factory()() as session:
            EngineeringModelService(session).create_equipment(
                uuid.UUID(project_id), uuid.UUID(base["id"]), "CT"
            )
    body = {"based_on_revision_id": base["id"]} if has_base else {"based_on_revision_id": None}
    if carry_value != "omitted":
        body["carry_forward_model"] = carry_value
    child = _revision(project_id, "1", **body)
    assert child.status_code == 201, child.text
    assert child.json()["inherited_model_equipment_count"] == expected


@pytest.mark.integration
def test_model_true_without_base_is_rejected(require_db) -> None:
    project_id = _project()
    for body in [
        {"carry_forward_model": True},
        {"based_on_revision_id": None, "carry_forward_model": True},
    ]:
        response = _revision(project_id, f"bad-{uuid.uuid4().hex[:4]}", **body)
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "invalid_base_revision"
    assert _revision_count(project_id) == 0


@pytest.mark.integration
def test_metadata_omitted_override_and_explicit_null(model_base) -> None:
    project_id = model_base["project_id"]
    inherited = _revision(project_id, "inherit", carry_forward_documents=False).json()
    assert (inherited["system_frequency"], inherited["system_phase_count"]) == ("60", 3)

    overridden = _revision(
        project_id,
        "override",
        based_on_revision_id=model_base["base"]["id"],
        carry_forward_model=True,
        system_frequency="50.5",
        system_phase_count=1,
    ).json()
    assert (overridden["system_frequency"], overridden["system_phase_count"]) == ("50.5", 1)

    cleared = _revision(
        project_id,
        "clear",
        based_on_revision_id=model_base["base"]["id"],
        carry_forward_model=True,
        system_frequency=None,
        system_phase_count=None,
    ).json()
    assert (cleared["system_frequency"], cleared["system_phase_count"]) == (None, None)

    no_model = _revision(
        project_id,
        "fresh",
        based_on_revision_id=model_base["base"]["id"],
        carry_forward_model=False,
        system_frequency="25",
    ).json()
    assert (no_model["system_frequency"], no_model["system_phase_count"]) == ("25", None)


@pytest.mark.integration
def test_metadata_create_without_base_and_request_validation(require_db) -> None:
    project_id = _project()
    created = _revision(
        project_id,
        "0",
        based_on_revision_id=None,
        system_frequency="16.67",
        system_phase_count=1,
    )
    assert created.status_code == 201
    assert created.json()["system_frequency"] == "16.67"
    invalid_values = [
        ("system_frequency", 0),
        ("system_frequency", "NaN"),
        ("system_phase_count", 2),
    ]
    for field, value in invalid_values:
        response = _revision(project_id, f"bad-{uuid.uuid4().hex[:4]}", **{field: value})
        assert response.status_code == 422


@pytest.mark.integration
def test_metadata_updates_obey_engineering_mutability(model_base) -> None:
    project_id = model_base["project_id"]
    base_id = model_base["base"]["id"]
    updated = client.patch(
        f"/api/projects/{project_id}/revisions/{base_id}",
        json={"system_frequency": "50", "system_phase_count": None},
    )
    assert updated.status_code == 200, updated.text
    assert (updated.json()["system_frequency"], updated.json()["system_phase_count"]) == (
        "50",
        None,
    )
    child = _revision(project_id, "1", activate=True).json()
    blocked = client.patch(
        f"/api/projects/{project_id}/revisions/{base_id}", json={"system_phase_count": 3}
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "revision_read_only"
    assert child["status"] == "ACTIVE"
    client.post(f"/api/projects/{project_id}/archive")
    archived = client.patch(
        f"/api/projects/{project_id}/revisions/{child['id']}", json={"system_frequency": 60}
    )
    assert archived.status_code == 409
    assert archived.json()["detail"]["code"] == "archived_project"


@pytest.mark.integration
@pytest.mark.parametrize(
    "project_status,revision_status,expected_code",
    [
        (ProjectStatus.ACTIVE, RevisionStatus.DRAFT, None),
        (ProjectStatus.ACTIVE, RevisionStatus.ACTIVE, None),
        (ProjectStatus.PAUSED, RevisionStatus.DRAFT, None),
        (ProjectStatus.PAUSED, RevisionStatus.ACTIVE, None),
        (ProjectStatus.ACTIVE, RevisionStatus.SUPERSEDED, "revision_read_only"),
        (ProjectStatus.ARCHIVED, RevisionStatus.ACTIVE, "archived_project"),
        (ProjectStatus.CANCELLED, RevisionStatus.ACTIVE, "cancelled_project"),
    ],
)
def test_metadata_update_mutability_matrix(
    model_base, project_status, revision_status, expected_code
) -> None:
    project_id = uuid.UUID(model_base["project_id"])
    revision_id = uuid.UUID(model_base["base"]["id"])
    with get_session_factory()() as session:
        session.get(Project, project_id).status = project_status
        session.get(ProjectRevision, revision_id).status = revision_status
        session.commit()

    response = client.patch(
        f"/api/projects/{project_id}/revisions/{revision_id}",
        json={"system_frequency": "50"},
    )
    if expected_code is None:
        assert response.status_code == 200, response.text
        assert response.json()["system_frequency"] == "50"
    else:
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == expected_code


@pytest.mark.integration
def test_metadata_update_does_not_materialize_or_change_equipment_attributes(model_base) -> None:
    [before] = [row for row in _equipment(model_base["base"]["id"]) if row.tag == "BUS-1"]
    phase_before = next(row for row in before.attributes if row.attribute_key == "phase_count")
    snapshot = (
        phase_before.id,
        phase_before.information_state,
        phase_before.integer_value,
        phase_before.origin,
        phase_before.verification_state,
    )

    response = client.patch(
        f"/api/projects/{model_base['project_id']}/revisions/{model_base['base']['id']}",
        json={"system_phase_count": 1},
    )
    assert response.status_code == 200, response.text

    [after] = [row for row in _equipment(model_base["base"]["id"]) if row.tag == "BUS-1"]
    phase_after = next(row for row in after.attributes if row.attribute_key == "phase_count")
    assert (
        phase_after.id,
        phase_after.information_state,
        phase_after.integer_value,
        phase_after.origin,
        phase_after.verification_state,
    ) == snapshot


@pytest.mark.integration
def test_registry_new_attribute_is_materialized_without_touching_source(
    model_base, monkeypatch
) -> None:
    original = get_equipment_definition("BUS")
    added = AttributeDefinition(
        key="future_marker",
        display_name="Future Marker",
        value_type=AttributeValueType.TEXT,
        canonical_unit=None,
        required=False,
        critical=False,
        allowed_values=(),
        notes=None,
        display_order=999,
    )
    evolved = replace(original, attributes=(*original.attributes, added))
    monkeypatch.setattr(
        engineering_model_inheritance,
        "get_equipment_definition",
        lambda equipment_type: (
            evolved if str(equipment_type) == "BUS" else get_equipment_definition(equipment_type)
        ),
    )
    child = _revision(model_base["project_id"], "evolved").json()
    [destination] = _equipment(child["id"])
    marker = next(row for row in destination.attributes if row.attribute_key == "future_marker")
    assert marker.information_state == InformationState.NOT_EXTRACTED
    assert marker.verification_state == VerificationState.UNVERIFIED
    assert marker.origin is marker.confidence is marker.inherited_from_attribute_id is None
    [source] = [row for row in _equipment(model_base["base"]["id"]) if row.tag == "BUS-1"]
    assert "future_marker" not in {row.attribute_key for row in source.attributes}


def _extra_source_attribute(model_base, *, meaningful: bool) -> None:
    with get_session_factory()() as session:
        source = session.get(Equipment, model_base["bus_id"])
        session.add(
            EquipmentAttribute(
                project_id=source.project_id,
                revision_id=source.revision_id,
                equipment_id=source.id,
                attribute_key="retired_attribute",
                value_type=AttributeValueType.TEXT,
                text_value="keep" if meaningful else None,
                information_state=(
                    InformationState.PRESENT if meaningful else InformationState.NOT_EXTRACTED
                ),
                verification_state=(
                    VerificationState.ENGINEER_REVIEWED
                    if meaningful
                    else VerificationState.UNVERIFIED
                ),
                origin=ValueOrigin.MANUAL if meaningful else None,
            )
        )
        session.commit()


@pytest.mark.integration
def test_old_only_untouched_attribute_is_omitted(model_base) -> None:
    _extra_source_attribute(model_base, meaningful=False)
    child = _revision(model_base["project_id"], "old-placeholder")
    assert child.status_code == 201, child.text
    [destination] = _equipment(child.json()["id"])
    assert "retired_attribute" not in {row.attribute_key for row in destination.attributes}


@pytest.mark.integration
def test_meaningful_registry_incompatibility_rolls_back_revision(model_base) -> None:
    _extra_source_attribute(model_base, meaningful=True)
    before = _revision_count(model_base["project_id"])
    response = _revision(model_base["project_id"], "must-fail")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "model_inheritance_conflict"
    assert _revision_count(model_base["project_id"]) == before


@pytest.mark.integration
@pytest.mark.parametrize("change", ["type", "unit", "enum"])
def test_changed_registry_rejects_meaningful_source(model_base, monkeypatch, change) -> None:
    original = get_equipment_definition("BUS")
    if change == "enum":
        target_key = "bus_type"
        replacement = replace(
            next(row for row in original.attributes if row.key == target_key),
            allowed_values=("PANELBOARD",),
        )
    else:
        target_key = "nominal_voltage"
        current = next(row for row in original.attributes if row.key == target_key)
        replacement = replace(
            current,
            value_type=AttributeValueType.TEXT if change == "type" else current.value_type,
            canonical_unit="V" if change == "unit" else current.canonical_unit,
        )
    evolved = replace(
        original,
        attributes=tuple(
            replacement if row.key == target_key else row for row in original.attributes
        ),
    )
    monkeypatch.setattr(
        engineering_model_inheritance, "get_equipment_definition", lambda _: evolved
    )
    before = _revision_count(model_base["project_id"])
    response = _revision(model_base["project_id"], f"bad-{change}")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "model_inheritance_conflict"
    assert _revision_count(model_base["project_id"]) == before


@pytest.mark.integration
def test_failure_after_document_copy_rolls_back_everything(model_base, monkeypatch) -> None:
    before = _revision_count(model_base["project_id"])

    def fail(*args, **kwargs):
        raise RuntimeError("model clone failed")

    monkeypatch.setattr(revision_service, "copy_active_engineering_model", fail)
    with pytest.raises(RuntimeError):
        _revision(model_base["project_id"], "rollback")
    assert _revision_count(model_base["project_id"]) == before
    with get_session_factory()() as session:
        project_id = uuid.UUID(model_base["project_id"])
        assert (
            session.scalar(
                select(func.count())
                .select_from(Equipment)
                .where(Equipment.project_id == project_id)
            )
            == 2
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(RevisionDocument)
                .where(RevisionDocument.project_id == project_id)
            )
            == 1
        )


@pytest.mark.integration
def test_failure_during_attribute_clone_rolls_back_flushed_equipment(
    model_base, monkeypatch
) -> None:
    before = _revision_count(model_base["project_id"])

    def fail(*args, **kwargs):
        raise RuntimeError("attribute clone failed")

    monkeypatch.setattr(engineering_model_inheritance, "_cloned_attribute", fail)
    with pytest.raises(RuntimeError):
        _revision(model_base["project_id"], "rollback-attribute")
    assert _revision_count(model_base["project_id"]) == before
    with get_session_factory()() as session:
        project_id = uuid.UUID(model_base["project_id"])
        assert (
            session.scalar(
                select(func.count())
                .select_from(Equipment)
                .where(Equipment.project_id == project_id)
            )
            == 2
        )
        assert session.scalar(
            select(func.count())
            .select_from(EquipmentAttribute)
            .where(EquipmentAttribute.project_id == project_id)
        ) == sum(len(row.attributes) for row in _equipment(model_base["base"]["id"]))


@pytest.mark.integration
def test_failure_during_metadata_resolution_creates_no_revision(model_base, monkeypatch) -> None:
    before = _revision_count(model_base["project_id"])

    def fail(*args, **kwargs):
        raise RuntimeError("metadata resolution failed")

    monkeypatch.setattr(revision_service.RevisionService, "_resolve_model_metadata", fail)
    with pytest.raises(RuntimeError):
        _revision(model_base["project_id"], "rollback-metadata", activate=True)
    assert _revision_count(model_base["project_id"]) == before
    fetched = client.get(
        f"/api/projects/{model_base['project_id']}/revisions/{model_base['base']['id']}"
    ).json()
    assert fetched["status"] == "ACTIVE"


@pytest.mark.integration
def test_failure_before_activation_restores_original_active(model_base, monkeypatch) -> None:
    before = _revision_count(model_base["project_id"])

    def fail(*args, **kwargs):
        raise RuntimeError("activation failed")

    monkeypatch.setattr(revision_service.RevisionService, "_activate_locked", fail)
    with pytest.raises(RuntimeError):
        _revision(model_base["project_id"], "rollback-active", activate=True)
    assert _revision_count(model_base["project_id"]) == before
    fetched = client.get(
        f"/api/projects/{model_base['project_id']}/revisions/{model_base['base']['id']}"
    ).json()
    assert fetched["status"] == "ACTIVE"


@pytest.mark.integration
def test_openapi_preserves_phase5c_revision_fields() -> None:
    schemas = app.openapi()["components"]["schemas"]
    assert {"carry_forward_model", "system_frequency", "system_phase_count"} <= set(
        schemas["RevisionCreate"]["properties"]
    )
    assert {"system_frequency", "system_phase_count"} <= set(
        schemas["RevisionUpdate"]["properties"]
    )
    assert {
        "system_frequency",
        "system_phase_count",
        "inherited_model_equipment_count",
    } <= set(schemas["RevisionResponse"]["properties"])
    # Phase 5E now exposes separate model routes; revision bodies still own only metadata.
    for name in ("RevisionCreate", "RevisionUpdate", "RevisionResponse"):
        assert not {"equipment", "attributes", "nodes", "connections"} & set(
            schemas[name]["properties"]
        )


@pytest.mark.integration
def test_inheritance_count_is_create_response_only(model_base) -> None:
    created = _revision(model_base["project_id"], "count-scope").json()
    assert created["inherited_model_equipment_count"] == 1

    fetched = client.get(
        f"/api/projects/{model_base['project_id']}/revisions/{created['id']}"
    ).json()
    assert fetched["inherited_model_equipment_count"] is None
    listed = client.get(f"/api/projects/{model_base['project_id']}/revisions").json()["items"]
    row = next(item for item in listed if item["id"] == created["id"])
    assert row["inherited_model_equipment_count"] is None
