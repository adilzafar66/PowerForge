"""Rescore F1-A, then evaluate supplementary and page-diagnostic OCR locally."""

import argparse
import json
import platform
from dataclasses import asdict
from pathlib import Path
from statistics import mean
from unittest.mock import patch

import pymupdf
from evaluate_sources import ARMS, native_words, run_arm, settings_for
from ocr_experiments import SWEEP, ExperimentOCR, Recipe, raster_at, request_check
from PIL import __version__ as pillow_version
from refined_scoring import LOCATED, construction_changes, refined_score
from source_ocr import RegionalOCR
from verify_ground_truth import CORPUS, FIXTURES, Fixture

from extraction_worker.spatial_evaluation import measure, render
from extraction_worker.tesseract import TesseractProvider
from powerforge_document_processing.native_spatial import extract_native
from powerforge_extraction.enrichment_prepare import sha
from powerforge_extraction.enrichment_profiles import preparation_profile
from powerforge_extraction.extraction_profile import extraction_profile
from powerforge_provenance.spatial_base import canonical_json

SCHNEIDER = "schneider-panel-drawing.pdf"
SUPPLEMENT = {
    "hybrid_regional": Recipe(regions="tiles"),
    "hybrid_selective": Recipe(regions="sparse"),
}
DIAGNOSTICS = {"control300": Recipe(), **SWEEP}


def fixture_cases(source_dir):
    result = []
    for filename, expected in CORPUS.items():
        path = source_dir / filename
        data = path.read_bytes()
        source = (FIXTURES / Path(filename).with_suffix(".json")).read_bytes()
        gold = Fixture.model_validate_json(source)
        if gold.pdf != filename or gold.sha256 != sha(data):
            raise ValueError(f"Original differs from approved fixture: {filename}")
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            if len(doc) != expected or [page.pdf_page for page in gold.pages] != list(
                range(1, expected + 1)
            ):
                raise ValueError(f"Incomplete approved page set: {filename}")
        for page in gold.pages:
            result.append((path, data, sha(source), page))
    return result


def located(result):
    return sum(result["status"].get(state, 0) for state in LOCATED)


def elapsed(attempts):
    return mean(sum(stage["wall_ms"] for stage in attempt.values()) for attempt in attempts)


def evaluate_arm(path, data, page, gold, native, extraction, provider, arm, repeats):
    profile = preparation_profile(settings_for(provider))
    experimental = isinstance(provider, ExperimentOCR)
    attempts = []
    for _ in range(repeats):
        options = (path, data, page, gold.pdf_page, native, profile, provider, extraction, arm)
        if experimental:
            with patch(
                "powerforge_extraction.enrichment_prepare.rasterize_pdf",
                raster_at(provider.recipe.dpi),
            ):
                record, streams, layout = run_arm(*options, reading_details=True)
            record["metadata"]["ocr_raster"] = provider.input
        else:
            record, streams, layout = run_arm(*options, reading_details=True)
        witnesses = record["metadata"].pop("reading_details", {})
        fingerprints = {
            name: sha(canonical_json([w.__dict__ for w in words]).encode())
            for name, words in streams.items()
        }
        fingerprints["alternate_witnesses"] = sha(canonical_json(witnesses).encode())
        if not attempts:
            first = record
            first_fingerprints = fingerprints
            first_witnesses = witnesses
            first_streams = streams
            first_layout = layout
        elif (
            first_fingerprints != fingerprints
            or first["failure"] != record["failure"]
            or first["metadata"].get("packing") != record["metadata"].get("packing")
        ):
            raise ValueError(f"Unstable repeated projection: {path.name}/{gold.pdf_page}/{arm}")
        attempts.append(record["timings"])
    stages = {
        stage: refined_score(
            gold,
            first_streams.get(stage, ()),
            first_layout if stage != "prepared" else None,
            first_witnesses if stage != "prepared" else None,
            associations=stage == "packed",
        )
        for stage in ("prepared", "readings", "packed")
    }
    return dict(
        metadata=first["metadata"],
        failure=first["failure"],
        fingerprints=first_fingerprints,
        timings=attempts,
        stages=stages,
        construction_changes=construction_changes(stages["prepared"], stages["readings"]),
    )


def benchmark(source_dir, provider, repeats):
    request_check(provider)
    engines = {
        "base": provider,
        "regional": RegionalOCR(provider),
        **{
            key: ExperimentOCR(provider, recipe)
            for key, recipe in (SUPPLEMENT | DIAGNOSTICS).items()
        },
    }
    extraction = extraction_profile(settings_for(provider))
    cases, pages = {}, {}
    for path, data, fixture_hash, gold in fixture_cases(source_dir):
        identity = f"{path.name}:{gold.pdf_page}"
        timings = {}
        with measure(timings, "shared_analysis_render"):
            page = render(path, data, gold.pdf_page)
        with measure(timings, "shared_native_inspection"):
            native = extract_native(data, gold.pdf_page)
        cases[identity] = (path, data, page, gold, native)
        pages[identity] = dict(
            pdf=path.name,
            page=gold.pdf_page,
            source_sha256=sha(data),
            fixture_sha256=fixture_hash,
            shared_timings=timings,
            arms={},
        )

    def compare(names, page_ids, experiment=False):
        for identity in page_ids:
            path, data, page, gold, native = cases[identity]
            raw = native_words(native)
            for name in names:
                if experiment:
                    engine = engines[name]
                    engine.native = raw
                    engine.input = None
                    engine.receipts = []
                    arm = name
                else:
                    engine = engines["regional" if name == "regional_ocr" else "base"]
                    arm = name
                pages[identity]["arms"][name] = evaluate_arm(
                    path,
                    data,
                    page,
                    gold,
                    native,
                    extraction,
                    engine,
                    arm,
                    repeats,
                )
                print(f"{identity} {name}", flush=True)

    compare(ARMS, pages)
    compare(SUPPLEMENT, pages, experiment=True)
    target = next(key for key, value in pages.items() if value["pdf"] == SCHNEIDER)
    compare(DIAGNOSTICS, [target], experiment=True)

    def key(name):
        result = pages[target]["arms"][name]
        packed = result["stages"]["packed"]
        totals = packed["available"]["totals"]
        return (
            -located(packed["available"]),
            -totals["located_numeric_literals"],
            totals["edit_distance"],
            elapsed(result["timings"]),
            name,
        )

    # The sweep chooses configurations on the development page. Cross-document
    # checks detect regressions on this corpus and do not serve as held-out validation.
    promoted = sorted(
        (name for name in SWEEP if pages[target]["arms"][name]["failure"] is None),
        key=key,
    )[:2]
    compare(promoted, [identity for identity in pages if identity != target], experiment=True)
    return dict(
        version="f1a2-source-refinement-v1",
        repeats=repeats,
        runtime=platform.platform(),
        pymupdf=pymupdf.VersionBind,
        pillow=pillow_version,
        extraction_profile_hash=extraction.identity_hash,
        engines={
            name: dict(
                identity=engine.identity.model_dump(mode="json"),
                settings=engine.settings.model_dump(mode="json"),
                preparation_profile_hash=preparation_profile(settings_for(engine)).identity_hash,
                recipe=asdict(engine.recipe) if isinstance(engine, ExperimentOCR) else None,
            )
            for name, engine in engines.items()
        },
        promoted=promoted,
        pages=list(pages.values()),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--repeats", type=int, choices=range(1, 4), default=2)
    parser.add_argument("--tesseract", default="/usr/bin/tesseract")
    parser.add_argument("--tessdata", default="/usr/share/tesseract-ocr/5/tessdata")
    args = parser.parse_args()
    result = benchmark(
        args.source_dir, TesseractProvider(args.tesseract, args.tessdata), args.repeats
    )
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
