"""Pinned resource identities and isolation of the accepted infrastructure profiles."""

import json
import subprocess
import sys
from pathlib import Path

from powerforge_extraction.engineering_stages import STAGES, engineering_manifest
from powerforge_extraction.identities import canonical_json, content_hash, identity_hash
from powerforge_extraction.profiles import (
    FAKE_PROFILE,
    OPENAI_PROFILE,
    PROMPT_HASH,
    SCHEMA_HASH,
    ExecutionProfile,
    resolve_profile,
)
from powerforge_shared.config import Settings

FIXTURE_DIR = Path(__file__).parent / "fixtures/extraction"


def test_v1_engineering_resource_manifest_matches_pinned_definition():
    expected = json.loads((FIXTURE_DIR / "engineering_identities_v1.json").read_text())
    manifest = engineering_manifest()
    assert manifest == expected["manifest"]
    assert identity_hash(manifest) == expected["manifest_hash"]
    for stage in STAGES:
        rendered = stage.render_instructions()
        assert stage.template_hash == content_hash(stage.template)
        assert rendered.instruction_hash == expected["empty_context_instructions"][stage.key]
    # New resource content/schema/terminology versions must be introduced deliberately.


def test_accepted_probe_hashes_and_profile_wire_identities_remain_unchanged():
    # Captured before M1 from accepted 6B, with all profile-affecting settings explicit.
    expected = json.loads((FIXTURE_DIR / "legacy_source_probe_v1.json").read_text())
    settings = Settings(_env_file=None, **expected["settings"])
    assert PROMPT_HASH == expected["prompt_hash"]
    assert SCHEMA_HASH == expected["schema_hash"]
    for key in (FAKE_PROFILE, OPENAI_PROFILE):
        profile = resolve_profile(key, settings)
        snapshot = expected["profiles"][key]
        assert profile.model_dump_json() == snapshot["wire_json"]
        assert profile.identity_hash == snapshot["identity_hash"]
        assert (
            ExecutionProfile.model_validate_json(snapshot["wire_json"]).identity_hash
            == (snapshot["identity_hash"])
        )


def test_new_contracts_context_and_prompts_import_without_infrastructure_or_sdk():
    script = """
import builtins
original = builtins.__import__
blocked = {'sqlalchemy', 'fastapi', 'celery', 'boto3', 'openai', 'PIL', 'powerforge_api'}
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in blocked:
        raise AssertionError('Unexpected infrastructure import: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from powerforge_extraction.engineering_stages import engineering_manifest, get_engineering_stage
assert len(engineering_manifest()['stages']) == 2
assert get_engineering_stage('ATTRIBUTE_EXTRACTION').render_instructions(['CABLE']).text
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_canonical_hashing_is_unicode_exact_and_order_independent():
    assert identity_hash({"b": "é", "a": 1}) == identity_hash({"a": 1, "b": "é"})
    assert canonical_json({"b": "é", "a": 1}) == '{"a":1,"b":"é"}'
    assert content_hash("é") != content_hash("e\u0301")
