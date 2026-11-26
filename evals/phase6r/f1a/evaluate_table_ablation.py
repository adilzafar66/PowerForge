"""Offline ablation of optional tables, with matched source and reading provenance."""

import argparse
import json
import platform
import time
from collections import Counter, defaultdict
from contextlib import ExitStack, contextmanager
from itertools import pairwise
from pathlib import Path
from statistics import mean
from unittest.mock import patch

import evaluate_sources as harness
import pymupdf
from evaluate_refinement import fixture_cases
from refined_scoring import refined_score
from source_metrics import Word, normalized_region, reading_order

from extraction_worker.spatial_evaluation import measure, render
from extraction_worker.tesseract import TesseractProvider
from powerforge_document_processing import layout_derive, layout_grid, native_spatial
from powerforge_extraction.enrichment_profiles import preparation_profile
from powerforge_extraction.evidence_localization import EvidenceLocalizer
from powerforge_extraction.extraction_profile import extraction_profile
from powerforge_extraction.stage_contracts import QuoteCitation, ReadingCitation
from powerforge_provenance.layout_observations import LAYOUT_POLICY, ReadingOrder, SpatialLayout
from powerforge_provenance.spatial_base import identity_hash

VERSION = "f1a2-table-ablation-v1"
ARMS = ("existing_tables", "positioned_only", "simple_lines")
CONTROL = Path(__file__).resolve().parents[2] / "tables/v1/sources/positioned_schedule.pdf"


def line_hints(layout, aspect):
    """Join short adjacent baselines in one witness stream without table roles."""
    by_stream = defaultdict(list)
    lookup = {reading.ref: reading for reading in layout.readings}
    for reading in layout.readings:
        if reading.region:
            by_stream[reading.preferred.representation_ref].append(
                Word(reading.ref, "", normalized_region(reading.region), ""),
            )

    occupied_out = {edge.before for edge in layout.order if edge.basis == "SAME_BASELINE"}
    occupied_in = {edge.after for edge in layout.order if edge.basis == "SAME_BASELINE"}
    edges = list(layout.order)
    for stream in by_stream.values():
        for left, right in pairwise(reading_order(stream)):
            if len(edges) >= LAYOUT_POLICY["max_edges"]:
                return edges
            if (
                left.ref in occupied_out
                or right.ref in occupied_in
                or lookup[left.ref].issues
                or lookup[right.ref].issues
            ):
                continue
            a, b = left.box, right.box
            overlap = min(a[3], b[3]) - max(a[1], b[1])
            height = min(a[3] - a[1], b[3] - b[1])
            gap = b[0] - a[2]
            if overlap >= 0.65 * height and 0 <= gap <= 1.25 * aspect * height:
                edges.append(ReadingOrder(before=left.ref, after=right.ref, basis="SAME_BASELINE"))
                occupied_out.add(left.ref)
                occupied_in.add(right.ref)
    return edges


@contextmanager
def ablation(arm):
    """Keep preparation, layout admission and replay in one scoped variant."""
    original_identity = layout_derive.layout_rules_identity
    original_derivation = layout_derive._derive
    experiment_sha = harness.sha(Path(__file__).read_bytes())

    def identity():
        return identity_hash(
            {"base": original_identity(), "arm": arm, "experiment": experiment_sha}
        )

    def derive(*args):
        result = original_derivation(*args)
        if arm == "positioned_only":
            return result
        frame = args[0].page_frame
        new_order = tuple(line_hints(result, float(frame.height / frame.width)))
        return SpatialLayout.model_validate(result.model_dump() | {"order": new_order})

    with ExitStack() as stack:
        if arm != "existing_tables":
            stack.enter_context(
                patch.object(native_spatial, "drawing_primitives", return_value=((), None))
            )
            stack.enter_context(patch.object(layout_derive, "derive_tables", return_value=([], [])))
            stack.enter_context(patch.object(layout_derive, "layout_rules_identity", identity))
            stack.enter_context(patch.object(layout_derive, "_derive", derive))
        yield layout_derive.layout_rules_identity()


def evidence_probe(source):
    """Replay reading IDs with literal text and the corresponding raw quotations."""
    localizer = EvidenceLocalizer(source, "compact-page-v1")
    reading = []
    quotes = {}
    for item in source.layout.readings[:128]:
        witness = item.preferred
        token = localizer.tokens[witness.representation_ref][witness.ref]
        if not token.raw_text.strip() or len(token.raw_text) > 500:
            continue
        citation = ReadingCitation(
            kind="READING",
            role="VALUE",
            reading_ref=item.ref,
            quote=token.raw_text,
        )
        reading.append(localizer.locate((citation,), "VALUE")[0])
        if token.raw_text not in quotes:
            quote = QuoteCitation(kind="QUOTE", role="VALUE", quote=token.raw_text)
            quotes[token.raw_text] = localizer.locate((quote,), "VALUE")[0]

    def output(fragments):
        counts = Counter(f["localization"] for f in fragments)
        counts["eligible_value_text"] = sum(localizer.value_text(f) is not None for f in fragments)
        # Artifact UUIDs are rerandomized for each in-memory benchmark attempt.
        stable = [{k: v for k, v in f.items() if not k.endswith("_id")} for f in fragments]
        return {"counts": dict(counts), "fingerprint": identity_hash(stable)}

    return {"reading": output(reading), "quote": output(list(quotes.values()))}


def layout_summary(layout, captured):
    members = Counter(m.representation_ref for r in layout.readings for m in r.members)
    return dict(
        layout_identity=layout.algorithm_sha256,
        positioned=sum(r.region is not None for r in layout.readings),
        reading_count=len(layout.readings),
        source_members=dict(members),
        overlap_pairs=dict(Counter(pair.kind for pair in layout.overlaps)),
        edges=dict(Counter(edge.basis for edge in layout.order)),
        table_count=len(layout.tables),
        tables=[
            dict(
                method=t.method,
                rows=t.rows,
                columns=t.columns,
                cells=len(t.cells),
                owned_readings=sum(len(cell.readings) for cell in t.cells),
                header_links=sum(len(cell.headers) for cell in t.cells),
                captions=len(t.captions),
            )
            for t in layout.tables
        ],
        limitations=dict(Counter(note.reason for note in layout.unresolved)),
        primitive_count=sum(r.primitive_count for r in captured.prepared.representations),
        prepared_geometry_bytes=sum(len(data) for data in captured.geometry.values()),
        evidence_probe=evidence_probe(captured),
    )


def run(path, data, rendered, number, native, provider, prep, profile, arm, ocr, *, probe=True):
    load = harness.load_bound
    captured = None

    def fingerprint_source(*args):
        nonlocal captured
        captured = load(*args)
        return captured

    with ablation(arm) as rules, patch.object(harness, "load_bound", fingerprint_source):
        if arm != "existing_tables":
            prep = prep.model_copy(
                update={
                    "native": prep.native
                    | {
                        "rules_sha256": identity_hash(
                            {"native": prep.native["rules_sha256"], "variant": rules}
                        )
                    }
                }
            )
            profile = profile.model_copy(update={"source_rules": rules})
        attempt, streams, layout = harness.run_arm(
            path,
            data,
            rendered,
            number,
            native,
            prep,
            provider,
            profile,
            "hybrid" if ocr == "forced_hybrid" else "existing",
            reading_details=probe,
        )
    return attempt, streams, layout, captured


@contextmanager
def counters_for_baseline():
    """Time nested functions on a separate run to avoid biasing the ablation."""
    totals = {}

    def wrap(original, label):
        def timed(*args, **kwargs):
            start = time.perf_counter_ns()
            try:
                return original(*args, **kwargs)
            finally:
                row = totals.setdefault(label, {"calls": 0, "elapsed_ns": 0})
                row["calls"] += 1
                row["elapsed_ns"] += time.perf_counter_ns() - start

        return timed

    with ExitStack() as stack:
        for module, name, label in (
            (native_spatial, "drawing_primitives", "native_primitive_extraction"),
            (layout_grid, "native_segments", "native_segment_projection"),
            (layout_grid, "connected", "grid_connectivity"),
            (layout_grid, "grid_component", "ruled_partition_and_assignment"),
            (layout_grid, "coverage", "ruled_boundary_coverage_nested"),
            (layout_grid, "contains", "ruled_cell_containment_nested"),
            (layout_grid, "with_headers", "header_assignment_nested"),
            (layout_derive, "borderless_tables", "borderless_partition_and_assignment"),
            (layout_derive, "align_readings", "independent_reading_alignment"),
        ):
            stack.enter_context(patch.object(module, name, wrap(getattr(module, name), label)))
        yield totals


def word_fingerprints(streams):
    return {key: identity_hash([word.__dict__ for word in words]) for key, words in streams.items()}


def verify_repeats(first, current):
    if any(first[field] != current[field] for field in ("fingerprints", "failure", "layout")):
        raise ValueError("Repeated ablation projections differ")
    if first["metadata"].get("packing") != current["metadata"].get("packing"):
        raise ValueError("Repeated packed request sizes differ")


def compare_page(path, data, number, gold, provider, prep, profile, repeats, ocr_modes):
    outer = {}
    with measure(outer, "shared_render"):
        rendered = render(path, data, number)
    with measure(outer, "shared_native_inspection"):
        native = native_spatial.extract_native(data, number)
    results = {}
    for ocr in ocr_modes:
        by_arm = {}
        for index in range(repeats):
            arms = ARMS[index % len(ARMS) :] + ARMS[: index % len(ARMS)]
            for arm in arms:
                out, streams, layout, captured = run(
                    path,
                    data,
                    rendered,
                    number,
                    native,
                    provider,
                    prep,
                    profile,
                    arm,
                    ocr,
                )
                witnesses = out["metadata"].pop("reading_details", {})
                item = dict(
                    metadata=out["metadata"],
                    failure=out["failure"],
                    fingerprints=word_fingerprints(streams)
                    | {"witnesses": identity_hash(witnesses)},
                    layout=layout_summary(layout, captured) if captured else None,
                )
                if arm in by_arm:
                    first = by_arm[arm]
                    verify_repeats(first, item)
                    first["timings"].append(out["timings"])
                else:
                    by_arm[arm] = item | {"timings": [out["timings"]]}
                    if gold is not None:
                        measured = refined_score(gold, streams.get("packed", ()), layout, witnesses)
                        del measured["annotations"]
                        by_arm[arm]["score"] = measured
        profiled = {}
        with counters_for_baseline() as counters:
            run(
                path,
                data,
                rendered,
                number,
                native,
                provider,
                prep,
                profile,
                "existing_tables",
                ocr,
                probe=False,
            )
            profiled = {
                key: dict(calls=row["calls"], wall_ms=round(row["elapsed_ns"] / 1_000_000, 3))
                for key, row in counters.items()
            }
        results[ocr] = dict(arms=by_arm, baseline_profile=profiled)
        print(f"{path.name}:{number} {ocr}", flush=True)
    return dict(
        pdf=path.name, page=number, source_sha256=harness.sha(data), shared=outer, modes=results
    )


def aggregate(pages):
    totals = {}
    for ocr in pages[0]["modes"]:
        result = {}
        for arm in ARMS:
            runs = [page["modes"][ocr]["arms"][arm] for page in pages]
            walls = [
                mean(sum(t["wall_ms"] for t in s.values()) for s in a["timings"]) for a in runs
            ]
            result[arm] = dict(
                attempted_pages=len(runs),
                failures=sum(r["failure"] is not None for r in runs),
                mean_attempt_wall_ms_sum=round(sum(walls), 2),
                source_json_bytes=sum(
                    r["metadata"].get("packing", {}).get("source_json_bytes", 0) for r in runs
                ),
                encoded_body_bytes=sum(
                    r["metadata"].get("packing", {}).get("encoded_body_bytes", 0) for r in runs
                ),
                prepared_geometry_bytes=sum(
                    r["layout"]["prepared_geometry_bytes"] for r in runs if r["layout"]
                ),
                available=dict(
                    sum((Counter(r["score"]["available"]["status"]) for r in runs), Counter())
                ),
                positioned=sum(r["layout"]["positioned"] for r in runs if r["layout"]),
                explicit_tables=sum(r["layout"]["table_count"] for r in runs if r["layout"]),
                edges=dict(
                    sum((Counter(r["layout"]["edges"]) for r in runs if r["layout"]), Counter())
                ),
            )
        totals[ocr] = result
    return totals


def evaluate(source_dir, provider, repeats):
    prep = preparation_profile(harness.settings_for(provider))
    profile = extraction_profile(harness.settings_for(provider))
    pages = []
    for path, data, fixture_sha, gold in fixture_cases(source_dir):
        page = compare_page(
            path,
            data,
            gold.pdf_page,
            gold,
            provider,
            prep,
            profile,
            repeats,
            ("default_eligibility", "forced_hybrid"),
        )
        page["fixture_sha256"] = fixture_sha
        pages.append(page)
    control = compare_page(
        CONTROL,
        CONTROL.read_bytes(),
        1,
        None,
        provider,
        prep,
        profile,
        repeats,
        ("default_eligibility",),
    )
    return dict(
        version=VERSION,
        runtime=platform.platform(),
        pymupdf=pymupdf.VersionBind,
        ocr_identity=provider.identity.model_dump(mode="json"),
        repeats=repeats,
        pages=pages,
        positive_control=control,
        aggregate=aggregate(pages),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--repeats", type=int, choices=range(1, 4), default=2)
    parser.add_argument("--tesseract", default="/usr/bin/tesseract")
    parser.add_argument("--tessdata", default="/usr/share/tesseract-ocr/5/tessdata")
    args = parser.parse_args()
    results = evaluate(
        args.source_dir, TesseractProvider(args.tesseract, args.tessdata), args.repeats
    )
    args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
