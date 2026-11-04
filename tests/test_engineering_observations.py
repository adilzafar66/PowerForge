"""Engineering response shape/reference checks; grounding and interpretation arrive in M2/M3."""

import copy
import json
from pathlib import Path

import pytest
from openai.lib._pydantic import to_strict_json_schema
from pydantic import ValidationError

from powerforge_extraction.engineering_stages import get_engineering_stage
from powerforge_extraction.observations import EquipmentRecognitionResponse

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures/extraction/engineering_observations_v1.json").read_text()
)["cases"]


@pytest.mark.parametrize("case", FIXTURES, ids=lambda case: case["id"])
def test_curated_observation_shapes_preserve_original_data(case):
    recognition = get_engineering_stage("EQUIPMENT_RECOGNITION").validate_result(
        case["recognition"], available_sources=case["available_sources"]
    )
    attributes = get_engineering_stage("ATTRIBUTE_EXTRACTION").validate_result(
        case["attributes"],
        available_sources=case["available_sources"],
        equipment_refs=[item.local_ref for item in recognition.equipment],
    )
    assert recognition.model_dump(mode="json") == case["recognition"]
    assert attributes.model_dump(mode="json") == case["attributes"]
    assert all(
        item.raw_value is None or type(item.raw_value) is str for item in attributes.attributes
    )


def test_model_proposals_are_not_registry_authority_or_normalized_values():
    unknown = next(case for case in FIXTURES if case["id"] == "unknown-equipment-and-attribute")
    result = get_engineering_stage("ATTRIBUTE_EXTRACTION").validate_result(
        unknown["attributes"], available_sources=["native_text"], equipment_refs=["eq1"]
    )
    assert result.attributes[0].proposed_attribute_key == "flux_alignment"
    assert result.attributes[0].raw_unit == "quux"
    assert result.attributes[0].ambiguous
    precision = next(case for case in FIXTURES if case["id"] == "cable-and-integer-precision")
    assert precision["attributes"]["attributes"][-1]["raw_value"] == "9007199254740993"
    false = next(case for case in FIXTURES if case["id"] == "breaker-distinct-ratings-and-false")
    assert false["attributes"]["attributes"][-1]["raw_value"] == "No"
    # M1 neither converts these source strings nor asserts their future mapping expectations.


@pytest.mark.parametrize(
    "failure",
    [
        "normalized_slot",
        "float_value",
        "boolean_value",
        "blank_expression",
        "duplicate_ref",
        "no_anchor",
        "forged_offset",
        "visual_quote",
        "native_role_mismatch",
        "unknown_source",
        "unavailable_source",
        "missing_equipment",
        "unknown_version",
        "overflow",
        "observation_count",
        "inconsistent_ambiguity",
        "missing_nullable_field",
    ],
)
def test_unsafe_or_malformed_responses_do_not_cross_stage_contract(failure):
    data = copy.deepcopy(FIXTURES[0]["attributes"])
    item = data["attributes"][0]
    anchor = item["anchors"][0]
    sources, equipment = ["native_text"], ["eq1"]
    if failure == "normalized_slot":
        item["numeric_value"] = "750"
    elif failure == "float_value":
        item["raw_value"] = 0.6
    elif failure == "boolean_value":
        item["raw_value"] = False
    elif failure == "blank_expression":
        item["raw_expression"] = " \n "
    elif failure == "duplicate_ref":
        data["attributes"][1]["local_ref"] = item["local_ref"]
    elif failure == "no_anchor":
        item["anchors"] = []
    elif failure == "forged_offset":
        anchor["text_start"] = 42
    elif failure == "visual_quote":
        anchor.update(kind="VISUAL_PAGE", source_ref="analysis_image")
        sources = ["analysis_image"]
    elif failure == "native_role_mismatch":
        anchor["source_ref"] = "analysis_image"
    elif failure == "unknown_source":
        anchor["source_ref"] = "another_document"
    elif failure == "unavailable_source":
        sources = ["analysis_image"]
    elif failure == "missing_equipment":
        equipment = []
    elif failure == "unknown_version":
        data["schema_version"] = "attribute-extraction-schema-v999"
    elif failure == "overflow":
        data["overflowed"] = True
    elif failure == "observation_count":
        data["attributes"] = [dict(item, local_ref=f"a{i}") for i in range(129)]
    elif failure == "inconsistent_ambiguity":
        item["ambiguous"] = True
    elif failure == "missing_nullable_field":
        del item["raw_unit"]
    with pytest.raises((ValidationError, ValueError)):
        get_engineering_stage("ATTRIBUTE_EXTRACTION").validate_result(
            data, available_sources=sources, equipment_refs=equipment
        )


def test_result_revalidation_detects_mutation_inside_frozen_model():
    stage = get_engineering_stage("EQUIPMENT_RECOGNITION")
    parsed = EquipmentRecognitionResponse.model_validate(FIXTURES[0]["recognition"])
    parsed.equipment.append(parsed.equipment[0])
    with pytest.raises(ValidationError, match="references must be unique"):
        stage.validate_result(parsed, available_sources=["native_text"])


def test_utf8_byte_bound_applies_even_with_legal_item_and_character_counts():
    data = copy.deepcopy(FIXTURES[0]["recognition"])
    item = data["equipment"][0]
    item["anchors"] = [dict(item["anchors"][0], quote="変" * 2000) for _ in range(8)]
    data["equipment"] = [dict(item, local_ref=f"eq{i}") for i in range(32)]
    with pytest.raises(ValidationError, match="byte limit"):
        EquipmentRecognitionResponse.model_validate(data)


def test_equal_tags_do_not_make_two_observation_references_the_same_equipment():
    data = copy.deepcopy(FIXTURES[0]["recognition"])
    second = dict(data["equipment"][0], local_ref="eq2")
    data["equipment"].append(second)
    result = EquipmentRecognitionResponse.model_validate(data)
    assert result.equipment[0].observed_tag == result.equipment[1].observed_tag
    assert len(result.equipment) == 2


def test_provider_schema_conversion_is_offline_and_keeps_closed_required_objects():
    for key in ("EQUIPMENT_RECOGNITION", "ATTRIBUTE_EXTRACTION"):
        schema = to_strict_json_schema(get_engineering_stage(key).response_model)
        assert schema["type"] == "object"
        for model in [schema, *schema.get("$defs", {}).values()]:
            if model.get("type") == "object":
                assert model["additionalProperties"] is False
                assert set(model["required"]) == set(model["properties"])
