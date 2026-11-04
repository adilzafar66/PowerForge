"""Production discovery, explicit spending controls and reproducible versioned settings."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from documents_support import client
from engineering_execution_support import attempt, start_engineering
from engineering_execution_support import engineering_ctx as engineering_ctx
from engineering_execution_support import execution_ctx as execution_ctx
from extraction_execution_support import detail
from powerforge_extraction.execution import execute_unit
from powerforge_extraction.production_profiles import (
    ENGINEERING_OPENAI_PROFILE,
    ENGINEERING_OPENAI_TEXT_PROFILE,
    PRODUCTION_PROFILES,
    ProductionProfile,
    production_profile,
)
from powerforge_extraction.profiles import FAKE_PROFILE, read_profile, resolve_profile
from powerforge_extraction.stage_runtime import require_supported
from powerforge_shared.config import Settings


def test_production_profile_wire_limits_and_probe_identity_are_independent():
    pinned = json.loads(
        (
            Path(__file__).parent / "fixtures/extraction/engineering_production_v1_identity.json"
        ).read_text()
    )
    a = Settings(_env_file=None, **pinned["settings"])
    b = a.model_copy(update={"extraction_max_output_tokens": 16})
    for key in PRODUCTION_PROFILES:
        profile = production_profile(key, a)
        restored = read_profile(profile.model_dump(mode="json"))
        assert (
            isinstance(restored, ProductionProfile)
            and restored.identity_hash == profile.identity_hash
        )
        assert profile.runtime == pinned["runtime"]
        assert profile.identity_hash == pinned["profiles"][key]["identity_hash"]
        assert profile.model_dump_json() == pinned["profiles"][key]["wire_json"]
        require_supported(restored)
        assert profile.identity_hash == production_profile(key, b).identity_hash
        assert len(profile.model_dump_json().encode()) < 64000
        assert profile.max_output_tokens == 16384 and profile.image_detail == "high"
        assert profile.reasoning_effort == "none" and profile.provider == "openai"
        assert "openai_api_key" not in profile.model_dump_json()
    assert (
        resolve_profile(FAKE_PROFILE, a).identity_hash
        != resolve_profile(FAKE_PROFILE, b).identity_hash
    )


@pytest.mark.parametrize(
    "setting,value",
    [
        ("extraction_engineering_max_output_tokens", 12000),
        ("extraction_engineering_max_text_chars", 80000),
        ("extraction_engineering_reasoning_effort", "low"),
        ("extraction_engineering_image_detail", "auto"),
    ],
)
def test_material_production_settings_change_only_their_pinned_profile(setting, value):
    a = Settings(_env_file=None)
    b = a.model_copy(update={setting: value})
    assert (
        production_profile(ENGINEERING_OPENAI_PROFILE, a).identity_hash
        != production_profile(ENGINEERING_OPENAI_PROFILE, b).identity_hash
    )
    assert (
        resolve_profile(FAKE_PROFILE, a).model_dump_json()
        == resolve_profile(FAKE_PROFILE, b).model_dump_json()
    )


def test_production_profile_resolution_does_not_import_worker_or_vendor_sdk():
    script = """
import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in {'openai', 'extraction_worker'}:
        raise AssertionError('Unexpected SDK import: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from powerforge_extraction.production_profiles import production_profile
from powerforge_shared.config import Settings
profile = production_profile('engineering-openai-v1', Settings(_env_file=None))
assert profile.execution_kind == 'ENGINEERING_EXTRACTION'
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.integration
def test_production_discovery_disabled_defaults_and_explicit_start_use_existing_api_controls(
    engineering_ctx,
):
    ctx = engineering_ctx
    profiles = client.get(ctx["base"] + "/profiles").json()["items"]
    assert [p["key"] for p in profiles[:2]] == [
        "infrastructure-fake-v1",
        "infrastructure-openai-v1",
    ]
    production = [p for p in profiles if p["production_extractor"]]
    assert {p["key"] for p in production} == set(PRODUCTION_PROFILES)
    assert all(
        not p["enabled"] and p["execution_kind"] == "ENGINEERING_EXTRACTION" for p in production
    )
    for key in PRODUCTION_PROFILES:
        assert client.post(ctx["base"] + "/runs", json={"profile_key": key}).status_code == 409
    ctx["settings"].extraction_external_enabled = True
    profiles = client.get(ctx["base"] + "/profiles").json()["items"]
    assert all(p["enabled"] for p in profiles if p["production_extractor"])
    for key in PRODUCTION_PROFILES:
        result = start_engineering(ctx, profile_key=key)
        assert result["execution"]["execution_kind"] == "ENGINEERING_EXTRACTION"
        assert result["run"]["profile_version"] == "execution-profile-v3"
        assert len(result["attempts"]) == 2 and result["execution"]["calls_admitted"] == 0
    # Default remains the synthetic probe even when production is enabled.
    assert (
        client.post(ctx["base"] + "/runs", json={}).json()["execution"]["profile_key"]
        == FAKE_PROFILE
    )
    ctx["settings"].extraction_enabled = False
    assert not any(p["enabled"] for p in client.get(ctx["base"] + "/profiles").json()["items"])


@pytest.mark.integration
def test_missing_worker_credentials_fail_without_a_provider_call_or_source_leak(engineering_ctx):
    from extraction_worker.openai_extraction import OpenAIExtractionProvider

    ctx = engineering_ctx
    ctx["settings"].extraction_external_enabled = True
    rid = start_engineering(ctx, profile_key=ENGINEERING_OPENAI_TEXT_PROFILE)["run"]["id"]

    def missing(claim):
        return OpenAIExtractionProvider(
            Settings(_env_file=None, extraction_external_enabled=True, openai_api_key=None),
            profile=claim.profile,
        )

    assert execute_unit(
        attempt(ctx, rid, "EQUIPMENT_RECOGNITION"),
        ctx["factory"],
        ctx["storage"],
        ctx["settings"],
        missing,
    )
    result = detail(ctx, rid)
    assert result["run"]["status"] == "FAILED"
    assert (
        result["execution"]["reported_calls"] == result["execution"]["provider_calls_started"] == 0
    )
    assert any(u["error_code"] == "PROVIDER_AUTH_ERROR" for u in result["attempts"])
    assert "storage_key" not in json.dumps(result)
