"""Enhanced profiles reproduce their own wire, schemas and execution resources."""

from pathlib import Path

from powerforge_extraction.enriched_observations import RESPONSES

FIXTURES = Path(__file__).parent / "fixtures"


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
