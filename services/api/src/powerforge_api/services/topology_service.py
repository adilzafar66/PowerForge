"""Manual internal topology authoring, scoped to a writable project revision."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from powerforge_api.db_errors import integrity_guard
from powerforge_api.exceptions import (
    EquipmentNotFound,
    InvalidTopology,
    ModelConnectionNotFound,
    ModelNodeNotFound,
    ProjectNotFound,
    RevisionNotFound,
    TopologyObjectRemoved,
)
from powerforge_api.services.revision_writes import lock_writable_revision
from powerforge_api.services.topology_support import (
    set_lifecycle,
    soft_remove_incident_connections,
    topology_constraint_errors,
    validate_topology_consistency,
)
from powerforge_engineering_model import LifecycleStatus, ValueOrigin, VerificationState
from powerforge_engineering_model.errors import EngineeringModelError
from powerforge_engineering_model.terminal_profiles import terminal_profile
from powerforge_engineering_model.units import normalize_value
from powerforge_persistence import Project, ProjectRevision
from powerforge_persistence.engineering import Equipment
from powerforge_persistence.topology import ModelConnection, ModelNode
from powerforge_topology import ConnectionDirection, ConnectionKind, ModelNodeKind


class _Unset(Enum):
    VALUE = "unset"


UNSET = _Unset.VALUE


def _text(value: str | None, *, required: bool = False) -> str | None:
    if value is not None and not isinstance(value, str):
        raise InvalidTopology("Expected text or null")
    result = (value.strip() or None) if value is not None else None
    if required and result is None:
        raise InvalidTopology("Terminal key must not be blank")
    return result


def normalize_nominal_voltage(
    value: object, input_unit: str | None = None
) -> tuple[Decimal | None, str | None]:
    if value is None:
        if input_unit is not None:
            raise InvalidTopology("Voltage unit requires a value")
        return None, None
    try:
        voltage = Decimal(
            normalize_value(value, input_unit if input_unit is not None else "kV", "kV")
        )
    except EngineeringModelError as exc:
        raise InvalidTopology("Invalid connection voltage or voltage unit") from exc
    if voltage <= 0:
        raise InvalidTopology("Connection voltage must be greater than zero")
    return voltage, "kV"


def _enum(enum_type, value):
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        raise InvalidTopology(f"Invalid {enum_type.__name__}") from None


class TopologyService:
    """Own commit/rollback by default; commit=False joins the editor's outer transaction."""

    def __init__(self, session: Session, *, commit: bool = True) -> None:
        self.session = session
        self._commit = commit

    @contextmanager
    def _mutation(self, project_id: UUID, revision_id: UUID, operation: str) -> Iterator[None]:
        try:
            with integrity_guard(self.session, topology_constraint_errors(), operation=operation):
                revision = lock_writable_revision(self.session, project_id, revision_id)
                validate_topology_consistency(self.session, project_id, revision_id)
                yield
                self.session.flush()
                validate_topology_consistency(self.session, project_id, revision_id)
                revision.updated_at = datetime.now(UTC)
                self.session.flush()
                if self._commit:
                    self.session.commit()
        except BaseException:
            self.session.rollback()
            raise

    def _context(self, project_id: UUID, revision_id: UUID) -> None:
        if self.session.get(Project, project_id) is None:
            raise ProjectNotFound("Project not found")
        if (
            self.session.scalar(
                select(ProjectRevision.id).where(
                    ProjectRevision.id == revision_id, ProjectRevision.project_id == project_id
                )
            )
            is None
        ):
            raise RevisionNotFound("Revision not found in this project")

    def _row(self, model, project_id, revision_id, object_id):
        row = self.session.scalar(
            select(model)
            .where(
                model.project_id == project_id,
                model.revision_id == revision_id,
                model.id == object_id,
            )
            .execution_options(populate_existing=True)
        )
        if row is None:
            error = ModelNodeNotFound if model is ModelNode else ModelConnectionNotFound
            raise error("Topology object not found in this revision")
        return row

    def _active_equipment(
        self, project_id: UUID, revision_id: UUID, equipment_id: UUID
    ) -> Equipment:
        row = self.session.scalar(
            select(Equipment)
            .where(
                Equipment.project_id == project_id,
                Equipment.revision_id == revision_id,
                Equipment.id == equipment_id,
            )
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise EquipmentNotFound("Equipment not found in this revision")
        if row.lifecycle_status != LifecycleStatus.ACTIVE:
            raise InvalidTopology("Terminal requires active equipment")
        return row

    @staticmethod
    def _active(row: ModelNode | ModelConnection) -> None:
        if row.lifecycle_status != LifecycleStatus.ACTIVE:
            raise TopologyObjectRemoved("Restore topology before editing or connecting it")

    @staticmethod
    def _manual(row: ModelNode | ModelConnection, actor_id: UUID | None) -> None:
        row.origin = ValueOrigin.MANUAL
        row.verification_state = VerificationState.ENGINEER_REVIEWED
        row.updated_at, row.updated_by = datetime.now(UTC), actor_id
        if isinstance(row, ModelConnection):
            row.confidence = None

    def create_terminal(
        self,
        project_id: UUID,
        revision_id: UUID,
        equipment_id: UUID,
        terminal_key: str,
        *,
        label: str | None = None,
        actor_id: UUID | None = None,
    ) -> ModelNode:
        with self._mutation(project_id, revision_id, "create_terminal"):
            self._active_equipment(project_id, revision_id, equipment_id)
            node = ModelNode(
                project_id=project_id,
                revision_id=revision_id,
                kind=ModelNodeKind.EQUIPMENT_TERMINAL,
                equipment_id=equipment_id,
                terminal_key=_text(terminal_key, required=True),
                label=_text(label),
                created_by=actor_id,
                updated_by=actor_id,
            )
            self.session.add(node)
        return node

    def create_electrical_node(
        self,
        project_id: UUID,
        revision_id: UUID,
        *,
        label: str | None = None,
        actor_id: UUID | None = None,
    ) -> ModelNode:
        with self._mutation(project_id, revision_id, "create_electrical_node"):
            node = ModelNode(
                project_id=project_id,
                revision_id=revision_id,
                kind=ModelNodeKind.ELECTRICAL_NODE,
                label=_text(label),
                created_by=actor_id,
                updated_by=actor_id,
            )
            self.session.add(node)
        return node

    def get_node(self, project_id: UUID, revision_id: UUID, node_id: UUID) -> ModelNode:
        self._context(project_id, revision_id)
        node = self._row(ModelNode, project_id, revision_id, node_id)
        validate_topology_consistency(self.session, project_id, revision_id)
        return node

    def get_connection(
        self, project_id: UUID, revision_id: UUID, connection_id: UUID
    ) -> ModelConnection:
        self._context(project_id, revision_id)
        connection = self._row(ModelConnection, project_id, revision_id, connection_id)
        validate_topology_consistency(self.session, project_id, revision_id)
        return connection

    def _list(self, model, project_id, revision_id, lifecycle_status):
        self._context(project_id, revision_id)
        nodes, connections = validate_topology_consistency(self.session, project_id, revision_id)
        rows = nodes if model is ModelNode else connections
        if lifecycle_status is None:
            return rows
        status = _enum(LifecycleStatus, lifecycle_status)
        return [row for row in rows if row.lifecycle_status == status]

    def list_nodes(
        self,
        project_id: UUID,
        revision_id: UUID,
        *,
        lifecycle_status: LifecycleStatus | None = LifecycleStatus.ACTIVE,
    ) -> list[ModelNode]:
        return self._list(ModelNode, project_id, revision_id, lifecycle_status)

    def list_connections(
        self,
        project_id: UUID,
        revision_id: UUID,
        *,
        lifecycle_status: LifecycleStatus | None = LifecycleStatus.ACTIVE,
    ) -> list[ModelConnection]:
        return self._list(ModelConnection, project_id, revision_id, lifecycle_status)

    def update_node(
        self,
        project_id: UUID,
        revision_id: UUID,
        node_id: UUID,
        *,
        terminal_key: str | _Unset = UNSET,
        label: str | None | _Unset = UNSET,
        actor_id: UUID | None = None,
    ) -> ModelNode:
        with self._mutation(project_id, revision_id, "update_node"):
            node = self._row(ModelNode, project_id, revision_id, node_id)
            self._active(node)
            if terminal_key is not UNSET:
                if node.kind != ModelNodeKind.EQUIPMENT_TERMINAL:
                    raise InvalidTopology("Electrical nodes cannot acquire a terminal key")
                if node.managed_by_profile and terminal_key != node.terminal_key:
                    raise InvalidTopology("Profile-managed terminal keys cannot be changed")
                node.terminal_key = _text(terminal_key, required=True)
            if label is not UNSET:
                node.label = _text(label)
            self._manual(node, actor_id)
        return node

    def _endpoints(self, project_id, revision_id, from_id, to_id):
        if from_id == to_id:
            raise InvalidTopology("A connection cannot connect a node to itself")
        for node_id in (from_id, to_id):
            self._active(self._row(ModelNode, project_id, revision_id, node_id))

    def create_connection(
        self,
        project_id: UUID,
        revision_id: UUID,
        from_node_id: UUID,
        to_node_id: UUID,
        *,
        connection_kind: ConnectionKind | str = ConnectionKind.ELECTRICAL,
        direction: ConnectionDirection | str = ConnectionDirection.UNDIRECTED,
        phase_configuration: str | None = None,
        nominal_voltage: object = None,
        input_unit: str | None = None,
        actor_id: UUID | None = None,
    ) -> ModelConnection:
        with self._mutation(project_id, revision_id, "create_connection"):
            self._endpoints(project_id, revision_id, from_node_id, to_node_id)
            voltage, unit = normalize_nominal_voltage(nominal_voltage, input_unit)
            connection = ModelConnection(
                project_id=project_id,
                revision_id=revision_id,
                from_node_id=from_node_id,
                to_node_id=to_node_id,
                connection_kind=_enum(ConnectionKind, connection_kind),
                direction=_enum(ConnectionDirection, direction),
                phase_configuration=_text(phase_configuration),
                nominal_voltage=voltage,
                nominal_voltage_unit=unit,
                created_by=actor_id,
                updated_by=actor_id,
            )
            self.session.add(connection)
        return connection

    def update_connection(
        self,
        project_id: UUID,
        revision_id: UUID,
        connection_id: UUID,
        *,
        from_node_id: UUID | _Unset = UNSET,
        to_node_id: UUID | _Unset = UNSET,
        connection_kind: ConnectionKind | str | _Unset = UNSET,
        direction: ConnectionDirection | str | _Unset = UNSET,
        phase_configuration: str | None | _Unset = UNSET,
        nominal_voltage: object = UNSET,
        input_unit: str | None = None,
        actor_id: UUID | None = None,
    ) -> ModelConnection:
        with self._mutation(project_id, revision_id, "update_connection"):
            row = self._row(ModelConnection, project_id, revision_id, connection_id)
            self._active(row)
            source = row.from_node_id if from_node_id is UNSET else from_node_id
            target = row.to_node_id if to_node_id is UNSET else to_node_id
            self._endpoints(project_id, revision_id, source, target)
            row.from_node_id, row.to_node_id = source, target
            if connection_kind is not UNSET:
                row.connection_kind = _enum(ConnectionKind, connection_kind)
            if direction is not UNSET:
                row.direction = _enum(ConnectionDirection, direction)
            if phase_configuration is not UNSET:
                row.phase_configuration = _text(phase_configuration)
            if nominal_voltage is not UNSET:
                row.nominal_voltage, row.nominal_voltage_unit = normalize_nominal_voltage(
                    nominal_voltage, input_unit
                )
            elif input_unit is not None:
                raise InvalidTopology("Voltage unit requires a value")
            self._manual(row, actor_id)
        return row

    def _lifecycle(self, model, project_id, revision_id, object_id, status, actor_id):
        with self._mutation(project_id, revision_id, "set_topology_lifecycle"):
            row = self._row(model, project_id, revision_id, object_id)
            now = datetime.now(UTC)
            if status == LifecycleStatus.ACTIVE:
                if model is ModelNode and row.kind == ModelNodeKind.EQUIPMENT_TERMINAL:
                    equipment = self._active_equipment(project_id, revision_id, row.equipment_id)
                    if row.managed_by_profile and row.terminal_key not in terminal_profile(
                        equipment.equipment_type
                    ):
                        raise InvalidTopology(
                            "Obsolete profile terminal cannot be restored independently"
                        )
                elif model is ModelConnection:
                    self._endpoints(project_id, revision_id, row.from_node_id, row.to_node_id)
            elif model is ModelNode:
                if row.managed_by_profile:
                    equipment = self.session.get(Equipment, row.equipment_id)
                    if row.terminal_key in terminal_profile(equipment.equipment_type):
                        raise InvalidTopology(
                            "Required profile terminal cannot be removed independently"
                        )
                soft_remove_incident_connections(
                    self.session, project_id, revision_id, [row.id], actor_id, now
                )
            set_lifecycle(row, status, actor_id, now)
        return row

    def remove_node(
        self, project_id: UUID, revision_id: UUID, node_id: UUID, *, actor_id: UUID | None = None
    ) -> ModelNode:
        return self._lifecycle(
            ModelNode, project_id, revision_id, node_id, LifecycleStatus.REMOVED, actor_id
        )

    def restore_node(
        self, project_id: UUID, revision_id: UUID, node_id: UUID, *, actor_id: UUID | None = None
    ) -> ModelNode:
        return self._lifecycle(
            ModelNode, project_id, revision_id, node_id, LifecycleStatus.ACTIVE, actor_id
        )

    def remove_connection(
        self,
        project_id: UUID,
        revision_id: UUID,
        connection_id: UUID,
        *,
        actor_id: UUID | None = None,
    ) -> ModelConnection:
        return self._lifecycle(
            ModelConnection,
            project_id,
            revision_id,
            connection_id,
            LifecycleStatus.REMOVED,
            actor_id,
        )

    def restore_connection(
        self,
        project_id: UUID,
        revision_id: UUID,
        connection_id: UUID,
        *,
        actor_id: UUID | None = None,
    ) -> ModelConnection:
        return self._lifecycle(
            ModelConnection,
            project_id,
            revision_id,
            connection_id,
            LifecycleStatus.ACTIVE,
            actor_id,
        )
