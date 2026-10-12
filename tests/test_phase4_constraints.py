"""Phase 4 schema constraints enforced by PostgreSQL. Requires RUN_INTEGRATION=1.

Each test runs inside a transaction that is rolled back, so no rows persist.
The configured database must already be migrated to 0006.
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
        {"number": f"C4-{uuid.uuid4().hex[:10]}"},
    ).scalar_one()


def make_revision(conn: Connection, project_id: uuid.UUID) -> uuid.UUID:
    return conn.execute(
        text(
            "INSERT INTO project_revisions (project_id, identifier) "
            "VALUES (:project_id, :identifier) RETURNING id"
        ),
        {"project_id": project_id, "identifier": uuid.uuid4().hex[:8]},
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


def make_association(
    conn: Connection,
    project_id: uuid.UUID,
    revision_id: uuid.UUID,
    document_id: uuid.UUID,
) -> uuid.UUID:
    return conn.execute(
        text(
            "INSERT INTO revision_documents (project_id, revision_id, document_id, origin) "
            "VALUES (:project_id, :revision_id, :document_id, 'UPLOADED'::document_origin) "
            "RETURNING id"
        ),
        {
            "project_id": project_id,
            "revision_id": revision_id,
            "document_id": document_id,
        },
    ).scalar_one()


def make_page(conn: Connection, document_id: uuid.UUID) -> uuid.UUID:
    return conn.execute(
        text(
            "INSERT INTO document_pages (document_id, page_number, source_width, source_height, "
            "source_unit, rotation_degrees) "
            "VALUES (:document_id, 1, 612, 792, 'POINTS'::source_unit, 0) RETURNING id"
        ),
        {"document_id": document_id},
    ).scalar_one()


def make_processing_run(conn: Connection, document_id: uuid.UUID) -> uuid.UUID:
    return conn.execute(
        text(
            "INSERT INTO document_processing_runs "
            "(document_id, processor_version, profile_version, profile_hash, status) "
            "VALUES (:document_id, '1', 'engineering-default-v1', 'abc', "
            "'COMPLETED'::processing_run_status) RETURNING id"
        ),
        {"document_id": document_id},
    ).scalar_one()


CLASSIFICATION_RUN_SQL = (
    "INSERT INTO document_classification_runs ("
    "document_id, processing_run_id, classifier_version, taxonomy_version, prompt_version, "
    "sampling_profile_version, sampling_profile_hash, classifier_identity_hash, provider, "
    "model, status) VALUES ("
    ":document_id, :processing_run_id, '1', 'document-taxonomy-v2', 'document_classifier_v1', "
    "'classification-default-v1', 'profile', :classifier_identity_hash, 'fake', 'gpt-6-luna', "
    "CAST(:status AS classification_run_status)) RETURNING id"
)


def classification_run_params(
    document_id: uuid.UUID,
    processing_run_id: uuid.UUID,
    **overrides: Any,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "document_id": document_id,
        "processing_run_id": processing_run_id,
        "classifier_identity_hash": "identity-1",
        "status": "PENDING",
    }
    params.update(overrides)
    return params


def make_classification_run(
    conn: Connection,
    document_id: uuid.UUID,
    processing_run_id: uuid.UUID,
    **overrides: Any,
) -> uuid.UUID:
    return conn.execute(
        text(CLASSIFICATION_RUN_SQL),
        classification_run_params(document_id, processing_run_id, **overrides),
    ).scalar_one()


PREDICTION_SQL = (
    "INSERT INTO classification_predictions ("
    "classification_run_id, document_id, scope, document_page_id, predicted_type, "
    "confidence_score, confidence_band) VALUES ("
    ":classification_run_id, :document_id, CAST(:scope AS classification_scope), "
    ":document_page_id, CAST(:predicted_type AS document_classification), 0.90, "
    "'HIGH'::confidence_band) RETURNING id"
)


def prediction_params(
    run_id: uuid.UUID,
    document_id: uuid.UUID,
    **overrides: Any,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "classification_run_id": run_id,
        "document_id": document_id,
        "scope": "DOCUMENT",
        "document_page_id": None,
        "predicted_type": "OTHER",
    }
    params.update(overrides)
    return params


def make_prediction(
    conn: Connection,
    run_id: uuid.UUID,
    document_id: uuid.UUID,
    **overrides: Any,
) -> uuid.UUID:
    return conn.execute(
        text(PREDICTION_SQL),
        prediction_params(run_id, document_id, **overrides),
    ).scalar_one()


def test_two_failed_runs_for_the_same_identity_insert(conn: Connection) -> None:
    document_id = make_document(conn, make_project(conn))
    processing_run_id = make_processing_run(conn, document_id)
    first = make_classification_run(conn, document_id, processing_run_id, status="FAILED")
    second = make_classification_run(conn, document_id, processing_run_id, status="FAILED")
    assert first != second


def test_two_completed_runs_for_the_same_identity_insert(conn: Connection) -> None:
    document_id = make_document(conn, make_project(conn))
    processing_run_id = make_processing_run(conn, document_id)
    first = make_classification_run(conn, document_id, processing_run_id, status="COMPLETED")
    second = make_classification_run(conn, document_id, processing_run_id, status="COMPLETED")
    assert first != second


@pytest.mark.parametrize("status", ["PENDING", "RUNNING"])
def test_second_live_run_for_the_same_identity_is_rejected(conn: Connection, status: str) -> None:
    document_id = make_document(conn, make_project(conn))
    processing_run_id = make_processing_run(conn, document_id)
    make_classification_run(conn, document_id, processing_run_id, status=status)
    violates(
        conn,
        "uq_document_classification_runs_one_live",
        CLASSIFICATION_RUN_SQL,
        classification_run_params(document_id, processing_run_id, status=status),
    )


def test_failed_plus_one_pending_is_allowed(conn: Connection) -> None:
    document_id = make_document(conn, make_project(conn))
    processing_run_id = make_processing_run(conn, document_id)
    failed = make_classification_run(conn, document_id, processing_run_id, status="FAILED")
    pending = make_classification_run(conn, document_id, processing_run_id, status="PENDING")
    assert failed != pending


def test_completed_plus_one_pending_is_allowed(conn: Connection) -> None:
    document_id = make_document(conn, make_project(conn))
    processing_run_id = make_processing_run(conn, document_id)
    completed = make_classification_run(conn, document_id, processing_run_id, status="COMPLETED")
    pending = make_classification_run(conn, document_id, processing_run_id, status="PENDING")
    assert completed != pending


def test_document_prediction_requires_null_page(conn: Connection) -> None:
    document_id = make_document(conn, make_project(conn))
    page_id = make_page(conn, document_id)
    run_id = make_classification_run(conn, document_id, make_processing_run(conn, document_id))
    violates(
        conn,
        "ck_classification_predictions_scope_page",
        PREDICTION_SQL,
        prediction_params(run_id, document_id, document_page_id=page_id),
    )


def test_page_prediction_requires_a_page(conn: Connection) -> None:
    document_id = make_document(conn, make_project(conn))
    run_id = make_classification_run(conn, document_id, make_processing_run(conn, document_id))
    violates(
        conn,
        "ck_classification_predictions_scope_page",
        PREDICTION_SQL,
        prediction_params(run_id, document_id, scope="PAGE"),
    )


def test_page_prediction_mixed_document_rejected(conn: Connection) -> None:
    document_id = make_document(conn, make_project(conn))
    page_id = make_page(conn, document_id)
    run_id = make_classification_run(conn, document_id, make_processing_run(conn, document_id))
    violates(
        conn,
        "ck_classification_predictions_page_not_mixed",
        PREDICTION_SQL,
        prediction_params(
            run_id,
            document_id,
            scope="PAGE",
            document_page_id=page_id,
            predicted_type="MIXED_DOCUMENT",
        ),
    )


def test_two_document_predictions_on_one_run_rejected(conn: Connection) -> None:
    document_id = make_document(conn, make_project(conn))
    run_id = make_classification_run(conn, document_id, make_processing_run(conn, document_id))
    make_prediction(conn, run_id, document_id)
    violates(
        conn,
        "uq_classification_predictions_one_document",
        PREDICTION_SQL,
        prediction_params(run_id, document_id, predicted_type="UNKNOWN"),
    )


def test_two_page_predictions_for_the_same_page_rejected(conn: Connection) -> None:
    document_id = make_document(conn, make_project(conn))
    page_id = make_page(conn, document_id)
    run_id = make_classification_run(conn, document_id, make_processing_run(conn, document_id))
    make_prediction(
        conn,
        run_id,
        document_id,
        scope="PAGE",
        document_page_id=page_id,
    )
    violates(
        conn,
        "uq_classification_predictions_run_page",
        PREDICTION_SQL,
        prediction_params(
            run_id,
            document_id,
            scope="PAGE",
            document_page_id=page_id,
            predicted_type="UNKNOWN",
        ),
    )


def test_run_document_must_match_the_processing_run(conn: Connection) -> None:
    project_id = make_project(conn)
    owner = make_document(conn, project_id)
    other = make_document(conn, project_id)
    processing_run_id = make_processing_run(conn, owner)
    violates(
        conn,
        "fk_document_classification_runs_processing_run",
        CLASSIFICATION_RUN_SQL,
        classification_run_params(other, processing_run_id),
    )


def test_page_from_another_document_rejected(conn: Connection) -> None:
    project_id = make_project(conn)
    owner = make_document(conn, project_id)
    other = make_document(conn, project_id)
    other_page = make_page(conn, other)
    run_id = make_classification_run(conn, owner, make_processing_run(conn, owner))
    violates(
        conn,
        "fk_classification_predictions_page",
        PREDICTION_SQL,
        prediction_params(
            run_id,
            owner,
            scope="PAGE",
            document_page_id=other_page,
        ),
    )


def test_accepted_prediction_from_another_document_rejected(conn: Connection) -> None:
    project_id = make_project(conn)
    revision_id = make_revision(conn, project_id)
    owner = make_document(conn, project_id)
    other = make_document(conn, project_id)
    association_id = make_association(conn, project_id, revision_id, owner)
    other_run = make_classification_run(conn, other, make_processing_run(conn, other))
    other_prediction = make_prediction(conn, other_run, other)
    violates(
        conn,
        "fk_revision_documents_accepted_prediction",
        "UPDATE revision_documents SET accepted_classification_prediction_id = :prediction_id "
        "WHERE id = :id",
        {"prediction_id": other_prediction, "id": association_id},
    )


def test_ai_calls_have_no_cost_columns(conn: Connection) -> None:
    rows = conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'classification_ai_calls'"
        )
    ).scalars()
    names = set(rows)
    assert "estimated_cost_usd" not in names
    assert "pricing_version" not in names
