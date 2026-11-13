"""Layout-only resources extend the frozen preparation and extraction identities."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from powerforge_document_processing.layout_derive import layout_rules_identity
from powerforge_extraction.enrichment_profiles import preparation_profile
from powerforge_extraction.layout_profiles import (
    SourceLayoutProfile,
    layout_execution_identity,
    layout_profile,
    require_layout,
)
from powerforge_extraction.profiles import read_profile, resolve_profile
from powerforge_provenance.layout_observations import layout_contract_identity
from powerforge_provenance.spatial_base import identity_hash
from powerforge_shared.config import Settings

FIXTURES = Path(__file__).resolve().parent / "fixtures/enrichment"


def test_layout_resources_are_pinned_separately_from_accepted_preparation():
    pinned = json.loads((FIXTURES / "layout_v2_identity.json").read_text())
    assert layout_contract_identity() == pinned["contracts"]
    assert layout_rules_identity() == pinned["algorithm_sha256"]
    assert layout_execution_identity() == pinned["execution_sha256"]
    assert identity_hash(SourceLayoutProfile.model_json_schema()) == pinned["profile_schema"]


def test_fixed_local_layout_plan_round_trips_without_changing_the_preparation_component():
    configuration = json.loads((FIXTURES / "preparation_v1_environment.json").read_text())
    settings = Settings(
        _env_file=None,
        enrichment_enabled=True,
        enrichment_ocr_configuration=json.dumps(configuration["configuration"]),
    )
    profile = layout_profile(settings)
    assert read_profile(json.loads(profile.model_dump_json())) == profile
    assert profile.preparation == preparation_profile(settings)
    require_layout(profile)
    with pytest.raises(ValueError):
        resolve_profile(profile.key, settings)
    with pytest.raises(ValueError):
        SourceLayoutProfile.model_validate(
            profile.model_copy(update={"stages": ("SPATIAL_LAYOUT",)})
        )
    with pytest.raises(ValueError, match="resources unavailable"):
        require_layout(profile.model_copy(update={"algorithm_sha256": "0" * 64}))
    prior = json.loads((FIXTURES / "layout_v1_identity.json").read_text())
    with pytest.raises(ValueError, match="resources unavailable"):
        require_layout(profile.model_copy(update={"algorithm_sha256": prior["algorithm_sha256"]}))


def test_layout_algorithms_import_without_extraction_api_or_registry():
    script = """
import builtins
original = builtins.__import__
def check(name, *args, **kwargs):
    if name.split('.')[0] in {'fastapi', 'powerforge_extraction', 'powerforge_engineering_model'}:
        raise AssertionError('Domain/API dependency in layout: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = check
from powerforge_document_processing.layout_derive import layout_rules_identity
assert len(layout_rules_identity()) == 64
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
