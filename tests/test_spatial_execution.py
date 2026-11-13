"""Real fixed preparation/layout lifecycle and immutable original-producer reuse."""

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from documents_support import client
from enrichment_support import build_source, detail, execute, start
from enrichment_support import enrichment_ctx as enrichment_ctx
from powerforge_document_processing.storage.base import TransientStorageError
from powerforge_extraction.enrichment_models import SourceEnrichmentPageResult
from powerforge_extraction.layout_execution import execute_enrichment
from powerforge_extraction.layout_models import SourcePreparationReceipt
from powerforge_extraction.models import ExtractionWorkUnit
from powerforge_extraction.orchestration import ExtractionCoordinator
from test_enrichment_native import scan_png

pytestmark = pytest.mark.integration


def run_unit(ctx, unit_id, provider=None):
    return execute_enrichment(
        UUID(str(unit_id)),
        ctx["factory"],
        ctx["storage"],
        ctx["settings"],
        provider or (lambda: ctx["provider"]),
    )


def stage(result, name):
    return next(
        a["id"] for a in reversed(result["attempts"]) if a["unit_key"].startswith(name + ":")
    )


def test_real_fixed_plan_derives_the_accepted_positioned_pdf_and_exposes_owned_artifact(
    enrichment_ctx,
):
    ctx = enrichment_ctx
    build_source(
        ctx, Path("evals/tables/v1/sources/positioned_schedule.pdf").read_bytes(), "positioned.pdf"
    )
    pending = start(ctx, profile_key="source-layout-v1")
    rid = pending["run"]["id"]
    assert len(pending["attempts"]) == 2
    assert not run_unit(ctx, stage(pending, "SPATIAL_LAYOUT"))
    assert detail(ctx, rid)["run"]["admissions"] == 0
    assert run_unit(ctx, stage(pending, "SOURCE_PREPARE"))
    assert detail(ctx, rid)["run"]["status"] == "RUNNING"
    assert run_unit(ctx, stage(pending, "SPATIAL_LAYOUT"))
    done = detail(ctx, rid)
    assert done["run"]["status"] == "COMPLETED", done
    assert done["run"]["admissions"] == 2 and done["confirmed_ocr_invocations"] == 0
    result = done["spatial_results"][0]
    response = client.get(
        ctx["base"] + f"/source-enrichment/runs/{rid}/spatial-results/{result['id']}"
    )
    assert response.status_code == 200, response.text
    table = response.json()["manifest"]["tables"][0]
    assert (table["rows"], table["columns"]) == (2, 2)
    assert table["structure_basis"] == "NATIVE_GEOMETRY_SUPPORTED"
    assert all(c["headers"] for c in table["cells"] if c["row"] == 1)
    signed = client.get(
        ctx["base"] + f"/source-enrichment/runs/{rid}/spatial-results/{result['id']}/artifact"
    )
    assert signed.status_code == 200 and signed.json()["sha256"] == result["manifest_hash"]
    assert start(ctx, profile_key="source-layout-v1")["run"]["id"] == rid


def test_existing_successful_ocr_is_reused_with_its_real_producer_without_provider_startup(
    enrichment_ctx,
):
    ctx = enrichment_ctx
    build_source(ctx, scan_png(), "scan.png")
    original = start(ctx)
    execute(ctx, stage(original, "SOURCE_PREPARE"))
    source = detail(ctx, original["run"]["id"])["results"][0]
    pending = start(ctx, profile_key="source-layout-v1")
    rid = pending["run"]["id"]

    def forbidden():
        raise AssertionError("Layout or receipt repeated OCR")

    assert run_unit(ctx, stage(pending, "SOURCE_PREPARE"), forbidden)
    assert run_unit(ctx, stage(pending, "SPATIAL_LAYOUT"), forbidden)
    done = detail(ctx, rid)
    assert done["run"]["status"] == "COMPLETED", done
    assert done["confirmed_ocr_invocations"] == 0 and done["ocr_requests_started"] == 0
    assert done["results"][0]["id"] == source["id"] and done["results"][0]["reused"] is True
    assert done["results"][0]["producer_run_id"] == original["run"]["id"]
    assert len(done["preparation_receipts"]) == 1 and len(done["spatial_results"]) == 1
    original_read = client.get(
        ctx["base"] + f"/source-enrichment/runs/{rid}/results/{source['id']}"
    )
    assert original_read.status_code == 200, original_read.text
    artifact_id = original_read.json()["manifest"]["representations"][0]["text_artifact"]["id"]
    assert (
        client.get(
            ctx["base"] + f"/source-enrichment/runs/{rid}/artifacts/{artifact_id}"
        ).status_code
        == 200
    )
    with ctx["factory"]() as session:
        assert (
            session.scalar(
                select(SourceEnrichmentPageResult.id).where(
                    SourceEnrichmentPageResult.run_id == UUID(rid)
                )
            )
            is None
        )
        assert session.scalar(
            select(SourcePreparationReceipt.prepared_result_id).where(
                SourcePreparationReceipt.run_id == UUID(rid)
            )
        ) == UUID(source["id"])


def test_layout_storage_retry_keeps_its_committed_preparation_and_never_repeats_ocr(
    enrichment_ctx, monkeypatch
):
    ctx = enrichment_ctx
    build_source(ctx, scan_png(), "retry-scan.png")
    pending = start(ctx, profile_key="source-layout-v1")
    rid = pending["run"]["id"]
    run_unit(ctx, stage(pending, "SOURCE_PREPARE"))
    source = detail(ctx, rid)["results"][0]
    put = ctx["storage"].put
    calls = []

    def fail(key, *args):
        if key.startswith("source-spatial/") and not calls:
            calls.append(key)
            raise TransientStorageError("transient")
        return put(key, *args)

    monkeypatch.setattr(ctx["storage"], "put", fail)
    run_unit(ctx, stage(pending, "SPATIAL_LAYOUT"))
    retry = detail(ctx, rid)
    assert retry["run"]["status"] == "RUNNING" and len(retry["attempts"]) == 3

    def forbidden():
        raise AssertionError("Layout retry repeated OCR")

    run_unit(ctx, stage(retry, "SPATIAL_LAYOUT"), forbidden)
    done = detail(ctx, rid)
    assert done["run"]["status"] == "COMPLETED", done
    assert done["confirmed_ocr_invocations"] == 1 and done["ocr_requests_started"] == 1
    assert done["results"][0]["id"] == source["id"]
    assert done["spatial_results"][0]["prepared_result_id"] == source["id"]


def test_spatial_direct_ids_are_scoped_to_the_source_purpose_and_exact_run(enrichment_ctx):
    ctx = enrichment_ctx
    pending = start(ctx, profile_key="source-layout-v1")
    rid = pending["run"]["id"]
    run_unit(ctx, stage(pending, "SOURCE_PREPARE"))
    run_unit(ctx, stage(pending, "SPATIAL_LAYOUT"))
    spatial = detail(ctx, rid)["spatial_results"][0]["id"]
    ordinary = str(uuid4())
    for suffix in ("", "/artifact"):
        assert (
            client.get(
                ctx["base"]
                + f"/source-enrichment/runs/{ordinary}/spatial-results/{spatial}"
                + suffix
            ).status_code
            == 404
        )
        assert (
            client.get(
                ctx["base"] + f"/source-enrichment/runs/{rid}/spatial-results/{uuid4()}" + suffix
            ).status_code
            == 404
        )
    assert client.get(ctx["base"] + f"/extraction/runs/{rid}").status_code == 404


def test_actual_image_schedule_produces_ocr_based_table_structure(enrichment_ctx):
    from io import BytesIO

    from PIL import Image, ImageDraw, ImageFont

    ctx = enrichment_ctx
    image = Image.new("RGB", (2000, 700), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=52)
    for y, left, right in (
        (60, "Equipment", "Secondary (V)"),
        (230, "TX-1", "600"),
        (400, "TX-2", "480"),
    ):
        draw.text((60, y), left, font=font, fill="black")
        draw.text((1000, y), right, font=font, fill="black")
    stream = BytesIO()
    image.save(stream, format="PNG")
    build_source(ctx, stream.getvalue(), "schedule.png")
    pending = start(ctx, profile_key="source-layout-v1")
    rid = pending["run"]["id"]
    run_unit(ctx, stage(pending, "SOURCE_PREPARE"))
    run_unit(ctx, stage(pending, "SPATIAL_LAYOUT"))
    done = detail(ctx, rid)
    assert done["run"]["status"] == "COMPLETED", done
    result_id = done["spatial_results"][0]["id"]
    manifest = client.get(
        ctx["base"] + f"/source-enrichment/runs/{rid}/spatial-results/{result_id}"
    ).json()["manifest"]
    assert len(manifest["tables"]) == 1
    table = manifest["tables"][0]
    assert (table["rows"], table["columns"]) == (3, 2)
    assert table["structure_basis"] == "OCR_GEOMETRY_SUPPORTED"
    assert all(c["headers"] for c in table["cells"] if c["row"] > 0)
    assert (
        done["confirmed_ocr_invocations"] == 1
        and manifest["printed_text_independently_verified"] is False
    )


def test_cancelled_layout_cannot_publish_and_original_preparation_survives(
    enrichment_ctx, monkeypatch
):
    from powerforge_extraction import layout_execution

    ctx = enrichment_ctx
    pending = start(ctx, profile_key="source-layout-v1")
    rid = pending["run"]["id"]
    run_unit(ctx, stage(pending, "SOURCE_PREPARE"))
    original = detail(ctx, rid)["results"][0]
    derive = layout_execution.derive_layout

    def cancel_before_return(*args):
        result = derive(*args)
        with ctx["factory"].begin() as session:
            ExtractionCoordinator(session, ctx["settings"]).cancel(
                UUID(rid), purpose="SOURCE_ENRICHMENT"
            )
        return result

    monkeypatch.setattr(layout_execution, "derive_layout", cancel_before_return)
    assert not run_unit(ctx, stage(pending, "SPATIAL_LAYOUT"))
    done = detail(ctx, rid)
    assert done["run"]["status"] == "CANCELLED" and not done["spatial_results"]
    assert done["results"][0]["id"] == original["id"]


def test_database_requires_spatial_output_and_preserves_immutable_history(enrichment_ctx):
    ctx = enrichment_ctx
    pending = start(ctx, profile_key="source-layout-v1")
    rid = pending["run"]["id"]
    run_unit(ctx, stage(pending, "SOURCE_PREPARE"))
    uid = UUID(stage(pending, "SPATIAL_LAYOUT"))
    with ctx["factory"].begin() as session:
        claim = ExtractionCoordinator(session, ctx["settings"]).claim(
            uid, purpose="SOURCE_ENRICHMENT"
        )
        assert claim
    with pytest.raises(DBAPIError, match="Layout completion requires"):
        with ctx["factory"].begin() as session:
            _, unit, _ = ExtractionCoordinator(session, ctx["settings"])._authorized(
                uid, claim.token
            )
            unit.status = "COMPLETED"
    # Expired attempt recovers through the shared retry mechanism.
    from datetime import timedelta

    with ctx["factory"].begin() as session:
        coordinator = ExtractionCoordinator(session, ctx["settings"])
        session.get(ExtractionWorkUnit, uid).lease_expires_at = coordinator.now() - timedelta(
            seconds=1
        )
    with ctx["factory"].begin() as session:
        ExtractionCoordinator(session, ctx["settings"]).reconcile()
    retry = detail(ctx, rid)
    run_unit(ctx, stage(retry, "SPATIAL_LAYOUT"))
    done = detail(ctx, rid)
    assert done["run"]["status"] == "COMPLETED", done
    with pytest.raises(DBAPIError, match="immutable"):
        with ctx["factory"].begin() as session:
            session.execute(
                text("UPDATE source_spatial_results SET usage='{}' WHERE run_id=:r"),
                {"r": UUID(rid)},
            )


def test_explicit_reuse_and_direct_reads_require_the_exact_bound_result(enrichment_ctx):
    ctx = enrichment_ctx
    first = start(ctx)
    execute(ctx, stage(first, "SOURCE_PREPARE"))
    original = detail(ctx, first["run"]["id"])["results"][0]
    other = start(ctx, mode="reextract")
    execute(ctx, stage(other, "SOURCE_PREPARE"))
    unrelated = detail(ctx, other["run"]["id"])["results"][0]
    pending = start(ctx, profile_key="source-layout-v1", prepared_result_ids=[original["id"]])
    rid = pending["run"]["id"]
    assert (
        client.get(
            ctx["base"] + f"/source-enrichment/runs/{rid}/results/{original['id']}"
        ).status_code
        == 404
    )  # Admission is not a completed receipt.
    run_unit(ctx, stage(pending, "SOURCE_PREPARE"))
    assert (
        client.get(
            ctx["base"] + f"/source-enrichment/runs/{rid}/results/{original['id']}"
        ).status_code
        == 200
    )
    assert (
        client.get(
            ctx["base"] + f"/source-enrichment/runs/{rid}/results/{unrelated['id']}"
        ).status_code
        == 404
    )
    response = client.post(
        ctx["base"] + "/source-enrichment/runs",
        json=dict(
            processing_run_id=str(ctx["processing"]),
            pages=[1],
            profile_key="source-layout-v1",
            prepared_result_ids=[str(uuid4())],
        ),
    )
    assert response.status_code == 404


def test_corrupted_pinned_objects_do_not_fall_back_to_newer_preparation(enrichment_ctx):
    from powerforge_extraction.enrichment_models import SourceEnrichmentArtifact

    ctx = enrichment_ctx
    original = start(ctx)
    execute(ctx, stage(original, "SOURCE_PREPARE"))
    source = detail(ctx, original["run"]["id"])["results"][0]
    pending = start(ctx, profile_key="source-layout-v1")
    newer = start(ctx, mode="reextract")
    execute(ctx, stage(newer, "SOURCE_PREPARE"))
    with ctx["factory"]() as session:
        artifact = session.scalar(
            select(SourceEnrichmentArtifact).where(
                SourceEnrichmentArtifact.result_id == UUID(source["id"])
            )
        )
        key = artifact.storage_key
    ctx["storage"].objects.pop(key)

    def forbidden():
        raise AssertionError("Pinned reuse must never re-OCR or re-prepare")

    run_unit(ctx, stage(pending, "SOURCE_PREPARE"), forbidden)
    done = detail(ctx, pending["run"]["id"])
    assert done["run"]["status"] == "FAILED", done
    assert not done["spatial_results"] and not done["preparation_receipts"]
    assert done["ocr_requests_started"] == 0
