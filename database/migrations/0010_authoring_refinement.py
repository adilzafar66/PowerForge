"""Canonical empty state and profile-managed equipment terminals.

Frozen migration data; never import the evolving runtime registry/profiles.
Downgrade retains all terminals/connections, and cannot recover UNKNOWN vs MISSING.
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_authoring_refinement"
down_revision = "0009_topology_persistence"
branch_labels = None
depends_on = None

PROFILES = {
    "UTILITY_SOURCE": ("OUTPUT",),
    "SYNCHRONOUS_GENERATOR": ("OUTPUT",),
    "TWO_WINDING_TRANSFORMER": ("PRIMARY", "SECONDARY"),
    "BUS": ("BUS",),
    "LV_BREAKER": ("INPUT", "OUTPUT"),
    "HV_BREAKER": ("INPUT", "OUTPUT"),
    "RECLOSER": ("INPUT", "OUTPUT"),
    "OVERCURRENT_RELAY": (),
    "FUSE": ("INPUT", "OUTPUT"),
    "SINGLE_THROW_SWITCH": ("INPUT", "OUTPUT"),
    "DOUBLE_THROW_SWITCH": ("SOURCE_1", "SOURCE_2", "COMMON"),
    "CABLE": ("END_A", "END_B"),
    "CT": ("INPUT", "OUTPUT"),
    "INDUCTION_MOTOR": ("INPUT",),
    "STATIC_LOAD": ("INPUT",),
    "LUMPED_LOAD": ("INPUT",),
    "CAPACITOR": ("INPUT",),
    "REACTOR": ("INPUT", "OUTPUT"),
    "VFD": ("INPUT", "OUTPUT"),
    "UPS": ("INPUT", "OUTPUT"),
}
TYPED_CHECK = """(information_state <> 'PRESENT'
                AND num_nonnulls(numeric_value, integer_value, text_value, boolean_value) = 0)
            OR (information_state = 'PRESENT'
                AND num_nonnulls(numeric_value, integer_value, text_value, boolean_value) = 1
                AND ((value_type = 'NUMBER' AND numeric_value IS NOT NULL)
                  OR (value_type = 'INTEGER' AND integer_value IS NOT NULL)
                  OR (value_type IN ('TEXT', 'ENUM') AND text_value IS NOT NULL)
                  OR (value_type = 'BOOLEAN' AND boolean_value IS NOT NULL)))"""


def _replace_state(labels, expression, default):
    op.drop_constraint("ck_equipment_attributes_typed_value", "equipment_attributes")
    op.execute("ALTER TABLE equipment_attributes ALTER COLUMN information_state DROP DEFAULT")
    op.execute("ALTER TYPE model_information_state RENAME TO model_information_state_old")
    op.execute(
        "CREATE TYPE model_information_state AS ENUM ("
        + ",".join("'" + s + "'" for s in labels)
        + ")"
    )
    op.execute(
        "ALTER TABLE equipment_attributes ALTER COLUMN information_state TYPE "
        "model_information_state USING (" + expression + ")::model_information_state"
    )
    op.execute("DROP TYPE model_information_state_old")
    op.execute(
        "ALTER TABLE equipment_attributes ALTER COLUMN information_state SET DEFAULT '"
        + default
        + "'::model_information_state"
    )
    op.create_check_constraint(
        "ck_equipment_attributes_typed_value", "equipment_attributes", TYPED_CHECK
    )


def upgrade():
    _replace_state(
        ("PRESENT", "MISSING", "NOT_APPLICABLE", "NOT_POPULATED", "CONFLICTING"),
        "CASE information_state::text WHEN 'NOT_EXTRACTED' THEN 'NOT_POPULATED' WHEN 'UNKNOWN' "
        "THEN 'MISSING' ELSE information_state::text END",
        "NOT_POPULATED",
    )
    op.add_column(
        "model_nodes",
        sa.Column("managed_by_profile", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_check_constraint(
        "ck_model_nodes_profile",
        "model_nodes",
        "NOT managed_by_profile OR kind = 'EQUIPMENT_TERMINAL'",
    )
    connection = op.get_bind()
    for equipment_type, keys in PROFILES.items():
        for key in keys:
            params = {"type": equipment_type, "key": key}
            # Adopt matching nodes without changing IDs, metadata, or connection endpoints.
            # Required terminals on active owners become active, without restoring edges.
            connection.execute(
                sa.text("""
                UPDATE model_nodes n SET managed_by_profile = true,
                    lifecycle_status = e.lifecycle_status,
                    removed_at = CASE WHEN e.lifecycle_status = 'REMOVED'
                        THEN COALESCE(n.removed_at, e.removed_at) ELSE NULL END,
                    removed_by = CASE WHEN e.lifecycle_status = 'REMOVED'
                        THEN n.removed_by ELSE NULL END
                FROM equipment e WHERE n.equipment_id = e.id
                AND e.equipment_type = :type AND n.terminal_key = :key
            """),
                params,
            )
            connection.execute(
                sa.text("""
                INSERT INTO model_nodes (project_id, revision_id, equipment_id, kind, terminal_key,
                    managed_by_profile, lifecycle_status, removed_at, removed_by)
                SELECT e.project_id, e.revision_id, e.id, 'EQUIPMENT_TERMINAL', :key,
                    true, e.lifecycle_status, e.removed_at, e.removed_by
                FROM equipment e WHERE e.equipment_type = :type
                AND NOT EXISTS (SELECT 1 FROM model_nodes n
                    WHERE n.equipment_id = e.id AND n.terminal_key = :key)
            """),
                params,
            )


def downgrade():
    op.drop_constraint("ck_model_nodes_profile", "model_nodes")
    op.drop_column("model_nodes", "managed_by_profile")
    _replace_state(
        ("PRESENT", "UNKNOWN", "MISSING", "NOT_APPLICABLE", "NOT_EXTRACTED", "CONFLICTING"),
        "CASE information_state::text WHEN 'NOT_POPULATED' THEN 'NOT_EXTRACTED' ELSE "
        "information_state::text END",
        "NOT_EXTRACTED",
    )
