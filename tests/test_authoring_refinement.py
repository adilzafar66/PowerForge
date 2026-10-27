"""Focused refinement boundaries: profiles, resets and atomic editor transactions."""

import pytest
from sqlalchemy import event

from engineering_support import engineering_context as engineering_context
from powerforge_api.db import get_engine
from powerforge_api.exceptions import EquipmentTypeChangeConflict, InvalidTopology
from powerforge_api.services.topology_service import TopologyService
from powerforge_engineering_model import EquipmentType, InformationState
from powerforge_engineering_model.terminal_profiles import TERMINAL_PROFILES, terminal_profile
from test_model_api import checked, client, equipment, items, node
from test_model_api import model_api as model_api


def test_terminal_profiles_cover_the_frozen_taxonomy():
    assert set(TERMINAL_PROFILES) == set(EquipmentType)
    assert terminal_profile("OVERCURRENT_RELAY") == ()
    assert terminal_profile("DOUBLE_THROW_SWITCH") == ("SOURCE_1", "SOURCE_2", "COMMON")
    assert terminal_profile("CABLE") == ("END_A", "END_B")
    assert all(len(keys) == len(set(keys)) for keys in TERMINAL_PROFILES.values())


def test_every_type_materializes_normal_terminals(engineering_context):
    ctx = engineering_context
    topology = TopologyService(ctx.session)
    for kind, keys in TERMINAL_PROFILES.items():
        row = ctx.service.create_equipment(*ctx.ids, kind)
        nodes = [n for n in topology.list_nodes(*ctx.ids) if n.equipment_id == row.id]
        assert {n.terminal_key for n in nodes} == set(keys)
        assert all(n.managed_by_profile for n in nodes)


def test_profile_reconciliation_adopts_preserves_and_rejects_connected_removal(engineering_context):
    ctx = engineering_context
    service = ctx.service
    topology = TopologyService(ctx.session)
    row = service.create_equipment(*ctx.ids, "BUS")
    bus = next(n for n in topology.list_nodes(*ctx.ids) if n.equipment_id == row.id)
    custom = topology.create_terminal(*ctx.ids, row.id, "INPUT", label="Keep my label")
    ground = topology.create_terminal(*ctx.ids, row.id, "GROUND")
    junction = topology.create_electrical_node(*ctx.ids)
    connection = topology.create_connection(*ctx.ids, bus.id, junction.id)
    with pytest.raises(EquipmentTypeChangeConflict):
        service.update_equipment(*ctx.ids, row.id, equipment_type="LV_BREAKER", tag="must rollback")
    assert service.get_equipment(*ctx.ids, row.id).tag is None
    assert service.get_equipment(*ctx.ids, row.id).equipment_type == "BUS"
    topology.remove_connection(*ctx.ids, connection.id)
    service.update_equipment(*ctx.ids, row.id, equipment_type="LV_BREAKER")
    nodes = {
        n.terminal_key: n
        for n in topology.list_nodes(*ctx.ids, lifecycle_status=None)
        if n.equipment_id == row.id
    }
    assert nodes["BUS"].id == bus.id and nodes["BUS"].lifecycle_status == "REMOVED"
    assert nodes["INPUT"].id == custom.id and nodes["INPUT"].managed_by_profile
    assert nodes["INPUT"].label == "Keep my label"
    assert nodes["OUTPUT"].managed_by_profile
    assert nodes["GROUND"].id == ground.id and not nodes["GROUND"].managed_by_profile
    with pytest.raises(InvalidTopology):
        topology.remove_node(*ctx.ids, custom.id)
    with pytest.raises(InvalidTopology):
        topology.update_node(*ctx.ids, custom.id, terminal_key="RENAMED")
    with pytest.raises(InvalidTopology):
        topology.restore_node(*ctx.ids, bus.id)
    service.remove_equipment(*ctx.ids, row.id)
    service.restore_equipment(*ctx.ids, row.id)
    assert topology.get_node(*ctx.ids, bus.id).lifecycle_status == "REMOVED"
    assert topology.get_connection(*ctx.ids, connection.id).lifecycle_status == "REMOVED"
    service.update_equipment(*ctx.ids, row.id, equipment_type="HV_BREAKER")
    assert topology.get_node(*ctx.ids, custom.id).id == custom.id


def test_reset_clears_values_and_review_provenance(engineering_context):
    ctx = engineering_context
    row = ctx.service.create_equipment(*ctx.ids, "BUS")
    ctx.service.set_attribute(
        *ctx.ids, row.id, "phase_count", InformationState.PRESENT, value="9007199254740993"
    )
    reset = ctx.service.set_attribute(
        *ctx.ids, row.id, "phase_count", InformationState.NOT_POPULATED
    )
    assert reset.integer_value is None and reset.numeric_value is None
    assert reset.boolean_value is None and reset.text_value is None
    assert reset.origin is None and reset.confidence is None
    assert reset.verification_state == "UNVERIFIED"
    ctx.service.update_equipment(*ctx.ids, row.id, equipment_type="CABLE")


def test_editor_saves_one_transaction_and_rolls_back_late_failure(model_api):
    base = model_api
    row = equipment(base)
    path = f"{base}/equipment/{row['id']}/editor"
    before = checked(client.get(path))
    payload = {
        "general": {"tag": "Saved together"},
        "attributes": {
            "phase_count": {"information_state": "PRESENT", "value": "9007199254740993"}
        },
        "create_terminals": [{"terminal_key": "GROUND"}],
    }
    commits = []

    def listener(connection):
        commits.append(True)

    event.listen(get_engine(), "commit", listener)
    try:
        saved = checked(client.patch(path, json=payload))
    finally:
        event.remove(get_engine(), "commit", listener)
    assert len(commits) == 1
    assert saved["equipment"]["tag"] == "Saved together"
    assert (
        next(a for a in saved["attributes"] if a["attribute_key"] == "phase_count")["integer_value"]
        == "9007199254740993"
    )
    assert {n["terminal_key"]: n["managed_by_profile"] for n in saved["terminals"]} == {
        "BUS": True,
        "GROUND": False,
    }
    assert (
        before["terminals"][0]["id"]
        == next(n for n in saved["terminals"] if n["terminal_key"] == "BUS")["id"]
    )
    bad = {
        "general": {"tag": "Rollback"},
        "attributes": {"phase_count": {"information_state": "PRESENT", "value": "3"}},
        "create_terminals": [{"terminal_key": "NEUTRAL"}, {"terminal_key": "GROUND"}],
    }
    checked(client.patch(path, json=bad), 422)
    assert checked(client.get(path)) == saved
    checked(
        client.patch(
            path, json={"attributes": {"phase_count": {"information_state": "NOT_POPULATED"}}}
        )
    )
    reset = next(
        a for a in checked(client.get(path))["attributes"] if a["attribute_key"] == "phase_count"
    )
    assert (
        reset["origin"],
        reset["verification_state"],
        reset["confidence"],
        reset["integer_value"],
    ) == (None, "UNVERIFIED", None, None)


def test_editor_ownership_managed_protection_and_read_only(model_api):
    base = model_api
    owner, other = equipment(base), equipment(base)
    path = f"{base}/equipment/{owner['id']}/editor"
    managed = checked(client.get(path))["terminals"][0]
    foreign = node(base, kind="EQUIPMENT_TERMINAL", equipment_id=other["id"], terminal_key="GROUND")
    for change in [
        {"remove_terminals": [managed["id"]]},
        {"update_terminals": [{"id": managed["id"], "terminal_key": "X"}]},
        {"update_terminals": [{"id": foreign["id"], "label": "Bad"}]},
        {"general": {"origin": "AI_EXTRACTION"}},
        {},
    ]:
        checked(client.patch(path, json=change), 422)
    project_id, revision_id = base.split("/")[3], base.split("/")[5]
    checked(client.post(f"/api/projects/{project_id}/revisions/{revision_id}/activate"))
    checked(
        client.post(
            f"/api/projects/{project_id}/revisions",
            json={"identifier": "child", "based_on_revision_id": revision_id, "activate": True},
        ),
        201,
    )
    checked(client.patch(path, json={"general": {"tag": "Read only"}}), 409)


def test_carry_forward_preserves_profile_and_custom_identity(model_api):
    base = model_api
    owner = equipment(base, "CABLE")
    custom = node(base, kind="EQUIPMENT_TERMINAL", equipment_id=owner["id"], terminal_key="GROUND")
    original = {n["id"]: n for n in items(base, "nodes")}
    project_id, revision_id = base.split("/")[3], base.split("/")[5]
    child = checked(
        client.post(
            f"/api/projects/{project_id}/revisions",
            json={
                "identifier": "child",
                "based_on_revision_id": revision_id,
                "carry_forward_model": True,
                "carry_forward_documents": False,
            },
        ),
        201,
    )
    clones = items(f"/api/projects/{project_id}/revisions/{child['id']}", "nodes")
    assert len(clones) == 3
    for clone in clones:
        source = original[clone["inherited_from_node_id"]]
        assert clone["id"] != source["id"] and clone["equipment_id"] != owner["id"]
        assert clone["managed_by_profile"] == source["managed_by_profile"]
    assert not next(n for n in clones if n["inherited_from_node_id"] == custom["id"])[
        "managed_by_profile"
    ]


def test_editor_reset_and_type_change_share_one_transaction(model_api):
    owner = equipment(model_api)
    path = f"{model_api}/equipment/{owner['id']}"
    checked(
        client.put(
            path + "/attributes/bus_type",
            json={"information_state": "PRESENT", "value": "SWITCHGEAR"},
        )
    )
    changed = checked(
        client.patch(
            path + "/editor",
            json={
                "general": {"equipment_type": "CABLE"},
                "attributes": {"bus_type": {"information_state": "NOT_POPULATED"}},
            },
        )
    )
    assert changed["equipment"]["equipment_type"] == "CABLE"
    assert {
        n["terminal_key"] for n in changed["terminals"] if n["lifecycle_status"] == "ACTIVE"
    } == {"END_A", "END_B"}


@pytest.mark.parametrize("populated", [False, True])
def test_child_type_change_uses_attribute_content_not_inheritance_pointer(model_api, populated):
    source = equipment(model_api, "BUS")
    source_path = f"{model_api}/equipment/{source['id']}"
    if populated:
        checked(
            client.put(
                source_path + "/attributes/bus_type",
                json={
                    "information_state": "PRESENT",
                    "value": "SWITCHGEAR",
                },
            )
        )
    original = checked(client.get(source_path + "/editor"))
    project_id, revision_id = model_api.split("/")[3], model_api.split("/")[5]
    child = checked(
        client.post(
            f"/api/projects/{project_id}/revisions",
            json={
                "identifier": "child",
                "based_on_revision_id": revision_id,
                "carry_forward_model": True,
                "carry_forward_documents": False,
            },
        ),
        201,
    )
    base = f"/api/projects/{project_id}/revisions/{child['id']}"
    clone = items(base, "equipment")[0]
    path = f"{base}/equipment/{clone['id']}/editor"
    before = checked(client.get(path))
    bus_type = next(a for a in before["attributes"] if a["attribute_key"] == "bus_type")
    original_type = next(a for a in original["attributes"] if a["attribute_key"] == "bus_type")
    assert bus_type["inherited_from_attribute_id"] == original_type["id"]
    if not populated:
        assert bus_type["information_state"] == "NOT_POPULATED"
        assert bus_type["verification_state"] == "UNVERIFIED"
        assert all(
            bus_type[key] is None
            for key in (
                "origin",
                "confidence",
                "numeric_value",
                "integer_value",
                "text_value",
                "boolean_value",
            )
        )
    response = client.patch(path, json={"general": {"equipment_type": "CABLE", "tag": "Child"}})
    if populated:
        checked(response, 409)
        assert checked(client.get(path)) == before
    else:
        saved = checked(response)
        assert saved["equipment"]["equipment_type"] == "CABLE"
        assert saved["equipment"]["lineage_id"] == source["lineage_id"]
        assert "bus_type" not in {a["attribute_key"] for a in saved["attributes"]}
        assert {
            n["terminal_key"] for n in saved["terminals"] if n["lifecycle_status"] == "ACTIVE"
        } == {"END_A", "END_B"}
    assert checked(client.get(source_path + "/editor")) == original
