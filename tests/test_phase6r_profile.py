"""The installed Phase 6R profile owns the only AI execution manifest."""

import json

import pytest

from powerforge_extraction.phase6r_profile import KEY, STAGES, phase6r_profile
from powerforge_extraction.profiles import read_profile, resolve_profile
from powerforge_shared.config import Settings


def test_profile_round_trips_and_rejects_pinned_manifest_drift():
    settings = Settings(_env_file=None, extraction_phase6r_fake=True)
    profile = resolve_profile(KEY, settings)
    assert profile.provider == "fake"
    assert profile.stages == STAGES
    assert read_profile(json.loads(profile.model_dump_json())) == profile
    stored = profile.model_dump(mode="json")
    stored["manifest"]["stages"][0]["schema_hash"] = "0" * 64
    with pytest.raises(ValueError, match="resources"):
        read_profile(stored)
    assert phase6r_profile(
        settings.model_copy(update={"extraction_max_calls": 2})
    ).identity_hash != (profile.identity_hash)


@pytest.mark.parametrize("version", [f"execution-profile-v{i}" for i in range(1, 7)])
def test_legacy_profile_versions_are_not_readable(version):
    with pytest.raises(ValueError, match="Unsupported pinned"):
        read_profile({"version": version})


@pytest.mark.parametrize(
    "key",
    [
        "infrastructure-fake-v1",
        "engineering-openai-v1",
        "tables-openai-v1",
        "engineering-openai-enriched-v1",
    ],
)
def test_legacy_profile_keys_are_not_admitted(key):
    with pytest.raises(ValueError, match="Unknown extraction profile"):
        resolve_profile(key, Settings(_env_file=None))
