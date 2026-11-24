"""Reconstruct pinned Stage 2 input and emit only content-free metrics."""

import argparse
import json
from types import SimpleNamespace
from uuid import UUID

import httpx

from extraction_worker.openai_extraction import responses_body
from powerforge_api.db import get_session_factory
from powerforge_document_processing.storage.factory import build_s3_storage
from powerforge_extraction.compact_context import expand_compact_page, reading_rows
from powerforge_extraction.controls import RunExecution, UnitExecution
from powerforge_extraction.extraction_profile import (
    REASONING_MODEL,
    extraction_profile,
    prompt_bundle,
    stage_request_hash,
)
from powerforge_extraction.identities import canonical_json
from powerforge_extraction.models import ExtractionWorkUnit
from powerforge_extraction.performance import (
    AttemptPerformance,
    active_performance,
    request_metrics,
)
from powerforge_extraction.pinned_sources import bound_snapshot, load_bound
from powerforge_extraction.profiles import read_profile
from powerforge_extraction.stage_contracts import (
    ATTRIBUTE_INPUT_VERSION,
    LEGACY_ATTRIBUTE_INPUT_VERSION,
)
from powerforge_extraction.stage_execution import (
    _build_request,
    prerequisite_result,
    provider_input,
    request_for,
)
from powerforge_shared.config import get_settings


def measure_attempt(
    factory, storage, settings, unit_id, reproject, compare_efforts, compare_context
):
    with factory() as session:
        unit = session.get(ExtractionWorkUnit, unit_id)
        if unit is None or unit.stage != "ATTRIBUTE_EXTRACTION":
            raise ValueError("A Stage 2 attempt ID is required")
        digest = session.get(UnitExecution, unit.id).provider_request_hash
        profile = (
            extraction_profile(settings)
            if reproject
            else read_profile(session.get(RunExecution, unit.run_id).configuration)
        )
        claim = SimpleNamespace(
            unit_id=unit.id,
            unit_key=unit.unit_key,
            profile=profile,
            attempt_number=unit.attempt_number,
        )
        if reproject:
            snapshot = bound_snapshot(session, unit)
            parent = prerequisite_result(session, unit)
            source = load_bound(snapshot, storage, unit, profile)
            wire, request, source = _build_request(
                unit, parent, snapshot.layout.owner, source, claim
            )

    performance = AttemptPerformance()
    if not reproject:
        token = active_performance.set(performance)
        try:
            wire, request, source = request_for(factory, storage, claim)
        finally:
            active_performance.reset(token)
    if request is None:
        raise ValueError("Selected attempt has no eligible attributes")
    if not reproject and (
        not digest or stage_request_hash(request.text, request.reasoning_effort) != digest
    ):
        raise ValueError("Reconstruction differs from recorded provider dispatch")

    payload = json.loads(request.text)
    body = responses_body(request, request.response_model)
    encoded = httpx.Request("POST", "https://api.openai.com/v1/responses", json=body).content
    metrics = request_metrics(
        payload,
        body_bytes=len(encoded),
        encoded_image_bytes=4 * ((len(request.image) + 2) // 3),
        image_detail=request.image_detail,
        instructions=request.instructions,
        schema_bytes=len(canonical_json(body["text"]["format"]["schema"]).encode()),
    )
    rows = reading_rows(payload["page"]["readings"])
    if [row[0] for row in rows] != [reading.reading_ref for reading in wire.page.readings]:
        raise ValueError("Provider view differs from pinned reading references")
    result = {
        "work_unit_id": str(unit_id),
        "matches_recorded_dispatch": not reproject,
        "text_bytes": len(request.text.encode()),
        "provider_view": metrics.model_dump(exclude_none=True),
        "source_load_ms": performance.source_load_ms,
        "request_build_ms": performance.request_build_ms,
    }

    if compare_efforts:
        if request.model != REASONING_MODEL:
            raise ValueError(
                "The source attempt uses a model outside the Stage 2 effort evaluation"
            )
        original = {key: value for key, value in body.items() if key != "reasoning"}
        variants = {}
        for effort in ("medium", "low", "none"):
            variant = request.model_copy(update={"reasoning_effort": effort})
            transport = responses_body(variant, variant.response_model)
            assert transport.pop("reasoning") == {"effort": effort}
            if transport != original:
                raise ValueError("Benchmark request differs outside reasoning effort")
            transport["reasoning"] = {"effort": effort}
            variants[effort] = {
                "request_sha256": stage_request_hash(variant.text, effort),
                "body_bytes": len(
                    httpx.Request(
                        "POST", "https://api.openai.com/v1/responses", json=transport
                    ).content
                ),
            }
        result["matched_reasoning_variants"] = variants
    if compare_context:
        result["matched_context_views"] = measure_context_views(wire, request)
    return result


def measure_context_views(wire, request):
    def measure(value):
        return len(canonical_json(value).encode())

    baseline, candidate = (
        provider_input(wire.model_copy(update={"input_version": version}))
        for version in (LEGACY_ATTRIBUTE_INPUT_VERSION, ATTRIBUTE_INPUT_VERSION)
    )
    expanded = {
        **candidate,
        "input_version": baseline["input_version"],
        "page": expand_compact_page(candidate["page"]),
    }
    if expanded != baseline:
        raise ValueError("Compact page did not reproduce every baseline reading and relationship")
    views = {}
    for payload in (baseline, candidate):
        version = payload["input_version"]
        _, prompts = prompt_bundle(version)
        # Compare using explicit medium, including older attempts pinned to the provider default.
        transport = request.model_copy(
            update={
                "text": canonical_json(payload),
                "instructions": prompts[request.stage],
                "reasoning_effort": "medium",
            }
        )
        body = responses_body(transport, transport.response_model)
        http = httpx.Request("POST", "https://api.openai.com/v1/responses", json=body)
        page = payload["page"]
        layout = page["layout"]
        views[version] = {
            "text_bytes": len(transport.text.encode()),
            "body_bytes": len(http.content),
            "reading_bytes": measure(page["readings"]),
            "layout_bytes": measure(layout),
            "reading_source_bytes": measure(layout.get("reading_sources", {})),
            "overlap_bytes": measure(layout["overlaps"]),
            "support_dictionary_bytes": measure(layout.get("support", [])),
            "table_bytes": measure(layout["tables"]),
            "catalog_bytes": measure(payload["attribute_catalog"]),
            "group_count": sum(isinstance(row, dict) for row in page["readings"]["rows"]),
            "reading_count": sum(1 for _ in reading_rows(page["readings"])),
            "stage_request_sha256": stage_request_hash(transport.text, transport.reasoning_effort),
        }
    return views


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("attempt", type=UUID, nargs="+")
    parser.add_argument(
        "--reproject", action="store_true", help="Use current wire with verified older sources"
    )
    parser.add_argument(
        "--compare-efforts", action="store_true", help="Verify matched offline variants"
    )
    parser.add_argument("--compare-context", action="store_true", help="Compare v1/v2 offline")
    args = parser.parse_args()
    settings = get_settings()
    factory = get_session_factory()
    storage = build_s3_storage(settings)
    for unit_id in args.attempt:
        print(
            json.dumps(
                measure_attempt(
                    factory,
                    storage,
                    settings,
                    unit_id,
                    args.reproject,
                    args.compare_efforts,
                    args.compare_context,
                )
            )
        )


if __name__ == "__main__":
    main()
