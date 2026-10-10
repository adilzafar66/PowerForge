"""Processing summary and retry routes. Integration cases need RUN_INTEGRATION=1.

The database fixture creates a database, upgrades it to head, and drops it. It does not
use the Compose development database.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.orm import sessionmaker

from documents_support import client, code, docs_url, make_project, make_revision, upload
from file_factory import PDF
from powerforge_document_model import DEFAULT_PROFILE, ProcessingRunStatus, RevisionDocumentStatus
from powerforge_document_processing.enqueue import get_processing_enqueue
from powerforge_document_processing.models import (
    DocumentProcessingRun,
    Project,
    ProjectRevision,
    RevisionDocument,
)
from powerforge_document_processing.storage.factory import get_object_storage
from powerforge_document_processing.storage.memory import InMemoryObjectStorage
from powerforge_project import ProjectStatus, RevisionStatus
from powerforge_shared.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = "database/alembic.ini"


class RecordingEnqueue:
    def __init__(self) -> None:
        self.calls: list[uuid.UUID] = []

    def enqueue_document_processing(self, run_id: uuid.UUID) -> None:
        self.calls.append(run_id)


def _integration_enabled() -> bool:
    return os.environ.get("RUN_INTEGRATION") == "1"


def _alembic(url: URL, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": url.render_as_string(hide_password=False)}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", ALEMBIC_INI, *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"alembic {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}"
    )


@pytest.fixture(scope="module")
def scratch_engine() -> Iterator[Engine]:
    if not _integration_enabled():
        pytest.skip("Set RUN_INTEGRATION=1 to run live database tests.")
    base = make_url(get_settings().database_url)
    name = f"powerforge_papi_{uuid.uuid4().hex[:8]}"
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    engine = None
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        url = base.set(database=name)
        _alembic(url, "upgrade", "head")
        engine = create_engine(url)
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def api(scratch_engine: Engine):
    from powerforge_api.db import get_session
    from powerforge_api.main import app

    factory = sessionmaker(bind=scratch_engine, expire_on_commit=False)
    enqueue = RecordingEnqueue()

    def session_override():
        bound = factory()
        try:
            yield bound
        finally:
            bound.close()

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_object_storage] = lambda: InMemoryObjectStorage()
    app.dependency_overrides[get_processing_enqueue] = lambda: enqueue
    try:
        yield factory, enqueue
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(get_object_storage, None)
        app.dependency_overrides.pop(get_processing_enqueue, None)


def _upload() -> tuple[str, str, str, str]:
    project_id = make_project()
    revision_id = make_revision(project_id, "0", activate=True).json()["id"]
    created = upload(project_id, revision_id, PDF, "sheet.pdf")
    assert created.status_code == 201, created.text
    body = created.json()
    return project_id, revision_id, body["id"], body["document"]["id"]


def _runs(factory, document_id: str) -> list[DocumentProcessingRun]:
    with factory() as session:
        rows = list(
            session.scalars(
                select(DocumentProcessingRun).where(
                    DocumentProcessingRun.document_id == uuid.UUID(document_id)
                )
            ).all()
        )
        session.expunge_all()
        return rows


def _latest(factory, document_id: str) -> DocumentProcessingRun:
    runs = _runs(factory, document_id)
    assert runs
    return max(runs, key=lambda run: run.attempt_count)


def _set_status(factory, document_id: str, **values: object) -> None:
    with factory() as session:
        run = session.scalar(
            select(DocumentProcessingRun)
            .where(DocumentProcessingRun.document_id == uuid.UUID(document_id))
            .order_by(DocumentProcessingRun.attempt_count.desc())
        )
        assert run is not None
        for key, value in values.items():
            setattr(run, key, value)
        session.commit()


def test_upload_list_and_detail_carry_the_current_run_only(api) -> None:
    factory, enqueue = api
    project_id, revision_id, association_id, document_id = _upload()
    uploaded = client.get(f"{docs_url(project_id, revision_id)}/{association_id}").json()
    assert uploaded["processing"]["status"] == "PENDING"
    assert uploaded["processing"]["attempt_count"] == 1
    assert uploaded["processing"]["pages_processed"] == 0
    assert uploaded["processing"]["pages_total"] is None
    assert uploaded["processing"]["error_code"] is None
    created = upload(project_id, revision_id, PDF, "other.pdf")
    assert created.status_code == 201, created.text
    assert created.json()["processing"]["status"] == "PENDING"

    _set_status(
        factory,
        document_id,
        status=ProcessingRunStatus.RUNNING,
        pages_processed=2,
        pages_total=5,
    )
    listed = client.get(docs_url(project_id, revision_id)).json()["items"]
    by_id = {item["id"]: item["processing"] for item in listed}
    assert by_id[association_id] == {
        "status": "RUNNING",
        "attempt_count": 1,
        "pages_processed": 2,
        "pages_total": 5,
        "error_code": None,
        "error_message": None,
    }
    detail = client.get(f"{docs_url(project_id, revision_id)}/{association_id}").json()
    assert detail["processing"] == by_id[association_id]
    assert "processor_version" not in detail["processing"]

    _set_status(
        factory,
        document_id,
        status=ProcessingRunStatus.FAILED,
        error_code="CORRUPT_PDF",
        error_message="Could not read the file",
    )
    failed = client.get(f"{docs_url(project_id, revision_id)}/{association_id}").json()
    assert failed["processing"]["status"] == "FAILED"
    assert failed["processing"]["error_code"] == "CORRUPT_PDF"
    assert failed["processing"]["error_message"] == "Could not read the file"

    calls_before = list(enqueue.calls)
    runs_before = len(_runs(factory, document_id))
    status = client.get(f"{docs_url(project_id, revision_id)}/{association_id}/processing")
    again = client.get(docs_url(project_id, revision_id))
    assert status.status_code == 200
    assert status.json()["processing"]["status"] == "FAILED"
    assert status.json()["processor_version"] == DEFAULT_PROFILE.processor_version
    assert status.json()["profile_version"] == DEFAULT_PROFILE.profile_version
    assert status.json()["profile_hash"] == DEFAULT_PROFILE.profile_hash
    assert enqueue.calls == calls_before
    assert len(_runs(factory, document_id)) == runs_before
    assert again.status_code == 200


def test_reads_do_not_create_a_run_when_none_exists(api) -> None:
    factory, enqueue = api
    project_id, revision_id, association_id, document_id = _upload()
    with factory() as session:
        session.execute(
            delete(DocumentProcessingRun).where(
                DocumentProcessingRun.document_id == uuid.UUID(document_id)
            )
        )
        session.commit()
    calls_before = list(enqueue.calls)

    listing = client.get(docs_url(project_id, revision_id))
    detail = client.get(f"{docs_url(project_id, revision_id)}/{association_id}")
    processing = client.get(f"{docs_url(project_id, revision_id)}/{association_id}/processing")

    assert listing.status_code == 200
    assert listing.json()["items"][0]["processing"] is None
    assert detail.json()["processing"] is None
    assert processing.status_code == 200
    assert processing.json() == {
        "processing": None,
        "processor_version": None,
        "profile_version": None,
        "profile_hash": None,
    }
    assert enqueue.calls == calls_before
    assert _runs(factory, document_id) == []


def test_upload_still_returns_when_ensure_fails(api, monkeypatch: pytest.MonkeyPatch) -> None:
    factory, _enqueue = api

    def boom(self, document_id: uuid.UUID) -> None:
        raise RuntimeError("ensure failed")

    monkeypatch.setattr(
        "powerforge_api.services.document_service.ProcessingService.ensure_document_processing",
        boom,
    )
    project_id = make_project()
    revision_id = make_revision(project_id, "0", activate=True).json()["id"]
    created = upload(project_id, revision_id, PDF, "sheet.pdf")
    assert created.status_code == 201, created.text
    assert created.json()["processing"] is None
    assert _runs(factory, created.json()["document"]["id"]) == []


def test_retry_is_only_for_a_failed_run(api) -> None:
    factory, enqueue = api
    project_id, revision_id, association_id, document_id = _upload()
    url = f"{docs_url(project_id, revision_id)}/{association_id}/processing/retry"

    pending = client.post(url)
    assert (pending.status_code, code(pending)) == (409, "processing_not_retryable")

    _set_status(factory, document_id, status=ProcessingRunStatus.RUNNING)
    running = client.post(url)
    assert (running.status_code, code(running)) == (409, "processing_not_retryable")

    _set_status(factory, document_id, status=ProcessingRunStatus.COMPLETED, pages_total=1)
    completed = client.post(url)
    assert (completed.status_code, code(completed)) == (409, "processing_not_retryable")
    assert len(enqueue.calls) == 1

    _set_status(
        factory,
        document_id,
        status=ProcessingRunStatus.FAILED,
        error_code="CORRUPT_PDF",
        error_message="Could not read the file",
    )
    retried = client.post(url)
    assert retried.status_code == 200, retried.text
    body = retried.json()
    assert body["processing"]["status"] == "PENDING"
    assert body["processing"]["attempt_count"] == 2
    assert body["processing"]["error_code"] is None
    assert body["processor_version"] == DEFAULT_PROFILE.processor_version
    assert len(_runs(factory, document_id)) == 2
    assert len(enqueue.calls) == 2
    listed = client.get(f"{docs_url(project_id, revision_id)}/{association_id}").json()
    assert listed["processing"]["status"] == "PENDING"
    assert listed["processing"]["error_message"] is None


def test_removed_and_superseded_and_archived_can_read_and_retry(api) -> None:
    factory, _enqueue = api
    project_id, revision_id, association_id, document_id = _upload()
    _set_status(
        factory,
        document_id,
        status=ProcessingRunStatus.FAILED,
        error_code="CORRUPT_PDF",
        error_message="Could not read the file",
    )
    with factory() as session:
        association = session.get(RevisionDocument, uuid.UUID(association_id))
        assert association is not None
        association.status = RevisionDocumentStatus.REMOVED
        association.removed_at = datetime.now(UTC)
        project = session.get(Project, uuid.UUID(project_id))
        assert project is not None
        project.status = ProjectStatus.ARCHIVED
        session.commit()

    processing_url = f"{docs_url(project_id, revision_id)}/{association_id}/processing"
    removed = client.get(processing_url)
    assert removed.status_code == 200
    assert removed.json()["processing"]["status"] == "FAILED"
    retried = client.post(f"{processing_url}/retry")
    assert retried.status_code == 200, retried.text
    assert retried.json()["processing"]["status"] == "PENDING"

    _set_status(
        factory,
        document_id,
        status=ProcessingRunStatus.FAILED,
        error_code="CORRUPT_PDF",
        error_message="Could not read the file",
    )
    with factory() as session:
        project = session.get(Project, uuid.UUID(project_id))
        assert project is not None
        project.status = ProjectStatus.ACTIVE
        revision = session.get(ProjectRevision, uuid.UUID(revision_id))
        assert revision is not None
        revision.status = RevisionStatus.SUPERSEDED
        session.commit()

    superseded = client.get(processing_url)
    assert superseded.status_code == 200
    assert superseded.json()["processing"]["status"] == "FAILED"
    retried_again = client.post(f"{processing_url}/retry")
    assert retried_again.status_code == 200, retried_again.text
    assert retried_again.json()["processing"]["status"] == "PENDING"
