"""Write terminal stage diagnostics under the existing attempt fence."""

from uuid import UUID

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from powerforge_extraction.stage_diagnostics import StageTrace
from powerforge_persistence.base import Base


class ExtractionStageTrace(Base):
    __tablename__ = "extraction_stage_traces"

    work_unit_id: Mapped[UUID] = mapped_column(
        ForeignKey("extraction_work_units.id"), primary_key=True
    )
    trace: Mapped[dict] = mapped_column(JSONB, nullable=False)


def record_stage_trace(session, unit, trace: StageTrace | None) -> None:
    if trace is not None:
        session.add(ExtractionStageTrace(work_unit_id=unit.id, trace=trace.model_dump(mode="json")))
        # The append-only trigger requires the attempt to still be running.
        session.flush()
