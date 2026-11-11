"""Safe structured-response failure details shared by the adapter and worker."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class FailureDetail(StrEnum):
    SDK_PARSE_FAILURE = "SDK_PARSE_FAILURE"
    MALFORMED_JSON = "MALFORMED_JSON"
    MISSING_FIELD = "MISSING_FIELD"
    SCHEMA_VALIDATION = "SCHEMA_VALIDATION"
    INVALID_TABLE_GRAPH = "INVALID_TABLE_GRAPH"
    INVALID_CELL_SPAN = "INVALID_CELL_SPAN"
    DUPLICATE_ALIAS = "DUPLICATE_ALIAS"
    RESPONSE_OVERFLOW = "RESPONSE_OVERFLOW"
    OUTPUT_TOKEN_LIMIT = "OUTPUT_TOKEN_LIMIT"
    INCOMPLETE_RESPONSE = "INCOMPLETE_RESPONSE"
    CONTENT_FILTERED = "CONTENT_FILTERED"
    MISSING_PARSED_OUTPUT = "MISSING_PARSED_OUTPUT"
    INVALID_USAGE = "INVALID_USAGE"
    PROVIDER_FAILED_RESPONSE = "PROVIDER_FAILED_RESPONSE"
    PROVIDER_HTTP_ERROR = "PROVIDER_HTTP_ERROR"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"
    UPSTREAM_SERVER_ERROR = "UPSTREAM_SERVER_ERROR"


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    reason: FailureDetail
    path: str = Field(max_length=256)


# Exact matches against validators in the frozen schemas. The exception messages
# and context never cross this boundary, including for unknown validators.
_VALIDATOR_REASONS = {
    "Cyclic header relationships": FailureDetail.INVALID_TABLE_GRAPH,
    "Duplicate header references": FailureDetail.INVALID_TABLE_GRAPH,
    "Header reference requires another header in this table": FailureDetail.INVALID_TABLE_GRAPH,
    "A header relationship requires a readable header": FailureDetail.INVALID_TABLE_GRAPH,
    "Header span does not cover its declared relationship axis": FailureDetail.INVALID_CELL_SPAN,
    "Cell span is outside the observed grid": FailureDetail.INVALID_CELL_SPAN,
    "Overlapping cells must be one spanning cell, not copies": FailureDetail.INVALID_CELL_SPAN,
    "Duplicate table references": FailureDetail.DUPLICATE_ALIAS,
    "Cell/caption/note references must be unique within a table": FailureDetail.DUPLICATE_ALIAS,
    "Row and column references must be distinct": FailureDetail.DUPLICATE_ALIAS,
    "Observation local references must be unique within the response": (
        FailureDetail.DUPLICATE_ALIAS
    ),
    "Repeated source alias": FailureDetail.DUPLICATE_ALIAS,
    "Observation response exceeds its extraction capacity": FailureDetail.RESPONSE_OVERFLOW,
    "Observation response exceeds its byte limit": FailureDetail.RESPONSE_OVERFLOW,
    "Page exceeds its total cell bound": FailureDetail.RESPONSE_OVERFLOW,
}


def validation_issues(exc: ValidationError, model: type[BaseModel]) -> tuple[ValidationIssue, ...]:
    schema = model.model_json_schema()
    known_fields = {
        name
        for definition in (schema, *schema.get("$defs", {}).values())
        for name in definition.get("properties", {})
    }
    issues = []
    for error in exc.errors(include_input=False, include_url=False)[:8]:
        kind = error["type"]
        reason = {
            "json_invalid": FailureDetail.MALFORMED_JSON,
            "duplicate_table_alias": FailureDetail.DUPLICATE_ALIAS,
            "table_response_overflow": FailureDetail.RESPONSE_OVERFLOW,
            "missing": FailureDetail.MISSING_FIELD,
            "too_long": FailureDetail.RESPONSE_OVERFLOW,
            "string_too_long": FailureDetail.RESPONSE_OVERFLOW,
        }.get(kind, FailureDetail.SCHEMA_VALIDATION)
        if kind == "value_error":
            original = error.get("ctx", {}).get("error")
            if isinstance(original, ValueError) and len(original.args) == 1:
                message = original.args[0]
                if isinstance(message, str):
                    reason = _VALIDATOR_REASONS.get(message, reason)
        segments = [
            str(part)
            if (type(part) is int and 0 <= part < 100_000)
            or (isinstance(part, str) and part in known_fields)
            else "*"
            for part in error["loc"][:8]
        ]
        issues.append(ValidationIssue(reason=reason, path=".".join(segments)[:256]))
    return tuple(issues)
