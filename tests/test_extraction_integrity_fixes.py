"""Review regressions: terminal parent states and exact artifact text coordinates."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from extraction_support import grounded, inputs, run_and_unit, source
from powerforge_api.db import get_session_factory
from powerforge_document_processing.models import DocumentPage, DocumentProcessingRun, PageArtifact
from powerforge_document_processing.storage.memory import StoredObject
from powerforge_extraction.contracts import WorkUnitInput, WorkUnitOutput
from powerforge_extraction.enums import ExtractionRunStatus, WorkUnitStatus
from powerforge_extraction.models import Evidence, ExtractionCandidate, ExtractionRun
from powerforge_extraction.persistence import ExtractionPersistence
from test_engineering_concurrency import wait_blocked

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "terminal,active_status",
    [
        ("PARTIALLY_COMPLETED", "RUNNING"),
        ("PARTIALLY_COMPLETED", "PENDING"),
        ("COMPLETED", "RUNNING"),
        ("COMPLETED", "PENDING"),
        ("FAILED", "RUNNING"),
        ("CANCELLED", "RUNNING"),
    ],
)
def test_terminal_run_requires_all_attempts_to_settle(ctx, terminal, active_status):
    src = source(ctx)
    with get_session_factory()() as session:
        store = ExtractionPersistence(session, ctx["storage"])
        if terminal != "FAILED":
            run, successful = run_and_unit(session, src, key="successful")
            store.publish(successful.id, WorkUnitOutput())
        else:
            run = store.create_run(inputs(src))
            run.status = ExtractionRunStatus.RUNNING
            session.flush()
        # Completion must account for optional work as well as required work.
        active = store.create_work_unit(
            run.id,
            WorkUnitInput(
                unit_key="unfinished",
                stage="attributes",
                page_numbers=[1],
                input_artifact_ids=[src["artifact"]],
                required=terminal != "COMPLETED",
            ),
        )
        active.status = WorkUnitStatus(active_status)
        session.commit()
        with pytest.raises(IntegrityError, match="Terminal extraction runs"):
            with session.begin_nested():
                session.execute(
                    text("UPDATE extraction_runs SET status=:status WHERE id=:id"),
                    {"id": run.id, "status": terminal},
                )
        assert session.get(ExtractionRun, run.id).status == ExtractionRunStatus.RUNNING
        # Rejection leaves the active attempt able to finish, rather than stuck.
        active.status = (
            WorkUnitStatus.CANCELLED
            if terminal in {"COMPLETED", "CANCELLED"}
            else WorkUnitStatus.FAILED
        )
        session.flush()
        run.status = ExtractionRunStatus(terminal)
        session.commit()
        assert session.get(ExtractionRun, run.id).status == terminal


def test_terminal_transition_waits_for_concurrent_unit_creation(ctx):
    src = source(ctx)
    factory = get_session_factory()
    with factory() as session:
        run = ExtractionPersistence(session).create_run(inputs(src))
        run.status = ExtractionRunStatus.RUNNING
        session.commit()
        run_id, engine = run.id, session.get_bind()
    started = Event()
    backend = {}

    def finish_run():
        with factory() as session:
            backend["pid"] = session.scalar(text("SELECT pg_backend_pid()"))
            started.set()
            with pytest.raises(IntegrityError, match="Terminal extraction runs"):
                session.execute(
                    text("UPDATE extraction_runs SET status='CANCELLED' WHERE id=:id"),
                    {"id": run_id},
                )
            session.rollback()

    with ThreadPoolExecutor(max_workers=1) as pool, factory() as holder:
        ExtractionPersistence(holder).create_work_unit(
            run_id,
            WorkUnitInput(
                unit_key="new",
                stage="attributes",
                page_numbers=[1],
                input_artifact_ids=[src["artifact"]],
            ),
        )
        future = pool.submit(finish_run)
        try:
            assert started.wait(5)
            wait_blocked(engine, backend["pid"])
            holder.commit()
        finally:
            holder.rollback()
        future.result(timeout=10)
    with factory() as session:
        assert session.get(ExtractionRun, run_id).status == ExtractionRunStatus.RUNNING


@pytest.mark.parametrize("newer_text", ["short", "newer longer text " * 20])
def test_offsets_use_pinned_artifact_after_page_metadata_changes(ctx, newer_text):
    original_text = "nameplate Ω🔌e\u0301 750 kVA"
    src = source(ctx, native_text=original_text)
    with get_session_factory()() as session:
        # A new processing identity shares the stable page but replaces its summary metadata.
        newer = DocumentProcessingRun(
            document_id=src["document"],
            processor_version="2",
            profile_version="v2",
            profile_hash="newer",
            status="COMPLETED",
        )
        session.add(newer)
        session.flush()
        newer_artifact = PageArtifact(
            document_page_id=src["page"],
            processing_run_id=newer.id,
            artifact_type="NATIVE_TEXT",
            storage_key=f"processing/{newer.id}/text.txt",
            mime_type="text/plain",
            size_bytes=len(newer_text.encode()),
            sha256=hashlib.sha256(newer_text.encode()).hexdigest(),
        )
        session.add(newer_artifact)
        payload = newer_text.encode("utf-8")
        ctx["storage"].put(newer_artifact.storage_key, BytesIO(payload), len(payload), "text/plain")
        session.get(DocumentPage, src["page"]).native_text_char_count = len(newer_text)
        session.commit()
        run, unit = run_and_unit(session, src)
        output = grounded(src)
        valid = output.evidence[0].model_copy(update={"text_end": len(original_text)})
        second = valid.model_copy(update={"id": uuid4()})
        store = ExtractionPersistence(session, ctx["storage"])
        # Valid old-artifact offsets survive a shorter page summary.
        # Both citations to the same artifact should use one verified read.
        store.publish(unit.id, output.model_copy(update={"evidence": [valid, second]}))
        session.commit()
        original = session.get(PageArtifact, src["artifact"])
        assert ctx["storage"].calls_for("get").count(original.storage_key) == 1
        _, next_unit = run_and_unit(session, src, key="out-of-bounds", run=run)
        invalid_output = grounded(src)
        invalid = invalid_output.evidence[0].model_copy(update={"text_end": len(original_text) + 1})
        with pytest.raises(ValueError, match="Offsets exceed the pinned text artifact"):
            store.publish(next_unit.id, invalid_output.model_copy(update={"evidence": [invalid]}))
        assert (
            session.scalar(
                select(func.count())
                .select_from(Evidence)
                .where(Evidence.work_unit_id == next_unit.id)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ExtractionCandidate)
                .where(ExtractionCandidate.work_unit_id == next_unit.id)
            )
            == 0
        )
        assert next_unit.status == WorkUnitStatus.RUNNING


def test_utf8_codepoints_across_stream_chunks_are_counted_correctly(ctx):
    original = "x" * (64 * 1024 - 1) + "🔌Ωe\u0301"
    src = source(ctx, native_text=original)
    with get_session_factory()() as session:
        _, unit = run_and_unit(session, src)
        output = grounded(src)
        evidence = output.evidence[0].model_copy(update={"text_end": len(original)})
        ExtractionPersistence(session, ctx["storage"]).publish(
            unit.id, output.model_copy(update={"evidence": [evidence]})
        )
        session.commit()
        assert session.get(Evidence, evidence.id).text_end == len(original)


@pytest.mark.parametrize("corruption", ["truncated", "changed", "invalid_utf8"])
def test_unverifiable_text_artifact_cannot_publish_offsets(ctx, corruption):
    src = source(ctx)
    with get_session_factory()() as session:
        _, unit = run_and_unit(session, src)
        artifact = session.get(PageArtifact, src["artifact"])
        original = ctx["storage"].objects[artifact.storage_key].data
        payload = {
            "truncated": original[:-1],
            "changed": b"!" + original[1:],
            "invalid_utf8": b"\xff" + original[1:],
        }[corruption]
        ctx["storage"].objects[artifact.storage_key] = StoredObject(payload, "text/plain")
        with pytest.raises(ValueError, match="Pinned text artifact"):
            ExtractionPersistence(session, ctx["storage"]).publish(unit.id, grounded(src))
        assert (
            session.scalar(
                select(func.count()).select_from(Evidence).where(Evidence.work_unit_id == unit.id)
            )
            == 0
        )
        assert unit.status == WorkUnitStatus.RUNNING


def test_offset_evidence_requires_storage_instead_of_page_count_fallback(ctx):
    src = source(ctx)
    with get_session_factory()() as session:
        _, unit = run_and_unit(session, src)
        with pytest.raises(ValueError, match="requires object storage"):
            ExtractionPersistence(session).publish(unit.id, grounded(src))
        assert unit.status == WorkUnitStatus.RUNNING
