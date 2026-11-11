"""Trace split-form losses through normal execution, persistence and revision reads."""

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from documents_support import client, make_project, make_revision
from enriched_support import enrich, extraction_detail, start_enriched
from enrichment_support import Delivery, build_source
from extraction_worker.openai_extraction import OpenAIExtractionProvider
from powerforge_ai.extraction import ExtractionResponse
from powerforge_api.db import get_session_factory
from powerforge_api.main import app
from powerforge_extraction.enqueue import get_extraction_enqueue
from powerforge_extraction.enriched_fake import FakeEnrichedProvider
from powerforge_extraction.execution import execute_unit
from powerforge_extraction.local_diagnostic_capture import LocalDiagnosticCapture
from powerforge_extraction.persistence import ExtractionPersistence
from powerforge_shared.config import Settings, get_settings
from test_enriched_grounding import prose_pdf
from test_spatial_execution import stage

pytestmark = pytest.mark.integration


@pytest.fixture
def native_ctx(ctx, monkeypatch):
    # Native PDF layout requires a pinned OCR identity even when OCR does not run.
    recorded = json.loads(
        Path("tests/fixtures/enrichment/preparation_v1_environment.json").read_text()
    )

    def forbidden_ocr():
        pytest.fail("This native-only fixture must not invoke OCR")

    settings = Settings(
        _env_file=None,
        enrichment_enabled=True,
        enrichment_ocr_configuration=json.dumps(recorded["configuration"]),
        extraction_external_enabled=True,
        extraction_backoff_seconds=0,
    )
    delivery = Delivery()
    monkeypatch.setitem(app.dependency_overrides, get_settings, lambda: settings)
    monkeypatch.setitem(app.dependency_overrides, get_extraction_enqueue, lambda: delivery)
    return {
        **ctx,
        "factory": get_session_factory(),
        "settings": settings,
        "delivery": delivery,
        "provider": forbidden_ocr,
    }


def execute(ctx, unit_id, provider_factory, *, capture=None):
    return execute_unit(
        UUID(unit_id),
        ctx["factory"],
        ctx["storage"],
        ctx["settings"],
        provider_factory,
        capture=capture,
    )


def trace_for(ctx, pending, unit_id):
    return next(
        attempt["stage_trace"]
        for attempt in extraction_detail(ctx, pending["run"]["id"])["attempts"]
        if attempt["id"] == unit_id
    )


@pytest.mark.parametrize("tables_version", [1, 4])
def test_split_rating_is_diagnosable_and_table_schema_failure_stays_independent(
    native_ctx, caplog, tables_version
):
    ctx = build_source(
        native_ctx,
        prose_pdf(["2-Winding Transformer", "kVA:", "350", "CONFIDENTIAL_FIXTURE"]),
        "split-form.pdf",
    )
    binding = enrich(ctx)
    engineering = start_enriched(ctx, binding, profile="engineering-test-enriched-v1")
    recognize = stage(engineering, "EQUIPMENT_RECOGNITION")
    attributes = stage(engineering, "ATTRIBUTE_EXTRACTION")
    assert trace_for(ctx, engineering, recognize) is None

    class SplitRating(FakeEnrichedProvider):
        request_text = None

        def execute(self, request):
            self.request_text = request.text
            source = json.loads(request.text)
            aliases = [r["ref"] for r in source["readings"] if r["raw_text"] in ("kVA:", "350")]
            assert len(aliases) == 2
            result = request.response_model.model_validate(
                dict(
                    schema_version=request.schema_version,
                    overflowed=False,
                    attributes=[
                        dict(
                            local_ref="rating",
                            raw_expression="kVA: 350",
                            ambiguous=False,
                            ambiguity_reason=None,
                            source_label="kVA",
                            raw_value="350",
                            raw_unit="kVA",
                            proposed_equipment_type="TWO_WINDING_TRANSFORMER",
                            proposed_attribute_key="rated_apparent_power",
                            equipment_ref=json.loads(request.upstream_context)["equipment"][0][
                                "local_ref"
                            ],
                            anchors=[dict(source_ref="spatial_readings", reading_refs=aliases)],
                        )
                    ],
                )
            )
            return ExtractionResponse[request.response_model](
                result=result, usage=dict(input_tokens=4, output_tokens=5)
            )

    with LocalDiagnosticCapture(UUID(recognize)) as capture:
        assert execute(ctx, recognize, lambda _: FakeEnrichedProvider(), capture=capture)
        events = capture.inspect()["events"]
        mapped = next(event for event in events if event["outcome"] == "MAPPED")
        candidates = client.get(
            ctx["base"] + f"/extraction/runs/{engineering['run']['id']}/candidates"
        ).json()["items"]
        assert mapped["output_id"] == candidates[0]["id"]
        assert mapped["final_equipment_type"] == "TWO_WINDING_TRANSFORMER"

    fake = SplitRating()
    with LocalDiagnosticCapture(UUID(attributes)) as capture:
        assert execute(ctx, attributes, lambda _: fake, capture=capture)
        local = capture.inspect()
        assert local["source_projection"] == fake.request_text
        parsed = json.loads(local["parsed_response"])["attributes"][0]
        assert parsed["raw_value"] == "350"
        assert parsed["proposed_attribute_key"] == "rated_apparent_power"
        assert local["events"] == (
            {
                "observation_ref": "rating",
                "outcome": "GROUNDING_REJECTED",
                "reason": "CROSSES_SOURCE_LINES",
                "output_id": None,
                "final_equipment_type": None,
                "final_attribute_key": None,
                "association_basis": None,
                "structure_basis": None,
                "reading_bases": (),
                "mapping_basis": None,
            },
        )
    with pytest.raises(RuntimeError, match="closed"):
        capture.inspect()

    trace = trace_for(ctx, engineering, attributes)
    assert trace["phase"] == "COMPLETED" and trace["provider_outcome"] == "PARSED"
    assert trace["returned"] == {"attributes": 1}
    assert trace["counts"]["GROUNDING_REJECTED"] == 1
    assert trace["counts"]["PUBLISHED_CANDIDATES"] == 0
    assert trace["reasons"] == {"CROSSES_SOURCE_LINES": 1}
    assert trace["source"]["native_readings"] > 0
    assert trace["source"]["ocr_readings"] == 0
    assert trace["source"]["prepared_result_id"] == binding["prepared_result_id"]
    assert trace["source"]["spatial_result_id"] == binding["spatial_result_id"]
    assert extraction_detail(ctx, engineering["run"]["id"])["run"]["status"] == "COMPLETED"

    reconstruction_schema = f"table-reconstruction-schema-v{2 if tables_version == 1 else 3}"

    class MissingTables:
        calls = 0

        def parse(self, **options):
            self.calls += 1
            options["text_format"].model_validate(
                {
                    "schema_version": reconstruction_schema,
                    "overflowed": False,
                    "CONFIDENTIAL_FIXTURE": "secret provider content",
                }
            )

    transport = MissingTables()
    tables = start_enriched(ctx, binding, profile=f"tables-openai-enriched-v{tables_version}")
    reconstruction = stage(tables, "TABLE_RECONSTRUCTION")
    assert execute(
        ctx,
        reconstruction,
        lambda claim: OpenAIExtractionProvider(
            ctx["settings"], client=SimpleNamespace(responses=transport), profile=claim.profile
        ),
    )
    failure = trace_for(ctx, tables, reconstruction)
    assert failure["phase"] == "PARSE" and failure["provider_detail"] == "MISSING_FIELD"
    assert failure["issues"] == [
        *[
            {"reason": "MISSING_FIELD", "path": path}
            for path in (("tables",) if tables_version == 1 else ("partitions", "reported_tables"))
        ],
        {"reason": "SCHEMA_VALIDATION", "path": "*"},
    ]
    assert failure["returned"] is None and transport.calls == 1
    table_detail = extraction_detail(ctx, tables["run"]["id"])
    assert table_detail["run"]["status"] == "FAILED"
    interpretation = next(
        a for a in table_detail["attempts"] if a["stage"] == "TABLE_INTERPRETATION"
    )
    assert interpretation["error_code"] == "PREREQUISITE_FAILED"
    assert interpretation["stage_trace"] is None
    assert table_detail["execution"]["provider_calls_started"] == 1
    tables_candidates = client.get(
        ctx["base"] + f"/extraction/runs/{tables['run']['id']}/candidates"
    )
    assert tables_candidates.status_code == 200 and tables_candidates.json()["items"] == []
    engineering_candidates = client.get(
        ctx["base"] + f"/extraction/runs/{engineering['run']['id']}/candidates"
    )
    assert engineering_candidates.json()["items"] == candidates
    assert trace_for(ctx, engineering, attributes) == trace

    log = next(record for record in caplog.records if getattr(record, "provider_detail", None))
    assert log.provider_detail == "MISSING_FIELD"
    assert log.validation_issues == failure["issues"]
    ordinary_diagnostics = json.dumps([trace, table_detail, log.validation_issues]) + caplog.text
    for private in ("CONFIDENTIAL_FIXTURE", "secret provider content", "kVA: 350", "storage_key"):
        assert private not in ordinary_diagnostics

    other_project = make_project()
    other_revision = make_revision(other_project, "0", activate=True).json()["id"]
    other_scope = (
        ctx["base"]
        .replace(ctx["project_id"], other_project)
        .replace(ctx["revision_id"], other_revision)
    )
    assert client.get(other_scope + f"/extraction/runs/{tables['run']['id']}").status_code == 404


def test_parsed_table_rejection_and_publication_rollback_keep_distinct_traces(
    native_ctx, monkeypatch
):
    ctx = build_source(
        native_ctx,
        Path("evals/tables/v1/sources/positioned_schedule.pdf").read_bytes(),
        "schedule.pdf",
    )
    binding = enrich(ctx)
    first = start_enriched(ctx, binding)
    unit_id = stage(first, "TABLE_RECONSTRUCTION")

    class WrongAlias(FakeEnrichedProvider):
        def execute(self, request):
            response = super().execute(request)
            body = response.result.model_dump()
            body["tables"][0]["spatial_table_ref"] = "unowned"
            return response.model_copy(
                update={"result": request.response_model.model_validate(body)}
            )

    assert execute(ctx, unit_id, lambda _: WrongAlias())
    failed = trace_for(ctx, first, unit_id)
    assert (failed["phase"], failed["provider_outcome"], failed["returned"]) == (
        "GROUNDING",
        "PARSED",
        {"tables": 1},
    )
    assert failed["reason"] == "UNAVAILABLE_SPATIAL_TABLE_ALIAS"

    retry = client.post(ctx["base"] + f"/extraction/runs/{first['run']['id']}/retry")
    assert retry.status_code == 202, retry.text
    retry_id = stage(retry.json(), "TABLE_RECONSTRUCTION")
    assert retry_id != unit_id and trace_for(ctx, first, retry_id) is None
    original_publish = ExtractionPersistence.publish

    def rollback(self, *args, **kwargs):
        original_publish(self, *args, **kwargs)
        raise RuntimeError("private SQL failure details")

    monkeypatch.setattr(ExtractionPersistence, "publish", rollback)
    with LocalDiagnosticCapture(UUID(retry_id)) as capture:
        assert execute(ctx, retry_id, lambda _: FakeEnrichedProvider(), capture=capture)
        assert all(event["output_id"] is None for event in capture.inspect()["events"])
    trace = trace_for(ctx, first, retry_id)
    assert trace["phase"] == "PUBLICATION" and trace["provider_outcome"] == "PARSED"
    assert trace["counts"]["CONVERTED_TABLES"] == 1
    assert "PUBLISHED_TABLES" not in trace["counts"]
    assert trace_for(ctx, first, unit_id) == failed
    assert not client.get(ctx["base"] + f"/extraction/runs/{first['run']['id']}/tables").json()[
        "items"
    ]
    with pytest.raises(DBAPIError, match="Extraction output is immutable"):
        with ctx["factory"].begin() as session:
            session.execute(
                text("DELETE FROM extraction_stage_traces WHERE work_unit_id = :unit"),
                {"unit": UUID(unit_id)},
            )


def test_empty_reconstruction_records_uncalled_interpretation(native_ctx):
    ctx = build_source(native_ctx, prose_pdf(["Synthetic sheet with no tables"]), "empty.pdf")
    run = start_enriched(ctx, enrich(ctx))
    reconstruction = stage(run, "TABLE_RECONSTRUCTION")
    interpretation = stage(run, "TABLE_INTERPRETATION")

    def forbidden_provider(_):
        pytest.fail("An empty committed table result must not start another provider")

    assert execute(ctx, reconstruction, lambda _: FakeEnrichedProvider("empty"))
    assert execute(ctx, interpretation, forbidden_provider)
    assert trace_for(ctx, run, reconstruction)["returned"] == {"tables": 0}
    trace = trace_for(ctx, run, interpretation)
    assert trace["phase"] == "COMPLETED"
    assert trace["provider_outcome"] == "SKIPPED_EMPTY_PREREQUISITE"
    assert trace["returned"] is None and trace["counts"]["PUBLISHED_TABLES"] == 0
    assert extraction_detail(ctx, run["run"]["id"])["execution"]["provider_calls_started"] == 1
