"""Conservative mapping and precise, source-grounded contracts."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from powerforge_api.main import app
from powerforge_extraction.contracts import (
    AICallInput,
    CandidateInput,
    EvidenceInput,
    TableCell,
    TableLayout,
)
from powerforge_extraction.enums import CandidateKind, MappingStatus
from powerforge_provenance.locations import Region, SourceLocation


def attribute(**changes):
    return CandidateInput(
        kind="ATTRIBUTE_VALUE",
        mapping_status="MAPPED",
        raw_text="750 kVA",
        equipment_type_key="TWO_WINDING_TRANSFORMER",
        attribute_key="rated_apparent_power",
        value_type="NUMBER",
        numeric_value="750.12345678901234567890123456789",
        unit="kVA",
        **changes,
    )


def test_exact_decimal_tagless_optional_context_and_boolean_false():
    c = attribute()
    assert c.source_group_id is None and c.equipment_mention_candidate_id is None
    assert c.model_dump(mode="json")["numeric_value"] == "750.12345678901234567890123456789"
    boolean = CandidateInput(
        kind="ATTRIBUTE_VALUE",
        mapping_status="MAPPED",
        raw_text="No bypass",
        equipment_type_key="UPS",
        attribute_key="static_bypass_available",
        value_type="BOOLEAN",
        boolean_value=False,
    )
    assert boolean.model_dump(mode="json")["boolean_value"] is False
    integer = CandidateInput(
        kind="ATTRIBUTE_VALUE",
        mapping_status="MAPPED",
        raw_text="9007199254740993",
        equipment_type_key="CABLE",
        attribute_key="parallel_run_count",
        value_type="INTEGER",
        integer_value=9007199254740993,
    )
    assert integer.model_dump(mode="json")["integer_value"] == "9007199254740993"


@pytest.mark.parametrize(
    "changes",
    [
        dict(numeric_value=1.1),
        dict(numeric_value="NaN"),
        dict(numeric_value="Infinity"),
        dict(numeric_value=None),
        dict(integer_value=2),
        dict(confidence="1.1"),
        dict(unit="V"),
        dict(attribute_key="made_up"),
        dict(value_type="TEXT"),
    ],
)
def test_invalid_mapping_or_precision_is_rejected(changes):
    data = attribute().model_dump()
    data.update(changes)
    with pytest.raises((ValidationError, ValueError)):
        CandidateInput.model_validate(data)


@pytest.mark.parametrize("status", list(MappingStatus)[1:])
def test_unmapped_and_invalid_preserve_original_expression(status):
    c = CandidateInput(
        kind=CandidateKind.UNMAPPED_OBSERVATION,
        mapping_status=status,
        raw_text="3Ø, source meaning uncertain",
        raw_value="3Ø",
        raw_unit="unknown",
    )
    assert c.model_dump(mode="json")["raw_value"] == "3Ø"


def test_geometry_and_offsets_are_optional_but_never_partially_fabricated():
    assert SourceLocation(document_page_id=uuid4()).region is None
    with pytest.raises(ValidationError):
        Region(x=".9", y=0, width=".2", height=1)
    with pytest.raises(ValidationError):
        EvidenceInput(
            location=SourceLocation(document_page_id=uuid4()),
            source_kind="NATIVE_TEXT",
            extraction_method="AI_TEXT",
            text_start=0,
            text_end=10,
        )


def test_table_layout_preserves_spans_and_rejects_impossible_cells():
    cell = TableCell(id="c", row=0, column=0, column_span=2, text="Transformer", is_header=True)
    table = TableLayout(rows=["header"], columns=["parameter", "value"], cells=[cell])
    assert table.model_dump()["cells"][0]["column_span"] == 2
    with pytest.raises(ValidationError):
        TableLayout(rows=["row"], columns=["one"], cells=[cell])


def test_telemetry_requires_pricing_basis_and_valid_timing():
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        AICallInput(
            provider="fake",
            model="fake",
            prompt_version="v1",
            prompt_hash="a",
            schema_version="v1",
            outcome="SUCCEEDED",
            started_at=now,
            finished_at=now,
            duration_ms=0,
            estimated_cost_usd="0.01",
        )


def test_openapi_is_read_only_and_preserves_integer_decimal_strings():
    schema = app.openapi()
    paths = {p: v for p, v in schema["paths"].items() if "/extraction" in p}
    assert len(paths) == 6
    assert all(set(v) == {"get"} for v in paths.values())
    candidate = schema["components"]["schemas"]["CandidateResponse"]["properties"]
    for field in ["integer_value", "numeric_value"]:
        assert {v["type"] for v in candidate[field]["anyOf"]} == {"string", "null"}
