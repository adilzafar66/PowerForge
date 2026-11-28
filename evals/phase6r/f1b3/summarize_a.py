"""Verify the private audit and export only adjudication and bounded attempt metrics."""

import argparse
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from investigation_a import HERE, Reply, digest, score_review
from live_a import estimate, slots
from occurrence_eval import read_gold

from powerforge_extraction.stage_contracts import equipment_catalog


def summarize(work):
    manifest = json.loads((HERE / "a-preflight.json").read_bytes())
    approved_slots = {slot: (page, arm) for slot, page, arm in slots(manifest)}
    gold = read_gold()
    adjudication = json.loads((HERE / "a-adjudication.json").read_bytes())["slots"]
    registry = {item.key for item in equipment_catalog()}
    attempts = []
    with closing(
        sqlite3.connect(f"{(work / 'dispatches.sqlite3').as_uri()}?mode=ro", uri=True)
    ) as db:
        rows = db.execute(
            "SELECT slot, work_unit, digest, reserved, result FROM dispatches ORDER BY rowid"
        ).fetchall()
    if {row[0] for row in rows} != approved_slots.keys():
        raise ValueError("Ledger does not contain every approved trial")
    for slot, unit, request_sha, reserved, result_json in rows:
        page, arm = approved_slots[slot]
        if request_sha != page["requests"][arm]["body_sha256"]:
            raise ValueError("Audit request digest does not match the approved slot")
        result = json.loads(result_json) if result_json else {"state": "UNKNOWN_PROVIDER_OUTCOME"}
        scope = next(doc.pages[0] for doc in gold.development if doc.pdf == page["pdf"])
        observations = {item.id: item for item in scope.occurrences}
        exclusions = {item.id: item.kind for item in scope.exceptions}
        if page["pdf"] == "schneider-panel-drawing.pdf":
            exclusions["breaker-9/accessory"] = "COMPONENT_OR_CONTEXT"
        summary = result | {
            "slot": slot,
            "work_unit": unit,
            "request_sha256": request_sha,
            "body_bytes": page["requests"][arm]["body_bytes"],
            "reserved_usd": f"{reserved / 100_000_000:.8f}",
            "usage_based_usd": estimate(result.get("usage")),
        }
        if result["state"] == "ADMITTED":
            receipt = result["audit"]
            if datetime.now(UTC) >= datetime.fromisoformat(receipt["expires_at"]):
                raise ValueError("Provider output retention period expired")
            raw = (work / f"{unit}.response").read_bytes()
            if (digest(raw), len(raw)) != (receipt["sha256"], receipt["size"]):
                raise ValueError("Original provider output fails its audit receipt")
            review = adjudication[slot]
            if review["output_sha256"] != receipt["sha256"]:
                raise ValueError("Adjudication is bound to a different original response")
            anchors = review["anchors"]
            case_only = set(review.get("case_only_tags", []))
            if arm != "A1":
                structured = Reply.model_validate_json(raw).equipment
                if len(structured) != len(anchors):
                    raise ValueError("Adjudication row count differs from structured output")
                for key, item in zip(anchors, structured, strict=True):
                    if key in observations:
                        expected = observations[key].tag
                        if key in case_only:
                            if not (
                                item.tag
                                and expected
                                and item.tag != expected
                                and item.tag.casefold() == expected.casefold()
                            ):
                                raise ValueError("Tag case adjudication disagrees with output")
                        elif item.tag != expected:
                            raise ValueError("Exact tag adjudication disagrees with output")
                if arm == "A3":
                    summary["registry_key_member_rows"] = sum(
                        x.type in registry for x in structured
                    )
                    summary["registry_type_correct_supplied"] = sum(
                        key in observations and item.type == observations[key].registry_type
                        for key, item in zip(anchors, structured, strict=True)
                    )
            summary["quality"] = score_review(
                [(key, True, key not in case_only) for key in anchors],
                observations.keys(),
                exclusions,
            )
            summary["quality"].update(
                claimed_rows=len(anchors),
                tag_case_only=len(case_only),
                expected_tagged=sum(bool(x.tag) for x in observations.values()),
                exact_tagged_matches=sum(bool(x.tag) for x in observations.values())
                - len(case_only),
            )
            summary["notes"] = review.get("notes", [])
        else:
            summary["quality"] = None
        summary["expected_supplied"] = len(observations)
        attempts.append(summary)
    return {
        "version": "f1b3-investigation-a-results-v1",
        "adjudication_sha256": digest((HERE / "a-adjudication.json").read_bytes()),
        "pricing": "openai-gpt-6-luna-standard-2026-11-28",
        "attempts": attempts,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = summarize(args.audit_directory.resolve())
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
