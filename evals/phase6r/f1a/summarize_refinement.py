"""Aggregate measured F1-A2 pages by document and recipe without dropping failures."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean


def count_fields(rows):
    counts = Counter()
    for row in rows:
        counts.update(row)
    return dict(counts)


def sum_recipe(records):
    stages = [arm["stages"]["packed"] for arm in records]
    packing = [arm["metadata"]["packing"] for arm in records if "packing" in arm["metadata"]]
    metadata = [arm["metadata"] for arm in records]
    return {
        "pages_evaluated": len(records),
        "failures": sum(arm["failure"] is not None for arm in records),
        "views": {
            view: {
                "status": count_fields(stage[view]["status"] for stage in stages),
                "totals": count_fields(stage[view]["totals"] for stage in stages),
                "geometry": {
                    key: sum(stage[view]["geometry"][key] for stage in stages)
                    for key in ("matches", "containment_sum", "iou_sum")
                },
            }
            for view in ("preferred", "available", "unambiguous")
        },
        "explicit_structure": count_fields(stage["explicit_structure"] for stage in stages),
        "geometric_associations": {
            kind: count_fields(stage["geometric_associations"].get(kind, {}) for stage in stages)
            for kind in ("row", "column", "header", "label_value")
        },
        "construction_changes": count_fields(
            {reason: len(items) for reason, items in arm["construction_changes"].items()}
            for arm in records
        ),
        "absent_token_witnesses": sum(
            m.get("representation_tokens_absent_from_readings", 0) for m in metadata
        ),
        "overlap_pairs": count_fields(m.get("overlap_pairs", {}) for m in metadata),
        "reading_issues": count_fields(m.get("reading_issues", {}) for m in metadata),
        "ocr_words": sum(m.get("confidence", {}).get("words", 0) for m in metadata),
        "ocr_words_below_50": sum(m.get("confidence", {}).get("below_50", 0) for m in metadata),
        "identical_reading_pairs": sum(
            m.get("same_location_identical_reading_pairs", 0) for m in metadata
        ),
        "engine_invocations_per_repeat": sum(
            m.get("ocr", {}).get("engine_invocations", m.get("ocr", {}).get("ocr_invocations", 0))
            for m in metadata
        ),
        "mean_attempt_wall_ms_sum_across_pages": sum(
            mean(sum(timer["wall_ms"] for timer in attempt.values()) for attempt in arm["timings"])
            for arm in records
        ),
        "packed_pages_measured": len(packing),
        "packed_source_bytes": sum(fields["source_json_bytes"] for fields in packing),
        "encoded_body_bytes": sum(fields["encoded_body_bytes"] for fields in packing),
    }


def summarize(result):
    combined = defaultdict(list)
    documents = defaultdict(lambda: defaultdict(list))
    for page in result["pages"]:
        for name, arm in page["arms"].items():
            documents[page["pdf"]][name].append(arm)
            combined[name].append(arm)
    return dict(
        version=result["version"],
        repeats=result["repeats"],
        promoted=result["promoted"],
        recipes={name: sum_recipe(records) for name, records in combined.items()},
        documents={
            name: {arm: sum_recipe(records) for arm, records in variants.items()}
            for name, variants in documents.items()
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    summary = summarize(json.loads(args.results.read_text()))
    args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
