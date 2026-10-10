from functools import lru_cache
from uuid import UUID

from celery import Celery
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from powerforge_document_processing.enqueue import PROCESS_RUN_TASK
from powerforge_document_processing.storage.base import ObjectStorage
from powerforge_shared.config import get_settings
from powerforge_shared.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)

SOFT_TIME_LIMIT_SECONDS = 600
HARD_TIME_LIMIT_SECONDS = 660
_TIMEOUT_MESSAGE = "Processing timed out"

celery_app = Celery(
    "document_worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)


class _NoopEnqueue:
    """Claim does not publish another task."""

    def enqueue_document_processing(self, run_id: UUID) -> None:
        return None


@lru_cache
def _engine():
    return create_engine(
        get_settings().database_url,
        pool_pre_ping=True,
        future=True,
    )


def _open_session() -> Session:
    factory = sessionmaker(bind=_engine(), autoflush=False, autocommit=False, future=True)
    return factory()


def mark_processing_timeout(session: Session, run_id: UUID) -> None:
    """Record PROCESSING_TIMEOUT when the soft time limit aborts a running claim."""
    from datetime import UTC, datetime

    from powerforge_document_model import ProcessingErrorCode, ProcessingRunStatus
    from powerforge_document_processing.models import DocumentProcessingRun

    session.rollback()
    run = session.get(DocumentProcessingRun, run_id)
    if run is None or run.status != ProcessingRunStatus.RUNNING:
        return
    run.status = ProcessingRunStatus.FAILED
    run.failed_at = datetime.now(UTC)
    run.error_code = ProcessingErrorCode.PROCESSING_TIMEOUT.value
    run.error_message = _TIMEOUT_MESSAGE
    session.commit()


def execute_processing_run(run_id: UUID, session: Session, storage: ObjectStorage) -> None:
    """Claim and process one run. A second call writes nothing."""
    from powerforge_document_processing.processing import ProcessingService

    service = ProcessingService(session, storage, _NoopEnqueue())
    try:
        service.claim_and_process(run_id)
    except Exception as exc:
        if exc.__class__.__name__ != "SoftTimeLimitExceeded":
            raise
        mark_processing_timeout(session, run_id)
        raise


@celery_app.task(name="document_worker.heartbeat")
def heartbeat() -> dict[str, str]:
    return {"status": "ok", "worker": "document-worker"}


@celery_app.task(
    name=PROCESS_RUN_TASK,
    soft_time_limit=SOFT_TIME_LIMIT_SECONDS,
    time_limit=HARD_TIME_LIMIT_SECONDS,
)
def process_document_run(run_id: str) -> None:
    from powerforge_document_processing.storage.factory import build_s3_storage

    session = _open_session()
    try:
        execute_processing_run(UUID(run_id), session, build_s3_storage(get_settings()))
    finally:
        session.close()
