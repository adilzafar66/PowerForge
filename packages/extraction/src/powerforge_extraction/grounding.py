"""Verified page inputs and conservative text/visual grounding; no ORM or provider SDK."""

import hashlib
import re
from dataclasses import dataclass
from importlib.resources import files
from io import BytesIO
from typing import Literal
from uuid import UUID

from PIL import Image

from powerforge_document_processing.storage.base import ObjectStorage
from powerforge_extraction.contracts import EvidenceInput
from powerforge_extraction.identities import content_hash, identity_hash
from powerforge_extraction.observations import SourceObservation
from powerforge_provenance.locations import SourceLocation

GROUNDING_VERSION = "engineering-grounding-v1"
_RATING_PAIR = re.compile(r"([+-]?[0-9]+(?:\.[0-9]+)?\s*AF)\s*/\s*([+-]?[0-9]+(?:\.[0-9]+)?\s*AT)")


def rating_line(text: str) -> bool:
    return bool(
        _RATING_PAIR.fullmatch(text.strip())
        or re.fullmatch(
            r"[+-]?[0-9]+(?:\.[0-9]+)?\s*(?:AF|AT|%Z)",
            text.strip(),
        )
    )


def grounding_identity(version: str = GROUNDING_VERSION) -> dict:
    if version != GROUNDING_VERSION:
        raise ValueError("Unsupported engineering grounding version")
    resources = files("powerforge_extraction")
    hashes = {
        name: content_hash(resources.joinpath(name).read_text(encoding="utf-8"))
        for name in (
            "grounding.py",
            "engineering_output.py",
            "engineering_sources.py",
        )
    }
    return {"version": version, "rules_hash": identity_hash(hashes)}


@dataclass(frozen=True)
class ArtifactSpec:
    id: UUID
    role: Literal["native_text", "analysis_image"]
    storage_key: str
    size_bytes: int
    sha256: str
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True)
class PageSpec:
    run_id: UUID
    unit_id: UUID
    unit_key: str
    stage: str
    document_id: UUID
    processing_run_id: UUID
    page_id: UUID
    page_number: int
    artifacts: tuple[ArtifactSpec, ...]


@dataclass(frozen=True)
class PageSources:
    spec: PageSpec
    text: str | None
    image: bytes | None

    def artifact(self, role: str) -> ArtifactSpec:
        for item in self.spec.artifacts:
            if item.role == role:
                return item
        raise ValueError("Source role is outside pinned page inputs")


def load_page_sources(
    spec: PageSpec,
    storage: ObjectStorage,
    *,
    max_artifact_bytes: int = 2 * 1024 * 1024,
    max_total_bytes: int = 4 * 1024 * 1024,
    max_image_pixels: int = 20_000_000,
) -> PageSources:
    """Load only server-selected pinned descriptors; never fall back to another artifact."""
    roles = [item.role for item in spec.artifacts]
    if (
        not roles
        or len(roles) != len(set(roles))
        or not set(roles) <= {"native_text", "analysis_image"}
    ):
        raise ValueError("Page inputs require distinct supported source roles")
    if any(item.size_bytes < 0 or item.size_bytes > max_artifact_bytes for item in spec.artifacts):
        raise ValueError("Pinned artifact exceeds its input bound")
    if sum(item.size_bytes for item in spec.artifacts) > max_total_bytes:
        raise ValueError("Pinned page inputs exceed their combined bound")
    text, image = None, None
    for artifact in spec.artifacts:
        stream = storage.get(artifact.storage_key)
        try:
            chunks, remaining = [], max_artifact_bytes + 1
            while remaining > 0:
                chunk = stream.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
        finally:
            stream.close()
        if len(data) != artifact.size_bytes or hashlib.sha256(data).hexdigest() != artifact.sha256:
            raise ValueError("Pinned source artifact integrity mismatch")
        if artifact.role == "native_text":
            try:
                text = data.decode("utf-8")
            except UnicodeError:
                raise ValueError("Pinned native text is not valid UTF-8") from None
        else:
            try:
                with Image.open(BytesIO(data)) as parsed:
                    if (
                        parsed.format != "PNG"
                        or parsed.width * parsed.height > max_image_pixels
                        or (parsed.width, parsed.height) != (artifact.width, artifact.height)
                    ):
                        raise ValueError("Invalid image bounds")
                    parsed.verify()
            except Exception:
                raise ValueError("Pinned analysis image is invalid or exceeds its bounds") from None
            image = data
    return PageSources(spec, text, image)


def occurrences(
    text: str, quote: str, prefix: str | None = None, suffix: str | None = None
) -> list[int]:
    """Two surviving occurrences suffice to establish ambiguity without allocating all matches."""
    found, start = [], 0
    while (position := text.find(quote, start)) >= 0:
        end = position + len(quote)
        if (prefix is None or text.endswith(prefix, 0, position)) and (
            suffix is None or text.startswith(suffix, end)
        ):
            found.append(position)
            if len(found) == 2:
                break
        start = position + 1
    return found


def line_span(text: str, start: int, end: int) -> tuple[int, int]:
    left, right = text.rfind("\n", 0, start) + 1, text.find("\n", end)
    return left, len(text) if right < 0 else right


def paragraph_span(text: str, start: int, end: int) -> tuple[int, int]:
    left, right = 0, len(text)
    for separator in re.finditer(r"\n[ \t\r]*\n", text):
        if separator.end() <= start:
            left = separator.end()
        elif separator.start() >= end:
            right = separator.start()
            break
    return left, right


@dataclass(frozen=True)
class GroundedObservation:
    role: str
    artifact_id: UUID
    statement: str
    own_span: tuple[int, int] | None
    evidence: tuple[EvidenceInput, ...]

    @property
    def precision(self) -> str:
        if self.role == "analysis_image":
            return "VISUAL_PAGE"
        return "TEXT_OFFSETS" if self.own_span is not None else "TEXT_PAGE"


def ground_observation(
    observation: SourceObservation, sources: PageSources
) -> GroundedObservation | None:
    native = [anchor for anchor in observation.anchors if anchor.kind == "NATIVE_TEXT"]
    if native:
        if sources.text is None:
            return None
        artifact = sources.artifact("native_text")
        evidence, own_spans = [], set()
        found_expression = False
        for anchor in native:
            positions = occurrences(sources.text, anchor.quote, anchor.prefix, anchor.suffix)
            if not positions:
                return None  # Invalid native claims cannot fall back to page-level vision.
            own_positions = occurrences(anchor.quote, observation.raw_expression)
            if own_positions:
                found_expression = True
                if len(positions) == 1 and len(own_positions) == 1:
                    start = positions[0] + own_positions[0]
                    own_spans.add((start, start + len(observation.raw_expression)))
                else:
                    own_spans.add(None)
            else:
                continue  # A real but unrelated excerpt is not support for this observation.
            precise = len(positions) == 1
            evidence.append(
                EvidenceInput(
                    location=SourceLocation(
                        document_page_id=sources.spec.page_id, page_artifact_id=artifact.id
                    ),
                    source_kind="NATIVE_TEXT",
                    extraction_method="AI_TEXT",
                    source_snippet=anchor.quote,
                    text_start=positions[0] if precise else None,
                    text_end=positions[0] + len(anchor.quote) if precise else None,
                    offset_convention="UNICODE_CODEPOINT" if precise else None,
                )
            )
        if not found_expression:
            return None
        own = next(iter(own_spans)) if len(own_spans) == 1 else None
        statement = observation.raw_expression
        if own is not None:
            start, end = line_span(sources.text, *own)
            statement = sources.text[start:end]
            # A fully matched AF/AT pair has two explicit field clauses and no hidden
            # qualifiers. Do not split arbitrary prose, ratios or unit expressions.
            paired = _RATING_PAIR.fullmatch(statement.strip())
            if paired:
                base = start + len(statement) - len(statement.lstrip())
                for group in (1, 2):
                    left, right = base + paired.start(group), base + paired.end(group)
                    if left <= own[0] and own[1] <= right:
                        start, end = left, right
                        statement = sources.text[start:end]
                        break
            if len(statement) <= 2000:
                evidence = [
                    EvidenceInput(
                        location=SourceLocation(
                            document_page_id=sources.spec.page_id, page_artifact_id=artifact.id
                        ),
                        source_kind="NATIVE_TEXT",
                        extraction_method="AI_TEXT",
                        source_snippet=statement,
                        text_start=start,
                        text_end=end,
                        offset_convention="UNICODE_CODEPOINT",
                    )
                ]
        if len(statement) > 2000:
            return None
        return GroundedObservation("native_text", artifact.id, statement, own, tuple(evidence))
    if sources.image is None:
        return None
    artifact = sources.artifact("analysis_image")
    return GroundedObservation(
        "analysis_image",
        artifact.id,
        observation.raw_expression,
        None,
        (
            EvidenceInput(
                location=SourceLocation(
                    document_page_id=sources.spec.page_id, page_artifact_id=artifact.id
                ),
                source_kind="VISUAL_REGION",
                extraction_method="AI_VISION",
            ),
        ),
    )
