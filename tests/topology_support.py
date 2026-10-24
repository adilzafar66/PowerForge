"""One reusable manual topology graph for lifecycle, clone, and structural tests."""

from dataclasses import dataclass

import pytest

from engineering_support import engineering_context as engineering_context
from powerforge_api.services.topology_service import TopologyService
from powerforge_topology import ConnectionKind


@dataclass
class Graph:
    ctx: object
    topology: TopologyService
    bus: object
    cable: object
    terminal: object
    cable_a: object
    cable_b: object
    junction: object
    edges: list


@pytest.fixture
def graph(engineering_context):
    ctx = engineering_context
    svc = TopologyService(ctx.session)
    bus = ctx.service.create_equipment(*ctx.ids, "BUS")
    cable = ctx.service.create_equipment(*ctx.ids, "CABLE")
    terminal = svc.create_terminal(*ctx.ids, bus.id, " MAIN ")
    a = svc.create_terminal(*ctx.ids, cable.id, "A")
    b = svc.create_terminal(*ctx.ids, cable.id, "B")
    junction = svc.create_electrical_node(*ctx.ids, label="Junction")
    edges = [
        svc.create_connection(
            *ctx.ids,
            terminal.id,
            a.id,
            nominal_voltage=600,
            input_unit="V",
            phase_configuration=" ABC ",
        ),
        svc.create_connection(*ctx.ids, b.id, junction.id),
        svc.create_connection(
            *ctx.ids, b.id, junction.id, connection_kind=ConnectionKind.GROUNDING
        ),
    ]
    yield Graph(ctx, svc, bus, cable, terminal, a, b, junction, edges)
