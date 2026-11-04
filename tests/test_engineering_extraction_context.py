"""Compare generated extraction context to the independent approved registry reference."""

import json
from pathlib import Path

import pytest

from powerforge_engineering_model.registry import get_attribute_definition, get_equipment_definition
from powerforge_extraction.engineering_stages import engineering_manifest, get_engineering_stage
from powerforge_extraction.identities import canonical_json, content_hash, identity_hash
from powerforge_extraction.registry_context import (
    MAX_CONTEXT_BYTES,
    attribute_context,
    equipment_catalog,
    registry_projection_hash,
)
from powerforge_extraction.terminology import TERMINOLOGY, terminology_hash

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = json.loads(
    (ROOT / "docs/specs/registry/PowerForge_registry-v1_reference.json").read_text()
)


def test_context_covers_all_types_and_attributes_against_approved_snapshot():
    expected = {equipment["key"]: equipment for equipment in REFERENCE["equipment_types"]}
    catalog = equipment_catalog()
    assert {item["key"]: item["display_name"] for item in catalog["equipment_types"]} == {
        key: item["display_name"] for key, item in expected.items()
    }
    context = attribute_context(expected)
    assert len(context["equipment_types"]) == 20
    assert {item["key"] for item in context["equipment_types"]} == set(expected)
    assert sum(len(item["attributes"]) for item in context["equipment_types"]) == 296
    for equipment in context["equipment_types"]:
        attributes = {item["key"]: item for item in expected[equipment["key"]]["attributes"]}
        assert len(equipment["attributes"]) == len(attributes)
        assert {item["key"] for item in equipment["attributes"]} == set(attributes)
        for generated in equipment["attributes"]:
            original = attributes[generated["key"]]
            assert {
                key: value for key, value in generated.items() if key != "supported_input_units"
            } == {key: original[key] for key in generated if key != "supported_input_units"}
    assert len(canonical_json(context).encode()) <= MAX_CONTEXT_BYTES
    assert registry_projection_hash() == identity_hash(context)


def test_targeted_context_is_canonical_and_empty_selection_keeps_isolated_observations_possible():
    first = attribute_context(["CABLE", "LV_BREAKER", "CABLE"])
    second = attribute_context(["LV_BREAKER", "CABLE"])
    assert canonical_json(first) == canonical_json(second)
    assert [item["key"] for item in first["equipment_types"]] == ["CABLE", "LV_BREAKER"]
    assert attribute_context([])["equipment_types"] == []
    assert len(attribute_context([])["type_catalog"]) == 20
    with pytest.raises(ValueError):
        attribute_context(["UNREGISTERED_FLUX_CONDITIONER"])
    first["equipment_types"][0]["attributes"][0]["notes"] = "mutation"
    assert attribute_context(["CABLE", "LV_BREAKER"]) == second


def test_supported_units_retain_registry_semantic_distinctions():
    context = attribute_context(["INDUCTION_MOTOR", "STATIC_LOAD", "TWO_WINDING_TRANSFORMER"])
    units = {
        (equipment["key"], item["key"]): item["supported_input_units"]
        for equipment in context["equipment_types"]
        for item in equipment["attributes"]
    }
    assert "hp" in units["INDUCTION_MOTOR", "rated_active_power"]
    assert "hp" not in units["STATIC_LOAD", "rated_active_power"]
    assert units["TWO_WINDING_TRANSFORMER", "positive_sequence_impedance"] == ["%"]


def test_small_scoped_terminology_policy_only_proposes_real_registry_targets():
    assert len({entry.key for entry in TERMINOLOGY}) == len(TERMINOLOGY)
    for entry in TERMINOLOGY:
        get_equipment_definition(entry.equipment_type)
        assert entry.expressions and entry.qualification
        if entry.attribute_key:
            definition = get_attribute_definition(entry.equipment_type, entry.attribute_key)
            if entry.enum_value:
                assert entry.enum_value in definition.allowed_values
    assert len(terminology_hash()) == 64


def test_stage_context_changes_rendered_identity_without_changing_template_identity():
    stage = get_engineering_stage("ATTRIBUTE_EXTRACTION")
    transformer = stage.render_instructions(["TWO_WINDING_TRANSFORMER"])
    cable = stage.render_instructions(["CABLE"])
    assert transformer.instruction_hash != cable.instruction_hash
    assert transformer.context_hash != cable.context_hash
    assert transformer.instruction_hash == content_hash(transformer.text)
    assert transformer == stage.render_instructions(["TWO_WINDING_TRANSFORMER"])
    assert stage.render_instructions(["CABLE", "LV_BREAKER"]) == stage.render_instructions(
        ["LV_BREAKER", "CABLE", "CABLE"]
    )
    assert len(canonical_json(engineering_manifest()).encode()) < 64000


def test_recognition_always_uses_complete_catalog_and_unknown_versions_never_fall_back():
    stage = get_engineering_stage("EQUIPMENT_RECOGNITION")
    with pytest.raises(ValueError, match="complete equipment catalog"):
        stage.render_instructions(["CABLE"])
    for key, version in [
        ("TABLE_EXTRACTION", "engineering-stage-manifest-v1"),
        ("EQUIPMENT_RECOGNITION", "engineering-stage-manifest-v999"),
    ]:
        with pytest.raises(ValueError, match="Unsupported engineering stage/version"):
            get_engineering_stage(key, version)
