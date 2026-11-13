"""Persist expiring extraction previews before admitting live execution."""

from alembic import op

revision = "6r_0013c_admission"
down_revision = "6r_0013_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE extraction_stage_results
          ADD COLUMN diagnostics jsonb NOT NULL DEFAULT '[]'::jsonb
          CHECK (jsonb_typeof(diagnostics) = 'array' AND jsonb_array_length(diagnostics) <= 128
                 AND octet_length(diagnostics::text) <= 32768);
        CREATE TABLE extraction_operation_previews (
            id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{64}$'),
            revision_id uuid NOT NULL REFERENCES project_revisions (id),
            plan_hash text NOT NULL CHECK (plan_hash ~ '^[0-9a-f]{64}$'),
            expires_at timestamptz NOT NULL
        );
        CREATE INDEX ix_extraction_previews_expiry
            ON extraction_operation_previews (revision_id, expires_at);
    """)


def downgrade() -> None:
    op.drop_table("extraction_operation_previews")
    op.drop_column("extraction_stage_results", "diagnostics")
