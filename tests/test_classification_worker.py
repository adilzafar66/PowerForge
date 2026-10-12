"""Classification queue, trigger, and backfill. Integration cases need RUN_INTEGRATION=1.

The database fixture creates a database, upgrades it to head, and drops it. It does not
use the Compose development database.
"""

from __future__ import annotations

import ast
import hashlib
import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from document_worker.celery_app import (
    execute_processing_run,
    maybe_enqueue_classification,
    process_document_run,
)
from extraction_worker.celery_app import (
    celery_app as extraction_app,
)
from extraction_worker.celery_app import (
    execute_classification_run,
    require_openai_credentials,
)
from powerforge_document_classification.backfill import (
    backfill_documents,
    main,
    select_backfill_ids,
)
from powerforge_document_classification.enqueue import (
    CLASSIFY_RUN_QUEUE,
    CLASSIFY_RUN_TASK,
    CeleryClassificationEnqueue,
)
from powerforge_document_classification.errors import (
    ClassificationErrorCode,
    ClassificationProviderError,
)
from powerforge_document_classification.fake import FakeClassificationProvider
from powerforge_document_classification.service import ClassificationDisabled, ClassificationService
from powerforge_document_model import (
    DEFAULT_PROFILE,
    ClassificationRunStatus,
    ProcessingRunStatus,
)
from powerforge_document_processing.models import (
    Document,
    DocumentClassificationRun,
    DocumentProcessingRun,
    Project,
)
from powerforge_document_processing.processing import ProcessingService
from powerforge_document_processing.storage.memory import InMemoryObjectStorage
from powerforge_shared.config import Settings, get_settings

REPO_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = "database/alembic.ini"


class RecordingEnqueue:
    def __init__(self) -> None:
        self.calls: list[uuid.UUID] = []

    def enqueue_document_classification(self, run_id: uuid.UUID) -> None:
        self.calls.append(run_id)


class RaisingEnqueue:
    def enqueue_document_classification(self, run_id: uuid.UUID) -> None:
        raise RuntimeError("broker down")


class CountingProvider:
    def __init__(self) -> None:
        self.documents = 0
        self.pages = 0
        self.inner = FakeClassificationProvider()

    def classify_document(self, request):
        self.documents += 1
        return self.inner.classify_document(request)

    def classify_pages(self, request):
        self.pages += 1
        return self.inner.classify_pages(request)


class SoftTimeLimitExceeded(Exception):
    pass


class TimeoutProvider:
    def classify_document(self, request):
        raise SoftTimeLimitExceeded

    def classify_pages(self, request):
        raise AssertionError("page classification is not part of the task timeout")


class ProviderTimeout:
    def classify_document(self, request):
        raise ClassificationProviderError(ClassificationErrorCode.PROVIDER_TIMEOUT)

    def classify_pages(self, request):
        raise AssertionError("page classification is not part of the provider timeout")


def _enabled() -> Settings:
    return Settings(ai_classification_enabled=True)


def test_enqueue_publishes_to_the_document_classification_queue() -> None:
    calls: dict[str, object] = {}

    class _FakeApp:
        def send_task(self, name: str, args: list[str], queue: str) -> None:
            calls["name"] = name
            calls["args"] = args
            calls["queue"] = queue

    enqueue = CeleryClassificationEnqueue()
    enqueue._app = _FakeApp()  # type: ignore[assignment]
    run_id = uuid.uuid4()
    enqueue.enqueue_document_classification(run_id)
    assert calls == {
        "name": CLASSIFY_RUN_TASK,
        "args": [str(run_id)],
        "queue": CLASSIFY_RUN_QUEUE,
    }


def test_classification_task_is_only_registered_on_the_extraction_worker() -> None:
    assert "extraction_worker.heartbeat" in extraction_app.tasks
    assert CLASSIFY_RUN_TASK in extraction_app.tasks
    task = extraction_app.tasks[CLASSIFY_RUN_TASK]
    assert task.__module__ == "extraction_worker.celery_app"
    assert task.soft_time_limit == 600
    assert task.time_limit == 660
    script = """
import json
from document_worker.celery_app import celery_app as document_app
from validation_worker.celery_app import celery_app as validation_app
print(json.dumps({
    "document": TASK in document_app.tasks,
    "validation": TASK in validation_app.tasks,
}))
""".replace("TASK", repr(CLASSIFY_RUN_TASK))
    pythonpath = os.pathsep.join(
        [
            str(REPO_ROOT / "services/document-worker/src"),
            str(REPO_ROOT / "services/validation-worker/src"),
            str(REPO_ROOT / "packages/shared/src"),
            str(REPO_ROOT / "packages/document-processing/src"),
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
    assert result.stdout.strip() == '{"document": false, "validation": false}'


def test_document_worker_does_not_import_openai_or_the_extraction_worker() -> None:
    root = REPO_ROOT / "services" / "document-worker" / "src"
    for path in root.rglob("*.py"):
        modules = _imported_modules(path)
        roots = {module.split(".", 1)[0] for module in modules}
        assert "openai" not in roots, path
        assert "extraction_worker" not in modules, path


def test_openai_key_is_required_only_for_an_enabled_openai_worker() -> None:
    require_openai_credentials(Settings())
    require_openai_credentials(Settings(ai_classification_enabled=True))
    require_openai_credentials(Settings(ai_provider="openai", openai_api_key="sk-test"))
    require_openai_credentials(
        Settings(
            ai_classification_enabled=True,
            ai_provider="openai",
            openai_api_key="sk-test",
        )
    )
    with pytest.raises(SystemExit):
        require_openai_credentials(
            Settings(ai_classification_enabled=True, ai_provider="openai")
        )


def test_processing_task_calls_classification_after_the_run() -> None:
    import inspect

    text = inspect.getsource(process_document_run)
    assert "execute_processing_run" in text
    assert "maybe_enqueue_classification" in text


def test_backfill_limit_is_required_and_positive() -> None:
    with pytest.raises(SystemExit):
        main([])
    with pytest.raises(SystemExit):
        main(["--limit", "0"])


def test_disabled_backfill_inserts_nothing() -> None:
    with pytest.raises(ClassificationDisabled):
        backfill_documents(
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            RecordingEnqueue(),
            1,
            Settings(ai_classification_enabled=False),
        )


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return set(modules)


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
    name = f"powerforge_classify_{uuid.uuid4().hex[:8]}"
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


def _pdf() -> bytes:
    import fitz

    document = fitz.open()
    try:
        page = document.new_page()
        page.insert_text((72, 72), "Hello")
        return document.tobytes()
    finally:
        document.close()


def _seed(
    session: Session,
    storage: InMemoryObjectStorage,
    payload: bytes,
    *,
    filename: str = "sheet.pdf",
) -> Document:
    project = Project(project_number=uuid.uuid4().hex[:12], project_name="Tower")
    session.add(project)
    session.flush()
    document_id = uuid.uuid4()
    storage_key = f"projects/{project.id}/documents/{document_id}/original"
    document = Document(
        id=document_id,
        project_id=project.id,
        original_filename=filename,
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


def _processed(session: Session, storage: InMemoryObjectStorage, payload: bytes) -> tuple:
    document = _seed(session, storage, payload)
    run = ProcessingService(session, storage, _ProcessingEnqueue()).ensure_document_processing(
        document.id
    )
    execute_processing_run(run.id, session, storage)
    return document, run


class _ProcessingEnqueue:
    def enqueue_document_processing(self, run_id: uuid.UUID) -> None:
        return None


def _classification_rows(
    session: Session, document_id: uuid.UUID
) -> list[DocumentClassificationRun]:
    return list(
        session.scalars(
            select(DocumentClassificationRun).where(
                DocumentClassificationRun.document_id == document_id
            )
        ).all()
    )


def test_completed_processing_publishes_one_classification_task(session: Session) -> None:
    storage = InMemoryObjectStorage()
    document, processing = _processed(session, storage, _pdf())
    assert session.get(DocumentProcessingRun, processing.id).status == ProcessingRunStatus.COMPLETED
    enqueue = RecordingEnqueue()
    maybe_enqueue_classification(session, storage, processing.id, enqueue, _enabled())
    assert len(enqueue.calls) == 1
    rows = _classification_rows(session, document.id)
    assert len(rows) == 1
    assert rows[0].status == ClassificationRunStatus.PENDING
    assert rows[0].id == enqueue.calls[0]
    provider = CountingProvider()
    execute_classification_run(rows[0].id, session, storage, provider, _enabled())
    finished = session.get(DocumentClassificationRun, rows[0].id)
    assert finished is not None
    assert finished.status == ClassificationRunStatus.COMPLETED
    assert provider.documents == 1
    execute_classification_run(rows[0].id, session, storage, provider, _enabled())
    assert provider.documents == 1
    assert session.get(DocumentProcessingRun, processing.id).status == ProcessingRunStatus.COMPLETED


def test_failed_processing_does_not_enqueue_classification(session: Session) -> None:
    storage = InMemoryObjectStorage()
    document, processing = _processed(session, storage, b"%PDF-1.4\nnot a pdf")
    assert session.get(DocumentProcessingRun, processing.id).status == ProcessingRunStatus.FAILED
    enqueue = RecordingEnqueue()
    maybe_enqueue_classification(session, storage, processing.id, enqueue, _enabled())
    assert enqueue.calls == []
    assert _classification_rows(session, document.id) == []


def test_enqueue_failure_leaves_processing_completed(session: Session) -> None:
    storage = InMemoryObjectStorage()
    document, processing = _processed(session, storage, _pdf())
    maybe_enqueue_classification(session, storage, processing.id, RaisingEnqueue(), _enabled())
    assert session.get(DocumentProcessingRun, processing.id).status == ProcessingRunStatus.COMPLETED
    rows = _classification_rows(session, document.id)
    assert len(rows) == 1
    assert rows[0].status == ClassificationRunStatus.PENDING


def test_disabled_mode_inserts_no_classification_row(session: Session) -> None:
    storage = InMemoryObjectStorage()
    document, processing = _processed(session, storage, _pdf())
    enqueue = RecordingEnqueue()
    maybe_enqueue_classification(
        session,
        storage,
        processing.id,
        enqueue,
        Settings(ai_classification_enabled=False),
    )
    assert enqueue.calls == []
    assert _classification_rows(session, document.id) == []


def test_ensure_exception_leaves_processing_completed(session: Session, monkeypatch) -> None:
    storage = InMemoryObjectStorage()
    _document, processing = _processed(session, storage, _pdf())

    def boom(self, document_id: uuid.UUID) -> None:
        raise RuntimeError("ensure failed")

    monkeypatch.setattr(ClassificationService, "ensure_document_classification", boom)
    maybe_enqueue_classification(session, storage, processing.id, RecordingEnqueue(), _enabled())
    assert session.get(DocumentProcessingRun, processing.id).status == ProcessingRunStatus.COMPLETED


def test_provider_timeout_and_task_timeout_stay_distinct(session: Session) -> None:
    storage = InMemoryObjectStorage()
    _document, processing = _processed(session, storage, _pdf())
    enqueue = RecordingEnqueue()
    maybe_enqueue_classification(session, storage, processing.id, enqueue, _enabled())
    run_id = enqueue.calls[0]
    execute_classification_run(run_id, session, storage, ProviderTimeout(), _enabled())
    failed = session.get(DocumentClassificationRun, run_id)
    assert failed is not None
    assert failed.status == ClassificationRunStatus.FAILED
    assert failed.error_code == ClassificationErrorCode.PROVIDER_TIMEOUT.value

    other, other_processing = _processed(session, storage, _pdf())
    other_enqueue = RecordingEnqueue()
    maybe_enqueue_classification(
        session, storage, other_processing.id, other_enqueue, _enabled()
    )
    with pytest.raises(SoftTimeLimitExceeded):
        execute_classification_run(
            other_enqueue.calls[0],
            session,
            storage,
            TimeoutProvider(),
            _enabled(),
        )
    timed_out = session.get(DocumentClassificationRun, other_enqueue.calls[0])
    assert timed_out is not None
    assert timed_out.status == ClassificationRunStatus.FAILED
    assert timed_out.error_code == ClassificationErrorCode.CLASSIFICATION_TASK_TIMEOUT.value
    assert timed_out.error_message == "Classification timed out"
    assert other.storage_key not in (timed_out.error_message or "")


def _document_with_processing(
    session: Session,
    *,
    uploaded_at: datetime,
    status: ProcessingRunStatus = ProcessingRunStatus.COMPLETED,
    profile_hash: str | None = None,
) -> tuple[Document, DocumentProcessingRun]:
    project = Project(project_number=uuid.uuid4().hex[:12], project_name="Tower")
    session.add(project)
    session.flush()
    document = Document(
        project_id=project.id,
        original_filename="sheet.pdf",
        storage_key=f"projects/{project.id}/documents/{uuid.uuid4()}/original",
        mime_type="application/pdf",
        file_extension=".pdf",
        size_bytes=8,
        sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        uploaded_at=uploaded_at,
    )
    session.add(document)
    session.flush()
    processing = DocumentProcessingRun(
        document_id=document.id,
        processor_version=DEFAULT_PROFILE.processor_version,
        profile_version=DEFAULT_PROFILE.profile_version,
        profile_hash=profile_hash or DEFAULT_PROFILE.profile_hash,
        status=status,
        pages_total=1,
        pages_processed=1 if status == ProcessingRunStatus.COMPLETED else 0,
        attempt_count=1,
    )
    session.add(processing)
    session.flush()
    return document, processing


def _mark(
    session: Session,
    storage: InMemoryObjectStorage,
    document: Document,
    status: ClassificationRunStatus,
    settings: Settings,
) -> DocumentClassificationRun:
    run = ClassificationService(
        session,
        storage,
        RecordingEnqueue(),
        FakeClassificationProvider(),
        settings,
    ).ensure_document_classification(document.id)
    run.status = status
    session.commit()
    return run


def test_backfill_selects_only_work_ensure_would_enqueue(session: Session) -> None:
    storage = InMemoryObjectStorage()
    settings = _enabled()
    origin = datetime(2024, 1, 1, tzinfo=UTC)

    failed_document, _failed_processing = _document_with_processing(
        session, uploaded_at=origin
    )
    _mark(session, storage, failed_document, ClassificationRunStatus.FAILED, settings)

    running_document, _running_processing = _document_with_processing(
        session, uploaded_at=origin + timedelta(minutes=1)
    )
    _mark(session, storage, running_document, ClassificationRunStatus.RUNNING, settings)

    completed_document, _completed_processing = _document_with_processing(
        session, uploaded_at=origin + timedelta(minutes=2)
    )
    _mark(session, storage, completed_document, ClassificationRunStatus.COMPLETED, settings)

    pending_document, _pending_processing = _document_with_processing(
        session, uploaded_at=origin + timedelta(minutes=3)
    )
    pending = _mark(session, storage, pending_document, ClassificationRunStatus.PENDING, settings)

    missing_document, _missing_processing = _document_with_processing(
        session, uploaded_at=origin + timedelta(minutes=4)
    )

    stale_document, current = _document_with_processing(
        session, uploaded_at=origin + timedelta(minutes=5)
    )
    old = DocumentProcessingRun(
        document_id=stale_document.id,
        processor_version=DEFAULT_PROFILE.processor_version,
        profile_version=DEFAULT_PROFILE.profile_version,
        profile_hash=DEFAULT_PROFILE.profile_hash,
        status=ProcessingRunStatus.FAILED,
        pages_total=1,
        pages_processed=0,
        attempt_count=1,
    )
    session.add(old)
    session.flush()
    session.add(
        DocumentClassificationRun(
            document_id=stale_document.id,
            processing_run_id=old.id,
            attempt_number=1,
            classifier_version="1",
            taxonomy_version="document-taxonomy-v2",
            prompt_version="old",
            sampling_profile_version="old",
            sampling_profile_hash="old",
            classifier_identity_hash="not-the-current-identity",
            provider="fake",
            model="fake-classifier",
            status=ClassificationRunStatus.COMPLETED,
            pages_total=0,
            pages_classified=0,
        )
    )
    session.flush()
    assert current.status == ProcessingRunStatus.COMPLETED

    other_document, _other_processing = _document_with_processing(
        session,
        uploaded_at=origin + timedelta(minutes=6),
        status=ProcessingRunStatus.FAILED,
    )
    _other_completed = DocumentProcessingRun(
        document_id=other_document.id,
        processor_version=DEFAULT_PROFILE.processor_version,
        profile_version="other",
        profile_hash="not-the-active-profile",
        status=ProcessingRunStatus.COMPLETED,
        pages_total=1,
        pages_processed=1,
        attempt_count=1,
    )
    session.add(_other_completed)
    session.commit()

    limited = select_backfill_ids(session, settings, 1)
    assert limited == [pending_document.id]

    selected = select_backfill_ids(session, settings, 10)
    assert selected == [pending_document.id, missing_document.id, stale_document.id]

    enqueue = RecordingEnqueue()
    count = backfill_documents(session, storage, enqueue, 10, settings)
    assert count == 3
    assert enqueue.calls[0] == pending.id
    assert len(enqueue.calls) == 3
    pending_row = session.get(DocumentClassificationRun, pending.id)
    assert pending_row is not None
    assert pending_row.status == ClassificationRunStatus.PENDING
    missing_rows = _classification_rows(session, missing_document.id)
    assert len(missing_rows) == 1
    assert missing_rows[0].status == ClassificationRunStatus.PENDING
    assert missing_rows[0].id in enqueue.calls
    failed_row = _classification_rows(session, failed_document.id)[0]
    running_row = _classification_rows(session, running_document.id)[0]
    assert failed_row.status == ClassificationRunStatus.FAILED
    assert running_row.status == ClassificationRunStatus.RUNNING
    assert (
        _classification_rows(session, completed_document.id)[0].status
        == ClassificationRunStatus.COMPLETED
    )
    assert _classification_rows(session, other_document.id) == []
