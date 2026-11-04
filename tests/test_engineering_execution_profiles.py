"""Versioned replay and provider neutrality, without any model/network calls."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from powerforge_extraction.profiles import (
    ENGINEERING_TEST_PROFILE,
    ENGINEERING_TEXT_TEST_PROFILE,
    EngineeringProfile,
    engineering_profile,
    read_profile,
)
from powerforge_extraction.stage_runtime import require_supported
from powerforge_shared.config import Settings


def test_profile_readers_preserve_legacy_wire_bytes_and_replay_v2_without_latest_fallback():
    legacy = json.loads(
        (Path(__file__).parent / "fixtures/extraction/legacy_source_probe_v1.json").read_text()
    )
    for snapshot in legacy["profiles"].values():
        profile = read_profile(json.loads(snapshot["wire_json"]))
        assert profile.model_dump_json() == snapshot["wire_json"]
        assert profile.identity_hash == snapshot["identity_hash"]
    settings = Settings(_env_file=None, **legacy["settings"])
    pinned = json.loads(
        (
            Path(__file__).parent / "fixtures/extraction/engineering_execution_v1_identity.json"
        ).read_text()
    )
    for key in (ENGINEERING_TEST_PROFILE, ENGINEERING_TEXT_TEST_PROFILE):
        profile = engineering_profile(key, settings)
        wire = profile.model_dump(mode="json")
        restored = read_profile(wire)
        assert isinstance(restored, EngineeringProfile)
        assert restored.identity_hash == profile.identity_hash
        assert profile.runtime == pinned["runtime"]
        assert profile.identity_hash == pinned["profiles"][key]
        assert len(profile.model_dump_json().encode()) < 64000
        require_supported(restored)
        wire["runtime"] = {"version": "future"}
        with pytest.raises(ValueError, match="unavailable"):
            require_supported(read_profile(wire))
    with pytest.raises(ValueError, match="version"):
        read_profile({"version": "execution-profile-v999"})


def test_provider_neutral_stage_envelopes_import_without_extraction_orm_or_sdk():
    script = """
import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in {'powerforge_extraction', 'sqlalchemy', 'openai', 'celery'}:
        raise AssertionError('Unexpected import: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from pydantic import BaseModel, ConfigDict
from powerforge_ai.extraction import ExtractionResponse, ExecutionUsage
class StageResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    observations: list[str]
response = ExtractionResponse[StageResult](
    result={'observations': ['source']}, usage=ExecutionUsage()
)
assert response.model_dump()['result'] == {'observations': ['source']}
restored = ExtractionResponse[StageResult].model_validate(response.model_dump())
assert restored.result.observations == ['source']
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
