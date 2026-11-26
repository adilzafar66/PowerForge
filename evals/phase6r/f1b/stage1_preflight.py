"""Assemble Stage 1 evaluation requests and replay admitted responses without transport."""

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import evaluate_sources as harness
from evaluate_table_ablation import ablation
from occurrence_eval import EVALS, Observation, check_corpus, digest, read_gold
from ocr_experiments import ExperimentOCR, Recipe

from extraction_worker.spatial_evaluation import MeteredStorage, derive, prepare, render
from extraction_worker.tesseract import TesseractProvider
from powerforge_extraction.enrichment_profiles import preparation_profile
from powerforge_extraction.evidence_localization import EvidenceLocalizer
from powerforge_extraction.extraction_profile import STAGES, extraction_profile
from powerforge_extraction.pinned_sources import load_bound
from powerforge_extraction.provider_body import dispatch_hash, encoded_body, responses_body
from powerforge_extraction.stage_contracts import parse_response
from powerforge_extraction.stage_execution import _build_request, project_page, provider_input
from powerforge_provenance.spatial_base import canonical_json

ARMS = ("existing_tables", "positioned_only")


def normalized_region(value):
    x, y, width, height = [float(value[key]) for key in ("x", "y", "width", "height")]
    return x, y, min(1.0, x + width), min(1.0, y + height)


def observations_from_output(source, wire, raw, *, dispatched_digest, request):
    """Use only the verified request and an externally audit-bound output body."""
    if (
        dispatched_digest != dispatch_hash(request)
        or request.work_unit_id != source.unit_id
        or request.stage != STAGES[0]
        or request.image != source.image
        or request.text != canonical_json(provider_input(wire))
        or wire.page != project_page(source)
    ):
        raise ValueError("Stage 1 replay is not bound to the supplied verified source and request")
    admitted = parse_response(wire, raw)
    locator = EvidenceLocalizer(source)
    output = []
    for item in admitted.equipment:
        evidence = [citation for citation in item.evidence if citation.role == "EQUIPMENT"]
        fragments = locator.locate(evidence, "EQUIPMENT")
        resolved = [fragment for fragment in fragments if fragment["localization"] == "RESOLVED"]
        visual = [
            fragment for fragment in fragments if fragment["localization"] == "VISUAL_REPORTED"
        ]
        tag_fragments = locator.locate(
            [citation for citation in item.evidence if citation.role == "TAG"], "TAG"
        )
        regions = [
            normalized_region(value) for fragment in resolved for value in fragment["regions"]
        ]
        regions.extend(normalized_region(fragment["region"]) for fragment in visual)
        output.append(
            Observation(
                local_ref=item.local_ref,
                registry_type=item.registry_type,
                qualification=item.qualification,
                tag_state=item.tag_state,
                tag=item.tag,
                equipment_regions=tuple(regions),
                resolved_equipment_fragments=len(resolved),
                approximate_equipment_fragments=len(visual),
                unresolved_equipment_fragments=len(fragments) - len(resolved) - len(visual),
                resolved_tag_fragments=sum(f["localization"] == "RESOLVED" for f in tag_fragments),
                approximate_tag_fragments=sum(
                    f["localization"] == "VISUAL_REPORTED" for f in tag_fragments
                ),
            )
        )
    return tuple(output)


def as_request(
    path, data, rendered, number, selection, engine, arm, *, recognition_variant="legacy"
):
    settings = harness.settings_for(engine).model_copy(
        update={"extraction_recognition_prompt_variant": recognition_variant}
    )
    prep = preparation_profile(settings)
    extraction = extraction_profile(settings)
    storage = MeteredStorage(None)
    case = SimpleNamespace(
        pdf_page=number,
        page=number,
        size_bytes=len(data),
        sha256=digest(data),
        force_ocr=selection != "native",
    )
    with ablation(arm) as rules:
        if arm == "positioned_only":
            prep = prep.model_copy(
                update={
                    "native": prep.native
                    | {"rules_sha256": harness.sha((prep.native["rules_sha256"] + rules).encode())}
                }
            )
            extraction = extraction.model_copy(update={"source_rules": rules})
        if selection == "native":
            with patch(
                "powerforge_extraction.enrichment_prepare.eligibility",
                return_value=(False, "F1B_EXPLICIT_NATIVE_ONLY"),
            ):
                out, prepared, base = prepare(
                    case, path, data, rendered, storage, prep, lambda: engine, lambda: None
                )
        else:
            out, prepared, base = prepare(
                case, path, data, rendered, storage, prep, lambda: engine, lambda: None
            )
        bound = derive(prepared, out, base, storage)
        unit = SimpleNamespace(
            stage=STAGES[0], run_id=uuid4(), id=uuid4(), unit_key="EQUIPMENT_RECOGNITION:f1b"
        )
        pinned = load_bound(bound, storage, unit, extraction)
        claim = SimpleNamespace(
            profile=extraction, unit_id=unit.id, unit_key=unit.unit_key, attempt_number=1
        )
        wire, request, _ = _build_request(unit, None, pinned.layout.owner, pinned, claim)
    return wire, request, pinned


def comparable(wire):
    page = wire.page
    return dict(
        source=page.source_sha256,
        image_sha256=page.image_sha256,
        image_size=(page.image_width, page.image_height),
        registry=wire.registry_version,
        equipment_catalog=[item.model_dump(mode="json") for item in wire.equipment_catalog],
        readings=[reading.model_dump(mode="json") for reading in page.readings],
        positioned=[item.model_dump(mode="json") for item in page.layout.readings],
    )


def preflight(source_dir, provider):
    gold = read_gold()
    check_corpus(gold, source_dir)
    line_engine = ExperimentOCR(provider, Recipe(preprocess="remove_lines"))
    for split, docs in (
        ("development", gold.development),
        ("structural_control", gold.structural_control),
        ("synthetic_holdout", gold.synthetic_holdout),
    ):
        for doc in docs:
            path = (source_dir if split == "development" else EVALS) / doc.pdf
            raw = path.read_bytes()
            for page in doc.pages:
                rendered = render(path, raw, page.pdf_page)
                engine = line_engine if page.preparation == "hybrid_300_line_removal" else provider
                before = None
                arms = {}
                for arm in ARMS:
                    wire, request, pinned = as_request(
                        path,
                        raw,
                        rendered,
                        page.pdf_page,
                        page.preparation,
                        engine,
                        arm,
                    )
                    body = responses_body(request, request.response_model)
                    control = comparable(wire) | dict(
                        model=request.model,
                        prompt=request.instructions,
                        reasoning=request.reasoning_effort,
                        schema=body["text"]["format"]["schema"],
                        max_output_tokens=request.max_output_tokens,
                        timeout_seconds=request.timeout_seconds,
                        witness_overlaps=[
                            item.model_dump(mode="json") for item in wire.page.layout.overlaps
                        ],
                    )
                    if before is not None and before != control:
                        raise ValueError(f"Stage 1 ablation changed a pinned control: {doc.pdf}")
                    before = control
                    data = encoded_body(body)
                    source_bytes = len(request.text.encode())
                    arms[arm] = dict(
                        body_bytes=len(data),
                        user_json_bytes=source_bytes,
                        table_count=len(pinned.layout.tables),
                        reading_count=len(wire.page.readings),
                        image_sha256=wire.page.image_sha256,
                        rules_sha256=pinned.layout.algorithm_sha256,
                        ocr_producer_sha256=(
                            engine.identity.identity_hash if page.preparation != "native" else None
                        ),
                        ocr_decision=pinned.prepared.ocr_decision,
                    )
                yield dict(
                    split=split,
                    pdf=doc.pdf,
                    page=page.pdf_page,
                    source_sha256=doc.sha256,
                    preparation=page.preparation,
                    arms=arms,
                )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--tesseract", default="/usr/bin/tesseract")
    parser.add_argument("--tessdata", default="/usr/share/tesseract-ocr/5/tessdata")
    args = parser.parse_args()
    provider = TesseractProvider(args.tesseract, args.tessdata)
    results = list(preflight(args.source_dir, provider))
    args.output.write_text(json.dumps(results, indent=2) + "\n")
    print(f"Verified {len(results)} matched local Stage 1 request pairs; sent 0 requests.")


if __name__ == "__main__":
    main()
