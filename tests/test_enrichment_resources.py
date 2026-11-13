"""New preparation identities and retained historical inputs; no gold regeneration."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from powerforge_extraction.enrichment_profiles import (
    PreparationProfile,
    preparation_profile,
    preparation_rules,
    require_preparation,
)
from powerforge_extraction.profiles import read_profile, resolve_profile
from powerforge_provenance.spatial_base import identity_hash
from powerforge_shared.config import Settings

ROOT = Path(__file__).resolve().parents[1]
RECORD = json.loads(
    (ROOT / "tests/fixtures/enrichment/preparation_v1_environment.json").read_text()
)


def test_retained_preparation_identity_and_v4_archive_are_pinned():
    from powerforge_provenance.spatial_base import POLICY

    # Reconstruct the historical policy over the frozen preparation source inputs.
    # The active profile includes the current policy and must reject the old digest.
    archive = (
        ROOT / "packages/extraction/src/powerforge_extraction/runtime_resources/preparation_v1"
    )
    archived_sources = {
        path.stem + ".py": hashlib.sha256(path.read_bytes()).hexdigest()
        for path in archive.glob("*.txt")
    }
    old_policy = dict(POLICY) | {"max_native_primitives": 2048}
    assert identity_hash(archived_sources | {"policy": old_policy}) == RECORD["preparation_rules"]
    assert POLICY["max_native_primitives"] == 5096
    assert identity_hash(archived_sources | {"policy": dict(POLICY)}) == preparation_rules()
    assert identity_hash(PreparationProfile.model_json_schema()) == RECORD["profile_schema"]
    archive = ROOT / "packages/extraction/src/powerforge_extraction/runtime_resources/table_v1"
    assert set(RECORD["retained_v4_inputs"]) == {p.name for p in archive.glob("*.txt")}
    for name, digest in RECORD["retained_v4_inputs"].items():
        assert hashlib.sha256((archive / name).read_bytes()).hexdigest() == digest


def test_pinned_local_wire_has_no_model_prompt_or_registry_and_round_trips():
    import pytest

    settings = Settings(
        _env_file=None,
        enrichment_enabled=True,
        enrichment_ocr_configuration=json.dumps(RECORD["configuration"]),
    )
    profile = preparation_profile(settings)
    require_preparation(profile)
    with pytest.raises(ValueError, match="Pinned preparation resources"):
        require_preparation(profile.model_copy(update={"rules_hash": RECORD["preparation_rules"]}))
    assert read_profile(json.loads(profile.model_dump_json())) == profile
    assert {"registry_version", "model", "prompt_version", "prompt_hash"}.isdisjoint(
        profile.model_dump()
    )
    with pytest.raises(ValueError):
        resolve_profile(profile.key, settings)


def test_native_preprocessing_adapter_imports_without_registry_extraction_or_api():
    script = """
import builtins
original=builtins.__import__
def check(name,*args,**kwargs):
    if name.split('.')[0] in {'fastapi','powerforge_extraction','powerforge_engineering_model'}:
        raise AssertionError('Domain/API dependency in source preparation: '+name)
    return original(name,*args,**kwargs)
builtins.__import__=check
from powerforge_document_processing.native_spatial import extract_native,native_identity
assert native_identity()['engine_version']=='1.28.2'
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
