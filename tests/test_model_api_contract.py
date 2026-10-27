"""Offline HTTP contract/error boundary tests; persistence remains covered separately."""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from powerforge_api import exceptions as errors
from powerforge_api.main import app
from powerforge_api.routers.errors import http_for, model_api_errors
from powerforge_engineering_model.errors import (
    IncompatibleUnit,
    InvalidAttributeValue,
    InvalidEnumValue,
    InvalidRegistryDefinition,
    UnknownAttribute,
    UnknownEquipmentType,
    UnknownUnit,
)

BASE = "/api/projects/{project_id}/revisions/{revision_id}"


def test_openapi_model_scope_and_allowlists():
    schema = TestClient(app).get("/openapi.json").json()
    expected = {
        "/equipment": {"get", "post"},
        "/equipment/{equipment_id}": {"get", "patch"},
        "/equipment/{equipment_id}/editor": {"get", "patch"},
        "/equipment/{equipment_id}/remove": {"post"},
        "/equipment/{equipment_id}/restore": {"post"},
        "/equipment/{equipment_id}/attributes": {"get"},
        "/equipment/{equipment_id}/attributes/{attribute_key}": {"put"},
        "/nodes": {"get", "post"},
        "/nodes/{node_id}": {"patch"},
        "/nodes/{node_id}/remove": {"post"},
        "/nodes/{node_id}/restore": {"post"},
        "/connections": {"get", "post"},
        "/connections/{connection_id}": {"patch"},
        "/connections/{connection_id}/remove": {"post"},
        "/connections/{connection_id}/restore": {"post"},
    }
    actual = {
        path.removeprefix(BASE): set(operations)
        for path, operations in schema["paths"].items()
        if path.startswith(
            tuple(BASE + "/" + name for name in ("equipment", "nodes", "connections"))
        )
    }
    assert actual == expected
    assert set(schema["paths"]["/api/engineering-model/registry"]) == {"get"}
    model_operations = {
        path
        for path, operations in schema["paths"].items()
        if any(
            "engineering-model" in operation.get("tags", []) for operation in operations.values()
        )
    }
    assert model_operations == {BASE + path for path in expected} | {
        "/api/engineering-model/registry"
    }
    allowlists = {
        "EquipmentCreate": {"equipment_type", "tag", "name", "description"},
        "EquipmentUpdate": {"equipment_type", "tag", "name", "description"},
        "AttributeUpdate": {"information_state", "value", "unit"},
        "NodeCreate": {"kind", "equipment_id", "terminal_key", "label"},
        "NodeUpdate": {"terminal_key", "label"},
        "ConnectionCreate": {
            "from_node_id",
            "to_node_id",
            "connection_kind",
            "direction",
            "phase_configuration",
            "nominal_voltage",
            "nominal_voltage_unit",
        },
        "ConnectionUpdate": {
            "from_node_id",
            "to_node_id",
            "connection_kind",
            "direction",
            "phase_configuration",
            "nominal_voltage",
            "nominal_voltage_unit",
        },
        "ManualAction": set(),
    }
    for name, fields in allowlists.items():
        definition = schema["components"]["schemas"][name]
        assert definition["additionalProperties"] is False
        assert set(definition["properties"]) == fields

    # Both small and large canonical integers use strings on the wire; null stays null.
    properties = schema["components"]["schemas"]["AttributeResponse"]["properties"]
    assert properties["integer_value"]["anyOf"] == [{"type": "string"}, {"type": "null"}]
    assert [item["type"] for item in properties["numeric_value"]["anyOf"]] == ["string", "null"]


def test_model_http_error_mapping():
    groups = {
        404: [
            errors.EquipmentNotFound,
            errors.EquipmentAttributeNotFound,
            errors.ModelNodeNotFound,
            errors.ModelConnectionNotFound,
        ],
        409: [
            errors.EquipmentRemoved,
            errors.TopologyObjectRemoved,
            errors.EquipmentTypeChangeConflict,
            errors.ArchivedProject,
            errors.CancelledProject,
            errors.RevisionReadOnly,
        ],
        422: [
            errors.InvalidEngineeringModelInput,
            errors.InvalidEquipmentAttributeState,
            errors.InvalidTopology,
        ],
        500: [errors.UnexpectedIntegrityError],
    }
    for status, classes in groups.items():
        for error in classes:
            response = http_for(error("safe message"))
            assert response.status_code == status
            assert response.detail == {"code": error.code, "detail": "safe message"}


def test_inconsistent_equipment_is_a_safe_server_error():
    with pytest.raises(HTTPException) as raised, model_api_errors():
        raise errors.InconsistentEquipment("Internal ownership and registry mismatch details")
    assert raised.value.status_code == 500
    assert raised.value.detail == {
        "code": "inconsistent_equipment",
        "detail": "An internal engineering model consistency error occurred",
    }


def test_domain_boundary_translates_input_but_not_programming_errors():
    for error in (
        UnknownEquipmentType,
        UnknownAttribute,
        InvalidAttributeValue,
        InvalidEnumValue,
        UnknownUnit,
        IncompatibleUnit,
    ):
        with pytest.raises(HTTPException) as raised, model_api_errors():
            raise error("Invalid input")
        assert raised.value.status_code == 422
        assert raised.value.detail == {
            "code": "invalid_engineering_model_input",
            "detail": "Invalid input",
        }
    for error in (InvalidRegistryDefinition, RuntimeError, TypeError):
        with pytest.raises(error), model_api_errors():
            raise error("Server bug")


@pytest.mark.parametrize(
    "body",
    [
        {"equipment_type": None},
        {"verification_state": "ENGINEER_VERIFIED"},
    ],
)
def test_request_validation_precedes_database_work(body):
    from powerforge_api.db import get_session

    # A dependency that supplies no database proves schema-invalid calls do not use services.
    app.dependency_overrides[get_session] = lambda: None
    try:
        path = BASE.format(project_id=uuid4(), revision_id=uuid4())
        response = TestClient(app).patch(f"{path}/equipment/{uuid4()}", json=body)
        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.parametrize("resource", ["equipment", "nodes", "connections"])
def test_empty_patch_is_rejected_before_service_call(resource):
    from powerforge_api.db import get_session

    app.dependency_overrides[get_session] = lambda: None
    try:
        path = BASE.format(project_id=uuid4(), revision_id=uuid4())
        response = TestClient(app).patch(f"{path}/{resource}/{uuid4()}", json={})
        assert response.status_code == 422
        assert "At least one field must be provided" in response.json()["detail"][0]["msg"]
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_explicit_null_is_a_supplied_patch_field():
    from powerforge_api.schemas.model import ConnectionUpdate, EquipmentUpdate, NodeUpdate

    for schema, key in (
        (EquipmentUpdate, "tag"),
        (NodeUpdate, "label"),
        (ConnectionUpdate, "phase_configuration"),
        (ConnectionUpdate, "nominal_voltage"),
    ):
        assert schema.model_validate({key: None}).model_dump(exclude_unset=True) == {key: None}
