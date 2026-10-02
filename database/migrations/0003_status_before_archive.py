"""Store the project status to restore on unarchive.

Revision ID: 0003_status_before_archive
Revises: 0002_projects_and_revisions
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_status_before_archive"
down_revision: str | None = "0002_projects_and_revisions"
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


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("status_before_archive", project_status, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("projects", "status_before_archive")
