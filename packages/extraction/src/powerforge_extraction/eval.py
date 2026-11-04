"""Repeatable offline replay by default; live work is an explicit bounded worker entrypoint."""

import argparse
import json
import sys
from pathlib import Path

from powerforge_extraction.evaluation import load_corpus, read_json, replay, resource_identity
from powerforge_extraction.evaluation_scoring import report, score_case
from powerforge_extraction.identities import identity_hash


def evaluate(corpus_path: Path, recordings_path: Path, selected: list[str] | None = None) -> dict:
    corpus, digest = load_corpus(corpus_path)
    recordings = read_json(recordings_path)
    if (
        recordings.get("version") != "engineering-recordings-v1"
        or recordings.get("corpus_sha256") != digest
        or recordings.get("resources") != resource_identity()
    ):
        raise ValueError("Recording/source/resource identity mismatch; no current-version fallback")
    ids = {case.id for case in corpus.cases}
    if set(recordings["cases"]) - ids or (
        selected is not None and (len(set(selected)) != len(selected) or set(selected) - ids)
    ):
        raise ValueError("Unknown or duplicate evaluation cases")
    cases = [case for case in corpus.cases if selected is None or case.id in selected]
    results = []
    for case in cases:
        if case.id not in recordings["cases"]:
            raise ValueError("Missing recorded case; refusing silent dataset shrinkage")
        recorded = recordings["cases"][case.id]
        if set(recorded) != {"equipment", "attributes"}:
            raise ValueError("Each recording must declare both planned stage payloads")
        sources, outputs, failures = replay(case, corpus_path.parent, recorded)
        scored = score_case(case, sources, outputs)
        scored["stage_failures"] = failures
        arrays = [
            recorded[stage].get(collection) if isinstance(recorded[stage], dict) else None
            for stage, collection in (("equipment", "equipment"), ("attributes", "attributes"))
        ]
        scored["recorded_observations"] = (
            sum(len(items) for items in arrays)
            if all(isinstance(items, list) for items in arrays)
            else None
        )
        results.append(scored)
    # A local file's claim of a live origin is not proof of provider execution.
    provenance = (
        "SCRIPTED_MOCK"
        if recordings.get("provenance") == "SCRIPTED_MOCK"
        else "UNVERIFIED_RECORDING"
    )
    result = report(
        results, provenance=provenance, corpus_digest=digest, resources=resource_identity()
    )
    result["recordings_sha256"] = identity_hash(recordings)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Evaluate engineering extraction without arbitrary accuracy thresholds"
    )
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--recordings", type=Path)
    parser.add_argument("--case", action="append", dest="cases")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--approved-corpus", help="Exact corpus digest explicitly approved for external processing"
    )
    parser.add_argument(
        "--bindings", type=Path, help="Case IDs to preprocessed immutable Document UUIDs"
    )
    parser.add_argument("--max-calls", type=int, default=0)
    parser.add_argument("--wait-seconds", type=int, default=300)
    args = parser.parse_args(argv)
    try:
        if args.live:
            corpus, digest = load_corpus(args.corpus)
            ids = set(args.cases) if args.cases else {case.id for case in corpus.cases}
            if (
                not ids
                or ids - {case.id for case in corpus.cases}
                or (args.cases and len(ids) != len(args.cases))
            ):
                raise ValueError("Unknown or duplicate live cases")
            if (
                args.recordings
                or args.approved_corpus != digest
                or args.bindings is None
                or args.max_calls < 2 * len(ids)
                or not 1 <= args.wait_seconds <= 3600
            ):
                raise ValueError(
                    "Live execution requires an approved digest, exact bindings, "
                    "and two calls per selected case"
                )
            # No SDK, credentials, DB or provider is accessed before explicit opt-in checks.
            from extraction_worker.evaluation_live import evaluate_live

            result = evaluate_live(
                args.corpus,
                args.bindings,
                approved_digest=digest,
                selected=ids,
                max_calls=args.max_calls,
                wait_seconds=args.wait_seconds,
            )
        else:
            if args.bindings or args.approved_corpus or args.max_calls:
                raise ValueError("Live-only arguments require --live")
            result = evaluate(
                args.corpus, args.recordings or args.corpus.parent / "scripted.json", args.cases
            )
    except Exception as exc:
        # Do not render DB/provider exception contexts containing source data or credentials.
        raise SystemExit(
            f"Evaluation failed ({type(exc).__name__}); "
            "check corpus identities, live controls and configured services"
        ) from None
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)


if __name__ == "__main__":
    main()
