"""Bounded, read-only projections of existing extraction records."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, StrictBool, StrictInt, StrictStr
from sqlalchemy import text

from powerforge_extraction.performance import AttemptPerformance
from powerforge_extraction.stage_contracts import AlternateRepresentation

Validation = Literal["validated", "partial", "fatal", "all_quarantined", "empty"]


Stage = Literal["EQUIPMENT_RECOGNITION", "ATTRIBUTE_EXTRACTION"]


class Attempt(BaseModel):
    stage: Stage
    attempt_id: UUID
    run_id: UUID
    document: str
    page: int
    attempt_number: int
    finished_at: datetime | None
    status: str
    provider: str
    model: str | None
    validation: Validation | None
    received: int | None
    accepted: int | None
    quarantined: int | None
    overflowed: int | None = None
    output_version: str | None = None
    output_bytes: int | None
    output_sha256: str | None
    expires_at: datetime | None
    retained: bool | None
    duration_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    cached_input_tokens: int | None
    cost: str | None
    pricing_basis: str | None
    published: int | None
    error_code: str | None


class AttemptPage(BaseModel):
    items: list[Attempt]
    next_cursor: UUID | None


class PublishedCandidate(BaseModel):
    ordinal: int
    local_ref: str
    mapping_status: str
    reason_code: str | None
    proposed_value: StrictStr | StrictInt | StrictBool | None
    alternate_representations: list[AlternateRepresentation] | None
    normalized_type: str | None
    normalized_value: str | None
    normalized_unit: str | None
    evidence: list[dict]


class AttemptDetail(BaseModel):
    attempt: Attempt
    request_sha256: str | None
    result_sha256: str | None
    upstream_sha256: str | None
    schema_version: str | None
    prompt_version: str | None
    rejections: list[dict]
    overflow_indices: list[int] = Field(default_factory=list)
    fatal: list[dict]
    validated: dict | None
    candidates: list[PublishedCandidate]
    performance: AttemptPerformance | None = None
    requested_reasoning_effort: Literal["none", "low", "medium"] | None = None


_FIELDS = """
u.id AS attempt_id, u.run_id, u.stage, d.original_filename AS document,
p.page_number AS page, u.attempt_number, u.finished_at, u.status::text AS status,
r.provider, r.model, CASE
    WHEN a.work_unit_id IS NULL THEN NULL
    WHEN a.received > 0 AND a.received = a.quarantined THEN 'all_quarantined'
    WHEN jsonb_array_length(a.fatal_diagnostics) > 0 THEN 'fatal'
    WHEN a.quarantined > 0 OR cardinality(a.overflow_indices) > 0 THEN 'partial'
    WHEN u.stage='EQUIPMENT_RECOGNITION' AND u.status='FAILED' THEN 'fatal'
    WHEN a.received = 0 THEN 'empty'
    ELSE 'validated' END AS validation,
a.received, a.accepted, a.quarantined, cardinality(a.overflow_indices) AS overflowed,
coalesce(a.output_version,u.execution_metadata->>'attribute_output_version') AS output_version,
a.output_bytes, a.output_sha256, a.expires_at,
(a.expires_at > statement_timestamp()) AS retained,
c.duration_ms, c.input_tokens, c.output_tokens, c.cached_input_tokens,
c.estimated_cost_usd::text AS cost, c.pricing_basis,
(u.output_counts->>'candidates')::int AS published, u.error_code
"""
_JOINS = """
FROM extraction_work_units u
JOIN extraction_runs r ON r.id=u.run_id
JOIN documents d ON d.id=r.document_id
JOIN document_pages p ON p.id::text=u.execution_metadata->>'source_page_id'
LEFT JOIN extraction_response_audits a ON a.work_unit_id=u.id
LEFT JOIN extraction_ai_calls c ON c.work_unit_id=u.id
"""


def list_attempts(engine, *, identity, validation, status, retention, cursor, limit, stage=None):
    # UUID ordering is stable across inserts and independent of mutable run state.
    query = f"""
    SELECT * FROM (SELECT {_FIELDS} {_JOINS}
      WHERE u.stage IN ('ATTRIBUTE_EXTRACTION', 'EQUIPMENT_RECOGNITION')
        AND (CAST(:stage AS text) IS NULL OR u.stage=:stage)
        AND (a.work_unit_id IS NOT NULL OR u.performance IS NOT NULL
             OR c.work_unit_id IS NOT NULL OR u.status IN ('FAILED', 'CANCELLED'))
        AND (CAST(:identity AS uuid) IS NULL
             OR u.id=:identity OR u.run_id=:identity)
        AND (CAST(:cursor AS uuid) IS NULL OR u.id<:cursor)
    ) s WHERE (CAST(:validation AS text) IS NULL OR validation=:validation)
        AND (CAST(:status AS text) IS NULL OR status=:status)
        AND (CAST(:retention AS boolean) IS NULL OR retained=:retention)
    ORDER BY attempt_id DESC LIMIT :limit
    """
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text(query),
                dict(
                    identity=identity,
                    stage=stage,
                    validation=validation,
                    status=status,
                    retention=retention,
                    cursor=cursor,
                    limit=limit + 1,
                ),
            )
            .mappings()
            .all()
        )
    items = [Attempt.model_validate(row) for row in rows[:limit]]
    return AttemptPage(items=items, next_cursor=items[-1].attempt_id if len(rows) > limit else None)


def attempt_detail(engine, attempt_id):
    query = f"""
    SELECT {_FIELDS},
    coalesce(a.request_hash,s.request_hash,e.provider_request_hash) AS request_sha256,
    s.result_hash AS result_sha256, s.upstream_hash AS upstream_sha256,
    c.schema_version, c.prompt_version, s.payload AS validated, u.performance,
    coalesce(a.attribute_reasoning_effort, u.execution_metadata->>'attribute_reasoning_effort')
        AS requested_reasoning_effort,
    coalesce(a.overflow_indices,ARRAY[]::integer[]) AS overflow_indices,
    coalesce(a.rejections,'[]'::jsonb) AS rejections,
    coalesce(a.fatal_diagnostics,c.validation_diagnostics,'[]'::jsonb) AS fatal
    {_JOINS} LEFT JOIN extraction_stage_results s ON s.work_unit_id=u.id
    LEFT JOIN extraction_unit_execution e ON e.work_unit_id=u.id
    WHERE u.id=:id AND u.stage IN ('ATTRIBUTE_EXTRACTION', 'EQUIPMENT_RECOGNITION')
    LIMIT 1
    """
    with engine.connect() as conn:
        row = conn.execute(text(query), {"id": attempt_id}).mappings().one_or_none()
        if row is None:
            return None
        candidates = (
            conn.execute(
                text("""
            SELECT ordinal, local_ref, mapping_status, reason_code,
              proposed_value, alternate_representations,
              normalized_type, normalized_unit,
              coalesce(value_number::text, value_integer::text, value_text,
                       value_boolean::text) AS normalized_value,
              coalesce((SELECT jsonb_agg(jsonb_build_object(
                'role', e.role, 'localization', e.localization, 'reason_code', e.reason_code
              ) ORDER BY e.ordinal) FROM extraction_evidence e WHERE e.candidate_id=c.id),
                '[]'::jsonb) AS evidence
            FROM extraction_candidates c WHERE c.work_unit_id=:id AND kind='ATTRIBUTE'
            ORDER BY ordinal LIMIT 528
        """),
                {"id": attempt_id},
            )
            .mappings()
            .all()
        )
    return AttemptDetail(
        attempt=Attempt.model_validate(row),
        performance=row["performance"],
        requested_reasoning_effort=row["requested_reasoning_effort"],
        request_sha256=row["request_sha256"],
        result_sha256=row["result_sha256"],
        upstream_sha256=row["upstream_sha256"],
        schema_version=row["schema_version"],
        prompt_version=row["prompt_version"],
        fatal=row["fatal"],
        overflow_indices=row["overflow_indices"],
        rejections=[
            {k: item[k] for k in ("collection", "index", "issues")} for item in row["rejections"]
        ],
        validated=row["validated"],
        candidates=[PublishedCandidate.model_validate(c) for c in candidates],
    )
