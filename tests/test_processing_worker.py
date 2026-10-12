"""Worker queue, upload enqueue, and backfill. Integration cases need RUN_INTEGRATION=1.

The database fixture creates a database, upgrades it to head, and drops it. It does not
use the Compose development database.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from document_worker.celery_app import (
    celery_app as document_celery_app,
)
from document_worker.celery_app import (
    execute_processing_run,
    mark_processing_timeout,
)
from file_factory import PDF, png_bytes
from powerforge_document_model import (
    DEFAULT_PROFILE,
    ProcessingErrorCode,
    ProcessingRunStatus,
)
from powerforge_document_processing.backfill import backfill_documents, main
from powerforge_document_processing.enqueue import (
    PROCESS_RUN_QUEUE,
    PROCESS_RUN_TASK,
    CeleryProcessingEnqueue,
    get_processing_enqueue,
)
from powerforge_document_processing.models import (
    Document,
    DocumentPage,
    DocumentProcessingRun,
    PageArtifact,
    Project,
)
from powerforge_document_processing.storage.memory import InMemoryObjectStorage
from powerforge_shared.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = "database/alembic.ini"


class RecordingEnqueue:
    def __init__(self) -> None:
        self.calls: list[uuid.UUID] = []

    def enqueue_document_processing(self, run_id: uuid.UUID) -> None:
        self.calls.append(run_id)


class RaisingEnqueue:
    def enqueue_document_processing(self, run_id: uuid.UUID) -> None:
        raise RuntimeError("broker down")


def test_processing_task_is_only_registered_on_the_document_worker() -> None:
    assert "document_worker.heartbeat" in document_celery_app.tasks
    assert PROCESS_RUN_TASK in document_celery_app.tasks
    task = document_celery_app.tasks[PROCESS_RUN_TASK]
    assert task.__module__ == "document_worker.celery_app"
    # Importing every app in this process makes Celery's registries share names.
    # A worker process loads only its own app, which is what this check runs.
    script = """
import json
from extraction_worker.celery_app import celery_app as extraction_app
from validation_worker.celery_app import celery_app as validation_app
print(json.dumps({
    "extraction": PROCESS in extraction_app.tasks,
    "validation": PROCESS in validation_app.tasks,
}))
""".replace("PROCESS", repr(PROCESS_RUN_TASK))
    pythonpath = os.pathsep.join(
        [
            str(REPO_ROOT / "services/extraction-worker/src"),
            str(REPO_ROOT / "services/validation-worker/src"),
            str(REPO_ROOT / "packages/shared/src"),
            str(REPO_ROOT / "packages/document-classification/src"),
        ]
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": pythonpath},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == '{"extraction": false, "validation": false}'


def test_enqueue_publishes_to_the_document_processing_queue() -> None:
    calls: dict[str, object] = {}

    class _FakeApp:
        def send_task(self, name: str, args: list[str], queue: str) -> None:
            calls["name"] = name
            calls["args"] = args
            calls["queue"] = queue

    enqueue = CeleryProcessingEnqueue()
    enqueue._app = _FakeApp()  # type: ignore[assignment]
    run_id = uuid.uuid4()
    enqueue.enqueue_document_processing(run_id)
    assert calls == {
        "name": PROCESS_RUN_TASK,
        "args": [str(run_id)],
        "queue": PROCESS_RUN_QUEUE,
    }


def test_compose_binds_only_the_document_worker_to_its_queue() -> None:
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    dockerfile = (REPO_ROOT / "services" / "worker.Dockerfile").read_text(encoding="utf-8")
    start = compose.index("  document-worker:")
    extraction = compose.index("  extraction-worker:")
    validation = compose.index("  validation-worker:")
    block = compose[start:extraction]
    extract = compose[extraction:validation]
    assert "CELERY_QUEUE: document_processing" in block
    assert "S3_ENDPOINT_URL: http://minio:9000" in block
    assert "S3_ACCESS_KEY: powerforge" in block
    assert "S3_SECRET_KEY: powerforge_minio" in block
    assert "S3_BUCKET: powerforge" in block
    assert "S3_PUBLIC_ENDPOINT_URL: http://localhost:9000" in block
    assert "OPENAI_API_KEY" not in block
    assert "CELERY_QUEUE: document_classification" in extract
    assert "DATABASE_URL:" in extract
    assert "S3_ENDPOINT_URL: http://minio:9000" in extract
    assert "AI_CLASSIFICATION_ENABLED:" in extract
    assert "AI_PROVIDER: fake" in extract
    assert "OPENAI_API_KEY: ${OPENAI_API_KEY:-}" in extract
    assert compose.count("OPENAI_API_KEY: ${OPENAI_API_KEY:-}") == 1
    assert "CELERY_QUEUE" not in compose[validation:]
    assert "OPENAI_API_KEY" not in compose[validation:]
    assert "ARG CELERY_QUEUE=celery" in dockerfile
    assert "--concurrency=1" in dockerfile
    assert "-Q ${CELERY_QUEUE}" in dockerfile
    document_image, extraction_image = dockerfile.split(
        'elif [ "$WORKER_PACKAGE" = "extraction-worker" ]', 1
    )
    extraction_image = extraction_image.split("else", 1)[0]
    assert "openai" not in document_image
    assert "/app/packages/document-classification" in document_image
    assert '"openai>=2"' in extraction_image
    assert "/app/packages/document-classification" in extraction_image


def test_api_lifespan_does_not_backfill() -> None:
    source = (REPO_ROOT / "services" / "api" / "src" / "powerforge_api" / "main.py").read_text(
        encoding="utf-8"
    )
    assert "backfill" not in source
    assert "ensure_document_processing" not in source


def test_backfill_limit_is_required_and_positive() -> None:
    with pytest.raises(SystemExit):
        main([])
    with pytest.raises(SystemExit):
        main(["--limit", "0"])


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


@pytest.fixture
def scratch_engine() -> Iterator[Engine]:
    if not _integration_enabled():
        pytest.skip("Set RUN_INTEGRATION=1 to run live database tests.")
    base = make_url(get_settings().database_url)
    name = f"powerforge_worker_{uuid.uuid4().hex[:8]}"
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
def session(scratch_engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=scratch_engine, expire_on_commit=False)
    bound = factory()
    try:
        yield bound
    finally:
        bound.close()


@pytest.fixture
def api(scratch_engine: Engine):
    from powerforge_api.db import get_session
    from powerforge_api.main import app

    factory = sessionmaker(bind=scratch_engine, expire_on_commit=False)
    storage = InMemoryObjectStorage()
    enqueue = RecordingEnqueue()

    def session_override():
        bound = factory()
        try:
            yield bound
        finally:
            bound.close()

    from powerforge_document_processing.storage.factory import get_object_storage

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_object_storage] = lambda: storage
    app.dependency_overrides[get_processing_enqueue] = lambda: enqueue
    try:
        yield factory, storage, enqueue
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(get_object_storage, None)
        app.dependency_overrides.pop(get_processing_enqueue, None)


def _seed(session: Session, storage: InMemoryObjectStorage, payload: bytes) -> Document:
    project = Project(project_number=uuid.uuid4().hex[:12], project_name="Tower")
    session.add(project)
    session.flush()
    document_id = uuid.uuid4()
    storage_key = f"projects/{project.id}/documents/{document_id}/original"
    document = Document(
        id=document_id,
        project_id=project.id,
        original_filename="sheet.pdf",
        storage_key=storage_key,
        mime_type="application/pdf",
        file_extension=".pdf",
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )
    session.add(document)
    session.commit()
    storage.put(storage_key, BytesIO(payload), len(payload), "application/pdf")
    return document


def _runs(session: Session, document_id: uuid.UUID) -> list[DocumentProcessingRun]:
    return list(
        session.scalars(
            select(DocumentProcessingRun).where(DocumentProcessingRun.document_id == document_id)
        ).all()
    )


def _pdf() -> bytes:
    import fitz

    document = fitz.open()
    try:
        page = document.new_page()
        page.insert_text((72, 72), "Hello")
        return document.tobytes()
    finally:
        document.close()


def test_upload_enqueues_one_run_per_new_document(api) -> None:
    from documents_support import client, docs_url, make_project, make_revision, upload

    factory, storage, enqueue = api
    project_id = make_project()
    revision_id = make_revision(project_id, "0", activate=True).json()["id"]
    first = upload(project_id, revision_id, PDF, "one.pdf")
    assert first.status_code == 201, first.text
    document_id = uuid.UUID(first.json()["document"]["id"])
    with factory() as bound:
        runs = _runs(bound, document_id)
    assert len(runs) == 1
    assert runs[0].status == ProcessingRunStatus.PENDING
    assert enqueue.calls == [runs[0].id]

    second = upload(project_id, revision_id, png_bytes(), "two.png")
    assert second.status_code == 201, second.text
    second_id = uuid.UUID(second.json()["document"]["id"])
    with factory() as bound:
        assert len(_runs(bound, second_id)) == 1
        assert len(_runs(bound, document_id)) == 1
    assert len(enqueue.calls) == 2

    held = make_revision(project_id, "1", carry_forward_documents=False).json()["id"]
    reused = client.post(
        f"{docs_url(project_id, held)}/reuse",
        json={"source_revision_document_id": first.json()["id"]},
    )
    assert reused.status_code == 201, reused.text
    inherited = make_revision(project_id, "2")
    assert inherited.status_code == 201, inherited.text
    with factory() as bound:
        assert len(_runs(bound, document_id)) == 1
        assert len(_runs(bound, second_id)) == 1
    assert len(enqueue.calls) == 2
    assert storage.objects


def test_raising_enqueue_leaves_the_upload_and_a_pending_run(api) -> None:
    from documents_support import make_project, make_revision, upload
    from powerforge_api.main import app

    factory, storage, _enqueue = api
    app.dependency_overrides[get_processing_enqueue] = lambda: RaisingEnqueue()
    project_id = make_project()
    revision_id = make_revision(project_id, "0", activate=True).json()["id"]
    response = upload(project_id, revision_id, PDF, "one.pdf")
    assert response.status_code == 201, response.text
    document_id = uuid.UUID(response.json()["document"]["id"])
    with factory() as bound:
        runs = _runs(bound, document_id)
        document = bound.get(Document, document_id)
    assert document is not None
    assert len(runs) == 1
    assert runs[0].status == ProcessingRunStatus.PENDING
    assert runs[0].error_code is None
    assert storage.objects[document.storage_key].data == PDF


def test_task_completes_a_pdf_and_a_second_delivery_writes_nothing(session: Session) -> None:
    storage = InMemoryObjectStorage()
    payload = _pdf()
    document = _seed(session, storage, payload)
    from powerforge_document_processing.processing import ProcessingService

    run = ProcessingService(session, storage, RecordingEnqueue()).ensure_document_processing(
        document.id
    )
    execute_processing_run(run.id, session, storage)
    completed = session.get(DocumentProcessingRun, run.id)
    assert completed is not None
    assert completed.status == ProcessingRunStatus.COMPLETED
    artifacts = session.scalar(
        select(func.count())
        .select_from(PageArtifact)
        .where(PageArtifact.processing_run_id == run.id)
    )
    pages = session.scalar(
        select(func.count())
        .select_from(DocumentPage)
        .where(DocumentPage.document_id == document.id)
    )
    puts = list(storage.calls_for("put"))
    execute_processing_run(run.id, session, storage)
    assert session.get(DocumentProcessingRun, run.id).status == ProcessingRunStatus.COMPLETED
    assert (
        session.scalar(
            select(func.count())
            .select_from(PageArtifact)
            .where(PageArtifact.processing_run_id == run.id)
        )
        == artifacts
    )
    assert (
        session.scalar(
            select(func.count())
            .select_from(DocumentPage)
            .where(DocumentPage.document_id == document.id)
        )
        == pages
    )
    assert storage.calls_for("put") == puts
    assert storage.objects[document.storage_key].data == payload
    assert storage.calls_for("delete") == []


def test_timeout_marks_a_running_run(session: Session) -> None:
    storage = InMemoryObjectStorage()
    document = _seed(session, storage, PDF)
    run = DocumentProcessingRun(
        document_id=document.id,
        processor_version=DEFAULT_PROFILE.processor_version,
        profile_version=DEFAULT_PROFILE.profile_version,
        profile_hash=DEFAULT_PROFILE.profile_hash,
        status=ProcessingRunStatus.RUNNING,
        attempt_count=1,
        pages_processed=0,
    )
    session.add(run)
    session.commit()
    mark_processing_timeout(session, run.id)
    failed = session.get(DocumentProcessingRun, run.id)
    assert failed is not None
    assert failed.status == ProcessingRunStatus.FAILED
    assert failed.error_code == ProcessingErrorCode.PROCESSING_TIMEOUT
    assert failed.error_message == "Processing timed out"
    assert document.storage_key not in (failed.error_message or "")


def test_backfill_is_bounded_and_leaves_finished_runs(session: Session) -> None:
    storage = InMemoryObjectStorage()
    enqueue = RecordingEnqueue()
    missing = _seed(session, storage, PDF)
    pending_document = _seed(session, storage, PDF + b"\n")
    failed_document = _seed(session, storage, PDF + b"\n\n")
    completed_document = _seed(session, storage, PDF + b"\n\n\n")
    profile = DEFAULT_PROFILE
    session.add(
        DocumentProcessingRun(
            document_id=pending_document.id,
            processor_version=profile.processor_version,
            profile_version=profile.profile_version,
            profile_hash=profile.profile_hash,
            status=ProcessingRunStatus.PENDING,
            attempt_count=1,
            pages_processed=0,
        )
    )
    session.add(
        DocumentProcessingRun(
            document_id=failed_document.id,
            processor_version=profile.processor_version,
            profile_version=profile.profile_version,
            profile_hash=profile.profile_hash,
            status=ProcessingRunStatus.FAILED,
            attempt_count=1,
            pages_processed=0,
        )
    )
    session.add(
        DocumentProcessingRun(
            document_id=completed_document.id,
            processor_version=profile.processor_version,
            profile_version=profile.profile_version,
            profile_hash=profile.profile_hash,
            status=ProcessingRunStatus.COMPLETED,
            attempt_count=1,
            pages_processed=1,
        )
    )
    session.commit()

    selected = backfill_documents(session, storage, enqueue, limit=10)
    assert selected == 2
    assert len(_runs(session, missing.id)) == 1
    assert _runs(session, missing.id)[0].status == ProcessingRunStatus.PENDING
    assert len(_runs(session, pending_document.id)) == 1
    assert len(enqueue.calls) == 2
    assert _runs(session, failed_document.id)[0].status == ProcessingRunStatus.FAILED
    assert _runs(session, completed_document.id)[0].status == ProcessingRunStatus.COMPLETED

    before = len(enqueue.calls)
    again = backfill_documents(session, storage, enqueue, limit=1)
    assert again == 1
    assert len(enqueue.calls) == before + 1
