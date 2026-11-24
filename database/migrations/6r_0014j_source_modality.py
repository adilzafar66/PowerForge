"""Permit bounded v2 attempt telemetry alongside historical v1 observations."""

from alembic import op

revision = "6r_0014j_source_modality"
down_revision = "6r_0014i_attribute_reasoning"


def upgrade():
    op.execute("""
        ALTER TABLE extraction_work_units DROP CONSTRAINT ck_extraction_attempt_performance,
        ADD CONSTRAINT ck_extraction_attempt_performance CHECK (performance IS NULL OR (
            stage = 'ATTRIBUTE_EXTRACTION' AND status IN ('COMPLETED','FAILED')
            AND started_at IS NOT NULL AND jsonb_typeof(performance) = 'object'
            AND (performance @> '{"version": 1}' OR performance @> '{"version": 2}')
            AND octet_length(performance::text) <= 4096))
    """)


def downgrade():
    raise RuntimeError("Source modality telemetry requires backup-based rollback")
