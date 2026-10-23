import json
from dataclasses import asdict

from fastapi.testclient import TestClient

from powerforge_api.main import app
from powerforge_engineering_model import REGISTRY, supported_input_units


def test_registry_endpoint_is_deterministic_and_matches_domain() -> None:
    client = TestClient(app)
    first = client.get("/api/engineering-model/registry")
    second = client.get("/api/engineering-model/registry")
    assert first.status_code == 200
    assert first.content == second.content
    body = first.json()
    assert body["registry_version"] == "registry-v1"
    assert len(body["equipment_types"]) == 20
    assert len(body["requirement_rules"]) == 44
    assert body["unit_families"] == json.loads(
        json.dumps([asdict(f) for f in REGISTRY.unit_families])
    )
    assert body["requirement_rules"] == json.loads(
        json.dumps([asdict(r) for r in REGISTRY.requirement_rules])
    )
    for actual, expected in zip(body["equipment_types"], REGISTRY.equipment_types, strict=True):
        assert actual["key"] == expected.key
        assert actual["display_name"] == expected.display_name
        assert actual["requirements"] == json.loads(
            json.dumps([asdict(r) for r in expected.requirements])
        )
        for attr, definition in zip(actual["attributes"], expected.attributes, strict=True):
            assert attr.pop("supported_input_units") == list(
                supported_input_units(expected.key, definition.key)
            )
            assert attr == json.loads(json.dumps(asdict(definition)))


def test_registry_is_read_only_and_has_typed_openapi_contract() -> None:
    client = TestClient(app)
    assert client.post("/api/engineering-model/registry", json={}).status_code == 405
    schema = client.get("/openapi.json").json()
    path = schema["paths"]["/api/engineering-model/registry"]
    assert set(path) == {"get"}
    assert path["get"]["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/RegistryResponse",
    }
