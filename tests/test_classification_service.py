"""Classification settings, fake provider, and run lifecycle."""

from __future__ import annotations

import ast
import hashlib
import inspect
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from powerforge_ai.providers import (
    ClassificationImageInput,
    ClassifyDocumentRequest,
    ClassifyPageInput,
    ClassifyPagesRequest,
)
from powerforge_document_classification.errors import (
    ClassificationErrorCode,
    ClassificationProviderError,
)
from powerforge_document_classification.fake import (
    FAKE_CACHED_INPUT_TOKENS,
    FAKE_INPUT_TOKENS,
    FAKE_LATENCY_MS,
    FAKE_MODEL,
    FAKE_OUTPUT_TOKENS,
    FAKE_PROVIDER,
    FAKE_REASONING_TOKENS,
    FAKE_RESPONSE_ID,
    FakeClassificationProvider,
)
from powerforge_document_classification.identity import classifier_identity_hash
from powerforge_document_classification.service import (
    ClassificationDisabled,
    ClassificationInProgress,
    ClassificationNotRetryable,
    ClassificationService,
    ProcessingNotComplete,
    classification_profile,
)
from powerforge_document_model import (
    DEFAULT_PROFILE,
    ClassificationCallKind,
    ClassificationRunStatus,
    ClassificationScope,
    ConfidenceBand,
    DocumentClassification,
    DocumentOrigin,
    PageArtifactType,
    ProcessingRunStatus,
    SourceUnit,
)
from powerforge_document_processing.models import (
    ClassificationAICall,
    ClassificationPrediction,
    Document,
    DocumentClassificationRun,
    DocumentPage,
    DocumentProcessingRun,
    PageArtifact,
    Project,
    ProjectRevision,
    RevisionDocument,
)
from powerforge_document_processing.storage.memory import InMemoryObjectStorage
from powerforge_shared.config import Settings, get_settings

REPO_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = REPO_ROOT / "database" / "alembic.ini"
_SECRET = "native-text-secret-token"


def test_classification_settings_use_decision_defaults() -> None:
    fields = Settings.model_fields
    assert fields["ai_classification_enabled"].default is False
    assert fields["ai_provider"].default == "fake"
    assert fields["ai_classification_model"].default == "gpt-6-luna"
    assert fields["ai_classification_reasoning_effort"].default == "none"
    assert fields["ai_classification_image_detail"].default == "low"
    assert fields["ai_classification_timeout_seconds"].default == 60
    assert fields["ai_classification_task_soft_time_limit_seconds"].default == 600
    assert fields["ai_classification_task_hard_time_limit_seconds"].default == 660
    assert fields["openai_api_key"].default is None


def test_settings_construct_without_an_api_key() -> None:
    settings = Settings()
    assert settings.ai_classification_enabled is False
    blank = Settings(openai_api_key="  ")
    assert blank.openai_api_key is None


def test_soft_task_limit_must_be_below_the_hard_limit() -> None:
    with pytest.raises(ValidationError):
        Settings(
            ai_classification_task_soft_time_limit_seconds=660,
            ai_classification_task_hard_time_limit_seconds=660,
        )
    with pytest.raises(ValidationError):
        Settings(
            ai_classification_task_soft_time_limit_seconds=700,
            ai_classification_task_hard_time_limit_seconds=660,
        )
    settings = Settings(
        ai_classification_task_soft_time_limit_seconds=600,
        ai_classification_task_hard_time_limit_seconds=660,
    )
    assert settings.ai_classification_task_soft_time_limit_seconds == 600


def test_provider_must_be_fake_or_openai() -> None:
    with pytest.raises(ValidationError):
        Settings(ai_provider="azure")


def test_image_detail_changes_the_profile_hash_and_reasoning_is_not_hashed() -> None:
    low = classification_profile(Settings(ai_classification_image_detail="low"))
    high = classification_profile(Settings(ai_classification_image_detail="high"))
    assert low.profile_hash != high.profile_hash
    assert "reasoning" not in inspect.signature(classifier_identity_hash).parameters


@pytest.mark.parametrize(
    ("filename", "predicted", "score"),
    [
        ("sheet.pdf", "SINGLE_LINE_DIAGRAM", 0.95),
        ("transformer-shop.pdf", "TRANSFORMER_SHOP_DRAWING", 0.95),
        ("mixed.pdf", "MIXED_DOCUMENT", 0.92),
        ("unknown.pdf", "UNKNOWN", 0.40),
        ("low.pdf", "PANEL_SCHEDULE", 0.50),
        ("invalid.pdf", "MIXED_DOCUMENT", 0.92),
        ("My-Mixed.PDF", "MIXED_DOCUMENT", 0.92),
        ("low-mixed.pdf", "MIXED_DOCUMENT", 0.92),
    ],
)
def test_fake_provider_reads_the_filename(filename: str, predicted: str, score: float) -> None:
    response = FakeClassificationProvider().classify_document(_document_request(filename))
    assert response.result.predicted_type == predicted
    assert response.result.confidence_score == score
    assert response.usage.provider == FAKE_PROVIDER
    assert response.usage.model == FAKE_MODEL
    assert response.usage.provider_response_id == FAKE_RESPONSE_ID
    assert response.usage.input_tokens == FAKE_INPUT_TOKENS
    assert response.usage.cached_input_tokens == FAKE_CACHED_INPUT_TOKENS
    assert response.usage.output_tokens == FAKE_OUTPUT_TOKENS
    assert response.usage.reasoning_tokens == FAKE_REASONING_TOKENS
    assert response.usage.latency_ms == FAKE_LATENCY_MS
    assert response.usage.image_count == 1


def test_fake_timeout_is_checked_before_fail() -> None:
    provider = FakeClassificationProvider()
    with pytest.raises(ClassificationProviderError) as timeout:
        provider.classify_document(_document_request("timeout-fail.pdf"))
    assert timeout.value.code == ClassificationErrorCode.PROVIDER_TIMEOUT
    with pytest.raises(ClassificationProviderError) as failed:
        provider.classify_document(_document_request("fail.pdf"))
    assert failed.value.code == ClassificationErrorCode.PROVIDER_UNAVAILABLE


def test_fake_invalid_page_uses_mixed_document_once() -> None:
    response = FakeClassificationProvider().classify_pages(_page_request("invalid.pdf"))
    assert [page.predicted_type for page in response.pages] == [
        "MIXED_DOCUMENT",
        "ELECTRICAL_DRAWING",
    ]
    assert response.usage.image_count == 1
    assert response.usage.input_tokens == FAKE_INPUT_TOKENS
    assert response.usage.latency_ms == FAKE_LATENCY_MS
    assert response.usage.provider_response_id == FAKE_RESPONSE_ID


def test_fake_provider_does_not_import_openai() -> None:
    source = Path(FakeClassificationProvider.__module__.replace(".", "/") + ".py")
    module = sys.modules[FakeClassificationProvider.__module__]
    text = Path(module.__file__ or "").read_text(encoding="utf-8")
    assert "openai" not in text.lower()
    assert source.name == "fake.py"


def test_api_package_does_not_import_extraction_worker_or_openai() -> None:
    """The API may import the classification package. It must not import the worker or OpenAI."""
    root = REPO_ROOT / "services" / "api"
    forbidden = ("extraction_worker", "openai")
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        modules: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
        for module in modules:
            assert not any(
                module == name or module.startswith(f"{name}.") for name in forbidden
            ), path
    dockerfile = (REPO_ROOT / "services" / "api" / "Dockerfile").read_text(encoding="utf-8")
    assert "-e /app/packages/document-classification" in dockerfile
    assert "openai" not in dockerfile.lower()


def _document_request(filename: str) -> ClassifyDocumentRequest:
    return ClassifyDocumentRequest(
        filename=filename,
        extension=".pdf",
        page_count=1,
        text_excerpts=[],
        images=[ClassificationImageInput(page_number=1, mime_type="image/webp", data=b"img")],
        allowed_types=("SINGLE_LINE_DIAGRAM",),
        instructions="classify",
    )


def _page_request(filename: str) -> ClassifyPagesRequest:
    return ClassifyPagesRequest(
        filename=filename,
        extension=".pdf",
        pages=[
            ClassifyPageInput(
                page_number=1,
                text="a",
                image=ClassificationImageInput(page_number=1, mime_type="image/webp", data=b"img"),
            ),
            ClassifyPageInput(page_number=2, text="b", image=None),
        ],
        allowed_types=("ELECTRICAL_DRAWING",),
        instructions="pages",
    )


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
    name = f"powerforge_cls_{uuid.uuid4().hex[:8]}"
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
        bound.rollback()
        bound.close()


class RecordingEnqueue:
    def __init__(self, error: BaseException | None = None) -> None:
        self.calls: list[uuid.UUID] = []
        self.error = error

    def enqueue_document_classification(self, run_id: uuid.UUID) -> None:
        self.calls.append(run_id)
        if self.error is not None:
            raise self.error


class RecordingProvider(FakeClassificationProvider):
    def __init__(self) -> None:
        self.document_requests: list[ClassifyDocumentRequest] = []
        self.page_requests: list[ClassifyPagesRequest] = []

    def classify_document(self, request: ClassifyDocumentRequest):
        self.document_requests.append(request)
        return super().classify_document(request)

    def classify_pages(self, request: ClassifyPagesRequest):
        self.page_requests.append(request)
        return super().classify_pages(request)


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {"ai_classification_enabled": True, "ai_provider": "fake"}
    values.update(overrides)
    return Settings(**values)


def _service(
    session: Session,
    storage: InMemoryObjectStorage,
    provider: FakeClassificationProvider | None = None,
    enqueue: RecordingEnqueue | None = None,
    settings: Settings | None = None,
) -> tuple[ClassificationService, RecordingEnqueue, FakeClassificationProvider]:
    port = enqueue or RecordingEnqueue()
    model = provider or RecordingProvider()
    service = ClassificationService(
        session,
        storage,
        port,
        model,
        settings if settings is not None else _settings(),
    )
    return service, port, model


@dataclass
class Ready:
    document: Document
    processing: DocumentProcessingRun
    pages: dict[int, DocumentPage]
    thumb_keys: dict[int, str]
    text_keys: dict[int, str]


def _ready(
    session: Session,
    storage: InMemoryObjectStorage,
    *,
    filename: str = "sheet.pdf",
    pages_total: int = 1,
    extra_pages: int = 0,
    status: ProcessingRunStatus = ProcessingRunStatus.COMPLETED,
    thumbnails: bool = True,
    texts: dict[int, str] | None = None,
    document_type: DocumentClassification | None = None,
) -> Ready:
    project = Project(project_number=uuid.uuid4().hex[:12], project_name="Tower")
    session.add(project)
    session.flush()
    document_id = uuid.uuid4()
    payload = b"%PDF-1.4\nclassification"
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
    session.flush()
    storage.put(storage_key, BytesIO(payload), len(payload), "application/pdf")
    processing = DocumentProcessingRun(
        document_id=document.id,
        processor_version=DEFAULT_PROFILE.processor_version,
        profile_version=DEFAULT_PROFILE.profile_version,
        profile_hash=DEFAULT_PROFILE.profile_hash,
        status=status,
        pages_total=pages_total,
        pages_processed=pages_total if status == ProcessingRunStatus.COMPLETED else 0,
        attempt_count=1,
    )
    session.add(processing)
    session.flush()
    pages: dict[int, DocumentPage] = {}
    thumb_keys: dict[int, str] = {}
    text_keys: dict[int, str] = {}
    bodies = texts or {}
    for number in range(1, pages_total + extra_pages + 1):
        page = DocumentPage(
            document_id=document.id,
            page_number=number,
            source_width=Decimal("612"),
            source_height=Decimal("792"),
            source_unit=SourceUnit.POINTS,
            rotation_degrees=0,
            native_text_char_count=999 if number in bodies else 0,
        )
        session.add(page)
        session.flush()
        pages[number] = page
        if thumbnails:
            thumb = b"RIFF\x00\x00\x00\x00WEBP" + bytes([number])
            key = f"projects/{project.id}/runs/{processing.id}/pages/{number}/thumbnail"
            _put_artifact(
                session,
                storage,
                page,
                processing,
                PageArtifactType.THUMBNAIL,
                key,
                thumb,
                "image/webp",
            )
            thumb_keys[number] = key
        if number in bodies:
            encoded = bodies[number].encode()
            key = f"projects/{project.id}/runs/{processing.id}/pages/{number}/text"
            _put_artifact(
                session,
                storage,
                page,
                processing,
                PageArtifactType.NATIVE_TEXT,
                key,
                encoded,
                "text/plain",
            )
            text_keys[number] = key
    if document_type is not None:
        _revision(session, document, "A", document_type)
    session.commit()
    return Ready(document, processing, pages, thumb_keys, text_keys)


def _put_artifact(
    session: Session,
    storage: InMemoryObjectStorage,
    page: DocumentPage,
    processing: DocumentProcessingRun,
    artifact_type: PageArtifactType,
    key: str,
    payload: bytes,
    mime_type: str,
) -> None:
    storage.put(key, BytesIO(payload), len(payload), mime_type)
    session.add(
        PageArtifact(
            document_page_id=page.id,
            processing_run_id=processing.id,
            artifact_type=artifact_type,
            storage_key=key,
            mime_type=mime_type,
            size_bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        )
    )


def _revision(
    session: Session,
    document: Document,
    identifier: str,
    document_type: DocumentClassification,
) -> None:
    revision = ProjectRevision(project_id=document.project_id, identifier=identifier)
    session.add(revision)
    session.flush()
    session.add(
        RevisionDocument(
            project_id=document.project_id,
            revision_id=revision.id,
            document_id=document.id,
            origin=DocumentOrigin.UPLOADED,
            document_type=document_type,
        )
    )


def _runs(session: Session, document_id: uuid.UUID) -> list[DocumentClassificationRun]:
    return list(
        session.scalars(
            select(DocumentClassificationRun)
            .where(DocumentClassificationRun.document_id == document_id)
            .order_by(DocumentClassificationRun.attempt_number)
        ).all()
    )


def _predictions(session: Session, run_id: uuid.UUID) -> list[ClassificationPrediction]:
    return list(
        session.scalars(
            select(ClassificationPrediction).where(
                ClassificationPrediction.classification_run_id == run_id
            )
        ).all()
    )


def _calls(session: Session, run_id: uuid.UUID) -> list[ClassificationAICall]:
    return list(
        session.scalars(
            select(ClassificationAICall)
            .where(ClassificationAICall.classification_run_id == run_id)
            .order_by(ClassificationAICall.created_at)
        ).all()
    )


def _finish(
    session: Session,
    storage: InMemoryObjectStorage,
    ready: Ready,
) -> tuple[ClassificationService, RecordingEnqueue, RecordingProvider, DocumentClassificationRun]:
    service, enqueue, provider = _service(session, storage)
    assert isinstance(provider, RecordingProvider)
    run = service.ensure_document_classification(ready.document.id)
    service.claim_and_classify(run.id)
    stored = session.get(DocumentClassificationRun, run.id)
    assert stored is not None
    return service, enqueue, provider, stored


@pytest.mark.parametrize(
    "status",
    [ProcessingRunStatus.PENDING, ProcessingRunStatus.RUNNING, ProcessingRunStatus.FAILED],
)
def test_incomplete_processing_inserts_nothing(
    session: Session, status: ProcessingRunStatus
) -> None:
    storage = InMemoryObjectStorage()
    ready = _ready(session, storage, status=status)
    service, _, _ = _service(session, storage)
    with pytest.raises(ProcessingNotComplete):
        service.ensure_document_classification(ready.document.id)
    assert _runs(session, ready.document.id) == []


def test_completed_processing_inserts_a_pending_run(session: Session) -> None:
    storage = InMemoryObjectStorage()
    ready = _ready(session, storage)
    service, enqueue, _ = _service(session, storage)
    run = service.ensure_document_classification(ready.document.id)
    assert run.status == ClassificationRunStatus.PENDING
    assert run.prompt_version == "document_classifier_v1+page_classifier_v1"
    assert run.provider == "fake"
    assert run.model == "gpt-6-luna"
    assert enqueue.calls == [run.id]
    assert len(_runs(session, ready.document.id)) == 1


def test_pages_above_pages_total_are_ignored_and_text_comes_from_the_artifact(
    session: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="powerforge_document_classification.service")
    storage = InMemoryObjectStorage()
    long_text = _SECRET + ("x" * 3000)
    ready = _ready(
        session,
        storage,
        pages_total=2,
        extra_pages=1,
        texts={1: long_text, 3: "only-on-page-three"},
        document_type=DocumentClassification.BREAKER_DOCUMENT,
    )
    _service_result = _finish(session, storage, ready)
    _service, _enqueue, provider, run = _service_result
    assert run.status == ClassificationRunStatus.COMPLETED
    request = provider.document_requests[0]
    assert request.page_count == 2
    assert {excerpt.page_number for excerpt in request.text_excerpts} <= {1, 2}
    assert {image.page_number for image in request.images} <= {1, 2}
    page_one = next(excerpt for excerpt in request.text_excerpts if excerpt.page_number == 1)
    assert page_one.text == long_text[:2000]
    page_two = next(excerpt for excerpt in request.text_excerpts if excerpt.page_number == 2)
    assert page_two.text == ""
    assert "only-on-page-three" not in request.model_dump_json()
    evidence = request.model_dump(exclude={"allowed_types", "instructions"})
    assert "BREAKER_DOCUMENT" not in str(evidence)
    assert "document_type" not in ClassifyDocumentRequest.model_fields
    assert request.images[0].mime_type == "image/webp"
    reads = storage.calls_for("get")
    assert ready.document.storage_key not in reads
    assert ready.thumb_keys[3] not in reads
    assert ready.text_keys[3] not in reads
    assert caplog.records
    for record in caplog.records:
        values = " ".join(str(value) for value in record.__dict__.values())
        blob = f"{record.getMessage()} {values}"
        assert _SECRET not in blob
        assert ready.document.storage_key not in blob


def test_missing_thumbnail_is_artifact_unavailable(session: Session) -> None:
    storage = InMemoryObjectStorage()
    ready = _ready(session, storage, thumbnails=False)
    service, _, provider = _service(session, storage)
    assert isinstance(provider, RecordingProvider)
    run = service.ensure_document_classification(ready.document.id)
    service.claim_and_classify(run.id)
    stored = session.get(DocumentClassificationRun, run.id)
    assert stored is not None
    assert stored.status == ClassificationRunStatus.FAILED
    assert stored.error_code == ClassificationErrorCode.ARTIFACT_UNAVAILABLE.value
    assert provider.document_requests == []
    assert _predictions(session, run.id) == []


def test_high_confidence_skips_page_classification_and_stores_usage(session: Session) -> None:
    storage = InMemoryObjectStorage()
    ready = _ready(session, storage, filename="sheet.pdf")
    service, _, provider, run = _finish(session, storage, ready)
    assert isinstance(provider, RecordingProvider)
    assert provider.page_requests == []
    assert run.status == ClassificationRunStatus.COMPLETED
    assert run.requires_page_classification is False
    assert run.pages_total == 0
    suggestion = service.latest_completed_document_prediction(ready.document.id)
    assert suggestion is not None
    assert suggestion.predicted_type == DocumentClassification.SINGLE_LINE_DIAGRAM
    assert suggestion.confidence_band == ConfidenceBand.HIGH
    calls = _calls(session, run.id)
    assert len(calls) == 1
    call = calls[0]
    assert call.call_kind == ClassificationCallKind.DOCUMENT
    assert call.page_numbers is None
    assert call.provider == FAKE_PROVIDER
    assert call.model == FAKE_MODEL
    assert call.provider_response_id == FAKE_RESPONSE_ID
    assert call.input_tokens == FAKE_INPUT_TOKENS
    assert call.cached_input_tokens == FAKE_CACHED_INPUT_TOKENS
    assert call.output_tokens == FAKE_OUTPUT_TOKENS
    assert call.reasoning_tokens == FAKE_REASONING_TOKENS
    assert call.image_count == 1
    assert call.latency_ms == FAKE_LATENCY_MS
    assert "estimated_cost_usd" not in ClassificationAICall.__table__.columns
    assert "pricing_version" not in ClassificationAICall.__table__.columns


@pytest.mark.parametrize(
    ("filename", "predicted"),
    [
        ("mixed.pdf", DocumentClassification.MIXED_DOCUMENT),
        ("unknown.pdf", DocumentClassification.UNKNOWN),
        ("low.pdf", DocumentClassification.PANEL_SCHEDULE),
    ],
)
def test_uncertain_documents_classify_every_expected_page(
    session: Session,
    filename: str,
    predicted: DocumentClassification,
) -> None:
    storage = InMemoryObjectStorage()
    ready = _ready(session, storage, filename=filename, pages_total=2)
    _service, _enqueue, provider, run = _finish(session, storage, ready)
    assert isinstance(provider, RecordingProvider)
    assert run.status == ClassificationRunStatus.COMPLETED
    assert run.requires_page_classification is True
    assert run.pages_total == 2
    assert run.pages_classified == 2
    document_prediction = next(
        item
        for item in _predictions(session, run.id)
        if item.scope == ClassificationScope.DOCUMENT
    )
    page_predictions = [
        item for item in _predictions(session, run.id) if item.scope == ClassificationScope.PAGE
    ]
    assert document_prediction.predicted_type == predicted
    assert len(page_predictions) == 2
    assert {item.document_page_id for item in page_predictions} == {
        ready.pages[1].id,
        ready.pages[2].id,
    }
    assert len(provider.page_requests) == 1
    assert [page.page_number for page in provider.page_requests[0].pages] == [1, 2]


def test_bad_page_result_keeps_the_document_prediction_off_the_suggestion(session: Session) -> None:
    storage = InMemoryObjectStorage()
    ready = _ready(session, storage, filename="invalid.pdf", pages_total=2)
    service, _, _, run = _finish(session, storage, ready)
    assert run.status == ClassificationRunStatus.FAILED
    assert run.error_code == ClassificationErrorCode.INVALID_PROVIDER_RESPONSE.value
    stored = _predictions(session, run.id)
    assert len(stored) == 1
    assert stored[0].scope == ClassificationScope.DOCUMENT
    assert stored[0].predicted_type == DocumentClassification.MIXED_DOCUMENT
    assert service.latest_completed_document_prediction(ready.document.id) is None


def test_claim_runs_pending_to_completed_and_a_second_claim_is_idle(session: Session) -> None:
    storage = InMemoryObjectStorage()
    ready = _ready(session, storage)

    class StatusProvider(FakeClassificationProvider):
        def __init__(self) -> None:
            self.seen: list[ClassificationRunStatus] = []
            self.document_calls = 0

        def classify_document(self, request: ClassifyDocumentRequest):
            current = session.get(DocumentClassificationRun, run_id)
            assert current is not None
            self.seen.append(current.status)
            self.document_calls += 1
            return super().classify_document(request)

    provider = StatusProvider()
    service, _, _ = _service(session, storage, provider)
    pending = service.ensure_document_classification(ready.document.id)
    assert pending.status == ClassificationRunStatus.PENDING
    run_id = pending.id
    service.claim_and_classify(run_id)
    completed = session.get(DocumentClassificationRun, run_id)
    assert completed is not None
    assert provider.seen == [ClassificationRunStatus.RUNNING]
    assert completed.status == ClassificationRunStatus.COMPLETED
    assert completed.started_at is not None
    assert completed.completed_at is not None
    service.claim_and_classify(run_id)
    assert provider.document_calls == 1


@pytest.mark.parametrize(
    ("filename", "code"),
    [
        ("fail.pdf", ClassificationErrorCode.PROVIDER_UNAVAILABLE),
        ("timeout.pdf", ClassificationErrorCode.PROVIDER_TIMEOUT),
    ],
)
def test_provider_failure_and_timeout_fail_the_run(
    session: Session,
    filename: str,
    code: ClassificationErrorCode,
) -> None:
    storage = InMemoryObjectStorage()
    ready = _ready(session, storage, filename=filename)
    service, _enqueue, provider, run = _finish(session, storage, ready)
    assert isinstance(provider, RecordingProvider)
    assert run.status == ClassificationRunStatus.FAILED
    assert run.error_code == code.value
    assert _predictions(session, run.id) == []
    calls = len(provider.document_requests)
    service.claim_and_classify(run.id)
    assert len(provider.document_requests) == calls


def test_ensure_reuses_completed_and_running_reenqueues_pending_and_skips_failed(
    session: Session,
) -> None:
    storage = InMemoryObjectStorage()
    ready = _ready(session, storage, filename="sheet.pdf")
    service, enqueue, _, completed = _finish(session, storage, ready)
    assert service.ensure_document_classification(ready.document.id).id == completed.id
    assert enqueue.calls == [completed.id]

    pending_storage = InMemoryObjectStorage()
    pending_ready = _ready(session, pending_storage, filename="sheet.pdf")
    pending_service, pending_enqueue, _ = _service(session, pending_storage)
    first = pending_service.ensure_document_classification(pending_ready.document.id)
    second = pending_service.ensure_document_classification(pending_ready.document.id)
    assert first.id == second.id
    assert pending_enqueue.calls == [first.id, first.id]
    assert len(_runs(session, pending_ready.document.id)) == 1

    running = session.get(DocumentClassificationRun, first.id)
    assert running is not None
    running.status = ClassificationRunStatus.RUNNING
    session.commit()
    assert pending_service.ensure_document_classification(pending_ready.document.id).id == first.id
    assert pending_enqueue.calls == [first.id, first.id]

    failed_storage = InMemoryObjectStorage()
    failed_ready = _ready(session, failed_storage, filename="fail.pdf")
    failed_service, failed_enqueue, _, failed = _finish(session, failed_storage, failed_ready)
    assert failed.status == ClassificationRunStatus.FAILED
    again = failed_service.ensure_document_classification(failed_ready.document.id)
    assert again.id == failed.id
    assert len(_runs(session, failed_ready.document.id)) == 1
    assert failed_enqueue.calls == [failed.id]


def test_retry_reclassify_and_a_second_identity(session: Session) -> None:
    storage = InMemoryObjectStorage()
    ready = _ready(session, storage, filename="fail.pdf")
    service, _, _, failed = _finish(session, storage, ready)
    retried = service.retry_failed_classification(failed.id)
    assert retried.id != failed.id
    assert retried.retry_of_run_id == failed.id
    assert retried.status == ClassificationRunStatus.PENDING
    assert retried.attempt_number == 2
    with pytest.raises(ClassificationInProgress) as in_progress:
        service.retry_failed_classification(failed.id)
    assert in_progress.value.run_id == retried.id
    service.claim_and_classify(retried.id)
    newer = session.get(DocumentClassificationRun, retried.id)
    assert newer is not None
    assert newer.status == ClassificationRunStatus.FAILED
    with pytest.raises(ClassificationNotRetryable):
        service.retry_failed_classification(failed.id)
    newest = service.retry_failed_classification(newer.id)
    assert newest.retry_of_run_id == newer.id

    done_storage = InMemoryObjectStorage()
    done_ready = _ready(session, done_storage, filename="sheet.pdf")
    done_service, _, _, completed = _finish(session, done_storage, done_ready)
    again = done_service.reclassify_document(done_ready.document.id)
    assert again.retry_of_run_id is None
    assert again.status == ClassificationRunStatus.PENDING
    assert session.get(DocumentClassificationRun, completed.id).status == (
        ClassificationRunStatus.COMPLETED
    )
    with pytest.raises(ClassificationInProgress) as blocked:
        done_service.reclassify_document(done_ready.document.id)
    assert blocked.value.run_id == again.id

    again.status = ClassificationRunStatus.RUNNING
    session.commit()
    other = ClassificationService(
        session,
        done_storage,
        RecordingEnqueue(),
        RecordingProvider(),
        _settings(ai_classification_model="gpt-6-luna-alt"),
    )
    second_identity = other.ensure_document_classification(done_ready.document.id)
    assert second_identity.status == ClassificationRunStatus.PENDING
    assert second_identity.classifier_identity_hash != again.classifier_identity_hash
    statuses = {run.status for run in _runs(session, done_ready.document.id)}
    assert ClassificationRunStatus.COMPLETED in statuses
    assert ClassificationRunStatus.RUNNING in statuses
    assert ClassificationRunStatus.PENDING in statuses


def test_three_revisions_share_one_completed_classification(session: Session) -> None:
    storage = InMemoryObjectStorage()
    ready = _ready(session, storage)
    for identifier in ("A", "B", "C"):
        _revision(session, ready.document, identifier, DocumentClassification.STUDY_DOCUMENT)
    session.commit()
    service, _, _, completed = _finish(session, storage, ready)
    assert service.ensure_document_classification(ready.document.id).id == completed.id
    assert len(_runs(session, ready.document.id)) == 1
    associations = session.scalars(
        select(RevisionDocument).where(RevisionDocument.document_id == ready.document.id)
    ).all()
    assert len(associations) == 3


def test_disabled_mode_inserts_nothing_and_failed_enqueue_leaves_pending(session: Session) -> None:
    storage = InMemoryObjectStorage()
    ready = _ready(session, storage)
    disabled, _, _ = _service(session, storage, settings=_settings(ai_classification_enabled=False))
    with pytest.raises(ClassificationDisabled) as raised:
        disabled.ensure_document_classification(ready.document.id)
    assert raised.value.code == ClassificationErrorCode.AI_CLASSIFICATION_DISABLED
    with pytest.raises(ClassificationDisabled):
        disabled.retry_failed_classification(uuid.uuid4())
    with pytest.raises(ClassificationDisabled):
        disabled.reclassify_document(ready.document.id)
    assert _runs(session, ready.document.id) == []

    enqueue = RecordingEnqueue(error=RuntimeError("down"))
    service, _, _ = _service(session, storage, enqueue=enqueue)
    pending = service.ensure_document_classification(ready.document.id)
    assert pending.status == ClassificationRunStatus.PENDING
    assert enqueue.calls == [pending.id]
    processing = session.get(DocumentProcessingRun, ready.processing.id)
    assert processing is not None
    assert processing.status == ProcessingRunStatus.COMPLETED
    assert processing.pages_total == ready.processing.pages_total
    assert processing.pages_processed == ready.processing.pages_processed


def test_nine_pages_produce_two_page_batches(session: Session) -> None:
    storage = InMemoryObjectStorage()
    ready = _ready(session, storage, filename="mixed.pdf", pages_total=9)
    _service, _enqueue, provider, run = _finish(session, storage, ready)
    assert isinstance(provider, RecordingProvider)
    assert run.status == ClassificationRunStatus.COMPLETED
    assert run.pages_classified == 9
    assert len(provider.page_requests) == 2
    batches = [[page.page_number for page in request.pages] for request in provider.page_requests]
    assert batches == [list(range(1, 9)), [9]]
    calls = _calls(session, run.id)
    assert [call.call_kind for call in calls] == [
        ClassificationCallKind.DOCUMENT,
        ClassificationCallKind.PAGE_BATCH,
        ClassificationCallKind.PAGE_BATCH,
    ]
    assert calls[0].page_numbers is None
    assert calls[1].page_numbers == list(range(1, 9))
    assert calls[2].page_numbers == [9]
    assert calls[0].image_count == 5
    assert calls[1].image_count == 8
    assert calls[2].image_count == 1
    assert all(call.input_tokens == FAKE_INPUT_TOKENS for call in calls)


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


def test_concurrent_ensure_returns_the_winner(session: Session, scratch_engine: Engine) -> None:
    storage = InMemoryObjectStorage()
    ready = _ready(session, storage)
    factory = sessionmaker(bind=scratch_engine, expire_on_commit=False)
    holder = factory()
    loser_session = factory()
    ready_event = threading.Event()
    release = threading.Event()
    errors: list[BaseException] = []
    loser_found: list[tuple[uuid.UUID, list[uuid.UUID]]] = []

    def hold() -> None:
        try:
            service, _, _ = _service(holder, storage)
            identity = service._current_identity(ready.document.id)
            _run, inserted = service._insert_pending(
                ready.document.id,
                identity,
                retry_of_run_id=None,
            )
            assert inserted
            ready_event.set()
            assert release.wait(5)
            holder.commit()
        except Exception as exc:
            errors.append(exc)
            ready_event.set()
        finally:
            release.set()

    def lose() -> None:
        try:
            assert ready_event.wait(5)
            enqueue = RecordingEnqueue()
            service, _, _ = _service(loser_session, storage, enqueue=enqueue)
            run = service.ensure_document_classification(ready.document.id)
            loser_found.append((run.id, list(enqueue.calls)))
        except Exception as exc:
            errors.append(exc)

    holder_thread = threading.Thread(target=hold)
    loser_thread = threading.Thread(target=lose)
    holder_thread.start()
    loser_thread.start()
    assert ready_event.wait(5)
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
    runs = _runs(session, ready.document.id)
    assert len(runs) == 1
    assert loser_found == [(runs[0].id, [])]
