"""Receipts retain the original preparation producer; layouts own independent immutable output."""

from uuid import UUID as PyUUID

from sqlalchemy import ForeignKeyConstraint, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from powerforge_extraction.models import OutputRecord, output_constraints
from powerforge_persistence.base import Base


def prepared_fk():
    return ForeignKeyConstraint(
        ["prepared_result_id", "document_id", "processing_run_id", "document_page_id"],
        [
            "source_enrichment_page_results.id",
            "source_enrichment_page_results.document_id",
            "source_enrichment_page_results.processing_run_id",
            "source_enrichment_page_results.document_page_id",
        ],
    )


class SourcePreparationReceipt(OutputRecord, Base):
    __tablename__ = "source_preparation_receipts"
    __table_args__ = (
        *output_constraints("source_preparation_receipts"),
        UniqueConstraint("work_unit_id"),
        prepared_fk(),
    )
    document_page_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    prepared_result_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    preparation_hash: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(Text, nullable=False)


class SourceSpatialResult(OutputRecord, Base):
    __tablename__ = "source_spatial_results"
    __table_args__ = (
        *output_constraints("source_spatial_results"),
        UniqueConstraint("work_unit_id"),
        prepared_fk(),
        UniqueConstraint("storage_key"),
    )
    document_page_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    prepared_result_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    layout_hash: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(Text, nullable=False)
    manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    usage: Mapped[dict] = mapped_column(JSONB, nullable=False)
