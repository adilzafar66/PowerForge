"""Enhanced profiles reproduce their own wire, schemas and execution resources."""

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from powerforge_extraction.enriched_observations import RESPONSES
from powerforge_extraction.enriched_profiles import PROFILES, manifest, runtime_identity
from powerforge_extraction.profiles import read_profile, resolve_profile
from powerforge_extraction.stage_runtime import require_supported
from powerforge_shared.config import Settings

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("key", PROFILES)
def test_enhanced_profiles_pin_their_wire_and_runtime_resources(key):
    pinned = json.loads((FIXTURES / "enrichment/enriched_v1_identity.json").read_text())
    material = json.loads((FIXTURES / "extraction/table_execution_v1_identity.json").read_text())
    profile = resolve_profile(key, Settings(_env_file=None, **material["settings"]))
    wire = profile.model_dump_json()
    restored = read_profile(json.loads(wire))
    assert restored.model_dump_json() == wire
    assert hashlib.sha256(wire.encode()).hexdigest() == pinned["profiles"][key]["wire_sha256"]
    assert restored.identity_hash == pinned["profiles"][key]["identity_hash"]
    assert restored.runtime == runtime_identity() == pinned["runtime"]
    assert restored.manifest == manifest() == pinned["manifest"]
    require_supported(restored)
    incorrect_key = (
        key.replace("-test-", "-openai-") if "-test-" in key else key.replace("-openai-", "-test-")
    )
    with pytest.raises(ValidationError):
        read_profile({**json.loads(wire), "key": incorrect_key})


def test_enhanced_response_schemas_exclude_model_supplied_offsets_and_geometry():
    for model in RESPONSES.values():
        schema = model.model_json_schema()
        properties = {
            name
            for definition in (schema, *schema.get("$defs", {}).values())
            for name in definition.get("properties", {})
        }
        assert {"reading_refs", "source_ref"} <= properties or "value_cell_ref" in properties
        assert properties.isdisjoint({"box", "region", "text_start", "text_end", "polygon"})
