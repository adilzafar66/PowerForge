"""Measure offline Stage 2 replay with verified original response bytes."""

import argparse
import json
from collections import Counter
from hashlib import sha256
from uuid import UUID

from powerforge_extraction.assertion_consistency import redundant_assertions
from powerforge_extraction.attribute_admission import admit_attributes
from powerforge_extraction.compact_output import OUTPUT_VERSION, compact_assertion
from powerforge_extraction.publication import build_publication, publication_diagnostics
from powerforge_extraction.server_owned_output import SERVER_OWNED_OUTPUT_VERSION


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def property_bytes(key, value):
    return len(encoded(key)) + 1 + len(encoded(value))


def measure_original(payload):
    counts = Counter()
    observations = Counter()
    quotes = Counter()
    for collection in ("attributes", "raw_unmapped"):
        items = payload[collection]
        counts[f"{collection}_items"] = len(items)
        counts[f"{collection}_bytes"] = len(encoded(items))
        for item in items:
            if not isinstance(item, dict):
                continue
            observations[
                (
                    collection,
                    encoded(
                        {key: value for key, value in sorted(item.items()) if key != "local_ref"}
                    ),
                )
            ] += 1
            for key, value in item.items():
                if value is None or value == []:
                    counts["null_empty_member_bytes"] += property_bytes(key, value)
                if key == "local_ref":
                    counts["id_member_bytes"] += property_bytes(key, value)
                if key in {
                    "raw_value",
                    "raw_unit",
                    "proposed_value",
                    "proposed_unit",
                    "alternate_representations",
                }:
                    counts["value_unit_member_bytes"] += property_bytes(key, value)
                if key == "evidence" and isinstance(value, list):
                    counts["evidence_member_bytes"] += property_bytes(key, value)
                    counts["evidence_citations"] += len(value)
                    for citation in value:
                        if isinstance(citation, dict):
                            for field in ("quote", "reported_text"):
                                if isinstance(citation.get(field), str):
                                    quotes[citation[field]] += 1

    def key_bytes(value):
        if isinstance(value, dict):
            return sum(len(encoded(key)) + 1 + key_bytes(child) for key, child in value.items())
        if isinstance(value, list):
            return sum(map(key_bytes, value))
        return 0

    counts["key_bytes"] = key_bytes(payload)
    counts["exact_duplicate_observations"] = sum(n - 1 for n in observations.values())
    counts["repeated_quotations"] = sum(n - 1 for n in quotes.values())
    counts["repeated_quote_value_bytes"] = sum((n - 1) * len(encoded(q)) for q, n in quotes.items())
    return dict(counts)


def replay(wire, source, original, output_version=OUTPUT_VERSION):
    if wire.output_version != "legacy-v7":
        raise ValueError("Comparison requires a legacy Stage 2 attempt")
    legacy = admit_attributes(wire, original)
    if legacy.fatal and not all(
        issue.error_type == "duplicate_reference"
        or (issue.error_type == "too_long" and issue.path == ("raw_unmapped",))
        for issue in legacy.fatal
    ):
        raise ValueError("Legacy envelope cannot be transformed")
    payload = json.loads(original)

    def transform(item):
        if output_version == OUTPUT_VERSION:
            return compact_assertion(item)
        if isinstance(item, dict):
            return {key: value for key, value in item.items() if key != "local_ref"}
        return item

    projected = {
        collection: [transform(item) for item in payload[collection]]
        for collection in ("attributes", "raw_unmapped")
    }
    candidate_bytes = encoded(projected)
    candidate_wire = wire.model_copy(update={"output_version": output_version})
    candidate = admit_attributes(candidate_wire, candidate_bytes)
    prefix = "compact" if output_version == OUTPUT_VERSION else "reliability"
    semantic_match = None
    if legacy.result is not None and candidate.result is not None:
        for collection in ("attributes", "raw_unmapped"):
            if len(getattr(legacy.result, collection)) != len(
                getattr(candidate.result, collection)
            ):
                semantic_match = False
                break
        else:
            # Rewrite references only for comparison. Keep the original and
            # compact results intact for replay and audit.
            comparable = legacy.result.model_copy(
                update={
                    collection: tuple(
                        item.model_copy(update={"local_ref": expanded.local_ref})
                        for item, expanded in zip(
                            getattr(legacy.result, collection),
                            getattr(candidate.result, collection),
                            strict=True,
                        )
                    )
                    for collection in ("attributes", "raw_unmapped")
                }
            )
            before = build_publication(wire, comparable, source)
            after = build_publication(candidate_wire, candidate.result, source)
            semantic_match = (
                comparable == candidate.result
                and before == after
                and publication_diagnostics(
                    before, redundant_assertions(comparable.model_dump(mode="json"))
                )
                == publication_diagnostics(
                    after, redundant_assertions(candidate.result.model_dump(mode="json"))
                )
            )
    return {
        "original_bytes": len(original),
        "minified_legacy_bytes": len(encoded(payload)),
        f"{prefix}_bytes": len(candidate_bytes),
        "structure": measure_original(payload),
        "legacy_fatal": [issue.error_type for issue in legacy.fatal],
        "legacy_accepted": legacy.accepted,
        "legacy_likely_redundant": (
            len(redundant_assertions(legacy.result.model_dump(mode="json")))
            if legacy.result is not None
            else None
        ),
        f"{prefix}_fatal": [issue.error_type for issue in candidate.fatal],
        f"{prefix}_accepted_attributes": len(candidate.result.attributes)
        if candidate.result
        else 0,
        f"{prefix}_accepted_raw": len(candidate.result.raw_unmapped) if candidate.result else 0,
        f"{prefix}_quarantined": len(candidate.rejected),
        f"{prefix}_overflowed": len(candidate.overflow_indices),
        "semantic_and_publication_match": semantic_match,
    }


def main():
    from attribute_performance_baseline import reconstruct_attempt

    from extraction_worker.read_response_audit import read_operator_audit
    from powerforge_api.db import get_session_factory
    from powerforge_document_processing.storage.factory import build_s3_storage
    from powerforge_extraction.provider_body import dispatch_hash
    from powerforge_extraction.response_audit import ResponseAudit
    from powerforge_shared.config import get_settings

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("attempts", nargs="+", type=UUID)
    parser.add_argument(
        "--output-version",
        choices=(OUTPUT_VERSION, SERVER_OWNED_OUTPUT_VERSION),
        default=OUTPUT_VERSION,
    )
    args = parser.parse_args()
    settings = get_settings()
    factory = get_session_factory()
    storage = build_s3_storage(settings)
    for attempt in args.attempts:
        wire, request, source, _ = reconstruct_attempt(factory, storage, settings, attempt, False)
        with factory() as session:
            audit = session.get(ResponseAudit, attempt)
            if audit is None or audit.request_hash != dispatch_hash(request):
                raise ValueError("Audit unavailable for reconstructed dispatch")
            digest = audit.output_sha256
        original = read_operator_audit(settings, attempt)
        if sha256(original).hexdigest() != digest:
            raise ValueError("Operator export differs from pinned attempt audit")
        print(
            json.dumps(
                {"attempt": str(attempt), **replay(wire, source, original, args.output_version)}
            )
        )


if __name__ == "__main__":
    main()
