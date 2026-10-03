"""Phase 2 schema constraints enforced by PostgreSQL. Requires RUN_INTEGRATION=1.

Each test runs inside a transaction that is rolled back, so no rows persist.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.exc import IntegrityError

from powerforge_shared.config import get_settings

pytestmark = pytest.mark.integration


@pytest.fixture
def conn() -> Iterator[Connection]:
    if os.environ.get("RUN_INTEGRATION") != "1":
        pytest.skip("Set RUN_INTEGRATION=1 to run live database tests.")
    engine = create_engine(get_settings().database_url)
    connection = engine.connect()
    transaction = connection.begin()
    try:
        yield connection
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()


def constraint_of(exc: IntegrityError) -> str | None:
    return getattr(getattr(exc.orig, "diag", None), "constraint_name", None)


def violates(conn: Connection, constraint: str, sql: str, params: dict[str, Any]) -> None:
    with pytest.raises(IntegrityError) as caught, conn.begin_nested():
        conn.execute(text(sql), params)
    assert constraint_of(caught.value) == constraint


def make_project(conn: Connection) -> uuid.UUID:
    return conn.execute(
        text(
            "INSERT INTO projects (project_number, project_name) "
            "VALUES (:number, 'Constraint test') RETURNING id"
        ),
        {"number": f"CT-{uuid.uuid4().hex[:10]}"},
    ).scalar_one()


def make_revision(
    conn: Connection,
    project_id: uuid.UUID,
    identifier: str = "0",
    based_on: uuid.UUID | None = None,
) -> uuid.UUID:
    return conn.execute(
        text(
            "INSERT INTO project_revisions (project_id, identifier, based_on_revision_id) "
            "VALUES (:project_id, :identifier, :based_on) RETURNING id"
        ),
        {"project_id": project_id, "identifier": identifier, "based_on": based_on},
    ).scalar_one()


DOCUMENT_SQL = (
    "INSERT INTO documents (project_id, original_filename, storage_key, mime_type, "
    "file_extension, size_bytes, sha256) "
    "VALUES (:project_id, 'a.pdf', :storage_key, 'application/pdf', 'pdf', :size, :sha) "
    "RETURNING id"
)


def document_params(project_id: uuid.UUID, **overrides: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "project_id": project_id,
        "storage_key": f"projects/{project_id}/documents/{uuid.uuid4()}/original.pdf",
        "size": 10,
        "sha": "a" * 64,
    }
    params.update(overrides)
    return params


def make_document(conn: Connection, project_id: uuid.UUID, **overrides: Any) -> uuid.UUID:
    return conn.execute(text(DOCUMENT_SQL), document_params(project_id, **overrides)).scalar_one()


REVISION_DOCUMENT_SQL = (
    "INSERT INTO revision_documents (project_id, revision_id, document_id, origin, "
    "inherited_from_revision_id, status, removed_at) "
    "VALUES (:project_id, :revision_id, :document_id, "
    "CAST(:origin AS document_origin), :inherited_from, "
    "CAST(:status AS revision_document_status), :removed_at) RETURNING id"
)


def revision_document_params(
    project_id: uuid.UUID, revision_id: uuid.UUID, document_id: uuid.UUID, **overrides: Any
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "project_id": project_id,
        "revision_id": revision_id,
        "document_id": document_id,
        "origin": "UPLOADED",
        "inherited_from": None,
        "status": "INCLUDED",
        "removed_at": None,
    }
    params.update(overrides)
    return params


def link(
    conn: Connection,
    project_id: uuid.UUID,
    revision_id: uuid.UUID,
    document_id: uuid.UUID,
    **overrides: Any,
) -> uuid.UUID:
    params = revision_document_params(project_id, revision_id, document_id, **overrides)
    return conn.execute(text(REVISION_DOCUMENT_SQL), params).scalar_one()


class TestRevisionLineage:
    def test_null_and_same_project_lineage_allowed(self, conn: Connection) -> None:
        project_id = make_project(conn)
        base = make_revision(conn, project_id, "0")
        child = make_revision(conn, project_id, "1", based_on=base)
        stored = conn.execute(
            text("SELECT based_on_revision_id FROM project_revisions WHERE id = :id"),
            {"id": child},
        ).scalar_one()
        assert stored == base

    def test_cross_project_lineage_rejected(self, conn: Connection) -> None:
        project_a = make_project(conn)
        project_b = make_project(conn)
        foreign_revision = make_revision(conn, project_b, "0")
        violates(
            conn,
            "fk_project_revisions_based_on",
            "INSERT INTO project_revisions (project_id, identifier, based_on_revision_id) "
            "VALUES (:project_id, '1', :based_on)",
            {"project_id": project_a, "based_on": foreign_revision},
        )

    def test_self_lineage_rejected(self, conn: Connection) -> None:
        project_id = make_project(conn)
        revision_id = uuid.uuid4()
        violates(
            conn,
            "ck_project_revisions_based_on_not_self",
            "INSERT INTO project_revisions (id, project_id, identifier, based_on_revision_id) "
            "VALUES (:id, :project_id, '0', :id)",
            {"id": revision_id, "project_id": project_id},
        )

    def test_lineage_parent_cannot_be_deleted(self, conn: Connection) -> None:
        project_id = make_project(conn)
        base = make_revision(conn, project_id, "0")
        make_revision(conn, project_id, "1", based_on=base)
        violates(
            conn,
            "fk_project_revisions_based_on",
            "DELETE FROM project_revisions WHERE id = :id",
            {"id": base},
        )


class TestDocuments:
    def test_duplicate_sha256_allowed_in_same_project(self, conn: Connection) -> None:
        project_id = make_project(conn)
        first = make_document(conn, project_id)
        second = make_document(conn, project_id)
        assert first != second

    @pytest.mark.parametrize("size", [0, -1])
    def test_non_positive_size_rejected(self, conn: Connection, size: int) -> None:
        project_id = make_project(conn)
        violates(
            conn,
            "ck_documents_size_positive",
            DOCUMENT_SQL,
            document_params(project_id, size=size),
        )

    def test_large_size_accepted(self, conn: Connection) -> None:
        project_id = make_project(conn)
        make_document(conn, project_id, size=5 * 1024**3)

    def test_duplicate_storage_key_rejected(self, conn: Connection) -> None:
        project_id = make_project(conn)
        key = f"projects/{project_id}/documents/{uuid.uuid4()}/original.pdf"
        make_document(conn, project_id, storage_key=key)
        violates(
            conn,
            "uq_documents_storage_key",
            DOCUMENT_SQL,
            document_params(project_id, storage_key=key),
        )

    def test_unknown_project_rejected(self, conn: Connection) -> None:
        violates(
            conn,
            "fk_documents_project_id",
            DOCUMENT_SQL,
            document_params(uuid.uuid4()),
        )

    def test_project_with_documents_cannot_be_deleted(self, conn: Connection) -> None:
        project_id = make_project(conn)
        make_document(conn, project_id)
        violates(
            conn,
            "fk_documents_project_id",
            "DELETE FROM projects WHERE id = :id",
            {"id": project_id},
        )


class TestRevisionDocuments:
    def test_defaults_applied(self, conn: Connection) -> None:
        project_id = make_project(conn)
        revision_id = make_revision(conn, project_id)
        document_id = make_document(conn, project_id)
        row = conn.execute(
            text(
                "INSERT INTO revision_documents (project_id, revision_id, document_id, origin) "
                "VALUES (:p, :r, :d, 'UPLOADED') "
                "RETURNING status::text, document_type::text, added_at"
            ),
            {"p": project_id, "r": revision_id, "d": document_id},
        ).one()
        assert row.status == "INCLUDED"
        assert row.document_type == "UNKNOWN"
        assert row.added_at is not None

    def test_origin_has_no_default(self, conn: Connection) -> None:
        project_id = make_project(conn)
        revision_id = make_revision(conn, project_id)
        document_id = make_document(conn, project_id)
        with pytest.raises(IntegrityError) as caught, conn.begin_nested():
            conn.execute(
                text(
                    "INSERT INTO revision_documents (project_id, revision_id, document_id) "
                    "VALUES (:p, :r, :d)"
                ),
                {"p": project_id, "r": revision_id, "d": document_id},
            )
        assert caught.value.orig.diag.column_name == "origin"

    def test_inherited_association_allowed(self, conn: Connection) -> None:
        project_id = make_project(conn)
        base = make_revision(conn, project_id, "0")
        child = make_revision(conn, project_id, "1", based_on=base)
        document_id = make_document(conn, project_id)
        link(conn, project_id, base, document_id)
        link(
            conn,
            project_id,
            child,
            document_id,
            origin="INHERITED",
            inherited_from=base,
        )

    def test_cross_project_revision_rejected(self, conn: Connection) -> None:
        project_a = make_project(conn)
        project_b = make_project(conn)
        revision_b = make_revision(conn, project_b)
        document_a = make_document(conn, project_a)
        violates(
            conn,
            "fk_revision_documents_revision",
            REVISION_DOCUMENT_SQL,
            revision_document_params(project_a, revision_b, document_a),
        )

    def test_cross_project_document_rejected(self, conn: Connection) -> None:
        project_a = make_project(conn)
        project_b = make_project(conn)
        revision_a = make_revision(conn, project_a)
        document_b = make_document(conn, project_b)
        violates(
            conn,
            "fk_revision_documents_document",
            REVISION_DOCUMENT_SQL,
            revision_document_params(project_a, revision_a, document_b),
        )

    def test_cross_project_inherited_from_rejected(self, conn: Connection) -> None:
        project_a = make_project(conn)
        project_b = make_project(conn)
        revision_a = make_revision(conn, project_a)
        revision_b = make_revision(conn, project_b)
        document_a = make_document(conn, project_a)
        violates(
            conn,
            "fk_revision_documents_inherited_from",
            REVISION_DOCUMENT_SQL,
            revision_document_params(
                project_a,
                revision_a,
                document_a,
                origin="INHERITED",
                inherited_from=revision_b,
            ),
        )

    def test_inherited_without_source_rejected(self, conn: Connection) -> None:
        project_id = make_project(conn)
        revision_id = make_revision(conn, project_id)
        document_id = make_document(conn, project_id)
        violates(
            conn,
            "ck_revision_documents_origin_inherited_from",
            REVISION_DOCUMENT_SQL,
            revision_document_params(project_id, revision_id, document_id, origin="INHERITED"),
        )

    def test_uploaded_with_source_rejected(self, conn: Connection) -> None:
        project_id = make_project(conn)
        base = make_revision(conn, project_id, "0")
        child = make_revision(conn, project_id, "1", based_on=base)
        document_id = make_document(conn, project_id)
        violates(
            conn,
            "ck_revision_documents_origin_inherited_from",
            REVISION_DOCUMENT_SQL,
            revision_document_params(project_id, child, document_id, inherited_from=base),
        )

    def test_inherited_from_self_rejected(self, conn: Connection) -> None:
        project_id = make_project(conn)
        revision_id = make_revision(conn, project_id)
        document_id = make_document(conn, project_id)
        violates(
            conn,
            "ck_revision_documents_inherited_not_self",
            REVISION_DOCUMENT_SQL,
            revision_document_params(
                project_id,
                revision_id,
                document_id,
                origin="INHERITED",
                inherited_from=revision_id,
            ),
        )

    def test_removed_requires_removed_at(self, conn: Connection) -> None:
        project_id = make_project(conn)
        revision_id = make_revision(conn, project_id)
        document_id = make_document(conn, project_id)
        violates(
            conn,
            "ck_revision_documents_status_removed_at",
            REVISION_DOCUMENT_SQL,
            revision_document_params(project_id, revision_id, document_id, status="REMOVED"),
        )

    def test_included_forbids_removed_at(self, conn: Connection) -> None:
        project_id = make_project(conn)
        revision_id = make_revision(conn, project_id)
        document_id = make_document(conn, project_id)
        violates(
            conn,
            "ck_revision_documents_status_removed_at",
            REVISION_DOCUMENT_SQL,
            revision_document_params(
                project_id,
                revision_id,
                document_id,
                removed_at="2026-01-01T00:00:00+00:00",
            ),
        )

    def test_removed_with_removed_at_allowed(self, conn: Connection) -> None:
        project_id = make_project(conn)
        revision_id = make_revision(conn, project_id)
        document_id = make_document(conn, project_id)
        link(
            conn,
            project_id,
            revision_id,
            document_id,
            status="REMOVED",
            removed_at="2026-01-01T00:00:00+00:00",
        )

    def test_duplicate_revision_document_rejected(self, conn: Connection) -> None:
        project_id = make_project(conn)
        revision_id = make_revision(conn, project_id)
        document_id = make_document(conn, project_id)
        link(conn, project_id, revision_id, document_id)
        violates(
            conn,
            "uq_revision_documents_revision_id_document_id",
            REVISION_DOCUMENT_SQL,
            revision_document_params(project_id, revision_id, document_id),
        )

    def test_same_document_in_two_revisions_allowed(self, conn: Connection) -> None:
        project_id = make_project(conn)
        first = make_revision(conn, project_id, "0")
        second = make_revision(conn, project_id, "1")
        document_id = make_document(conn, project_id)
        link(conn, project_id, first, document_id)
        link(conn, project_id, second, document_id)

    def test_referenced_revision_cannot_be_deleted(self, conn: Connection) -> None:
        project_id = make_project(conn)
        revision_id = make_revision(conn, project_id)
        document_id = make_document(conn, project_id)
        link(conn, project_id, revision_id, document_id)
        violates(
            conn,
            "fk_revision_documents_revision",
            "DELETE FROM project_revisions WHERE id = :id",
            {"id": revision_id},
        )

    def test_referenced_document_cannot_be_deleted(self, conn: Connection) -> None:
        project_id = make_project(conn)
        revision_id = make_revision(conn, project_id)
        document_id = make_document(conn, project_id)
        link(conn, project_id, revision_id, document_id)
        violates(
            conn,
            "fk_revision_documents_document",
            "DELETE FROM documents WHERE id = :id",
            {"id": document_id},
        )

    def test_inheritance_source_cannot_be_deleted(self, conn: Connection) -> None:
        project_id = make_project(conn)
        base = make_revision(conn, project_id, "0")
        child = make_revision(conn, project_id, "1", based_on=base)
        other = make_revision(conn, project_id, "2")
        document_id = make_document(conn, project_id)
        link(conn, project_id, child, document_id, origin="INHERITED", inherited_from=other)
        violates(
            conn,
            "fk_revision_documents_inherited_from",
            "DELETE FROM project_revisions WHERE id = :id",
            {"id": other},
        )

    def test_invalid_enum_label_rejected_before_constraints(self, conn: Connection) -> None:
        project_id = make_project(conn)
        revision_id = make_revision(conn, project_id)
        document_id = make_document(conn, project_id)
        with pytest.raises(Exception) as caught, conn.begin_nested():
            conn.execute(
                text(REVISION_DOCUMENT_SQL),
                revision_document_params(
                    project_id, revision_id, document_id, origin="NOT_AN_ORIGIN"
                ),
            )
        assert "document_origin" in str(caught.value)
