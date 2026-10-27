"""Reconcile terminal roles inside the caller's locked revision transaction."""

from datetime import UTC, datetime

from sqlalchemy import or_, select

from powerforge_api.exceptions import EquipmentTypeChangeConflict
from powerforge_api.services.topology_support import set_lifecycle
from powerforge_engineering_model import LifecycleStatus
from powerforge_engineering_model.terminal_profiles import terminal_profile
from powerforge_persistence.topology import ModelConnection, ModelNode
from powerforge_topology import ModelNodeKind


def reconcile_terminals(session, equipment, actor_id=None, *, destination=None):
    required = terminal_profile(destination or equipment.equipment_type)
    nodes = list(session.scalars(select(ModelNode).where(ModelNode.equipment_id == equipment.id)))
    by_key = {node.terminal_key: node for node in nodes}
    obsolete = [n for n in nodes if n.managed_by_profile and n.terminal_key not in required]
    ids = [n.id for n in obsolete]
    if ids and session.scalar(
        select(ModelConnection.id)
        .where(
            ModelConnection.lifecycle_status == LifecycleStatus.ACTIVE,
            or_(ModelConnection.from_node_id.in_(ids), ModelConnection.to_node_id.in_(ids)),
        )
        .limit(1)
    ):
        raise EquipmentTypeChangeConflict(
            "Type change would remove profile terminals with active connections"
        )
    now = datetime.now(UTC)
    for node in obsolete:
        set_lifecycle(node, LifecycleStatus.REMOVED, actor_id, now)
    for key in required:
        node = by_key.get(key)
        if node is None:
            session.add(
                ModelNode(
                    project_id=equipment.project_id,
                    revision_id=equipment.revision_id,
                    equipment_id=equipment.id,
                    kind=ModelNodeKind.EQUIPMENT_TERMINAL,
                    terminal_key=key,
                    managed_by_profile=True,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        else:
            node.managed_by_profile = True
            set_lifecycle(node, LifecycleStatus.ACTIVE, actor_id, now)
    session.flush()
