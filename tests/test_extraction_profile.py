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
    assert profile.prompt_version == "phase-6r-stages-v9"
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
    ],
)
def test_previous_publication_pin_cannot_be_loaded_for_execution(previous_version):
    profile = extraction_profile(Settings(_env_file=None, extraction_use_fake_provider=True))
    assert profile.manifest["publication_version"] == "phase-6r-publication-v9"
    assert profile.manifest["unit_interpretation_version"] == "source-unit-interpretation-v3"
    assert profile.schema_version == profile.manifest["version"] == "phase-6r-wire-v6"
    assert [stage["version"] for stage in profile.manifest["stages"]] == [
        "phase-6r-v1",
        "phase-6r-attributes-v6",
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


def test_v5_wire_pin_is_rejected_by_v6_execution_profile():
    profile = extraction_profile(Settings(_env_file=None, extraction_use_fake_provider=True))
    stored = profile.model_dump(mode="json")
    stored["schema_version"] = "phase-6r-wire-v5"
    with pytest.raises(ValueError, match="phase-6r-wire-v6"):
        read_profile(stored)


def test_typed_wire_cannot_execute_before_publication_is_ready():
    from powerforge_extraction.extraction_profile import provider_available

    fake = Settings(_env_file=None, extraction_use_fake_provider=True, enrichment_enabled=True)
    live = Settings(_env_file=None, extraction_external_enabled=True)
    assert not provider_available(fake, "fake")
    assert not provider_available(live, "openai")
    assert provider_available(fake, "local")
