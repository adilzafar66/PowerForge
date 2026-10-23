"""Core canonical equipment, lineage, and typed attributes (Phase 5B only).

Revision ID: 0007_engineering_model_core
Revises: 0006_document_classification

Frozen schema vocabulary, independent of the runtime registry. No equipment is
synthesized from documents. Inheritance columns are reserved for Phase 5C.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_engineering_model_core"
down_revision: str | None = "0006_document_classification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUM_LABELS = {
    "model_lifecycle_status": ("ACTIVE", "REMOVED"),
    "model_value_origin": ("MANUAL", "AI_EXTRACTION", "INFERRED", "IMPORTED"),
    "model_information_state": (
        "PRESENT",
        "UNKNOWN",
        "MISSING",
        "NOT_APPLICABLE",
        "NOT_EXTRACTED",
        "CONFLICTING",
    ),
    "model_verification_state": (
        "UNVERIFIED",
        "AI_EXTRACTED",
        "SYSTEM_VALIDATED",
        "ENGINEER_REVIEWED",
        "ENGINEER_VERIFIED",
    ),
    "model_attribute_value_type": ("NUMBER", "INTEGER", "TEXT", "BOOLEAN", "ENUM"),
}
ENUMS = {
    name: postgresql.ENUM(*labels, name=name, create_type=False)
    for name, labels in ENUM_LABELS.items()
}


def _id() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def _uuid(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _audit(*, updated: bool = True) -> list[sa.Column]:
    columns = [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        _uuid("created_by", nullable=True),
    ]
    if updated:
        columns += [
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            _uuid("updated_by", nullable=True),
        ]
    return columns


def upgrade() -> None:
    for enum in ENUMS.values():
        enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "equipment_lineages",
        _id(),
        _uuid("project_id"),
        *_audit(updated=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_equipment_lineages_project_id"
        ),
        sa.UniqueConstraint("project_id", "id", name="uq_equipment_lineages_project_id_id"),
    )
    op.create_index("ix_equipment_lineages_project_id", "equipment_lineages", ["project_id"])
    op.create_table(
        "equipment",
        _id(),
        _uuid("project_id"),
        _uuid("revision_id"),
        _uuid("lineage_id"),
        sa.Column("equipment_type", sa.Text, nullable=False),
        sa.Column("tag", sa.Text),
        sa.Column("name", sa.Text),
        sa.Column("description", sa.Text),
        sa.Column(
            "lifecycle_status",
            ENUMS["model_lifecycle_status"],
            nullable=False,
            server_default=sa.text("'ACTIVE'::model_lifecycle_status"),
        ),
        sa.Column(
            "origin",
            ENUMS["model_value_origin"],
            nullable=False,
            server_default=sa.text("'MANUAL'::model_value_origin"),
        ),
        sa.Column(
            "verification_state",
            ENUMS["model_verification_state"],
            nullable=False,
            server_default=sa.text("'ENGINEER_REVIEWED'::model_verification_state"),
        ),
        _uuid("inherited_from_equipment_id", nullable=True),
        *_audit(),
        sa.Column("removed_at", sa.DateTime(timezone=True)),
        _uuid("removed_by", nullable=True),
        sa.UniqueConstraint("revision_id", "lineage_id", name="uq_equipment_revision_lineage"),
        sa.UniqueConstraint("project_id", "id", name="uq_equipment_project_id_id"),
        sa.UniqueConstraint(
            "project_id", "revision_id", "id", name="uq_equipment_project_revision_id"
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "revision_id"],
            ["project_revisions.project_id", "project_revisions.id"],
            name="fk_equipment_revision",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "lineage_id"],
            ["equipment_lineages.project_id", "equipment_lineages.id"],
            name="fk_equipment_lineage",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "inherited_from_equipment_id"],
            ["equipment.project_id", "equipment.id"],
            name="fk_equipment_inherited_from",
        ),
        sa.CheckConstraint(
            "inherited_from_equipment_id IS NULL OR inherited_from_equipment_id <> id",
            name="ck_equipment_inherited_not_self",
        ),
        sa.CheckConstraint(
            "(lifecycle_status = 'REMOVED' AND removed_at IS NOT NULL) OR "
            "(lifecycle_status = 'ACTIVE' AND removed_at IS NULL AND removed_by IS NULL)",
            name="ck_equipment_lifecycle_removed_at",
        ),
    )
    for name, columns in {
        "ix_equipment_revision_lifecycle": ["revision_id", "lifecycle_status"],
        "ix_equipment_project_id": ["project_id"],
        "ix_equipment_lineage_id": ["lineage_id"],
        "ix_equipment_revision_tag": ["revision_id", "tag"],
        "ix_equipment_inherited_from": ["inherited_from_equipment_id"],
    }.items():
        op.create_index(name, "equipment", columns)
    op.create_table(
        "equipment_attributes",
        _id(),
        _uuid("project_id"),
        _uuid("revision_id"),
        _uuid("equipment_id"),
        sa.Column("attribute_key", sa.Text, nullable=False),
        sa.Column("value_type", ENUMS["model_attribute_value_type"], nullable=False),
        sa.Column("numeric_value", sa.Numeric),
        sa.Column("integer_value", sa.BigInteger),
        sa.Column("text_value", sa.Text),
        sa.Column("boolean_value", sa.Boolean),
        sa.Column("unit", sa.Text),
        sa.Column(
            "information_state",
            ENUMS["model_information_state"],
            nullable=False,
            server_default=sa.text("'NOT_EXTRACTED'::model_information_state"),
        ),
        sa.Column(
            "verification_state",
            ENUMS["model_verification_state"],
            nullable=False,
            server_default=sa.text("'UNVERIFIED'::model_verification_state"),
        ),
        sa.Column("origin", ENUMS["model_value_origin"]),
        sa.Column("confidence", sa.Numeric),
        _uuid("inherited_from_attribute_id", nullable=True),
        *_audit(),
        sa.UniqueConstraint("equipment_id", "attribute_key", name="uq_equipment_attributes_key"),
        sa.UniqueConstraint("project_id", "id", name="uq_equipment_attributes_project_id_id"),
        sa.ForeignKeyConstraint(
            ["project_id", "revision_id", "equipment_id"],
            ["equipment.project_id", "equipment.revision_id", "equipment.id"],
            name="fk_equipment_attributes_equipment",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "inherited_from_attribute_id"],
            ["equipment_attributes.project_id", "equipment_attributes.id"],
            name="fk_equipment_attributes_inherited_from",
        ),
        sa.CheckConstraint(
            "inherited_from_attribute_id IS NULL OR inherited_from_attribute_id <> id",
            name="ck_equipment_attributes_inherited_not_self",
        ),
        sa.CheckConstraint(
            """
            (information_state <> 'PRESENT'
                AND num_nonnulls(numeric_value, integer_value, text_value, boolean_value) = 0)
            OR (information_state = 'PRESENT'
                AND num_nonnulls(numeric_value, integer_value, text_value, boolean_value) = 1
                AND ((value_type = 'NUMBER' AND numeric_value IS NOT NULL)
                  OR (value_type = 'INTEGER' AND integer_value IS NOT NULL)
                  OR (value_type IN ('TEXT', 'ENUM') AND text_value IS NOT NULL)
                  OR (value_type = 'BOOLEAN' AND boolean_value IS NOT NULL)))
            """,
            name="ck_equipment_attributes_typed_value",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_equipment_attributes_confidence",
        ),
        sa.CheckConstraint(
            "numeric_value IS NULL OR numeric_value NOT IN "
            "('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)",
            name="ck_equipment_attributes_finite_numeric",
        ),
    )
    op.create_index(
        "ix_equipment_attributes_project_revision",
        "equipment_attributes",
        ["project_id", "revision_id"],
    )
    op.create_index(
        "ix_equipment_attributes_inherited_from",
        "equipment_attributes",
        ["inherited_from_attribute_id"],
    )


def downgrade() -> None:
    op.drop_table("equipment_attributes")
    op.drop_table("equipment")
    op.drop_table("equipment_lineages")
    for enum in reversed(tuple(ENUMS.values())):
        enum.drop(op.get_bind(), checkfirst=True)
