"""Create projects and project_revisions tables.

Revision ID: 0002_projects_and_revisions
Revises: 0001_enable_extensions
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_projects_and_revisions"
down_revision: str | None = "0001_enable_extensions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

project_status = postgresql.ENUM(
    "ACTIVE",
    "PAUSED",
    "CANCELLED",
    "ARCHIVED",
    name="project_status",
    create_type=False,
)
revision_status = postgresql.ENUM(
    "DRAFT",
    "ACTIVE",
    "SUPERSEDED",
    name="revision_status",
    create_type=False,
)


def upgrade() -> None:
    op.execute(
        "CREATE TYPE project_status AS ENUM ('ACTIVE', 'PAUSED', 'CANCELLED', 'ARCHIVED')"
    )
    op.execute("CREATE TYPE revision_status AS ENUM ('DRAFT', 'ACTIVE', 'SUPERSEDED')")

    op.create_table(
        "projects",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("project_number", sa.Text(), nullable=False),
        sa.Column("project_name", sa.Text(), nullable=False),
        sa.Column("project_address", sa.Text(), nullable=True),
        sa.Column("project_scope", sa.Text(), nullable=True),
        sa.Column("client_name", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "engineer_names",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "status",
            project_status,
            nullable=False,
            server_default=sa.text("'ACTIVE'::project_status"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint("project_number", name="uq_projects_project_number"),
    )
    op.create_index("ix_projects_status", "projects", ["status"])
    op.create_index("ix_projects_updated_at", "projects", ["updated_at"])

    op.create_table(
        "project_revisions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", name="fk_project_revisions_project_id"),
            nullable=False,
        ),
        sa.Column("identifier", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            revision_status,
            nullable=False,
            server_default=sa.text("'DRAFT'::revision_status"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint(
            "project_id",
            "identifier",
            name="uq_project_revisions_project_id_identifier",
        ),
    )
    op.create_index("ix_project_revisions_project_id", "project_revisions", ["project_id"])
    op.create_index(
        "uq_project_revisions_one_active",
        "project_revisions",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )


def downgrade() -> None:
    op.drop_index("uq_project_revisions_one_active", table_name="project_revisions")
    op.drop_index("ix_project_revisions_project_id", table_name="project_revisions")
    op.drop_table("project_revisions")
    op.drop_index("ix_projects_updated_at", table_name="projects")
    op.drop_index("ix_projects_status", table_name="projects")
    op.drop_table("projects")
    op.execute("DROP TYPE revision_status")
    op.execute("DROP TYPE project_status")
