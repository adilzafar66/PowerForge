"""Extraction execution records and call telemetry."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID as PyUUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from powerforge_extraction.enums import (
    AICallOutcome,
    ExtractionRunStatus,
    WorkUnitStatus,
)
from powerforge_persistence.base import Base


def enum_type(enum: type[Enum], name: str) -> ENUM:
    return ENUM(
        enum,
        name=name,
        create_type=False,
        values_callable=lambda members: [m.value for m in members],
    )


class Record:
    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OutputRecord(Record):
    run_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    processing_run_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    work_unit_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)


def output_constraints(table: str) -> tuple[UniqueConstraint | ForeignKeyConstraint | Index, ...]:
    return (
        UniqueConstraint("id", "run_id", "document_id", name=f"uq_{table}_owner"),
        ForeignKeyConstraint(
            ["work_unit_id", "run_id", "document_id", "processing_run_id"],
            [
                "extraction_work_units.id",
                "extraction_work_units.run_id",
                "extraction_work_units.document_id",
                "extraction_work_units.processing_run_id",
            ],
            name=f"fk_{table}_unit",
        ),
        Index(f"ix_{table}_run_unit", "run_id", "work_unit_id"),
    )


class ExtractionRun(Record, Base):
    __tablename__ = "extraction_runs"
    __table_args__ = (
        UniqueConstraint("id", "document_id", "processing_run_id", name="uq_extraction_runs_owner"),
        UniqueConstraint("id", "document_id", name="uq_extraction_runs_document"),
        ForeignKeyConstraint(
            ["processing_run_id", "document_id"],
            ["document_processing_runs.id", "document_processing_runs.document_id"],
            name="fk_extraction_runs_processing",
        ),
        ForeignKeyConstraint(
            ["reextracts_run_id", "document_id"],
            ["extraction_runs.id", "extraction_runs.document_id"],
            name="fk_extraction_runs_reextracts",
        ),
        ForeignKeyConstraint(
            ["initiated_from_revision_document_id"],
            ["revision_documents.id"],
            name="fk_extraction_runs_initiator",
        ),
        ForeignKeyConstraint(
            ["context_revision_id"], ["project_revisions.id"], name="fk_extraction_runs_context"
        ),
        CheckConstraint(
            "reextracts_run_id IS NULL OR reextracts_run_id <> id",
            name="ck_extraction_runs_not_self",
        ),
        CheckConstraint(
            "(context_revision_id IS NULL) = (context_fingerprint IS NULL)",
            name="ck_extraction_runs_context",
        ),
        CheckConstraint(
            "pages_processed >= 0 AND units_total >= 0 AND units_completed >= 0 AND "
            "units_completed <= units_total",
            name="ck_extraction_runs_progress",
        ),
        CheckConstraint(
            "jsonb_typeof(selected_pages) = 'array' AND jsonb_array_length(selected_pages) > 0 "
            "AND jsonb_typeof(stages) = 'array' AND jsonb_array_length(stages) > 0 AND "
            "jsonb_typeof(input_artifact_ids) = 'array' AND "
            "jsonb_array_length(input_artifact_ids) > 0",
            name="ck_extraction_runs_inputs",
        ),
        CheckConstraint(
            "error_message IS NULL OR char_length(error_message) <= 1000",
            name="ck_extraction_runs_error",
        ),
        Index("ix_extraction_runs_history", "document_id", "created_at", "id"),
        Index(
            "uq_extraction_runs_active",
            "document_id",
            "input_identity_hash",
            unique=True,
            postgresql_where=text("status IN ('PENDING', 'RUNNING')"),
        ),
    )
    execution_purpose: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'EXTRACTION'")
    )
    document_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    processing_run_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    initiated_from_revision_document_id: Mapped[PyUUID | None] = mapped_column(UUID(as_uuid=True))
    context_revision_id: Mapped[PyUUID | None] = mapped_column(UUID(as_uuid=True))
    requested_by: Mapped[PyUUID | None] = mapped_column(UUID(as_uuid=True))
    reextracts_run_id: Mapped[PyUUID | None] = mapped_column(UUID(as_uuid=True))
    extractor_version: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    registry_version: Mapped[str | None] = mapped_column(Text)
    profile_version: Mapped[str] = mapped_column(Text, nullable=False)
    profile_hash: Mapped[str] = mapped_column(Text, nullable=False)
    input_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    prompt_hash: Mapped[str | None] = mapped_column(Text)
    context_fingerprint: Mapped[str | None] = mapped_column(Text)
    selected_pages: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    stages: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    input_artifact_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    status: Mapped[ExtractionRunStatus] = mapped_column(
        enum_type(ExtractionRunStatus, "extraction_run_status"), nullable=False
    )
    pages_processed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    units_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    units_completed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)


class ExtractionWorkUnit(Record, Base):
    __tablename__ = "extraction_work_units"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "run_id",
            "document_id",
            "processing_run_id",
            name="uq_extraction_work_units_owner",
        ),
        UniqueConstraint("id", "run_id", "unit_key", name="uq_extraction_work_units_retry_owner"),
        UniqueConstraint(
            "run_id", "unit_key", "attempt_number", name="uq_extraction_work_units_attempt"
        ),
        ForeignKeyConstraint(
            ["run_id", "document_id", "processing_run_id"],
            [
                "extraction_runs.id",
                "extraction_runs.document_id",
                "extraction_runs.processing_run_id",
            ],
            name="fk_extraction_work_units_run",
        ),
        ForeignKeyConstraint(
            ["retry_of_work_unit_id", "run_id", "unit_key"],
            [
                "extraction_work_units.id",
                "extraction_work_units.run_id",
                "extraction_work_units.unit_key",
            ],
            name="fk_extraction_work_units_retry",
        ),
        CheckConstraint(
            "attempt_number >= 1 AND (retry_of_work_unit_id IS NULL OR retry_of_work_unit_id <>"
            " id)",
            name="ck_extraction_work_units_attempt",
        ),
        CheckConstraint(
            "jsonb_typeof(page_numbers) = 'array' AND jsonb_array_length(page_numbers) > 0 AND "
            "jsonb_typeof(input_artifact_ids) = 'array'",
            name="ck_extraction_work_units_inputs",
        ),
        CheckConstraint(
            "error_message IS NULL OR char_length(error_message) <= 1000",
            name="ck_extraction_work_units_error",
        ),
        Index(
            "uq_extraction_work_units_active",
            "run_id",
            "unit_key",
            unique=True,
            postgresql_where=text("status IN ('PENDING', 'RUNNING')"),
        ),
        Index(
            "uq_extraction_work_units_success",
            "run_id",
            "unit_key",
            unique=True,
            postgresql_where=text("status = 'COMPLETED'"),
        ),
    )
    run_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    processing_run_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    unit_key: Mapped[str] = mapped_column(Text, nullable=False)
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    retry_of_work_unit_id: Mapped[PyUUID | None] = mapped_column(UUID(as_uuid=True))
    required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    page_numbers: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    input_artifact_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    execution_metadata: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[WorkUnitStatus] = mapped_column(
        enum_type(WorkUnitStatus, "extraction_work_unit_status"), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    performance: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), deferred=True)
    output_counts: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class ExtractionAICall(OutputRecord, Base):
    __tablename__ = "extraction_ai_calls"
    __table_args__ = (
        *output_constraints("extraction_ai_calls"),
        CheckConstraint(
            "duration_ms >= 0 AND input_tokens >= 0 AND cached_input_tokens >= 0 AND "
            "output_tokens >= 0 AND finished_at >= started_at AND (cached_input_tokens IS NULL "
            "OR input_tokens IS NULL OR cached_input_tokens <= input_tokens)",
            name="ck_extraction_ai_calls_usage",
        ),
        CheckConstraint(
            "estimated_cost_usd IS NULL OR (estimated_cost_usd >= 0 AND "
            "estimated_cost_usd::text NOT IN ('NaN','Infinity','-Infinity') AND pricing_basis "
            "IS NOT NULL)",
            name="ck_extraction_ai_calls_cost",
        ),
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_hash: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    request_correlation_id: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[AICallOutcome] = mapped_column(
        enum_type(AICallOutcome, "extraction_ai_call_outcome"), nullable=False
    )
    error_code: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    validation_diagnostics: Mapped[list[dict]] = mapped_column(JSONB, server_default="[]")
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric)
    pricing_basis: Mapped[str | None] = mapped_column(Text)
