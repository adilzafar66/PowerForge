"""Bounded Stage 2 envelope admission and assertion quarantine."""

import json
from dataclasses import dataclass, replace
from typing import Literal

from pydantic import Field, TypeAdapter, ValidationError

from powerforge_ai.extraction import ValidationIssue
from powerforge_extraction.response_diagnostics import validation_issues
from powerforge_extraction.stage_contracts import (
    ATTRIBUTE_VERSION,
    MAX_RESPONSE_BYTES,
    AttributeRequest,
    AttributeResponse,
    Contract,
    Hash,
    InferredAssertion,
    RawUnmappedAssertion,
    Ref,
    RegistryAssertion,
)

_REF = TypeAdapter(Ref)


class AttributeEnvelope(Contract):
    version: Literal[ATTRIBUTE_VERSION]
    stage: Literal["ATTRIBUTE_EXTRACTION"]
    page_context_hash: Hash
    upstream_hash: Hash
    attributes: list[object] = Field(max_length=512)
    raw_unmapped: list[object] = Field(max_length=16)


@dataclass(frozen=True)
class RejectedAssertion:
    collection: str
    index: int
    local_ref: str | None
    issues: tuple[ValidationIssue, ...]


@dataclass(frozen=True)
class AttributeAdmission:
    received: int | None = None
    result: AttributeResponse | None = None
    rejected: tuple[RejectedAssertion, ...] = ()
    fatal: tuple[ValidationIssue, ...] = ()

    @property
    def accepted(self):
        if self.received is None:
            return None
        return (len(self.result.attributes) + len(self.result.raw_unmapped)) if self.result else 0


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("Duplicate JSON object member")
        obj[key] = value
    return obj


def _reject_constant(_):
    raise ValueError("Non-finite JSON constant")


def _bounded_tree(value):
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > 24:
            raise ValueError("Response nesting exceeds the contract")
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)


def _validate_persistable_strings(value):
    """Reject strings that cannot be inserted into PostgreSQL JSONB."""
    if isinstance(value, str):
        if "\x00" in value:
            raise ValueError("Invalid persisted string")
        value.encode("utf-8")
    elif isinstance(value, dict):
        for child in value.values():
            _validate_persistable_strings(child)
    elif isinstance(value, (tuple, list)):
        for child in value:
            _validate_persistable_strings(child)


def admit_attributes(request: AttributeRequest, raw: bytes) -> AttributeAdmission:
    if len(raw) > MAX_RESPONSE_BYTES:
        return AttributeAdmission(
            fatal=(ValidationIssue(category="CAPACITY", error_type="response_byte_limit"),)
        )
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_reject_constant
        )
        _bounded_tree(value)
    except (ValueError, RecursionError):
        return AttributeAdmission(
            fatal=(ValidationIssue(category="JSON", error_type="invalid_json_structure"),)
        )
    try:
        envelope = AttributeEnvelope.model_validate(value)
    except ValidationError as error:
        return AttributeAdmission(fatal=validation_issues(error))
    received = len(envelope.attributes) + len(envelope.raw_unmapped)
    for field, error_type in (
        ("page_context_hash", "page_identity_mismatch"),
        ("upstream_hash", "upstream_identity_mismatch"),
    ):
        if getattr(envelope, field) != getattr(request, field):
            return AttributeAdmission(
                received=received,
                fatal=(
                    ValidationIssue(category="CROSS_FIELD", error_type=error_type, path=(field,)),
                ),
            )

    items = [
        (group, index, item)
        for group in ("attributes", "raw_unmapped")
        for index, item in enumerate(getattr(envelope, group))
    ]
    refs = set()
    identified = []
    for group, index, item in items:
        try:
            ref = (
                _REF.validate_python(item.get("local_ref"), strict=True)
                if isinstance(item, dict)
                else None
            )
        except ValidationError:
            ref = None
        if ref is not None and ref in refs:
            return AttributeAdmission(
                received=received,
                fatal=(
                    ValidationIssue(
                        category="CROSS_FIELD",
                        error_type="duplicate_reference",
                        path=(group, index, "local_ref"),
                    ),
                ),
            )
        if ref is not None:
            refs.add(ref)
        identified.append((group, index, item, ref))

    attributes = []
    raw_unmapped = []
    rejected = []
    for group, index, item, ref in identified:
        path = (group, index)
        try:
            if not isinstance(item, dict):
                issues = (ValidationIssue(category="SCHEMA", error_type="model_type", path=path),)
            elif group == "attributes" and item.get("origin") not in ("INFERRED", "EXTRACTED"):
                issues = (
                    ValidationIssue(
                        category="SCHEMA", error_type="literal_error", path=(*path, "origin")
                    ),
                )
            else:
                model = (
                    RawUnmappedAssertion
                    if group == "raw_unmapped"
                    else InferredAssertion
                    if item["origin"] == "INFERRED"
                    else RegistryAssertion
                )
                # JSON mode preserves strict tuple and exact-decimal wire semantics.
                assertion = model.model_validate_json(json.dumps(item, allow_nan=False))
                _validate_persistable_strings(assertion.model_dump(mode="json"))
                if group == "raw_unmapped":
                    raw_unmapped.append(assertion)
                else:
                    attributes.append(assertion)
                continue
        except ValidationError as error:
            issues = tuple(
                issue.model_copy(update={"path": (*path, *issue.path)[:8]})
                for issue in validation_issues(error)
            )
        except ValueError:
            issues = (ValidationIssue(category="SCHEMA", error_type="schema_invalid", path=path),)
        rejected.append(RejectedAssertion(group, index, ref, issues))
    admission = AttributeAdmission(received=len(items), rejected=tuple(rejected))
    if items and len(rejected) == len(items):
        return replace(
            admission,
            fatal=(ValidationIssue(category="SCHEMA", error_type="all_assertions_quarantined"),),
        )
    return replace(
        admission,
        result=AttributeResponse(
            version=ATTRIBUTE_VERSION,
            stage="ATTRIBUTE_EXTRACTION",
            page_context_hash=request.page_context_hash,
            upstream_hash=request.upstream_hash,
            attributes=tuple(attributes),
            raw_unmapped=tuple(raw_unmapped),
        ),
    )
