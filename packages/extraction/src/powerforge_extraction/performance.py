"""Bounded, content-free observations of extraction work."""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from hashlib import sha256
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from powerforge_extraction.compact_context import reading_rows
from powerforge_extraction.identities import canonical_json

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Count = Annotated[int, Field(strict=True, ge=0, le=2**53 - 1)]
Phase = Literal[
    "source_load",
    "request_build",
    "provider_call",
    "admission",
    "localization_normalization",
    "audit_store",
    "db_publish",
]
ServiceTier = Literal["auto", "default", "flex", "priority", "scale"]
Effort = Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]
ResponseStatus = Literal[
    "completed",
    "incomplete",
    "failed",
    "cancelled",
    "queued",
    "in_progress",
    "refusal",
    "timeout",
    "transport_error",
]
SERVICE_TIERS = ("auto", "default", "flex", "priority", "scale")
EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
RESPONSE_STATUSES = ("completed", "incomplete", "failed", "cancelled", "queued", "in_progress")


class Metrics(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class RequestMetrics(Metrics):
    input_sha256: Digest
    body_bytes: Count
    encoded_image_bytes: Count
    image_detail: Literal["low", "high", "auto"]
    image_width: Count
    image_height: Count
    native_readings: Count
    ocr_readings: Count
    reading_text_chars: Count
    alternate_readings: Count
    uncertain_readings: Count
    line_count: Count | None = None
    table_count: Count
    cell_count: Count
    order_count: Count
    overlap_count: Count
    conflicting_overlap_count: Count
    equipment_count: Count
    eligible_type_count: Count
    registry_definition_count: Count
    catalog_bytes: Count
    recognition_bytes: Count
    page_bytes: Count
    instructions_bytes: Count
    schema_bytes: Count


class AttemptPerformance(Metrics):
    version: Literal[1] = 1
    queue_wait_ms: Count | None = None
    source_load_ms: Count | None = None
    request_build_ms: Count | None = None
    provider_call_ms: Count | None = None
    admission_ms: Count | None = None
    localization_normalization_ms: Count | None = None
    audit_store_ms: Count | None = None
    db_publish_ms: Count | None = None
    attempt_total_ms: Count | None = None
    failure_stage: Phase | None = None
    reasoning_tokens: Count | None = None
    visible_output_tokens: Count | None = None
    service_tier: ServiceTier | None = None
    reasoning_effort: Effort | None = None
    response_status: ResponseStatus | None = None
    ocr_selected: bool | None = None
    profile_sha256: Digest | None = None
    prompt_sha256: Digest | None = None
    schema_sha256: Digest | None = None
    request: RequestMetrics | None = None


active_performance: ContextVar[AttemptPerformance | None] = ContextVar(
    "active_extraction_performance", default=None
)


@contextmanager
def measure(phase: Phase) -> Iterator[None]:
    performance = active_performance.get()
    if performance is None:
        yield
        return
    start = time.perf_counter_ns()
    try:
        yield
    except Exception:
        performance.failure_stage = phase
        raise
    finally:
        field = f"{phase}_ms"
        setattr(performance, field, (getattr(performance, field) or 0) + elapsed_ms(start))


def elapsed_ms(start: int) -> int:
    return (time.perf_counter_ns() - start) // 1_000_000


def request_metrics(
    payload, *, body_bytes, encoded_image_bytes, image_detail, instructions, schema_bytes
):
    page = payload["page"]
    layout = page["layout"]
    projected_rows = page["readings"]["rows"]
    rows = list(reading_rows(page["readings"]))
    grouped = "member_columns" in page["readings"]
    catalog = payload["attribute_catalog"]
    upstream = payload["upstream"]

    def size(value):
        return len(canonical_json(value).encode())

    return RequestMetrics(
        input_sha256=sha256(canonical_json(payload).encode()).hexdigest(),
        body_bytes=body_bytes,
        encoded_image_bytes=encoded_image_bytes,
        image_detail=image_detail,
        image_width=page["image_width"],
        image_height=page["image_height"],
        native_readings=sum(row[2] == "NATIVE_PDF" for row in rows),
        ocr_readings=sum(row[2] == "OCR" for row in rows),
        reading_text_chars=sum(len(row[1]) + sum(map(len, row[3])) for row in rows),
        alternate_readings=sum(len(row[3]) for row in rows),
        uncertain_readings=sum(bool(row[4]) for row in rows),
        line_count=sum(row.get("kind") == "LINE" for row in projected_rows if isinstance(row, dict))
        if grouped
        else None,
        table_count=len(layout["tables"]),
        cell_count=sum(len(table["cells"]) for table in layout["tables"]),
        order_count=len(layout["order"]["rows"]),
        overlap_count=len(layout["overlaps"]),
        conflicting_overlap_count=sum(
            (item[2] if grouped else item["kind"]) in {"CONFLICT", "AMBIGUOUS"}
            for item in layout["overlaps"]
        ),
        equipment_count=len(upstream["equipment"]),
        eligible_type_count=len({definition["equipment_type"] for definition in catalog}),
        registry_definition_count=len(catalog),
        catalog_bytes=size(catalog),
        recognition_bytes=size(upstream),
        page_bytes=size(page),
        instructions_bytes=len(instructions.encode()),
        schema_bytes=schema_bytes,
    )
