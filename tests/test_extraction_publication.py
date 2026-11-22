"""Candidate semantics and localization using immutable native source fixtures."""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from powerforge_document_processing.layout_readings import selected_readings
from powerforge_engineering_model.enums import EquipmentType
from powerforge_extraction.evidence_localization import EvidenceLocalizer
from powerforge_extraction.publication import build_publication
from powerforge_extraction.stage_contracts import (
    QuoteCitation,
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
            equipment("bus", EquipmentType.BUS),
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
            "proposed_value": "600",
            "alternate_representations": (),
            "proposed_unit": None,
            **fields,
        }
    )


def test_published_units_and_qualifiers(stage_inputs, pinned_source):
    header = (cite(pinned_source, "(V)", "HEADER"), cite(pinned_source, "600"))
    other_source = (cite(pinned_source, "TX-1", "HEADER"),)
    rows = stage_inputs(
        assertion("a", raw_unit="V", proposed_unit="V", evidence=header, association="UNCERTAIN"),
        assertion("b", raw_unit="V", proposed_unit="V", evidence=other_source),
        assertion(
            "c",
            raw_unit="V",
            proposed_unit="V",
            evidence=header,
            value_form="RANGE",
            raw_value="600–690",
            proposed_value="600–690",
            qualifiers=("continuous",),
        ),
        assertion(
            "d",
            raw_unit="V",
            proposed_unit="V",
            evidence=header,
            raw_value="600 / 347",
            proposed_value="600/347",
            value_form="MULTIPLE",
        ),
        assertion(
            "e",
            raw_unit="V",
            proposed_unit="V",
            evidence=header,
            raw_value="NaN",
            proposed_value="NaN",
        ),
        assertion(
            "f",
            raw_unit="V",
            proposed_unit="V",
            evidence=header,
            attribute_key="apparent_power_rating",
        ),
        assertion(
            "g",
            raw_unit="V",
            proposed_unit="V",
            evidence=header,
            raw_value="600.1234567890123456789012345",
            proposed_value="600.1234567890123456789012345",
        ),
        assertion("h", raw_unit="kV", proposed_unit="kV", evidence=header),
        assertion(
            "i",
            raw_unit="V",
            proposed_unit="V",
            evidence=header,
            raw_value="601",
            proposed_value="601",
        ),
        assertion("j", raw_unit="V", proposed_unit="kV", evidence=header),
    )
    (
        first,
        missing,
        qualified,
        multiple,
        malformed,
        wrong_key,
        exact,
        disputed,
        conflicting,
        rejected,
    ) = rows
    assert first["value_number"] == Decimal("0.6")
    assert first["raw_unit"] == first["proposed_unit"] == "V"
    assert first["normalized_unit"] == "kV" and first["association"] == "UNCERTAIN"
    assert first["value_source_support"] == "TEXT_MATCH"
    assert conflicting["mapping_status"] == "MAPPED" and conflicting["raw_value"] == "601"
    assert conflicting["value_number"] == Decimal("0.601")
    assert conflicting["value_source_support"] == "TEXT_MISMATCH"
    assert missing["reason_code"] == disputed["reason_code"] == "UNIT_MISSING_OR_AMBIGUOUS"
    assert disputed["value_source_support"] == "TEXT_MATCH"
    assert qualified["qualifiers"] == ["continuous"] and qualified["raw_value"] == "600–690"
    assert qualified["reason_code"] == multiple["reason_code"] == "PROPOSAL_TYPE_MISMATCH"
    assert qualified["value_source_support"] == multiple["value_source_support"] == "UNVERIFIED"
    assert malformed["reason_code"] == "PROPOSAL_TYPE_MISMATCH"
    assert wrong_key["reason_code"] == "UNKNOWN_ATTRIBUTE_KEY"
    assert rejected["reason_code"] == "UNIT_INTERPRETATION_UNVERIFIED"
    assert rejected["raw_unit"] == "V" and rejected["proposed_unit"] == "kV"
    assert rejected["raw_value"] == "600" and rejected["value_source_support"] == "TEXT_MATCH"
    assert "value_number" not in rejected
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
    from powerforge_extraction.stage_contracts import AttributeDefinitionView
    from powerforge_extraction.value_proposal import normalize_proposal

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

    def apply(raw_unit, evidence, proposed_unit="V", **fields):
        observation = assertion("a", raw_unit=raw_unit, proposed_unit=proposed_unit, **fields)
        return normalize_proposal(observation, definition, evidence)

    assert apply("V", [resolved("LABEL", "(V):")])[2]["value_number"] == Decimal("0.6")
    assert apply("V", [resolved("VALUE", "600V")], raw_value="600 V")[2]["value_number"] == (
        Decimal("0.6")
    )
    assert apply("Volts", [resolved("UNIT", "Volts")])[2]["value_number"] == Decimal("0.6")
    assert apply("KV", [resolved("HEADER", "Voltage in KV")], "kV")[2]["value_number"] == (
        Decimal("600")
    )
    for fragments in (
        [resolved("HEADER", "(V / kV)")],
        [dict(resolved("UNIT", "V"), source_issues=["TRANSCRIPTION_CONFLICT"])],
        [resolved("HEADER", "(V)"), resolved("UNIT", "unreadable")],
        [resolved("HEADER", "(V)"), resolved("VALUE", "600 (mV)")],
        [resolved("HEADER", "(V)"), resolved("UNIT", "V/km")],
        [resolved("VALUE", "1600 V")],
        [resolved("VALUE", "1,600 V")],
        [{"localization": "VISUAL_REPORTED", "role": "UNIT", "reported_text": "V"}],
    ):
        assert apply("V", fragments)[1] == "UNIT_MISSING_OR_AMBIGUOUS"
    assert apply(None, [resolved("HEADER", "V")])[1] == "UNIT_MISSING_OR_AMBIGUOUS"
    assert apply("V", [resolved("HEADER", "V")], None)[1] == "UNIT_MISSING_OR_AMBIGUOUS"
    assert apply("A", [resolved("UNIT", "A")], "A")[1] == "UNIT_INTERPRETATION_UNVERIFIED"


def test_owner_and_enum_are_independent_of_evidence(stage_inputs):
    from powerforge_extraction.stage_contracts import RawUnmappedAssertion

    common = {"attribute_key": "primary_connection", "raw_value": "Star"}
    rows = stage_inputs(
        assertion("a", **common, proposed_value="WYE"),
        assertion("b", **common, proposed_value="Star"),
        assertion("c", **common, proposed_value=None),
        assertion("d", **common, equipment_ref="absent", proposed_value="WYE"),
        assertion("e", **common, equipment_ref="legend", proposed_value="WYE"),
        assertion("f", **common, equipment_ref="unknown", proposed_value="WYE"),
        assertion("g", **common, association="UNASSIGNED", proposed_value="WYE"),
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
    assert rows[1]["proposed_value"] == "Star"
    assert rows[1]["reason_code"] == "PROPOSAL_TYPE_MISMATCH"
    assert rows[2]["reason_code"] == "NO_VALUE_PROPOSAL"
    assert all(
        row["reason_code"] == "UNASSIGNED_OWNER"
        and row["association"] == "UNASSIGNED"
        and row["owner_ref"] is None
        and row["claimed_owner_ref"]
        for row in rows[3:7]
    )
    assert rows[7]["reason_code"] == "UNSUPPORTED_ATTRIBUTE" and rows[7]["owner_ref"] == "owner"


def test_boolean_and_integer_lexical_policy():
    from powerforge_extraction.stage_contracts import (
        EquipmentObservation,
        RecognitionResponse,
        attribute_catalog,
    )
    from powerforge_extraction.value_proposal import normalize_proposal

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
    assert (
        normalize_proposal(assertion("a", raw_value="  YeS ", proposed_value=True), boolean, [])[2][
            "value_boolean"
        ]
        is True
    )
    assert (
        normalize_proposal(assertion("b", raw_value="available", proposed_value=True), boolean, [])[
            1
        ]
        == "SOURCE_EXPRESSION_UNVERIFIED"
    )
    assert (
        normalize_proposal(
            assertion("c", raw_value=str(2**63 - 1), proposed_value=2**63 - 1), integer, []
        )[2]["value_integer"]
        == 2**63 - 1
    )
    for raw, proposal, reason in (
        (str(2**63), 2**63, "INVALID_VALUE"),
        ("1.2", 1, "SOURCE_VALUE_MISMATCH"),
        ("1e1000000", "1e1000000", "PROPOSAL_TYPE_MISMATCH"),
    ):
        assert (
            normalize_proposal(assertion("d", raw_value=raw, proposed_value=proposal), integer, [])[
                1
            ]
            == reason
        )


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
                    *[(model, "CMD6 3 Pole" if model == "CMD6" else "Breaker") for model in models],
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
                    proposed_value=model,
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
                proposed_value="ETU745",
                evidence=(cite(source, "ETU745"),),
            ),
            assertion(
                "inline-poles",
                attribute_key="pole_count",
                equipment_ref="CMD6",
                raw_label=None,
                raw_value="3 Pole",
                proposed_value=3,
                evidence=(QuoteCitation(kind="QUOTE", role="VALUE", quote="3 Pole"),),
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
    *direct, poles, inferred, contextual, mislabelled, invalid, foreign = observations
    assert len(direct) == 5
    assert all(d.fields["attribute_origin"] == "EXTRACTED" for d in direct)
    assert all(d.fields["value_source_support"] == "TEXT_MATCH" for d in direct)
    assert [d.fields["value_text"] for d in direct] == [*models, "ETU745"]
    assert all(d.fields["raw_label"] is None for d in direct[:-1])
    assert poles.fields["owner_ref"] == "CMD6" and poles.fields["value_integer"] == 3
    assert poles.evidence[0]["quote"] == "3 Pole"
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
    "equipment,key,source_value,raw_unit,proposed_unit,normalized",
    [
        ("BUS", "short_circuit_current_rating", "65KA", "KA", "kA", "65"),
        ("BUS", "short_circuit_current_rating", "65kA 65KA", "KA", "kA", "65"),
        ("BUS", "short_circuit_current_rating", "65kiloamps", "kiloamps", "kA", "65"),
        ("BUS", "short_circuit_current_rating", "65A", "A", "A", "0.065"),
        ("BUS", "nominal_voltage", "65KV", "KV", "kV", "65"),
        ("BUS", "nominal_voltage", "65volts", "volts", "V", "0.065"),
        ("BUS", "nominal_voltage", "65MV", "MV", "MV", "65000"),
        ("BUS", "short_time_withstand_duration", "65msec", "msec", "ms", "0.065"),
        ("TWO_WINDING_TRANSFORMER", "rated_apparent_power", "65KVA", "KVA", "kVA", "65"),
        ("CAPACITOR", "rated_reactive_power", "65KVAR", "KVAR", "kvar", "65"),
        ("CAPACITOR", "rated_capacitance", "65uF", "uF", "µF", "65"),
        ("CAPACITOR", "rated_capacitance", "65μF", "μF", "µF", "65"),
        ("CAPACITOR", "rated_capacitance", "65nF", "nF", "nF", "0.065"),
        ("CAPACITOR", "rated_capacitance", "65mF", "mF", "mF", "65000"),
        ("CAPACITOR", "discharge_resistance", "65Ω", "Ω", "Ω", "65"),
        ("CABLE", "positive_sequence_resistance", "65Ω/m", "Ω/m", "Ω/m", "65000"),
        ("REACTOR", "rated_inductance", "65uH", "uH", "µH", "0.065"),
        ("REACTOR", "positive_sequence_impedance", "65kohms", "kohms", "kΩ", "65000"),
        ("TWO_WINDING_TRANSFORMER", "temperature_rise", "65℃", "℃", "°C", "65"),
        (
            "TWO_WINDING_TRANSFORMER",
            "positive_sequence_impedance",
            "65percent",
            "percent",
            "%",
            "65",
        ),
        ("BUS", "short_circuit_current_rating", "65mA", "mA", "kA", None),
        ("BUS", "short_circuit_current_rating", "65MA", "MA", "kA", None),
        ("BUS", "short_circuit_current_rating", "65KA/m", "KA", "kA", None),
        ("BUS", "short_circuit_current_rating", "65KA 65mA", "KA", "kA", None),
        ("BUS", "short_circuit_current_rating", "65kA", "KA", "kA", None),
        ("BUS", "nominal_voltage", "65", None, "V", None),
        ("BUS", "nominal_voltage", "65KV", "KV", "V", None),
        ("BUS", "nominal_voltage", "65KV", "KV", "KV", None),
        ("BUS", "nominal_voltage", "65kV·A", "kV", "kV", None),
        ("BUS", "nominal_voltage", "65kV A", "kV", "kV", None),
        ("BUS", "nominal_voltage", "65kV2", "kV", "kV", None),
        ("BUS", "nominal_voltage", "65W", "W", "W", None),
        ("BUS", "nominal_voltage", "65mV", "mV", "MV", None),
        ("BUS", "nominal_voltage", "65MV", "MV", "kV", None),
        ("BUS", "short_time_withstand_duration", "65mS", "mS", "ms", None),
        ("CAPACITOR", "rated_capacitance", "65MF", "MF", "mF", None),
        ("CAPACITOR", "rated_capacitance", "65μF", "μF", "mF", None),
        ("REACTOR", "positive_sequence_impedance", "65MΩ", "MΩ", "mΩ", None),
        ("REACTOR", "positive_sequence_impedance", "65ohms/km", "ohms", "Ω", None),
        ("REACTOR", "positive_sequence_impedance", "65ohms per km", "ohms", "Ω", None),
    ],
)
def test_proposed_unit_verifies_spelling_and_scale_across_registry_families(
    equipment, key, source_value, raw_unit, proposed_unit, normalized
):
    from powerforge_engineering_model.registry import (
        get_attribute_definition,
        supported_input_units,
    )
    from powerforge_extraction.stage_contracts import AttributeDefinitionView
    from powerforge_extraction.value_proposal import normalize_proposal

    attribute = get_attribute_definition(equipment, key)
    definition = AttributeDefinitionView(
        equipment_type=EquipmentType(equipment),
        key=key,
        name=attribute.display_name,
        required=attribute.required,
        value_type=attribute.value_type.value,
        canonical_unit=attribute.canonical_unit,
        supported_units=supported_input_units(equipment, key),
        allowed_values=(),
        notes=None,
        extraction_guidance=None,
    )
    item = assertion(
        "rating",
        attribute_key=key,
        raw_value="65",
        proposed_value="65",
        raw_unit=raw_unit,
        proposed_unit=proposed_unit,
    )
    evidence = [dict(role="VALUE", localization="RESOLVED", quote=source_value)]
    status, _, fields = normalize_proposal(item, definition, evidence)
    if normalized is None:
        assert status == "UNMAPPED" and fields == {}
    else:
        assert status == "MAPPED"
        assert fields["value_number"] == Decimal(normalized)
        assert fields["normalized_unit"] == attribute.canonical_unit
        uncertain = [dict(evidence[0], source_issues=["TRANSCRIPTION_CONFLICT"])]
        assert normalize_proposal(item, definition, uncertain)[0] == "UNMAPPED"


def test_equipment_identifier_can_support_its_literal_attributenormalize_proposal(
    stage_inputs, pinned_source
):
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
    from powerforge_extraction.stage_contracts import AttributeDefinitionView
    from powerforge_extraction.value_proposal import normalize_proposal

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
        normalize_proposal(
            assertion("phases", attribute_key="phase_count", raw_value="3", proposed_value=3),
            definition,
            [],
        )[2]["value_integer"]
        == 3
    )
    assert (
        normalize_proposal(
            assertion(
                "qualified-phases",
                attribute_key="phase_count",
                raw_value="3",
                proposed_value=3,
                qualifiers=("3PH",),
            ),
            definition,
            [],
        )[1]
        == "UNREPRESENTABLE_VALUE_FORM"
    )
    rows = stage_inputs(
        assertion(
            "model",
            attribute_key="model",
            raw_value="MODEL-X",
            proposed_value="MODEL-X",
            qualifiers=("LSIG",),
        ),
        assertion(
            "voltage",
            raw_value="347/600V",
            raw_unit="V",
            value_form="MULTIPLE",
            proposed_value="347/600",
        ),
    )
    assert rows[0]["reason_code"] == "UNREPRESENTABLE_VALUE_FORM"
    assert rows[1]["mapping_status"] == "UNMAPPED"
    assert rows[1]["raw_value"] == "347/600V"


def test_corrected_semantic_fixture_preserves_source_facts_and_inference():
    """Publication of a reviewed response fixture, without simulating AI reasoning."""
    from powerforge_extraction.attribute_admission import admit_attributes
    from powerforge_extraction.stage_contracts import (
        ATTRIBUTE_VERSION,
        VERSION,
        AlternateRepresentation,
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
                    ("Trip Unit", "ETU745 LSIG"),
                    ("Short circuit", "SC=65KA"),
                    ("Bus Bracing", "65KA"),
                    ("Phase notation", "3PH"),
                    ("Voltage", "347/600V"),
                    ("Current", "400 A / 600 A"),
                    ("Width", "20 in (508.000 mm)"),
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
        proposed_value="ETU745",
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
            proposed_value="65",
            raw_unit="KA",
            proposed_unit="kA",
            evidence=(cite(source, "SC=65KA"),),
        ),
        assertion(
            "phases",
            equipment_ref="bus",
            attribute_key="phase_count",
            raw_value="3PH",
            proposed_value=3,
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
        assertion(
            "compound-current",
            equipment_ref="bus",
            attribute_key="short_circuit_current_rating",
            raw_value="400 A / 600 A",
            raw_unit="A",
            proposed_value="400/600",
            proposed_unit="A",
            value_form="MULTIPLE",
            evidence=(QuoteCitation(kind="QUOTE", role="VALUE", quote="400 A / 600 A"),),
        ),
        assertion(
            "dimension",
            equipment_ref="bus",
            attribute_key="enclosure_width",
            raw_value="20 in (508.000 mm)",
            raw_unit="in",
            proposed_value="20",
            proposed_unit="in",
            value_form="EQUIVALENT_UNITS",
            alternate_representations=(AlternateRepresentation(value="508.000", unit="mm"),),
            evidence=(QuoteCitation(kind="QUOTE", role="VALUE", quote="20 in (508.000 mm)"),),
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
    wire = SimpleNamespace(
        upstream=upstream,
        attribute_catalog=attribute_catalog(upstream),
        page_context_hash=upstream.page_context_hash,
        upstream_hash=contract_hash(upstream),
    )
    admitted = admit_attributes(
        wire, response.model_dump_json(include={"attributes", "raw_unmapped"}).encode()
    )
    assert not admitted.fatal and not admitted.rejected
    observations = build_publication(wire, admitted.result, source)
    rows = {o.fields["local_ref"]: o.fields for o in observations}
    assert rows["model"]["value_text"] == "ETU745"
    assert rows["technology"]["value_text"] == "ELECTRONIC"
    assert rows["technology"]["attribute_origin"] == "INFERRED"
    assert rows["sccr"]["value_number"] == Decimal("65")
    assert rows["sccr"]["raw_value"] == "65KA" and rows["sccr"]["raw_unit"] == "KA"
    assert rows["phases"]["value_integer"] == 3 and not rows["phases"]["qualifiers"]
    assert rows["voltage"]["reason_code"] == "UNREPRESENTABLE_VALUE_FORM"
    assert "value_number" not in rows["voltage"]
    assert attributes[4].source_expression == "347/600V"
    assert rows["compound-current"]["mapping_status"] == "UNMAPPED"
    assert rows["compound-current"]["proposed_value"] == "400/600"
    assert rows["dimension"]["alternate_representations"] == [{"value": "508.000", "unit": "mm"}]
    assert rows["dimension"]["value_number"] == Decimal("508")
    assert rows["dimension"]["normalized_unit"] == "mm"
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


def proposal_definition(equipment, key):
    from powerforge_engineering_model.registry import (
        get_attribute_definition,
        supported_input_units,
    )
    from powerforge_extraction.stage_contracts import AttributeDefinitionView

    definition = get_attribute_definition(equipment, key)
    return AttributeDefinitionView(
        equipment_type=EquipmentType(equipment),
        key=key,
        name=definition.display_name,
        required=definition.required,
        value_type=definition.value_type.value,
        canonical_unit=definition.canonical_unit,
        supported_units=supported_input_units(equipment, key),
        allowed_values=definition.allowed_values,
        notes=definition.notes,
        extraction_guidance=None,
    )


@pytest.mark.parametrize(
    "raw,proposal,unit,expected",
    [
        ("12 Sym. kA", "12", "kA", Decimal("12")),
        ("1600 A RMS", "1600", "A", Decimal("1.6")),
        ("Isc = 25 kA", "25", "kA", Decimal("25")),
        ("15.75 A", "15.75", "A", Decimal("0.01575")),
        ("+0012.7500 kA", "12.75", "kA", Decimal("12.75")),
        ("-1.25e3 A", "-1250.000", "A", Decimal("-1.25")),
        ("12 kA", 12, "kA", "PROPOSAL_TYPE_MISMATCH"),
        ("12 kA", None, "kA", "NO_VALUE_PROPOSAL"),
        ("12.75 kA", "13", "kA", "SOURCE_VALUE_MISMATCH"),
        ("1.2 kA", "1200", "A", "SOURCE_VALUE_MISMATCH"),
        ("400/600 A", "600", "A", "SOURCE_VALUE_MISMATCH"),
        ("3 × 500 A", "1500", "A", "SOURCE_VALUE_MISMATCH"),
        ("12 kA at 480 V", "12", "kA", "SOURCE_VALUE_MISMATCH"),
        ("12 kA at full load", "12", "kA", "UNREPRESENTABLE_VALUE_FORM"),
        ("12–15 kA", "12", "kA", "SOURCE_VALUE_MISMATCH"),
        ("1200A1", "1200", "A", "SOURCE_EXPRESSION_UNVERIFIED"),
        ("CMD6", "6", "A", "SOURCE_EXPRESSION_UNVERIFIED"),
        ("1,600 A", "1600", "A", "SOURCE_EXPRESSION_UNVERIFIED"),
        ("12 kg", "12", "A", "SOURCE_EXPRESSION_UNVERIFIED"),
        ("12 kA", "12", "A", "SOURCE_UNIT_MISMATCH"),
        ("12 kA", "1e" + "9" * 100, "kA", "INVALID_VALUE"),
        (
            "1.234567891234567891234567891234567894 A",
            "1.234567891234567891234567891234567894",
            "A",
            "INEXACT_NORMALIZATION",
        ),
    ],
)
def test_numeric_proposal_requires_an_exact_unambiguous_literal(raw, proposal, unit, expected):
    from powerforge_extraction.value_proposal import normalize_proposal

    definition = proposal_definition("BUS", "short_circuit_current_rating")
    item = assertion(
        "numeric",
        attribute_key=definition.key,
        raw_value=raw,
        proposed_value=proposal,
        raw_unit=unit,
        proposed_unit=unit,
    )
    evidence = [
        {"role": "VALUE", "localization": "RESOLVED", "quote": raw},
        {"role": "HEADER", "localization": "RESOLVED", "quote": f"Rating ({unit})"},
    ]
    status, reason, fields = normalize_proposal(item, definition, evidence)
    if isinstance(expected, Decimal):
        assert (status, reason, fields["value_number"]) == ("MAPPED", None, expected)
    else:
        assert reason == expected and not fields
        if expected in {"SOURCE_VALUE_MISMATCH", "SOURCE_UNIT_MISMATCH", "INVALID_VALUE"}:
            assert status == "INVALID"
        else:
            assert status == "UNMAPPED"


@pytest.mark.parametrize(
    "raw,proposal,form",
    [
        ("400/600 V", "400/600", "MULTIPLE"),
        ("12–15 kA", "12–15", "RANGE"),
        ("3 × 500 A", "3 × 500", "MULTIPLE"),
        ("400 A / 600 A", "400/600", "MULTIPLE"),
    ],
)
def test_source_faithful_compound_remains_reviewable(stage_inputs, raw, proposal, form):
    (row,) = stage_inputs(
        assertion("compound", raw_value=raw, proposed_value=proposal, value_form=form)
    )
    assert row["mapping_status"] == "UNMAPPED"
    assert row["raw_value"] == raw and row["proposed_value"] == proposal
    assert "value_number" not in row


@pytest.mark.parametrize(
    "raw,primary,primary_literal,primary_unit,alternate,alternate_unit,expected",
    [
        ("20”(508mm)W", "20", "”", "in", "508", "mm", None),
        ("0 in (0 mm)", "0", "in", "in", "0", "mm", None),
        ("508mm (20”)", "508", "mm", "mm", "20", "”", None),
        ("20 in (50.8 cm)", "20", "in", "in", "50.8", "cm", None),
        ("20”(500mm)W", "20", "”", "in", "500", "mm", "INCONSISTENT_REPRESENTATIONS"),
        ("20”(500mm)W", "20", "”", "in", "508", "mm", "UNVERIFIED_REPRESENTATIONS"),
        ("20”(508mm)W", "508", "”", "in", "20", "mm", "SOURCE_VALUE_MISMATCH"),
        ("20”(508mm)W", "20", "”", "in", "508", "cm", "UNVERIFIED_REPRESENTATIONS"),
        ("20 in", "20", "in", "in", "508", "mm", "UNVERIFIED_REPRESENTATIONS"),
        ("20”(508mm) (50.8cm)", "20", "”", "in", "508", "mm", "UNVERIFIED_REPRESENTATIONS"),
        (
            "20 in (508.000000000000000000000000000000000001 mm)",
            "20",
            "in",
            "in",
            "508.000000000000000000000000000000000001",
            "mm",
            "INCONSISTENT_REPRESENTATIONS",
        ),
    ],
)
def test_alternate_quantities_require_complete_exact_pairs(
    raw, primary, primary_literal, primary_unit, alternate, alternate_unit, expected
):
    from powerforge_extraction.stage_contracts import AlternateRepresentation
    from powerforge_extraction.value_proposal import normalize_proposal

    definition = proposal_definition("BUS", "enclosure_width")
    item = assertion(
        "width",
        raw_value=raw,
        raw_unit=primary_literal,
        proposed_unit=primary_unit,
        proposed_value=primary,
        value_form="EQUIVALENT_UNITS",
        alternate_representations=(AlternateRepresentation(value=alternate, unit=alternate_unit),),
    )
    resolved = {"role": "VALUE", "localization": "RESOLVED", "quote": raw}
    status, reason, fields = normalize_proposal(item, definition, [resolved])
    assert reason == expected
    if expected is None:
        assert status == "MAPPED"
        assert fields["value_number"] == Decimal("0" if primary == "0" else "508")
        uncertain = dict(resolved, source_issues=["TRANSCRIPTION_CONFLICT"])
        for evidence in ([], [uncertain], [dict(resolved, quote="20 in")]):
            assert normalize_proposal(item, definition, evidence) == (
                "UNMAPPED",
                "UNVERIFIED_REPRESENTATIONS",
                {},
            )
    else:
        assert status == ("INVALID" if expected == "SOURCE_VALUE_MISMATCH" else "UNMAPPED")
        assert not fields


@pytest.mark.parametrize(
    "equipment,key,raw,proposal,expected",
    [
        ("LV_BREAKER", "pole_count", "3 Pole", 3, "MAPPED"),
        ("LV_BREAKER", "pole_count", "3 Pole", True, "UNMAPPED"),
        ("LV_BREAKER", "pole_count", "3 Pole", "3", "UNMAPPED"),
        ("LV_BREAKER", "pole_count", "2.5 Pole", 2, "INVALID"),
        ("LV_BREAKER", "normally_closed", "No", False, "MAPPED"),
        ("LV_BREAKER", "normally_closed", "No", True, "INVALID"),
        ("LV_BREAKER", "normally_closed", "Yes", "true", "UNMAPPED"),
        ("LV_BREAKER", "normally_closed", "auto", False, "UNMAPPED"),
        ("LV_BREAKER", "model", " 00-AB 75 ", "00-AB 75", "MAPPED"),
        ("LV_BREAKER", "model", "00-AB 75", "0-ab75", "INVALID"),
        ("LV_BREAKER", "trip_unit_type", "Electronic", "ELECTRONIC", "MAPPED"),
        ("LV_BREAKER", "trip_unit_type", "Electronic", "UNKNOWN_ENUM", "INVALID"),
    ],
)
def test_registry_types_are_strict_and_text_preserves_identifiers(
    equipment, key, raw, proposal, expected
):
    from powerforge_extraction.value_proposal import normalize_proposal

    definition = proposal_definition(equipment, key)
    item = assertion("typed", raw_value=raw, proposed_value=proposal)
    status, _, fields = normalize_proposal(item, definition, [])
    assert status == expected
    assert bool(fields) == (expected == "MAPPED")


@pytest.mark.parametrize(
    "equipment,key,raw,proposal,status,reason",
    [
        (
            "TWO_WINDING_TRANSFORMER",
            "primary_connection",
            "Delta",
            "WYE",
            "INVALID",
            "SOURCE_VALUE_MISMATCH",
        ),
        ("TWO_WINDING_TRANSFORMER", "primary_connection", " dElTa ", "DELTA", "MAPPED", None),
        ("TWO_WINDING_TRANSFORMER", "primary_connection", "Star", "WYE", "MAPPED", None),
        ("TWO_WINDING_TRANSFORMER", "secondary_connection", "STAR", "WYE", "MAPPED", None),
        (
            "TWO_WINDING_TRANSFORMER",
            "secondary_connection",
            "Star",
            "DELTA",
            "INVALID",
            "SOURCE_VALUE_MISMATCH",
        ),
        (
            "TWO_WINDING_TRANSFORMER",
            "primary_connection",
            "Star",
            None,
            "UNMAPPED",
            "NO_VALUE_PROPOSAL",
        ),
        (
            "TWO_WINDING_TRANSFORMER",
            "primary_connection",
            "Star/Delta",
            "WYE",
            "UNMAPPED",
            "SOURCE_EXPRESSION_UNVERIFIED",
        ),
        (
            "TWO_WINDING_TRANSFORMER",
            "primary_connection",
            "Y",
            "WYE",
            "UNMAPPED",
            "SOURCE_EXPRESSION_UNVERIFIED",
        ),
        (
            "LV_BREAKER",
            "trip_unit_type",
            "Star",
            "ELECTRONIC",
            "UNMAPPED",
            "SOURCE_EXPRESSION_UNVERIFIED",
        ),
    ],
)
def test_extracted_enum_requires_complete_verified_source_spelling(
    equipment, key, raw, proposal, status, reason
):
    from powerforge_extraction.value_proposal import normalize_proposal

    definition = proposal_definition(equipment, key)
    item = assertion("enum", attribute_key=key, raw_value=raw, proposed_value=proposal)
    actual_status, actual_reason, fields = normalize_proposal(item, definition, [])
    assert (actual_status, actual_reason) == (status, reason)
    assert fields.get("value_text") == (proposal if status == "MAPPED" else None)


def test_extracted_enum_mismatch_retains_raw_value_and_proposal(stage_inputs):
    (row,) = stage_inputs(
        assertion(
            "contradiction",
            attribute_key="primary_connection",
            raw_value="Delta",
            proposed_value="WYE",
        )
    )
    assert row["mapping_status"] == "INVALID"
    assert row["reason_code"] == "SOURCE_VALUE_MISMATCH"
    assert row["raw_value"] == "Delta" and row["proposed_value"] == "WYE"
    assert "value_text" not in row


@pytest.mark.parametrize(
    "equipment,key,proposal,unit,expression,expected",
    [
        ("LV_BREAKER", "pole_count", 3, None, None, "MAPPED"),
        ("LV_BREAKER", "pole_count", "3", None, None, "INVALID"),
        ("LV_BREAKER", "normally_closed", False, None, None, "MAPPED"),
        ("LV_BREAKER", "normally_closed", "false", None, None, "INVALID"),
        ("LV_BREAKER", "manufacturer", "Example", None, "CMD6", "MAPPED"),
        ("LV_BREAKER", "manufacturer", 123, None, None, "INVALID"),
        ("LV_BREAKER", "trip_unit_type", "ELECTRONIC", None, "ETU745", "MAPPED"),
        ("LV_BREAKER", "trip_unit_type", "INVENTED", None, None, "INVALID"),
        ("BUS", "short_circuit_current_rating", "1.25", "kA", None, "MAPPED"),
        ("BUS", "short_circuit_current_rating", 12, "kA", None, "INVALID"),
        ("BUS", "short_circuit_current_rating", "1200", "A", "1.2 kA", "INVALID"),
        ("BUS", "short_circuit_current_rating", "1500", "A", "3 × 500 A", "UNMAPPED"),
        ("BUS", "short_circuit_current_rating", "600", "A", "400/600 A", "UNMAPPED"),
    ],
)
def test_inferred_proposals_use_registry_types_and_cannot_resolve_source_arithmetic(
    equipment, key, proposal, unit, expression, expected
):
    from powerforge_extraction.stage_contracts import InferredAssertion
    from powerforge_extraction.value_proposal import normalize_proposal

    definition = proposal_definition(equipment, key)
    item = InferredAssertion(
        origin="INFERRED",
        local_ref="inference",
        equipment_ref="owner",
        association="ASSERTED",
        attribute_key=key,
        proposed_value=proposal,
        proposed_unit=unit,
        source_expression=expression,
        inference_explanation="Test fixture for a separately reviewable inference.",
        inference_basis="EQUIPMENT_CHARACTERISTICS",
        evidence=(),
    )
    status, _, fields = normalize_proposal(item, definition, [])
    assert status == expected and bool(fields) == (expected == "MAPPED")


def test_publication_preserves_equivalent_proposals_before_database_write(stage_inputs):
    from powerforge_extraction.stage_contracts import AlternateRepresentation

    raw = "20”(508.0mm)W"
    alternates = (AlternateRepresentation(value="508.0", unit="mm"),)
    (row,) = stage_inputs(
        assertion(
            "width",
            equipment_ref="bus",
            attribute_key="enclosure_width",
            raw_value=raw,
            raw_unit="”",
            proposed_value="20",
            proposed_unit="in",
            value_form="EQUIVALENT_UNITS",
            alternate_representations=alternates,
        )
    )
    assert row["mapping_status"] == "UNMAPPED"
    assert row["reason_code"] == "UNVERIFIED_REPRESENTATIONS"
    assert row["raw_value"] == raw
    assert row["proposed_value"] == "20"
    assert row["alternate_representations"] == [{"value": "508.0", "unit": "mm"}]
    assert row["value_source_support"] == "UNVERIFIED"
    assert "value_number" not in row


@pytest.mark.parametrize(
    "key,raw,proposal,status,reason",
    [
        ("model", "  CMD6  ", "CMD6", "MAPPED", None),
        ("model", "Model: CMD6", "CMD6", "MAPPED", None),
        ("model", " model : 00-AB  75 ", "00-AB  75", "MAPPED", None),
        ("catalog_number", "Catalog Number: 00-AB 75", "00-AB 75", "MAPPED", None),
        ("trip_unit_model", "Trip Unit Model: ETU745", "ETU745", "MAPPED", None),
        ("model", "00-AB 75", "0-ab75", "INVALID", "SOURCE_VALUE_MISMATCH"),
        ("model", "Model: 00-AB", "0-AB", "INVALID", "SOURCE_VALUE_MISMATCH"),
        ("model", "Model: CMD6", "cmd6", "INVALID", "SOURCE_VALUE_MISMATCH"),
        ("model", "Model: CMD6 75", "CMD6", "UNMAPPED", "SOURCE_EXPRESSION_UNVERIFIED"),
        ("model", "Model: CMD6 3 Pole", "CMD6", "UNMAPPED", "SOURCE_EXPRESSION_UNVERIFIED"),
        ("model", "Model: CMD6\nSerial: Q2", "CMD6", "UNMAPPED", "SOURCE_EXPRESSION_UNVERIFIED"),
        ("model", "Description: CMD6", "CMD6", "UNMAPPED", "SOURCE_EXPRESSION_UNVERIFIED"),
        ("catalog_number", "Model: CMD6", "CMD6", "UNMAPPED", "SOURCE_EXPRESSION_UNVERIFIED"),
        (
            "manufacturer",
            "Equipment from Acme Corp",
            "Acme Corp",
            "UNMAPPED",
            "SOURCE_EXPRESSION_UNVERIFIED",
        ),
    ],
)
def test_text_cleanup_preserves_the_complete_source_value(key, raw, proposal, status, reason):
    from powerforge_extraction.value_proposal import normalize_proposal

    definition = proposal_definition("LV_BREAKER", key)
    item = assertion(
        "cleanup", attribute_key=key, raw_label=None, raw_value=raw, proposed_value=proposal
    )
    actual_status, actual_reason, fields = normalize_proposal(item, definition, [])
    assert (actual_status, actual_reason) == (status, reason)
    assert fields.get("value_text") == (proposal if status == "MAPPED" else None)
    assert item.raw_value == raw and item.proposed_value == proposal


@pytest.mark.parametrize(
    "equipment,key,magnitude,unit,shared,exact",
    [
        (
            "TWO_WINDING_TRANSFORMER",
            "temperature_rise",
            "1",
            "°F",
            "0.5555555555555555555555555555555556",
            False,
        ),
        ("TWO_WINDING_TRANSFORMER", "temperature_rise", "9", "°F", "5", True),
        (
            "CABLE",
            "positive_sequence_resistance",
            "1",
            "Ω/1000 ft",
            "3.280839895013123359580052493438320",
            False,
        ),
        ("CABLE", "positive_sequence_resistance", "0.3048", "Ω/1000 ft", "1", True),
    ],
)
def test_extraction_requires_exact_conversion_with_existing_normalizer(
    equipment, key, magnitude, unit, shared, exact
):
    from powerforge_engineering_model.registry import normalize_attribute_value
    from powerforge_extraction.value_proposal import normalize_proposal

    definition = proposal_definition(equipment, key)
    raw = f"{magnitude} {unit}"
    item = assertion(
        "conversion",
        attribute_key=key,
        raw_value=raw,
        raw_unit=unit,
        proposed_value=magnitude,
        proposed_unit=unit,
    )
    evidence = [{"role": "VALUE", "localization": "RESOLVED", "quote": raw}]
    assert normalize_attribute_value(equipment, key, Decimal(magnitude), unit) == Decimal(shared)
    status, reason, fields = normalize_proposal(item, definition, evidence)
    if exact:
        assert (status, reason) == ("MAPPED", None)
        assert fields["value_number"] == Decimal(shared)
        assert fields["normalized_unit"] == definition.canonical_unit
    else:
        assert (status, reason, fields) == ("UNMAPPED", "INEXACT_NORMALIZATION", {})


@pytest.mark.parametrize(
    "key,label,raw,proposal,status",
    [
        ("model", "Breaker Type", "Breaker Type: PDG3", "PDG3", "MAPPED"),
        ("catalog_number", "Catalog No.", " Catalog No. : ABC123 ", "ABC123", "MAPPED"),
        ("model", "Breaker Type", "  PDG3  ", "PDG3", "MAPPED"),
        ("model", "Breaker Type", "Model: PDG3", "PDG3", "UNMAPPED"),
        ("model", "breaker type", "Breaker Type: PDG3", "PDG3", "UNMAPPED"),
        ("model", " ", "Model: PDG3", "PDG3", "UNMAPPED"),
        ("model", None, "Model: PDG3", "PDG3", "MAPPED"),
        ("model", None, "Breaker Type: PDG3", "PDG3", "UNMAPPED"),
        ("model", "Breaker Type", "Breaker Type: PDG3", "pdg3", "INVALID"),
        ("catalog_number", "Catalog No.", "Catalog No.: 00-AB 75", "0-ab75", "INVALID"),
        ("model", "Breaker Type", "Breaker Type: PDG3 3 Pole", "PDG3", "UNMAPPED"),
        ("model", "Breaker Type", "Breaker Type: PDG3 / PDG4", "PDG3", "UNMAPPED"),
        ("model", "Breaker Type", "Breaker Type: PDG3\nSerial: Q2", "PDG3", "UNMAPPED"),
        ("model", "Breaker Type", "Breaker Type:\nPDG3", "PDG3", "UNMAPPED"),
    ],
)
def test_text_cleanup_uses_the_literal_source_label(key, label, raw, proposal, status):
    from powerforge_extraction.value_proposal import normalize_proposal

    definition = proposal_definition("LV_BREAKER", key)
    item = assertion(
        "source-label", attribute_key=key, raw_label=label, raw_value=raw, proposed_value=proposal
    )
    reason = {
        "MAPPED": None,
        "UNMAPPED": "SOURCE_EXPRESSION_UNVERIFIED",
        "INVALID": "SOURCE_VALUE_MISMATCH",
    }[status]
    actual_status, actual_reason, fields = normalize_proposal(item, definition, [])
    assert (actual_status, actual_reason) == (status, reason)
    assert fields.get("value_text") == (proposal if status == "MAPPED" else None)
    assert (item.raw_label, item.raw_value, item.proposed_value) == (label, raw, proposal)


@pytest.mark.parametrize("inferred", [False, True], ids=["extracted", "inferred"])
def test_normalized_text_trims_outer_whitespace_but_preserves_the_proposal(stage_inputs, inferred):
    from powerforge_extraction.stage_contracts import InferredAssertion

    proposal = "  PDG3  75 \t"
    if inferred:
        item = InferredAssertion(
            origin="INFERRED",
            local_ref="model",
            equipment_ref="owner",
            association="ASSERTED",
            attribute_key="model",
            proposed_value=proposal,
            proposed_unit=None,
            inference_explanation="Synthetic contextual proposal.",
            inference_basis=None,
            source_expression=None,
            evidence=(),
        )
    else:
        item = assertion(
            "model", attribute_key="model", raw_value="PDG3  75", proposed_value=proposal
        )
    (row,) = stage_inputs(item)
    assert row["mapping_status"] == "MAPPED"
    assert row["value_text"] == "PDG3  75"
    assert row["proposed_value"] == proposal
    if not inferred:
        assert row["raw_value"] == "PDG3  75"
