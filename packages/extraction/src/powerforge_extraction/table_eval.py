"""Separate versioned, offline-only table replay CLI. No infrastructure imports or calls."""

import argparse
import json
import sys
from pathlib import Path

from powerforge_extraction.evaluation import read_json
from powerforge_extraction.identities import identity_hash
from powerforge_extraction.table_evaluation import load_table_corpus, replay, resources
from powerforge_extraction.table_evaluation_scoring import report, score_case


def evaluate(corpus_path: Path, recordings_path: Path, selected: list[str] | None = None):
    corpus, digest = load_table_corpus(corpus_path)
    recordings = read_json(recordings_path)
    if (
        recordings.get("version") != "table-recordings-v1"
        or recordings.get("corpus_sha256") != digest
        or recordings.get("resources") != resources()
    ):
        raise ValueError("Recording/source/resource identity mismatch; no version fallback")
    ids = {c.id for c in corpus.cases}
    payloads = recordings.get("cases")
    if (
        not isinstance(payloads, dict)
        or set(payloads) - ids
        or selected is not None
        and (not selected or len(set(selected)) != len(selected) or set(selected) - ids)
    ):
        raise ValueError("Unknown, empty or duplicate evaluation selection")
    results = []
    for case in corpus.cases:
        if selected is not None and case.id not in selected:
            continue
        if case.id not in payloads:
            raise ValueError("Missing recorded case; refusing dataset shrinkage")
        recorded = payloads[case.id]
        if not isinstance(recorded, dict) or set(recorded) != {"reconstruction", "interpretation"}:
            raise ValueError("Both planned stage payloads must be declared (null means failure)")
        sources, outputs, failures = replay(case, corpus_path.parent, recorded)
        results.append(score_case(case, sources, outputs, failures))
    result = report(
        results,
        provenance=(
            "SCRIPTED_MOCK"
            if recordings.get("provenance") == "SCRIPTED_MOCK"
            else "UNVERIFIED_RECORDING"
        ),
        corpus_digest=digest,
        resources=resources(),
    )
    result["recordings_sha256"] = identity_hash(recordings)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline table extraction evaluation v1")
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--recordings", type=Path)
    parser.add_argument("--case", action="append", dest="cases")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = evaluate(
            args.corpus, args.recordings or args.corpus.parent / "scripted.json", args.cases
        )
    except Exception as exc:
        raise SystemExit(
            f"Table evaluation failed ({type(exc).__name__}); check corpus identities"
        ) from None
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)


if __name__ == "__main__":
    main()
