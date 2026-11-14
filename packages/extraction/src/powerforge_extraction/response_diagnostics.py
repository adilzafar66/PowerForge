"""Translate model validation failures without carrying provider-controlled strings."""

from typing import get_args

from pydantic import ValidationError

from powerforge_ai.extraction import (
    MAX_VALIDATION_ISSUES,
    ValidationField,
    ValidationIssue,
    ValidationType,
)

_FIELDS = frozenset(get_args(ValidationField))
_TYPES = frozenset(get_args(ValidationType))
_CONSTRAINTS = frozenset(
    {
        "string_pattern_mismatch",
        "string_too_short",
        "string_too_long",
        "enum",
        "literal_error",
        "too_short",
        "too_long",
        "greater_than",
        "greater_than_equal",
        "less_than",
        "less_than_equal",
    }
)


def validation_issues(error: ValidationError) -> tuple[ValidationIssue, ...]:
    issues = []
    for entry in error.errors(include_input=False, include_context=False, include_url=False):
        error_type = entry["type"]
        # Pydantic extra-field locations contain arbitrary keys, even when the key
        # happens to look like a trusted field name.
        parts = entry["loc"]
        if error_type == "extra_forbidden":
            parts = (*parts[:-1], "*")
        path = tuple(
            part if (type(part) is int and 0 <= part < 1024) or part in _FIELDS else "*"
            for part in parts[:8]
        )
        category = (
            "JSON"
            if error_type == "json_invalid"
            else "FIELD_CONSTRAINT"
            if error_type in _CONSTRAINTS
            else "SCHEMA"
        )
        issue = ValidationIssue(
            category=category,
            error_type=error_type if error_type in _TYPES else "schema_invalid",
            path=path,
        )
        if issue not in issues:
            issues.append(issue)
            if len(issues) == MAX_VALIDATION_ISSUES:
                break
    return tuple(issues)
