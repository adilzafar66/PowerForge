"""Topology integrity and lifecycle helpers participating in the caller's transaction."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from powerforge_api.exceptions import InvalidTopology
from powerforge_engineering_model import LifecycleStatus, ValueOrigin, VerificationState
from powerforge_engineering_model.terminal_profiles import terminal_profile
from powerforge_persistence.engineering import Equipment
from powerforge_persistence.topology import ModelConnection, ModelNode
from powerforge_topology import ConnectionDirection, ConnectionKind, ModelNodeKind


def topology_constraint_errors() -> dict[str, InvalidTopology]:
    names = (
        "fk_model_nodes_revision",
        "fk_model_nodes_equipment",
        "fk_model_nodes_inherited_from",
        "uq_model_nodes_terminal",
        "ck_model_nodes_shape",
        "ck_model_nodes_inherited_not_self",
        "ck_model_nodes_lifecycle",
        "fk_model_connections_revision",
        "fk_model_connections_from_node",
        "fk_model_connections_to_node",
        "fk_model_connections_inherited_from",
        "ck_model_connections_not_self_loop",
        "ck_model_connections_inherited_not_self",
        "ck_model_connections_lifecycle",
        "ck_model_connections_confidence",
        "ck_model_connections_voltage",
    )
    return {name: InvalidTopology(f"Topology constraint violated: {name}") for name in names}


def scoped_rows(session, model, project_id, revision_id):
    try:
        return list(
            session.scalars(
                select(model)
                .where(model.project_id == project_id, model.revision_id == revision_id)
                .order_by(model.created_at, model.id)
                .execution_options(populate_existing=True)
            )
        )
    except LookupError as exc:
        raise InvalidTopology("Persisted topology uses an unknown enum state") from exc


def _validate_common(row):
    if (
        row.lifecycle_status not in tuple(LifecycleStatus)
        or row.origin not in tuple(ValueOrigin)
        or row.verification_state not in tuple(VerificationState)
    ):
        raise InvalidTopology("Unknown topology state")
    if row.lifecycle_status == LifecycleStatus.ACTIVE:
        if row.removed_at is not None or row.removed_by is not None:
            raise InvalidTopology("Active topology has removal metadata")
    elif row.removed_at is None:
        raise InvalidTopology("Removed topology lacks a removal timestamp")


def validate_node(node: ModelNode, equipment_by_id: dict[UUID, Equipment]) -> None:
    _validate_common(node)
    if node.kind == ModelNodeKind.ELECTRICAL_NODE:
        if node.equipment_id is not None or node.terminal_key is not None:
            raise InvalidTopology("Electrical nodes cannot reference equipment or a terminal key")
    elif node.kind == ModelNodeKind.EQUIPMENT_TERMINAL:
        if not isinstance(node.terminal_key, str) or not node.terminal_key.strip():
            raise InvalidTopology("Terminal requires a nonblank key")
        equipment = equipment_by_id.get(node.equipment_id)
        if equipment is None or (equipment.project_id, equipment.revision_id) != (
            node.project_id,
            node.revision_id,
        ):
            raise InvalidTopology("Terminal equipment ownership is invalid")
        if node.lifecycle_status == LifecycleStatus.ACTIVE and (
            equipment.lifecycle_status != LifecycleStatus.ACTIVE
        ):
            raise InvalidTopology("Active terminal requires active equipment")
    else:
        raise InvalidTopology("Unknown node kind")


def validate_connection(connection: ModelConnection, nodes_by_id: dict[UUID, ModelNode]) -> None:
    _validate_common(connection)
    if connection.connection_kind not in tuple(ConnectionKind) or (
        connection.direction not in tuple(ConnectionDirection)
    ):
        raise InvalidTopology("Unknown connection kind or direction")
    if connection.from_node_id == connection.to_node_id:
        raise InvalidTopology("A connection cannot connect a node to itself")
    for node_id in (connection.from_node_id, connection.to_node_id):
        node = nodes_by_id.get(node_id)
        if node is None or (node.project_id, node.revision_id) != (
            connection.project_id,
            connection.revision_id,
        ):
            raise InvalidTopology("Connection endpoint ownership is invalid")
        if connection.lifecycle_status == LifecycleStatus.ACTIVE and (
            node.lifecycle_status != LifecycleStatus.ACTIVE
        ):
            raise InvalidTopology("Active connection requires active endpoints")
    voltage = connection.nominal_voltage
    if voltage is None:
        if connection.nominal_voltage_unit is not None:
            raise InvalidTopology("Voltage unit requires a value")
    elif not voltage.is_finite() or voltage <= 0 or connection.nominal_voltage_unit != "kV":
        raise InvalidTopology("Voltage must be positive finite canonical kV")
    confidence = connection.confidence
    if confidence is not None and (not confidence.is_finite() or not 0 <= confidence <= 1):
        raise InvalidTopology("Confidence must be finite and between zero and one")


def validate_topology_consistency(
    session: Session, project_id: UUID, revision_id: UUID
) -> tuple[list[ModelNode], list[ModelConnection]]:
    """Check structural state, without engineering findings or silent repairs."""
    equipment = {r.id: r for r in scoped_rows(session, Equipment, project_id, revision_id)}
    nodes = scoped_rows(session, ModelNode, project_id, revision_id)
    connections = scoped_rows(session, ModelConnection, project_id, revision_id)
    keys = set()
    for node in nodes:
        validate_node(node, equipment)
        if node.kind == ModelNodeKind.EQUIPMENT_TERMINAL:
            key = (node.equipment_id, node.terminal_key.strip())
            if key in keys:
                raise InvalidTopology("Duplicate terminal key within equipment")
            keys.add(key)
    by_id = {r.id: r for r in nodes}
    for connection in connections:
        validate_connection(connection, by_id)
    return nodes, connections


def set_lifecycle(row, status, actor_id, now):
    if row.lifecycle_status == status:
        return
    row.lifecycle_status = status
    row.removed_at = now if status == LifecycleStatus.REMOVED else None
    row.removed_by = actor_id if status == LifecycleStatus.REMOVED else None
    row.updated_at, row.updated_by = now, actor_id


def soft_remove_incident_connections(session, project_id, revision_id, node_ids, actor_id, now):
    if not node_ids:
        return
    rows = session.scalars(
        select(ModelConnection)
        .where(
            ModelConnection.project_id == project_id,
            ModelConnection.revision_id == revision_id,
            ModelConnection.lifecycle_status == LifecycleStatus.ACTIVE,
            or_(
                ModelConnection.from_node_id.in_(node_ids), ModelConnection.to_node_id.in_(node_ids)
            ),
        )
        .execution_options(populate_existing=True)
    )
    for row in rows:
        set_lifecycle(row, LifecycleStatus.REMOVED, actor_id, now)


def set_equipment_topology_lifecycle(
    session: Session, equipment: Equipment, status: LifecycleStatus, actor_id: UUID | None
) -> None:
    """Called under the equipment mutation's revision lock. Never commits."""
    now = datetime.now(UTC)
    nodes = list(
        session.scalars(
            select(ModelNode)
            .where(
                ModelNode.project_id == equipment.project_id,
                ModelNode.revision_id == equipment.revision_id,
                ModelNode.equipment_id == equipment.id,
            )
            .execution_options(populate_existing=True)
        )
    )
    if status == LifecycleStatus.REMOVED:
        soft_remove_incident_connections(
            session,
            equipment.project_id,
            equipment.revision_id,
            [n.id for n in nodes],
            actor_id,
            now,
        )
    for node in nodes:
        if (
            status == LifecycleStatus.ACTIVE
            and node.managed_by_profile
            and node.terminal_key not in terminal_profile(equipment.equipment_type)
        ):
            continue
        set_lifecycle(node, status, actor_id, now)
