"""Manual authoring, conservative lifecycle, ownership and shared guard coverage."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import event

from engineering_support import engineering_context as engineering_context
from engineering_support import seed_revision
from powerforge_api.exceptions import (
    ArchivedProject,
    CancelledProject,
    EquipmentNotFound,
    InvalidTopology,
    ModelConnectionNotFound,
    ModelNodeNotFound,
    ProjectNotFound,
    RevisionNotFound,
    RevisionReadOnly,
    TopologyObjectRemoved,
)
from powerforge_api.services.topology_service import TopologyService
from powerforge_api.services.topology_support import validate_topology_consistency
from powerforge_engineering_model import LifecycleStatus, ValueOrigin, VerificationState
from powerforge_persistence import Project, ProjectRevision
from powerforge_project import ProjectStatus, RevisionStatus
from powerforge_topology import ConnectionDirection, ModelNodeKind
from topology_support import graph as graph

pytestmark = pytest.mark.integration


def test_manual_nodes_connections_scoping_and_safe_edits(graph):
    g, ctx, svc = graph, graph.ctx, graph.topology
    assert g.terminal.terminal_key == "MAIN"
    assert g.junction.kind == ModelNodeKind.ELECTRICAL_NODE
    assert g.junction.equipment_id is g.junction.terminal_key is None
    for row in [g.terminal, *g.edges]:
        assert row.origin == ValueOrigin.MANUAL
        assert row.verification_state == VerificationState.ENGINEER_REVIEWED
    assert g.edges[0].phase_configuration == "ABC"
    assert g.edges[1].nominal_voltage is g.edges[1].phase_configuration is None
    with pytest.raises(InvalidTopology):
        svc.create_terminal(*ctx.ids, g.bus.id, " MAIN ")
    with pytest.raises(InvalidTopology):
        svc.create_terminal(*ctx.ids, g.bus.id, "   ")
    with pytest.raises(InvalidTopology):
        svc.update_node(*ctx.ids, g.junction.id, terminal_key="X")
    with pytest.raises(TypeError):
        svc.update_node(*ctx.ids, g.terminal.id, equipment_id=g.cable.id)
    with pytest.raises(TypeError):
        svc.update_node(*ctx.ids, g.terminal.id, kind=ModelNodeKind.ELECTRICAL_NODE)
    svc.update_node(*ctx.ids, g.terminal.id, terminal_key=" IN ", label=" Bus ")
    assert g.terminal.terminal_key == "IN" and g.terminal.label == "Bus"
    with pytest.raises(InvalidTopology):
        svc.create_connection(*ctx.ids, g.junction.id, g.junction.id)
    svc.update_connection(
        *ctx.ids,
        g.edges[0].id,
        to_node_id=g.junction.id,
        direction=ConnectionDirection.NOMINAL_FROM_TO,
        nominal_voltage="13.8",
    )
    assert g.edges[0].to_node_id == g.junction.id
    assert g.edges[0].from_node_id == g.terminal.id
    with pytest.raises(TypeError):
        svc.create_connection(*ctx.ids, g.terminal.id, g.junction.id, confidence="0.5")
    other = seed_revision(ctx.session)
    foreign = TopologyService(ctx.session).create_electrical_node(*other)
    for operation, error in [
        (lambda: svc.get_node(*other, g.terminal.id), ModelNodeNotFound),
        (lambda: svc.get_connection(*other, g.edges[0].id), ModelConnectionNotFound),
        (lambda: svc.get_node(uuid4(), ctx.revision_id, g.terminal.id), ProjectNotFound),
        (lambda: svc.list_nodes(ctx.project_id, other[1]), RevisionNotFound),
        (lambda: svc.create_terminal(*other, g.bus.id, "A"), EquipmentNotFound),
        (lambda: svc.create_connection(*ctx.ids, g.terminal.id, foreign.id), ModelNodeNotFound),
        (
            lambda: svc.update_connection(*ctx.ids, g.edges[0].id, to_node_id=foreign.id),
            ModelNodeNotFound,
        ),
    ]:
        with pytest.raises(error):
            operation()
    assert g.edges[0].to_node_id == g.junction.id
    assert len(svc.list_nodes(*ctx.ids)) == 4
    assert len(svc.list_connections(*ctx.ids)) == 3


def test_equipment_and_node_lifecycle_cascades_are_conservative(graph):
    g, ctx, svc = graph, graph.ctx, graph.topology
    actor = uuid4()
    # Keep an unrelated edge/node and equipment terminal outside the cable cascade.
    unaffected = svc.create_connection(*ctx.ids, g.terminal.id, g.junction.id)
    svc.remove_node(*ctx.ids, g.cable_b.id)
    assert g.cable_b.lifecycle_status == LifecycleStatus.REMOVED
    assert all(e.lifecycle_status == LifecycleStatus.REMOVED for e in g.edges[1:])
    svc.restore_node(*ctx.ids, g.cable_b.id)
    assert all(e.lifecycle_status == LifecycleStatus.REMOVED for e in g.edges[1:])
    for edge in g.edges[1:]:
        svc.restore_connection(*ctx.ids, edge.id)
    ctx.service.remove_equipment(*ctx.ids, g.cable.id, actor_id=actor)
    for row in [g.cable_a, g.cable_b, *g.edges]:
        ctx.session.refresh(row)
        assert row.lifecycle_status == LifecycleStatus.REMOVED
        assert row.removed_by == actor
        assert row.origin == ValueOrigin.MANUAL
    assert g.terminal.lifecycle_status == g.junction.lifecycle_status == LifecycleStatus.ACTIVE
    assert unaffected.lifecycle_status == LifecycleStatus.ACTIVE
    with pytest.raises(InvalidTopology):
        svc.restore_node(*ctx.ids, g.cable_a.id)
    with pytest.raises(InvalidTopology):
        svc.create_terminal(*ctx.ids, g.cable.id, "C")
    with pytest.raises(TopologyObjectRemoved):
        svc.restore_connection(*ctx.ids, g.edges[0].id)
    with pytest.raises(TopologyObjectRemoved):
        svc.update_connection(*ctx.ids, g.edges[0].id, phase_configuration="A")
    ctx.service.restore_equipment(*ctx.ids, g.cable.id)
    assert all(n.lifecycle_status == LifecycleStatus.ACTIVE for n in [g.cable_a, g.cable_b])
    assert all(e.lifecycle_status == LifecycleStatus.REMOVED for e in g.edges)
    assert len(svc.list_connections(*ctx.ids)) == 1
    assert len(svc.list_connections(*ctx.ids, lifecycle_status=None)) == 4
    svc.restore_connection(*ctx.ids, g.edges[0].id)
    svc.remove_node(*ctx.ids, g.terminal.id)
    with pytest.raises(TopologyObjectRemoved):
        svc.create_connection(*ctx.ids, g.terminal.id, g.junction.id)
    svc.restore_node(*ctx.ids, g.terminal.id)
    assert g.edges[0].lifecycle_status == LifecycleStatus.REMOVED


@pytest.mark.parametrize("project_status", list(ProjectStatus))
@pytest.mark.parametrize("revision_status", list(RevisionStatus))
def test_representative_write_uses_existing_mutability_matrix(
    graph, project_status, revision_status
):
    ctx, svc = graph.ctx, graph.topology
    ctx.session.get(Project, ctx.project_id).status = project_status
    ctx.session.get(ProjectRevision, ctx.revision_id).status = revision_status
    ctx.session.commit()
    error = {
        ProjectStatus.ARCHIVED: ArchivedProject,
        ProjectStatus.CANCELLED: CancelledProject,
    }.get(project_status)
    if error is None and revision_status == RevisionStatus.SUPERSEDED:
        error = RevisionReadOnly
    if error:
        with pytest.raises(error):
            svc.create_electrical_node(*ctx.ids)
        assert not ctx.session.in_transaction()
    else:
        svc.create_electrical_node(*ctx.ids)
    assert svc.get_node(*ctx.ids, graph.junction.id)


def test_all_mutations_take_project_then_revision_locks(graph):
    g, ctx, svc = graph, graph.ctx, graph.topology
    operations = [
        lambda: svc.create_terminal(*ctx.ids, g.bus.id, "NEW"),
        lambda: svc.create_electrical_node(*ctx.ids),
        lambda: svc.update_node(*ctx.ids, g.junction.id, label="Edit"),
        lambda: svc.create_connection(*ctx.ids, g.terminal.id, g.junction.id),
        lambda: svc.update_connection(*ctx.ids, g.edges[0].id, phase_configuration="A"),
        lambda: svc.remove_connection(*ctx.ids, g.edges[0].id),
        lambda: svc.restore_connection(*ctx.ids, g.edges[0].id),
        lambda: svc.remove_node(*ctx.ids, g.junction.id),
        lambda: svc.restore_node(*ctx.ids, g.junction.id),
    ]
    statements = []

    def capture(conn, cursor, statement, *rest):
        statements.append(statement)

    engine = ctx.session.get_bind()
    event.listen(engine, "before_cursor_execute", capture)
    try:
        for operation in operations:
            statements.clear()
            operation()
            p = next(
                i for i, s in enumerate(statements) if "FROM projects" in s and "FOR SHARE" in s
            )
            r = next(
                i
                for i, s in enumerate(statements)
                if "FROM project_revisions" in s and "FOR UPDATE" in s
            )
            assert p < r
            assert not any(s.lstrip().startswith("UPDATE projects") for s in statements)
    finally:
        event.remove(engine, "before_cursor_execute", capture)


def test_consistency_detects_active_relationship_corruption(graph):
    ctx = graph.ctx
    graph.cable.lifecycle_status = LifecycleStatus.REMOVED
    graph.cable.removed_at = datetime.now(UTC)
    ctx.session.commit()  # SQL permits cross-row lifecycle corruption; service must detect it.
    with pytest.raises(InvalidTopology):
        validate_topology_consistency(ctx.session, *ctx.ids)
    with pytest.raises(InvalidTopology):
        graph.topology.get_node(*ctx.ids, graph.cable_a.id)
