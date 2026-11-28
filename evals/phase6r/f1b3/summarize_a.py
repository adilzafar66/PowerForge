"""Verify the private audit and export only adjudication and bounded attempt metrics."""

import argparse
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from investigation_a import HERE, Reply, digest, revised_gold, score_review
from live_a import estimate, slots

from powerforge_extraction.stage_contracts import equipment_catalog


def page_scope(document, rule, number):
    page = next(page for page in document.pages if page.pdf_page == number)
    excluded = rule.get("additional_exclusions", {})
    overrides = rule.get("tag_overrides", {})
    supplied = {}
    for item in page.occurrences:
        key = f"{number}/{item.id}"
        if key not in excluded:
            supplied[item.id] = (item.registry_type, overrides.get(key, item.tag))
    exclusions = {item.id: item.kind for item in page.exceptions}
    exclusions.update(
        {
            key.partition("/")[2]: kind
            for key, kind in excluded.items()
            if key.partition("/")[0] == str(number)
        }
    )
    return supplied, exclusions


def tag_verdict(anchor, reported, supplied):
    expected = supplied.get(anchor, (None, None))[1]
    if reported is None:
        return "ABSENT_AS_EXPECTED" if expected is None else "MISSING"
    if reported == expected:
        return "EXACT"
    if expected is not None and reported.casefold() == expected.casefold():
        return "CASE_ONLY"
    if any(
        key != anchor and tag is not None and reported.casefold() == tag.casefold()
        for key, (_, tag) in supplied.items()
    ):
        return "WRONG_OWNER"
    return "INVENTED" if expected is None else "INCORRECT"


def evaluate(raw, arm, review, supplied, exclusions, registry):
    adjudicated = review["observations"]
    structured = Reply.model_validate_json(raw).equipment if arm != "A1" else None
    if structured is not None and len(structured) != len(adjudicated):
        raise ValueError("Adjudication row count differs from structured output")
    rows = []
    scored = []
    matched = set()
    for index, row in enumerate(adjudicated):
        anchor = row["anchor"]
        semantic = row["semantic_classification"]
        allowed = (
            {"CORRECT", "INCORRECT", "UNRESOLVED"} if anchor in supplied else {"NOT_APPLICABLE"}
        )
        if semantic not in allowed:
            raise ValueError("Missing or invalid semantic classification verdict")
        item = structured[index] if structured is not None else None
        tag = row["reported_tag"] if item is None else item.tag
        verdict = tag_verdict(anchor, tag, supplied)
        registry_verdict = None
        if arm == "A3":
            registry_verdict = (
                "MISSING"
                if item.type is None
                else "UNSUPPORTED"
                if item.type not in registry
                else "NOT_APPLICABLE"
                if anchor not in supplied
                else "CORRECT"
                if item.type == supplied[anchor][0]
                else "INCORRECT"
            )
        primary = anchor in supplied and anchor not in matched
        if primary:
            matched.add(anchor)
        scored.append((anchor, semantic == "CORRECT", verdict in {"EXACT", "ABSENT_AS_EXPECTED"}))
        rows.append(
            {
                "anchor": anchor,
                "semantic_classification": semantic,
                "tag_verdict": verdict,
                "registry_classification": registry_verdict,
                "primary_supplied_match": primary,
            }
        )
    quality = score_review(scored, supplied.keys(), exclusions)
    quality["claimed_rows"] = len(rows)
    quality["classification_evaluated"] = sum(
        row["primary_supplied_match"] and row["semantic_classification"] != "UNRESOLVED"
        for row in rows
    )
    evaluated = quality["classification_evaluated"]
    quality["classification_accuracy"] = (
        quality["classification_correct"] / evaluated if evaluated else None
    )
    quality["tag_verdict_counts"] = {
        key: sum(row["tag_verdict"] == key for row in rows)
        for key in (
            "EXACT",
            "CASE_ONLY",
            "MISSING",
            "INCORRECT",
            "INVENTED",
            "WRONG_OWNER",
            "ABSENT_AS_EXPECTED",
        )
    }
    quality["tag_case_only"] = sum(
        row["primary_supplied_match"] and row["tag_verdict"] == "CASE_ONLY" for row in rows
    )
    quality["expected_tagged"] = sum(tag is not None for _, tag in supplied.values())
    quality["exact_tagged_matches"] = sum(
        row["primary_supplied_match"] and row["tag_verdict"] == "EXACT" for row in rows
    )
    quality["undetected_tagged_occurrences"] = sum(
        tag is not None and key not in matched for key, (_, tag) in supplied.items()
    )
    result = {"quality": quality, "observation_verdicts": rows}
    if arm == "A3":
        result["registry_key_member_rows"] = sum(item.type in registry for item in structured)
        result["registry_type_correct_supplied"] = sum(
            row["primary_supplied_match"] and row["registry_classification"] == "CORRECT"
            for row in rows
        )
    return result


def summarize(work):
    manifest = json.loads((HERE / "a-preflight.json").read_bytes())
    approved_slots = {slot: (page, arm) for slot, page, arm in slots(manifest)}
    gold, revised, gold_sha = revised_gold()
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
        document = next(doc for doc in gold.development if doc.pdf == page["pdf"])
        observations, exclusions = page_scope(
            document, revised["documents"][document.pdf], page["pdf_page"]
        )
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
            context = review.get("contextual_exclusions", {})
            if context.keys() & (observations.keys() | exclusions.keys()):
                raise ValueError("Adjudication cannot override revised ground truth")
            summary.update(evaluate(raw, arm, review, observations, exclusions | context, registry))
            summary["notes"] = review.get("notes", [])
        else:
            summary["quality"] = None
        summary["expected_supplied"] = len(observations)
        attempts.append(summary)
    return {
        "version": "f1b3-investigation-a-results-v2",
        "gold_sha256": gold_sha,
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
