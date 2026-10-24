"""Focused end-to-end canonical API tests against a disposable PostgreSQL database."""

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from powerforge_api.db import get_engine, get_session_factory
from powerforge_api.main import app
from powerforge_engineering_model import ValueOrigin, VerificationState, get_equipment_definition
from powerforge_persistence import Project, ProjectRevision
from powerforge_persistence.engineering import Equipment
from powerforge_persistence.topology import ModelConnection, ModelNode
from powerforge_project import ProjectStatus, RevisionStatus

client = TestClient(app)


def checked(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


@pytest.fixture
def model_api(require_db):
    project = checked(
        client.post(
            "/api/projects",
            json={
                "project_number": f"API-{uuid4().hex}",
                "project_name": "Model API",
            },
        ),
        201,
    )
    revision = checked(
        client.post(f"/api/projects/{project['id']}/revisions", json={"identifier": "0"}), 201
    )
    return f"/api/projects/{project['id']}/revisions/{revision['id']}"


def equipment(base, equipment_type="BUS", **values):
    return checked(
        client.post(base + "/equipment", json={"equipment_type": equipment_type, **values}), 201
    )


def node(base, **values):
    return checked(client.post(base + "/nodes", json={"kind": "ELECTRICAL_NODE", **values}), 201)


def connection(base, first, second, **values):
    return checked(
        client.post(
            base + "/connections",
            json={"from_node_id": first["id"], "to_node_id": second["id"], **values},
        ),
        201,
    )


def items(base, resource, **filters):
    return checked(client.get(f"{base}/{resource}", params=filters))["items"]


def test_equipment_contract_search_filters_and_patch(model_api):
    base = model_api
    first = equipment(base, tag="SWGR-1", name="Main", description="Indoor 100%_rated")
    duplicate = equipment(base, tag="SWGR-1", name="Spare")
    cable = equipment(base, "CABLE", tag="C1")
    assert first["origin"] == "MANUAL" and first["verification_state"] == "ENGINEER_REVIEWED"
    assert first["lifecycle_status"] == "ACTIVE" and first["lineage_id"]
    for key in (
        "created_by",
        "updated_by",
        "removed_by",
        "removed_at",
        "inherited_from_equipment_id",
    ):
        assert first[key] is None
    assert {"created_at", "updated_at", "project_id", "revision_id"} <= first.keys()
    assert "attributes" not in first
    path = f"{base}/equipment/{first['id']}"
    assert checked(client.get(path)) == first
    assert [r["id"] for r in items(base, "equipment")] == [
        first["id"],
        duplicate["id"],
        cable["id"],
    ]
    for search in (" main ", "INDOOR", "%_"):
        assert [r["id"] for r in items(base, "equipment", search=search)] == [first["id"]]
    assert len(items(base, "equipment", search=" swgr ", equipment_type="BUS")) == 2
    assert len(items(base, "equipment", search="  ")) == 3
    assert [r["id"] for r in items(base, "equipment", equipment_type="CABLE")] == [cable["id"]]
    assert (
        client.get(base + "/equipment", params={"equipment_type": "SWITCHGEAR"}).status_code == 422
    )
    assert (
        client.get(base + "/equipment", params={"lifecycle_status": "INVALID"}).status_code == 422
    )

    changed = checked(client.patch(path, json={"tag": None}))
    assert changed["tag"] is None and changed["name"] == "Main"
    assert changed["description"] == first["description"]
    assert (
        checked(client.patch(path, json={"equipment_type": "CABLE"}))["equipment_type"] == "CABLE"
    )
    checked(client.post(path + "/remove"))
    assert len(items(base, "equipment")) == 2
    assert [r["id"] for r in items(base, "equipment", lifecycle_status="REMOVED")] == [first["id"]]
    assert len(items(base, "equipment", lifecycle_status="ALL")) == 3
    assert checked(client.get(path))["lifecycle_status"] == "REMOVED"
    assert (
        checked(client.patch(path, json={"name": "Blocked"}), 409)["detail"]["code"]
        == "equipment_removed"
    )
    assert checked(client.post(path + "/restore"))["lifecycle_status"] == "ACTIVE"

    # List summaries must not fetch the materialized attributes (including via ORM eager loading).
    statements = []

    def record(_conn, _cursor, statement, *_args):
        statements.append(statement.lower())

    engine = get_engine()
    event.listen(engine, "before_cursor_execute", record)
    try:
        assert len(items(base, "equipment")) == 3
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert not any("equipment_attributes" in sql for sql in statements)


def test_attributes_registry_order_normalization_and_safe_type_conflict(model_api):
    bus = equipment(model_api)
    path = f"{model_api}/equipment/{bus['id']}"
    attrs = items(model_api, f"equipment/{bus['id']}/attributes")
    assert [a["attribute_key"] for a in attrs] == [
        a.key for a in get_equipment_definition("BUS").attributes
    ]
    assert all(
        a["information_state"] == "NOT_EXTRACTED"
        and a["verification_state"] == "UNVERIFIED"
        and a["origin"] is None
        for a in attrs
    )
    voltage = path + "/attributes/nominal_voltage"
    result = checked(
        client.put(voltage, json={"information_state": "PRESENT", "value": 600, "unit": "V"})
    )
    assert result["numeric_value"] == "0.6" and result["unit"] == "kV"
    assert result["origin"] == "MANUAL" and result["verification_state"] == "ENGINEER_REVIEWED"
    assert result["confidence"] is None and result["inherited_from_attribute_id"] is None
    precise = "0.1234567890123456789012345678901234"
    assert (
        checked(client.put(voltage, json={"information_state": "PRESENT", "value": precise}))[
            "numeric_value"
        ]
        == precise
    )
    for state in ("UNKNOWN", "MISSING", "NOT_APPLICABLE"):
        changed = checked(client.put(voltage, json={"information_state": state}))
        assert changed["information_state"] == state
        assert all(
            changed[key] is None
            for key in ("numeric_value", "integer_value", "text_value", "boolean_value")
        )
    assert (
        checked(
            client.put(
                path + "/attributes/bus_type",
                json={"information_state": "PRESENT", "value": "SWITCHGEAR"},
            )
        )["text_value"]
        == "SWITCHGEAR"
    )
    conflict = checked(client.patch(path, json={"equipment_type": "CABLE"}), 409)
    assert conflict["detail"]["code"] == "equipment_type_change_conflict"
    assert checked(client.get(path))["equipment_type"] == "BUS"
    assert (
        checked(
            client.put(
                path + "/attributes/phase_count", json={"information_state": "PRESENT", "value": 1}
            )
        )["integer_value"]
        == 1
    )
    ups = equipment(model_api, "UPS")
    boolean = f"{model_api}/equipment/{ups['id']}/attributes/static_bypass_available"
    assert (
        checked(client.put(boolean, json={"information_state": "PRESENT", "value": False}))[
            "boolean_value"
        ]
        is False
    )
    # Explicit equipment phase remains independent of revision-wide defaults.
    checked(client.patch(model_api, json={"system_phase_count": 3, "system_frequency": 60}))
    assert (
        checked(
            client.put(
                path + "/attributes/phase_count", json={"information_state": "PRESENT", "value": 1}
            )
        )["integer_value"]
        == 1
    )


@pytest.mark.parametrize(
    ("key", "body"),
    [
        ("nominal_voltage", {"information_state": "PRESENT", "value": 600, "unit": "A"}),
        ("nominal_voltage", {"information_state": "PRESENT", "value": 600, "unit": "bogus"}),
        ("nominal_voltage", {"information_state": "PRESENT", "value": True}),
        ("bus_type", {"information_state": "PRESENT", "value": "INVALID"}),
        ("phase_count", {"information_state": "PRESENT", "value": 1.5}),
        ("phase_count", {"information_state": "PRESENT", "value": False}),
        ("invented", {"information_state": "UNKNOWN"}),
        ("nominal_voltage", {"information_state": "NOT_EXTRACTED"}),
        ("nominal_voltage", {"information_state": "CONFLICTING"}),
        ("nominal_voltage", {"information_state": "MISSING", "value": 600}),
    ],
)
def test_invalid_attribute_inputs_are_client_errors(model_api, key, body):
    row = equipment(model_api)
    checked(client.put(f"{model_api}/equipment/{row['id']}/attributes/{key}", json=body), 422)


def test_topology_contract_rewire_voltage_and_lifecycle_cascades(model_api):
    base = model_api
    owner = equipment(base)
    terminal = node(
        base,
        kind="EQUIPMENT_TERMINAL",
        equipment_id=owner["id"],
        terminal_key=" LINE ",
        label="Input",
    )
    first, second = node(base, label="Junction"), node(base)
    assert terminal["terminal_key"] == "LINE"
    assert terminal["origin"] == "MANUAL" and terminal["verification_state"] == "ENGINEER_REVIEWED"
    terminal_path = f"{base}/nodes/{terminal['id']}"
    updated = checked(client.patch(terminal_path, json={"terminal_key": "SUPPLY", "label": None}))
    assert updated["terminal_key"] == "SUPPLY" and updated["label"] is None
    edge = connection(
        base,
        terminal,
        first,
        nominal_voltage=600,
        nominal_voltage_unit="V",
        phase_configuration=" ABC ",
    )
    assert edge["connection_kind"] == "ELECTRICAL" and edge["direction"] == "UNDIRECTED"
    assert edge["nominal_voltage"] == "0.6" and edge["nominal_voltage_unit"] == "kV"
    assert edge["phase_configuration"] == "ABC" and edge["confidence"] is None
    assert edge["origin"] == "MANUAL" and edge["verification_state"] == "ENGINEER_REVIEWED"
    parallel = connection(base, terminal, first)
    assert [r["id"] for r in items(base, "connections")] == [edge["id"], parallel["id"]]
    path = f"{base}/connections/{edge['id']}"
    updated = checked(
        client.patch(
            path,
            json={
                "to_node_id": second["id"],
                "direction": "NOMINAL_FROM_TO",
                "connection_kind": "OTHER",
            },
        )
    )
    assert updated["from_node_id"] == terminal["id"] and updated["to_node_id"] == second["id"]
    assert updated["phase_configuration"] == "ABC" and updated["nominal_voltage"] == "0.6"
    cleared = checked(
        client.patch(
            path,
            json={
                "phase_configuration": None,
                "nominal_voltage": None,
                "nominal_voltage_unit": None,
            },
        )
    )
    assert all(
        cleared[key] is None
        for key in ("phase_configuration", "nominal_voltage", "nominal_voltage_unit")
    )
    precise = "13.12345678901234567890123456789012"
    assert (
        checked(client.patch(path, json={"nominal_voltage": precise}))["nominal_voltage"] == precise
    )
    checked(client.post(terminal_path + "/remove"))
    assert items(base, "connections") == []
    assert len(items(base, "connections", lifecycle_status="REMOVED")) == 2
    assert len(items(base, "connections", lifecycle_status="ALL")) == 2
    assert len(items(base, "nodes")) == 2
    assert [r["id"] for r in items(base, "nodes", lifecycle_status="REMOVED")] == [terminal["id"]]
    assert len(items(base, "nodes", lifecycle_status="ALL")) == 3
    checked(client.post(path + "/restore"), 409)
    checked(client.patch(terminal_path, json={"label": "blocked"}), 409)
    checked(client.patch(path, json={"direction": "UNDIRECTED"}), 409)
    checked(client.post(terminal_path + "/restore"))
    assert items(base, "connections") == []
    checked(client.post(path + "/restore"))
    checked(client.post(path + "/remove"))
    checked(client.post(path + "/restore"))
    equipment_path = f"{base}/equipment/{owner['id']}"
    checked(client.post(equipment_path + "/remove"))
    assert items(base, "connections") == []
    checked(client.post(terminal_path + "/restore"), 422)
    checked(client.post(equipment_path + "/restore"))
    assert len(items(base, "nodes")) == 3 and items(base, "connections") == []


def test_topology_invalid_shapes_and_patch_nulls(model_api):
    base = model_api
    first, second = node(base), node(base)
    owner = equipment(base)
    for payload in (
        {"kind": "EQUIPMENT_TERMINAL"},
        {"kind": "EQUIPMENT_TERMINAL", "equipment_id": owner["id"], "terminal_key": " "},
        {"kind": "ELECTRICAL_NODE", "equipment_id": owner["id"]},
        {"kind": "ELECTRICAL_NODE", "terminal_key": "X"},
        {"kind": "BUS"},
    ):
        checked(client.post(base + "/nodes", json=payload), 422)
    for payload in (
        {"terminal_key": None},
        {"terminal_key": "X"},
        {"kind": "EQUIPMENT_TERMINAL"},
        {"equipment_id": owner["id"]},
    ):
        checked(client.patch(f"{base}/nodes/{first['id']}", json=payload), 422)
    endpoints = {"from_node_id": first["id"], "to_node_id": second["id"]}
    for payload in (
        {"to_node_id": first["id"]},
        {"nominal_voltage_unit": "V"},
        {"nominal_voltage": 0},
        {"nominal_voltage": -1},
        {"nominal_voltage": True},
        {"nominal_voltage": False},
        {"nominal_voltage": "NaN"},
        {"nominal_voltage": "Infinity"},
        {"nominal_voltage": 10, "nominal_voltage_unit": "A"},
        {"direction": "REVERSE"},
    ):
        checked(client.post(base + "/connections", json={**endpoints, **payload}), 422)
    edge = connection(base, first, second)
    for payload in (
        {"from_node_id": None},
        {"to_node_id": None},
        {"connection_kind": None},
        {"direction": None},
        {"nominal_voltage_unit": "V"},
        {"nominal_voltage_unit": None},
    ):
        checked(client.patch(f"{base}/connections/{edge['id']}", json=payload), 422)
    for payload in ({"equipment_type": None}, {"equipment_type": "INVALID"}):
        checked(client.patch(f"{base}/equipment/{owner['id']}", json=payload), 422)
    checked(client.post(base + "/equipment", json={"equipment_type": "INVALID"}), 422)


def test_manual_request_provenance_is_not_writable(model_api):
    base = model_api
    row = equipment(base)
    first, second = node(base), node(base)
    edge = connection(base, first, second)
    cases = [
        ("post", "/equipment", {"equipment_type": "BUS", "origin": "AI_EXTRACTION"}),
        ("patch", f"/equipment/{row['id']}", {"created_by": str(uuid4())}),
        (
            "put",
            f"/equipment/{row['id']}/attributes/nominal_voltage",
            {"information_state": "UNKNOWN", "verification_state": "ENGINEER_VERIFIED"},
        ),
        (
            "put",
            f"/equipment/{row['id']}/attributes/nominal_voltage",
            {"information_state": "UNKNOWN", "confidence": 0.99},
        ),
        (
            "put",
            f"/equipment/{row['id']}/attributes/nominal_voltage",
            {"information_state": "UNKNOWN", "origin": "AI_EXTRACTION"},
        ),
        (
            "put",
            f"/equipment/{row['id']}/attributes/nominal_voltage",
            {"information_state": "UNKNOWN", "inherited_from_attribute_id": str(uuid4())},
        ),
        ("post", "/nodes", {"kind": "ELECTRICAL_NODE", "origin": "IMPORTED"}),
        ("patch", f"/nodes/{first['id']}", {"verification_state": "ENGINEER_VERIFIED"}),
        (
            "post",
            "/connections",
            {"from_node_id": first["id"], "to_node_id": second["id"], "confidence": 0.99},
        ),
        (
            "patch",
            f"/connections/{edge['id']}",
            {"origin": "AI_EXTRACTION", "verification_state": "ENGINEER_VERIFIED"},
        ),
        ("post", f"/equipment/{row['id']}/remove", {"removed_by": str(uuid4())}),
    ]
    for method, path, body in cases:
        checked(client.request(method, base + path, json=body), 422)
    assert checked(client.get(f"{base}/equipment/{row['id']}"))["lifecycle_status"] == "ACTIVE"


def test_empty_patch_preserves_provenance_and_audit(model_api):
    owner = equipment(model_api)
    first, second = node(model_api), node(model_api)
    edge = connection(model_api, first, second)
    rows = ((Equipment, owner), (ModelNode, first), (ModelConnection, edge))
    with get_session_factory()() as session:
        for model, response in rows:
            row = session.get(model, UUID(response["id"]))
            row.origin = ValueOrigin.AI_EXTRACTION
            row.verification_state = VerificationState.AI_EXTRACTED
            if model is ModelConnection:
                row.confidence = Decimal("0.83")
        session.commit()

    # Compare full canonical responses, including provenance, confidence and audit timestamps.
    before = {
        resource: items(model_api, resource) for resource in ("equipment", "nodes", "connections")
    }
    for resource, response in (("equipment", owner), ("nodes", first), ("connections", edge)):
        checked(client.patch(f"{model_api}/{resource}/{response['id']}", json={}), 422)
    assert {resource: items(model_api, resource) for resource in before} == before


def test_path_scoping_and_missing_objects(model_api):
    base = model_api
    parent = base.rsplit("/", 1)[0]
    other_revision = checked(
        client.post(parent, json={"identifier": "1", "carry_forward_model": False}), 201
    )
    other = parent + "/" + other_revision["id"]
    row = equipment(base)
    first, second = node(base), node(base)
    edge = connection(base, first, second)
    for scoped_id in (row["id"], str(uuid4())):
        checked(client.get(f"{other}/equipment/{scoped_id}"), 404)
        checked(client.patch(f"{other}/equipment/{scoped_id}", json={"tag": "X"}), 404)
        checked(client.get(f"{other}/equipment/{scoped_id}/attributes"), 404)
        checked(
            client.put(
                f"{other}/equipment/{scoped_id}/attributes/nominal_voltage",
                json={"information_state": "UNKNOWN"},
            ),
            404,
        )
        checked(client.post(f"{other}/equipment/{scoped_id}/remove"), 404)
    for resource, identity in (("nodes", first["id"]), ("connections", edge["id"])):
        for scoped_id in (identity, str(uuid4())):
            body = {"label": "Edited"} if resource == "nodes" else {"phase_configuration": "ABC"}
            checked(client.patch(f"{other}/{resource}/{scoped_id}", json=body), 404)
            checked(client.post(f"{other}/{resource}/{scoped_id}/restore"), 404)
    checked(
        client.post(
            other + "/nodes",
            json={"kind": "EQUIPMENT_TERMINAL", "equipment_id": row["id"], "terminal_key": "A"},
        ),
        404,
    )
    local = node(other)
    checked(
        client.post(
            other + "/connections", json={"from_node_id": first["id"], "to_node_id": local["id"]}
        ),
        404,
    )
    local_second = node(other)
    local_edge = connection(other, local, local_second)
    checked(
        client.patch(f"{other}/connections/{local_edge['id']}", json={"to_node_id": second["id"]}),
        404,
    )
    # Existing revision under an unrelated existing project is not accessible.
    project = checked(
        client.post("/api/projects", json={"project_number": uuid4().hex, "project_name": "Other"}),
        201,
    )
    wrong = f"/api/projects/{project['id']}/revisions/{base.rsplit('/', 1)[1]}"
    for resource in ("equipment", "nodes", "connections"):
        checked(client.get(wrong + "/" + resource), 404)
    assert items(other, "equipment") == []


@pytest.mark.parametrize(
    ("project_status", "revision_status", "code"),
    [
        (ProjectStatus.ARCHIVED, RevisionStatus.DRAFT, "archived_project"),
        (ProjectStatus.CANCELLED, RevisionStatus.DRAFT, "cancelled_project"),
        (ProjectStatus.ACTIVE, RevisionStatus.SUPERSEDED, "revision_read_only"),
    ],
)
def test_readonly_errors_propagate_and_historical_reads_remain(
    model_api, project_status, revision_status, code
):
    row = equipment(model_api)
    with get_session_factory()() as session:
        session.get(Project, UUID(row["project_id"])).status = project_status
        session.get(ProjectRevision, UUID(row["revision_id"])).status = revision_status
        session.commit()
    result = checked(
        client.patch(f"{model_api}/equipment/{row['id']}", json={"tag": "Blocked"}), 409
    )
    assert result["detail"]["code"] == code
    assert len(items(model_api, "equipment")) == 1
    assert items(model_api, "nodes") == []
    assert checked(client.get(f"{model_api}/equipment/{row['id']}"))["tag"] is None
