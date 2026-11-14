"""Phase 6 derived records, separate from the canonical engineering model."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID as PyUUID

from sqlalchemy import (
    BigInteger,
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
    CandidateKind,
    EvidenceRole,
    EvidenceSourceKind,
    ExtractionMethod,
    ExtractionRunStatus,
    MappingStatus,
    TableKind,
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
    output_counts: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class SourceGroup(OutputRecord, Base):
    __tablename__ = "extraction_source_groups"
    __table_args__ = (
        *output_constraints("extraction_source_groups"),
        UniqueConstraint("run_id", "local_key", name="uq_extraction_source_groups_local_key"),
    )
    local_key: Mapped[str] = mapped_column(Text, nullable=False)
    equipment_type_hint: Mapped[str | None] = mapped_column(Text)
    tag_text: Mapped[str | None] = mapped_column(Text)
    label: Mapped[str | None] = mapped_column(Text)
    evidence_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )


class ExtractedTable(OutputRecord, Base):
    __tablename__ = "extracted_tables"
    __table_args__ = (
        *output_constraints("extracted_tables"),
        CheckConstraint(
            "layout_schema_version IN ('table-layout-v1','table-layout-v2') AND "
            "jsonb_typeof(layout) = 'object' AND "
            "jsonb_typeof(source_locations) = 'array' AND jsonb_array_length(source_locations) "
            "> 0",
            name="ck_extracted_tables_layout",
        ),
    )
    layout_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    table_kind: Mapped[TableKind] = mapped_column(
        enum_type(TableKind, "extraction_table_kind"), nullable=False
    )
    source_locations: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    evidence_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    layout: Mapped[dict] = mapped_column(JSONB, nullable=False)


class Evidence(OutputRecord, Base):
    __tablename__ = "extraction_evidence"
    __table_args__ = (
        *output_constraints("extraction_evidence"),
        ForeignKeyConstraint(
            ["document_page_id", "document_id"],
            ["document_pages.id", "document_pages.document_id"],
            name="fk_extraction_evidence_page",
        ),
        ForeignKeyConstraint(
            ["page_artifact_id", "processing_run_id", "document_page_id"],
            [
                "page_artifacts.id",
                "page_artifacts.processing_run_id",
                "page_artifacts.document_page_id",
            ],
            name="fk_extraction_evidence_artifact",
        ),
        ForeignKeyConstraint(
            ["table_id", "run_id", "document_id"],
            ["extracted_tables.id", "extracted_tables.run_id", "extracted_tables.document_id"],
            name="fk_extraction_evidence_table",
        ),
        ForeignKeyConstraint(
            ["enrichment_artifact_id", "document_id", "processing_run_id", "document_page_id"],
            [
                "source_enrichment_artifacts.id",
                "source_enrichment_artifacts.document_id",
                "source_enrichment_artifacts.processing_run_id",
                "source_enrichment_artifacts.document_page_id",
            ],
            name="fk_evidence_enriched_text",
        ),
        ForeignKeyConstraint(
            ["geometry_artifact_id", "document_id", "processing_run_id", "document_page_id"],
            [
                "source_enrichment_artifacts.id",
                "source_enrichment_artifacts.document_id",
                "source_enrichment_artifacts.processing_run_id",
                "source_enrichment_artifacts.document_page_id",
            ],
            name="fk_evidence_enriched_geometry",
        ),
        CheckConstraint(
            "source_snippet IS NULL OR char_length(source_snippet) <= 2000",
            name="ck_extraction_evidence_snippet",
        ),
        CheckConstraint(
            "(text_start IS NULL AND text_end IS NULL AND offset_convention IS NULL) OR "
            "(text_start IS NOT NULL AND text_end IS NOT NULL AND text_start >= 0 AND text_end "
            "> text_start AND num_nonnulls(page_artifact_id,enrichment_artifact_id)=1 "
            "AND offset_convention IS NOT NULL "
            "AND offset_convention = 'UNICODE_CODEPOINT')",
            name="ck_extraction_evidence_offsets",
        ),
        CheckConstraint(
            "(source_locator IS NULL AND enrichment_artifact_id IS NULL "
            "AND geometry_artifact_id IS NULL) "
            "OR (jsonb_typeof(source_locator)='object' AND "
            "octet_length(source_locator::text)<=32768 "
            "AND source_locator->>'version'='source-location-v2')",
            name="ck_evidence_enriched_locator",
        ),
        CheckConstraint(
            "(x IS NULL AND y IS NULL AND width IS NULL AND height IS NULL) OR (x IS NOT NULL "
            "AND y IS NOT NULL AND width IS NOT NULL AND height IS NOT NULL AND x >= 0 AND y >="
            " 0 AND width > 0 AND height > 0 AND x + width <= 1 AND y + height <= 1)",
            name="ck_extraction_evidence_region",
        ),
        CheckConstraint(
            "cell_id IS NULL OR table_id IS NOT NULL", name="ck_extraction_evidence_cell"
        ),
        Index("ix_extraction_evidence_page", "document_page_id"),
    )
    document_page_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    page_artifact_id: Mapped[PyUUID | None] = mapped_column(UUID(as_uuid=True))
    source_kind: Mapped[EvidenceSourceKind] = mapped_column(
        enum_type(EvidenceSourceKind, "extraction_source_kind"), nullable=False
    )
    extraction_method: Mapped[ExtractionMethod] = mapped_column(
        enum_type(ExtractionMethod, "extraction_method"), nullable=False
    )
    source_snippet: Mapped[str | None] = mapped_column(Text)
    text_start: Mapped[int | None] = mapped_column(Integer)
    text_end: Mapped[int | None] = mapped_column(Integer)
    offset_convention: Mapped[str | None] = mapped_column(Text)
    x: Mapped[Decimal | None] = mapped_column(Numeric)
    y: Mapped[Decimal | None] = mapped_column(Numeric)
    width: Mapped[Decimal | None] = mapped_column(Numeric)
    height: Mapped[Decimal | None] = mapped_column(Numeric)
    table_id: Mapped[PyUUID | None] = mapped_column(UUID(as_uuid=True))
    cell_id: Mapped[str | None] = mapped_column(Text)
    enrichment_artifact_id: Mapped[PyUUID | None] = mapped_column(UUID(as_uuid=True))
    geometry_artifact_id: Mapped[PyUUID | None] = mapped_column(UUID(as_uuid=True))
    source_locator: Mapped[dict | None] = mapped_column(JSONB)


class ExtractionCandidate(OutputRecord, Base):
    __tablename__ = "extraction_candidates"
    __table_args__ = (
        *output_constraints("extraction_candidates"),
        ForeignKeyConstraint(
            ["source_group_id", "run_id", "document_id"],
            [
                "extraction_source_groups.id",
                "extraction_source_groups.run_id",
                "extraction_source_groups.document_id",
            ],
            name="fk_extraction_candidates_group",
        ),
        ForeignKeyConstraint(
            ["equipment_mention_candidate_id", "run_id", "document_id"],
            [
                "extraction_candidates.id",
                "extraction_candidates.run_id",
                "extraction_candidates.document_id",
            ],
            name="fk_extraction_candidates_mention",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_extraction_candidates_confidence"
        ),
        CheckConstraint(
            "numeric_value IS NULL OR numeric_value::text NOT IN ('NaN','Infinity','-Infinity')",
            name="ck_extraction_candidates_finite",
        ),
        CheckConstraint(
            "char_length(raw_text) BETWEEN 1 AND 2000 AND (raw_value IS NULL OR "
            "char_length(raw_value) <= 2000) AND (explanation IS NULL OR "
            "char_length(explanation) <= 1000) AND octet_length(diagnostics::text) <= 16000",
            name="ck_extraction_candidates_bounded",
        ),
        CheckConstraint(
            "(mapping_status = 'MAPPED' AND kind = 'ATTRIBUTE_VALUE' AND equipment_type_key IS "
            "NOT NULL AND attribute_key IS NOT NULL AND value_type IS NOT NULL AND "
            "num_nonnulls(numeric_value, integer_value, text_value, boolean_value) = 1 AND "
            "((value_type = 'NUMBER' AND numeric_value IS NOT NULL) OR (value_type = 'INTEGER' "
            "AND integer_value IS NOT NULL) OR (value_type IN ('TEXT','ENUM') AND text_value IS"
            " NOT NULL) OR (value_type = 'BOOLEAN' AND boolean_value IS NOT NULL))) OR "
            "(num_nonnulls(numeric_value, integer_value, text_value, boolean_value) = 0 AND "
            "value_type IS NULL AND unit IS NULL AND attribute_key IS NULL AND (mapping_status "
            "<> 'MAPPED' OR (kind = 'EQUIPMENT_MENTION' AND equipment_type_key IS NOT NULL)))",
            name="ck_extraction_candidates_typed",
        ),
        CheckConstraint(
            "equipment_mention_candidate_id IS NULL OR (equipment_mention_candidate_id <> id "
            "AND kind <> 'EQUIPMENT_MENTION')",
            name="ck_extraction_candidates_not_self",
        ),
        Index("ix_extraction_candidates_filters", "run_id", "mapping_status", "kind", "id"),
        Index("ix_extraction_candidates_group", "source_group_id"),
    )
    kind: Mapped[CandidateKind] = mapped_column(
        enum_type(CandidateKind, "extraction_candidate_kind"), nullable=False
    )
    mapping_status: Mapped[MappingStatus] = mapped_column(
        enum_type(MappingStatus, "extraction_mapping_status"), nullable=False
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    raw_value: Mapped[str | None] = mapped_column(Text)
    raw_unit: Mapped[str | None] = mapped_column(Text)
    observed_tag: Mapped[str | None] = mapped_column(Text)
    equipment_type_key: Mapped[str | None] = mapped_column(Text)
    attribute_key: Mapped[str | None] = mapped_column(Text)
    value_type: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(Text)
    source_group_id: Mapped[PyUUID | None] = mapped_column(UUID(as_uuid=True))
    equipment_mention_candidate_id: Mapped[PyUUID | None] = mapped_column(UUID(as_uuid=True))
    numeric_value: Mapped[Decimal | None] = mapped_column(Numeric)
    integer_value: Mapped[int | None] = mapped_column(BigInteger)
    text_value: Mapped[str | None] = mapped_column(Text)
    boolean_value: Mapped[bool | None] = mapped_column(Boolean)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric)
    confidence_band: Mapped[str | None] = mapped_column(Text)
    confidence_method: Mapped[str | None] = mapped_column(Text)
    reason_code: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    diagnostics: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class CandidateEvidence(OutputRecord, Base):
    __tablename__ = "candidate_evidence"
    __table_args__ = (
        *output_constraints("candidate_evidence"),
        UniqueConstraint("candidate_id", "evidence_id", name="uq_candidate_evidence_link"),
        ForeignKeyConstraint(
            ["candidate_id", "run_id", "document_id"],
            [
                "extraction_candidates.id",
                "extraction_candidates.run_id",
                "extraction_candidates.document_id",
            ],
            name="fk_candidate_evidence_candidate",
        ),
        ForeignKeyConstraint(
            ["evidence_id", "run_id", "document_id"],
            [
                "extraction_evidence.id",
                "extraction_evidence.run_id",
                "extraction_evidence.document_id",
            ],
            name="fk_candidate_evidence_evidence",
        ),
        CheckConstraint("position >= 0", name="ck_candidate_evidence_position"),
        Index("ix_candidate_evidence_evidence", "evidence_id"),
    )
    candidate_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evidence_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    role: Mapped[EvidenceRole] = mapped_column(
        enum_type(EvidenceRole, "extraction_evidence_role"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)


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
