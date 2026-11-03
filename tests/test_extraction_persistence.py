"""Live ownership, append-only history and atomic successful publication."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from extraction_support import claim, grounded, inputs, run_and_unit, source
from powerforge_api.db import get_session_factory
from powerforge_extraction.contracts import CandidateEvidenceInput, WorkUnitInput, WorkUnitOutput
from powerforge_extraction.enums import ExtractionRunStatus, WorkUnitStatus
from powerforge_extraction.models import (
    CandidateEvidence,
    Evidence,
    ExtractionCandidate,
    ExtractionWorkUnit,
)
from powerforge_extraction.persistence import ExtractionPersistence, effective_units

pytestmark = pytest.mark.integration


def test_publish_is_atomic_and_success_immutable(ctx):
    src = source(ctx)
    with get_session_factory()() as s:
        run, unit = run_and_unit(s, src)
        output = grounded(src)
        store = ExtractionPersistence(s)
        store.publish(unit.id, output)
        s.commit()
        assert (
            s.scalar(select(func.count()).select_from(Evidence).where(Evidence.run_id == run.id))
            == 1
        )
        assert s.get(ExtractionWorkUnit, unit.id).status == WorkUnitStatus.COMPLETED
        with pytest.raises(ValueError):
            store.publish(unit.id, output)
        s.rollback()
        with pytest.raises(DBAPIError):
            s.execute(
                text("UPDATE extraction_candidates SET raw_text='changed' WHERE id=:id"),
                {"id": output.candidates[0].id},
            )
        s.rollback()


def test_failure_after_inserting_outputs_rolls_back_savepoint(ctx):
    src = source(ctx)
    with get_session_factory()() as s:
        run, unit = run_and_unit(s, src)
        s.commit()
        output = grounded(src)
        broken = output.model_copy(
            update={
                "candidate_evidence": [
                    CandidateEvidenceInput(
                        candidate_id=output.candidates[0].id, evidence_id=uuid4()
                    )
                ]
            }
        )
        with pytest.raises(DBAPIError):
            ExtractionPersistence(s).publish(unit.id, broken)
        assert s.get(ExtractionWorkUnit, unit.id).status == WorkUnitStatus.RUNNING
        assert (
            s.scalar(select(func.count()).select_from(Evidence).where(Evidence.run_id == run.id))
            == 0
        )
        assert (
            s.scalar(
                select(func.count())
                .select_from(ExtractionCandidate)
                .where(ExtractionCandidate.run_id == run.id)
            )
            == 0
        )
        s.commit()


def test_success_survives_failed_sibling_and_retry_preserves_history(ctx):
    src = source(ctx)
    with get_session_factory()() as s:
        store = ExtractionPersistence(s)
        run, success = run_and_unit(s, src)
        store.publish(success.id, grounded(src))
        _, failed = run_and_unit(s, src, key="attributes:other", run=run)
        failed.status = WorkUnitStatus.FAILED
        s.flush()
        retry = store.create_work_unit(
            run.id,
            WorkUnitInput(
                unit_key=failed.unit_key,
                stage=failed.stage,
                page_numbers=[1],
                input_artifact_ids=[src["artifact"]],
                attempt_number=2,
                retry_of_work_unit_id=failed.id,
            ),
        )
        retry.status = WorkUnitStatus.RUNNING
        s.flush()
        store.publish(retry.id, WorkUnitOutput())
        run.status = ExtractionRunStatus.COMPLETED
        s.commit()
        assert set(s.scalars(effective_units(run.id))) == {success.id, retry.id}
        assert s.get(ExtractionWorkUnit, failed.id).status == WorkUnitStatus.FAILED
        assert (
            s.scalar(
                select(func.count())
                .select_from(ExtractionCandidate)
                .where(ExtractionCandidate.run_id == run.id)
            )
            == 1
        )


def test_equivalent_active_run_prohibited_completed_allows_deliberate_reextract(ctx):
    src = source(ctx)
    with get_session_factory()() as s:
        store = ExtractionPersistence(s)
        run = store.create_run(inputs(src))
        s.commit()
        with pytest.raises(DBAPIError):
            with s.begin_nested():
                store.create_run(inputs(src))
        run, unit = run_and_unit(s, src, run=run)
        store.publish(unit.id, WorkUnitOutput())
        run.status = ExtractionRunStatus.COMPLETED
        s.commit()
        second = store.create_run(inputs(src, reextracts_run_id=run.id))
        s.commit()
        assert second.id != run.id and second.input_identity_hash == run.input_identity_hash


def test_processing_and_page_artifact_provenance(ctx):
    src, other = source(ctx), source(ctx)
    with get_session_factory()() as s:
        store = ExtractionPersistence(s)
        bad = inputs(src).model_copy(update={"processing_run_id": other["processing"]})
        with pytest.raises(ValueError):
            store.create_run(bad)
        run, unit = run_and_unit(s, src)
        for location in [other, {**src, "artifact": other["artifact"]}]:
            with pytest.raises(ValueError):
                store.publish(unit.id, grounded(location))
        assert (
            s.scalar(select(func.count()).select_from(Evidence).where(Evidence.run_id == run.id))
            == 0
        )


def test_database_rejects_cross_run_evidence_and_invalid_values(ctx):
    src, other = source(ctx), source(ctx)
    with get_session_factory()() as s:
        store = ExtractionPersistence(s)
        run, unit = run_and_unit(s, src)
        foreign_run, foreign_unit = run_and_unit(s, other)
        foreign = grounded(other)
        store.publish(foreign_unit.id, foreign)
        output = grounded(src)
        output = output.model_copy(
            update={
                "candidate_evidence": [
                    CandidateEvidenceInput(
                        candidate_id=output.candidates[0].id, evidence_id=foreign.evidence[0].id
                    )
                ]
            }
        )
        with pytest.raises(DBAPIError):
            store.publish(unit.id, output)
        for overrides in [
            dict(document_page_id=other["page"]),
            dict(page_artifact_id=other["artifact"]),
            dict(x=0, y=0, width=2, height=1),
        ]:
            with pytest.raises(DBAPIError):
                with s.begin_nested():
                    s.add(
                        Evidence(
                            run_id=run.id,
                            document_id=run.document_id,
                            processing_run_id=run.processing_run_id,
                            work_unit_id=unit.id,
                            source_kind="VISUAL_REGION",
                            extraction_method="AI_VISION",
                            **{"document_page_id": src["page"], **overrides},
                        )
                    )
                    s.flush()
        for values in [dict(confidence=2), dict(value_type="NUMBER", numeric_value="1")]:
            with pytest.raises(DBAPIError):
                with s.begin_nested():
                    s.add(
                        ExtractionCandidate(
                            run_id=run.id,
                            document_id=run.document_id,
                            processing_run_id=run.processing_run_id,
                            work_unit_id=unit.id,
                            kind="UNMAPPED_OBSERVATION",
                            mapping_status="UNMAPPED",
                            raw_text="raw",
                            **values,
                        )
                    )
                    s.flush()


def test_database_prevents_half_published_commit_and_duplicate_attempt(ctx):
    src = source(ctx)
    with get_session_factory()() as s:
        run, unit = run_and_unit(s, src)
        s.commit()
        with pytest.raises(DBAPIError):
            with s.begin_nested():
                ExtractionPersistence(s).create_work_unit(
                    run.id,
                    WorkUnitInput(
                        unit_key=unit.unit_key,
                        stage=unit.stage,
                        page_numbers=[1],
                        input_artifact_ids=[src["artifact"]],
                    ),
                )
        s.add(
            ExtractionCandidate(
                run_id=run.id,
                document_id=run.document_id,
                processing_run_id=run.processing_run_id,
                work_unit_id=unit.id,
                kind="UNMAPPED_OBSERVATION",
                mapping_status="UNMAPPED",
                raw_text="unpublished",
            )
        )
        with pytest.raises(DBAPIError):
            s.commit()
        s.rollback()
        assert (
            s.scalar(
                select(func.count())
                .select_from(ExtractionCandidate)
                .where(ExtractionCandidate.run_id == run.id)
            )
            == 0
        )


def test_structured_tables_tagless_groups_many_to_many_citations_and_telemetry(ctx):
    from powerforge_extraction.contracts import (
        AICallInput,
        EvidenceInput,
        SourceGroupInput,
        TableCell,
        TableInput,
        TableLayout,
    )
    from powerforge_extraction.models import ExtractedTable, ExtractionAICall, SourceGroup
    from powerforge_provenance.locations import SourceLocation

    src = source(ctx)
    location = SourceLocation(document_page_id=src["page"], page_artifact_id=src["artifact"])
    now = datetime.now(UTC)
    with get_session_factory()() as s:
        run, unit = run_and_unit(s, src)
        tables = [
            TableInput(
                table_kind=kind,
                source_locations=[location],
                layout=TableLayout(
                    rows=["first"],
                    columns=["parameter", "value"],
                    cells=[
                        TableCell(id="value", row=0, column=1, text="750 kVA", location=location)
                    ],
                ),
            )
            for kind in ["ATTRIBUTE_ROWS", "EQUIPMENT_ROWS"]
        ]
        evidence = [
            EvidenceInput(
                location=location,
                source_kind="TABLE_CELL",
                extraction_method="TABLE",
                table_id=t.id,
                cell_id="value",
                source_snippet="750 kVA",
            )
            for t in tables
        ]
        group = SourceGroupInput(
            local_key="tagless-transformer",
            equipment_type_hint="TWO_WINDING_TRANSFORMER",
            evidence_ids=[e.id for e in evidence],
        )
        candidates = [claim(source_group_id=group.id), claim(source_group_id=group.id)]
        links = [
            CandidateEvidenceInput(candidate_id=c.id, evidence_id=e.id, position=i)
            for c in candidates
            for i, e in enumerate(evidence)
        ]
        output = WorkUnitOutput(
            tables=tables,
            evidence=evidence,
            source_groups=[group],
            candidates=candidates,
            candidate_evidence=links,
            ai_calls=[
                AICallInput(
                    provider="fake",
                    model="fixture",
                    prompt_version="v1",
                    prompt_hash="hash",
                    schema_version="v1",
                    outcome="SUCCEEDED",
                    started_at=now,
                    finished_at=now,
                    duration_ms=0,
                    input_tokens=100,
                    cached_input_tokens=50,
                    output_tokens=10,
                    estimated_cost_usd="0.0000123456789",
                    pricing_basis="fixture-price-v1",
                )
            ],
        )
        ExtractionPersistence(s).publish(unit.id, output)
        s.commit()
        assert s.get(SourceGroup, group.id).tag_text is None
        assert s.get(ExtractedTable, tables[0].id).layout["cells"][0]["text"] == "750 kVA"
        assert (
            s.scalar(
                select(func.count())
                .select_from(CandidateEvidence)
                .where(CandidateEvidence.run_id == run.id)
            )
            == 4
        )
        assert (
            str(
                s.scalar(
                    select(ExtractionAICall.estimated_cost_usd).where(
                        ExtractionAICall.run_id == run.id
                    )
                )
            )
            == "0.0000123456789"
        )
        # A later unit may reuse the committed run-local group without mutating it.
        _, later = run_and_unit(s, src, key="attributes:later", run=run)
        ExtractionPersistence(s).publish(later.id, grounded(src, [claim(source_group_id=group.id)]))
        s.commit()


def test_failed_call_telemetry_survives_without_publishing_failed_output(ctx):
    from powerforge_extraction.contracts import AICallInput
    from powerforge_extraction.models import ExtractionAICall

    src = source(ctx)
    with get_session_factory()() as s:
        run, unit = run_and_unit(s, src)
        now = datetime.now(UTC)
        call = ExtractionPersistence(s).record_ai_call(
            unit.id,
            AICallInput(
                provider="fake",
                model="fixture",
                prompt_version="v1",
                prompt_hash="hash",
                schema_version="v1",
                outcome="FAILED",
                error_code="PROVIDER_TIMEOUT",
                started_at=now,
                finished_at=now,
                duration_ms=0,
            ),
        )
        unit.status = WorkUnitStatus.FAILED
        s.flush()
        run.status = ExtractionRunStatus.FAILED
        s.commit()
        assert s.get(ExtractionAICall, call.id).outcome == "FAILED"
        assert list(s.scalars(effective_units(run.id))) == []


def test_database_rejects_incomplete_processing_false_completion_and_input_mutation(ctx):
    from powerforge_document_processing.models import DocumentProcessingRun

    src = source(ctx)
    with get_session_factory()() as s:
        processing = s.get(DocumentProcessingRun, src["processing"])
        processing.status = "RUNNING"
        s.commit()
        # Exercise the DB precondition independently of the internal service validation.
        from powerforge_extraction.models import ExtractionRun

        data = inputs(src).model_dump(mode="json")
        with pytest.raises(DBAPIError):
            with s.begin_nested():
                s.add(ExtractionRun(**data, input_identity_hash="bad-processing", status="PENDING"))
                s.flush()
        processing.status = "COMPLETED"
        s.commit()
        run, unit = run_and_unit(s, src)
        s.commit()
        for statement in [
            "UPDATE extraction_runs SET status='COMPLETED' WHERE id=:id",
            "UPDATE extraction_runs SET prompt_hash='changed' WHERE id=:id",
        ]:
            with pytest.raises(DBAPIError):
                with s.begin_nested():
                    s.execute(text(statement), {"id": run.id})
        unit.status = WorkUnitStatus.FAILED
        s.commit()
        with pytest.raises(DBAPIError):
            with s.begin_nested():
                s.execute(
                    text("UPDATE extraction_work_units SET status='RUNNING' WHERE id=:id"),
                    {"id": unit.id},
                )
