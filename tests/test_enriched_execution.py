"""Real bound extraction, exact v2 evidence and conservative source semantics."""

from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select

from documents_support import client, make_revision
from enriched_support import enrich, execute, extraction_detail, finish, start_enriched
from enrichment_support import build_source, detail
from enrichment_support import enrichment_ctx as enrichment_ctx
from enrichment_support import execute as prepare
from enrichment_support import start as start_source
from powerforge_document_processing.models import RevisionDocument
from powerforge_extraction.enriched_fake import FakeEnrichedProvider
from powerforge_extraction.enrichment_models import RunSourceEnrichmentBinding
from powerforge_extraction.models import Evidence

pytestmark = pytest.mark.integration


def test_actual_positioned_pdf_publishes_supported_table_and_exact_new_native_artifact(
    enrichment_ctx,
):
    ctx = enrichment_ctx
    build_source(
        ctx, Path("evals/tables/v1/sources/positioned_schedule.pdf").read_bytes(), "schedule.pdf"
    )
    binding = enrich(ctx)
    pending = start_enriched(ctx, binding)
    rid = pending["run"]["id"]
    done = finish(ctx, pending)
    assert done["run"]["status"] == "COMPLETED", done
    assert done["execution"]["calls_admitted"] == 2
    candidates = client.get(ctx["base"] + f"/extraction/runs/{rid}/candidates").json()["items"]
    assert len(candidates) == 2, candidates
    value = next(c for c in candidates if c["kind"] == "ATTRIBUTE_VALUE")
    assert value["mapping_status"] == "MAPPED" and value["attribute_key"] == "secondary_voltage"
    assert value["numeric_value"] == "0.6" and value["unit"] == "kV"
    assert value["diagnostics"]["synthetic"] is True
    evidence = next(e["evidence"] for e in value["evidence"] if e["role"] == "PRIMARY")
    reply = client.get(ctx["base"] + f"/extraction/evidence/{evidence['id']}")
    assert reply.status_code == 200, reply.text
    body = reply.json()
    assert body["source_snippet"] == "600" and body["page_artifact_id"] is None
    assert body["source_locator"]["reading_basis"] == "NATIVE_PDF"
    assert body["source_locator"]["structure_basis"] == "NATIVE_GEOMETRY_SUPPORTED"
    assert body["source_locator"]["printed_text_independently_verified"] is False
    assert body["artifact_url"] and body["source_image_url"] and body["region"]
    table = client.get(ctx["base"] + f"/extraction/runs/{rid}/tables").json()["items"][0]
    assert table["layout_schema_version"] == "table-layout-v2"
    assert table["layout"]["metadata"]["structure_basis"] == "NATIVE_GEOMETRY_SUPPORTED"
    assert start_enriched(ctx, binding)["run"]["id"] == rid
    source_read = client.get(ctx["base"] + f"/extraction/runs/{rid}/sources")
    assert (
        source_read.status_code == 200
        and source_read.json()["items"][0]["spatial_result_id"] == binding["spatial_result_id"]
    )
    with ctx["factory"]() as session:
        assert session.scalar(
            select(RunSourceEnrichmentBinding.prepared_result_id).where(
                RunSourceEnrichmentBinding.run_id == UUID(rid)
            )
        ) == UUID(binding["prepared_result_id"])
        assert (
            session.scalar(
                select(Evidence.enrichment_artifact_id).where(Evidence.id == UUID(evidence["id"]))
            )
            is not None
        )


def test_missing_enrichment_is_rejected_before_any_attempt_or_delivery(enrichment_ctx):
    ctx = enrichment_ctx
    before = len(ctx["delivery"].ids)
    response = client.post(
        ctx["base"] + "/extraction/runs",
        json=dict(profile_key="engineering-test-enriched-v1", pages=[1]),
    )
    assert response.status_code == 409, response.text
    assert len(ctx["delivery"].ids) == before


def scan_lines(lines):
    from io import BytesIO

    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (2000, 700), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=52)
    for i, line in enumerate(lines):
        draw.text((60, 60 + i * 170), line, font=font, fill="black")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_actual_ocr_nameplate_maps_with_ocr_offsets_and_separate_image_evidence(enrichment_ctx):
    ctx = enrichment_ctx
    build_source(
        ctx, scan_lines(["2-Winding Transformer TX-1", "Secondary Voltage: 600 V"]), "nameplate.png"
    )
    binding = enrich(ctx)
    pending = start_enriched(ctx, binding, profile="engineering-test-enriched-v1")
    done = finish(ctx, pending)
    assert done["run"]["status"] == "COMPLETED", done
    rid = done["run"]["id"]
    values = client.get(ctx["base"] + f"/extraction/runs/{rid}/candidates").json()["items"]
    value = next(c for c in values if c["kind"] == "ATTRIBUTE_VALUE")
    assert value["mapping_status"] == "MAPPED" and value["numeric_value"] == "0.6", values
    primary = next(c["evidence"] for c in value["evidence"] if c["role"] == "PRIMARY")
    evidence = client.get(ctx["base"] + f"/extraction/evidence/{primary['id']}").json()
    assert evidence["source_locator"]["reading_basis"] == "OCR"
    assert evidence["source_locator"]["geometry_basis"] == "OCR_ENGINE"
    assert evidence["source_locator"]["printed_text_independently_verified"] is False
    assert evidence["source_kind"] == "OCR_TEXT" and evidence["page_artifact_id"] is None
    assert evidence["artifact_url"] != evidence["source_image_url"]
    assert value["equipment_mention_candidate_id"] and evidence["region"]


def test_newer_enrichment_does_not_replace_the_selected_binding_or_history(enrichment_ctx):
    ctx = enrichment_ctx
    build_source(
        ctx, Path("evals/tables/v1/sources/positioned_schedule.pdf").read_bytes(), "pinned.pdf"
    )
    first = enrich(ctx)
    pending = start_enriched(ctx, first)
    newer = enrich(ctx, mode="reextract")
    assert newer["spatial_result_id"] != first["spatial_result_id"]
    assert newer["prepared_result_id"] == first["prepared_result_id"]
    preparation = start_source(ctx, profile_key="source-preparation-v1", mode="reextract")
    prepare(ctx, preparation["attempts"][0]["id"])
    replacement = detail(ctx, preparation["run"]["id"])["results"][0]["id"]
    assert replacement != first["prepared_result_id"]
    before = len(ctx["delivery"].ids)
    mismatch = client.post(
        ctx["base"] + "/extraction/runs",
        json=dict(
            profile_key="tables-test-enriched-v1",
            pages=[1],
            enrichment_bindings=[
                dict(
                    prepared_result_id=replacement,
                    spatial_result_id=first["spatial_result_id"],
                )
            ],
        ),
    )
    assert mismatch.status_code == 409, mismatch.text
    assert len(ctx["delivery"].ids) == before
    done = finish(ctx, pending)
    assert done["run"]["status"] == "COMPLETED", done
    rid = done["run"]["id"]
    bound = client.get(ctx["base"] + f"/extraction/runs/{rid}/sources").json()["items"][0]
    assert bound["prepared_result_id"] == first["prepared_result_id"]
    assert bound["spatial_result_id"] == first["spatial_result_id"]
    assert start_enriched(ctx, first)["run"]["id"] == rid
    separate = start_enriched(ctx, first, profile="engineering-test-enriched-v1")
    finish(ctx, separate)
    assert client.get(ctx["base"] + f"/extraction/runs/{rid}/tables").json()["items"]
    summary = client.get(ctx["base"] + "/extraction").json()
    assert summary["latest_result"]["id"] == separate["run"]["id"]


def test_wrong_purpose_source_routes_and_mutations_have_no_side_effects(enrichment_ctx):
    ctx = enrichment_ctx
    binding = enrich(ctx)
    pending = start_enriched(ctx, binding, profile="engineering-test-enriched-v1")
    rid = pending["run"]["id"]
    with ctx["factory"]() as session:
        from powerforge_extraction.layout_models import SourceSpatialResult

        source_run = session.get(SourceSpatialResult, UUID(binding["spatial_result_id"])).run_id
    before = (len(ctx["delivery"].ids), len(ctx["storage"].calls))
    for suffix in ("sources", "candidates", "tables"):
        assert (
            client.get(ctx["base"] + f"/extraction/runs/{source_run}/{suffix}").status_code == 404
        )
    for suffix in ("retry", "cancel"):
        assert (
            client.post(ctx["base"] + f"/extraction/runs/{source_run}/{suffix}").status_code == 404
        )
        assert (
            client.post(ctx["base"] + f"/source-enrichment/runs/{rid}/{suffix}").status_code == 404
        )
    assert client.get(ctx["base"] + f"/source-enrichment/runs/{rid}").status_code == 404
    assert before == (len(ctx["delivery"].ids), len(ctx["storage"].calls))


def test_transient_model_retry_reuses_committed_layout_and_never_starts_ocr(enrichment_ctx):
    ctx = enrichment_ctx
    build_source(
        ctx, Path("evals/tables/v1/sources/positioned_schedule.pdf").read_bytes(), "retry.pdf"
    )
    binding = enrich(ctx)
    pending = start_enriched(ctx, binding)
    first = next(a for a in pending["attempts"] if a["stage"] == "TABLE_RECONSTRUCTION")
    execute(ctx, first["id"])
    current = extraction_detail(ctx, pending["run"]["id"])
    second = next(a for a in current["attempts"] if a["stage"] == "TABLE_INTERPRETATION")
    execute(ctx, second["id"], FakeEnrichedProvider("transient"))
    retry = extraction_detail(ctx, pending["run"]["id"])
    assert len(retry["attempts"]) == 3
    assert finish(ctx, retry)["run"]["status"] == "COMPLETED"
    assert detail(ctx, source_run_for(ctx, binding))["confirmed_ocr_invocations"] == 0


def test_partial_result_keeps_signed_table_evidence_visible_to_inheriting_revision(enrichment_ctx):
    ctx = enrichment_ctx
    build_source(
        ctx, Path("evals/tables/v1/sources/positioned_schedule.pdf").read_bytes(), "partial.pdf"
    )
    binding = enrich(ctx)
    pending = start_enriched(ctx, binding)
    rid = pending["run"]["id"]
    first = next(a for a in pending["attempts"] if a["stage"] == "TABLE_RECONSTRUCTION")
    execute(ctx, first["id"])
    current = extraction_detail(ctx, rid)
    second = next(a for a in current["attempts"] if a["stage"] == "TABLE_INTERPRETATION")
    execute(ctx, second["id"], FakeEnrichedProvider("permanent"))
    done = extraction_detail(ctx, rid)
    assert done["run"]["status"] == "PARTIALLY_COMPLETED"
    assert not done["coverage"]["complete"]
    base = ctx["base"] + "/extraction"
    assert client.get(base).json()["latest_result"]["id"] == rid
    tables = client.get(base + f"/runs/{rid}/tables").json()["items"]
    assert len(tables) == 1
    with ctx["factory"]() as session:
        evidence = session.scalar(
            select(Evidence.id).where(
                Evidence.run_id == UUID(rid), Evidence.enrichment_artifact_id.is_not(None)
            )
        )
    path = f"/extraction/evidence/{evidence}"
    source = client.get(ctx["base"] + path).json()
    assert source["artifact_url"] and source["source_image_url"]

    inherited = make_revision(
        ctx["project_id"],
        "1",
        based_on_revision_id=ctx["revision_id"],
        carry_forward_documents=True,
        activate=True,
    )
    assert inherited.status_code == 201, inherited.text
    revision_id = UUID(inherited.json()["id"])
    with ctx["factory"]() as session:
        association = session.scalar(
            select(RevisionDocument.id).where(
                RevisionDocument.revision_id == revision_id,
                RevisionDocument.document_id == ctx["document"],
            )
        )
    revision_base = f"/api/projects/{ctx['project_id']}/revisions/{revision_id}/documents/"
    actual = client.get(revision_base + str(association) + path)
    assert actual.status_code == 200, actual.text
    assert actual.json()["source_locator"] == source["source_locator"]
    original_association = ctx["base"].rsplit("/", 1)[-1]
    denied = client.get(revision_base + original_association + path)
    assert denied.status_code == 404
    assert "artifact_url" not in denied.json()


def source_run_for(ctx, binding):
    from powerforge_extraction.layout_models import SourceSpatialResult

    with ctx["factory"]() as session:
        return session.get(SourceSpatialResult, UUID(binding["spatial_result_id"])).run_id


def test_structurally_correct_ocr_table_can_still_cite_a_wrong_recognized_number(
    enrichment_ctx, monkeypatch
):
    """Controlled recognition error; this is not a Tesseract accuracy measurement."""
    from io import BytesIO

    from PIL import Image, ImageDraw, ImageFont

    ctx = enrichment_ctx
    image = Image.new("RGB", (2000, 800), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=52)
    draw.text((60, 30), "2-Winding Transformer Schedule", font=font, fill="black")
    for y, left, right in (
        (140, "Equipment", "Secondary (V)"),
        (310, "TX-1", "690"),
        (480, "TX-2", "480"),
    ):
        draw.text((60, y), left, font=font, fill="black")
        draw.text((1000, y), right, font=font, fill="black")
    output = BytesIO()
    image.save(output, format="PNG")
    build_source(ctx, output.getvalue(), "controlled-ocr-error.png")
    recognize = ctx["provider"].recognize
    changed = []

    def wrong_reading(request):
        result = recognize(request)
        assert any(w.text == "690" for w in result.words)
        changed.append(True)
        return result.model_copy(
            update={
                "words": tuple(
                    w.model_copy(update={"text": "600"}) if w.text == "690" else w
                    for w in result.words
                )
            }
        )

    monkeypatch.setattr(ctx["provider"], "recognize", wrong_reading)
    binding = enrich(ctx)
    pending = start_enriched(ctx, binding)
    done = finish(ctx, pending)
    assert done["run"]["status"] == "COMPLETED", done
    rid = done["run"]["id"]
    values = client.get(ctx["base"] + f"/extraction/runs/{rid}/candidates").json()["items"]
    assert any(c["raw_value"] == "600" for c in values), values
    value = next(c for c in values if c["raw_value"] == "600")
    assert value["mapping_status"] == "MAPPED" and value["numeric_value"] == "0.6"
    assert value["diagnostics"]["printed_text_independently_verified"] is False
    assert value["diagnostics"]["reading_bases"] == ["OCR"]
    citation = next(e["evidence"] for e in value["evidence"] if e["role"] == "PRIMARY")
    evidence = client.get(ctx["base"] + f"/extraction/evidence/{citation['id']}").json()
    assert evidence["source_snippet"] == "600"
    assert evidence["source_locator"]["structure_basis"] == "OCR_GEOMETRY_SUPPORTED"
    assert evidence["source_locator"]["printed_text_independently_verified"] is False
    assert evidence["source_locator"]["raw_engine_confidence"]["method"]
    assert changed == [True]


def test_cancel_during_model_execution_fences_all_new_output(enrichment_ctx):
    from enriched_support import execute, extraction_detail
    from powerforge_extraction.enriched_fake import FakeEnrichedProvider

    ctx = enrichment_ctx
    binding = enrich(ctx)
    pending = start_enriched(ctx, binding, profile="engineering-test-enriched-v1")
    rid = pending["run"]["id"]

    class Cancelling:
        def execute(self, request):
            response = FakeEnrichedProvider().execute(request)
            assert client.post(ctx["base"] + f"/extraction/runs/{rid}/cancel").status_code == 200
            return response

    first = next(a for a in pending["attempts"] if a["stage"] == "EQUIPMENT_RECOGNITION")
    assert execute(ctx, first["id"], Cancelling()) is False
    assert extraction_detail(ctx, rid)["run"]["status"] == "CANCELLED"
    assert not client.get(ctx["base"] + f"/extraction/runs/{rid}/candidates").json()["items"]


def test_missing_pinned_object_fails_before_model_and_does_not_fall_back(enrichment_ctx):
    from enriched_support import execute, extraction_detail
    from powerforge_extraction.enrichment_models import SourceEnrichmentArtifact

    ctx = enrichment_ctx
    binding = enrich(ctx)
    pending = start_enriched(ctx, binding, profile="engineering-test-enriched-v1")
    enrich(ctx, mode="reextract")
    with ctx["factory"]() as session:
        artifact = session.scalar(
            select(SourceEnrichmentArtifact).where(
                SourceEnrichmentArtifact.result_id == UUID(binding["prepared_result_id"])
            )
        )
        ctx["storage"].objects.pop(artifact.storage_key)

    class Forbidden:
        def execute(self, request):
            raise AssertionError("Missing source must not reach the model")

    first = next(a for a in pending["attempts"] if a["stage"] == "EQUIPMENT_RECOGNITION")
    execute(ctx, first["id"], Forbidden())
    done = extraction_detail(ctx, pending["run"]["id"])
    assert done["run"]["status"] == "FAILED", done
    assert done["execution"]["provider_calls_started"] == 0
    assert not client.get(
        ctx["base"] + f"/extraction/runs/{pending['run']['id']}/candidates"
    ).json()["items"]


def test_empty_committed_reconstruction_settles_without_second_provider_call(enrichment_ctx):
    from powerforge_extraction.enriched_fake import FakeEnrichedProvider

    ctx = enrichment_ctx
    binding = enrich(ctx)
    pending = start_enriched(ctx, binding)
    done = finish(ctx, pending, FakeEnrichedProvider("empty"))
    assert done["run"]["status"] == "COMPLETED", done
    assert done["execution"]["calls_admitted"] == 2
    assert done["execution"]["provider_calls_started"] == 1
    assert done["execution"]["reported_calls"] == 1
