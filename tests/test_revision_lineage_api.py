"""Revision lineage and document inheritance. Integration cases need RUN_INTEGRATION=1.

Documents are seeded straight through the ORM because no upload endpoint exists yet.
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import IntegrityError

from powerforge_api.db import get_engine, get_session_factory
from powerforge_api.main import app
from powerforge_api.models import Document, ProjectRevision, RevisionDocument
from powerforge_api.services import revision_service
from powerforge_api.storage import InMemoryObjectStorage
from powerforge_document_model import (
    DocumentClassification,
    DocumentOrigin,
    RevisionDocumentStatus,
)

client = TestClient(app)

OLD = datetime(2020, 1, 1, tzinfo=UTC)


@pytest.fixture
def require_db() -> None:
    if os.environ.get("RUN_INTEGRATION") != "1":
        pytest.skip("Set RUN_INTEGRATION=1 to run live database tests.")
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))


@pytest.fixture
def storage(object_storage: InMemoryObjectStorage) -> Iterator[InMemoryObjectStorage]:
    yield object_storage
    assert object_storage.calls == [], "revision creation must never touch object storage"


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def make_project() -> str:
    response = client.post(
        "/api/projects",
        json={"project_number": _unique("LIN"), "project_name": "Lineage"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def make_revision(project_id: str, identifier: str, **body: Any) -> Any:
    return client.post(
        f"/api/projects/{project_id}/revisions",
        json={"identifier": identifier, **body},
    )


def seed_document(
    project_id: str,
    revision_id: str,
    *,
    status: RevisionDocumentStatus = RevisionDocumentStatus.INCLUDED,
    origin: DocumentOrigin = DocumentOrigin.UPLOADED,
    inherited_from: str | None = None,
    document_id: uuid.UUID | None = None,
    **metadata: Any,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Insert (or reuse) a Document and attach it to a revision. Returns both ids."""
    with get_session_factory()() as session:
        if document_id is None:
            new_id = uuid.uuid4()
            session.add(
                Document(
                    id=new_id,
                    project_id=uuid.UUID(project_id),
                    original_filename="plan.pdf",
                    storage_key=f"projects/{project_id}/documents/{new_id}/original.pdf",
                    mime_type="application/pdf",
                    file_extension=".pdf",
                    size_bytes=10,
                    sha256="0" * 64,
                )
            )
            session.flush()
            document_id = new_id
        link = RevisionDocument(
            project_id=uuid.UUID(project_id),
            revision_id=uuid.UUID(revision_id),
            document_id=document_id,
            origin=origin,
            inherited_from_revision_id=uuid.UUID(inherited_from) if inherited_from else None,
            status=status,
            removed_at=OLD if status is RevisionDocumentStatus.REMOVED else None,
            added_at=OLD,
            **metadata,
        )
        session.add(link)
        session.commit()
        return document_id, link.id


def associations(revision_id: str) -> list[RevisionDocument]:
    with get_session_factory()() as session:
        rows = session.scalars(
            select(RevisionDocument).where(RevisionDocument.revision_id == uuid.UUID(revision_id))
        ).all()
        session.expunge_all()
        return list(rows)


def revision_count(project_id: str) -> int:
    with get_session_factory()() as session:
        return session.scalar(
            select(func.count())
            .select_from(ProjectRevision)
            .where(ProjectRevision.project_id == uuid.UUID(project_id))
        )


def association_count() -> int:
    with get_session_factory()() as session:
        return session.scalar(select(func.count()).select_from(RevisionDocument))


def code(response: Any) -> str:
    return response.json()["detail"]["code"]


@pytest.fixture
def project_with_base(require_db: None, storage: InMemoryObjectStorage) -> dict[str, Any]:
    """A project whose ACTIVE revision "0" holds documents A and B (INCLUDED) and C (REMOVED)."""
    project_id = make_project()
    base = make_revision(project_id, "0", activate=True).json()
    meta_a = {
        "document_type": DocumentClassification.SINGLE_LINE_DIAGRAM,
        "document_number": "E-001",
        "description": "Main SLD",
        "notes": "Rev A drawing",
    }
    doc_a, _ = seed_document(project_id, base["id"], **meta_a)
    doc_b, _ = seed_document(
        project_id, base["id"], document_type=DocumentClassification.PANEL_SCHEDULE
    )
    doc_c, _ = seed_document(project_id, base["id"], status=RevisionDocumentStatus.REMOVED)
    return {"project_id": project_id, "base": base, "docs": {"a": doc_a, "b": doc_b, "c": doc_c}}


def test_inheritance_matrix(project_with_base: dict[str, Any]) -> None:
    project_id = project_with_base["project_id"]
    base = project_with_base["base"]
    docs = project_with_base["docs"]

    response = make_revision(project_id, "1")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "DRAFT"
    assert body["based_on_revision_id"] == base["id"]
    assert body["based_on_identifier"] == "0"
    assert body["inherited_document_count"] == 2

    child = {row.document_id: row for row in associations(body["id"])}
    assert set(child) == {docs["a"], docs["b"]}
    base_rows = {row.document_id: row for row in associations(base["id"])}
    assert set(base_rows) == {docs["a"], docs["b"], docs["c"]}

    row_a = child[docs["a"]]
    assert row_a.origin is DocumentOrigin.INHERITED
    assert row_a.status is RevisionDocumentStatus.INCLUDED
    assert str(row_a.inherited_from_revision_id) == base["id"]
    assert row_a.document_type is DocumentClassification.SINGLE_LINE_DIAGRAM
    assert (row_a.document_number, row_a.description, row_a.notes) == (
        "E-001",
        "Main SLD",
        "Rev A drawing",
    )
    assert row_a.id != base_rows[docs["a"]].id
    assert row_a.added_at > OLD
    assert row_a.removed_at is None and row_a.removed_by is None
    assert child[docs["b"]].document_type is DocumentClassification.PANEL_SCHEDULE

    assert all(row.origin is DocumentOrigin.UPLOADED for row in base_rows.values())
    assert base_rows[docs["c"]].status is RevisionDocumentStatus.REMOVED


def test_inheritance_is_logged_with_counts_only(
    project_with_base: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=revision_service.logger.name)
    make_revision(project_with_base["project_id"], "1")
    message = "revision document inheritance completed"
    records = [r for r in caplog.records if r.getMessage() == message]
    assert len(records) == 1
    assert records[0].inherited_document_count == 2  # type: ignore[attr-defined]


def test_carry_forward_false_records_base_but_copies_nothing(
    project_with_base: dict[str, Any],
) -> None:
    response = make_revision(project_with_base["project_id"], "1", carry_forward_documents=False)
    body = response.json()
    assert response.status_code == 201
    assert body["based_on_revision_id"] == project_with_base["base"]["id"]
    assert body["inherited_document_count"] == 0
    assert associations(body["id"]) == []


def test_explicit_null_base_means_no_base_even_with_an_active_revision(
    project_with_base: dict[str, Any],
) -> None:
    response = make_revision(project_with_base["project_id"], "1", based_on_revision_id=None)
    body = response.json()
    assert response.status_code == 201
    assert body["based_on_revision_id"] is None
    assert body["based_on_identifier"] is None
    assert body["inherited_document_count"] == 0
    assert associations(body["id"]) == []


def test_carry_forward_true_without_a_base_is_rejected(require_db: None, storage) -> None:
    project_id = make_project()
    response = make_revision(project_id, "0", carry_forward_documents=True)
    assert response.status_code == 422
    assert code(response) == "invalid_base_revision"
    assert revision_count(project_id) == 0

    explicit_null = make_revision(
        project_id, "0", based_on_revision_id=None, carry_forward_documents=True
    )
    assert explicit_null.status_code == 422
    assert revision_count(project_id) == 0


def test_omitted_base_with_no_active_revision_has_no_base(require_db: None, storage) -> None:
    project_id = make_project()
    body = make_revision(project_id, "0").json()
    assert body["based_on_revision_id"] is None
    assert body["inherited_document_count"] == 0


def test_explicit_carry_forward_null_behaves_like_omitted(
    project_with_base: dict[str, Any],
) -> None:
    response = make_revision(project_with_base["project_id"], "1", carry_forward_documents=None)
    assert response.json()["inherited_document_count"] == 2


def test_base_may_be_an_older_superseded_revision(project_with_base: dict[str, Any]) -> None:
    project_id = project_with_base["project_id"]
    base = project_with_base["base"]
    newer = make_revision(project_id, "1", activate=True).json()
    assert newer["inherited_document_count"] == 2

    response = make_revision(project_id, "2", based_on_revision_id=base["id"])
    body = response.json()
    assert response.status_code == 201, response.text
    assert body["based_on_revision_id"] == base["id"]
    assert body["inherited_document_count"] == 2
    listing = client.get(f"/api/projects/{project_id}/revisions").json()["items"]
    assert {r["id"]: r["status"] for r in listing}[base["id"]] == "SUPERSEDED"


def test_base_from_another_project_is_rejected(project_with_base: dict[str, Any]) -> None:
    other_project = make_project()
    other_revision = make_revision(other_project, "0", activate=True).json()

    response = make_revision(
        project_with_base["project_id"], "1", based_on_revision_id=other_revision["id"]
    )
    assert response.status_code == 422
    assert code(response) == "invalid_base_revision"
    assert revision_count(project_with_base["project_id"]) == 1


def test_unknown_base_is_rejected(project_with_base: dict[str, Any]) -> None:
    response = make_revision(
        project_with_base["project_id"], "1", based_on_revision_id=str(uuid.uuid4())
    )
    assert response.status_code == 422
    assert code(response) == "invalid_base_revision"


def test_malformed_base_id_fails_request_validation(project_with_base: dict[str, Any]) -> None:
    response = make_revision(
        project_with_base["project_id"], "1", based_on_revision_id="not-a-uuid"
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "constraint", ["fk_project_revisions_based_on", "ck_project_revisions_based_on_not_self"]
)
def test_lineage_constraint_violations_map_to_invalid_base_revision(
    project_with_base: dict[str, Any], monkeypatch: pytest.MonkeyPatch, constraint: str
) -> None:
    class Diag:
        constraint_name = constraint
        sqlstate = "23503"

    class Orig(Exception):
        diag = Diag()
        sqlstate = "23503"

    def violate(*_args: object, **_kwargs: object) -> int:
        raise IntegrityError("INSERT", {}, Orig("violation"))

    monkeypatch.setattr(revision_service, "copy_included_associations", violate)
    project_id = project_with_base["project_id"]
    response = make_revision(project_id, "1")
    assert response.status_code == 422
    assert code(response) == "invalid_base_revision"
    assert revision_count(project_id) == 1


def test_lineage_cannot_be_changed_with_patch(project_with_base: dict[str, Any]) -> None:
    project_id = project_with_base["project_id"]
    child = make_revision(project_id, "1").json()
    response = client.patch(
        f"/api/projects/{project_id}/revisions/{child['id']}",
        json={"based_on_revision_id": None},
    )
    assert response.status_code == 422
    fetched = client.get(f"/api/projects/{project_id}/revisions/{child['id']}").json()
    assert fetched["based_on_revision_id"] == project_with_base["base"]["id"]


def test_activate_with_carry_forward_copies_before_the_base_is_superseded(
    project_with_base: dict[str, Any],
) -> None:
    project_id = project_with_base["project_id"]
    response = make_revision(project_id, "1", activate=True)
    body = response.json()
    assert response.status_code == 201, response.text
    assert body["status"] == "ACTIVE"
    assert body["inherited_document_count"] == 2
    assert len(associations(body["id"])) == 2

    revisions = client.get(f"/api/projects/{project_id}/revisions").json()["items"]
    statuses = {r["identifier"]: r["status"] for r in revisions}
    assert statuses == {"0": "SUPERSEDED", "1": "ACTIVE"}
    # The superseded base keeps its package untouched.
    assert len(associations(project_with_base["base"]["id"])) == 3


def test_inherited_rows_reference_the_immediate_base(project_with_base: dict[str, Any]) -> None:
    project_id = project_with_base["project_id"]
    first = make_revision(project_id, "1").json()
    second = make_revision(project_id, "2", based_on_revision_id=first["id"]).json()
    assert second["inherited_document_count"] == 2
    rows = associations(second["id"])
    assert {str(row.inherited_from_revision_id) for row in rows} == {first["id"]}
    assert all(row.origin is DocumentOrigin.INHERITED for row in rows)


def test_failure_during_inheritance_leaves_nothing_behind(
    project_with_base: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id = project_with_base["project_id"]
    associations_before = association_count()

    def boom(*_args: object, **_kwargs: object) -> int:
        raise RuntimeError("inheritance failed")

    monkeypatch.setattr(revision_service, "copy_included_associations", boom)
    with pytest.raises(RuntimeError):
        make_revision(project_id, "1")

    assert revision_count(project_id) == 1
    assert association_count() == associations_before
    # The same identifier is still free, so no half-created row lingers.
    monkeypatch.undo()
    assert make_revision(project_id, "1").status_code == 201


def test_failure_during_activation_rolls_back_the_copy(
    project_with_base: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id = project_with_base["project_id"]
    associations_before = association_count()

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("activation failed")

    monkeypatch.setattr(revision_service.RevisionService, "_activate_locked", boom)
    with pytest.raises(RuntimeError):
        make_revision(project_id, "1", activate=True)

    assert revision_count(project_id) == 1
    assert association_count() == associations_before
    revisions = client.get(f"/api/projects/{project_id}/revisions").json()["items"]
    assert [(r["identifier"], r["status"]) for r in revisions] == [("0", "ACTIVE")]


def test_inheritance_is_a_snapshot(project_with_base: dict[str, Any]) -> None:
    project_id = project_with_base["project_id"]
    base_id = project_with_base["base"]["id"]
    docs = project_with_base["docs"]
    child = make_revision(project_id, "1").json()

    with get_session_factory()() as session:
        base_row = session.scalar(
            select(RevisionDocument).where(
                RevisionDocument.revision_id == uuid.UUID(base_id),
                RevisionDocument.document_id == docs["a"],
            )
        )
        base_row.status = RevisionDocumentStatus.REMOVED
        base_row.removed_at = datetime.now(UTC)
        base_row.description = "changed on base"
        session.commit()

    child_rows = {row.document_id: row for row in associations(child["id"])}
    assert child_rows[docs["a"]].status is RevisionDocumentStatus.INCLUDED
    assert child_rows[docs["a"]].description == "Main SLD"

    with get_session_factory()() as session:
        child_row = session.scalar(
            select(RevisionDocument).where(
                RevisionDocument.revision_id == uuid.UUID(child["id"]),
                RevisionDocument.document_id == docs["b"],
            )
        )
        child_row.notes = "changed on child"
        session.commit()

    base_rows = {row.document_id: row for row in associations(base_id)}
    assert base_rows[docs["b"]].notes is None


def test_project_lock_is_taken_before_the_base_revision_lock(
    project_with_base: dict[str, Any],
) -> None:
    statements: list[str] = []

    def record(_conn: Any, _cursor: Any, statement: str, *_rest: Any) -> None:
        if "FOR UPDATE" in statement:
            statements.append(statement)

    engine = get_engine()
    event.listen(engine, "before_cursor_execute", record)
    try:
        response = make_revision(project_with_base["project_id"], "1")
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert response.status_code == 201

    project_lock = next(i for i, s in enumerate(statements) if "FROM projects" in s)
    revision_lock = next(i for i, s in enumerate(statements) if "FROM project_revisions" in s)
    assert project_lock < revision_lock


def test_explicit_null_without_activation_takes_no_locks(project_with_base: dict[str, Any]) -> None:
    statements: list[str] = []

    def record(_conn: Any, _cursor: Any, statement: str, *_rest: Any) -> None:
        if "FOR UPDATE" in statement:
            statements.append(statement)

    engine = get_engine()
    event.listen(engine, "before_cursor_execute", record)
    try:
        response = make_revision(project_with_base["project_id"], "1", based_on_revision_id=None)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert response.status_code == 201
    assert statements == []


def test_revision_responses_expose_lineage_everywhere(project_with_base: dict[str, Any]) -> None:
    project_id = project_with_base["project_id"]
    base_id = project_with_base["base"]["id"]
    child = make_revision(project_id, "1").json()

    fetched = client.get(f"/api/projects/{project_id}/revisions/{child['id']}").json()
    assert fetched["based_on_revision_id"] == base_id
    assert fetched["based_on_identifier"] == "0"
    assert fetched["inherited_document_count"] is None

    items = client.get(f"/api/projects/{project_id}/revisions").json()["items"]
    listing = {r["identifier"]: r for r in items}
    assert listing["1"]["based_on_identifier"] == "0"
    assert listing["0"]["based_on_revision_id"] is None
    assert listing["1"]["inherited_document_count"] is None

    patched = client.patch(
        f"/api/projects/{project_id}/revisions/{child['id']}", json={"description": "x"}
    ).json()
    assert patched["based_on_identifier"] == "0"

    activated = client.post(f"/api/projects/{project_id}/revisions/{child['id']}/activate").json()
    assert activated["based_on_identifier"] == "0"


def test_openapi_documents_the_new_fields() -> None:
    schemas = app.openapi()["components"]["schemas"]
    create_props = schemas["RevisionCreate"]["properties"]
    assert {"based_on_revision_id", "carry_forward_documents"} <= set(create_props)
    response_props = schemas["RevisionResponse"]["properties"]
    assert {
        "based_on_revision_id",
        "based_on_identifier",
        "inherited_document_count",
    } <= set(response_props)
    assert "based_on_revision_id" not in schemas["RevisionUpdate"]["properties"]
