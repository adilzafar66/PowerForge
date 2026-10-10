"""Enqueue processing for documents that have no live completed attempt.

Not a FastAPI route and not called when the API starts. ``--limit`` is required
so a bare invocation cannot walk the whole table.
"""

from __future__ import annotations

import argparse
import logging
from uuid import UUID

from sqlalchemy import create_engine, exists, or_, select
from sqlalchemy.orm import Session, sessionmaker

from powerforge_document_model import DEFAULT_PROFILE, ProcessingRunStatus
from powerforge_document_processing.enqueue import CeleryProcessingEnqueue
from powerforge_document_processing.models import Document, DocumentProcessingRun
from powerforge_document_processing.processing import (
    DocumentProcessingEnqueue,
    ProcessingService,
)
from powerforge_document_processing.storage.base import ObjectStorage
from powerforge_document_processing.storage.factory import build_s3_storage
from powerforge_shared.config import get_settings

logger = logging.getLogger(__name__)

_LIVE_BLOCK = (ProcessingRunStatus.RUNNING, ProcessingRunStatus.COMPLETED)


def select_backfill_ids(session: Session, limit: int) -> list[UUID]:
    """Documents with no compatible run, or an unclaimed pending run, oldest first."""
    profile = DEFAULT_PROFILE
    version = profile.processor_version
    digest = profile.profile_hash

    def _match(*extra: object):
        return (
            DocumentProcessingRun.document_id == Document.id,
            DocumentProcessingRun.processor_version == version,
            DocumentProcessingRun.profile_hash == digest,
            *extra,
        )

    pending = exists().where(
        *_match(DocumentProcessingRun.status == ProcessingRunStatus.PENDING)
    )
    any_run = exists().where(*_match())
    blocking = exists().where(*_match(DocumentProcessingRun.status.in_(_LIVE_BLOCK)))
    statement = (
        select(Document.id)
        .where(or_(pending, ~any_run), ~blocking)
        .order_by(Document.uploaded_at, Document.id)
        .limit(limit)
    )
    return list(session.scalars(statement).all())


def backfill_documents(
    session: Session,
    storage: ObjectStorage,
    enqueue: DocumentProcessingEnqueue,
    limit: int,
) -> int:
    """Call ``ensure`` for up to ``limit`` documents. Returns how many were selected."""
    service = ProcessingService(session, storage, enqueue, profile=DEFAULT_PROFILE)
    document_ids = select_backfill_ids(session, limit)
    for document_id in document_ids:
        service.ensure_document_processing(document_id)
    return len(document_ids)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Enqueue document processing for documents that still need a run."
    )
    parser.add_argument("--limit", type=int, required=True)
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error("--limit must be a positive integer")
    engine = create_engine(get_settings().database_url, pool_pre_ping=True, future=True)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = factory()
    try:
        count = backfill_documents(
            session,
            build_s3_storage(get_settings()),
            CeleryProcessingEnqueue(),
            args.limit,
        )
    finally:
        session.close()
        engine.dispose()
    logger.info(
        "processing backfill finished",
        extra={"count": count, "limit": args.limit},
    )


if __name__ == "__main__":
    main()
