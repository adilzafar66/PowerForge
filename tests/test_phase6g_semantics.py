"""Synthetic evidence, semantic decisions and frozen profile dispatch."""

from dataclasses import replace
from pathlib import Path

import pytest

from enriched_pure_support import fake, native_sources, table_interpretation
from powerforge_extraction.enriched_profiles import (
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


@pytest.mark.parametrize("label", ["kVA:", "Continuous transfer duty (kVA)"])
def test_split_native_field_maps_from_proposal_even_after_unmapped_recognition(label):
    sources = native_sources(
        prose_pdf(["2-Winding Transformer", label, "350", "TAG: 80T1"]),
        "EQUIPMENT_RECOGNITION",
    )
    recognized = convert_engineering(recognition(sources, mapped=False), sources)
    assert recognized.candidates[0].mapping_status == "UNMAPPED"
    assert recognized.candidates[0].observed_tag == "80T1"
    if label.startswith("Continuous"):
        assert _attribute(TRANSFORMER, label, InterpretationContext(label)) is None
    later = replace(
        sources, stage="ATTRIBUTE_EXTRACTION", unit_key="ATTRIBUTE_EXTRACTION:page:000001"
    )
    output = convert_engineering(
        attributes(attribute(later, label, "350", "kVA", "rated_apparent_power")),
        later,
        recognized,
    )
    value = output.candidates[0]
    assert value.mapping_status == "MAPPED" and value.numeric_value == 350
    assert value.attribute_key == "rated_apparent_power"
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
@pytest.mark.parametrize("family", ["engineering", "tables"])
def test_successor_execution_publishes_via_existing_attempts(native_ctx, family):
    import json
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
    run = start_enriched(ctx, binding, profile=f"{family}-openai-enriched-v2")
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
            if model is SemanticEquipmentResponse:
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


def test_operation_opt_in_preserves_the_profile_hash_of_existing_consent():
    from powerforge_extraction.operation_plan import operation_profiles, pinned_operation_profile

    settings = Settings(_env_file=None)
    historical = operation_profiles(settings, ("engineering", "tables"))
    settings.extraction_operation_semantic_profiles = True
    successor = operation_profiles(settings, ("engineering", "tables"))
    assert [p.key for p in successor] == list(SEMANTIC_PROFILES)
    for family, profile in zip(("engineering", "tables"), historical, strict=True):
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
