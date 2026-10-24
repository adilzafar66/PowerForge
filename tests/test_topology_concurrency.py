"""One risk-driven clone race: a node removal and its edge cascade are indivisible."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from engineering_support import engineering_context as engineering_context
from powerforge_api.schemas.projects import RevisionCreate
from powerforge_api.services import topology_service
from powerforge_api.services.revision_service import RevisionService
from powerforge_api.services.topology_service import TopologyService
from test_engineering_concurrency import wait_blocked
from topology_support import graph as graph

pytestmark = pytest.mark.integration


def test_clone_waits_for_complete_topology_mutation(graph, monkeypatch):
    ctx = graph.ctx
    engine = ctx.session.get_bind()
    ids, node_id = ctx.ids, graph.cable_b.id
    partial, release, clone_ready = Event(), Event(), Event()
    backend = {}
    original = topology_service.soft_remove_incident_connections

    def hold_after_edge_removal(session, *args):
        original(session, *args)
        session.flush()  # Edges removed, node still ACTIVE: uncommitted partial state.
        partial.set()
        assert release.wait(10)

    monkeypatch.setattr(
        topology_service, "soft_remove_incident_connections", hold_after_edge_removal
    )

    def mutate():
        with Session(engine) as session:
            TopologyService(session).remove_node(*ids, node_id)

    def clone():
        with Session(engine) as session:
            backend["pid"] = session.scalar(text("SELECT pg_backend_pid()"))
            clone_ready.set()
            result = RevisionService(session).create_revision(
                ids[0], RevisionCreate(identifier="race", based_on_revision_id=ids[1])
            )
            return result.revision.id

    with ThreadPoolExecutor(max_workers=2) as pool:
        mutation = pool.submit(mutate)
        try:
            assert partial.wait(10)
            inheritance = pool.submit(clone)
            assert clone_ready.wait(10)
            wait_blocked(engine, backend["pid"])
        finally:
            release.set()
        mutation.result(timeout=10)
        child_id = inheritance.result(timeout=10)
    with Session(engine) as session:
        svc = TopologyService(session)
        nodes = svc.list_nodes(ids[0], child_id)
        edges = svc.list_connections(ids[0], child_id)
        assert len(nodes) == 3 and len(edges) == 1
        assert node_id not in {n.inherited_from_node_id for n in nodes}
        assert edges[0].from_node_id in {n.id for n in nodes}
        assert edges[0].to_node_id in {n.id for n in nodes}
