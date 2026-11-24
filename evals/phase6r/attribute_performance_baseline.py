"""Reconstruct pinned Stage 2 input and emit only content-free metrics."""

import argparse
import json
from copy import deepcopy
from itertools import pairwise
from types import SimpleNamespace
from uuid import UUID

import httpx

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
from powerforge_extraction.identities import canonical_json, identity_hash
from powerforge_extraction.models import ExtractionWorkUnit
from powerforge_extraction.performance import (
    AttemptPerformance,
    active_performance,
    request_metrics,
)
from powerforge_extraction.pinned_sources import bound_snapshot, load_bound
from powerforge_extraction.profiles import read_profile
from powerforge_extraction.provider_body import dispatch_hash, encoded_body, responses_body
from powerforge_extraction.readable_context import reading_blocks
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
from powerforge_shared.config import EXPERIMENTAL_INPUTS, get_settings


def reconstruct_attempt(factory, storage, settings, unit_id, reproject):
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
    if not reproject and (not digest or dispatch_hash(request) != digest):
        raise ValueError("Reconstruction differs from recorded provider dispatch")

    return wire, request, source, performance


def measure_attempt(
    factory,
    storage,
    settings,
    unit_id,
    reproject,
    compare_efforts,
    compare_context,
    compare_modalities=False,
):
    wire, request, source, performance = reconstruct_attempt(
        factory, storage, settings, unit_id, reproject
    )
    if compare_modalities:
        return {
            "work_unit_id": str(unit_id),
            "historical_dispatch_verified": not reproject,
            "modalities": measure_modalities(wire, request, source.image),
        }
    payload = json.loads(request.text)
    body = responses_body(request, request.response_model)
    encoded = httpx.Request("POST", "https://api.openai.com/v1/responses", json=body).content
    metrics = request_metrics(
        payload,
        body_bytes=len(encoded),
        encoded_image_bytes=4 * ((len(request.image or b"") + 2) // 3),
        image_detail=request.image_detail,
        instructions=request.instructions,
        schema_bytes=len(canonical_json(body["text"]["format"]["schema"]).encode()),
    )
    if wire.input_version not in EXPERIMENTAL_INPUTS:
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


def measure_modalities(wire, request, pinned_image):
    def size(value):
        return len(canonical_json(value).encode())

    rows = {}
    for version in (LEGACY_ATTRIBUTE_INPUT_VERSION, ATTRIBUTE_INPUT_VERSION, *EXPERIMENTAL_INPUTS):
        variant = wire.model_copy(update={"input_version": version})
        payload = provider_input(variant)
        assert canonical_json(payload) == canonical_json(provider_input(variant))
        page = payload.get("page", {})
        if "blocks" in page:
            exposed = [
                (ref, literal)
                for block in reading_blocks(page)
                for line in block["lines"]
                for ref, literal, *_ in line
            ]
        elif page:
            exposed = [(r[0], r[1]) for r in reading_rows(page["readings"])]
        else:
            exposed = []
        expected = [(r.reading_ref, r.text) for r in wire.page.readings]
        assert sorted(exposed) == ([] if version == "image-only-v1" else sorted(expected))
        image = None if version == "readable-text-v1" else pinned_image
        if image is None and version != "readable-text-v1":
            raise ValueError("Comparison requires the pinned original image")
        transport = request.model_copy(
            update={
                "input_version": version,
                "text": canonical_json(payload),
                "image": image,
                "image_mime_type": "image/png" if image else None,
                "instructions": prompt_bundle(version)[1][request.stage],
                "reasoning_effort": "medium",
            }
        )
        body = responses_body(transport, transport.response_model)
        # All experimental live comparisons request standard tier, including baseline controls.
        body["service_tier"] = "default"
        layout = deepcopy(page)
        if "blocks" in page:
            readings = list(reading_blocks(page))
            layout.pop("blocks")
            for table in layout.get("tables", []):
                for row in table.get("rows", []):
                    for cell in row:
                        cell.pop("blocks", None)
            geometry = [
                entry[2]
                for block in readings
                for line in block["lines"]
                for entry in line
                if len(entry) > 2
            ]
            by_ref = {
                ref: box for block in readings for line in block["lines"] for ref, _, *box in line
            }
            for loc, reading in zip(wire.page.layout.readings, wire.page.readings, strict=True):
                box = loc.region.model_dump(mode="json") if loc.region else None
                expected_box = [[box[k] for k in ("x", "y", "width", "height")]] if box else []
                assert by_ref[loc.ref] == expected_box
                note = page.get("notes", {}).get(loc.ref, {})
                assert tuple(note.get("issues", ())) == loc.issues
                assert tuple(a[1] for a in note.get("alternatives", ())) == reading.alternate_texts
            grouped = {
                (a[0], b[0], "SAME_BASELINE")
                for block in readings
                for line in block["lines"]
                for a, b in pairwise(line)
            }
            assert grouped | set(map(tuple, page.get("order", []))) == {
                (e.before, e.after, e.basis) for e in wire.page.layout.order
            }
            members = {m: loc.ref for loc in wire.page.layout.readings for m in loc.members}
            assert page.get("overlaps", []) == [
                [members[edge.left], members[edge.right], edge.kind]
                for edge in wire.page.layout.overlaps
            ]
            assert [item["reason"] for item in page.get("unresolved", [])] == [
                item.reason for item in wire.page.layout.unresolved
            ]
            assert len(page.get("tables", [])) == len(wire.page.layout.tables)
            relations = layout
        else:
            readings = layout.pop("readings", [])
            geometry = [r[-4:] for r in reading_rows(readings)] if readings else []
            relations = layout.get("layout", {})

        def section(key, relations=relations):
            return size(relations[key]) if key in relations else 0

        rows[version] = dict(
            text_bytes=len(transport.text.encode()),
            geometry_bytes=size(geometry) if geometry else 0,
            literal_bytes=size([t for _, t in exposed]) if exposed else 0,
            table_bytes=section("tables"),
            overlap_bytes=section("overlaps"),
            order_bytes=section("order"),
            annotation_bytes=section("notes"),
            witness_bytes=section("reading_sources"),
            support_bytes=section("support"),
            other_page_metadata_bytes=size({k: v for k, v in layout.items() if k != "layout"})
            if "layout" in layout
            else 0,
            benchmark_body_sha256=identity_hash(body),
            available=len(expected),
            exposed=len(exposed),
            body_bytes=len(encoded_body(body)),
            page_bytes=size(page) if page else 0,
            readings_bytes=size(readings) if page else 0,
            layout_metadata_bytes=size(layout) if layout else 0,
            image_base64_bytes=4 * ((len(image or b"") + 2) // 3),
            catalog_bytes=size(payload["attribute_catalog"]),
            recognition_bytes=size(payload["upstream"]),
            instructions_bytes=len(transport.instructions.encode()),
            schema_bytes=size(body["text"]["format"]["schema"]),
            projection_sha256=identity_hash(payload),
            dispatch_sha256=dispatch_hash(transport),
        )
    return rows


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
    parser.add_argument(
        "--compare-modalities",
        action="store_true",
        help="Verify all five Stage 2 source presets offline",
    )
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
                    args.compare_modalities,
                )
            )
        )


if __name__ == "__main__":
    main()
