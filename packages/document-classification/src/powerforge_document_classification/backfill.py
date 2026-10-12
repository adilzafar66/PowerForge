"""Enqueue classification for documents whose current processing run is complete.

Not a FastAPI route and not called when the API starts. ``--limit`` is required
so a bare invocation cannot walk the whole table. Compatible completed, running,
and failed classification runs are left alone.
"""

from __future__ import annotations

import argparse
import logging
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from powerforge_document_classification.enqueue import CeleryClassificationEnqueue
from powerforge_document_classification.errors import ClassificationErrorCode
from powerforge_document_classification.fake import FakeClassificationProvider
from powerforge_document_classification.service import (
    ClassificationDisabled,
    ClassificationService,
    DocumentClassificationEnqueue,
    _identity_from_settings,
    classification_profile,
)
from powerforge_document_model import DEFAULT_PROFILE, ClassificationRunStatus, ProcessingRunStatus
from powerforge_document_processing.models import (
    Document,
    DocumentClassificationRun,
    DocumentProcessingRun,
)
from powerforge_document_processing.storage.base import ObjectStorage
from powerforge_document_processing.storage.factory import build_s3_storage
from powerforge_shared.config import Settings, get_settings

logger = logging.getLogger(__name__)

_SKIP = (ClassificationRunStatus.COMPLETED, ClassificationRunStatus.RUNNING)


def select_backfill_ids(session: Session, settings: Settings, limit: int) -> list[UUID]:
    """Oldest documents ``ensure`` would enqueue, at most ``limit`` of them."""
    profile = DEFAULT_PROFILE
    sampling = classification_profile(settings)
    statement = (
        select(Document.id, DocumentProcessingRun.id)
        .join(DocumentProcessingRun, DocumentProcessingRun.document_id == Document.id)
        .where(
            DocumentProcessingRun.processor_version == profile.processor_version,
            DocumentProcessingRun.profile_hash == profile.profile_hash,
            DocumentProcessingRun.status == ProcessingRunStatus.COMPLETED,
        )
        .order_by(Document.uploaded_at, Document.id)
    )
    selected: list[UUID] = []
    for document_id, processing_run_id in session.execute(statement):
        identity = _identity_from_settings(settings, sampling, processing_run_id)
        if not _would_enqueue(session, document_id, identity.identity_hash):
            continue
        selected.append(document_id)
        if len(selected) >= limit:
            break
    return selected


def _would_enqueue(session: Session, document_id: UUID, identity_hash: str) -> bool:
    """Match ``ensure``: enqueue only when nothing compatible exists, or pending is unclaimed."""
    statuses = set(
        session.scalars(
            select(DocumentClassificationRun.status).where(
                DocumentClassificationRun.document_id == document_id,
                DocumentClassificationRun.classifier_identity_hash == identity_hash,
            )
        ).all()
    )
    if statuses & set(_SKIP):
        return False
    if ClassificationRunStatus.PENDING in statuses or not statuses:
        return True
    return False


def backfill_documents(
    session: Session,
    storage: ObjectStorage,
    enqueue: DocumentClassificationEnqueue,
    limit: int,
    settings: Settings | None = None,
) -> int:
    """Call ``ensure`` for up to ``limit`` documents. Returns how many were selected."""
    chosen = settings if settings is not None else get_settings()
    if not chosen.ai_classification_enabled:
        raise ClassificationDisabled
    service = ClassificationService(
        session,
        storage,
        enqueue,
        FakeClassificationProvider(),
        chosen,
    )
    document_ids = select_backfill_ids(session, chosen, limit)
    for document_id in document_ids:
        service.ensure_document_classification(document_id)
    return len(document_ids)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Enqueue classification for processed documents that still need a run."
    )
    parser.add_argument("--limit", type=int, required=True)
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error("--limit must be a positive integer")
    settings = get_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = factory()
    try:
        count = backfill_documents(
            session,
            build_s3_storage(settings),
            CeleryClassificationEnqueue(),
            args.limit,
            settings,
        )
    except ClassificationDisabled:
        logger.error(
            "classification backfill requires classification to be enabled",
            extra={"error_code": ClassificationErrorCode.AI_CLASSIFICATION_DISABLED.value},
        )
        raise SystemExit(1) from None
    finally:
        session.close()
        engine.dispose()
    logger.info(
        "classification backfill finished",
        extra={"count": count, "limit": args.limit},
    )


if __name__ == "__main__":
    main()
