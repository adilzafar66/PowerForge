"""Live publication, ownership, immutable context, read precision and atomic rejection counts."""

from dataclasses import replace
from decimal import Decimal
from io import BytesIO
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from documents_support import client
from engineering_grounding_support import attribute, attributes, equipment, recognition
from engineering_publication_support import plan
from extraction_support import url
from powerforge_document_processing.models import DocumentPage, DocumentProcessingRun, PageArtifact
from powerforge_extraction.contracts import CandidateEvidenceInput
from powerforge_extraction.engineering_output import convert_attributes, convert_equipment
from powerforge_extraction.engineering_sources import load_recognition_context, page_spec_for_unit
from powerforge_extraction.grounding import load_page_sources
from powerforge_extraction.models import (
    Evidence,
    ExtractionCandidate,
    ExtractionRun,
    ExtractionWorkUnit,
)
from powerforge_extraction.persistence import ExtractionPersistence

pytestmark = pytest.mark.integration


def test_two_stage_outputs_publish_read_exact_provenance_and_never_mutate_canonical(ctx):
    src, rid, eqid, aid, factory = plan(ctx)
    with factory.begin() as session:
        before = session.execute(
            text("SELECT updated_at FROM project_revisions WHERE id=:id"),
            {"id": ctx["revision_id"]},
        ).scalar()
        eq_sources = load_page_sources(page_spec_for_unit(session, eqid), ctx["storage"])
        eq_output = convert_equipment(
            recognition(equipment("2-Winding Transformer TX-1", tag="TX-1")), eq_sources
        )
        with pytest.raises(ValueError, match="completed"):
            load_recognition_context(session, eq_sources, eqid)
        ExtractionPersistence(session, ctx["storage"]).publish(eqid, eq_output)
    with factory.begin() as session:
        sources = load_page_sources(page_spec_for_unit(session, aid), ctx["storage"])
        context = load_recognition_context(session, sources, eqid)
        result = convert_attributes(attributes(attribute()), sources, context)
        assert result.candidates[0].numeric_value == Decimal("0.6")
        assert result.candidates[0].equipment_mention_candidate_id == eq_output.candidates[0].id
        ExtractionPersistence(session, ctx["storage"]).publish(aid, result)
        session.get(ExtractionRun, rid).status = "COMPLETED"
        assert (
            session.execute(
                text("SELECT updated_at FROM project_revisions WHERE id=:id"),
                {"id": ctx["revision_id"]},
            ).scalar()
            == before
        )
        assert (
            session.scalar(
                text("SELECT count(*) FROM equipment WHERE revision_id=:id"),
                {"id": ctx["revision_id"]},
            )
            == 0
        )
    base = url(ctx, src)
    response = client.get(base + f"/runs/{rid}/candidates")
    assert response.status_code == 200, response.text
    mapped = next(
        item for item in response.json()["items"] if item["attribute_key"] == "secondary_voltage"
    )
    assert mapped["numeric_value"] == "0.6" and mapped["supported"]
    assert mapped["source_group"]["tag_text"] == "TX-1"
    assert {item["evidence"]["grounding_precision"] for item in mapped["evidence"]} == {
        "TEXT_OFFSETS"
    }
    evidence = client.get(base + f"/evidence/{result.evidence[0].id}").json()
    assert evidence["source_snippet"] == "Secondary Voltage: 600 V"
    assert evidence["text_start"] == len("2-Winding Transformer TX-1\n")
    assert evidence["grounding_precision"] == "TEXT_OFFSETS" and "storage_key" not in evidence


def test_rejections_commit_as_counts_without_invented_facts_and_roll_back_atomically(ctx):
    src, rid, eqid, aid, factory = plan(ctx)
    with factory.begin() as session:
        sources = load_page_sources(page_spec_for_unit(session, eqid), ctx["storage"])
        output = convert_equipment(recognition(equipment("not in source")), sources)
        assert output.diagnostic_counts == {"rejected_ungrounded": 1}
        broken = output.model_copy(
            update={
                "candidate_evidence": [
                    CandidateEvidenceInput(candidate_id=uuid4(), evidence_id=uuid4())
                ]
            }
        )
        with pytest.raises(DBAPIError):
            ExtractionPersistence(session, ctx["storage"]).publish(eqid, broken)
        unit = session.get(ExtractionWorkUnit, eqid)
        assert unit.status == "RUNNING" and unit.output_counts == {}
        assert (
            session.scalar(select(func.count()).select_from(Evidence).where(Evidence.run_id == rid))
            == 0
        )
        ExtractionPersistence(session, ctx["storage"]).publish(eqid, output)
    with factory() as session:
        unit = session.get(ExtractionWorkUnit, eqid)
        assert unit.status == "COMPLETED" and unit.output_counts["rejected_ungrounded"] == 1
        assert unit.output_counts["candidates"] == 0
        assert (
            session.scalar(
                select(func.count())
                .select_from(ExtractionCandidate)
                .where(ExtractionCandidate.run_id == rid)
            )
            == 0
        )
        with pytest.raises(DBAPIError):
            session.execute(
                text("UPDATE extraction_work_units SET output_counts='{}'::jsonb WHERE id=:id"),
                {"id": eqid},
            )
        session.rollback()


def test_publication_failure_after_inserted_candidates_keeps_successful_recognition_only(ctx):
    src, rid, eqid, aid, factory = plan(ctx)
    with factory.begin() as session:
        sources = load_page_sources(page_spec_for_unit(session, eqid), ctx["storage"])
        eq = convert_equipment(recognition(equipment("2-Winding Transformer TX-1")), sources)
        ExtractionPersistence(session, ctx["storage"]).publish(eqid, eq)
    with factory.begin() as session:
        sources = load_page_sources(page_spec_for_unit(session, aid), ctx["storage"])
        output = convert_attributes(
            attributes(attribute()), sources, load_recognition_context(session, sources, eqid)
        )
        # An unknown group forces rollback after evidence has already been inserted.
        bad = output.candidates[0].model_copy(update={"source_group_id": uuid4()})
        broken = output.model_copy(update={"candidates": [bad]})
        with pytest.raises(DBAPIError):
            ExtractionPersistence(session, ctx["storage"]).publish(aid, broken)
        assert session.get(ExtractionWorkUnit, aid).status == "RUNNING"
        assert (
            session.scalar(
                select(func.count())
                .select_from(ExtractionCandidate)
                .where(ExtractionCandidate.run_id == rid)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count()).select_from(Evidence).where(Evidence.work_unit_id == aid)
            )
            == 0
        )


def test_context_is_pinned_to_completed_same_run_page_and_exact_artifacts(ctx):
    src, rid, eqid, aid, factory = plan(ctx)
    with factory.begin() as session:
        sources = load_page_sources(page_spec_for_unit(session, eqid), ctx["storage"])
        eq = convert_equipment(recognition(equipment("2-Winding Transformer TX-1")), sources)
        ExtractionPersistence(session, ctx["storage"]).publish(eqid, eq)
    with factory.begin() as session:
        sources = load_page_sources(page_spec_for_unit(session, aid), ctx["storage"])
        context = load_recognition_context(session, sources, eqid)
        for field in ["run_id", "document_id", "processing_run_id", "page_id"]:
            wrong = replace(context, **{field: uuid4()})
            with pytest.raises(ValueError, match="ownership"):
                convert_attributes(attributes(attribute()), sources, wrong)
        wrong_source = replace(sources, spec=replace(sources.spec, page_id=uuid4()))
        with pytest.raises(ValueError, match="ownership"):
            load_recognition_context(session, wrong_source, eqid)
        # A later processor summary or processing run never replaces the pinned object.
        session.get(DocumentPage, src["page"]).native_text_char_count = 0
        later = DocumentProcessingRun(
            document_id=src["document"],
            processor_version="later",
            profile_version="later",
            profile_hash="later",
            status="COMPLETED",
        )
        session.add(later)
        session.flush()
        import hashlib

        payload = b"Later text version"
        newer = PageArtifact(
            document_page_id=src["page"],
            processing_run_id=later.id,
            artifact_type="NATIVE_TEXT",
            storage_key=f"processing/{later.id}/native.txt",
            mime_type="text/plain",
            size_bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        )
        session.add(newer)
        ctx["storage"].put(newer.storage_key, BytesIO(payload), len(payload), "text/plain")
        session.flush()
        loaded = load_page_sources(page_spec_for_unit(session, aid), ctx["storage"])
        assert loaded.spec.processing_run_id == src["processing"] and loaded.text == sources.text
        assert load_recognition_context(session, loaded, eqid).mentions[0].scope is not None


def test_repeated_tags_in_separate_source_blocks_have_distinct_groups_and_correct_values(ctx):
    text_body = (
        "2-Winding Transformer TX-1\nSecondary Voltage: 600 V\n\n"
        "2-Winding Transformer TX-1\nSecondary Voltage: 690 V"
    )
    src, rid, eqid, aid, factory = plan(ctx, text_body)
    with factory.begin() as session:
        sources = load_page_sources(page_spec_for_unit(session, eqid), ctx["storage"])
        eq = convert_equipment(
            recognition(
                equipment(
                    "2-Winding Transformer TX-1", tag="TX-1", suffix="\nSecondary Voltage: 600 V"
                ),
                equipment(
                    "2-Winding Transformer TX-1",
                    ref="eq2",
                    tag="TX-1",
                    suffix="\nSecondary Voltage: 690 V",
                ),
            ),
            sources,
        )
        assert len({group.id for group in eq.source_groups}) == 2
        ExtractionPersistence(session, ctx["storage"]).publish(eqid, eq)
    with factory.begin() as session:
        sources = load_page_sources(page_spec_for_unit(session, aid), ctx["storage"])
        result = convert_attributes(
            attributes(
                attribute(),
                attribute("Secondary Voltage: 690 V", ref="a2", equipment_ref="eq2", value="690"),
            ),
            sources,
            load_recognition_context(session, sources, eqid),
        )
        assert len({item.source_group_id for item in result.candidates}) == 2
        ExtractionPersistence(session, ctx["storage"]).publish(aid, result)


def test_visual_image_artifact_publication_is_page_level_and_inspectable(ctx):
    import hashlib

    from PIL import Image, ImageDraw

    src, rid, eqid, aid, factory = plan(ctx)
    content = BytesIO()
    label = Image.new("RGB", (400, 150), "white")
    ImageDraw.Draw(label).multiline_text(
        (10, 10), "Two-Winding Transformer\nSecondary Voltage: 600 V", fill="black"
    )
    label.save(content, format="PNG")
    payload = content.getvalue()
    # Use a separate exact pinned image on a fresh M3 plan, before immutable run creation.
    with factory.begin() as session:
        image = PageArtifact(
            document_page_id=src["page"],
            processing_run_id=src["processing"],
            artifact_type="ANALYSIS_IMAGE",
            storage_key=f"processing/{src['processing']}/image.png",
            mime_type="image/png",
            size_bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            width_px=400,
            height_px=150,
        )
        session.add(image)
        session.flush()
        ctx["storage"].put(image.storage_key, BytesIO(payload), len(payload), "image/png")
        # The existing run's immutable inputs cannot be changed: create a new identity.
        from extraction_support import inputs
        from powerforge_extraction.contracts import WorkUnitInput

        store = ExtractionPersistence(session)
        run = store.create_run(
            inputs(src).model_copy(
                update={
                    "profile_hash": "image-m3",
                    "stages": ["EQUIPMENT_RECOGNITION", "ATTRIBUTE_EXTRACTION"],
                    "input_artifact_ids": [image.id],
                }
            )
        )
        run.status = "RUNNING"
        session.flush()
        units = []
        for stage in run.stages:
            unit = store.create_work_unit(
                run.id,
                WorkUnitInput(
                    unit_key=f"{stage}:page:000001",
                    stage=stage,
                    page_numbers=[1],
                    input_artifact_ids=[image.id],
                ),
            )
            unit.status = "RUNNING"
            session.flush()
            units.append(unit.id)
        new_rid = run.id
        sources = load_page_sources(page_spec_for_unit(session, units[0]), ctx["storage"])
        output = convert_equipment(
            recognition(equipment("Two-Winding Transformer", visual=True)), sources
        )
        store.publish(units[0], output)
    with factory.begin() as session:
        sources = load_page_sources(page_spec_for_unit(session, units[1]), ctx["storage"])
        output = convert_attributes(
            attributes(attribute(visual=True)),
            sources,
            load_recognition_context(session, sources, units[0]),
        )
        ExtractionPersistence(session, ctx["storage"]).publish(units[1], output)
    response = client.get(url(ctx, src) + f"/runs/{new_rid}/candidates")
    assert response.status_code == 200, response.text
    for item in response.json()["items"]:
        assert item["diagnostics"]["text_verified"] is False
        assert item["evidence"][0]["evidence"]["grounding_precision"] == "VISUAL_PAGE"
    detail = client.get(url(ctx, src) + f"/evidence/{output.evidence[0].id}").json()
    assert detail["grounding_precision"] == "VISUAL_PAGE" and detail["source_snippet"] is None
    assert detail["text_start"] is None and detail["region"] is None


def test_source_factory_rejects_foreign_artifact_inputs_before_any_storage_read(ctx):
    from extraction_support import source

    src, rid, eqid, aid, factory = plan(ctx)
    foreign = source(ctx)
    with factory() as session:
        # No flush: exercise loader ownership independently of the DB mutation guard.
        unit = session.get(ExtractionWorkUnit, eqid)
        run = session.get(ExtractionRun, rid)
        unit.input_artifact_ids = [str(foreign["artifact"])]
        run.input_artifact_ids = [*run.input_artifact_ids, str(foreign["artifact"])]
        with pytest.raises(ValueError, match="ownership"):
            page_spec_for_unit(session, eqid)
        session.rollback()


@pytest.mark.parametrize("family", ["breaker", "cable"])
def test_converter_publication_and_http_preserve_false_and_large_integer(ctx, family):
    if family == "breaker":
        heading, kind, label, value, key = (
            "LV Breaker CB1",
            "LV_BREAKER",
            "Normally Closed",
            "No",
            "normally_closed",
        )
    else:
        heading, kind, label, value, key = (
            "Cable C1",
            "CABLE",
            "Parallel Run Count",
            "9007199254740993",
            "parallel_run_count",
        )
    statement = f"{label}: {value}"
    src, rid, eqid, aid, factory = plan(ctx, heading + "\n" + statement)
    with factory.begin() as session:
        sources = load_page_sources(page_spec_for_unit(session, eqid), ctx["storage"])
        output = convert_equipment(recognition(equipment(heading, proposed=kind)), sources)
        ExtractionPersistence(session, ctx["storage"]).publish(eqid, output)
    with factory.begin() as session:
        sources = load_page_sources(page_spec_for_unit(session, aid), ctx["storage"])
        output = convert_attributes(
            attributes(
                attribute(statement, label=label, value=value, unit=None, key=key, proposed=kind)
            ),
            sources,
            load_recognition_context(session, sources, eqid),
        )
        ExtractionPersistence(session, ctx["storage"]).publish(aid, output)
    response = client.get(url(ctx, src) + f"/runs/{rid}/candidates").json()
    candidate = next(item for item in response["items"] if item["attribute_key"] == key)
    if family == "breaker":
        assert candidate["boolean_value"] is False
    else:
        assert candidate["integer_value"] == value


def test_invalid_and_unmapped_observations_survive_beside_rejected_inventions(ctx):
    # The unknown field is independent; an unknown line inside the equipment block
    # would conservatively disable that block's association for every observation.
    body = "2-Winding Transformer TX-1\nSecondary Voltage: 600 A\n\nFlux alignment: 42 quux"
    src, rid, eqid, aid, factory = plan(ctx, body)
    with factory.begin() as session:
        sources = load_page_sources(page_spec_for_unit(session, eqid), ctx["storage"])
        ExtractionPersistence(session, ctx["storage"]).publish(
            eqid, convert_equipment(recognition(equipment("2-Winding Transformer TX-1")), sources)
        )
    with factory.begin() as session:
        sources = load_page_sources(page_spec_for_unit(session, aid), ctx["storage"])
        good = attribute("Secondary Voltage: 600 A", unit="A")
        unknown = attribute(
            "Flux alignment: 42 quux",
            ref="a2",
            label="Flux alignment",
            value="42",
            unit="quux",
            key="flux_alignment",
            equipment_ref=None,
        )
        invented = good.model_copy(update={"local_ref": "a3", "raw_value": "900"})
        output = convert_attributes(
            attributes(good, unknown, invented),
            sources,
            load_recognition_context(session, sources, eqid),
        )
        assert [item.mapping_status for item in output.candidates] == ["INVALID", "UNMAPPED"]
        assert all(
            item.attribute_key is None and item.numeric_value is None for item in output.candidates
        )
        assert output.diagnostic_counts == {"rejected_source_fields": 1}
        ExtractionPersistence(session, ctx["storage"]).publish(aid, output)
    detail = client.get(url(ctx, src) + f"/runs/{rid}").json()
    attempt = next(item for item in detail["attempts"] if item["id"] == str(aid))
    assert attempt["output_counts"]["rejected_source_fields"] == 1
    assert attempt["output_counts"]["candidates"] == 2
