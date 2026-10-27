"""Graph snapshot remapping, conservative corruption handling and atomic rollback."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import event, text

from engineering_support import engineering_context as engineering_context
from powerforge_api.exceptions import ModelInheritanceConflict
from powerforge_api.schemas.projects import RevisionCreate
from powerforge_api.services.engineering_model_inheritance import copy_active_engineering_model
from powerforge_api.services.revision_service import RevisionService
from powerforge_api.services.topology_inheritance import copy_active_topology
from powerforge_engineering_model import LifecycleStatus, ValueOrigin, VerificationState
from powerforge_persistence import ProjectRevision
from powerforge_project import RevisionStatus
from test_phase5c_revision_model import _seed_document
from topology_support import graph as graph

pytestmark = pytest.mark.integration


def clone(graph, *, base=None, identifier="1", **kwargs):
    ctx = graph.ctx
    return RevisionService(ctx.session).create_revision(
        ctx.project_id,
        RevisionCreate(
            identifier=identifier, based_on_revision_id=base or ctx.revision_id, **kwargs
        ),
    )


def test_graph_remaps_exact_metadata_and_immediate_base_with_independent_snapshots(graph):
    g, ctx, svc = graph, graph.ctx, graph.topology
    removed = svc.create_electrical_node(*ctx.ids, label="removed")
    svc.remove_node(*ctx.ids, removed.id)
    old_edge = svc.create_connection(*ctx.ids, g.terminal.id, g.junction.id)
    svc.remove_connection(*ctx.ids, old_edge.id)
    g.edges[0].origin = ValueOrigin.IMPORTED
    g.edges[0].verification_state = VerificationState.AI_EXTRACTED
    g.edges[0].confidence = Decimal("0.73")
    ctx.session.commit()
    child = clone(g)
    assert child.inherited_model_equipment_count == 2
    child_ids = (ctx.project_id, child.revision.id)
    nodes = svc.list_nodes(*child_ids)
    edges = svc.list_connections(*child_ids)
    assert len(nodes) == 7 and len(edges) == 3
    equipment = {
        r.inherited_from_equipment_id: r.id for r in ctx.service.list_equipment(*child_ids)
    }
    node_map = {n.inherited_from_node_id: n for n in nodes}
    assert removed.id not in node_map
    for source in [g.terminal, g.cable_a, g.cable_b, g.junction]:
        dest = node_map[source.id]
        assert dest.id != source.id
        assert dest.equipment_id == equipment.get(source.equipment_id)
        assert (dest.kind, dest.label, dest.terminal_key, dest.origin, dest.verification_state) == (
            source.kind,
            source.label,
            source.terminal_key,
            source.origin,
            source.verification_state,
        )
    for source in g.edges:
        dest = next(e for e in edges if e.inherited_from_connection_id == source.id)
        assert dest.id != source.id
        assert dest.from_node_id == node_map[source.from_node_id].id
        assert dest.to_node_id == node_map[source.to_node_id].id
        for field in [
            "connection_kind",
            "direction",
            "phase_configuration",
            "nominal_voltage",
            "nominal_voltage_unit",
            "confidence",
            "origin",
            "verification_state",
        ]:
            assert getattr(dest, field) == getattr(source, field)
    # A second generation points to the immediate base, not the original ancestors.
    grandchild = clone(g, base=child.revision.id, identifier="2")
    assert {
        n.inherited_from_node_id for n in svc.list_nodes(ctx.project_id, grandchild.revision.id)
    } == {n.id for n in nodes}
    assert {
        e.inherited_from_connection_id
        for e in svc.list_connections(ctx.project_id, grandchild.revision.id)
    } == {e.id for e in edges}
    svc.update_node(*child_ids, node_map[g.terminal.id].id, label="Child", terminal_key="CHILD")
    svc.update_connection(*child_ids, edges[0].id, phase_configuration="CHILD")
    svc.remove_connection(*child_ids, edges[0].id)
    assert g.terminal.terminal_key == "MAIN"
    assert all(e.lifecycle_status == LifecycleStatus.ACTIVE for e in g.edges)
    svc.update_node(*ctx.ids, g.junction.id, label="Source changed")
    assert node_map[g.junction.id].label == "Junction"
    assert svc.list_connections(*child_ids, lifecycle_status=None)[0].phase_configuration == "CHILD"
    empty = clone(g, identifier="fresh", carry_forward_model=False)
    assert svc.list_nodes(ctx.project_id, empty.revision.id) == []
    assert svc.list_connections(ctx.project_id, empty.revision.id) == []


def snapshot(session, project_id):
    # Also covers the document package and canonical attribute rows.
    return {
        table: session.execute(
            text(f"SELECT to_jsonb(t) FROM {table} t WHERE project_id=:p ORDER BY id"),
            {"p": project_id},
        )
        .scalars()
        .all()
        for table in [
            "project_revisions",
            "revision_documents",
            "equipment",
            "equipment_attributes",
            "model_nodes",
            "model_connections",
        ]
    }


@pytest.mark.parametrize("corruption", ["equipment", "endpoint", "during_clone"])
def test_inconsistent_source_or_partial_clone_rolls_back_entire_revision(graph, corruption):
    ctx = graph.ctx
    base = ctx.session.get(ProjectRevision, ctx.revision_id)
    base.status = RevisionStatus.ACTIVE
    ctx.session.commit()
    _seed_document(str(ctx.project_id), str(ctx.revision_id))
    if corruption in ("equipment", "endpoint"):
        row = graph.cable if corruption == "equipment" else graph.cable_a
        row.lifecycle_status = LifecycleStatus.REMOVED
        row.removed_at = datetime.now(UTC)
        ctx.session.commit()
    before = snapshot(ctx.session, ctx.project_id)
    inserts = []

    def fail_after_node_flush(conn, cursor, statement, *rest):
        if statement.startswith("INSERT INTO model_nodes"):
            inserts.append(statement)
            if len(inserts) == 2:
                raise RuntimeError("Injected failure after target node was flushed")

    engine = ctx.session.get_bind()
    if corruption == "during_clone":
        event.listen(engine, "after_cursor_execute", fail_after_node_flush)
    try:
        with pytest.raises(
            RuntimeError if corruption == "during_clone" else ModelInheritanceConflict
        ):
            clone(graph, activate=True)
    finally:
        if corruption == "during_clone":
            event.remove(engine, "after_cursor_execute", fail_after_node_flush)
    assert snapshot(ctx.session, ctx.project_id) == before
    assert ctx.session.get(ProjectRevision, ctx.revision_id).status == RevisionStatus.ACTIVE


def test_clone_helpers_reject_arbitrary_same_project_source(graph):
    ctx = graph.ctx
    target = ProjectRevision(project_id=ctx.project_id, identifier="unbased")
    ctx.session.add(target)
    ctx.session.flush()
    source = ctx.session.get(ProjectRevision, ctx.revision_id)
    with pytest.raises(ModelInheritanceConflict):
        copy_active_engineering_model(ctx.session, source, target)
    with pytest.raises(ModelInheritanceConflict):
        copy_active_topology(ctx.session, source, target, {})
    ctx.session.rollback()


def test_equipment_cascade_failure_is_atomic(graph, monkeypatch):
    from powerforge_api.services import engineering_model_service

    ctx = graph.ctx
    before = snapshot(ctx.session, ctx.project_id)
    original = engineering_model_service.set_equipment_topology_lifecycle

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        ctx.session.flush()
        raise RuntimeError("cascade failed")

    monkeypatch.setattr(engineering_model_service, "set_equipment_topology_lifecycle", fail)
    with pytest.raises(RuntimeError):
        ctx.service.remove_equipment(*ctx.ids, graph.cable.id)
    assert snapshot(ctx.session, ctx.project_id) == before
