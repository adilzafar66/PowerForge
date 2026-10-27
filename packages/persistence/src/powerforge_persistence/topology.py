"""Canonical revision topology; endpoints are nodes, never equipment edges."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column

from powerforge_engineering_model import LifecycleStatus, ValueOrigin, VerificationState
from powerforge_persistence.base import Base
from powerforge_persistence.engineering import (
    lifecycle_status_enum,
    value_origin_enum,
    verification_state_enum,
)
from powerforge_topology import ConnectionDirection, ConnectionKind, ModelNodeKind

node_kind_enum = ENUM(
    ModelNodeKind,
    name="model_node_kind",
    create_type=False,
    values_callable=lambda enum: [member.value for member in enum],
)
connection_kind_enum = ENUM(
    ConnectionKind,
    name="model_connection_kind",
    create_type=False,
    values_callable=lambda enum: [member.value for member in enum],
)
connection_direction_enum = ENUM(
    ConnectionDirection,
    name="model_connection_direction",
    create_type=False,
    values_callable=lambda enum: [member.value for member in enum],
)


class _TopologySnapshot:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    lifecycle_status: Mapped[LifecycleStatus] = mapped_column(
        lifecycle_status_enum, server_default=text("'ACTIVE'::model_lifecycle_status")
    )
    origin: Mapped[ValueOrigin] = mapped_column(
        value_origin_enum, server_default=text("'MANUAL'::model_value_origin")
    )
    verification_state: Mapped[VerificationState] = mapped_column(
        verification_state_enum,
        server_default=text("'ENGINEER_REVIEWED'::model_verification_state"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class ModelNode(_TopologySnapshot, Base):
    __tablename__ = "model_nodes"
    __table_args__ = (
        UniqueConstraint("project_id", "id", name="uq_model_nodes_project_id_id"),
        UniqueConstraint("project_id", "revision_id", "id", name="uq_model_nodes_revision_id"),
        UniqueConstraint("equipment_id", "terminal_key", name="uq_model_nodes_terminal"),
        ForeignKeyConstraint(
            ["project_id", "revision_id"],
            ["project_revisions.project_id", "project_revisions.id"],
            name="fk_model_nodes_revision",
        ),
        ForeignKeyConstraint(
            ["project_id", "revision_id", "equipment_id"],
            ["equipment.project_id", "equipment.revision_id", "equipment.id"],
            name="fk_model_nodes_equipment",
        ),
        ForeignKeyConstraint(
            ["project_id", "inherited_from_node_id"],
            ["model_nodes.project_id", "model_nodes.id"],
            name="fk_model_nodes_inherited_from",
        ),
        CheckConstraint(
            "(kind = 'EQUIPMENT_TERMINAL' AND equipment_id IS NOT NULL "
            "AND terminal_key IS NOT NULL AND length(btrim(terminal_key)) > 0) OR "
            "(kind = 'ELECTRICAL_NODE' AND equipment_id IS NULL AND terminal_key IS NULL)",
            name="ck_model_nodes_shape",
        ),
        CheckConstraint(
            "NOT managed_by_profile OR kind = 'EQUIPMENT_TERMINAL'", name="ck_model_nodes_profile"
        ),
        CheckConstraint(
            "inherited_from_node_id IS NULL OR inherited_from_node_id <> id",
            name="ck_model_nodes_inherited_not_self",
        ),
        CheckConstraint(
            "(lifecycle_status = 'REMOVED' AND removed_at IS NOT NULL) OR "
            "(lifecycle_status = 'ACTIVE' AND removed_at IS NULL AND removed_by IS NULL)",
            name="ck_model_nodes_lifecycle",
        ),
        Index("ix_model_nodes_revision_lifecycle", "project_id", "revision_id", "lifecycle_status"),
        Index("ix_model_nodes_equipment", "equipment_id"),
        Index("ix_model_nodes_inherited_from", "inherited_from_node_id"),
    )
    managed_by_profile: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    kind: Mapped[ModelNodeKind] = mapped_column(node_kind_enum)
    equipment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    terminal_key: Mapped[str | None] = mapped_column(Text)
    label: Mapped[str | None] = mapped_column(Text)
    inherited_from_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class ModelConnection(_TopologySnapshot, Base):
    __tablename__ = "model_connections"
    __table_args__ = (
        UniqueConstraint("project_id", "id", name="uq_model_connections_project_id_id"),
        ForeignKeyConstraint(
            ["project_id", "revision_id"],
            ["project_revisions.project_id", "project_revisions.id"],
            name="fk_model_connections_revision",
        ),
        ForeignKeyConstraint(
            ["project_id", "revision_id", "from_node_id"],
            ["model_nodes.project_id", "model_nodes.revision_id", "model_nodes.id"],
            name="fk_model_connections_from_node",
        ),
        ForeignKeyConstraint(
            ["project_id", "revision_id", "to_node_id"],
            ["model_nodes.project_id", "model_nodes.revision_id", "model_nodes.id"],
            name="fk_model_connections_to_node",
        ),
        ForeignKeyConstraint(
            ["project_id", "inherited_from_connection_id"],
            ["model_connections.project_id", "model_connections.id"],
            name="fk_model_connections_inherited_from",
        ),
        CheckConstraint("from_node_id <> to_node_id", name="ck_model_connections_not_self_loop"),
        CheckConstraint(
            "inherited_from_connection_id IS NULL OR inherited_from_connection_id <> id",
            name="ck_model_connections_inherited_not_self",
        ),
        CheckConstraint(
            "(lifecycle_status = 'REMOVED' AND removed_at IS NOT NULL) OR "
            "(lifecycle_status = 'ACTIVE' AND removed_at IS NULL AND removed_by IS NULL)",
            name="ck_model_connections_lifecycle",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1 AND "
            "confidence NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric))",
            name="ck_model_connections_confidence",
        ),
        CheckConstraint(
            "(nominal_voltage IS NULL AND nominal_voltage_unit IS NULL) OR "
            "(nominal_voltage IS NOT NULL AND nominal_voltage_unit IS NOT NULL "
            "AND nominal_voltage_unit = 'kV' AND nominal_voltage > 0 AND "
            "nominal_voltage NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric))",
            name="ck_model_connections_voltage",
        ),
        Index(
            "ix_model_connections_revision_lifecycle",
            "project_id",
            "revision_id",
            "lifecycle_status",
        ),
        Index("ix_model_connections_from_node", "from_node_id"),
        Index("ix_model_connections_to_node", "to_node_id"),
        Index("ix_model_connections_inherited_from", "inherited_from_connection_id"),
    )
    from_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    to_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    connection_kind: Mapped[ConnectionKind] = mapped_column(
        connection_kind_enum, server_default=text("'ELECTRICAL'::model_connection_kind")
    )
    direction: Mapped[ConnectionDirection] = mapped_column(
        connection_direction_enum, server_default=text("'UNDIRECTED'::model_connection_direction")
    )
    phase_configuration: Mapped[str | None] = mapped_column(Text)
    nominal_voltage: Mapped[Decimal | None] = mapped_column(Numeric)
    nominal_voltage_unit: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric)
    inherited_from_connection_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
