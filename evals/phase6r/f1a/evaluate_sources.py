"""Run the F1-A experiment offline, using original PDFs and the local OCR engine."""

import argparse
import json
import platform
from collections import Counter, defaultdict
from dataclasses import replace
from itertools import combinations
from pathlib import Path
from statistics import median
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pymupdf
from PIL import Image
from source_metrics import Word, contains_center, normalized_region, score
from source_ocr import RegionalOCR
from verify_ground_truth import CORPUS, FIXTURES, Fixture

from extraction_worker.spatial_evaluation import MeteredStorage, derive, measure, prepare, render
from extraction_worker.tesseract import TesseractProvider
from powerforge_ai.ocr import OCRFailure
from powerforge_document_processing.layout_derive import layout_rules_identity
from powerforge_document_processing.native_spatial import extract_native
from powerforge_document_processing.rendering import RenderingFailed
from powerforge_engineering_model.enums import EquipmentType
from powerforge_extraction.compact_context import reading_rows
from powerforge_extraction.enrichment_prepare import sha
from powerforge_extraction.enrichment_profiles import preparation_profile
from powerforge_extraction.extraction_profile import STAGES, extraction_profile
from powerforge_extraction.layout_sources import PreparedSnapshot
from powerforge_extraction.pinned_sources import load_bound
from powerforge_extraction.provider_body import encoded_body, responses_body
from powerforge_extraction.stage_contracts import VERSION, RecognitionResponse, contract_hash
from powerforge_extraction.stage_execution import _build_request, project_page
from powerforge_provenance.spatial_base import POLICY, canonical_json
from powerforge_provenance.spatial_sources import PreparedPage, load_positioned_text
from powerforge_shared.config import Settings

ARMS = ("existing", "native_only", "full_ocr", "regional_ocr", "hybrid")
VERSION_ID = "f1a-source-coverage-v1"


def settings_for(provider):
    return Settings(
        _env_file=None,
        enrichment_enabled=True,
        enrichment_ocr_configuration=json.dumps(
            {
                "identity": provider.identity.model_dump(mode="json"),
                "settings": provider.settings.model_dump(mode="json"),
            }
        ),
        extraction_attribute_input_version="compact-page-v1",
        extraction_attribute_prompt_variant="core-catalog-v1",
        extraction_attribute_output_version="server-owned-assertions-v1",
        extraction_attribute_reasoning_effort="medium",
    )


def representations(output):
    result = {}
    for descriptor in output.manifest.representations:
        body, _ = load_positioned_text(
            output.manifest,
            descriptor.ref,
            output.blobs[descriptor.geometry_artifact.id][1],
            output.blobs[descriptor.text_artifact.id][1],
        )
        result[descriptor.ref] = body
    return result


def prepared_words(bodies):
    return [
        Word(
            f"{alias}/{token.ref}",
            token.raw_text,
            normalized_region(body.transform.map_rectangle(token.source_box))
            if token.source_box
            else None,
            body.producer.kind,
        )
        for alias, body in bodies.items()
        for token in body.tokens
    ]


def prepare_arm(case, path, data, page, storage, profile, provider, arm, native):
    def without_native_geometry(*_):
        return replace(native, readings=(), primitives=(), drawing_limitation=None)

    # Restrict the experimental input to one modality. The real prepare function
    # still owns rasterization, token geometry, and pinning. Patches never escape
    # this single-threaded benchmark process.
    def factory():
        return provider

    if arm in ("full_ocr", "regional_ocr"):
        with patch(
            "powerforge_extraction.enrichment_prepare.extract_native", without_native_geometry
        ):
            output, snapshot, base = prepare(
                case, path, data, page, storage, profile, factory, lambda: None
            )
        manifest = output.manifest.model_dump()
        manifest["representations"] = tuple(
            r for r in output.manifest.representations if r.ref == "ocr"
        )
        manifest = PreparedPage.model_validate(manifest)
        output = replace(output, manifest=manifest)
        return output, PreparedSnapshot(manifest, snapshot.objects), base
    if arm == "native_only":
        with patch(
            "powerforge_extraction.enrichment_prepare.eligibility",
            return_value=(False, "BENCHMARK_NATIVE_ONLY"),
        ):
            return prepare(case, path, data, page, storage, profile, factory, lambda: None)
    return prepare(case, path, data, page, storage, profile, factory, lambda: None)


def packed_page(source, profile):
    # Fixed synthetic prerequisite on every page and arm. This measures packed
    # source and request size while excluding equipment-recognition variation.
    context = project_page(source)
    page_hash = contract_hash(context)
    recognition = RecognitionResponse(
        version=VERSION,
        stage=STAGES[0],
        page_context_hash=page_hash,
        equipment=(
            {
                "local_ref": "size-control",
                "source_description": "Benchmark control",
                "registry_type": EquipmentType.BUS,
                "tag_state": "ABSENT",
                "tag": None,
                "qualification": "UNKNOWN",
                "raw_qualification": None,
                "evidence": (),
            },
        ),
    )
    parent = SimpleNamespace(
        page_context_hash=page_hash,
        result_hash=contract_hash(recognition),
        payload=recognition.model_dump(mode="json"),
    )
    unit = SimpleNamespace(stage=STAGES[1])
    claim = SimpleNamespace(
        profile=profile,
        unit_id=source.unit_id,
        unit_key="ATTRIBUTE_EXTRACTION:benchmark",
        attempt_number=1,
    )
    _, request, _ = _build_request(unit, parent, context.owner, source, claim)
    payload = json.loads(request.text)
    wire = payload["page"]
    if wire["layout"]["tables"] != context.layout.model_dump(mode="json")["tables"]:
        raise ValueError("Packed table topology differs from the pinned layout")
    word_rows = list(reading_rows(wire["readings"]))
    expected = [
        (reading.reading_ref, reading.text, list(reading.alternate_texts))
        for reading in context.readings
    ]
    observed = [(ref, text, alternates) for ref, text, _, alternates, *_ in word_rows]
    if observed != expected:
        raise ValueError("Packed text or alternate readings differ from the pinned layout")
    return word_rows, {
        "image_bytes": len(source.image),
        "source_json_bytes": len(canonical_json(wire).encode()),
        "user_json_bytes": len(request.text.encode()),
        "text_token_proxy_utf8_bytes_div_4": round(
            len((request.instructions + request.text).encode()) / 4
        ),
        "encoded_body_bytes": len(encoded_body(responses_body(request, request.response_model))),
    }


def words_from_pack(rows):
    for ref, text, modality, _, _, x, y, w, h in rows:
        box = None if x is None else (float(x), float(y), float(x) + float(w), float(y) + float(h))
        yield Word(ref, text, box, modality)


def duplicates(words):
    buckets = defaultdict(list)
    for word in words:
        if word.box:
            buckets[word.text].append(word.box)
    result = 0
    for boxes in buckets.values():
        for a, b in combinations(boxes, 2):
            shared = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
                0, min(a[3], b[3]) - max(a[1], b[1])
            )
            smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
            if shared >= 0.8 * smaller:
                result += 1
    return result


def confidence_stats(bodies):
    words = [
        token for body in bodies.values() if body.producer.kind == "OCR" for token in body.tokens
    ]
    values = [float(w.confidence.value) for w in words if w.confidence is not None]
    return dict(
        words=len(words),
        missing_confidence=len(words) - len(values),
        below_50=sum(v < 50 for v in values),
        median=round(median(values), 2) if values else None,
    )


def run_arm(
    path,
    data,
    rendered,
    page_number,
    native,
    profile,
    provider,
    extraction,
    arm,
    *,
    reading_details=False,
):
    timings, metadata, streams = {}, {}, {}
    layout, error = None, None
    storage = MeteredStorage(None)
    case = SimpleNamespace(
        page=page_number,
        sha256=sha(data),
        size_bytes=len(data),
        force_ocr=arm not in ("existing", "native_only"),
    )
    stage = "prepare"
    try:
        with measure(timings, stage):
            output, snapshot, base = prepare_arm(
                case, path, data, rendered, storage, profile, provider, arm, native
            )
        bodies = representations(output)
        streams["prepared"] = prepared_words(bodies)
        metadata.update(
            preparation_reason=output.manifest.ocr_reason,
            limitations=output.manifest.limitations,
            ocr=output.usage,
            confidence=confidence_stats(bodies),
            representation_counts={d.ref: d.token_count for d in output.manifest.representations},
            same_location_identical_prepared_pairs=duplicates(streams["prepared"]),
        )
        if hasattr(provider, "receipts"):
            metadata["regional_crops"] = provider.receipts
            metadata["ocr"]["engine_invocations"] = len(provider.receipts)
        stage = "layout"
        with measure(timings, stage):
            bound = derive(snapshot, output, base, storage)
        layout = bound.layout
        metadata.update(
            layout_tables=len(layout.tables),
            layout_unresolved=dict(Counter(item.reason for item in layout.unresolved)),
            overlap_pairs=dict(Counter(item.kind for item in layout.overlaps)),
            reading_issues=dict(Counter(issue for r in layout.readings for issue in r.issues)),
        )
        stage = "pin_and_project"
        with measure(timings, stage):
            identity = SimpleNamespace(
                run_id=uuid4(), id=uuid4(), unit_key="benchmark", stage=STAGES[1]
            )
            pinned = load_bound(bound, storage, identity, extraction)
            context = project_page(pinned)
            streams["readings"] = [
                Word(item.reading_ref, item.text, normalized_region(r.region), item.modality)
                for r, item in zip(layout.readings, context.readings, strict=True)
            ]
            if reading_details:
                tokens = {
                    (alias, token.ref): token.raw_text
                    for alias, body in pinned.bodies.items()
                    for token in body.tokens
                }
                metadata["reading_details"] = {
                    reading.ref: (
                        reading.preferred.representation_ref,
                        tuple(
                            (
                                member.representation_ref,
                                tokens[member.representation_ref, member.ref],
                            )
                            for member in reading.members
                            if member != reading.preferred
                        ),
                        reading.issues,
                    )
                    for reading in layout.readings
                }
                selected = {
                    (member.representation_ref, member.ref)
                    for reading in layout.readings
                    for member in reading.members
                }
                metadata["representation_tokens_absent_from_readings"] = len(
                    tokens.keys() - selected
                )
        metadata["same_location_identical_reading_pairs"] = duplicates(streams["readings"])
        stage = "pack"
        with measure(timings, stage):
            rows, sizes = packed_page(pinned, extraction)
            packed_words = list(words_from_pack(rows))
            if packed_words != streams["readings"]:
                # Exact-decimal region right/bottom become floats at the scorer
                # boundary. Compare those with a fixed tolerance.
                for before, after in zip(streams["readings"], packed_words, strict=True):
                    if (before.ref, before.text, before.stream) != (
                        after.ref,
                        after.text,
                        after.stream,
                    ):
                        raise ValueError("Packed reading identity differs")
                    if (before.box is None) != (after.box is None) or (
                        before.box
                        and any(
                            abs(a - b) > 1e-12 for a, b in zip(before.box, after.box, strict=True)
                        )
                    ):
                        raise ValueError("Packed reading coordinates differ")
            streams["packed"] = packed_words
            metadata["packing"] = sizes
    except (OCRFailure, RenderingFailed, OSError, ValueError) as exc:
        failure_code = str(getattr(exc, "code", type(exc).__name__))
        detail = exc.errors(include_input=False)[0]["msg"] if hasattr(exc, "errors") else str(exc)
        error = dict(stage=stage, code=failure_code, detail=detail[:250])
    return dict(metadata=metadata, timings=timings, failure=error), streams, layout


def native_words(native):
    # Rotation affects extraction coordinates. This benchmark's seven PDFs are
    # currently upright. Keep failure explicit for any future rotated addition.
    if native.rotation:
        from powerforge_provenance.spatial_geometry import (
            CoordinateFrame,
            Rectangle,
            UprightTransform,
        )

        source = CoordinateFrame(
            unit="PDF_POINTS", width=native.source_width, height=native.source_height
        )
        target = CoordinateFrame(unit="PDF_POINTS", width=native.width, height=native.height)
        transform = UprightTransform(
            source_frame=source,
            target_frame=target,
            source_region=source.bounds,
            target_region=target.bounds,
            rotation_degrees=native.rotation,
        )

        def box(reading):
            return normalized_region(
                transform.map_rectangle(
                    Rectangle(x=reading[0], y=reading[1], width=reading[2], height=reading[3])
                )
            )
    else:

        def box(reading):
            x, y, w, h = map(float, reading)
            return (
                x / float(native.width),
                y / float(native.height),
                (x + w) / float(native.width),
                (y + h) / float(native.height),
            )

    return [
        Word(f"n{index}", reading.text, box(reading.box) if reading.box else None, "NATIVE_PDF")
        for index, reading in enumerate(native.readings)
    ]


def adaptive_signals(rendered, native):
    """A deliberately simple source-only coverage proxy, independent of gold."""
    from io import BytesIO

    with Image.open(BytesIO(rendered.analysis_png)) as image:
        sample = image.convert("L").resize((400, 400))
    empty_ink = 0
    for row in range(4):
        for col in range(4):
            x, y = col * 100, row * 100
            ink = sum(sample.crop((x, y, x + 100, y + 100)).histogram()[:160]) / 10_000
            box = (col / 4, row / 4, (col + 1) / 4, (row + 1) / 4)
            if 0.007 <= ink <= 0.98 and not any(contains_center(box, w.box) for w in native):
                empty_ink += 1
    return {"ink_tiles_without_native_centers": empty_ink, "would_select_hybrid": empty_ink >= 3}


def evaluate(source_dir, repeats, provider):
    regional = RegionalOCR(provider)
    profiles = [preparation_profile(settings_for(item)) for item in (provider, regional)]
    extraction = extraction_profile(settings_for(provider))
    results = []
    for filename, expected in CORPUS.items():
        fixture_path = FIXTURES / Path(filename).with_suffix(".json")
        fixture_bytes = fixture_path.read_bytes()
        fixture = Fixture.model_validate_json(fixture_bytes)
        source_path = source_dir / filename
        data = source_path.read_bytes()
        if fixture.pdf != filename or sha(data) != fixture.sha256:
            raise ValueError(f"Original differs from reviewed fixture: {filename}")
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            if doc.page_count != expected or [page.pdf_page for page in fixture.pages] != list(
                range(1, expected + 1)
            ):
                raise ValueError(f"Incomplete source review: {filename}")
        for number in range(1, expected + 1):
            shared_timings = {}
            with measure(shared_timings, "analysis_render"):
                rendered = render(source_path, data, number)
            with measure(shared_timings, "native_inspection"):
                native = extract_native(data, number)
            raw = native_words(native)
            with measure(shared_timings, "adaptive_signal"):
                adaptive = adaptive_signals(rendered, raw)
            finished = {}
            for index in range(repeats):
                order = ARMS[index % len(ARMS) :] + ARMS[: index % len(ARMS)]
                for arm in order:
                    reg = arm == "regional_ocr"
                    run = run_arm(
                        source_path,
                        data,
                        rendered,
                        number,
                        native,
                        profiles[reg],
                        regional if reg else provider,
                        extraction,
                        arm,
                    )
                    finished.setdefault(arm, []).append(run)
            # Score only after every arm has produced its own source projection.
            gold = fixture.pages[number - 1]
            arms = {}
            for arm, runs in finished.items():
                first, streams, layout = runs[0]
                fingerprint = {
                    stage: sha(canonical_json([w.__dict__ for w in words]).encode())
                    for stage, words in streams.items()
                }
                for attempt, later, later_layout in runs[1:]:
                    actual = {
                        stage: sha(canonical_json([w.__dict__ for w in words]).encode())
                        for stage, words in later.items()
                    }
                    if (
                        attempt["failure"] != first["failure"]
                        or actual != fingerprint
                        or ((layout is None) != (later_layout is None))
                        or any(
                            attempt["metadata"].get(field) != first["metadata"].get(field)
                            for field in (
                                "layout_tables",
                                "layout_unresolved",
                                "overlap_pairs",
                                "packing",
                            )
                        )
                    ):
                        raise ValueError(f"Nonrepeatable source output: {filename} p{number} {arm}")
                arms[arm] = dict(
                    metadata=first["metadata"],
                    failure=first["failure"],
                    fingerprints=fingerprint,
                    timings=[run["timings"] for run, _, _ in runs],
                    stages={
                        stage: score(
                            gold, streams.get(stage, ()), layout if stage != "prepared" else None
                        )
                        for stage in ("prepared", "readings", "packed")
                    },
                )
            results.append(
                dict(
                    pdf=filename,
                    page=number,
                    source_sha256=fixture.sha256,
                    fixture_sha256=sha(fixture_bytes),
                    shared_timings=shared_timings,
                    adaptive=adaptive,
                    native=dict(
                        words=len(raw),
                        characters=native.characters,
                        base_artifact_characters=rendered.native_text_char_count,
                        replacement_characters=native.replacement_characters,
                        raster_boxes=len(native.raster_boxes),
                        primitives=len(native.primitives),
                        limitation=native.drawing_limitation,
                    ),
                    raster=dict(
                        width=rendered.width_px,
                        height=rendered.height_px,
                        bytes=len(rendered.analysis_png),
                    ),
                    native_extraction=score(gold, raw),
                    base_text_availability=score(
                        gold,
                        [
                            Word(f"b{i}", text, None, "NATIVE_TEXT_ARTIFACT")
                            for i, text in enumerate((rendered.native_text or "").split())
                        ],
                    )["status"],
                    arms=arms,
                )
            )
            print(f"Finished {filename} p{number}", flush=True)
    return dict(
        version=VERSION_ID,
        runtime=platform.platform(),
        pymupdf=pymupdf.VersionBind,
        repeats=repeats,
        preparation_profile_hash=profiles[0].identity_hash,
        regional_profile_hash=profiles[1].identity_hash,
        layout_rules_hash=layout_rules_identity(),
        extraction_profile_hash=extraction.identity_hash,
        extraction_limits=dict(
            transport_bytes=extraction.max_transport_bytes,
            image_bytes=extraction.max_input_bytes,
            image_pixels=extraction.max_image_pixels,
        ),
        preparation_limits=dict(POLICY),
        ocr_identity=provider.identity.model_dump(mode="json"),
        ocr_settings=provider.settings.model_dump(mode="json"),
        regional_ocr_identity=regional.identity.model_dump(mode="json"),
        pages=results,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--tesseract", default="/usr/bin/tesseract")
    parser.add_argument("--tessdata", default="/usr/share/tesseract-ocr/5/tessdata")
    args = parser.parse_args()
    if not 1 <= args.repeats <= 5:
        parser.error("repeats must be between 1 and 5")
    provider = TesseractProvider(args.tesseract, args.tessdata)
    result = evaluate(args.source_dir, args.repeats, provider)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
