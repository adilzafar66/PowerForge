"""Reject terminal extraction runs with active work-unit attempts.

Keep 0011 stable and upgrade already-migrated databases without changing history.
"""

from alembic import op

revision = "0012_extraction_terminal_guard"
down_revision = "0011_extraction_persistence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION extraction_terminal_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.status IN ('COMPLETED', 'PARTIALLY_COMPLETED', 'FAILED', 'CANCELLED')
             AND EXISTS (
               SELECT 1 FROM extraction_work_units
               WHERE run_id = NEW.id AND status IN ('PENDING', 'RUNNING')
             ) THEN
            RAISE EXCEPTION 'Terminal extraction runs cannot have active work units'
              USING ERRCODE = '23514', CONSTRAINT = 'ck_extraction_runs_no_active_units';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER extraction_terminal_guard
        BEFORE INSERT OR UPDATE ON extraction_runs
        FOR EACH ROW EXECUTE FUNCTION extraction_terminal_guard();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER extraction_terminal_guard ON extraction_runs")
    op.execute("DROP FUNCTION extraction_terminal_guard()")
