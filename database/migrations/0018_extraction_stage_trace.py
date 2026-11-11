"""Add append-only, bounded diagnostic records for enriched extraction attempts."""

from alembic import op

revision = "0018_extraction_stage_trace"
down_revision = "0017_extraction_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE extraction_stage_traces (
            work_unit_id uuid PRIMARY KEY REFERENCES extraction_work_units(id),
            trace jsonb NOT NULL,
            CONSTRAINT ck_extraction_stage_trace_v1 CHECK (
                jsonb_typeof(trace) = 'object'
                AND coalesce(trace->>'version', '') = 'extraction-stage-trace-v1'
                AND octet_length(trace::text) <= 8192
            )
        );
        CREATE TRIGGER extraction_stage_trace_guard
        BEFORE INSERT OR UPDATE OR DELETE ON extraction_stage_traces
        FOR EACH ROW EXECUTE FUNCTION extraction_output_guard();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM extraction_stage_traces) THEN
                RAISE EXCEPTION 'Cannot downgrade with persisted extraction stage traces';
            END IF;
        END $$;
        DROP TABLE extraction_stage_traces;
        """
    )
