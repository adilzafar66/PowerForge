"""Localize model citations against the verified, immutable page representations."""

import re
from bisect import bisect_right
from decimal import localcontext

from pydantic import ValidationError

from powerforge_extraction.phase6r_contracts import QuoteCitation, ReadingCitation
from powerforge_provenance.locations import Region
from powerforge_provenance.spatial_geometry import region_for_points

MAX_QUOTE_SCOPE_BYTES = 2 * 1024 * 1024
MAX_QUOTE_SEARCH_BYTES = 64 * 1024 * 1024
MAX_FRAGMENT_REGIONS = 32


def unresolved(role, code):
    return {"role": role, "localization": "UNRESOLVED", "reason_code": code}


def _matches(text, quote):
    """Return at most two intervals, preserving original Unicode offsets."""
    start = text.find(quote)
    if start == -1:
        return ()
    first = (start, start + len(quote))
    second = text.find(quote, start + 1)
    return (first,) if second == -1 else (first, (second, second + len(quote)))


def _reading_matches(text, quote):
    # Compare whitespace runs while retaining their original offsets.
    matches = _matches(text, quote)
    normalized_quote = " ".join(quote.split())
    if not normalized_quote:
        return matches
    words = list(re.finditer(r"\S+", text))
    normalized = " ".join(word[0] for word in words)
    offsets = [pos for word in words for pos in (*range(word.start(), word.end()), word.end())]
    tolerant = tuple(
        (offsets[start], offsets[end - 1] + 1)
        for start, end in _matches(normalized, normalized_quote)
    )
    # A whitespace-tolerant match of an exact quote may describe the same span.
    if quote == quote.strip():
        return tuple(dict.fromkeys((*matches, *tolerant)))[:2]
    return matches


class EvidenceLocalizer:
    def __init__(self, source):
        self.bodies = source.bodies
        self.readings = {reading.ref: reading for reading in source.layout.readings}
        self.tokens = {
            alias: {token.ref: token for token in body.tokens}
            for alias, body in self.bodies.items()
        }
        self.ordered = {
            alias: sorted(tokens.values(), key=lambda token: token.span.start)
            for alias, tokens in self.tokens.items()
        }
        self.ends = {
            alias: [token.span.end for token in tokens] for alias, tokens in self.ordered.items()
        }
        self.text = {alias: value.decode("utf-8") for alias, value in source.text.items()}
        self.scope = sum(len(value) for value in source.text.values())
        self.remaining = MAX_QUOTE_SEARCH_BYTES
        self.quote_cache = {}
        self.token_regions = {}

    def locate(self, citations, default_role):
        if not citations:
            return [unresolved(default_role, "NO_CITATION")]
        return [self._locate(citation) for citation in citations]

    def _locate(self, citation):
        if isinstance(citation, ReadingCitation):
            return self._reading(citation)
        if isinstance(citation, QuoteCitation):
            if citation.quote not in self.quote_cache:
                self.quote_cache[citation.quote] = self._quote(citation.quote)
            location = self.quote_cache[citation.quote]
            return (
                unresolved(citation.role, location)
                if isinstance(location, str)
                else self._resolved(citation.role, *location)
            )
        try:
            # Coordinates retain the exact-decimal values admitted by the wire parser.
            with localcontext() as context:
                context.prec = 50
                region = Region(**citation.region.model_dump())
        except ValidationError:
            return unresolved(citation.role, "INVALID_VISUAL_REGION")
        return {
            "role": citation.role,
            "localization": "VISUAL_REPORTED",
            "reported_text": citation.reported_text,
            "region": region.model_dump(mode="json"),
        }

    def _reading(self, citation):
        role = citation.role
        reading = self.readings.get(citation.reading_ref)
        if reading is None:
            return unresolved(role, "UNKNOWN_READING")
        if citation.quote is None:
            alias = reading.preferred.representation_ref
            token = self.tokens[alias][reading.preferred.ref]
            return self._resolved(role, alias, token.span.start, token.span.end, reading.issues)
        matches = []
        for member in (reading.preferred, *(m for m in reading.members if m != reading.preferred)):
            alias = member.representation_ref
            token = self.tokens[alias][member.ref]
            intervals = _reading_matches(token.raw_text, citation.quote)
            if len(intervals) > 1:
                return unresolved(role, "AMBIGUOUS_QUOTE")
            if intervals:
                start, end = intervals[0]
                matches.append((alias, token.span.start + start, token.span.start + end, token))
        if not matches:
            return unresolved(role, "QUOTE_MISMATCH")
        alias, start, end, token = matches[0]
        if len(matches) > 1 and (
            "AMBIGUOUS_OVERLAP" in reading.issues
            or any(
                other.raw_text != token.raw_text
                or (start - token.span.start, end - token.span.start)
                != (left - other.span.start, right - other.span.start)
                for _, left, right, other in matches[1:]
            )
        ):
            return unresolved(role, "AMBIGUOUS_QUOTE")
        return self._resolved(role, alias, start, end, reading.issues)

    def _quote(self, quote):
        if self.scope > MAX_QUOTE_SCOPE_BYTES or self.scope > self.remaining:
            return "QUOTE_SEARCH_LIMIT"
        self.remaining -= self.scope
        found = None
        artifacts = set()
        for alias, text in self.text.items():
            artifact = self.bodies[alias].text_artifact.id
            if artifact in artifacts:
                continue
            artifacts.add(artifact)
            matches = _matches(text, quote)
            if len(matches) > 1 or (matches and found):
                return "AMBIGUOUS_QUOTE"
            if matches:
                found = (alias, *matches[0])
        return found if found else "QUOTE_MISMATCH"

    def _token_region(self, alias, token):
        key = (alias, token.ref)
        if key not in self.token_regions:
            transform = self.bodies[alias].transform
            if token.source_quad is not None:
                region = region_for_points(tuple(transform.map_point(p) for p in token.source_quad))
            else:
                region = transform.map_rectangle(token.source_box) if token.source_box else None
            self.token_regions[key] = region and region.model_dump(mode="json")
        return self.token_regions[key]

    def _resolved(self, role, alias, start, end, issues=()):
        body = self.bodies[alias]
        regions = []
        first = bisect_right(self.ends[alias], start)
        tokens = self.ordered[alias]
        for index in range(first, len(tokens)):
            token = tokens[index]
            if token.span.start >= end:
                break
            # Token-level geometry cannot precisely highlight a substring of that token.
            if start <= token.span.start and token.span.end <= end:
                region = self._token_region(alias, token)
                if region is not None:
                    regions.append(region)
                    if len(regions) > MAX_FRAGMENT_REGIONS:
                        regions = []
                        issues = (*issues, "REGION_LIMIT")
                        break
        return {
            "role": role,
            "localization": "RESOLVED",
            "modality": body.producer.kind,
            "text_artifact_id": body.text_artifact.id,
            "start": start,
            "end": end,
            "quote": self.text[alias][start:end],
            "regions": regions,
            "source_issues": list(issues),
        }
