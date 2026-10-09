"""Phase 3 schema constraints enforced by PostgreSQL. Requires RUN_INTEGRATION=1.

Each test runs inside a transaction that is rolled back, so no rows persist.
The configured database must already be migrated to 0005.
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


def make_document(conn: Connection, project_id: uuid.UUID) -> uuid.UUID:
    return conn.execute(
        text(
            "INSERT INTO documents (project_id, original_filename, storage_key, mime_type, "
            "file_extension, size_bytes, sha256) "
            "VALUES (:project_id, 'a.pdf', :storage_key, 'application/pdf', 'pdf', 10, :sha) "
            "RETURNING id"
        ),
        {
            "project_id": project_id,
            "storage_key": f"projects/{project_id}/documents/{uuid.uuid4()}/original.pdf",
            "sha": "b" * 64,
        },
    ).scalar_one()


PAGE_SQL = (
    "INSERT INTO document_pages (document_id, page_number, source_width, source_height, "
    "source_unit, rotation_degrees) "
    "VALUES (:document_id, :page_number, :source_width, :source_height, "
    "CAST(:source_unit AS source_unit), :rotation_degrees) RETURNING id"
)


def page_params(document_id: uuid.UUID, **overrides: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "document_id": document_id,
        "page_number": 1,
        "source_width": 612,
        "source_height": 792,
        "source_unit": "POINTS",
        "rotation_degrees": 0,
    }
    params.update(overrides)
    return params


def make_page(conn: Connection, document_id: uuid.UUID, **overrides: Any) -> uuid.UUID:
    return conn.execute(text(PAGE_SQL), page_params(document_id, **overrides)).scalar_one()


RUN_SQL = (
    "INSERT INTO document_processing_runs "
    "(document_id, processor_version, profile_version, profile_hash, status) "
    "VALUES (:document_id, :processor_version, :profile_version, :profile_hash, "
    "CAST(:status AS processing_run_status)) RETURNING id"
)


def run_params(document_id: uuid.UUID, **overrides: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "document_id": document_id,
        "processor_version": "1",
        "profile_version": "engineering-default-v1",
        "profile_hash": "abc",
        "status": "PENDING",
    }
    params.update(overrides)
    return params


def make_run(conn: Connection, document_id: uuid.UUID, **overrides: Any) -> uuid.UUID:
    return conn.execute(text(RUN_SQL), run_params(document_id, **overrides)).scalar_one()


ARTIFACT_SQL = (
    "INSERT INTO page_artifacts (document_page_id, processing_run_id, artifact_type, "
    "storage_key, mime_type, size_bytes, sha256) "
    "VALUES (:document_page_id, :processing_run_id, CAST(:artifact_type AS page_artifact_type), "
    ":storage_key, 'image/png', 10, :sha) RETURNING id"
)


def artifact_params(page_id: uuid.UUID, run_id: uuid.UUID, **overrides: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "document_page_id": page_id,
        "processing_run_id": run_id,
        "artifact_type": "ANALYSIS_IMAGE",
        "storage_key": f"projects/p/documents/d/processing/{run_id}/pages/0001/analysis.png",
        "sha": "c" * 64,
    }
    params.update(overrides)
    return params


def test_duplicate_page_number_rejected(conn: Connection) -> None:
    document_id = make_document(conn, make_project(conn))
    make_page(conn, document_id)
    violates(
        conn,
        "uq_document_pages_document_id_page_number",
        PAGE_SQL,
        page_params(document_id),
    )


def test_page_number_zero_rejected(conn: Connection) -> None:
    document_id = make_document(conn, make_project(conn))
    violates(
        conn,
        "ck_document_pages_page_number_positive",
        PAGE_SQL,
        page_params(document_id, page_number=0),
    )


def test_rotation_45_rejected(conn: Connection) -> None:
    document_id = make_document(conn, make_project(conn))
    violates(
        conn,
        "ck_document_pages_rotation_degrees",
        PAGE_SQL,
        page_params(document_id, rotation_degrees=45),
    )


def test_two_failed_runs_for_the_same_target_insert(conn: Connection) -> None:
    document_id = make_document(conn, make_project(conn))
    first = make_run(conn, document_id, status="FAILED")
    second = make_run(conn, document_id, status="FAILED")
    assert first != second


@pytest.mark.parametrize("status", ["PENDING", "RUNNING", "COMPLETED"])
def test_second_live_run_for_the_same_target_is_rejected(conn: Connection, status: str) -> None:
    document_id = make_document(conn, make_project(conn))
    make_run(conn, document_id, status=status)
    violates(
        conn,
        "uq_document_processing_runs_one_live",
        RUN_SQL,
        run_params(document_id, status=status),
    )


def test_failed_plus_one_pending_is_allowed(conn: Connection) -> None:
    document_id = make_document(conn, make_project(conn))
    failed = make_run(conn, document_id, status="FAILED")
    pending = make_run(conn, document_id, status="PENDING")
    assert failed != pending


def test_duplicate_artifact_type_rejected(conn: Connection) -> None:
    document_id = make_document(conn, make_project(conn))
    page_id = make_page(conn, document_id)
    run_id = make_run(conn, document_id, status="FAILED")
    conn.execute(text(ARTIFACT_SQL), artifact_params(page_id, run_id))
    violates(
        conn,
        "uq_page_artifacts_run_page_type",
        ARTIFACT_SQL,
        artifact_params(
            page_id,
            run_id,
            storage_key=f"projects/p/documents/d/processing/{run_id}/pages/0001/other.png",
        ),
    )


def test_duplicate_storage_key_rejected(conn: Connection) -> None:
    document_id = make_document(conn, make_project(conn))
    page_id = make_page(conn, document_id)
    run_id = make_run(conn, document_id, status="FAILED")
    params = artifact_params(page_id, run_id)
    conn.execute(text(ARTIFACT_SQL), params)
    violates(
        conn,
        "uq_page_artifacts_storage_key",
        ARTIFACT_SQL,
        artifact_params(
            page_id,
            run_id,
            artifact_type="THUMBNAIL",
            storage_key=params["storage_key"],
        ),
    )
