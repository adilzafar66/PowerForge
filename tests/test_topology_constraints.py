"""Raw PostgreSQL checks protect topology even when services are bypassed."""

import pytest

from engineering_support import engineering_context as engineering_context
from engineering_support import seed_revision
from powerforge_persistence import ProjectRevision
from test_engineering_constraints import rejects
from topology_support import graph as graph

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "assignment",
    [
        "equipment_id=NULL",
        "terminal_key=NULL",
        "terminal_key='   '",
        "kind='ELECTRICAL_NODE'",
    ],
)
def test_node_shape(graph, assignment):
    rejects(
        graph.ctx.session,
        f"UPDATE model_nodes SET {assignment} WHERE id=:id",
        {"id": graph.terminal.id},
        "ck_model_nodes_shape",
    )


def test_node_ownership_uniqueness_and_inheritance(graph):
    g, ctx, svc = graph, graph.ctx, graph.topology
    other_ids = seed_revision(ctx.session)
    foreign_equipment = ctx.service.create_equipment(*other_ids, "BUS")
    foreign_node = svc.create_electrical_node(*other_ids)
    second_revision = ProjectRevision(project_id=ctx.project_id, identifier="same-project")
    ctx.session.add(second_revision)
    ctx.session.commit()
    same_project_equipment = ctx.service.create_equipment(ctx.project_id, second_revision.id, "BUS")
    # Equal terminal names across equipment are valid; removed rows still reserve the key.
    another = svc.create_terminal(*ctx.ids, g.bus.id, "A")
    for equipment in [foreign_equipment, same_project_equipment]:
        rejects(
            ctx.session,
            "UPDATE model_nodes SET equipment_id=:e WHERE id=:id",
            {"id": g.terminal.id, "e": equipment.id},
            "fk_model_nodes_equipment",
        )
    rejects(
        ctx.session,
        "UPDATE model_nodes SET terminal_key='MAIN' WHERE id=:id",
        {"id": another.id},
        "uq_model_nodes_terminal",
    )
    for source, constraint in [
        (g.terminal.id, "ck_model_nodes_inherited_not_self"),
        (foreign_node.id, "fk_model_nodes_inherited_from"),
    ]:
        rejects(
            ctx.session,
            "UPDATE model_nodes SET inherited_from_node_id=:source WHERE id=:id",
            {"id": g.terminal.id, "source": source},
            constraint,
        )
    isolated = svc.create_electrical_node(*ctx.ids)
    rejects(
        ctx.session,
        "UPDATE model_nodes SET revision_id=:r WHERE id=:id",
        {"id": isolated.id, "r": other_ids[1]},
        "fk_model_nodes_revision",
    )
    rejects(
        ctx.session,
        "UPDATE model_nodes SET lifecycle_status='REMOVED' WHERE id=:id",
        {"id": g.junction.id},
        "ck_model_nodes_lifecycle",
    )


def test_connection_ownership_self_loop_parallel_and_inheritance(graph):
    g, ctx, svc = graph, graph.ctx, graph.topology
    foreign_ids = seed_revision(ctx.session)
    foreign_a = svc.create_electrical_node(*foreign_ids)
    foreign_b = svc.create_electrical_node(*foreign_ids)
    foreign_edge = svc.create_connection(*foreign_ids, foreign_a.id, foreign_b.id)
    second = ProjectRevision(project_id=ctx.project_id, identifier="same-project")
    ctx.session.add(second)
    ctx.session.commit()
    same_project_node = svc.create_electrical_node(ctx.project_id, second.id)
    assert len(svc.list_connections(*ctx.ids)) == 3  # Parallel edges in fixture.
    for endpoint in ["from_node_id", "to_node_id"]:
        for node in [foreign_a, same_project_node]:
            rejects(
                ctx.session,
                f"UPDATE model_connections SET {endpoint}=:node WHERE id=:id",
                {"id": g.edges[0].id, "node": node.id},
                f"fk_model_connections_{endpoint.removesuffix('_id')}",
            )
    rejects(
        ctx.session,
        "UPDATE model_connections SET to_node_id=from_node_id WHERE id=:id",
        {"id": g.edges[0].id},
        "ck_model_connections_not_self_loop",
    )
    for source, constraint in [
        (g.edges[0].id, "ck_model_connections_inherited_not_self"),
        (foreign_edge.id, "fk_model_connections_inherited_from"),
    ]:
        rejects(
            ctx.session,
            "UPDATE model_connections SET inherited_from_connection_id=:source WHERE id=:id",
            {"id": g.edges[0].id, "source": source},
            constraint,
        )
    rejects(
        ctx.session,
        "UPDATE model_connections SET lifecycle_status='REMOVED' WHERE id=:id",
        {"id": g.edges[0].id},
        "ck_model_connections_lifecycle",
    )


@pytest.mark.parametrize("value", ["-0.1", "1.1", "NaN", "Infinity", "-Infinity"])
def test_connection_confidence_bounds(graph, value):
    rejects(
        graph.ctx.session,
        "UPDATE model_connections SET confidence=CAST(:v AS numeric) WHERE id=:id",
        {"id": graph.edges[0].id, "v": value},
        "ck_model_connections_confidence",
    )


@pytest.mark.parametrize(
    "value,unit",
    [
        (None, "kV"),
        ("1", None),
        ("1", "V"),
        ("0", "kV"),
        ("-1", "kV"),
        ("NaN", "kV"),
        ("Infinity", "kV"),
        ("-Infinity", "kV"),
    ],
)
def test_connection_voltage_pairing(graph, value, unit):
    rejects(
        graph.ctx.session,
        "UPDATE model_connections SET nominal_voltage=CAST(:v AS numeric), "
        "nominal_voltage_unit=:u WHERE id=:id",
        {"id": graph.edges[0].id, "v": value, "u": unit},
        "ck_model_connections_voltage",
    )
