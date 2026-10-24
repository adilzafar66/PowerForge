"""Canonical manually authored topology, with no synthesized terminals or edges."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0009_topology_persistence"
down_revision = "0008_revision_model_metadata"
branch_labels = None
depends_on = None

ENUM_LABELS = {
    "model_node_kind": ("EQUIPMENT_TERMINAL", "ELECTRICAL_NODE"),
    "model_connection_kind": ("ELECTRICAL", "GROUNDING", "OTHER"),
    "model_connection_direction": ("UNDIRECTED", "NOMINAL_FROM_TO"),
}


def _enum(name):
    return pg.ENUM(name=name, create_type=False)


def _uuid(name, nullable=False):
    return sa.Column(name, pg.UUID(as_uuid=True), nullable=nullable)


def _common(table, inherited):
    return [
        sa.Column(
            "id",
            pg.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        _uuid("project_id"),
        _uuid("revision_id"),
        _uuid(inherited, True),
        sa.Column(
            "lifecycle_status",
            _enum("model_lifecycle_status"),
            nullable=False,
            server_default=sa.text("'ACTIVE'::model_lifecycle_status"),
        ),
        sa.Column(
            "origin",
            _enum("model_value_origin"),
            nullable=False,
            server_default=sa.text("'MANUAL'::model_value_origin"),
        ),
        sa.Column(
            "verification_state",
            _enum("model_verification_state"),
            nullable=False,
            server_default=sa.text("'ENGINEER_REVIEWED'::model_verification_state"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        _uuid("created_by", True),
        _uuid("updated_by", True),
        sa.Column("removed_at", sa.DateTime(timezone=True)),
        _uuid("removed_by", True),
        sa.UniqueConstraint("project_id", "id", name=f"uq_{table}_project_id_id"),
        sa.ForeignKeyConstraint(
            ["project_id", "revision_id"],
            ["project_revisions.project_id", "project_revisions.id"],
            name=f"fk_{table}_revision",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", inherited],
            [f"{table}.project_id", f"{table}.id"],
            name=f"fk_{table}_inherited_from",
        ),
        sa.CheckConstraint(
            f"{inherited} IS NULL OR {inherited} <> id", name=f"ck_{table}_inherited_not_self"
        ),
        sa.CheckConstraint(
            "(lifecycle_status = 'REMOVED' AND removed_at IS NOT NULL) OR "
            "(lifecycle_status = 'ACTIVE' AND removed_at IS NULL AND removed_by IS NULL)",
            name=f"ck_{table}_lifecycle",
        ),
    ]


def upgrade():
    for name, labels in ENUM_LABELS.items():
        pg.ENUM(*labels, name=name).create(op.get_bind(), checkfirst=False)
    op.create_table(
        "model_nodes",
        *_common("model_nodes", "inherited_from_node_id"),
        sa.Column("kind", _enum("model_node_kind"), nullable=False),
        _uuid("equipment_id", True),
        sa.Column("terminal_key", sa.Text()),
        sa.Column("label", sa.Text()),
        sa.UniqueConstraint("project_id", "revision_id", "id", name="uq_model_nodes_revision_id"),
        sa.UniqueConstraint("equipment_id", "terminal_key", name="uq_model_nodes_terminal"),
        sa.ForeignKeyConstraint(
            ["project_id", "revision_id", "equipment_id"],
            ["equipment.project_id", "equipment.revision_id", "equipment.id"],
            name="fk_model_nodes_equipment",
        ),
        sa.CheckConstraint(
            "(kind = 'EQUIPMENT_TERMINAL' AND equipment_id IS NOT NULL "
            "AND terminal_key IS NOT NULL AND length(btrim(terminal_key)) > 0) OR "
            "(kind = 'ELECTRICAL_NODE' AND equipment_id IS NULL AND terminal_key IS NULL)",
            name="ck_model_nodes_shape",
        ),
    )
    op.create_table(
        "model_connections",
        *_common("model_connections", "inherited_from_connection_id"),
        _uuid("from_node_id"),
        _uuid("to_node_id"),
        sa.Column(
            "connection_kind",
            _enum("model_connection_kind"),
            nullable=False,
            server_default=sa.text("'ELECTRICAL'::model_connection_kind"),
        ),
        sa.Column(
            "direction",
            _enum("model_connection_direction"),
            nullable=False,
            server_default=sa.text("'UNDIRECTED'::model_connection_direction"),
        ),
        sa.Column("phase_configuration", sa.Text()),
        sa.Column("nominal_voltage", sa.Numeric()),
        sa.Column("nominal_voltage_unit", sa.Text()),
        sa.Column("confidence", sa.Numeric()),
        sa.ForeignKeyConstraint(
            ["project_id", "revision_id", "from_node_id"],
            ["model_nodes.project_id", "model_nodes.revision_id", "model_nodes.id"],
            name="fk_model_connections_from_node",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "revision_id", "to_node_id"],
            ["model_nodes.project_id", "model_nodes.revision_id", "model_nodes.id"],
            name="fk_model_connections_to_node",
        ),
        sa.CheckConstraint("from_node_id <> to_node_id", name="ck_model_connections_not_self_loop"),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1 AND "
            "confidence NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric))",
            name="ck_model_connections_confidence",
        ),
        sa.CheckConstraint(
            "(nominal_voltage IS NULL AND nominal_voltage_unit IS NULL) OR "
            "(nominal_voltage IS NOT NULL AND nominal_voltage_unit IS NOT NULL "
            "AND nominal_voltage_unit = 'kV' AND nominal_voltage > 0 AND "
            "nominal_voltage NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric))",
            name="ck_model_connections_voltage",
        ),
    )
    for table, inherited, references in [
        ("model_nodes", "inherited_from_node_id", ["equipment_id"]),
        ("model_connections", "inherited_from_connection_id", ["from_node_id", "to_node_id"]),
    ]:
        op.create_index(
            f"ix_{table}_revision_lifecycle",
            table,
            ["project_id", "revision_id", "lifecycle_status"],
        )
        op.create_index(f"ix_{table}_inherited_from", table, [inherited])
        for column in references:
            op.create_index(f"ix_{table}_{column.removesuffix('_id')}", table, [column])


def downgrade():
    op.drop_table("model_connections")
    op.drop_table("model_nodes")
    for name in reversed(ENUM_LABELS):
        pg.ENUM(name=name).drop(op.get_bind(), checkfirst=False)
