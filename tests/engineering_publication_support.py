"""Real DB plans for M3, using the existing trusted internal 6A publication boundary."""

from datetime import UTC, datetime

from extraction_support import inputs, source
from powerforge_api.db import get_session_factory
from powerforge_extraction.contracts import WorkUnitInput
from powerforge_extraction.persistence import ExtractionPersistence


def plan(ctx, text="2-Winding Transformer TX-1\nSecondary Voltage: 600 V"):
    src = source(ctx, native_text=text)
    factory = get_session_factory()
    with factory.begin() as session:
        store = ExtractionPersistence(session)
        run = store.create_run(
            inputs(src).model_copy(
                update={"stages": ["EQUIPMENT_RECOGNITION", "ATTRIBUTE_EXTRACTION"]}
            )
        )
        run.status, run.started_at = "RUNNING", datetime.now(UTC)
        session.flush()
        unit_ids = []
        for stage in run.stages:
            unit = store.create_work_unit(
                run.id,
                WorkUnitInput(
                    unit_key=f"{stage}:page:000001",
                    stage=stage,
                    page_numbers=[1],
                    input_artifact_ids=[src["artifact"]],
                ),
            )
            unit.status, unit.started_at = "RUNNING", datetime.now(UTC)
            session.flush()
            unit_ids.append(unit.id)
        return src, run.id, unit_ids[0], unit_ids[1], factory
