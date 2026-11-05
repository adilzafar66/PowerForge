"""Real PostgreSQL publication/loader/read tests, without production providers or scheduling."""

from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from documents_support import client
from extraction_support import url
from powerforge_extraction.contracts import CandidateEvidenceInput
from powerforge_extraction.engineering_sources import page_spec_for_unit
from powerforge_extraction.enums import ExtractionMethod
from powerforge_extraction.grounding import load_page_sources
from powerforge_extraction.models import (
    ExtractedTable,
    ExtractionCandidate,
    ExtractionRun,
    ExtractionWorkUnit,
)
from powerforge_extraction.persistence import ExtractionPersistence
from powerforge_extraction.table_grounding import convert_table_reconstruction
from powerforge_extraction.table_output import convert_table_interpretation
from powerforge_extraction.table_sources import load_table_context
from table_grounding_support import claims, schedule
from table_publication_support import plan

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("visual", [False, True])
def test_committed_table_cells_publish_exact_http_values_and_evidence_with_no_canonical_writes(
    ctx, visual
):
    recon, source_text = schedule(visual=visual)
    src, rid, reconstruction, interpretation, factory, recon = plan(
        ctx, reconstruction=recon, text=source_text, image=visual
    )
    with factory.begin() as session:
        before = session.execute(
            text("SELECT updated_at FROM project_revisions WHERE id=:id"),
            {"id": ctx["revision_id"]},
        ).scalar()
        sources = load_page_sources(page_spec_for_unit(session, reconstruction), ctx["storage"])
        output = convert_table_reconstruction(recon, sources)
        target = load_page_sources(page_spec_for_unit(session, interpretation), ctx["storage"])
        with pytest.raises(ValueError, match="completed"):
            load_table_context(session, target, reconstruction)
        ExtractionPersistence(session, ctx["storage"]).publish(reconstruction, output)
    with factory.begin() as session:
        target = load_page_sources(page_spec_for_unit(session, interpretation), ctx["storage"])
        context = load_table_context(session, target, reconstruction)
        result = convert_table_interpretation(claims(), target, context)
        ExtractionPersistence(session, ctx["storage"]).publish(interpretation, result)
        session.get(ExtractionRun, rid).status = "COMPLETED"
        assert (
            session.scalar(
                text("SELECT count(*) FROM equipment WHERE revision_id=:id"),
                {"id": ctx["revision_id"]},
            )
            == 0
        )
        assert (
            session.execute(
                text("SELECT updated_at FROM project_revisions WHERE id=:id"),
                {"id": ctx["revision_id"]},
            ).scalar()
            == before
        )
    base = url(ctx, src)
    response = client.get(base + f"/runs/{rid}/tables")
    assert response.status_code == 200 and response.json()["total"] == 1
    table = response.json()["items"][0]
    assert table["layout"]["cells"][7]["text"] == "600"
    response = client.get(base + f"/runs/{rid}/candidates")
    assert response.status_code == 200, response.text
    a = next(c for c in response.json()["items"] if c["attribute_key"] == "secondary_voltage")
    assert a["numeric_value"] == "0.6" and a["raw_unit"] == "V" and a["unit"] == "kV"
    primary = next(c["evidence"] for c in a["evidence"] if c["role"] == "PRIMARY")
    assert primary["source_kind"] == "TABLE_CELL" and primary["table_id"] == table["id"]
    assert primary["cell_id"] == "c1_3"
    detail = client.get(base + f"/evidence/{primary['id']}").json()
    assert detail["grounding_precision"] == ("VISUAL_PAGE" if visual else "TEXT_OFFSETS")
    assert detail["artifact_url"] and "storage_key" not in detail
    if visual:
        assert (
            detail["text_start"] is None
            and detail["source_snippet"] is None
            and detail["region"] is None
        )
    else:
        assert target.text[detail["text_start"] : detail["text_end"]] == "600"
    with factory() as session:
        assert (
            len(list(session.scalars(select(ExtractedTable).where(ExtractedTable.run_id == rid))))
            == 1
        )


def test_bad_second_stage_publication_rolls_back_while_committed_tables_remain(ctx):
    src, rid, reconstruction, interpretation, factory, recon = plan(ctx)
    with factory.begin() as session:
        sources = load_page_sources(page_spec_for_unit(session, reconstruction), ctx["storage"])
        first = convert_table_reconstruction(recon, sources)
        ExtractionPersistence(session, ctx["storage"]).publish(reconstruction, first)
    with factory.begin() as session:
        target = load_page_sources(page_spec_for_unit(session, interpretation), ctx["storage"])
        result = convert_table_interpretation(
            claims(), target, load_table_context(session, target, reconstruction)
        )
        broken = result.model_copy(
            update={
                "candidate_evidence": [
                    *result.candidate_evidence,
                    CandidateEvidenceInput(
                        candidate_id=result.candidates[0].id, evidence_id=uuid4(), position=99
                    ),
                ]
            }
        )
        with pytest.raises(DBAPIError):
            ExtractionPersistence(session, ctx["storage"]).publish(interpretation, broken)
        assert session.get(ExtractionWorkUnit, interpretation).status == "RUNNING"
        assert (
            session.scalar(
                select(func.count())
                .select_from(ExtractionCandidate)
                .where(ExtractionCandidate.run_id == rid)
            )
            == 0
        )
        assert session.get(ExtractionWorkUnit, reconstruction).status == "COMPLETED"
        assert (
            session.scalar(
                select(func.count()).select_from(ExtractedTable).where(ExtractedTable.run_id == rid)
            )
            == 1
        )
        ExtractionPersistence(session, ctx["storage"]).publish(interpretation, result)
        session.get(ExtractionRun, rid).status = "COMPLETED"


@pytest.mark.parametrize(
    "mutation", ["run", "page", "processing", "artifact", "producer", "target_stage"]
)
def test_table_loader_rejects_incompatible_prerequisite_context(ctx, mutation):
    _, _, reconstruction, interpretation, factory, recon = plan(ctx)
    with factory.begin() as session:
        sources = load_page_sources(page_spec_for_unit(session, reconstruction), ctx["storage"])
        ExtractionPersistence(session, ctx["storage"]).publish(
            reconstruction, convert_table_reconstruction(recon, sources)
        )
    with factory() as session:
        target = load_page_sources(page_spec_for_unit(session, interpretation), ctx["storage"])
        field = {
            "run": "run_id",
            "page": "page_id",
            "processing": "processing_run_id",
            "producer": "unit_id",
            "target_stage": "stage",
        }.get(mutation)
        if mutation == "artifact":
            spec = replace(target.spec, artifacts=(replace(target.spec.artifacts[0], id=uuid4()),))
        else:
            value = (
                reconstruction
                if mutation == "producer"
                else "ATTRIBUTE_EXTRACTION"
                if mutation == "target_stage"
                else uuid4()
            )
            spec = replace(target.spec, **{field: value})
        with pytest.raises(ValueError):
            load_table_context(session, replace(target, spec=spec), reconstruction)


def test_loader_revalidates_committed_layout_against_its_producer_metadata(ctx):
    _, rid, reconstruction, interpretation, factory, recon = plan(ctx)
    with factory.begin() as session:
        sources = load_page_sources(page_spec_for_unit(session, reconstruction), ctx["storage"])
        output = convert_table_reconstruction(recon, sources)
        table = output.tables[0]
        # An existing cell ID is insufficient when the declared cell location disagrees.
        bad_location = table.layout.cells[7].location.model_copy(update={"page_artifact_id": None})
        bad = output.model_copy(
            update={
                "tables": [
                    table.model_copy(
                        update={
                            "layout": table.layout.model_copy(
                                update={
                                    "cells": [
                                        c.model_copy(update={"location": bad_location})
                                        if c.id == "c1_3"
                                        else c
                                        for c in table.layout.cells
                                    ]
                                }
                            )
                        }
                    )
                ]
            }
        )
        # A page-only cell location is intentionally legal for legacy table layouts;
        # producer/source revalidation must still reject tampered 6D metadata/layout.
        ExtractionPersistence(session, ctx["storage"]).publish(reconstruction, bad)
    with factory() as session:
        target = load_page_sources(page_spec_for_unit(session, interpretation), ctx["storage"])
        with pytest.raises(ValueError, match="differs"):
            load_table_context(session, target, reconstruction)


def test_new_cell_evidence_cannot_change_its_pinned_representation(ctx):
    src, _, reconstruction, _, factory, recon = plan(ctx, image="hybrid")
    with factory.begin() as session:
        sources = load_page_sources(page_spec_for_unit(session, reconstruction), ctx["storage"])
        output = convert_table_reconstruction(recon, sources)
        # Cell 600 cannot be attached to a different pinned artifact/processing representation.
        evidence = next(e for e in output.evidence if e.cell_id == "c1_3")
        broken = evidence.model_copy(
            update={
                "location": evidence.location.model_copy(update={"page_artifact_id": src["image"]}),
                "source_snippet": None,
                "text_start": None,
                "text_end": None,
                "offset_convention": None,
                "extraction_method": ExtractionMethod.AI_VISION,
            }
        )
        bad = output.model_copy(
            update={"evidence": [broken if e.id == evidence.id else e for e in output.evidence]}
        )
        with pytest.raises(ValueError, match="artifact"):
            ExtractionPersistence(session, ctx["storage"]).publish(reconstruction, bad)


def test_same_run_cell_citation_cannot_be_reused_on_another_page(ctx):
    src, rid, reconstruction, interpretation, factory, recon = plan(ctx, second_page=True)
    with factory.begin() as session:
        sources = load_page_sources(page_spec_for_unit(session, reconstruction), ctx["storage"])
        ExtractionPersistence(session, ctx["storage"]).publish(
            reconstruction, convert_table_reconstruction(recon, sources)
        )
    with factory.begin() as session:
        target = load_page_sources(page_spec_for_unit(session, interpretation), ctx["storage"])
        output = convert_table_interpretation(
            claims(), target, load_table_context(session, target, reconstruction)
        )
        with pytest.raises(ValueError, match="page|artifact"):
            ExtractionPersistence(session, ctx["storage"]).publish(src["other_unit"], output)
        assert (
            session.scalar(
                select(func.count())
                .select_from(ExtractionCandidate)
                .where(ExtractionCandidate.run_id == rid)
            )
            == 0
        )
        assert session.get(ExtractionWorkUnit, src["other_unit"]).status == "RUNNING"
        assert session.get(ExtractionWorkUnit, reconstruction).status == "COMPLETED"


@pytest.mark.parametrize("status", ["RUNNING", "FAILED", "CANCELLED"])
def test_unsuccessful_upstream_table_cannot_be_cited_before_atomic_success(ctx, status):
    _, rid, reconstruction, interpretation, factory, recon = plan(ctx)
    with factory() as session:
        sources = load_page_sources(page_spec_for_unit(session, reconstruction), ctx["storage"])
        output = convert_table_reconstruction(recon, sources)
        table = output.tables[0]
        session.add(
            ExtractedTable(
                id=table.id,
                run_id=rid,
                document_id=sources.spec.document_id,
                processing_run_id=sources.spec.processing_run_id,
                work_unit_id=reconstruction,
                **table.model_dump(mode="json", exclude={"id"}),
            )
        )
        session.flush()
        if status != "RUNNING":
            from datetime import UTC, datetime

            unit = session.get(ExtractionWorkUnit, reconstruction)
            unit.status, unit.finished_at = status, datetime.now(UTC)
            session.flush()
        from powerforge_extraction.contracts import WorkUnitOutput

        with pytest.raises(ValueError, match="committed"):
            ExtractionPersistence(session, ctx["storage"]).publish(
                interpretation, WorkUnitOutput(evidence=[output.evidence[1]])
            )
        session.rollback()


def test_table_evidence_remains_immutable_and_uses_the_historical_artifact(ctx):
    from powerforge_document_processing.models import DocumentPage

    src, _, reconstruction, interpretation, factory, recon = plan(ctx)
    with factory.begin() as session:
        sources = load_page_sources(page_spec_for_unit(session, reconstruction), ctx["storage"])
        output = convert_table_reconstruction(recon, sources)
        ExtractionPersistence(session, ctx["storage"]).publish(reconstruction, output)
        # Reprocessing may change page metadata, but never the selected artifact.
        session.get(DocumentPage, src["page"]).native_text_char_count = 1
    with factory.begin() as session:
        target = load_page_sources(page_spec_for_unit(session, interpretation), ctx["storage"])
        context = load_table_context(session, target, reconstruction)
        result = convert_table_interpretation(claims(), target, context)
        ExtractionPersistence(session, ctx["storage"]).publish(interpretation, result)
    with factory() as session:
        for statement, uid in [
            (
                "UPDATE extracted_tables SET table_kind='UNCLASSIFIED' WHERE id=:id",
                output.tables[0].id,
            ),
            (
                "UPDATE extraction_evidence SET source_snippet='changed' WHERE id=:id",
                output.evidence[1].id,
            ),
        ]:
            with pytest.raises(DBAPIError) as error:
                with session.begin_nested():
                    session.execute(text(statement), {"id": uid})
            assert error.value.orig.sqlstate == "P0001"
            assert (
                "immutable" in str(error.value).lower() or "completed" in str(error.value).lower()
            )
    detail = client.get(url(ctx, src) + f"/evidence/{output.evidence[1].id}")
    assert detail.status_code == 200
    assert detail.json()["page_artifact_id"] == str(src["artifact"])
    assert detail.json()["artifact_url"]


def test_hybrid_cell_can_publish_both_explicit_source_representations(ctx):
    from engineering_grounding_support import anchor

    recon, source_text = schedule()
    recon["tables"][0]["anchors"].append(anchor(visual=True))
    recon["tables"][0]["cells"][7]["anchors"].append(anchor(visual=True))
    _, rid, reconstruction, interpretation, factory, recon = plan(
        ctx, reconstruction=recon, text=source_text.replace("|", " "), image="hybrid"
    )
    with factory.begin() as session:
        sources = load_page_sources(page_spec_for_unit(session, reconstruction), ctx["storage"])
        output = convert_table_reconstruction(recon, sources)
        ExtractionPersistence(session, ctx["storage"]).publish(reconstruction, output)
    with factory.begin() as session:
        target = load_page_sources(page_spec_for_unit(session, interpretation), ctx["storage"])
        context = load_table_context(session, target, reconstruction)
        result = convert_table_interpretation(claims(), target, context)
        ExtractionPersistence(session, ctx["storage"]).publish(interpretation, result)
        session.get(ExtractionRun, rid).status = "COMPLETED"
        assert result.candidates[-1].numeric_value == Decimal("0.6")
