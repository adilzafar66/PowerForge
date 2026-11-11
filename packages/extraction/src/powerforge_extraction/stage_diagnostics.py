"""Bounded, content-free diagnostics for enriched stage attempts."""

import hashlib
import json
from collections import Counter
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from powerforge_ai.extraction_diagnostics import FailureDetail, ValidationIssue

Code = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")]
Count = Annotated[int, Field(ge=0, le=100_000)]
Phase = Literal[
    "SOURCE",
    "PROVIDER",
    "PARSE",
    "GROUNDING",
    "INTERPRETATION",
    "CONVERSION",
    "PUBLICATION",
    "COMPLETED",
]


class DiagnosticModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceCoverage(DiagnosticModel):
    prepared_result_id: UUID
    spatial_result_id: UUID
    document_page_id: UUID
    native_available: bool
    ocr_available: bool
    image_present: bool
    native_readings: Count
    ocr_readings: Count
    withheld_readings: Count
    layout_tables: Count
    conflict_pairs: Count
    text_coverage: Literal["UNKNOWN"]


class StageTrace(DiagnosticModel):
    version: Literal["extraction-stage-trace-v1"] = "extraction-stage-trace-v1"
    phase: Phase
    reason: Code | None = None
    provider_outcome: Code
    provider_detail: FailureDetail | None = None
    issues: tuple[ValidationIssue, ...] = Field(default=(), max_length=8)
    source: SourceCoverage | None = None
    schema_version: str | None = Field(default=None, max_length=80)
    prompt_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    returned: dict[Literal["equipment", "attributes", "tables"], Count] | None = None
    counts: dict[Code, Count] = Field(default_factory=dict, max_length=24)
    reasons: dict[Code, Count] = Field(default_factory=dict, max_length=48)


class SourceRejection(ValueError):
    """A grounded-source check failed. Its fixed code is safe for diagnostics."""

    def __init__(self, reason: Code, message: str):
        self.reason = reason
        super().__init__(message)


class StageDiagnostics:
    def __init__(self, capture=None):
        self.phase: Phase = "SOURCE"
        self.provider_outcome = "NOT_ATTEMPTED"
        self.provider_detail = None
        self.issues = ()
        self.source = None
        self.schema_version = None
        self.prompt_sha256 = None
        self.returned = None
        self.counts = Counter()
        self.reasons = Counter()
        self.capture = capture

    def observe(self, count, observation=None, *, reason=None, candidate=None, association=None):
        self.counts[count] += 1
        if reason:
            self.reasons[reason] += 1
        if self.capture is not None and observation is not None:
            self.capture.observation(
                observation, count, reason=reason, candidate=candidate, association=association
            )

    def result(self, *, reason=None, phase=None, publication_counts=None):
        return StageTrace(
            phase=phase or self.phase,
            reason=reason,
            provider_outcome=self.provider_outcome,
            provider_detail=self.provider_detail,
            issues=self.issues,
            source=self.source,
            schema_version=self.schema_version,
            prompt_sha256=self.prompt_sha256,
            returned=self.returned,
            counts=dict(self.counts) | (publication_counts or {}),
            reasons=dict(self.reasons),
        )

    def request_ready(self, request, sources):
        projection = json.loads(request.text)
        kinds = Counter(reading["reading_basis"] for reading in projection["readings"])
        roles = {item.text_artifact.role for item in sources.prepared.representations}
        self.source = SourceCoverage(
            prepared_result_id=sources.prepared.id,
            spatial_result_id=sources.layout.id,
            document_page_id=sources.layout.owner.document_page_id,
            native_available="NATIVE_POSITIONED_TEXT" in roles,
            ocr_available="OCR_TEXT" in roles,
            image_present=request.image is not None,
            native_readings=kinds["NATIVE_PDF"],
            ocr_readings=kinds["OCR"],
            withheld_readings=len(sources.readings) - len(projection["readings"]),
            layout_tables=len(sources.layout.tables),
            conflict_pairs=sum(item.kind == "CONFLICT" for item in sources.layout.overlaps),
            text_coverage=sources.prepared.text_coverage,
        )
        self.schema_version = request.schema_version
        self.prompt_sha256 = hashlib.sha256(request.instructions.encode()).hexdigest()
        if self.capture is not None:
            self.capture.request(request.text, self.schema_version, self.prompt_sha256)

    def parsed(self, response):
        self.provider_outcome = "PARSED"
        self.returned = {
            name: len(getattr(response, name))
            for name in ("equipment", "attributes", "tables")
            if hasattr(response, name)
        }
        if self.capture is not None:
            self.capture.response(response)

    def publication_trace(self, output):
        return self.result(
            phase="COMPLETED",
            publication_counts={
                "PUBLISHED_CANDIDATES": len(output.candidates),
                "PUBLISHED_TABLES": len(output.tables),
                "PUBLISHED_EVIDENCE": len(output.evidence),
            },
        )
