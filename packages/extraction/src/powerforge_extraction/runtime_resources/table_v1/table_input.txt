"""Pinned table Responses envelopes. Pure validation/rendering; no vendor SDK or ORM."""

import base64
import json

from powerforge_extraction.identities import canonical_json
from powerforge_extraction.table_profiles import table_input_contract
from powerforge_extraction.table_stages import get_table_stage

TABLE_FIELDS = {
    "local_ref",
    "proposed_kind",
    "rows",
    "columns",
    "cells",
    "title",
    "notes",
    "ambiguous",
    "ambiguity_reason",
    "truncated",
    "truncation_reason",
    "structure_basis",
    "scoped_refs",
    "cell_text_basis",
}
CELL_FIELDS = {
    "local_ref",
    "row",
    "column",
    "row_span",
    "column_span",
    "state",
    "raw_text",
    "header_role",
    "header_refs",
    "ambiguous",
    "ambiguity_reason",
}
TEXT_FIELDS = {"local_ref", "raw_text", "ambiguous", "ambiguity_reason"}


def validate_projection(context):
    contract = table_input_contract()
    if (
        not isinstance(context, dict)
        or set(context) != {"version", "tables"}
        or (
            context["version"] != contract["context_version"]
            or not isinstance(context["tables"], list)
            or len(context["tables"]) > 8
        )
    ):
        raise ValueError("Unsupported committed table context")
    total = 0
    for item in context["tables"]:
        if not isinstance(item, dict) or set(item) != TABLE_FIELDS:
            raise ValueError("Unsupported committed table fields")
        if not isinstance(item["cells"], list) or not isinstance(item["notes"], list):
            raise ValueError("Malformed committed table items")
        total += len(item["cells"])
        for cell in item["cells"]:
            if not isinstance(cell, dict) or set(cell) != CELL_FIELDS:
                raise ValueError("Unsupported committed cell fields")
            if not isinstance(cell["local_ref"], str) or not (
                cell["raw_text"] is None or isinstance(cell["raw_text"], str)
            ):
                raise ValueError("Malformed committed cell reading")
        for text in [*item["notes"], *([item["title"]] if item["title"] is not None else [])]:
            if not isinstance(text, dict) or set(text) != TEXT_FIELDS:
                raise ValueError("Unsupported committed text fields")
            if not isinstance(text["local_ref"], str) or not isinstance(text["raw_text"], str):
                raise ValueError("Malformed committed text reading")
        basis = item["cell_text_basis"]
        if (
            not isinstance(basis, dict)
            or set(basis) != {c["local_ref"] for c in item["cells"]}
            or any(
                not isinstance(value, str)
                or value not in {"NATIVE_VERIFIED", "VISUAL_REPORTED", "UNVERIFIED"}
                for value in basis.values()
            )
        ):
            raise ValueError("Malformed committed text reliability")
        for field in ("rows", "columns", "scoped_refs"):
            if not isinstance(item[field], list) or any(
                not isinstance(ref, str) for ref in item[field]
            ):
                raise ValueError("Malformed committed local references")
    if total > 512:
        raise ValueError("Committed context exceeds the cell bound")


def table_production_input(request, profile):
    from powerforge_extraction.table_runtime import require_table_supported

    require_table_supported(profile)
    stage = get_table_stage(request.stage, profile.manifest["version"])
    roles = tuple(
        role
        for role, present in (
            ("native_text", request.text is not None),
            ("analysis_image", request.image is not None),
        )
        if present
    )
    if (
        profile.provider != "openai"
        or profile.execution_kind != "TABLE_EXTRACTION"
        or request.response_model is not stage.response_model
        or request.schema_version != stage.schema_version
        or request.instructions != stage.render_instructions().text
        or request.source_roles != roles
        or not roles
        or request.model != profile.model
        or request.timeout_seconds != profile.timeout_seconds
        or request.max_output_tokens != profile.max_output_tokens
        or request.image_detail != profile.image_detail
        or (request.image is not None and request.image_mime_type != "image/png")
        or (profile.input_strategy == "NATIVE_TEXT_ONLY" and roles != ("native_text",))
        or ((request.stage == "TABLE_INTERPRETATION") != (request.upstream_context is not None))
    ):
        raise ValueError("Request differs from its table profile")
    text_bytes, image_bytes = len((request.text or "").encode()), len(request.image or b"")
    if (
        max(text_bytes, image_bytes) > profile.max_input_bytes
        or text_bytes + image_bytes > profile.max_total_input_bytes
        or len(request.text or "") > profile.max_text_chars
        or len(request.instructions.encode()) > profile.max_instruction_bytes
        or len((request.upstream_context or "").encode()) > profile.max_upstream_bytes
    ):
        raise ValueError("Request exceeds its table bounds")
    contract, content = table_input_contract(), []
    if request.text is not None:
        content.append(
            {
                "type": "input_text",
                "text": canonical_json(
                    {
                        "schema_version": contract["source_envelope_version"],
                        "untrusted": True,
                        "source_ref": contract["native_source_ref"],
                        "text": request.text,
                    }
                ),
            }
        )
    if request.image is not None:
        content.extend(
            [
                {"type": "input_text", "text": contract["image_label"]},
                {
                    "type": "input_image",
                    "detail": request.image_detail,
                    "image_url": "data:image/png;base64,"
                    + base64.b64encode(request.image).decode(),
                },
            ]
        )
    messages = [{"role": "user", "content": content}]
    if request.upstream_context is not None:
        context = json.loads(request.upstream_context)
        validate_projection(context)
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": canonical_json(
                            {
                                "schema_version": contract["upstream_envelope_version"],
                                "untrusted": True,
                                "observations": context,
                            }
                        ),
                    }
                ],
            }
        )
    return messages
