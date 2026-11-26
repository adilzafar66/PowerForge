"""Dedicated reconciliation consumer. This app registers only the control task."""

import logging
from datetime import UTC, datetime
from time import monotonic

from sqlalchemy.orm import sessionmaker

from extraction_worker.celery_app import _engine, create_app
from powerforge_document_processing.storage.factory import build_s3_storage
from powerforge_extraction.enqueue import CONTROL_QUEUE, RECOVER_TASK, CeleryExtractionEnqueue
from powerforge_extraction.operations import reconcile_operations
from powerforge_extraction.orchestration import ExtractionCoordinator
from powerforge_shared.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
celery_app = create_app("extraction_control", settings)


def reconcile(app, *, queue_wait_ms=None):
    settings = get_settings()
    factory = sessionmaker(bind=_engine(), autoflush=False, expire_on_commit=False)
    start = monotonic()
    with factory.begin() as session:
        recovered = ExtractionCoordinator(session, settings).reconcile()
    swept = monotonic()
    if not settings.enrichment_worker_only:
        reconcile_operations(factory, settings, build_s3_storage(settings))
    advanced = monotonic()
    with factory.begin() as session:
        sent = ExtractionCoordinator(session, settings).dispatch(
            CeleryExtractionEnqueue(app), purpose=None
        )
    logger.info(
        "extraction reconciliation completed",
        extra={
            "queue_wait_ms": queue_wait_ms,
            "recovered": recovered,
            "dispatched": sent,
            "lease_sweep_ms": round((swept - start) * 1000),
            "operations_ms": round((advanced - swept) * 1000),
            "redispatch_ms": round((monotonic() - advanced) * 1000),
        },
    )


@celery_app.task(
    name=RECOVER_TASK,
    bind=True,
    ignore_result=True,
    soft_time_limit=60,
    time_limit=90,
    shared=False,
)
def reconcile_extraction(task):
    queue_wait_ms = None
    if task.request.expires:
        expires = datetime.fromisoformat(task.request.expires).astimezone(UTC)
        remaining = (expires - datetime.now(UTC)).total_seconds()
        queue_wait_ms = max(
            0, round((settings.extraction_recovery_interval_seconds - remaining) * 1000)
        )
    reconcile(celery_app, queue_wait_ms=queue_wait_ms)


celery_app.conf.beat_schedule = {
    "reconcile-extraction-and-source": {
        "task": RECOVER_TASK,
        "schedule": settings.extraction_recovery_interval_seconds,
        "options": {
            "queue": CONTROL_QUEUE,
            "expires": settings.extraction_recovery_interval_seconds,
        },
    },
}
