"""Candidate semantics and localization using immutable native source fixtures."""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from powerforge_document_processing.layout_readings import selected_readings
from powerforge_engineering_model.enums import EquipmentType
from powerforge_extraction.evidence_localization import EvidenceLocalizer
from powerforge_extraction.publication import build_publication
from powerforge_extraction.stage_contracts import (
    ReadingCitation,
    RegistryAssertion,
)
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
    from powerforge_extraction.stage_contracts import QuoteCitation

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
    from powerforge_extraction.stage_contracts import VisualCitation

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

    from powerforge_extraction.stage_contracts import QuoteCitation
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
    from powerforge_extraction import evidence_localization
    from powerforge_extraction.stage_contracts import QuoteCitation

    assert evidence_localization._reading_matches("µ\t  600", "µ 600") == ((0, 7),)
    assert len(evidence_localization._reading_matches("600   A\t600 A", "600 A")) == 2
    monkeypatch.setattr(evidence_localization, "MAX_QUOTE_SCOPE_BYTES", 1)
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
    from powerforge_extraction.stage_contracts import (
        ATTRIBUTE_VERSION,
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
            version=ATTRIBUTE_VERSION,
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
            "origin": "EXTRACTED",
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
    assert first["value_source_support"] == "TEXT_MATCH"
    assert conflicting["mapping_status"] == "MAPPED" and conflicting["raw_value"] == "601"
    assert conflicting["value_number"] == Decimal("0.601")
    assert conflicting["value_source_support"] == "TEXT_MISMATCH"
    assert missing["reason_code"] == disputed["reason_code"] == "UNIT_MISSING_OR_AMBIGUOUS"
    assert disputed["value_source_support"] == "TEXT_MATCH"
    assert qualified["qualifiers"] == ["continuous"] and qualified["raw_value"] == "600–690"
    assert qualified["reason_code"] == multiple["reason_code"] == "UNREPRESENTABLE_VALUE_FORM"
    assert qualified["value_source_support"] == multiple["value_source_support"] == "UNVERIFIED"
    assert malformed["reason_code"] == "INVALID_VALUE"
    assert wrong_key["reason_code"] == "UNKNOWN_ATTRIBUTE_KEY"
    assert exact["value_number"] == Decimal("0.6001234567890123456789012345")
    assert first["conflict"] and exact["conflict"] and conflicting["conflict"]


def test_value_support_uses_cited_occurrences(stage_inputs, pinned_source):
    from powerforge_extraction.stage_contracts import QuoteCitation, VisualCitation

    first = cite(pinned_source, "600")
    second = cite(pinned_source, "600", occurrence=1)
    repeated = QuoteCitation(kind="QUOTE", role="VALUE", quote="600")
    visual = VisualCitation(
        kind="VISUAL",
        role="VALUE",
        region={"x": 0, "y": 0, "width": "0.25", "height": "0.25"},
        reported_text="600",
    )
    cases = (
        ("600", (), "UNVERIFIED"),
        ("600", (visual,), "UNVERIFIED"),
        ("600", (repeated,), "UNVERIFIED"),
        ("600", (first, repeated), "TEXT_MATCH"),
        (" 600 ", (first, second), "TEXT_MATCH"),
        ("601", (first, second), "TEXT_MISMATCH"),
        ("601", (first, visual), "UNVERIFIED"),
        ("600", (first, cite(pinned_source, "999")), "UNVERIFIED"),
        ("601", (first, cite(pinned_source, "999")), "UNVERIFIED"),
        ("600.0", (first,), "UNVERIFIED"),
        ("601 V", (first,), "UNVERIFIED"),
        ("60", (cite(pinned_source, "600", quote="60"),), "UNVERIFIED"),
        ("60", (QuoteCitation(kind="QUOTE", role="VALUE", quote="99"),), "UNVERIFIED"),
        ("999", (QuoteCitation(kind="QUOTE", role="VALUE", quote="999"),), "TEXT_MATCH"),
        ("600", (cite(pinned_source, "600", role="HEADER"),), "UNVERIFIED"),
    )
    rows = stage_inputs(
        *(
            assertion(f"v{index}", raw_value=raw, evidence=evidence)
            for index, (raw, evidence, _) in enumerate(cases)
        )
    )
    assert [row["value_source_support"] for row in rows] == [case[2] for case in cases]
    assert [row["raw_value"] for row in rows] == [case[0] for case in cases]


def test_value_support_defers_to_transcription_conflicts(stage_inputs, pinned_source):
    from powerforge_extraction.stage_contracts import QuoteCitation

    reading = cite(pinned_source, "999")
    pinned_source.layout = pinned_source.layout.model_copy(
        update={
            "readings": tuple(
                item.model_copy(update={"issues": ("TRANSCRIPTION_CONFLICT",)})
                if item.ref == reading.reading_ref
                else item
                for item in pinned_source.layout.readings
            ),
        }
    )
    quote = QuoteCitation(kind="QUOTE", role="VALUE", quote="999")
    cases = ((reading,), (quote,), (reading, quote))
    for index, evidence in enumerate(cases):
        rows = stage_inputs(
            assertion(f"match{index}", raw_value="999", evidence=evidence),
            assertion(f"differ{index}", raw_value="998", evidence=evidence),
        )
        assert [row["value_source_support"] for row in rows] == ["UNVERIFIED", "UNVERIFIED"]


def test_units_match_label_or_value_without_guessing_unsupported_spellings():
    from powerforge_extraction.publication import _value
    from powerforge_extraction.stage_contracts import AttributeDefinitionView

    definition = AttributeDefinitionView(
        equipment_type=EquipmentType.TWO_WINDING_TRANSFORMER,
        key="secondary_voltage",
        name="Secondary voltage",
        required=False,
        value_type="NUMBER",
        canonical_unit="kV",
        supported_units=("V", "kV", "MV"),
        allowed_values=(),
        notes=None,
        extraction_guidance=None,
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
    from powerforge_extraction.stage_contracts import RawUnmappedAssertion

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
                display_label=None,
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
    from powerforge_extraction.publication import _value
    from powerforge_extraction.stage_contracts import (
        EquipmentObservation,
        RecognitionResponse,
        attribute_catalog,
    )

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


def test_siemens_style_inline_models_and_reviewable_inference():
    from powerforge_extraction.stage_contracts import (
        ATTRIBUTE_VERSION,
        VERSION,
        AttributeResponse,
        EquipmentObservation,
        InferredAssertion,
        RecognitionResponse,
        attribute_catalog,
        contract_hash,
    )

    models = ("CMD6", "CJD6", "CND6", "WL")
    source = fixture_source(
        prepare_pdf(
            drawn_table(
                rows=[
                    ("Device", "Description"),
                    *[(model, "3 Pole") for model in models],
                    ("Trip Unit", "ETU745"),
                ]
            )
        )
    )
    upstream = RecognitionResponse(
        version=VERSION,
        stage="EQUIPMENT_RECOGNITION",
        page_context_hash="0" * 64,
        equipment=tuple(
            EquipmentObservation(
                local_ref=model,
                source_description=model,
                registry_type=EquipmentType.LV_BREAKER,
                tag_state="ABSENT",
                tag=None,
                qualification="INSTALLED",
                raw_qualification=None,
                evidence=(),
            )
            for model in models
        ),
    )

    def infer(ref, owner="WL", value="ELECTRONIC", evidence=()):
        return InferredAssertion(
            local_ref=ref,
            origin="INFERRED",
            equipment_ref=owner,
            association="ASSERTED",
            attribute_key="trip_unit_type",
            proposed_value=value,
            proposed_unit=None,
            inference_explanation="The fixture uses ETU745 to propose an electronic trip.",
            inference_basis="EQUIPMENT_CHARACTERISTICS",
            source_expression=None,
            evidence=evidence,
        )

    result = AttributeResponse(
        version=ATTRIBUTE_VERSION,
        stage="ATTRIBUTE_EXTRACTION",
        page_context_hash=upstream.page_context_hash,
        upstream_hash=contract_hash(upstream),
        attributes=(
            *(
                assertion(
                    f"{model}-model",
                    attribute_key="model",
                    equipment_ref=model,
                    raw_label=None,
                    raw_value=model,
                    evidence=(cite(source, model),),
                )
                for model in models
            ),
            assertion(
                "trip-model",
                attribute_key="trip_unit_model",
                equipment_ref="WL",
                raw_label="Trip Unit",
                raw_value="ETU745",
                evidence=(cite(source, "ETU745"),),
            ),
            infer("proposal"),
            infer("context", evidence=(cite(source, "ETU745", role="CONTEXT"),)),
            infer("mislabelled-citation", evidence=(cite(source, "ETU745"),)),
            infer("unsupported-enum", value="Solid state"),
            infer("foreign-owner", owner="foreign"),
        ),
        raw_unmapped=(),
    )
    wire = SimpleNamespace(upstream=upstream, attribute_catalog=attribute_catalog(upstream))
    observations = build_publication(wire, result, source)
    *direct, inferred, contextual, mislabelled, invalid, foreign = observations
    assert len(direct) == 5
    assert all(d.fields["attribute_origin"] == "EXTRACTED" for d in direct)
    assert all(d.fields["value_source_support"] == "TEXT_MATCH" for d in direct)
    assert [d.fields["value_text"] for d in direct] == [*models, "ETU745"]
    assert all(d.fields["raw_label"] is None for d in direct[:-1])
    assert inferred.fields["attribute_origin"] == "INFERRED"
    assert inferred.fields["value_text"] == "ELECTRONIC" and not inferred.evidence
    assert (
        "raw_value" not in inferred.fields
        and inferred.fields["value_source_support"] == "UNVERIFIED"
    )
    assert contextual.evidence[0]["localization"] == "RESOLVED"
    assert contextual.fields["value_source_support"] == "UNVERIFIED"
    assert mislabelled.fields["mapping_status"] == "MAPPED"
    assert mislabelled.fields["value_source_support"] == "UNVERIFIED"
    assert mislabelled.evidence == [
        {
            "role": "VALUE",
            "localization": "UNRESOLVED",
            "reason_code": "INFERRED_VALUE_CITATION",
        }
    ]
    assert invalid.fields["mapping_status"] == "INVALID"
    assert invalid.fields["proposed_value"] == "Solid state"
    assert foreign.fields["mapping_status"] == "UNMAPPED" and foreign.fields["owner_ref"] is None
    assert foreign.issues == ("INVALID_OWNER_REFERENCE",)
    # Branch trip-unit types are left absent in the fixture, with no default filled.
    assert not any(
        d.fields.get("proposed_attribute_key") == "trip_unit_type"
        and d.fields["owner_ref"] in models[:3]
        for d in observations
    )


@pytest.mark.parametrize(
    "source_value,raw_value,reported_unit,expected",
    [
        ("SC=65KA", "65KA", "kA", "MAPPED"),
        ("65 kA", "65", "kA", "MAPPED"),
        ("65KA", "65KA", "KA", "MAPPED"),
        ("65 KA", "65 KA", "KA", "MAPPED"),
        ("65Ka", "65Ka", "kA", "UNMAPPED"),
        ("65ka", "65ka", "kA", "UNMAPPED"),
        ("65mA", "65mA", "kA", "UNMAPPED"),
        ("65MA", "65MA", "kA", "UNMAPPED"),
        ("65KA/m", "65", "kA", "UNMAPPED"),
        ("65KA 65mA", "65", "kA", "UNMAPPED"),
    ],
)
def test_explicit_source_unit_notation_preserves_si_distinctions(
    source_value, raw_value, reported_unit, expected
):
    from powerforge_extraction.publication import _value
    from powerforge_extraction.stage_contracts import AttributeDefinitionView

    definition = AttributeDefinitionView(
        equipment_type=EquipmentType.BUS,
        key="short_circuit_current_rating",
        name="Short-Circuit Current Rating (kA)",
        required=True,
        value_type="NUMBER",
        canonical_unit="kA",
        supported_units=("A", "kA"),
        allowed_values=(),
        notes=None,
        extraction_guidance=None,
    )
    item = assertion(
        "rating", attribute_key=definition.key, raw_value=raw_value, raw_unit=reported_unit
    )
    evidence = [dict(role="VALUE", localization="RESOLVED", quote=source_value)]
    status, _, normalized = _value(item, definition, evidence)
    assert status == expected
    assert item.raw_value == raw_value and item.raw_unit == reported_unit
    if expected == "MAPPED":
        assert normalized["value_number"] == Decimal("65")
        assert normalized["normalized_unit"] == "kA"
    assert (
        _value(item, definition, [dict(evidence[0], source_issues=["TRANSCRIPTION_CONFLICT"])])[0]
        == "UNMAPPED"
    )


def test_equipment_identifier_can_support_its_literal_attribute_value(stage_inputs, pinned_source):
    # A model can use the very same source token as the equipment description.
    rows = stage_inputs(
        assertion(
            "identifier",
            attribute_key="model",
            raw_value="TX-1",
            evidence=(cite(pinned_source, "TX-1", role="EQUIPMENT"),),
        ),
        assertion(
            "manufacturer",
            attribute_key="manufacturer",
            raw_value="TX-1",
            evidence=(cite(pinned_source, "TX-1", role="EQUIPMENT"),),
        ),
        assertion("uncited", attribute_key="model", raw_value="TX-1"),
        assertion(
            "wrong",
            attribute_key="model",
            raw_value="TX-2",
            evidence=(cite(pinned_source, "TX-1", role="EQUIPMENT"),),
        ),
    )
    assert [r["value_source_support"] for r in rows] == [
        "TEXT_MATCH",
        "UNVERIFIED",
        "UNVERIFIED",
        "UNVERIFIED",
    ]


def test_genuine_qualifiers_and_combined_values_stay_unmapped(stage_inputs):
    from powerforge_extraction.publication import _value
    from powerforge_extraction.stage_contracts import AttributeDefinitionView

    definition = AttributeDefinitionView(
        equipment_type=EquipmentType.BUS,
        key="phase_count",
        name="Phase Count",
        required=False,
        value_type="INTEGER",
        canonical_unit=None,
        supported_units=(),
        allowed_values=(),
        notes=None,
        extraction_guidance=None,
    )
    assert (
        _value(assertion("phases", attribute_key="phase_count", raw_value="3"), definition, [])[2][
            "value_integer"
        ]
        == 3
    )
    assert (
        _value(
            assertion(
                "qualified-phases", attribute_key="phase_count", raw_value="3", qualifiers=("3PH",)
            ),
            definition,
            [],
        )[1]
        == "UNREPRESENTABLE_VALUE_FORM"
    )
    rows = stage_inputs(
        assertion("model", attribute_key="model", raw_value="MODEL-X", qualifiers=("LSIG",)),
        assertion("voltage", raw_value="347/600V", raw_unit="V", value_form="MULTIPLE"),
    )
    assert rows[0]["reason_code"] == "UNREPRESENTABLE_VALUE_FORM"
    assert rows[1]["mapping_status"] == "UNMAPPED"
    assert rows[1]["raw_value"] == "347/600V"


def test_corrected_semantic_fixture_preserves_source_facts_and_inference():
    """Publication of a reviewed response fixture, without simulating AI reasoning."""
    from powerforge_extraction.stage_contracts import (
        ATTRIBUTE_VERSION,
        VERSION,
        AttributeResponse,
        EquipmentObservation,
        InferredAssertion,
        RawUnmappedAssertion,
        RecognitionResponse,
        attribute_catalog,
        contract_hash,
    )

    source = fixture_source(
        prepare_pdf(
            drawn_table(
                rows=[
                    ("Trip Unit", "ETU745"),
                    ("Functions", "LSIG"),
                    ("Short circuit", "SC=65KA"),
                    ("Bus Bracing", "65KA"),
                    ("Phase notation", "3PH"),
                    ("Voltage", "347/600V"),
                    ("Standard / Branch device", "UL489 600A"),
                ]
            )
        )
    )
    upstream = RecognitionResponse(
        version=VERSION,
        stage="EQUIPMENT_RECOGNITION",
        page_context_hash="0" * 64,
        equipment=tuple(
            EquipmentObservation(
                local_ref=ref,
                source_description="Synthetic assembly" if ref == "bus" else "Synthetic breaker",
                registry_type=kind,
                tag_state="PRESENT" if ref == "bus" else "ABSENT",
                tag="BOARD-1" if ref == "bus" else None,
                qualification="INSTALLED",
                raw_qualification=None,
                evidence=(),
            )
            for ref, kind in (("breaker", EquipmentType.LV_BREAKER), ("bus", EquipmentType.BUS))
        ),
    )
    trip = assertion(
        "model",
        equipment_ref="breaker",
        attribute_key="trip_unit_model",
        raw_value="ETU745",
        evidence=(cite(source, "ETU745"),),
    )

    def inferred(ref, owner, key, value, explanation, unit=None, expression=None):
        return InferredAssertion(
            origin="INFERRED",
            local_ref=ref,
            equipment_ref=owner,
            association="ASSERTED",
            attribute_key=key,
            proposed_value=value,
            proposed_unit=unit,
            inference_explanation=explanation,
            inference_basis="DOCUMENT_CONTEXT",
            source_expression=expression,
            evidence=(),
        )

    raw = tuple(
        RawUnmappedAssertion(
            local_ref=ref,
            equipment_ref=owner,
            association="ASSERTED",
            raw_label=label,
            display_label=display,
            raw_value=value,
            raw_unit=unit,
            qualifiers=(),
            value_form="SINGLE",
            evidence=(cite(source, value),),
        )
        for ref, owner, label, display, value, unit in (
            ("functions", "breaker", "Functions", "Protection Functions", "LSIG", None),
            ("bracing", "bus", "Bus Bracing", "Bus Bracing", "65KA", "KA"),
            ("standard", "breaker", "Standard", "Product Standard", "UL489", None),
            ("current", "breaker", "Branch device", "Current Rating (Unspecified)", "600A", "A"),
        )
    )
    attributes = (
        trip,
        inferred(
            "technology",
            "breaker",
            "trip_unit_type",
            "ELECTRONIC",
            "The identified trip-unit model supports the technology proposal.",
        ),
        assertion(
            "sccr",
            equipment_ref="bus",
            attribute_key="short_circuit_current_rating",
            raw_value="65KA",
            raw_unit="KA",
            evidence=(cite(source, "SC=65KA"),),
        ),
        assertion(
            "phases",
            equipment_ref="bus",
            attribute_key="phase_count",
            raw_value="3",
            evidence=(cite(source, "3PH"),),
        ),
        inferred(
            "voltage",
            "bus",
            "nominal_voltage",
            "600",
            "The combined phase-neutral/line-line expression identifies the line-line voltage.",
            "V",
            "347/600V",
        ),
        inferred(
            "manufacturer",
            "breaker",
            "manufacturer",
            "Example Manufacturer",
            "The synthetic product identification supports this manufacturer proposal.",
        ),
    )
    response = AttributeResponse(
        version=ATTRIBUTE_VERSION,
        stage="ATTRIBUTE_EXTRACTION",
        page_context_hash="0" * 64,
        upstream_hash=contract_hash(upstream),
        attributes=attributes,
        raw_unmapped=raw,
    )
    wire = SimpleNamespace(upstream=upstream, attribute_catalog=attribute_catalog(upstream))
    observations = build_publication(wire, response, source)
    rows = {o.fields["local_ref"]: o.fields for o in observations}
    assert rows["model"]["value_text"] == "ETU745"
    assert rows["technology"]["value_text"] == "ELECTRONIC"
    assert rows["technology"]["attribute_origin"] == "INFERRED"
    assert rows["sccr"]["value_number"] == Decimal("65")
    assert rows["sccr"]["raw_value"] == "65KA" and rows["sccr"]["raw_unit"] == "KA"
    assert rows["phases"]["value_integer"] == 3 and not rows["phases"]["qualifiers"]
    assert rows["voltage"]["value_number"] == Decimal("0.6")
    assert attributes[4].source_expression == "347/600V"
    assert rows["manufacturer"]["attribute_origin"] == "INFERRED"
    assert all(
        rows[ref]["value_source_support"] == "UNVERIFIED"
        for ref in ("technology", "voltage", "manufacturer")
    )
    assert all(
        rows[ref]["mapping_status"] == "UNMAPPED"
        for ref in ("functions", "bracing", "standard", "current")
    )
    assert not any(
        o.fields.get("proposed_attribute_key") == "short_time_withstand_current"
        for o in observations
    )
