"""Durable extraction delivery, leases and publication fencing."""

from alembic import op

revision = "0013_extraction_execution"
down_revision = "0012_extraction_terminal_guard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE extraction_run_execution (
      run_id uuid PRIMARY KEY REFERENCES extraction_runs(id),
      configuration jsonb NOT NULL,
      calls_admitted integer NOT NULL DEFAULT 0,
      cancel_requested_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT ck_extraction_run_execution_calls CHECK (calls_admitted >= 0
        AND calls_admitted <= (configuration->>'max_calls')::int),
      CONSTRAINT ck_extraction_run_execution_configuration CHECK (
        jsonb_typeof(configuration)='object' AND octet_length(configuration::text) <= 64000)
    );
    CREATE TABLE extraction_unit_execution (
      work_unit_id uuid PRIMARY KEY, run_id uuid NOT NULL, unit_key varchar NOT NULL,
      token uuid, available_at timestamptz NOT NULL, dispatch_after timestamptz NOT NULL,
      dispatched_at timestamptz, dispatch_count integer NOT NULL DEFAULT 0,
      hard_deadline_at timestamptz, provider_started_at timestamptz,
      CONSTRAINT fk_extraction_unit_execution_owner FOREIGN KEY(work_unit_id,run_id,unit_key)
        REFERENCES extraction_work_units(id,run_id,unit_key),
      CONSTRAINT ck_extraction_unit_execution_dispatch CHECK (dispatch_count >= 0)
    );
    CREATE INDEX ix_extraction_unit_execution_delivery
      ON extraction_unit_execution(dispatch_after,available_at);

    CREATE FUNCTION extraction_control_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Execution control history cannot be deleted'; END IF;
      IF TG_TABLE_NAME='extraction_run_execution' AND TG_OP='UPDATE' THEN
        IF NEW.run_id <> OLD.run_id OR NEW.configuration <> OLD.configuration
           OR NEW.created_at <> OLD.created_at OR NEW.calls_admitted < OLD.calls_admitted
           OR (OLD.cancel_requested_at IS NOT NULL AND
               NEW.cancel_requested_at IS DISTINCT FROM OLD.cancel_requested_at) THEN
          RAISE EXCEPTION 'Pinned execution configuration/history is immutable';
        END IF;
      ELSIF TG_TABLE_NAME='extraction_unit_execution' AND TG_OP='UPDATE' THEN
        IF NEW.work_unit_id <> OLD.work_unit_id OR NEW.run_id <> OLD.run_id
           OR NEW.unit_key <> OLD.unit_key OR NEW.available_at <> OLD.available_at
           OR (OLD.token IS NOT NULL AND NEW.token IS DISTINCT FROM OLD.token)
           OR (OLD.hard_deadline_at IS NOT NULL AND
               NEW.hard_deadline_at IS DISTINCT FROM OLD.hard_deadline_at)
           OR (OLD.provider_started_at IS NOT NULL AND
               NEW.provider_started_at IS DISTINCT FROM OLD.provider_started_at) THEN
          RAISE EXCEPTION 'Execution attempt identity/token is immutable';
        END IF;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER extraction_control_guard BEFORE UPDATE OR DELETE ON extraction_run_execution
      FOR EACH ROW EXECUTE FUNCTION extraction_control_guard();
    CREATE TRIGGER extraction_control_guard BEFORE UPDATE OR DELETE ON extraction_unit_execution
      FOR EACH ROW EXECUTE FUNCTION extraction_control_guard();

    CREATE FUNCTION extraction_fence_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE uid uuid; rid uuid; supplied text; authorized boolean;
    BEGIN
      IF TG_TABLE_NAME='extraction_work_units' THEN
        IF NEW.status <> 'COMPLETED' THEN RETURN NEW; END IF;
        uid := NEW.id; rid := NEW.run_id;
      ELSE uid := NEW.work_unit_id; rid := NEW.run_id;
      END IF;
      IF NOT EXISTS (SELECT 1 FROM extraction_run_execution WHERE run_id=rid) THEN
        RETURN NEW; -- Preserve legacy/internal 6A publication contracts.
      END IF;
      supplied := current_setting('powerforge.extraction_lease_token', true);
      SELECT true INTO authorized FROM extraction_unit_execution c
        JOIN extraction_work_units u ON u.id=c.work_unit_id
        JOIN extraction_run_execution e ON e.run_id=c.run_id
        JOIN extraction_runs r ON r.id=c.run_id
        WHERE c.work_unit_id=uid AND c.run_id=rid AND c.token::text=supplied
          AND u.status='RUNNING' AND u.lease_expires_at > clock_timestamp()
          AND c.hard_deadline_at > clock_timestamp() AND e.cancel_requested_at IS NULL
          AND r.status='RUNNING';
      IF authorized IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'Execution lease does not authorize publication'
          USING ERRCODE='23514', CONSTRAINT='ck_extraction_publication_fence';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER extraction_fence_guard BEFORE UPDATE ON extraction_work_units
      FOR EACH ROW EXECUTE FUNCTION extraction_fence_guard();
    """)
    for table in (
        "extraction_source_groups",
        "extracted_tables",
        "extraction_evidence",
        "extraction_candidates",
        "candidate_evidence",
        "extraction_ai_calls",
    ):
        op.execute(
            f"CREATE TRIGGER extraction_fence_guard BEFORE INSERT ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION extraction_fence_guard()"
        )


def downgrade() -> None:
    for table in (
        "extraction_source_groups",
        "extracted_tables",
        "extraction_evidence",
        "extraction_candidates",
        "candidate_evidence",
        "extraction_ai_calls",
        "extraction_work_units",
    ):
        op.execute(f"DROP TRIGGER extraction_fence_guard ON {table}")
    op.execute("DROP FUNCTION extraction_fence_guard()")
    op.execute("DROP TABLE extraction_unit_execution")
    op.execute("DROP TABLE extraction_run_execution")
    op.execute("DROP FUNCTION extraction_control_guard()")
