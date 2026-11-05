"""Independent table profile/runtime identity, settings and resource compatibility gates."""

import json
from pathlib import Path

import pytest

from powerforge_extraction.profiles import EngineeringProfile, read_profile, resolve_profile
from powerforge_extraction.stage_runtime import require_supported
from powerforge_extraction.table_profiles import (
    TABLE_OPENAI_PROFILE,
    TABLE_PROFILES,
    TableProfile,
    table_profile,
)
from powerforge_shared.config import Settings


@pytest.mark.parametrize("key", TABLE_PROFILES)
def test_v4_table_profiles_roundtrip_without_widening_v2_v3(key):
    profile = table_profile(key, Settings(_env_file=None))
    restored = read_profile(json.loads(profile.model_dump_json()))
    assert isinstance(restored, TableProfile) and not isinstance(restored, EngineeringProfile)
    assert restored.model_dump_json() == profile.model_dump_json()
    assert restored.identity_hash == profile.identity_hash
    assert profile.stages == ("TABLE_RECONSTRUCTION", "TABLE_INTERPRETATION")
    require_supported(restored)


@pytest.mark.parametrize("field", ["manifest", "grounding", "runtime", "adapter_hash"])
def test_unknown_table_resources_never_fall_back_to_prose(field):
    profile = table_profile(TABLE_OPENAI_PROFILE, Settings(_env_file=None))
    value = "future" if field == "adapter_hash" else {"version": "future"}
    with pytest.raises(ValueError, match="unavailable"):
        require_supported(profile.model_copy(update={field: value}))


@pytest.mark.parametrize(
    "setting,value",
    [
        ("extraction_tables_max_output_tokens", 16000),
        ("extraction_tables_max_total_input_bytes", 3000000),
        ("extraction_tables_max_text_chars", 20000),
        ("extraction_tables_max_upstream_bytes", 64000),
        ("extraction_tables_image_detail", "auto"),
        ("extraction_tables_reasoning_effort", "low"),
    ],
)
def test_table_settings_change_only_the_new_profile_identity(setting, value):
    a = Settings(_env_file=None)
    b = a.model_copy(update={setting: value})
    assert (
        table_profile(TABLE_OPENAI_PROFILE, a).identity_hash
        != table_profile(TABLE_OPENAI_PROFILE, b).identity_hash
    )
    for key in ["infrastructure-fake-v1", "engineering-test-v1", "engineering-openai-v1"]:
        assert (
            resolve_profile(key, a).model_dump_json() == resolve_profile(key, b).model_dump_json()
        )


def test_table_identity_fixture_and_retained_runtime_resources_reproduce():
    from importlib.resources import files

    from powerforge_extraction.identities import content_hash

    expected = json.loads(
        (Path(__file__).parent / "fixtures/extraction/table_execution_v1_identity.json").read_text()
    )
    settings = Settings(_env_file=None, **expected["settings"])
    root = files("powerforge_extraction").joinpath("runtime_resources/page_v2")
    assert {item.name: content_hash(item.read_text()) for item in root.iterdir()} == expected[
        "retained_resources"
    ]
    for key in TABLE_PROFILES:
        profile = table_profile(key, settings)
        assert profile.model_dump_json() == expected["profiles"][key]["wire_json"]
        assert profile.identity_hash == expected["profiles"][key]["identity_hash"]
