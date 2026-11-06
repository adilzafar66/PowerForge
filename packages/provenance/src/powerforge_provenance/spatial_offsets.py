"""Representation matching and native emission-trace correspondence; never OCR-to-native."""

from collections import defaultdict
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from powerforge_provenance.spatial_base import (
    POLICY,
    LocalRef,
    SpatialContract,
    TextSpan,
    bounded_json,
    revalidate,
)
from powerforge_provenance.spatial_geometry import UprightTransform
from powerforge_provenance.spatial_sources import (
    ArtifactRef,
    EnrichmentArtifactRef,
    OriginalDocument,
    PageOwner,
    ProducerIdentity,
    checked_bytes,
    checked_text,
)


class TextMatch(SpatialContract):
    version: Literal["source-occurrence-v1"] = "source-occurrence-v1"
    artifact_id: UUID
    status: Literal["EXACT", "MISSING", "AMBIGUOUS", "UNPROVEN"]
    span: TextSpan | None
    reason: Literal[
        "UNIQUE_LITERAL",
        "LITERAL_ABSENT",
        "MULTIPLE_LITERAL_OCCURRENCES",
        "MISSING_NATIVE_TRACE",
        "DIFFERENT_ORIGIN_DATASET",
        "INCOMPLETE_OR_NONCONTIGUOUS_ORIGINS",
        "DIFFERENT_READING",
        "SHARED_NATIVE_ORIGINS",
    ]

    @model_validator(mode="after")
    def exact_only(self):
        if (self.status == "EXACT") != (self.span is not None):
            raise ValueError("Only an exact occurrence has a text span")
        allowed = {
            "EXACT": {"UNIQUE_LITERAL", "SHARED_NATIVE_ORIGINS"},
            "MISSING": {"LITERAL_ABSENT"},
            "AMBIGUOUS": {"MULTIPLE_LITERAL_OCCURRENCES"},
        }
        if (self.status in allowed and self.reason not in allowed[self.status]) or (
            self.status == "UNPROVEN" and self.reason in set().union(*allowed.values())
        ):
            raise ValueError("Text match reason differs from its resolution status")
        return self


def match_quote(artifact: ArtifactRef, data: bytes, quote: str, *, within: TextSpan | None = None):
    """Exact text occurrence only. This establishes neither geometry nor row membership."""
    text = checked_text(artifact, data)
    if type(quote) is not str or not 0 < len(quote) <= POLICY["max_reading_characters"]:
        raise ValueError("Quote exceeds the source reading bound")
    start, end = 0, len(text)
    if within is not None:
        within = revalidate(within)
        start, end = within.start, within.end
        if end > len(text):
            raise ValueError("Selected occurrence window exceeds its text artifact")
    found = []
    while (position := text.find(quote, start, end)) >= 0:
        found.append(position)
        if len(found) == 2:
            return TextMatch(
                artifact_id=artifact.id,
                status="AMBIGUOUS",
                span=None,
                reason="MULTIPLE_LITERAL_OCCURRENCES",
            )
        start = position + 1
    return TextMatch(
        artifact_id=artifact.id,
        status="EXACT" if found else "MISSING",
        span=TextSpan(start=found[0], end=found[0] + len(quote)) if found else None,
        reason="UNIQUE_LITERAL" if found else "LITERAL_ABSENT",
    )


class OriginFragment(SpatialContract):
    span: TextSpan
    origin_ref: LocalRef
    origin_start: int = Field(ge=0, lt=POLICY["max_text_characters"])

    @model_validator(mode="after")
    def bounded_origin(self):
        if self.origin_start + self.span.length > POLICY["max_text_characters"]:
            raise ValueError("Native origin interval exceeds its bound")
        return self


class NativeEmissionTrace(SpatialContract):
    """Producer-supplied origin witness, NOT a trace inferred by matching words.

    A historical Phase 3 artifact has no such witness today. M2 must not manufacture
    one from a newly sorted reading. Persistence must validate the witness producer.
    """

    version: Literal["native-emission-trace-v1"] = "native-emission-trace-v1"
    text_artifact: ArtifactRef
    # Identifies a shared immutable native character/emission-origin dataset,
    # distinct from the text/geometry artifact's digest. Equal text hashes do not suffice.
    origin_artifact: EnrichmentArtifactRef
    fragments: tuple[OriginFragment, ...] = Field(max_length=POLICY["max_origin_fragments"])

    @model_validator(mode="after")
    def native_only(self):
        if (
            self.text_artifact.role not in {"NATIVE_TEXT", "NATIVE_POSITIONED_TEXT"}
            or self.origin_artifact.role != "NATIVE_ORIGINS"
            or self.origin_artifact.owner != self.text_artifact.owner
        ):
            raise ValueError(
                "Native correspondence requires same-page native text/origin identities"
            )
        previous = -1
        origins = defaultdict(list)
        for fragment in sorted(self.fragments, key=lambda f: f.span.start):
            if fragment.span.start < previous:
                raise ValueError("Native text emission intervals overlap")
            previous = fragment.span.end
            origins[fragment.origin_ref].append(
                (fragment.origin_start, fragment.origin_start + fragment.span.length)
            )
        for intervals in origins.values():
            for a, b in zip(sorted(intervals), sorted(intervals)[1:], strict=False):
                if a[1] > b[0]:
                    raise ValueError("A native origin occurrence is emitted more than once")
        bounded_json(self, POLICY["max_manifest_bytes"])
        return self


class NativeOrigin(SpatialContract):
    ref: LocalRef
    raw_text: str = Field(min_length=1, max_length=POLICY["max_reading_characters"])
    # Native engine traversal locator; it is not an index into another text string.
    path: tuple[int, ...] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def nonnegative_path(self):
        if any(index < 0 or index > 1_000_000 for index in self.path):
            raise ValueError("Native traversal path is outside its bound")
        return self


class NativeOriginDataset(SpatialContract):
    version: Literal["native-origin-dataset-v1"] = "native-origin-dataset-v1"
    id: UUID
    owner: PageOwner
    original: OriginalDocument
    producer: ProducerIdentity
    transform: UprightTransform
    origins: tuple[NativeOrigin, ...] = Field(max_length=POLICY["max_origin_fragments"])

    @model_validator(mode="after")
    def native_dataset(self):
        if (
            self.original.document_id != self.owner.document_id
            or self.producer.kind != "NATIVE_PDF"
            or self.transform.source_frame.unit != "PDF_POINTS"
            or len({o.ref for o in self.origins}) != len(self.origins)
            or len({o.path for o in self.origins}) != len(self.origins)
            or sum(len(o.raw_text) for o in self.origins) > POLICY["max_text_characters"]
        ):
            raise ValueError(
                "Native origin dataset has mismatched ownership/kind or invalid origins"
            )
        bounded_json(self, POLICY["max_manifest_bytes"])
        return self


def _checked_trace(trace, artifact, data):
    trace = revalidate(trace)
    if trace.text_artifact != artifact:
        raise ValueError("Native trace refers to another immutable text artifact")
    text = checked_text(artifact, data)
    if any(f.span.end > len(text) for f in trace.fragments):
        raise ValueError("Native trace exceeds its exact text representation")
    return trace, text


def map_native_occurrence(
    source_trace: NativeEmissionTrace,
    source_data: bytes,
    source_span: TextSpan,
    target: ArtifactRef,
    target_data: bytes,
    target_trace: NativeEmissionTrace | None,
    *,
    origin_data: bytes | None = None,
):
    """Map only a consistent contiguous shared-origin witness, not equal substrings.

    This checks a detached witness. It cannot authenticate the origin engine,
    original producer's commitment or artifact storage; those are M2/M4 boundaries.
    """
    source_span, target = revalidate(source_span), revalidate(target)
    source_trace, source = _checked_trace(source_trace, source_trace.text_artifact, source_data)
    target_text = checked_text(target, target_data)
    if source_trace.text_artifact.owner != target.owner or target.role not in {
        "NATIVE_TEXT",
        "NATIVE_POSITIONED_TEXT",
    }:
        raise ValueError("Native offsets cannot cross pages/processing runs or cite OCR")
    if source_span.end > len(source):
        raise ValueError("Source occurrence exceeds its text representation")

    def unproven(reason):
        return TextMatch(artifact_id=target.id, status="UNPROVEN", span=None, reason=reason)

    if target_trace is None:
        return unproven("MISSING_NATIVE_TRACE")
    target_trace, _ = _checked_trace(target_trace, target, target_data)
    if source_trace.origin_artifact != target_trace.origin_artifact:
        return unproven("DIFFERENT_ORIGIN_DATASET")
    if origin_data is None:
        return unproven("MISSING_NATIVE_TRACE")
    checked_bytes(source_trace.origin_artifact, origin_data)
    dataset = NativeOriginDataset.model_validate_json(origin_data)
    if (
        dataset.id != source_trace.origin_artifact.id
        or dataset.owner != source_trace.text_artifact.owner
    ):
        raise ValueError("Native origin data differs from its pinned source identity")
    origins = {o.ref: o.raw_text for o in dataset.origins}
    for trace, text in ((source_trace, source), (target_trace, target_text)):
        for fragment in trace.fragments:
            raw = origins.get(fragment.origin_ref)
            if (
                raw is None
                or fragment.origin_start + fragment.span.length > len(raw)
                or (
                    raw[fragment.origin_start : fragment.origin_start + fragment.span.length]
                    != text[fragment.span.start : fragment.span.end]
                )
            ):
                raise ValueError("Native emission trace differs from its exact origin dataset")
    targets = defaultdict(list)
    for f in target_trace.fragments:
        targets[f.origin_ref].append(f)
    mapped = []
    cursor = source_span.start
    for f in sorted(source_trace.fragments, key=lambda item: item.span.start):
        lo, hi = max(f.span.start, source_span.start), min(f.span.end, source_span.end)
        if lo >= hi:
            continue
        if lo != cursor:
            return unproven("INCOMPLETE_OR_NONCONTIGUOUS_ORIGINS")
        origin_lo, origin_hi = (
            f.origin_start + lo - f.span.start,
            f.origin_start + hi - f.span.start,
        )
        origin_cursor = origin_lo
        for t in sorted(targets[f.origin_ref], key=lambda item: item.origin_start):
            left, right = (
                max(origin_lo, t.origin_start),
                min(origin_hi, t.origin_start + t.span.length),
            )
            if left >= right:
                continue
            if left != origin_cursor:
                return unproven("INCOMPLETE_OR_NONCONTIGUOUS_ORIGINS")
            mapped.append((t.span.start + left - t.origin_start, right - left))
            origin_cursor = right
        if origin_cursor != origin_hi:
            return unproven("INCOMPLETE_OR_NONCONTIGUOUS_ORIGINS")
        cursor = hi
    if (
        cursor != source_span.end
        or not mapped
        or any(a[0] + a[1] != b[0] for a, b in zip(mapped, mapped[1:], strict=False))
    ):
        return unproven("INCOMPLETE_OR_NONCONTIGUOUS_ORIGINS")
    start, end = mapped[0][0], mapped[-1][0] + mapped[-1][1]
    if source[source_span.start : source_span.end] != target_text[start:end]:
        return unproven("DIFFERENT_READING")
    return TextMatch(
        artifact_id=target.id,
        status="EXACT",
        span=TextSpan(start=start, end=end),
        reason="SHARED_NATIVE_ORIGINS",
    )
