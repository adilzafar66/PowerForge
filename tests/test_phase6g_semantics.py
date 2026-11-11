"""Synthetic evidence, semantic decisions and frozen profile dispatch."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from enriched_pure_support import fake, native_sources, table_interpretation
from powerforge_extraction.enriched_profiles import (
    COMPACT_TABLES,
    DISTRIBUTED_ENGINEERING,
    SEMANTIC_PROFILES,
    enriched_profile,
    require_enriched,
    stage_models,
)
from powerforge_extraction.enriched_tables import reconstruct
from powerforge_extraction.interpretation_v1 import InterpretationContext, _attribute
from powerforge_extraction.profiles import read_profile
from powerforge_extraction.semantic_observations import (
    SemanticAttributeResponse,
    SemanticEquipmentResponse,
    SemanticTableResponse,
)
from powerforge_extraction.semantic_output import convert_engineering
from powerforge_extraction.semantic_tables import interpret_tables
from powerforge_shared.config import Settings
from test_enriched_grounding import prose_pdf
from test_phase6g_stage_diagnostics import native_ctx as native_ctx

TRANSFORMER = "TWO_WINDING_TRANSFORMER"


def part(sources, role, words):
    if isinstance(words, str):
        words = words.split()
    refs = [next(r.model.ref for r in sources.readings if r.text == word) for word in words]
    return dict(role=role, quote=" ".join(words), source_ref="spatial_readings", reading_refs=refs)


def recognition(sources, *, mapped=True):
    return SemanticEquipmentResponse.model_validate(
        {
            "schema_version": "equipment-recognition-schema-v3",
            "overflowed": False,
            "equipment": [
                {
                    "local_ref": "eq1",
                    "raw_expression": "2-Winding Transformer",
                    "anchors": [
                        part(sources, "EQUIPMENT", "2-Winding Transformer"),
                        part(sources, "TAG", "80T1"),
                    ],
                    "observed_tag": "80T1",
                    "observed_name": None,
                    "proposed_equipment_type": TRANSFORMER if mapped else None,
                    "ambiguous": False,
                    "ambiguity_reason": None,
                }
            ],
        }
    )


def attribute(sources, label, value, unit, key, *, ref="a1"):
    return dict(
        local_ref=ref,
        raw_expression=f"{label} {value}",
        equipment_ref="eq1",
        anchors=[part(sources, "LABEL", label), part(sources, "VALUE", value)],
        source_label=label,
        raw_value=value,
        raw_unit=unit,
        proposed_equipment_type=TRANSFORMER,
        proposed_attribute_key=key,
        ambiguous=False,
        ambiguity_reason=None,
    )


def attributes(*items):
    return SemanticAttributeResponse.model_validate(
        dict(
            schema_version="attribute-extraction-schema-v3",
            overflowed=False,
            attributes=list(items),
        )
    )


@pytest.mark.parametrize("key", SEMANTIC_PROFILES)
def test_successor_profiles_round_trip_with_distinct_pinned_resources(key):
    profile = enriched_profile(key, Settings(_env_file=None))
    restored = read_profile(profile.model_dump(mode="json"))
    require_enriched(restored)
    assert restored == profile
    assert (
        profile.identity_hash
        != enriched_profile(key[:-1] + "1", Settings(_env_file=None)).identity_hash
    )
    assert stage_models(profile)[profile.stages[-1]].__name__.startswith("Semantic")


@pytest.mark.parametrize("unfamiliar", [False, True])
def test_split_native_field_maps_from_proposal_even_after_unmapped_recognition(unfamiliar):
    case = json.loads(Path("evals/extraction/phase6g/synthetic.json").read_text())["cases"][
        "split_transformer"
    ]
    device, printed_label, printed_value = case["lines"]
    label = printed_label if unfamiliar else "kVA:"
    gold = case["expected"]
    sources = native_sources(
        prose_pdf([device, label, printed_value, "TAG: 80T1"]),
        "EQUIPMENT_RECOGNITION",
    )
    recognized = convert_engineering(recognition(sources, mapped=False), sources)
    assert recognized.candidates[0].mapping_status == "UNMAPPED"
    assert recognized.candidates[0].observed_tag == "80T1"
    if unfamiliar:
        assert _attribute(TRANSFORMER, label, InterpretationContext(label)) is None
    later = replace(
        sources, stage="ATTRIBUTE_EXTRACTION", unit_key="ATTRIBUTE_EXTRACTION:page:000001"
    )
    output = convert_engineering(
        attributes(attribute(later, label, printed_value, gold["unit"], gold["key"])),
        later,
        recognized,
    )
    value = output.candidates[0]
    assert value.mapping_status == "MAPPED" and str(value.numeric_value) == gold["numeric"]
    assert value.attribute_key == gold["key"]
    assert value.diagnostics["relationship_basis"] == "LOCAL_FORM_GEOMETRY"
    assert {p["role"] for p in value.diagnostics["evidence_parts"]} == {"LABEL", "VALUE"}
    assert "350" in {e.source_snippet for e in output.evidence}
    assert all(e.source_snippet != f"{label} 350" for e in output.evidence)


def test_contradicted_key_unavailable_alias_and_qualified_values():
    sources = native_sources(
        prose_pdf(
            [
                "2-Winding Transformer",
                "Secondary Voltage:",
                "600 V",
                "Minimum Capacity (kVA)",
                "350",
                "TAG: 80T1",
            ]
        ),
        "EQUIPMENT_RECOGNITION",
    )
    recognized = convert_engineering(recognition(sources), sources)
    later = replace(
        sources, stage="ATTRIBUTE_EXTRACTION", unit_key="ATTRIBUTE_EXTRACTION:page:000001"
    )
    wrong = attribute(later, "Secondary Voltage:", "600", "V", "primary_voltage")
    wrong["anchors"].append(part(later, "UNIT", "V"))
    qualified = attribute(
        later, "Minimum Capacity (kVA)", "350", "kVA", "rated_apparent_power", ref="a2"
    )
    forged = {**wrong, "local_ref": "forged"}
    forged["anchors"] = [dict(wrong["anchors"][0], reading_refs=["foreign"]), *wrong["anchors"][1:]]
    output = convert_engineering(attributes(wrong, qualified, forged), later, recognized)
    assert [c.reason_code for c in output.candidates] == [
        "ATTRIBUTE_PROPOSAL_CONFLICT",
        "QUALIFIED_VALUE_RETAINED",
    ]
    assert all(
        c.mapping_status == "UNMAPPED" and c.numeric_value is None for c in output.candidates
    )


def test_tables_uses_proposals_against_committed_cells():
    sources = native_sources(Path("evals/tables/v1/sources/positioned_schedule.pdf").read_bytes())
    reconstruction, context = reconstruct(fake(sources), sources)
    later, response = table_interpretation(sources, reconstruction)
    payload = response.model_dump(mode="json")
    payload["schema_version"] = "table-interpretation-schema-v3"
    payload["equipment"][0]["proposed_equipment_type"] = TRANSFORMER
    item = payload["attributes"][0]
    item["proposed_equipment_type"] = TRANSFORMER
    item["proposed_attribute_key"] = "secondary_voltage"
    item["raw_unit"] = "V"
    output = interpret_tables(SemanticTableResponse.model_validate(payload), later, context)
    assert output.candidates[-1].mapping_status == "MAPPED"
    assert str(output.candidates[-1].numeric_value) == "0.6"


@pytest.mark.integration
@pytest.mark.parametrize(
    ("family", "version"),
    [("engineering", 2), ("engineering", 3), ("tables", 2), ("tables", 3), ("tables", 4)],
)
def test_successor_execution_publishes_via_existing_attempts(native_ctx, family, version):
    from types import SimpleNamespace
    from uuid import UUID

    from documents_support import client
    from enriched_support import enrich, extraction_detail, start_enriched
    from enrichment_support import build_source
    from extraction_worker.openai_extraction import OpenAIExtractionProvider
    from powerforge_extraction.enriched_fake import FakeEnrichedProvider
    from powerforge_extraction.execution import execute_unit

    label = "Continuous transfer duty (kVA)"
    pdf = (
        prose_pdf(["2-Winding Transformer", label, "350", "TAG: 80T1"])
        if family == "engineering"
        else Path("evals/tables/v1/sources/positioned_schedule.pdf").read_bytes()
    )
    ctx = build_source(native_ctx, pdf, "synthetic.pdf")
    binding = enrich(ctx)
    run = start_enriched(ctx, binding, profile=f"{family}-openai-enriched-v{version}")
    calls = []

    class Transport:
        def parse(self, **options):
            model = options["text_format"]
            projection = json.loads(options["input"][0]["content"][0]["text"])["source"]
            upstream = (
                json.loads(options["input"][1]["content"][0]["text"])["observations"]
                if len(options["input"]) > 1
                else None
            )
            calls.append(model.__name__)
            by_ref = SimpleNamespace(
                readings=[
                    SimpleNamespace(text=r["raw_text"], model=SimpleNamespace(ref=r["ref"]))
                    for r in projection["readings"]
                ]
            )
            from powerforge_extraction.table_reconstruction_v4 import CompactReconstructionResponse

            if model is CompactReconstructionResponse:
                result = model.model_validate(
                    {
                        "schema_version": "table-reconstruction-schema-v3",
                        "overflowed": False,
                        "partitions": [
                            {
                                "local_ref": "t0",
                                "spatial_table_ref": projection["tables"][0]["ref"],
                                "proposed_kind": "EQUIPMENT_ROWS",
                            },
                        ],
                        "reported_tables": [],
                    }
                )
            elif model is SemanticEquipmentResponse:
                result = recognition(by_ref, mapped=False)
            elif model is SemanticAttributeResponse:
                assert upstream["equipment"][0]["mapping_status"] == "UNMAPPED"
                assert '"rated_apparent_power"' in options["instructions"]
                result = attributes(attribute(by_ref, label, "350", "kVA", "rated_apparent_power"))
            else:
                from powerforge_extraction.enriched_observations import RESPONSES, SCHEMAS

                stage = "TABLE_INTERPRETATION" if upstream is not None else "TABLE_RECONSTRUCTION"
                fake_request = SimpleNamespace(
                    text=json.dumps(projection),
                    stage=stage,
                    schema_version=SCHEMAS[stage],
                    response_model=RESPONSES[stage],
                    upstream_context=json.dumps(upstream) if upstream is not None else None,
                )
                result = FakeEnrichedProvider().execute(fake_request).result
                if model is SemanticTableResponse:
                    body = result.model_dump(mode="json")
                    body["schema_version"] = "table-interpretation-schema-v3"
                    body["equipment"][0]["proposed_equipment_type"] = TRANSFORMER
                    body["attributes"][0].update(
                        proposed_equipment_type=TRANSFORMER,
                        proposed_attribute_key="secondary_voltage",
                        raw_unit="V",
                    )
                    result = model.model_validate(body)
            return SimpleNamespace(
                status="completed",
                output=[],
                output_parsed=result,
                usage=SimpleNamespace(input_tokens=20, output_tokens=30),
            )

    def provider(claim):
        return OpenAIExtractionProvider(
            ctx["settings"],
            client=SimpleNamespace(responses=Transport()),
            profile=claim.profile,
        )

    for stage in run["run"]["stages"]:
        attempt = next(a for a in run["attempts"] if a["stage"] == stage)
        assert execute_unit(
            UUID(attempt["id"]), ctx["factory"], ctx["storage"], ctx["settings"], provider
        )
    run_id = run["run"]["id"]
    completed = extraction_detail(ctx, run_id)
    assert completed["run"]["status"] == "COMPLETED", completed["attempts"]
    assert len(calls) == completed["execution"]["provider_calls_started"] == 2
    response = client.get(ctx["base"] + f"/extraction/runs/{run_id}/candidates")
    assert response.status_code == 200
    value = next(c for c in response.json()["items"] if c["kind"] == "ATTRIBUTE_VALUE")
    assert value["mapping_status"] == "MAPPED"
    assert value["numeric_value"] == ("350" if family == "engineering" else "0.6")


def test_competing_equipment_prevents_title_block_tag_assignment():
    source = native_sources(
        prose_pdf(
            ["2-Winding Transformer", "Secondary Voltage: 600 V", "Power Cable", "TAG: 80T1"]
        ),
        "EQUIPMENT_RECOGNITION",
    )
    payload = recognition(source).model_dump(mode="json")
    payload["equipment"].append(
        {
            **payload["equipment"][0],
            "local_ref": "eq2",
            "raw_expression": "Power Cable",
            "anchors": [part(source, "EQUIPMENT", "Power Cable"), part(source, "TAG", "80T1")],
            "proposed_equipment_type": "CABLE",
        }
    )
    result = convert_engineering(SemanticEquipmentResponse.model_validate(payload), source)
    assert len(result.candidates) == 2
    assert all(c.observed_tag is None for c in result.candidates)


def test_unrelated_fragments_and_image_reports_remain_raw():
    source = native_sources(
        prose_pdf(["2-Winding Transformer", "kVA:", *(["Gap"] * 7), "350", "TAG: 80T1"]),
        "EQUIPMENT_RECOGNITION",
    )
    recognized = convert_engineering(recognition(source), source)
    later = replace(
        source, stage="ATTRIBUTE_EXTRACTION", unit_key="ATTRIBUTE_EXTRACTION:page:000001"
    )
    distant = attribute(later, "kVA:", "350", "kVA", "rated_apparent_power")
    visual = {
        **distant,
        "local_ref": "visual",
        "anchors": [
            {"role": "VALUE", "quote": "350", "source_ref": "analysis_image", "reading_refs": []},
        ],
    }
    output = convert_engineering(attributes(distant, visual), later, recognized)
    assert [c.raw_text for c in output.candidates] == ["350", "350"]
    assert all(c.mapping_status == "UNMAPPED" for c in output.candidates)
    page = next(e for e in output.evidence if e.source_kind == "VISUAL_REGION")
    assert page.source_snippet is None and page.text_start is None and page.location.region is None


def test_repeated_breakers_keep_separate_source_local_mentions():
    from spatial_layout_support import drawn_table

    sources = native_sources(
        drawn_table(
            rows=[
                ("Equipment", "Trip (A)"),
                ("LV Breaker GBH3020", "20"),
                ("LV Breaker GBH3020", "20"),
                ("PROV", "18"),
            ]
        )
    )
    reconstruction, context = reconstruct(fake(sources), sources)
    later, response = table_interpretation(sources, reconstruction)
    data = response.model_dump(mode="json")
    data["schema_version"] = "table-interpretation-schema-v3"
    for equipment in data["equipment"]:
        equipment["proposed_equipment_type"] = "LV_BREAKER"
    output = interpret_tables(SemanticTableResponse.model_validate(data), later, context)
    breakers = [c for c in output.candidates if c.kind == "EQUIPMENT_MENTION"]
    assert len(breakers) == 2
    assert len({c.id for c in breakers}) == 2
    assert len({c.source_group_id for c in breakers}) == 2
    assert all(c.equipment_type_key == "LV_BREAKER" for c in breakers)
    assert any(c.raw_value == "18" and c.mapping_status == "UNMAPPED" for c in output.candidates)


def test_panelboard_designation_maps_to_existing_bus_type():
    source = native_sources(
        prose_pdf(["Panelboard", "Main Lugs Only", "DESIGNATION: CDP-6C"]),
        "EQUIPMENT_RECOGNITION",
    )
    response = SemanticEquipmentResponse.model_validate(
        {
            "schema_version": "equipment-recognition-schema-v3",
            "overflowed": False,
            "equipment": [
                {
                    "local_ref": "panel",
                    "raw_expression": "Panelboard",
                    "anchors": [
                        part(source, "EQUIPMENT", "Panelboard"),
                        part(source, "TAG", "CDP-6C"),
                    ],
                    "observed_tag": "CDP-6C",
                    "observed_name": None,
                    "proposed_equipment_type": "BUS",
                    "ambiguous": False,
                    "ambiguity_reason": None,
                }
            ],
        }
    )
    output = convert_engineering(response, source)
    assert [(c.equipment_type_key, c.observed_tag) for c in output.candidates] == [
        ("BUS", "CDP-6C")
    ]


def test_default_operation_profiles_preserve_previously_pinned_consent():
    from powerforge_extraction.operation_plan import operation_profiles, pinned_operation_profile

    settings = Settings(_env_file=None)
    families = ("engineering", "tables")
    assert [p.key for p in operation_profiles(settings, families)] == [
        DISTRIBUTED_ENGINEERING,
        COMPACT_TABLES,
    ]
    for family, versions in (("engineering", (1, 2, 3)), ("tables", (1, 2, 3, 4))):
        for version in versions:
            profile = enriched_profile(f"{family}-openai-enriched-v{version}", settings)
            assert pinned_operation_profile(settings, family, profile.identity_hash) == profile


def test_manufacturer_equipment_description_uses_corroborating_winding_context():
    from powerforge_extraction.interpretation_v1 import _equipment_type

    title = "Magnetic isolation unit"
    detail = "Primary and secondary winding ratings"
    source = native_sources(prose_pdf([title, detail, "TAG: 80T1"]), "EQUIPMENT_RECOGNITION")
    payload = {
        "schema_version": "equipment-recognition-schema-v3",
        "overflowed": False,
        "equipment": [
            {
                "local_ref": "eq1",
                "raw_expression": title,
                "anchors": [part(source, "EQUIPMENT", title), part(source, "CONTEXT", detail)],
                "observed_tag": None,
                "observed_name": None,
                "proposed_equipment_type": TRANSFORMER,
                "ambiguous": False,
                "ambiguity_reason": None,
            }
        ],
    }
    assert _equipment_type(f"{title} {detail}") is None
    supported = convert_engineering(SemanticEquipmentResponse.model_validate(payload), source)
    assert supported.candidates[0].equipment_type_key == TRANSFORMER
    payload["equipment"][0]["anchors"].pop()
    uncertain = convert_engineering(SemanticEquipmentResponse.model_validate(payload), source)
    assert uncertain.candidates[0].mapping_status == "UNMAPPED"


def test_split_primary_voltage_normalizes_literal_unit_spelling():
    sources = native_sources(
        prose_pdf(["2-Winding Transformer", "Primary:", "600 Delta Volts", "TAG: 80T1"]),
        "EQUIPMENT_RECOGNITION",
    )
    recognized = convert_engineering(recognition(sources), sources)
    later = replace(
        sources, stage="ATTRIBUTE_EXTRACTION", unit_key="ATTRIBUTE_EXTRACTION:page:000001"
    )
    primary = attribute(later, "Primary:", "600", "Volts", "primary_voltage")
    primary["anchors"].append(part(later, "UNIT", "Volts"))
    output = convert_engineering(attributes(primary), later, recognized)
    c = output.candidates[0]
    assert (c.mapping_status, c.raw_value, c.raw_unit, c.unit) == ("MAPPED", "600", "Volts", "kV")
    assert str(c.numeric_value) == "0.6"
    assert any(e.source_snippet == "Delta" for e in output.evidence)


def test_horizontal_form_value_associates_through_grounded_label():
    import pymupdf

    with pymupdf.open() as document:
        page = document.new_page(width=500, height=300)
        for point, text in [
            ((40, 45), "2-Winding Transformer"),
            ((40, 75), "kVA:"),
            ((125, 75), "350"),
            ((300, 220), "TAG: 80T1"),
        ]:
            page.insert_text(point, text, fontsize=12)
        source = native_sources(document.tobytes(), "EQUIPMENT_RECOGNITION")
    recognized = convert_engineering(recognition(source), source)
    later = replace(
        source, stage="ATTRIBUTE_EXTRACTION", unit_key="ATTRIBUTE_EXTRACTION:page:000001"
    )
    output = convert_engineering(
        attributes(attribute(later, "kVA:", "350", "kVA", "rated_apparent_power")),
        later,
        recognized,
    )
    value = output.candidates[0]
    assert value.numeric_value == 350
    assert value.diagnostics["relationship_basis"] in {"SAME_SOURCE_LINE", "LOCAL_FORM_GEOMETRY"}
    assert value.equipment_mention_candidate_id == recognized.candidates[0].id


@pytest.mark.parametrize("competing", [False, True])
def test_distributed_specification_regions_require_single_transformer(competing):
    import pymupdf

    with pymupdf.open() as doc:
        page = doc.new_page(width=760, height=650)
        case = json.loads(Path("evals/extraction/phase6g/synthetic.json").read_text())["cases"][
            "distributed_transformer"
        ]
        fields = [((x, y), text) for x, y, text in case["lines"]]
        if competing:
            fields.append(((30, 175), "Auxiliary Transformer"))
        for point, text in fields:
            page.insert_text(point, text, fontsize=12)
        sources = native_sources(doc.tobytes(), "EQUIPMENT_RECOGNITION")

    wire = {
        "schema_version": "equipment-recognition-schema-v3",
        "overflowed": False,
        "equipment": [
            {
                "local_ref": "eq1",
                "raw_expression": "Dry-type Transformer",
                "anchors": [
                    part(sources, "EQUIPMENT", "Dry-type Transformer"),
                    part(sources, "CONTEXT", "Primary: 13.8 kV"),
                    part(sources, "CONTEXT", "Secondary: 600 V"),
                    part(sources, "TAG", "80T1"),
                ],
                "observed_tag": "80T1",
                "observed_name": None,
                "proposed_equipment_type": TRANSFORMER,
                "ambiguous": False,
                "ambiguity_reason": None,
            }
        ],
    }
    recognized = convert_engineering(
        SemanticEquipmentResponse.model_validate(wire),
        sources,
        distributed=True,
    )
    later = replace(
        sources, stage="ATTRIBUTE_EXTRACTION", unit_key="ATTRIBUTE_EXTRACTION:page:000001"
    )
    result = convert_engineering(
        attributes(attribute(later, "kVA:", "350", "kVA", "rated_apparent_power")),
        later,
        recognized,
        distributed=True,
    )
    mention, rating = recognized.candidates[0], result.candidates[0]
    assert not mention.diagnostics["scope_readings"]
    if competing:
        assert mention.mapping_status == rating.mapping_status == "UNMAPPED"
        assert rating.equipment_mention_candidate_id is None
    else:
        assert mention.mapping_status == rating.mapping_status == "MAPPED"
        assert rating.equipment_mention_candidate_id == mention.id
        assert str(rating.numeric_value) == case["expected"]["rated_apparent_power"]
        assert (
            rating.diagnostics["equipment_association_basis"]
            == "CORROBORATED_SPECIFICATION_SECTION"
        )
        assert "Electrical" in {item.source_snippet for item in result.evidence}


def test_distributed_profile_pins_its_own_dispatch():
    profile = enriched_profile(DISTRIBUTED_ENGINEERING, Settings(_env_file=None))
    restored = read_profile(profile.model_dump(mode="json"))
    require_enriched(restored)
    assert restored.schema_version == "enriched-stage-manifest-v3"


@pytest.mark.parametrize(
    ("label", "ambiguous", "expected", "reason"),
    [
        ("Durchgang (kVA)", False, "MAPPED", "AI_SUPPORTED_ATTRIBUTE"),
        ("Auxiliary Load (kVA):", False, "UNMAPPED", "ATTRIBUTE_PROPOSAL_CONFLICT"),
        ("Durchgang (kVA)", True, "UNMAPPED", "AMBIGUOUS_OBSERVATION"),
    ],
)
def test_v3_mapping_checks_evidence_and_conflicts_instead_of_label_length(
    label,
    ambiguous,
    expected,
    reason,
):
    source = native_sources(
        prose_pdf(["2-Winding Transformer", label, "350", "TAG: 80T1"]),
        "EQUIPMENT_RECOGNITION",
    )
    recognized = convert_engineering(recognition(source), source, distributed=True)
    later = replace(
        source, stage="ATTRIBUTE_EXTRACTION", unit_key="ATTRIBUTE_EXTRACTION:page:000001"
    )
    observation = attribute(later, label, "350", "kVA", "rated_apparent_power")
    if ambiguous:
        observation.update(ambiguous=True, ambiguity_reason="Equipment rating role is unclear")
    output = convert_engineering(
        attributes(observation),
        later,
        recognized,
        distributed=True,
    )
    value = output.candidates[0]
    assert value.mapping_status == expected
    assert value.reason_code == reason
    assert value.raw_value == "350" and value.raw_unit == "kVA"
    assert value.diagnostics["observation"]["proposed_attribute_key"] == "rated_apparent_power"
    assert value.numeric_value == (350 if expected == "MAPPED" else None)


@pytest.mark.parametrize(
    ("reading", "expected"),
    [
        ("kVA: 350", "MAPPED"),
        ("kVA: 350 kVA", "MAPPED"),
        ("kVA: 350 MAX", "UNMAPPED"),
        ("kVA: 350 MIN.", "UNMAPPED"),
        ("kVA: 350 fan cooled", "UNMAPPED"),
        ("350 kVA:", "UNMAPPED"),
        ("kVA: 350 / 350", "UNMAPPED"),
        ("kVA: 350.5", "UNMAPPED"),
        ("kVA: 350; Secondary: 600 V", "UNMAPPED"),
    ],
)
def test_shared_source_reading_uses_unique_ordered_substrings(monkeypatch, reading, expected):
    from powerforge_extraction import enrichment_prepare

    extract_native = enrichment_prepare.extract_native

    def combined_reading(data, page_number):
        native = extract_native(data, page_number)
        # Supply a combined extractor reading before constructing the immutable artifact.
        return replace(
            native,
            readings=tuple(
                replace(item, text=reading) if item.text == "FIELD" else item
                for item in native.readings
            ),
        )

    monkeypatch.setattr(enrichment_prepare, "extract_native", combined_reading)
    source = native_sources(
        prose_pdf(["2-Winding Transformer", "FIELD", "TAG: 80T1"]),
        "EQUIPMENT_RECOGNITION",
    )
    recognized = convert_engineering(recognition(source), source, distributed=True)
    later = replace(
        source, stage="ATTRIBUTE_EXTRACTION", unit_key="ATTRIBUTE_EXTRACTION:page:000001"
    )
    ref = next(item.model.ref for item in later.readings if item.text == reading)
    anchors = [
        dict(role=role, quote=quote, source_ref="spatial_readings", reading_refs=[ref])
        for role, quote in (("LABEL", "kVA:"), ("VALUE", "350"))
    ]
    claim = dict(
        local_ref="combined",
        raw_expression="kVA: 350",
        equipment_ref="eq1",
        anchors=anchors,
        source_label="kVA:",
        raw_value="350",
        raw_unit="kVA",
        proposed_equipment_type=TRANSFORMER,
        proposed_attribute_key="rated_apparent_power",
        ambiguous=False,
        ambiguity_reason=None,
    )
    output = convert_engineering(attributes(claim), later, recognized, distributed=True)
    assert output.candidates[0].mapping_status == expected
    if reading.endswith(("MAX", "MIN.", "fan cooled")):
        candidate = output.candidates[0]
        assert candidate.reason_code == "QUALIFIED_VALUE_RETAINED"
        assert candidate.numeric_value is None and candidate.raw_value == "350"
        assert candidate.raw_text == reading
        assert any(e.source_snippet == reading for e in output.evidence)
    if expected == "MAPPED":
        candidate = output.candidates[0]
        assert candidate.numeric_value == 350
        assert candidate.diagnostics["relationship_basis"] == "SAME_SOURCE_LINE"
        label, value = candidate.diagnostics["evidence_parts"]
        assert label["evidence_ids"] == value["evidence_ids"]
        assert any(e.source_snippet == reading for e in output.evidence)


@pytest.mark.parametrize("conflict", [None, "competing_panel", "unscoped_breakers"])
def test_title_block_designates_panelboard_with_two_installed_branch_breakers(conflict):
    from powerforge_extraction.enriched_grounding import line_groups, render

    first = "1 LV Breaker GBH3020"
    second = "2 LV Breaker GBH3020"
    branch_heading = "Installed Branch Breakers" if conflict != "unscoped_breakers" else "Devices"
    rows = ["Panelboard", "Main Lugs Only", branch_heading, first, second]
    if conflict == "competing_panel":
        rows.append("Second Panelboard")
    sources = native_sources(
        prose_pdf([*rows, "DESIGNATION: CDP-6C"]),
        "EQUIPMENT_RECOGNITION",
    )
    panel = dict(
        local_ref="panel",
        raw_expression="Panelboard",
        anchors=[part(sources, "EQUIPMENT", "Panelboard"), part(sources, "TAG", "CDP-6C")],
        observed_tag="CDP-6C",
        observed_name=None,
        proposed_equipment_type="BUS",
        ambiguous=False,
        ambiguity_reason=None,
    )

    def breaker(ref, text):
        row = next(row for row in line_groups(sources).values() if render(row) == text)
        return {
            **panel,
            "local_ref": ref,
            "raw_expression": text,
            "proposed_equipment_type": "LV_BREAKER",
            # A mistaken designation proposal still has exact text evidence.
            "anchors": [
                dict(
                    role="EQUIPMENT",
                    quote=text,
                    source_ref="spatial_readings",
                    reading_refs=[r.model.ref for r in row],
                ),
                part(sources, "TAG", "CDP-6C"),
            ],
        }

    response = SemanticEquipmentResponse.model_validate(
        dict(
            schema_version="equipment-recognition-schema-v3",
            overflowed=False,
            equipment=[panel, breaker("branch_1", first), breaker("branch_2", second)],
        )
    )
    output = convert_engineering(response, sources, distributed=True)
    host, left, right = output.candidates
    assert host.equipment_type_key == "BUS"
    assert host.observed_tag == ("CDP-6C" if conflict is None else None)
    assert left.equipment_type_key == right.equipment_type_key == "LV_BREAKER"
    assert left.observed_tag is None and right.observed_tag is None
    assert left.source_group_id != right.source_group_id
    if conflict is None:
        assert host.diagnostics["relationship_basis"] == "EXPLICIT_PANELBOARD_DESIGNATION"
        assert host.diagnostics["designation_context_evidence_ids"]
