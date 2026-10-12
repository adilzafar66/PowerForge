from __future__ import annotations

from functools import lru_cache
from uuid import UUID

from celery import Celery
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from powerforge_document_classification.enqueue import CLASSIFY_RUN_TASK
from powerforge_shared.config import Settings, get_settings
from powerforge_shared.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)

celery_app = Celery(
    "extraction_worker",
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

    def enqueue_document_classification(self, run_id: UUID) -> None:
        return None


def require_openai_credentials(chosen: Settings) -> None:
    """Refuse to start only when a live OpenAI classification worker has no key."""
    if (
        chosen.ai_classification_enabled
        and chosen.ai_provider == "openai"
        and not chosen.openai_api_key
    ):
        raise SystemExit(
            "OPENAI_API_KEY is required when classification is enabled and AI_PROVIDER=openai"
        )


@lru_cache
def _engine():
    return create_engine(get_settings().database_url, pool_pre_ping=True, future=True)


def _open_session() -> Session:
    factory = sessionmaker(bind=_engine(), autoflush=False, autocommit=False, future=True)
    return factory()


def _provider(chosen: Settings):
    if chosen.ai_provider == "fake":
        from powerforge_document_classification.fake import FakeClassificationProvider

        return FakeClassificationProvider()
    from extraction_worker.openai_classification import OpenAIClassificationProvider

    return OpenAIClassificationProvider(chosen)


def execute_classification_run(
    run_id: UUID,
    session: Session,
    storage: object,
    provider: object | None = None,
    settings: Settings | None = None,
) -> None:
    """Claim and classify one run. A second delivery does not call the provider."""
    from powerforge_document_classification.service import ClassificationService

    chosen = settings if settings is not None else get_settings()
    model = provider if provider is not None else _provider(chosen)
    service = ClassificationService(session, storage, _NoopEnqueue(), model, chosen)
    try:
        service.claim_and_classify(run_id)
    except Exception as exc:
        if exc.__class__.__name__ != "SoftTimeLimitExceeded":
            raise
        service.mark_task_timeout(run_id)
        raise


require_openai_credentials(settings)


@celery_app.task(name="extraction_worker.heartbeat")
def heartbeat() -> dict[str, str]:
    return {"status": "ok", "worker": "extraction-worker"}


@celery_app.task(
    name=CLASSIFY_RUN_TASK,
    soft_time_limit=settings.ai_classification_task_soft_time_limit_seconds,
    time_limit=settings.ai_classification_task_hard_time_limit_seconds,
)
def classify_document_run(run_id: str) -> None:
    from powerforge_document_processing.storage.factory import build_s3_storage

    session = _open_session()
    try:
        execute_classification_run(UUID(run_id), session, build_s3_storage(get_settings()))
    finally:
        session.close()
