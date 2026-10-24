"""Copy active topology with explicit equipment/node maps in the caller's transaction."""

from uuid import UUID

from sqlalchemy.orm import Session

from powerforge_api.exceptions import InvalidTopology, ModelInheritanceConflict
from powerforge_api.services.topology_support import validate_topology_consistency
from powerforge_engineering_model import LifecycleStatus
from powerforge_persistence import ProjectRevision
from powerforge_persistence.topology import ModelConnection, ModelNode
from powerforge_topology import ModelNodeKind


def copy_active_topology(
    session: Session,
    source: ProjectRevision,
    target: ProjectRevision,
    equipment_map: dict[UUID, UUID],
    *,
    actor_id: UUID | None = None,
) -> tuple[int, int]:
    if (
        source.project_id != target.project_id
        or target.based_on_revision_id != source.id
        or source.id == target.id
    ):
        raise ModelInheritanceConflict("Topology source must be the selected base revision")
    try:
        nodes, connections = validate_topology_consistency(session, source.project_id, source.id)
    except InvalidTopology as exc:
        raise ModelInheritanceConflict("Base revision contains inconsistent topology") from exc
    node_map = {}
    for row in nodes:
        if row.lifecycle_status != LifecycleStatus.ACTIVE:
            continue
        equipment_id = None
        if row.kind == ModelNodeKind.EQUIPMENT_TERMINAL:
            equipment_id = equipment_map.get(row.equipment_id)
            if equipment_id is None:
                raise ModelInheritanceConflict("Active terminal equipment was not cloned")
        clone = ModelNode(
            project_id=target.project_id,
            revision_id=target.id,
            kind=row.kind,
            equipment_id=equipment_id,
            terminal_key=row.terminal_key,
            label=row.label,
            origin=row.origin,
            verification_state=row.verification_state,
            inherited_from_node_id=row.id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(clone)
        session.flush()
        node_map[row.id] = clone.id
    count = 0
    for row in connections:
        if row.lifecycle_status != LifecycleStatus.ACTIVE:
            continue
        if row.from_node_id not in node_map or row.to_node_id not in node_map:
            raise ModelInheritanceConflict("Active connection endpoint was not cloned")
        session.add(
            ModelConnection(
                project_id=target.project_id,
                revision_id=target.id,
                from_node_id=node_map[row.from_node_id],
                to_node_id=node_map[row.to_node_id],
                connection_kind=row.connection_kind,
                direction=row.direction,
                phase_configuration=row.phase_configuration,
                nominal_voltage=row.nominal_voltage,
                nominal_voltage_unit=row.nominal_voltage_unit,
                origin=row.origin,
                verification_state=row.verification_state,
                confidence=row.confidence,
                inherited_from_connection_id=row.id,
                created_by=actor_id,
                updated_by=actor_id,
            )
        )
        count += 1
    session.flush()
    validate_topology_consistency(session, target.project_id, target.id)
    return len(node_map), count
