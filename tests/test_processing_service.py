"""Processing service lifecycle against a scratch database. Requires RUN_INTEGRATION=1.

The fixture creates a database, upgrades it to head, and drops it. It does not use the
Compose development database. Storage is in memory. There is no Celery worker.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path

import fitz
import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from powerforge_document_model import (
    DocumentOrigin,
    PageArtifactType,
    ProcessingErrorCode,
    ProcessingRunStatus,
)
from powerforge_document_processing.models import (
    Document,
    DocumentPage,
    DocumentProcessingRun,
    PageArtifact,
    Project,
    ProjectRevision,
    RevisionDocument,
)
from powerforge_document_processing.processing import (
    DocumentNotFound,
    ProcessingNotRetryable,
    ProcessingService,
)
from powerforge_document_processing.storage.base import StorageError
from powerforge_document_processing.storage.memory import InMemoryObjectStorage
from powerforge_shared.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = "database/alembic.ini"


class RecordingEnqueue:
    """Test double for the enqueue port. Records run ids or raises."""

    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[uuid.UUID] = []
        self.error = error

    def enqueue_document_processing(self, run_id: uuid.UUID) -> None:
        if self.error is not None:
            raise self.error
        self.calls.append(run_id)


class FailSecondPage(InMemoryObjectStorage):
    """Accepts the original and the first page, then fails a put for page 2."""

    def put(self, key: str, fileobj, size: int, content_type: str) -> None:
        if "/pages/0002/" in key:
            self.calls.append(("put", key))
            raise StorageError("Injected storage failure")
        super().put(key, fileobj, size, content_type)


def _integration_enabled() -> bool:
    return os.environ.get("RUN_INTEGRATION") == "1"


def _base_url() -> URL:
    return make_url(get_settings().database_url)


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
    base = _base_url()
    name = f"powerforge_proc_{uuid.uuid4().hex[:8]}"
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


def _pdf(pages: list[str]) -> bytes:
    document = fitz.open()
    try:
        for text_line in pages:
            page = document.new_page()
            if text_line:
                page.insert_text((72, 72), text_line)
        return document.tobytes()
    finally:
        document.close()


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


def _service(
    session: Session,
    storage: InMemoryObjectStorage,
    enqueue: RecordingEnqueue | None = None,
) -> tuple[ProcessingService, RecordingEnqueue]:
    port = enqueue or RecordingEnqueue()
    return ProcessingService(session, storage, port), port


def _runs(session: Session, document_id: uuid.UUID) -> list[DocumentProcessingRun]:
    return list(
        session.scalars(
            select(DocumentProcessingRun)
            .where(DocumentProcessingRun.document_id == document_id)
            .order_by(DocumentProcessingRun.attempt_count)
        ).all()
    )


def _artifacts(session: Session, run_id: uuid.UUID) -> list[PageArtifact]:
    return list(
        session.scalars(select(PageArtifact).where(PageArtifact.processing_run_id == run_id)).all()
    )


def _lock_waits(engine: Engine) -> int:
    with engine.connect() as connection:
        return connection.execute(
            text(
                """
                SELECT count(*)
                FROM pg_stat_activity
                WHERE datname = current_database()
                  AND wait_event_type = 'Lock'
                """
            )
        ).scalar_one()


def test_pdf_run_completes_with_pages_and_artifacts(session: Session) -> None:
    storage = InMemoryObjectStorage()
    payload = _pdf(["Hello"])
    document = _seed(session, storage, payload)
    service, enqueue = _service(session, storage)

    pending = service.ensure_document_processing(document.id)
    assert pending.status == ProcessingRunStatus.PENDING
    assert pending.attempt_count == 1
    assert pending.pages_processed == 0
    assert enqueue.calls == [pending.id]

    service.claim_and_process(pending.id)
    run = session.get(DocumentProcessingRun, pending.id)
    assert run is not None
    assert run.status == ProcessingRunStatus.COMPLETED
    assert run.pages_total == 1
    assert run.pages_processed == 1
    assert run.attempt_count == 1
    assert run.started_at is not None
    assert run.completed_at is not None
    assert run.error_code is None

    pages = list(
        session.scalars(select(DocumentPage).where(DocumentPage.document_id == document.id)).all()
    )
    assert len(pages) == 1
    assert pages[0].page_number == 1
    assert pages[0].native_text_char_count > 0

    artifacts = _artifacts(session, run.id)
    kinds = {artifact.artifact_type for artifact in artifacts}
    assert kinds == {
        PageArtifactType.ANALYSIS_IMAGE,
        PageArtifactType.THUMBNAIL,
        PageArtifactType.NATIVE_TEXT,
    }
    by_type = {artifact.artifact_type: artifact for artifact in artifacts}
    analysis = storage.objects[by_type[PageArtifactType.ANALYSIS_IMAGE].storage_key].data
    thumbnail = storage.objects[by_type[PageArtifactType.THUMBNAIL].storage_key].data
    native = storage.objects[by_type[PageArtifactType.NATIVE_TEXT].storage_key].data
    assert analysis.startswith(b"\x89PNG")
    assert thumbnail.startswith(b"RIFF") and thumbnail[8:12] == b"WEBP"
    assert b"Hello" in native
    image = by_type[PageArtifactType.ANALYSIS_IMAGE]
    assert image.sha256 == hashlib.sha256(analysis).hexdigest()
    assert image.size_bytes == len(analysis)
    assert image.mime_type == "image/png"
    assert image.width_px is not None and image.height_px is not None
    assert str(run.id) in image.storage_key
    assert storage.objects[document.storage_key].data == payload
    assert storage.calls_for("delete") == []


def test_corrupt_original_fails_with_renderer_code(session: Session) -> None:
    storage = InMemoryObjectStorage()
    payload = b"%PDF-1.4\nnot a pdf"
    document = _seed(session, storage, payload)
    service, _enqueue = _service(session, storage)
    run = service.ensure_document_processing(document.id)
    service.claim_and_process(run.id)

    failed = session.get(DocumentProcessingRun, run.id)
    assert failed is not None
    assert failed.status == ProcessingRunStatus.FAILED
    assert failed.error_code == ProcessingErrorCode.CORRUPT_PDF
    assert failed.completed_at is None
    assert document.storage_key not in (failed.error_message or "")
    assert storage.objects[document.storage_key].data == payload
    assert storage.calls_for("delete") == []


def test_second_page_write_failure_keeps_first_page(session: Session) -> None:
    storage = FailSecondPage()
    payload = _pdf(["one", "two"])
    document = _seed(session, storage, payload)
    service, _enqueue = _service(session, storage)
    run = service.ensure_document_processing(document.id)
    service.claim_and_process(run.id)

    failed = session.get(DocumentProcessingRun, run.id)
    assert failed is not None
    assert failed.status == ProcessingRunStatus.FAILED
    assert failed.error_code == ProcessingErrorCode.STORAGE_WRITE_FAILED
    assert failed.completed_at is None
    assert failed.pages_processed == 1
    artifacts = _artifacts(session, failed.id)
    assert artifacts
    assert all("/pages/0001/" in artifact.storage_key for artifact in artifacts)
    assert storage.objects[document.storage_key].data == payload
    assert storage.calls_for("delete") == []


def test_three_revisions_share_one_completed_run(session: Session) -> None:
    storage = InMemoryObjectStorage()
    document = _seed(session, storage, _pdf(["Hello"]))
    for identifier in ("A", "B", "C"):
        revision = ProjectRevision(project_id=document.project_id, identifier=identifier)
        session.add(revision)
        session.flush()
        session.add(
            RevisionDocument(
                project_id=document.project_id,
                revision_id=revision.id,
                document_id=document.id,
                origin=DocumentOrigin.UPLOADED,
            )
        )
    session.commit()

    service, enqueue = _service(session, storage)
    first = service.ensure_document_processing(document.id)
    service.claim_and_process(first.id)
    again = service.ensure_document_processing(document.id)
    third = service.ensure_document_processing(document.id)

    assert again.id == first.id
    assert third.id == first.id
    assert enqueue.calls == [first.id]
    assert len(_runs(session, document.id)) == 1
    pages = session.scalar(
        select(func.count())
        .select_from(DocumentPage)
        .where(DocumentPage.document_id == document.id)
    )
    assert pages == 1
    completed = session.get(DocumentProcessingRun, first.id)
    assert completed is not None
    assert completed.status == ProcessingRunStatus.COMPLETED


def test_retry_inserts_a_new_run_and_keeps_the_failed_attempt(session: Session) -> None:
    storage = FailSecondPage()
    payload = _pdf(["one", "two"])
    document = _seed(session, storage, payload)
    service, _enqueue = _service(session, storage)
    failed = service.ensure_document_processing(document.id)
    service.claim_and_process(failed.id)
    old_artifacts = list(_artifacts(session, failed.id))
    assert old_artifacts

    fresh = InMemoryObjectStorage()
    fresh.put(document.storage_key, BytesIO(payload), len(payload), "application/pdf")
    retry_service, retry_enqueue = _service(session, fresh)
    retried = retry_service.retry_failed_processing(document.id)

    assert retried.id != failed.id
    assert retried.status == ProcessingRunStatus.PENDING
    assert retried.attempt_count == 2
    assert retried.pages_processed == 0
    assert retry_enqueue.calls == [retried.id]
    still_failed = session.get(DocumentProcessingRun, failed.id)
    assert still_failed is not None
    assert still_failed.status == ProcessingRunStatus.FAILED
    assert _artifacts(session, failed.id) == old_artifacts

    retry_service.claim_and_process(retried.id)
    completed = session.get(DocumentProcessingRun, retried.id)
    assert completed is not None
    assert completed.status == ProcessingRunStatus.COMPLETED
    new_artifacts = _artifacts(session, retried.id)
    assert new_artifacts
    assert all(str(retried.id) in artifact.storage_key for artifact in new_artifacts)
    assert _artifacts(session, failed.id) == old_artifacts


def test_claim_does_not_change_attempt_count_and_second_claim_writes_nothing(
    session: Session,
) -> None:
    storage = InMemoryObjectStorage()
    document = _seed(session, storage, _pdf(["Hello"]))
    service, _enqueue = _service(session, storage)
    run = service.ensure_document_processing(document.id)
    assert run.attempt_count == 1
    service.claim_and_process(run.id)
    claimed = session.get(DocumentProcessingRun, run.id)
    assert claimed is not None
    assert claimed.attempt_count == 1
    assert claimed.status == ProcessingRunStatus.COMPLETED

    puts = list(storage.calls_for("put"))
    artifact_count = session.scalar(select(func.count()).select_from(PageArtifact))
    page_count = session.scalar(select(func.count()).select_from(DocumentPage))
    service.claim_and_process(run.id)
    assert storage.calls_for("put") == puts
    assert session.scalar(select(func.count()).select_from(PageArtifact)) == artifact_count
    assert session.scalar(select(func.count()).select_from(DocumentPage)) == page_count
    assert session.get(DocumentProcessingRun, run.id).status == ProcessingRunStatus.COMPLETED


def test_ensure_enqueues_pending_and_skips_running_completed_and_failed(session: Session) -> None:
    storage = InMemoryObjectStorage()
    document = _seed(session, storage, _pdf(["Hello"]))
    service, enqueue = _service(session, storage)

    pending = service.ensure_document_processing(document.id)
    again = service.ensure_document_processing(document.id)
    assert again.id == pending.id
    assert enqueue.calls == [pending.id, pending.id]
    assert len(_runs(session, document.id)) == 1

    pending.status = ProcessingRunStatus.RUNNING
    session.commit()
    running = service.ensure_document_processing(document.id)
    assert running.id == pending.id
    assert enqueue.calls == [pending.id, pending.id]

    service.claim_and_process(pending.id)
    assert session.get(DocumentProcessingRun, pending.id).status == ProcessingRunStatus.RUNNING
    calls_while_running = list(enqueue.calls)
    service.ensure_document_processing(document.id)
    assert enqueue.calls == calls_while_running

    pending.status = ProcessingRunStatus.PENDING
    pending.started_at = None
    session.commit()
    service.claim_and_process(pending.id)
    completed = session.get(DocumentProcessingRun, pending.id)
    assert completed.status == ProcessingRunStatus.COMPLETED
    calls_while_completed = list(enqueue.calls)
    returned = service.ensure_document_processing(document.id)
    assert returned.id == pending.id
    assert enqueue.calls == calls_while_completed


def test_ensure_of_failed_does_not_enqueue(session: Session) -> None:
    storage = InMemoryObjectStorage()
    document = _seed(session, storage, b"%PDF-1.4\nnot a pdf")
    service, enqueue = _service(session, storage)
    run = service.ensure_document_processing(document.id)
    service.claim_and_process(run.id)
    assert session.get(DocumentProcessingRun, run.id).status == ProcessingRunStatus.FAILED
    calls = list(enqueue.calls)
    returned = service.ensure_document_processing(document.id)
    assert returned.id == run.id
    assert returned.status == ProcessingRunStatus.FAILED
    assert enqueue.calls == calls


def test_enqueue_failure_leaves_pending_run_and_document(session: Session) -> None:
    storage = InMemoryObjectStorage()
    payload = _pdf(["Hello"])
    document = _seed(session, storage, payload)
    service, _enqueue = _service(session, storage, RecordingEnqueue(error=RuntimeError("down")))
    run = service.ensure_document_processing(document.id)

    assert run.status == ProcessingRunStatus.PENDING
    assert run.error_code is None
    kept = session.get(Document, document.id)
    assert kept is not None
    assert kept.storage_key == document.storage_key
    assert storage.objects[document.storage_key].data == payload


def test_storage_read_failure_keeps_the_original(session: Session) -> None:
    storage = InMemoryObjectStorage()
    payload = _pdf(["Hello"])
    document = _seed(session, storage, payload)
    storage.fail_on("get")
    service, _enqueue = _service(session, storage)
    run = service.ensure_document_processing(document.id)
    service.claim_and_process(run.id)

    failed = session.get(DocumentProcessingRun, run.id)
    assert failed is not None
    assert failed.status == ProcessingRunStatus.FAILED
    assert failed.error_code == ProcessingErrorCode.STORAGE_READ_FAILED
    assert document.storage_key not in (failed.error_message or "")
    assert storage.objects[document.storage_key].data == payload
    assert storage.calls_for("delete") == []


def test_missing_document_and_retry_guards(session: Session) -> None:
    storage = InMemoryObjectStorage()
    service, _enqueue = _service(session, storage)
    missing = uuid.uuid4()
    with pytest.raises(DocumentNotFound):
        service.ensure_document_processing(missing)
    with pytest.raises(DocumentNotFound):
        service.retry_failed_processing(missing)

    document = _seed(session, storage, _pdf(["Hello"]))
    with pytest.raises(ProcessingNotRetryable):
        service.retry_failed_processing(document.id)
    pending = service.ensure_document_processing(document.id)
    with pytest.raises(ProcessingNotRetryable):
        service.retry_failed_processing(document.id)
    service.claim_and_process(pending.id)
    with pytest.raises(ProcessingNotRetryable):
        service.retry_failed_processing(document.id)


def test_concurrent_ensure_leaves_one_run(session: Session, scratch_engine: Engine) -> None:
    storage = InMemoryObjectStorage()
    document = _seed(session, storage, _pdf(["Hello"]))
    factory = sessionmaker(bind=scratch_engine, expire_on_commit=False)
    holder = factory()
    loser_session = factory()
    ready = threading.Event()
    release = threading.Event()
    errors: list[BaseException] = []
    loser_found: list[tuple[uuid.UUID, list[uuid.UUID]]] = []

    def hold() -> None:
        try:
            service = ProcessingService(holder, storage, RecordingEnqueue())
            _run, inserted = service._insert_pending(document.id, attempt_count=1)
            assert inserted
            ready.set()
            assert release.wait(5)
            holder.commit()
        except Exception as exc:
            errors.append(exc)
            ready.set()
        finally:
            release.set()

    def lose() -> None:
        try:
            assert ready.wait(5)
            enqueue = RecordingEnqueue()
            service = ProcessingService(loser_session, storage, enqueue)
            run = service.ensure_document_processing(document.id)
            loser_found.append((run.id, list(enqueue.calls)))
        except Exception as exc:
            errors.append(exc)

    holder_thread = threading.Thread(target=hold)
    loser_thread = threading.Thread(target=lose)
    holder_thread.start()
    loser_thread.start()
    assert ready.wait(5)
    deadline = time.time() + 5
    while time.time() < deadline and _lock_waits(scratch_engine) == 0:
        time.sleep(0.05)
    assert _lock_waits(scratch_engine) > 0
    release.set()
    holder_thread.join(5)
    loser_thread.join(5)
    holder.close()
    loser_session.close()

    assert errors == []
    assert len(_runs(session, document.id)) == 1
    winner_id = _runs(session, document.id)[0].id
    assert loser_found == [(winner_id, [])]


def test_concurrent_retry_leaves_one_pending(session: Session, scratch_engine: Engine) -> None:
    storage = InMemoryObjectStorage()
    document = _seed(session, storage, b"%PDF-1.4\nnot a pdf")
    service, _enqueue = _service(session, storage)
    failed = service.ensure_document_processing(document.id)
    service.claim_and_process(failed.id)
    assert session.get(DocumentProcessingRun, failed.id).status == ProcessingRunStatus.FAILED

    factory = sessionmaker(bind=scratch_engine, expire_on_commit=False)
    holder = factory()
    loser_session = factory()
    ready = threading.Event()
    release = threading.Event()
    errors: list[BaseException] = []
    loser_found: list[tuple[uuid.UUID, list[uuid.UUID]]] = []

    def hold() -> None:
        try:
            held = ProcessingService(holder, storage, RecordingEnqueue())
            _run, inserted = held._insert_pending(document.id, attempt_count=2)
            assert inserted
            ready.set()
            assert release.wait(5)
            holder.commit()
        except Exception as exc:
            errors.append(exc)
            ready.set()
        finally:
            release.set()

    def lose() -> None:
        try:
            assert ready.wait(5)
            enqueue = RecordingEnqueue()
            retried = ProcessingService(loser_session, storage, enqueue).retry_failed_processing(
                document.id
            )
            loser_found.append((retried.id, list(enqueue.calls)))
        except Exception as exc:
            errors.append(exc)

    holder_thread = threading.Thread(target=hold)
    loser_thread = threading.Thread(target=lose)
    holder_thread.start()
    loser_thread.start()
    assert ready.wait(5)
    deadline = time.time() + 5
    while time.time() < deadline and _lock_waits(scratch_engine) == 0:
        time.sleep(0.05)
    assert _lock_waits(scratch_engine) > 0
    release.set()
    holder_thread.join(5)
    loser_thread.join(5)
    holder.close()
    loser_session.close()

    assert errors == []
    runs = _runs(session, document.id)
    pending = [run for run in runs if run.status == ProcessingRunStatus.PENDING]
    assert len(runs) == 2
    assert len(pending) == 1
    assert pending[0].attempt_count == 2
    assert pending[0].pages_processed == 0
    assert loser_found == [(pending[0].id, [])]
