"""Revision lineage, documents, and revision_documents.

Revision ID: 0004_documents_and_lineage
Revises: 0003_status_before_archive

Downgrade drops the documents and revision_documents tables and the lineage
column, so it destroys any Phase 2 data. Phase 1 projects and revisions are kept.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_documents_and_lineage"
down_revision: str | None = "0003_status_before_archive"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Labels are a frozen snapshot, not imported from the live enum. Order is permanent.
DOCUMENT_CLASSIFICATION_LABELS = (
    "SINGLE_LINE_DIAGRAM",
    "ELECTRICAL_DRAWING",
    "PANEL_SCHEDULE",
    "EQUIPMENT_SCHEDULE",
    "CABLE_SCHEDULE",
    "TRANSFORMER_SHOP_DRAWING",
    "SWITCHGEAR_SHOP_DRAWING",
    "BREAKER_DOCUMENT",
    "MOTOR_DATA",
    "FAULT_DATA",
    "SPECIFICATION",
    "EQUIPMENT_PHOTO",
    "NAMEPLATE_PHOTO",
    "STUDY_DOCUMENT",
    "OTHER",
    "UNKNOWN",
)

document_classification = postgresql.ENUM(
    *DOCUMENT_CLASSIFICATION_LABELS,
    name="document_classification",
    create_type=False,
)
document_origin = postgresql.ENUM(
    "UPLOADED",
    "INHERITED",
    name="document_origin",
    create_type=False,
)
revision_document_status = postgresql.ENUM(
    "INCLUDED",
    "REMOVED",
    name="revision_document_status",
    create_type=False,
)


def _labels_sql(labels: Sequence[str]) -> str:
    return ", ".join(f"'{label}'" for label in labels)


def upgrade() -> None:
    op.execute(
        "CREATE TYPE document_classification AS ENUM "
        f"({_labels_sql(DOCUMENT_CLASSIFICATION_LABELS)})"
    )
    op.execute("CREATE TYPE document_origin AS ENUM ('UPLOADED', 'INHERITED')")
    op.execute("CREATE TYPE revision_document_status AS ENUM ('INCLUDED', 'REMOVED')")

    op.add_column(
        "project_revisions",
        sa.Column("based_on_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_project_revisions_project_id_id",
        "project_revisions",
        ["project_id", "id"],
    )
    op.create_foreign_key(
        "fk_project_revisions_based_on",
        "project_revisions",
        "project_revisions",
        ["project_id", "based_on_revision_id"],
        ["project_id", "id"],
    )
    op.create_check_constraint(
        "ck_project_revisions_based_on_not_self",
        "project_revisions",
        "based_on_revision_id IS NULL OR based_on_revision_id <> id",
    )

    op.create_table(
        "documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", name="fk_documents_project_id"),
            nullable=False,
        ),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("file_extension", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint("storage_key", name="uq_documents_storage_key"),
        sa.UniqueConstraint("project_id", "id", name="uq_documents_project_id_id"),
        sa.CheckConstraint("size_bytes > 0", name="ck_documents_size_positive"),
    )
    op.create_index("ix_documents_project_id", "documents", ["project_id"])
    op.create_index("ix_documents_project_id_sha256", "documents", ["project_id", "sha256"])

    op.create_table(
        "revision_documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("origin", document_origin, nullable=False),
        sa.Column("inherited_from_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            revision_document_status,
            nullable=False,
            server_default=sa.text("'INCLUDED'::revision_document_status"),
        ),
        sa.Column(
            "document_type",
            document_classification,
            nullable=False,
            server_default=sa.text("'UNKNOWN'::document_classification"),
        ),
        sa.Column("document_number", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("added_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint(
            "revision_id",
            "document_id",
            name="uq_revision_documents_revision_id_document_id",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "revision_id"],
            ["project_revisions.project_id", "project_revisions.id"],
            name="fk_revision_documents_revision",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "document_id"],
            ["documents.project_id", "documents.id"],
            name="fk_revision_documents_document",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "inherited_from_revision_id"],
            ["project_revisions.project_id", "project_revisions.id"],
            name="fk_revision_documents_inherited_from",
        ),
        sa.CheckConstraint(
            "(origin = 'INHERITED') = (inherited_from_revision_id IS NOT NULL)",
            name="ck_revision_documents_origin_inherited_from",
        ),
        sa.CheckConstraint(
            "(status = 'REMOVED') = (removed_at IS NOT NULL)",
            name="ck_revision_documents_status_removed_at",
        ),
        sa.CheckConstraint(
            "inherited_from_revision_id IS NULL OR inherited_from_revision_id <> revision_id",
            name="ck_revision_documents_inherited_not_self",
        ),
    )
    op.create_index("ix_revision_documents_revision_id", "revision_documents", ["revision_id"])
    op.create_index("ix_revision_documents_document_id", "revision_documents", ["document_id"])
    op.create_index(
        "ix_revision_documents_revision_id_status",
        "revision_documents",
        ["revision_id", "status"],
    )
    op.create_index(
        "ix_revision_documents_revision_id_document_type",
        "revision_documents",
        ["revision_id", "document_type"],
    )


def downgrade() -> None:
    op.drop_table("revision_documents")
    op.drop_table("documents")

    op.drop_constraint("ck_project_revisions_based_on_not_self", "project_revisions", type_="check")
    op.drop_constraint("fk_project_revisions_based_on", "project_revisions", type_="foreignkey")
    op.drop_constraint("uq_project_revisions_project_id_id", "project_revisions", type_="unique")
    op.drop_column("project_revisions", "based_on_revision_id")

    op.execute("DROP TYPE revision_document_status")
    op.execute("DROP TYPE document_origin")
    op.execute("DROP TYPE document_classification")
