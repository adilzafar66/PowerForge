"""Storage for Phase 6F intent. The execution and result records are still document-scoped."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Text, func, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from powerforge_extraction.models import Record
from powerforge_persistence.base import Base


class ExtractionOperation(Record, Base):
    __tablename__ = "extraction_operations"

    project_id: Mapped[UUID]
    revision_id: Mapped[UUID]
    intent_hash: Mapped[str] = mapped_column(Text)
    policy: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OperationPreview(Base):
    __tablename__ = "extraction_operation_previews"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    revision_id: Mapped[UUID]
    plan_hash: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OperationRequest(Base):
    __tablename__ = "extraction_operation_requests"

    revision_id: Mapped[UUID] = mapped_column(primary_key=True)
    request_key: Mapped[UUID] = mapped_column(primary_key=True)
    operation_id: Mapped[UUID]
    request_hash: Mapped[str] = mapped_column(Text)


class OperationItem(Base):
    __tablename__ = "extraction_operation_items"

    operation_id: Mapped[UUID] = mapped_column(primary_key=True)
    revision_document_id: Mapped[UUID] = mapped_column(primary_key=True)
    document_id: Mapped[UUID]
    processing_run_id: Mapped[UUID]
    selection: Mapped[dict] = mapped_column(JSONB)
    layout_run_id: Mapped[UUID | None]
    extraction_run_id: Mapped[UUID | None]
    owns_extraction: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    blocked_reason: Mapped[str | None] = mapped_column(Text)


UNKNOWN_PROVIDER_OUTCOME = "EXTRACTION_PROVIDER_OUTCOME_UNKNOWN"


def managed_remote_run(session, run_id):
    return (
        session.scalar(
            select(OperationItem.operation_id)
            .where(OperationItem.extraction_run_id == run_id, OperationItem.owns_extraction)
            .limit(1)
        )
        is not None
    )
