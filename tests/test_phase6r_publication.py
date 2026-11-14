"""Candidate semantics and localization using immutable native source fixtures."""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from powerforge_document_processing.layout_readings import selected_readings
from powerforge_engineering_model.enums import EquipmentType
from powerforge_extraction.phase6r_contracts import (
    ReadingCitation,
    RegistryAssertion,
)
from powerforge_extraction.phase6r_evidence import EvidenceLocalizer
from powerforge_extraction.phase6r_publication import build_publication
from spatial_layout_support import alter_body, derive, drawn_table, prepare_pdf, sources


def fixture_source(output):
    layout, _ = derive(output)
    geometry, text = sources(output)
    _, bodies = selected_readings(output.manifest, geometry, text)
    return SimpleNamespace(layout=layout, text=text, bodies=bodies)


@pytest.fixture
def pinned_source():
    return fixture_source(
        prepare_pdf(
            drawn_table(
                rows=[("Equipment", "Secondary (V)"), ("TX-1", "600"), ("TX-2", "600")],
                nearby=True,
            )
        )
    )


def cite(source, text, role="VALUE", occurrence=0, quote=None):
    tokens = {alias: {t.ref: t.raw_text for t in b.tokens} for alias, b in source.bodies.items()}
    matched = [
        r.ref
        for r in source.layout.readings
        if tokens[r.preferred.representation_ref][r.preferred.ref] == text
    ]
    return ReadingCitation(kind="READING", role=role, reading_ref=matched[occurrence], quote=quote)


def test_grounding_repeated_quotes_and_distinct_fragments(pinned_source):
    from powerforge_extraction.phase6r_contracts import QuoteCitation

    locator = EvidenceLocalizer(pinned_source)
    own_label, header, first, second = locator.locate(
        [
            cite(pinned_source, "TX-1", "LABEL"),
            cite(pinned_source, "(V)", "HEADER"),
            cite(pinned_source, "600"),
            cite(pinned_source, "600", occurrence=1),
        ],
        "VALUE",
    )
    assert [f["quote"] for f in (own_label, header, first, second)] == ["TX-1", "(V)", "600", "600"]
    assert len({f["start"] for f in (own_label, header, first, second)}) == 4
    assert first["regions"] != second["regions"]
    assert all(len(f["regions"]) == 1 for f in (own_label, header, first, second))
    ambiguous, invented, verified, foreign, substring = locator.locate(
        [
            QuoteCitation(kind="QUOTE", role="VALUE", quote="600"),
            QuoteCitation(kind="QUOTE", role="CONTEXT", quote="TX-1 (V) 600"),
            QuoteCitation(kind="QUOTE", role="LABEL", quote="Transformer Schedule"),
            ReadingCitation(kind="READING", role="VALUE", reading_ref="foreign", quote="TX-1"),
            cite(pinned_source, "TX-1", quote="TX"),
        ],
        "VALUE",
    )
    assert ambiguous["reason_code"] == "AMBIGUOUS_QUOTE"
    assert invented["reason_code"] == "QUOTE_MISMATCH"
    assert verified["quote"] == "Transformer Schedule" and len(verified["regions"]) == 2
    assert foreign["reason_code"] == "UNKNOWN_READING"
    assert substring["quote"] == "TX" and substring["regions"] == []


def test_missing_geometry_and_approximate_region():
    from powerforge_extraction.phase6r_contracts import VisualCitation

    output = prepare_pdf(drawn_table())

    def missing(body):
        tokens = tuple(
            token.model_copy(update={"source_box": None, "geometry_unavailable_reason": "fixture"})
            if token.raw_text == "TX-1"
            else token
            for token in body.tokens
        )
        return body.model_copy(update={"tokens": tokens})

    source = fixture_source(alter_body(output, "native", missing))
    region = {"x": "0.123456789012345678", "y": 0, "width": "0.5", "height": "0.2"}
    good = VisualCitation(kind="VISUAL", role="CONTEXT", region=region, reported_text="Model text")
    bad = VisualCitation(
        kind="VISUAL", role="CONTEXT", region={**region, "width": 1}, reported_text=None
    )
    resolved, visual, invalid = EvidenceLocalizer(source).locate(
        [cite(source, "TX-1"), good, bad], "VALUE"
    )
    assert resolved["localization"] == "RESOLVED" and resolved["regions"] == []
    assert "MISSING_GEOMETRY" in resolved["source_issues"]
    assert visual["localization"] == "VISUAL_REPORTED"
    assert visual["region"]["x"] == region["x"] and "text_artifact_id" not in visual
    assert invalid == {
        "role": "CONTEXT",
        "localization": "UNRESOLVED",
        "reason_code": "INVALID_VISUAL_REGION",
    }


def test_reading_members_report_native_ocr_disagreement(pinned_source):
    from uuid import uuid4

    from powerforge_extraction.phase6r_contracts import QuoteCitation
    from powerforge_provenance.spatial_layout import SourceSupport

    reading = next(
        r for r in pinned_source.layout.readings if r.ref == cite(pinned_source, "600").reading_ref
    )
    native = pinned_source.bodies["native"]
    token = next(t for t in native.tokens if t.ref == reading.preferred.ref)
    ocr_token = token.model_copy(update={"raw_text": "G00"})
    # Simulate an already admitted alternate member with a different transcription.
    ocr = SimpleNamespace(
        tokens=(ocr_token,),
        producer=SimpleNamespace(kind="OCR"),
        text_artifact=SimpleNamespace(id=uuid4()),
        transform=native.transform,
    )
    alternate = SourceSupport(representation_ref="ocr", kind="TOKEN", ref=token.ref)
    pinned_source.layout = pinned_source.layout.model_copy(
        update={
            "readings": (
                reading.model_copy(
                    update={
                        "members": (reading.preferred, alternate),
                        "issues": ("TRANSCRIPTION_CONFLICT",),
                    }
                ),
            )
        }
    )
    pinned_source.bodies = {**pinned_source.bodies, "ocr": ocr}
    pinned_source.text = {
        **pinned_source.text,
        "ocr": (" " * token.span.start + "G00").encode(),
    }
    locator = EvidenceLocalizer(pinned_source)
    different, preferred = locator.locate(
        [
            ReadingCitation(kind="READING", role="VALUE", reading_ref=reading.ref, quote="G00"),
            ReadingCitation(kind="READING", role="VALUE", reading_ref=reading.ref, quote=None),
        ],
        "VALUE",
    )
    assert (different["modality"], different["quote"]) == ("OCR", "G00")
    assert (preferred["modality"], preferred["quote"]) == ("NATIVE_PDF", "600")
    assert different["source_issues"] == preferred["source_issues"] == ["TRANSCRIPTION_CONFLICT"]
    # A quote without an occurrence reference cannot choose among representations.
    pinned_source.text["ocr"] = (" " * token.span.start + "TX-1").encode()
    (ambiguous,) = EvidenceLocalizer(pinned_source).locate(
        [QuoteCitation(kind="QUOTE", role="VALUE", quote="TX-1")], "VALUE"
    )
    assert ambiguous["reason_code"] == "AMBIGUOUS_QUOTE"


def test_quote_and_reading_bounds_and_whitespace(pinned_source, monkeypatch):
    from powerforge_extraction import phase6r_evidence
    from powerforge_extraction.phase6r_contracts import QuoteCitation

    assert phase6r_evidence._reading_matches("µ\t  600", "µ 600") == ((0, 7),)
    assert len(phase6r_evidence._reading_matches("600   A\t600 A", "600 A")) == 2
    monkeypatch.setattr(phase6r_evidence, "MAX_QUOTE_SCOPE_BYTES", 1)
    quote, reading = EvidenceLocalizer(pinned_source).locate(
        [
            QuoteCitation(kind="QUOTE", role="LABEL", quote="TX-1"),
            cite(pinned_source, "TX-1"),
        ],
        "VALUE",
    )
    assert quote["reason_code"] == "QUOTE_SEARCH_LIMIT"
    assert reading["quote"] == "TX-1"


@pytest.fixture
def stage_inputs(pinned_source):
    from powerforge_extraction.phase6r_contracts import (
        AttributeResponse,
        EquipmentObservation,
        RecognitionResponse,
        attribute_catalog,
        contract_hash,
    )

    def equipment(ref, type_, qualification="INSTALLED"):
        return EquipmentObservation(
            local_ref=ref,
            registry_type=type_,
            source_description=ref,
            tag_state="ABSENT",
            tag=None,
            qualification=qualification,
            raw_qualification=None,
            evidence=(),
        )

    upstream = RecognitionResponse(
        version="phase-6r-v1",
        stage="EQUIPMENT_RECOGNITION",
        page_context_hash="0" * 64,
        equipment=(
            equipment("owner", EquipmentType.TWO_WINDING_TRANSFORMER),
            equipment("legend", EquipmentType.TWO_WINDING_TRANSFORMER, "LEGEND_ONLY"),
            equipment("unknown", None),
        ),
    )
    wire = SimpleNamespace(upstream=upstream, attribute_catalog=attribute_catalog(upstream))

    def apply(*attributes, raw_unmapped=()):
        result = AttributeResponse(
            version="phase-6r-v1",
            stage="ATTRIBUTE_EXTRACTION",
            page_context_hash="0" * 64,
            upstream_hash=contract_hash(upstream),
            attributes=attributes,
            raw_unmapped=raw_unmapped,
        )
        return [part.fields for part in build_publication(wire, result, pinned_source)]

    return apply


def assertion(ref, **fields):
    return RegistryAssertion(
        **{
            "local_ref": ref,
            "equipment_ref": "owner",
            "association": "ASSERTED",
            "raw_label": "Secondary",
            "raw_value": "600",
            "raw_unit": None,
            "qualifiers": (),
            "value_form": "SINGLE",
            "evidence": (),
            "attribute_key": "secondary_voltage",
            "proposed_enum_value": None,
            **fields,
        }
    )


def test_published_units_and_qualifiers(stage_inputs, pinned_source):
    header = (cite(pinned_source, "(V)", "HEADER"), cite(pinned_source, "600"))
    other_source = (cite(pinned_source, "TX-1", "HEADER"),)
    rows = stage_inputs(
        assertion("a", evidence=header, association="UNCERTAIN"),
        assertion("b", raw_unit="V", evidence=other_source),
        assertion(
            "c",
            raw_unit="V",
            evidence=header,
            value_form="RANGE",
            raw_value="600–690",
            qualifiers=("continuous",),
        ),
        assertion("d", raw_unit="V", evidence=header, raw_value="600 / 347", value_form="MULTIPLE"),
        assertion("e", raw_unit="V", evidence=header, raw_value="NaN"),
        assertion("f", raw_unit="V", evidence=header, attribute_key="apparent_power_rating"),
        assertion("g", raw_unit="V", evidence=header, raw_value="600.1234567890123456789012345"),
        assertion("h", raw_unit="kV", evidence=header),
        assertion("i", raw_unit="V", evidence=header, raw_value="601"),
    )
    first, missing, qualified, multiple, malformed, wrong_key, exact, disputed, conflicting = rows
    assert first["value_number"] == Decimal("0.6") and first["raw_unit"] is None
    assert first["normalized_unit"] == "kV" and first["association"] == "UNCERTAIN"
    assert missing["reason_code"] == disputed["reason_code"] == "UNIT_MISSING_OR_AMBIGUOUS"
    assert qualified["qualifiers"] == ["continuous"] and qualified["raw_value"] == "600–690"
    assert qualified["reason_code"] == multiple["reason_code"] == "UNREPRESENTABLE_VALUE_FORM"
    assert malformed["reason_code"] == "INVALID_VALUE"
    assert wrong_key["reason_code"] == "UNKNOWN_ATTRIBUTE_KEY"
    assert exact["value_number"] == Decimal("0.6001234567890123456789012345")
    assert first["conflict"] and exact["conflict"] and conflicting["conflict"]


def test_units_match_label_or_value_without_guessing_unsupported_spellings():
    from powerforge_extraction.phase6r_contracts import AttributeDefinitionView
    from powerforge_extraction.phase6r_publication import _value

    definition = AttributeDefinitionView(
        equipment_type=EquipmentType.TWO_WINDING_TRANSFORMER,
        key="secondary_voltage",
        name="Secondary voltage",
        value_type="NUMBER",
        canonical_unit="kV",
        supported_units=("V", "kV", "MV"),
        allowed_values=(),
        notes=None,
    )

    def resolved(role, quote):
        return {"localization": "RESOLVED", "role": role, "quote": quote}

    def apply(unit, evidence, **fields):
        return _value(assertion("a", raw_unit=unit, **fields), definition, evidence)

    assert apply("V", [resolved("LABEL", "(V):")])[2]["value_number"] == Decimal("0.6")
    assert apply(None, [resolved("LABEL", "(V):")])[1] == "UNIT_MISSING_OR_AMBIGUOUS"
    assert apply(None, [resolved("VALUE", "600V")], raw_value="600 V")[2]["value_number"] == (
        Decimal("0.6")
    )
    for fragments in (
        [resolved("HEADER", "(V / kV)")],
        [dict(resolved("UNIT", "V"), source_issues=["TRANSCRIPTION_CONFLICT"])],
        [resolved("HEADER", "(V)"), resolved("UNIT", "Volts")],
        [resolved("VALUE", "1600 V")],
        [resolved("VALUE", "1,600 V")],
        [{"localization": "VISUAL_REPORTED", "role": "UNIT", "reported_text": "V"}],
    ):
        assert apply("V", fragments)[1] == "UNIT_MISSING_OR_AMBIGUOUS"
    assert apply("Volts", [resolved("UNIT", "Volts")])[1] == "INVALID_UNIT"
    assert apply("A", [resolved("UNIT", "A")])[1] == "INVALID_UNIT"
    assert apply("Ω", [resolved("UNIT", "Ω/km")])[1] == "UNIT_MISSING_OR_AMBIGUOUS"


def test_owner_and_enum_are_independent_of_evidence(stage_inputs):
    from powerforge_extraction.phase6r_contracts import RawUnmappedAssertion

    common = {"attribute_key": "primary_connection", "raw_value": "Star"}
    rows = stage_inputs(
        assertion("a", **common, proposed_enum_value="WYE"),
        assertion("b", **common, proposed_enum_value="Star"),
        assertion("c", **common),
        assertion("d", **common, equipment_ref="absent", proposed_enum_value="WYE"),
        assertion("e", **common, equipment_ref="legend", proposed_enum_value="WYE"),
        assertion("f", **common, equipment_ref="unknown", proposed_enum_value="WYE"),
        assertion("g", **common, association="UNASSIGNED", proposed_enum_value="WYE"),
        raw_unmapped=(
            RawUnmappedAssertion(
                local_ref="h",
                equipment_ref="owner",
                association="ASSERTED",
                raw_label="Noise",
                raw_value="45 to 50",
                raw_unit="dB",
                qualifiers=(),
                value_form="RANGE",
                evidence=(),
            ),
        ),
    )
    assert rows[0]["value_text"] == "WYE" and rows[0]["raw_value"] == "Star"
    assert rows[1]["proposed_enum_value"] == "Star"
    assert all(row["reason_code"] == "INVALID_VALUE" for row in rows[1:3])
    assert all(
        row["reason_code"] == "UNASSIGNED_OWNER"
        and row["association"] == "UNASSIGNED"
        and row["owner_ref"] is None
        and row["claimed_owner_ref"]
        for row in rows[3:7]
    )
    assert rows[7]["reason_code"] == "UNSUPPORTED_ATTRIBUTE" and rows[7]["owner_ref"] == "owner"


def test_boolean_and_integer_lexical_policy():
    from powerforge_extraction.phase6r_contracts import (
        EquipmentObservation,
        RecognitionResponse,
        attribute_catalog,
    )
    from powerforge_extraction.phase6r_publication import _value

    sample = RecognitionResponse(
        version="phase-6r-v1",
        stage="EQUIPMENT_RECOGNITION",
        page_context_hash="0" * 64,
        equipment=tuple(
            EquipmentObservation(
                local_ref=item.value,
                registry_type=item,
                source_description=item.value,
                tag_state="ABSENT",
                tag=None,
                qualification="UNKNOWN",
                raw_qualification=None,
                evidence=(),
            )
            for item in EquipmentType
        ),
    )
    definitions = attribute_catalog(sample)
    boolean = next(d for d in definitions if d.value_type == "BOOLEAN")
    integer = next(d for d in definitions if d.value_type == "INTEGER" and d.canonical_unit is None)
    assert _value(assertion("a", raw_value="  YeS "), boolean, [])[2]["value_boolean"] is True
    assert _value(assertion("b", raw_value="available"), boolean, [])[1] == "INVALID_VALUE"
    assert (
        _value(assertion("c", raw_value=str(2**63 - 1)), integer, [])[2]["value_integer"]
        == 2**63 - 1
    )
    for raw in (str(2**63), "1.2", "1e1000000"):
        assert _value(assertion("d", raw_value=raw), integer, [])[1] == "INVALID_VALUE"
