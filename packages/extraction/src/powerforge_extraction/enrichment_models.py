"""Immutable independently owned source preparation outputs; no evidence publication."""

from uuid import UUID as PyUUID

from sqlalchemy import ForeignKeyConstraint, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from powerforge_extraction.models import OutputRecord, Record, output_constraints
from powerforge_persistence.base import Base


class SourceEnrichmentPageResult(OutputRecord, Base):
    __tablename__ = "source_enrichment_page_results"
    __table_args__ = (
        *output_constraints("source_enrichment_page_results"),
        UniqueConstraint("work_unit_id"),
        UniqueConstraint("id", "document_id", "processing_run_id", "document_page_id"),
        ForeignKeyConstraint(
            ["document_page_id", "document_id"], ["document_pages.id", "document_pages.document_id"]
        ),
    )
    document_page_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    preparation_hash: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(Text, nullable=False)
    manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    usage: Mapped[dict] = mapped_column(JSONB, nullable=False)


class SourceEnrichmentArtifact(Record, Base):
    __tablename__ = "source_enrichment_artifacts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["result_id", "document_id", "processing_run_id", "document_page_id"],
            [
                "source_enrichment_page_results.id",
                "source_enrichment_page_results.document_id",
                "source_enrichment_page_results.processing_run_id",
                "source_enrichment_page_results.document_page_id",
            ],
        ),
        UniqueConstraint("storage_key"),
        UniqueConstraint("id", "document_id", "processing_run_id", "document_page_id"),
    )
    result_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    processing_run_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_page_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    width_px: Mapped[int | None] = mapped_column(Integer)
    height_px: Mapped[int | None] = mapped_column(Integer)


class RunSourceEnrichmentBinding(Record, Base):
    __tablename__ = "run_source_enrichment_bindings"
    __table_args__ = (
        ForeignKeyConstraint(["spatial_result_id"], ["source_spatial_results.id"]),
        ForeignKeyConstraint(
            ["run_id", "document_id", "processing_run_id"],
            [
                "extraction_runs.id",
                "extraction_runs.document_id",
                "extraction_runs.processing_run_id",
            ],
        ),
        ForeignKeyConstraint(
            ["prepared_result_id", "document_id", "processing_run_id", "document_page_id"],
            [
                "source_enrichment_page_results.id",
                "source_enrichment_page_results.document_id",
                "source_enrichment_page_results.processing_run_id",
                "source_enrichment_page_results.document_page_id",
            ],
        ),
        UniqueConstraint("run_id", "document_page_id"),
    )
    run_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    processing_run_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_page_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    prepared_result_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    manifest_hash: Mapped[str] = mapped_column(Text, nullable=False)
    spatial_result_id: Mapped[PyUUID | None] = mapped_column(UUID(as_uuid=True))
    spatial_manifest_hash: Mapped[str | None] = mapped_column(Text)
    binding_hash: Mapped[str | None] = mapped_column(Text)
