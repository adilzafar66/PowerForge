"""Append extraction attempts and telemetry inside the caller's transaction."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from powerforge_extraction.contracts import AICallInput, WorkUnitInput
from powerforge_extraction.enums import WorkUnitStatus
from powerforge_extraction.models import ExtractionAICall, ExtractionRun, ExtractionWorkUnit


class ExtractionPersistence:
    def __init__(self, session: Session) -> None:
        # Complete the shared FK registry for standalone worker/service callers too.
        from importlib import import_module

        import_module("powerforge_extraction.enrichment_models")
        import_module("powerforge_extraction.layout_models")
        self.session = session

    def create_work_unit(self, run_id: UUID, inputs: WorkUnitInput) -> ExtractionWorkUnit:
        inputs = WorkUnitInput.model_validate(inputs.model_dump())
        run = self.session.scalar(
            select(ExtractionRun).where(ExtractionRun.id == run_id).with_for_update()
        )
        if run is None:
            raise ValueError("Extraction run not found")
        data = inputs.model_dump()
        data["input_artifact_ids"] = [str(i) for i in inputs.input_artifact_ids]
        unit = ExtractionWorkUnit(
            **data,
            run_id=run.id,
            document_id=run.document_id,
            processing_run_id=run.processing_run_id,
            status=WorkUnitStatus.PENDING,
        )
        self.session.add(unit)
        self.session.flush()
        run.units_total = self.session.scalar(
            select(func.count(func.distinct(ExtractionWorkUnit.unit_key))).where(
                ExtractionWorkUnit.run_id == run.id
            )
        )
        self.session.flush()
        return unit

    def record_ai_call(self, work_unit_id: UUID, call: AICallInput) -> ExtractionAICall:
        """Append technical telemetry even when the unit subsequently fails; no commit."""
        call = AICallInput.model_validate(call.model_dump())
        unit = self.session.get(ExtractionWorkUnit, work_unit_id)
        if unit is None or unit.status != WorkUnitStatus.RUNNING:
            raise ValueError("AI telemetry requires a running attempt")
        row = ExtractionAICall(
            **call.model_dump(exclude={"validation_diagnostics"}),
            validation_diagnostics=[
                issue.model_dump(mode="json") for issue in call.validation_diagnostics
            ],
            run_id=unit.run_id,
            document_id=unit.document_id,
            processing_run_id=unit.processing_run_id,
            work_unit_id=unit.id,
        )
        self.session.add(row)
        self.session.flush()
        return row
