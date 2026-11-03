"""Execution control beside immutable Phase 6A result history."""

from datetime import datetime
from uuid import UUID as PyUUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from powerforge_extraction.models import ExtractionRun as ExtractionRun
from powerforge_extraction.models import ExtractionWorkUnit as ExtractionWorkUnit
from powerforge_persistence import Base


class RunExecution(Base):
    __tablename__ = "extraction_run_execution"
    __table_args__ = (
        CheckConstraint(
            "calls_admitted >= 0 AND calls_admitted <= (configuration->>'max_calls')::int",
            name="ck_extraction_run_execution_calls",
        ),
        CheckConstraint(
            "jsonb_typeof(configuration)='object' AND octet_length(configuration::text) <= 64000",
            name="ck_extraction_run_execution_configuration",
        ),
    )
    run_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("extraction_runs.id"), primary_key=True
    )
    configuration: Mapped[dict] = mapped_column(JSONB, nullable=False)
    calls_admitted: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UnitExecution(Base):
    __tablename__ = "extraction_unit_execution"
    __table_args__ = (
        ForeignKeyConstraint(
            ["work_unit_id", "run_id", "unit_key"],
            [
                "extraction_work_units.id",
                "extraction_work_units.run_id",
                "extraction_work_units.unit_key",
            ],
            name="fk_extraction_unit_execution_owner",
        ),
        CheckConstraint("dispatch_count >= 0", name="ck_extraction_unit_execution_dispatch"),
        Index("ix_extraction_unit_execution_delivery", "dispatch_after", "available_at"),
    )
    work_unit_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    unit_key: Mapped[str] = mapped_column(nullable=False)
    token: Mapped[PyUUID | None] = mapped_column(UUID(as_uuid=True))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dispatch_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatch_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    hard_deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
