"""Export baseline metrics after verifying private response digests."""

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path
from statistics import median

from occurrence_eval import digest


def summarize(rows):
    admitted = [r for r in rows if "score" in r]
    matched = sum(r["score"]["matched"] for r in admitted)
    gold = sum(r["expected_occurrences"] for r in rows)
    observed = sum(r["score"]["observed"] - r["score"]["pending_adjudication"] for r in admitted)
    usage = {
        key: sum(r["usage"].get(key) or 0 for r in admitted)
        for key in ("input_tokens", "cached_input_tokens", "output_tokens")
    }
    latency = [r["provider_seconds"] for r in admitted]
    fields = defaultdict(Counter)
    for row in admitted:
        for grades in row["score"]["field_accuracy_by_occurrence"].values():
            for field, grade in grades.items():
                fields[field][
                    "disputed" if grade is None else "correct" if grade else "incorrect"
                ] += 1
    return {
        "attempted": len(rows),
        "admitted": len(admitted),
        "expected_in_all_attempts": gold,
        "expected_in_admitted_attempts": sum(r["expected_occurrences"] for r in admitted),
        "observed": sum(r["score"]["observed"] for r in admitted),
        "matched": matched,
        "precision_over_resolved_claims": matched / observed if observed else None,
        "recall_over_attempted_pages": matched / gold if gold else None,
        "f1": 2 * matched / (gold + observed) if gold + observed else None,
        "field_grades": {key: dict(counts) for key, counts in fields.items()},
        "admitted_usage": usage,
        "estimated_standard_token_spend_usd": round(
            (
                (usage["input_tokens"] - usage["cached_input_tokens"]) * 0.1
                + usage["cached_input_tokens"] * 0.01
                + usage["output_tokens"] * 0.5
            )
            / 1_000_000,
            6,
        ),
        "median_admitted_latency_seconds": median(latency) if latency else None,
    }


def export(work):
    private = json.loads((work / "baseline.json").read_text())
    with closing(sqlite3.connect(work / "dispatches.sqlite3")) as connection:
        reservations = dict(
            connection.execute("SELECT slot,reserved FROM dispatches WHERE slot LIKE 'baseline/%'")
        )
    if {row["slot"] for row in private} != reservations.keys():
        raise ValueError("baseline report and dispatch ledger do not have identical attempts")
    rows = []
    for entry in private:
        if "audit" in entry:
            raw = (work / (entry["work_unit"] + ".response")).read_bytes()
            audit = entry["audit"]
            if len(raw) != audit["size"] or digest(raw) != audit["sha256"]:
                raise ValueError("restricted response digest or size mismatch")
        keep = {key: value for key, value in entry.items() if key not in ("work_unit", "score")}
        keep["reserved_usd"] = reservations[entry["slot"]] / 100_000_000
        if "score" in entry:
            keep["score"] = entry["score"].copy()
            # The model's reference strings may include source content.
            keep["score"]["observations"] = {
                f"observation-{index}": outcome
                for index, outcome in enumerate(entry["score"]["observations"].values(), start=1)
            }
        rows.append(keep)
    groups = defaultdict(list)
    complete_pairs = defaultdict(list)
    for row in rows:
        groups[(row["split"], row["arm"])].append(row)
        complete_pairs[(row["split"], row["pdf"], row["page"], row["repeat"])].append(row)
    paired = [
        row
        for pair in complete_pairs.values()
        if len(pair) == 2 and all(r["state"] == "ADMITTED" for r in pair)
        for row in pair
    ]
    return dict(
        version="f1b-baseline-v1",
        total_reserved_usd=sum(reservations.values()) / 100_000_000,
        summaries={f"{split}/{arm}": summarize(items) for (split, arm), items in groups.items()},
        complete_development_pairs={
            arm: summarize([r for r in paired if r["split"] == "development" and r["arm"] == arm])
            for arm in ("existing_tables", "positioned_only")
        },
        attempts=rows,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_work", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(export(args.private_work), indent=2) + "\n")


if __name__ == "__main__":
    main()
