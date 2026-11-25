"""The installed Phase 6R profile owns the only AI execution manifest."""

import json

import pytest

from powerforge_extraction.extraction_profile import KEY, STAGES, extraction_profile
from powerforge_extraction.profiles import read_profile, resolve_profile
from powerforge_shared.config import Settings


def test_profile_round_trips_and_rejects_pinned_manifest_drift():
    settings = Settings(_env_file=None, extraction_use_fake_provider=True)
    profile = resolve_profile(KEY, settings)
    assert profile.provider == "fake"
    assert profile.prompt_version == "phase-6r-stages-v10"
    assert profile.stages == STAGES
    assert read_profile(json.loads(profile.model_dump_json())) == profile
    stored = profile.model_dump(mode="json")
    stored["manifest"]["stages"][0]["schema_hash"] = "0" * 64
    with pytest.raises(ValueError, match="resources"):
        read_profile(stored)
    assert extraction_profile(
        settings.model_copy(update={"extraction_max_calls": 2})
    ).identity_hash != (profile.identity_hash)


@pytest.mark.parametrize(
    "previous_version",
    [
        "phase-6r-publication-v1",
        "phase-6r-publication-v2",
        "phase-6r-publication-v3",
        "phase-6r-publication-v4",
        "phase-6r-publication-v5",
        "phase-6r-publication-v6",
        "phase-6r-publication-v7",
        "phase-6r-publication-v8",
        "phase-6r-publication-v9",
        "phase-6r-publication-v10",
    ],
)
def test_previous_publication_pin_cannot_be_loaded_for_execution(previous_version):
    profile = extraction_profile(Settings(_env_file=None, extraction_use_fake_provider=True))
    assert profile.manifest["publication_version"] == "phase-6r-publication-v11"
    assert profile.manifest["unit_interpretation_version"] == "source-unit-interpretation-v3"
    assert profile.schema_version == profile.manifest["version"] == "phase-6r-wire-v7"
    assert [stage["version"] for stage in profile.manifest["stages"]] == [
        "phase-6r-v1",
        "phase-6r-attributes-v7",
    ]
    previous = profile.model_copy(
        update={"manifest": {**profile.manifest, "publication_version": previous_version}}
    )
    assert previous.identity_hash != profile.identity_hash
    with pytest.raises(ValueError, match="Pinned extraction resources"):
        read_profile(previous.model_dump(mode="json"))
    assert read_profile(profile.model_dump(mode="json")) == profile


def test_previous_attribute_input_pin_cannot_be_loaded_for_execution():
    profile = extraction_profile(Settings(_env_file=None, extraction_use_fake_provider=True))
    assert profile.manifest["attribute_input_version"] == "compact-page-v1"
    stored = profile.model_dump(mode="json")
    del stored["manifest"]["attribute_input_version"]
    with pytest.raises(ValueError, match="Pinned extraction resources"):
        read_profile(stored)


@pytest.mark.parametrize("version", [f"execution-profile-v{i}" for i in range(1, 7)])
def test_legacy_profile_versions_are_not_readable(version):
    with pytest.raises(ValueError, match="Unsupported pinned"):
        read_profile({"version": version})


@pytest.mark.parametrize(
    "key",
    [
        "infrastructure-fake-v1",
        "infrastructure-openai-v1",
        "engineering-openai-v1",
        "engineering-openai-text-v1",
        "engineering-test-v1",
        "engineering-test-text-v1",
        "tables-openai-v1",
        "tables-openai-text-v1",
        "tables-test-v1",
        "tables-test-text-v1",
        "engineering-openai-enriched-v1",
        "engineering-test-enriched-v1",
        "tables-openai-enriched-v1",
        "tables-test-enriched-v1",
    ],
)
def test_legacy_profile_keys_are_not_admitted(key):
    with pytest.raises(ValueError, match="Unknown extraction profile"):
        resolve_profile(key, Settings(_env_file=None))


def test_v6_wire_pin_is_rejected_by_v7_execution_profile():
    profile = extraction_profile(Settings(_env_file=None, extraction_use_fake_provider=True))
    stored = profile.model_dump(mode="json")
    stored["schema_version"] = "phase-6r-wire-v6"
    with pytest.raises(ValueError, match="phase-6r-wire-v7"):
        read_profile(stored)


def test_reasoning_policy_is_optional_only_for_legacy_and_fake_runs():
    from powerforge_extraction.extraction_profile import STAGES, stage_request_hash
    from powerforge_extraction.identities import content_hash, identity_hash

    hashes = set()
    for effort in ("medium", "low", "none"):
        profile = extraction_profile(
            Settings(_env_file=None, extraction_attribute_reasoning_effort=effort)
        )
        assert profile.attribute_reasoning.version == "openai-stage2-effort-v1"
        assert profile.reasoning_effort_for(STAGES[0]) is None
        assert profile.reasoning_effort_for(STAGES[1]) == effort
        stored = profile.model_dump(mode="json")
        assert read_profile(stored).identity_hash == profile.identity_hash
        hashes.add(profile.identity_hash)
    assert len(hashes) == 3

    del stored["attribute_reasoning"]
    legacy = read_profile(stored)
    assert legacy.reasoning_effort_for(STAGES[1]) is None
    assert legacy.identity_hash == identity_hash(stored)
    assert stage_request_hash("test", None) == content_hash("test")
    assert len({stage_request_hash("test", effort) for effort in ("medium", "low", "none")}) == 3
    fake = extraction_profile(Settings(_env_file=None, extraction_use_fake_provider=True))
    assert fake.reasoning_effort_for(STAGES[1]) is None


def test_unsupported_model_and_invalid_policy_fail_early():
    from pydantic import ValidationError

    from powerforge_extraction.errors import ExtractionDisabled

    with pytest.raises(ValidationError):
        Settings(_env_file=None, extraction_attribute_reasoning_effort="high")
    with pytest.raises(ExtractionDisabled, match="unsupported"):
        extraction_profile(Settings(_env_file=None, extraction_model="unsupported-model"))
    profile = extraction_profile(Settings(_env_file=None))
    configuration = profile.model_dump(mode="json")
    configuration["model"] = "unsupported-model"
    with pytest.raises(ValidationError, match="Unsupported model"):
        read_profile(configuration)


def test_compact_v2_profile_pins_its_prompt_and_keeps_v1_runnable():
    from powerforge_extraction.extraction_profile import STAGES

    settings = Settings(_env_file=None)
    baseline = extraction_profile(settings)
    candidate = extraction_profile(
        settings.model_copy(update={"extraction_attribute_input_version": "compact-page-v2"})
    )
    assert baseline.manifest["attribute_input_version"] == "compact-page-v1"
    assert candidate.manifest["attribute_input_version"] == "compact-page-v2"
    assert candidate.prompt_version == "phase-6r-stages-v11"
    assert candidate.identity_hash != baseline.identity_hash
    assert candidate.instructions_for(STAGES[0]) == baseline.instructions_for(STAGES[0])
    assert candidate.instructions_for(STAGES[1]) != baseline.instructions_for(STAGES[1])
    for profile in (baseline, candidate):
        assert read_profile(profile.model_dump(mode="json")) == profile
    mixed = candidate.model_dump(mode="json")
    mixed["manifest"]["attribute_input_version"] = "compact-page-v1"
    with pytest.raises(ValueError, match="Pinned extraction resources"):
        read_profile(mixed)


@pytest.mark.parametrize(
    "source,guide",
    [
        ("compact-page-v1", "page.readings and page.layout.order"),
        ("compact-page-v2", "Half-open Unicode offsets"),
        ("readable-hybrid-v1", "The high-detail image"),
        ("image-only-v1", "Do not cite READING"),
        ("readable-text-v1", "Do not cite VISUAL"),
    ],
)
def test_d0_prompt_and_catalog_pins_are_independent_of_source(source, guide):
    settings = Settings(_env_file=None, extraction_attribute_input_version=source)
    baseline = extraction_profile(settings)
    core = extraction_profile(
        settings.model_copy(update={"extraction_attribute_prompt_variant": "core-v1"})
    )
    consolidated = extraction_profile(
        settings.model_copy(update={"extraction_attribute_prompt_variant": "core-catalog-v1"})
    )
    assert len({p.identity_hash for p in (baseline, core, consolidated)}) == 3
    assert core.instructions_for(STAGES[1]) == consolidated.instructions_for(STAGES[1])
    assert guide in core.instructions_for(STAGES[1])
    assert core.instructions_for(STAGES[1]).count("## Source format") == 1
    assert core.manifest["catalog_hash"] == baseline.manifest["catalog_hash"]
    assert consolidated.manifest["catalog_hash"] != core.manifest["catalog_hash"]
    assert (
        core.request_digest_for(STAGES[1])
        == consolidated.request_digest_for(STAGES[1])
        == "responses-body-v1"
    )
    for profile in (core, consolidated):
        assert read_profile(json.loads(profile.model_dump_json())) == profile
        assert profile.manifest["stages"][0] == baseline.manifest["stages"][0]
        assert profile.instructions_for(STAGES[0]) == baseline.instructions_for(STAGES[0])
        assert profile.request_digest_for(STAGES[0]) == "responses-body-v1"
        for digest in ("schema_hash", "transport_schema_hash"):
            assert profile.manifest["stages"][1][digest] == baseline.manifest["stages"][1][digest]
        for digest in ("attribute_core_hash", "source_guidance_hash", "catalog_hash"):
            tampered = profile.model_dump(mode="json")
            tampered["manifest"][digest] = "0" * 64
            with pytest.raises(ValueError, match="Pinned extraction resources"):
                read_profile(tampered)


def test_profiles_without_the_recognition_provider_contract_fail_closed():
    profile = extraction_profile(Settings(_env_file=None))
    pinned = profile.model_dump(mode="json")
    assert pinned["manifest"].pop("recognition_provider_version") == "server-owned-recognition-v1"
    with pytest.raises(ValueError, match="Pinned extraction resources"):
        read_profile(pinned)


@pytest.mark.parametrize(
    "source",
    [
        "compact-page-v1",
        "compact-page-v2",
        "readable-hybrid-v1",
        "image-only-v1",
        "readable-text-v1",
    ],
)
@pytest.mark.parametrize("variant", ["legacy", "core-v1", "core-catalog-v1"])
def test_compact_output_is_pinned_independently_and_preserves_stage_one(source, variant):
    from powerforge_extraction.compact_output import OUTPUT_VERSION
    from powerforge_extraction.extraction_profile import (
        BODY_DIGEST_VERSION,
        prompt_bundle,
        structured_schema,
    )

    settings = Settings(
        _env_file=None,
        extraction_attribute_input_version=source,
        extraction_attribute_prompt_variant=variant,
    )
    legacy = extraction_profile(settings)
    candidate = extraction_profile(
        settings.model_copy(
            update={"extraction_attribute_output_version": OUTPUT_VERSION},
        )
    )
    assert read_profile(candidate.model_dump(mode="json")) == candidate
    assert read_profile(legacy.model_dump(mode="json")) == legacy
    assert candidate.manifest["stages"][0] == legacy.manifest["stages"][0]
    assert candidate.manifest["catalog_hash"] == legacy.manifest["catalog_hash"]
    assert candidate.identity_hash != legacy.identity_hash
    assert candidate.request_digest_for(STAGES[1]) == BODY_DIGEST_VERSION
    assert (
        candidate.manifest["stages"][1]["transport_schema_hash"]
        != (legacy.manifest["stages"][1]["transport_schema_hash"])
    )
    schema = structured_schema(candidate.response_model_for(STAGES[1]).model_json_schema())
    assert "local_ref" not in json.dumps(schema) and '"kind"' not in json.dumps(schema)
    assert "reading" in json.dumps(schema) and "reported_text" in json.dumps(schema)
    _, prompts = prompt_bundle(source, variant, OUTPUT_VERSION)
    assert "Omit local_ref" in prompts[STAGES[1]]
    assert "Use unique local_ref" not in prompts[STAGES[1]]
    assert "Use distinct local_ref" not in prompts[STAGES[1]]


def test_reliability_schema_preserves_legacy_fields_order_and_discriminators():
    from powerforge_extraction.extraction_profile import structured_schema
    from powerforge_extraction.server_owned_output import ServerOwnedAttributeResponse
    from powerforge_extraction.stage_contracts import AttributeProviderResponse

    legacy = AttributeProviderResponse.model_json_schema()
    candidate = ServerOwnedAttributeResponse.model_json_schema()
    for name in ("RegistryAssertion", "InferredAssertion", "RawUnmappedAssertion"):
        expected = legacy["$defs"][name]
        actual = candidate["$defs"][f"Provider{name}"]
        assert list(actual["properties"]) == [
            key for key in expected["properties"] if key != "local_ref"
        ]
        assert actual["properties"] == {
            key: value for key, value in expected["properties"].items() if key != "local_ref"
        }
        assert actual["required"] == [key for key in expected["required"] if key != "local_ref"]
    assert list(candidate["properties"]) == list(legacy["properties"])
    assert candidate["properties"]["attributes"]["maxItems"] == 512
    assert candidate["properties"]["raw_unmapped"]["maxItems"] == 32
    for name in ("ReadingCitation", "QuoteCitation", "VisualCitation"):
        assert structured_schema(candidate["$defs"][name]) == structured_schema(
            legacy["$defs"][name]
        )


@pytest.mark.parametrize(
    "input_version",
    [
        "compact-page-v1",
        "compact-page-v2",
        "readable-hybrid-v1",
        "image-only-v1",
        "readable-text-v1",
    ],
)
@pytest.mark.parametrize("variant", ["legacy", "core-v1", "core-catalog-v1"])
def test_reliability_prompt_and_profile_pins(input_version, variant):
    from powerforge_extraction.extraction_profile import BODY_DIGEST_VERSION

    settings = Settings(
        _env_file=None,
        extraction_attribute_input_version=input_version,
        extraction_attribute_prompt_variant=variant,
    )
    legacy = extraction_profile(settings)
    candidate = extraction_profile(
        settings.model_copy(
            update={"extraction_attribute_output_version": "server-owned-assertions-v1"},
        )
    )
    assert read_profile(candidate.model_dump(mode="json")) == candidate
    assert candidate.manifest["stages"][0] == legacy.manifest["stages"][0]
    assert candidate.manifest["catalog_hash"] == legacy.manifest["catalog_hash"]
    assert candidate.request_digest_for(STAGES[1]) == BODY_DIGEST_VERSION
    assert (
        candidate.manifest["stages"][1]["transport_schema_hash"]
        != (legacy.manifest["stages"][1]["transport_schema_hash"])
    )
    candidate_prompt = candidate.instructions_for(STAGES[1])
    identity = (
        "PowerForge assigns assertion identifiers. "
        "Do not include `local_ref` in either response collection."
    )
    allowed = (
        "Return at most 12 evidence citations per assertion and 512 registry-linked assertions.\n"
    )
    allowed += (
        "Return at most 16 raw-unmapped assertions, prioritizing the most meaningful observations."
    )
    assert identity in candidate_prompt
    if variant == "legacy":
        restored = candidate_prompt.replace(
            identity, "Use distinct local_ref values across both lists."
        )
    else:
        assert allowed in candidate_prompt
        restored = candidate_prompt.replace(
            identity, "Use unique local_ref values across both response collections."
        )
        restored = restored.replace(
            allowed,
            (
                "Return at most 12 evidence citations per assertion, "
                "512 registry-linked assertions and 16\n"
                "raw-unmapped assertions."
            ),
        )
    assert restored == legacy.instructions_for(STAGES[1])
