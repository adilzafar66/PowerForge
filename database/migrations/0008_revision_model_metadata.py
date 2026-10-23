"""Revision-level engineering-model metadata (Phase 5C only).

Revision ID: 0008_revision_model_metadata
Revises: 0007_engineering_model_core
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_revision_model_metadata"
down_revision: str | None = "0007_engineering_model_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("project_revisions", sa.Column("system_frequency", sa.Numeric(), nullable=True))
    op.add_column("project_revisions", sa.Column("system_phase_count", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_project_revisions_system_frequency_positive",
        "project_revisions",
        "system_frequency IS NULL OR "
        "(system_frequency > 0 AND system_frequency NOT IN "
        "('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric))",
    )
    op.create_check_constraint(
        "ck_project_revisions_system_phase_count",
        "project_revisions",
        "system_phase_count IS NULL OR system_phase_count IN (1, 3)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_project_revisions_system_phase_count", "project_revisions", type_="check"
    )
    op.drop_constraint(
        "ck_project_revisions_system_frequency_positive",
        "project_revisions",
        type_="check",
    )
    op.drop_column("project_revisions", "system_phase_count")
    op.drop_column("project_revisions", "system_frequency")
