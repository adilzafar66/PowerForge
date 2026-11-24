"""Offline-only comparison with the original visual witness and the pinned text."""

from decimal import Decimal, localcontext
from itertools import pairwise

from powerforge_extraction.evidence_localization import MAX_QUOTE_SCOPE_BYTES, EvidenceLocalizer
from powerforge_extraction.readable_context import readable_page, reading_blocks

POLICY = "region-literal-replay-v1"
MAX_REGION_AREA = Decimal("0.25")


def _bounds(box):
    x, y, w, h = (Decimal(box[k]) for k in ("x", "y", "width", "height"))
    with localcontext() as context:
        context.prec = max(100, *(len(value.as_tuple().digits) + 4 for value in (x, y, w, h)))
        return x, y, x + w, y + h


class RegionalReplay(EvidenceLocalizer):
    def __init__(self, source, page, equipment=()):
        super().__init__(source)
        self.equipment_regions = []
        for item in equipment:
            boxes = []
            for fragment in self.locate(item.evidence, "EQUIPMENT"):
                regions = fragment.get("regions") or (
                    [fragment["region"]] if fragment.get("region") else []
                )
                boxes.extend(_bounds(box) for box in regions)
            if boxes:
                self.equipment_regions.append(boxes)
        self.ambiguous = {
            self.token_refs.get((side.representation_ref, side.ref))
            for edge in source.layout.overlaps
            if edge.kind != "AGREEMENT"
            for side in (edge.left, edge.right)
        }
        self.successor = {
            a[0]: b[0]
            for block in reading_blocks(readable_page(page))
            for line in block["lines"]
            for a, b in pairwise(line)
        }

    def compare(self, citation):
        original = self._locate(citation)
        outcome = dict(policy=POLICY, original=original)
        if original["localization"] != "VISUAL_REPORTED" or not citation.reported_text:
            return outcome | {"outcome": "NO_LITERAL_REGION"}
        if self.scope > min(self.remaining, MAX_QUOTE_SCOPE_BYTES):
            return outcome | {"outcome": "SEARCH_LIMIT"}
        self.remaining -= self.scope
        target = _bounds(original["region"])
        left, top, right, bottom = target
        if (
            sum(
                any(x < right and y < bottom and x2 > left and y2 > top for x, y, x2, y2 in boxes)
                for boxes in self.equipment_regions
            )
            > 1
        ):
            return outcome | {"outcome": "OVERLAPPING_EQUIPMENT"}
        literal = citation.reported_text
        found = {}
        hits = 0
        for alias, text in self.text.items():
            pos = text.find(literal)
            while pos >= 0:
                hits += 1
                if hits > 64:
                    return outcome | {"outcome": "SEARCH_LIMIT"}
                end = pos + len(literal)
                tokens = self._span_tokens(alias, pos, end)
                if not tokens:
                    return outcome | {"outcome": "INSUFFICIENT_SUPPORT"}
                # Substrings of larger tokens do not establish a complete expression.
                if tokens[0].span.start == pos and tokens[-1].span.end == end:
                    boxes = [self._token_region(alias, t) for t in tokens]
                    if not all(boxes):
                        return outcome | {"outcome": "INSUFFICIENT_GEOMETRY"}
                    bounds = [_bounds(b) for b in boxes]
                    if any(
                        x < right and y < bottom and x2 > left and y2 > top
                        for x, y, x2, y2 in bounds
                    ):
                        refs = tuple(self.token_refs.get((alias, token.ref)) for token in tokens)
                        if (
                            not all(
                                left <= x < x2 <= right and top <= y < y2 <= bottom
                                for x, y, x2, y2 in bounds
                            )
                            or any(
                                text[a.span.end : c.span.start].strip() for a, c in pairwise(tokens)
                            )
                            or any(
                                ref is None or ref in self.ambiguous or self.readings[ref].issues
                                for ref in refs
                            )
                            or any(self.successor.get(a) != c for a, c in pairwise(refs))
                        ):
                            return outcome | {"outcome": "INSUFFICIENT_SUPPORT"}
                        found.setdefault(refs, (alias, pos, end))
                        if len(found) > 1:
                            return outcome | {"outcome": "AMBIGUOUS"}
                pos = text.find(literal, pos + 1)
        if not found:
            return outcome | {"outcome": "NO_MATCH"}
        # A page-wide hint plus one literal occurrence is only a page-text match.
        region = original["region"]
        if Decimal(region["width"]) * Decimal(region["height"]) > MAX_REGION_AREA:
            return outcome | {"outcome": "INSUFFICIENT_REGIONAL_SUPPORT"}
        refs, location = next(iter(found.items()))
        return outcome | {
            "outcome": "MATCH",
            "reading_refs": refs,
            "derived": self._resolved(citation.role, *location),
        }


def replay_original(wire, source, original):
    """Compare protected, admitted citations. Return only content-free metrics."""
    from collections import Counter

    from powerforge_extraction.attribute_admission import admit_attributes
    from powerforge_extraction.stage_contracts import InferredAssertion, VisualCitation

    admitted = admit_attributes(wire, original)
    if admitted.result is None:
        return {"fatal": 1}
    counts = Counter()
    baseline = EvidenceLocalizer(source, wire.input_version, wire.page)
    candidate = RegionalReplay(source, wire.page, wire.upstream.equipment)
    for item in (*admitted.result.attributes, *admitted.result.raw_unmapped):
        for citation in item.evidence:
            if not isinstance(citation, VisualCitation):
                continue
            if isinstance(item, InferredAssertion) and citation.role == "VALUE":
                counts["INELIGIBLE"] += 1
                continue
            if baseline._locate(citation)["localization"] != "VISUAL_REPORTED":
                counts["INELIGIBLE"] += 1
                continue
            result = candidate.compare(citation)
            counts[result["outcome"]] += 1
    return dict(counts)


def main():
    import argparse
    import json
    from hashlib import sha256
    from uuid import UUID

    from attribute_performance_baseline import reconstruct_attempt

    from extraction_worker.read_response_audit import read_operator_audit
    from powerforge_api.db import get_session_factory
    from powerforge_document_processing.storage.factory import build_s3_storage
    from powerforge_extraction.provider_body import dispatch_hash
    from powerforge_extraction.response_audit import ResponseAudit
    from powerforge_shared.config import get_settings

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("attempts", nargs="+", type=UUID)
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
                {
                    "attempt": str(attempt),
                    "policy": POLICY,
                    "counts": replay_original(wire, source, original),
                }
            )
        )


if __name__ == "__main__":
    main()
