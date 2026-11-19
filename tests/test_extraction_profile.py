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
    ],
)
def test_previous_publication_pin_cannot_be_loaded_for_execution(previous_version):
    profile = extraction_profile(Settings(_env_file=None, extraction_use_fake_provider=True))
    assert profile.manifest["publication_version"] == "phase-6r-publication-v6"
    assert profile.manifest["unit_interpretation_version"] == "source-unit-interpretation-v2"
    assert profile.schema_version == profile.manifest["version"] == "phase-6r-wire-v4"
    assert [stage["version"] for stage in profile.manifest["stages"]] == [
        "phase-6r-v1",
        "phase-6r-attributes-v4",
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
