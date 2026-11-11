"""Independent synthetic source gold and compact reconstruction validation."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from enriched_pure_support import fake, native_sources, table_interpretation
from powerforge_ai.extraction_diagnostics import validation_issues
from powerforge_extraction.enriched_profiles import (
    COMPACT_TABLES,
    enriched_profile,
    require_enriched,
)
from powerforge_extraction.enriched_publication import validate_locations
from powerforge_extraction.enriched_tables import reconstruct
from powerforge_extraction.profiles import read_profile
from powerforge_extraction.semantic_observations import SemanticTableResponse
from powerforge_extraction.semantic_tables import interpret_tables
from powerforge_extraction.stage_diagnostics import SourceRejection, StageDiagnostics
from powerforge_extraction.table_reconstruction_v4 import (
    CompactReconstructionResponse,
    reconstruct_compact,
)
from powerforge_shared.config import Settings
from spatial_layout_support import drawn_table
from test_phase6g_stage_diagnostics import native_ctx as native_ctx

CORPUS = json.loads(Path("evals/extraction/phase6g/synthetic.json").read_text())["cases"]


def response(partitions=(), reports=()):
    return CompactReconstructionResponse.model_validate(
        dict(
            schema_version="table-reconstruction-schema-v3",
            overflowed=False,
            partitions=list(partitions),
            reported_tables=list(reports),
        )
    )


def select(sources, kind):
    return dict(local_ref="t0", spatial_table_ref=sources.layout.tables[0].ref, proposed_kind=kind)


def test_v4_profile_round_trips_under_existing_tables_envelope():
    profile = enriched_profile(COMPACT_TABLES, Settings(_env_file=None))
    restored = read_profile(profile.model_dump(mode="json"))
    require_enriched(restored)
    assert restored == profile


def test_compact_form_grounds_unfamiliar_label_and_preserves_exact_cells():
    case = CORPUS["transformer_form"]
    gold = case["expected"]
    sources = native_sources(drawn_table(rows=case["rows"]))
    trace = StageDiagnostics()
    request = response([select(sources, gold["orientation"])])
    trace.parsed(request)
    output, context = reconstruct_compact(request, sources, trace=trace)
    validate_locations(sources, output, compact=True)
    assert len(output.tables) == gold["tables"]
    assert len(output.tables[0].layout.cells) == gold["cells"]
    assert trace.returned == {"tables": 1}
    assert trace.counts["SELECTED_PARTITIONS"] == 1
    table = context.tables[0]
    assert table.basis == "NATIVE_GEOMETRY_SUPPORTED"
    cells = {c.raw_text: c for c in table.observation.cells}
    device, label, value = (
        cells[name] for name in ("2-Winding Transformer", "Continuous transfer duty (kVA)", "350")
    )
    assert label.local_ref in value.header_refs
    # Feed the exact same expanded source grid to the older admission rule.
    from powerforge_extraction.enriched_tables import _admit

    assert _admit(sources, table.observation) == "UNRESOLVED"

    later, _ = table_interpretation(sources, output)
    interpretation = SemanticTableResponse.model_validate(
        dict(
            schema_version="table-interpretation-schema-v3",
            overflowed=False,
            equipment=[
                dict(
                    local_ref="eq",
                    table_ref="t0",
                    raw_expression=device.raw_text,
                    source_refs=[device.local_ref],
                    observed_tag=None,
                    observed_name=None,
                    proposed_equipment_type="TWO_WINDING_TRANSFORMER",
                    ambiguous=False,
                    ambiguity_reason=None,
                )
            ],
            attributes=[
                dict(
                    local_ref="rating",
                    table_ref="t0",
                    equipment_ref="eq",
                    value_cell_ref=value.local_ref,
                    label_refs=[label.local_ref],
                    unit_refs=[label.local_ref],
                    qualifier_refs=[],
                    raw_expression="350",
                    source_label=label.raw_text,
                    raw_value="350",
                    raw_unit="kVA",
                    proposed_equipment_type="TWO_WINDING_TRANSFORMER",
                    proposed_attribute_key="rated_apparent_power",
                    ambiguous=False,
                    ambiguity_reason=None,
                )
            ],
        )
    )
    interpreted = interpret_tables(
        interpretation, later, context, compact=True, source_supported=True
    )
    candidate = interpreted.candidates[-1]
    assert candidate.attribute_key == gold["key"]
    assert str(candidate.numeric_value) == gold["numeric"] and candidate.unit == gold["unit"]


def test_compact_schedule_keeps_repeated_devices_and_grounds_provisioned_count():
    case = CORPUS["breaker_schedule"]
    gold = case["expected"]
    sources = native_sources(drawn_table(rows=case["rows"]))
    output, context = reconstruct_compact(response([select(sources, gold["orientation"])]), sources)
    validate_locations(sources, output, compact=True)
    assert len(output.tables[0].layout.cells) == gold["cells"]
    later, stub = table_interpretation(sources, output)
    payload = stub.model_dump(mode="json")
    payload["schema_version"] = "table-interpretation-schema-v3"
    for item in payload["equipment"]:
        item.update(proposed_equipment_type="LV_BREAKER", observed_tag="GBH3020")
    interpreted = interpret_tables(
        SemanticTableResponse.model_validate(payload),
        later,
        context,
        compact=True,
        source_supported=True,
    )
    mentions = [c for c in interpreted.candidates if c.kind == "EQUIPMENT_MENTION"]
    assert len(mentions) == len({c.source_group_id for c in mentions}) == gold["installed_mentions"]
    assert [c.observed_tag for c in mentions if c.observed_tag] == gold["breaker_tags"]
    positions = next(c for c in interpreted.candidates if c.raw_value == gold["provisioned_count"])
    assert (
        positions.mapping_status == "UNMAPPED" and positions.reason_code == "PROVISIONED_POSITION"
    )
    assert positions.equipment_mention_candidate_id is None
    snippets = {item.id: item.source_snippet for item in output.evidence}
    assert {
        snippets[link.evidence_id]
        for link in interpreted.candidate_evidence
        if link.candidate_id == positions.id and link.role == "SUPPORTING"
    } >= {"PROV"}


def test_compact_invalid_duplicate_unknown_and_empty_remain_distinct():
    sources = native_sources(drawn_table())
    partition = select(sources, "EQUIPMENT_ROWS")
    with pytest.raises(ValidationError) as exc:
        response([partition, {**partition, "local_ref": "other"}])
    assert (
        validation_issues(exc.value, CompactReconstructionResponse)[0].reason == "DUPLICATE_ALIAS"
    )
    with pytest.raises(ValidationError) as exc:
        CompactReconstructionResponse.model_validate_json('{"partitions": [')
    assert validation_issues(exc.value, CompactReconstructionResponse)[0].reason == "MALFORMED_JSON"
    with pytest.raises(SourceRejection) as exc:
        reconstruct_compact(response([{**partition, "spatial_table_ref": "other-page"}]), sources)
    assert exc.value.reason == "UNAVAILABLE_SPATIAL_TABLE_ALIAS"
    output, context = reconstruct_compact(response(), sources)
    assert not output.tables and not context.tables


def test_visual_report_cannot_acquire_source_text_or_geometry():
    sources = native_sources(drawn_table())
    table = fake(sources).model_dump()["tables"][0]
    table["spatial_table_ref"] = None
    visual = [{"source_ref": "analysis_image", "reading_refs": []}]
    table["anchors"] = visual
    if table["title"]:
        table["title"]["anchors"] = visual
    for cell in table["cells"]:
        cell.update(spatial_cell_ref=None, anchors=visual)
    output, _ = reconstruct_compact(response(reports=[table]), sources)
    validate_locations(sources, output, compact=True)
    assert output.tables[0].layout.metadata["structure_basis"] == "VISUAL_REPORTED"
    assert output.evidence
    assert all(e.text_start is None and e.location.region is None for e in output.evidence)


def test_merged_header_paths_are_copied_from_source():
    sources = native_sources(drawn_table(merged=True))
    baseline, _ = reconstruct(fake(sources), sources)
    output, _ = reconstruct_compact(response([select(sources, "EQUIPMENT_ROWS")]), sources)
    old, new = baseline.tables[0].layout, output.tables[0].layout
    assert [(c.row, c.column, c.row_span, c.column_span, c.text) for c in new.cells] == [
        (c.row, c.column, c.row_span, c.column_span, c.text) for c in old.cells
    ]
    old_cells = old.metadata["observation"]["cells"]
    new_cells = new.metadata["observation"]["cells"]
    assert [c["header_refs"] for c in new_cells] == [c["header_refs"] for c in old_cells]
    assert any(len(c["header_refs"]) > 1 for c in new_cells)


@pytest.mark.integration
def test_v4_and_historical_v3_recover_on_real_broker_and_publish_to_minio(
    native_ctx,
    s3_scratch_storage,
    tmp_path,
):
    from datetime import timedelta
    from uuid import UUID

    import httpx
    from sqlalchemy import select

    from documents_support import client
    from enriched_support import enrich, extraction_detail, start_enriched
    from enrichment_support import build_source
    from powerforge_api.main import app
    from powerforge_document_processing.storage.factory import get_object_storage
    from powerforge_extraction.controls import RunExecution
    from powerforge_extraction.models import ExtractionWorkUnit
    from powerforge_extraction.orchestration import ExtractionCoordinator
    from test_enrichment_celery import copy_source
    from test_extraction_celery_integration import live_worker, wait_for

    ctx = build_source(
        native_ctx,
        Path("evals/tables/v1/sources/positioned_schedule.pdf").read_bytes(),
        "broker-schedule.pdf",
    )
    binding = enrich(ctx)
    pending = [start_enriched(ctx, binding, profile=f"tables-openai-enriched-v{v}") for v in (3, 4)]
    copy_source(ctx, s3_scratch_storage)
    hashes = {}
    with ctx["factory"].begin() as session:
        coordinator = ExtractionCoordinator(session, ctx["settings"])
        for run in pending:
            unit_id = UUID(
                next(a["id"] for a in run["attempts"] if a["stage"] == "TABLE_RECONSTRUCTION")
            )
            assert coordinator.claim(unit_id)
            unit = session.get(ExtractionWorkUnit, unit_id)
            unit.lease_expires_at = coordinator.now() - timedelta(seconds=1)
            hashes[unit.run_id] = session.get(RunExecution, unit.run_id).configuration

    with live_worker(
        ctx,
        s3_scratch_storage,
        tmp_path / "phase6g-worker",
        beat=True,
        app_module="phase6g_tables_worker_fixture",
        extra_env={"EXTRACTION_EXTERNAL_ENABLED": "true"},
    ):
        for run in pending:
            run_id = run["run"]["id"]
            completed = wait_for(
                lambda run_id=run_id: (
                    detail
                    if (detail := extraction_detail(ctx, run_id))["run"]["status"]
                    in {"COMPLETED", "FAILED", "PARTIALLY_COMPLETED"}
                    else None
                ),
                seconds=40,
            )
            assert completed["run"]["status"] == "COMPLETED", completed
            assert completed["execution"]["provider_calls_started"] == 2
            with ctx["factory"]() as session:
                units = session.scalars(
                    select(ExtractionWorkUnit)
                    .where(
                        ExtractionWorkUnit.run_id == UUID(run_id),
                        ExtractionWorkUnit.stage == "TABLE_RECONSTRUCTION",
                    )
                    .order_by(ExtractionWorkUnit.attempt_number)
                ).all()
                assert [unit.status for unit in units] == ["FAILED", "COMPLETED"]
                assert units[0].error_code == "WORKER_INTERRUPTED"
                assert units[1].retry_of_work_unit_id == units[0].id
                assert units[1].execution_metadata == units[0].execution_metadata
                assert session.get(RunExecution, UUID(run_id)).configuration == hashes[UUID(run_id)]

            candidates = client.get(ctx["base"] + f"/extraction/runs/{run_id}/candidates").json()
            value = next(
                item for item in candidates["items"] if item["attribute_key"] == "secondary_voltage"
            )
            assert value["numeric_value"] == "0.6"
            evidence = next(
                c["evidence"]
                for c in value["evidence"]
                if c["role"] == "PRIMARY" and c["evidence"]["source_snippet"] == "600"
            )
            previous = app.dependency_overrides[get_object_storage]
            app.dependency_overrides[get_object_storage] = lambda: s3_scratch_storage
            try:
                signed = client.get(ctx["base"] + f"/extraction/evidence/{evidence['id']}").json()
                source = httpx.get(signed["artifact_url"], timeout=5)
                assert source.status_code == 200
                assert source.text[signed["text_start"] : signed["text_end"]] == "600"
            finally:
                app.dependency_overrides[get_object_storage] = previous


def test_long_schedule_does_not_require_repeating_cell_payload():
    import pymupdf

    with pymupdf.open() as doc:
        page = doc.new_page(width=600, height=1050)
        rows = [("Equipment", "Trip (A)"), *[(f"LV Breaker {i}", "20") for i in range(1, 41)]]
        for i in range(len(rows) + 1):
            page.draw_line((30, 30 + 22 * i), (550, 30 + 22 * i))
        for x in (30, 280, 550):
            page.draw_line((x, 30), (x, 30 + 22 * len(rows)))
        for i, (left, right) in enumerate(rows):
            page.insert_text((40, 46 + i * 22), left, fontsize=10)
            page.insert_text((290, 46 + i * 22), right, fontsize=10)
        sources = native_sources(doc.tobytes())
    baseline = fake(sources)
    compact = response([select(sources, "EQUIPMENT_ROWS")])
    output, _ = reconstruct_compact(compact, sources)
    assert len(output.tables[0].layout.cells) == 82
    assert len(compact.model_dump_json().encode()) < len(baseline.model_dump_json().encode()) / 10


def test_compact_image_only_cell_stays_unreadable_with_supported_table_geometry():
    import pymupdf

    rows = [("Equipment", "Quantity"), ("TX-1", ""), ("TX-2", "2")]
    with (
        pymupdf.open(stream=drawn_table(rows=rows), filetype="pdf") as document,
        pymupdf.open() as image_document,
    ):
        image_page = image_document.new_page(width=90, height=24)
        image_page.insert_text((3, 16), "IMAGE ONLY", fontsize=12)
        document[0].insert_image(pymupdf.Rect(280, 104, 370, 128), pixmap=image_page.get_pixmap())
        sources = native_sources(document.tobytes())
    spatial = next(c for c in sources.layout.tables[0].cells if (c.row, c.column) == (1, 1))
    assert spatial.state == "NO_READINGS"
    request = response([select(sources, "EQUIPMENT_ROWS")])
    output, context = reconstruct_compact(request, sources)
    validate_locations(sources, output, compact=True)

    (table,) = context.tables
    assert table.basis == "NATIVE_GEOMETRY_SUPPORTED"
    assert len(output.tables[0].layout.cells) == 6
    missing = next(c for c in table.observation.cells if c.spatial_cell_ref == spatial.ref)
    assert missing.state == "UNREADABLE" and missing.ambiguous
    assert missing.ambiguity_reason == "No committed text readings for this cell"
    assert missing.raw_text is None and not missing.anchors[0].reading_refs
    (evidence,) = table.items[missing.local_ref]
    assert evidence.source_snippet is None and evidence.text_start is None
    assert evidence.location.reading_basis == "VISUAL_REPORTED"
    assert evidence.location.region is None
    assert any(c.state == "VALUE" and c.raw_text == "2" for c in table.observation.cells)

    previous, old_context = reconstruct_compact(request, sources, legacy_blank_cells=True)
    validate_locations(sources, previous, compact=True, legacy_blank_cells=True)
    old_cell = next(
        c for c in old_context.tables[0].observation.cells if c.local_ref == missing.local_ref
    )
    assert old_cell.state == "BLANK" and old_cell.raw_text == ""
    with pytest.raises(ValueError, match="does not reproduce"):
        validate_locations(sources, previous, compact=True)


def test_existing_compact_consent_resolves_the_original_runtime():
    from powerforge_extraction.enriched_profiles import semantic_runtime
    from powerforge_extraction.operation_plan import pinned_operation_profile

    settings = Settings(_env_file=None)
    current = enriched_profile(COMPACT_TABLES, settings)
    previous = current.model_copy(
        update={"runtime": semantic_runtime(current, legacy_blank_cells=True)}
    )
    restored = read_profile(previous.model_dump(mode="json"))
    assert not current.legacy_blank_cells and restored.legacy_blank_cells
    assert previous.identity_hash != current.identity_hash
    require_enriched(restored)
    assert pinned_operation_profile(settings, "tables", previous.identity_hash) == restored
