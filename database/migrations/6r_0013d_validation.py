"""Bounded Phase 6R response validation diagnostics in the fenced call audit."""

from alembic import op

revision = "6r_0013d_validation"
down_revision = "6r_0013c_admission"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE extraction_ai_calls
        ADD COLUMN validation_diagnostics jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(validation_diagnostics) = 'array'
            AND jsonb_array_length(validation_diagnostics) <= 8
            AND octet_length(validation_diagnostics::text) <= 4096);
    """)


def downgrade() -> None:
    op.drop_column("extraction_ai_calls", "validation_diagnostics")
