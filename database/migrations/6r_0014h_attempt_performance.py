"""Add bounded performance metrics to fenced terminal extraction attempts."""

from alembic import op

revision = "6r_0014h_attempt_performance"
down_revision = "6r_0014g_attribute_dispatch"


def upgrade() -> None:
    op.execute("""
    ALTER TABLE extraction_work_units
        ADD COLUMN performance jsonb,
        ADD CONSTRAINT ck_extraction_attempt_performance CHECK (
            performance IS NULL OR (
                stage = 'ATTRIBUTE_EXTRACTION' AND status IN ('COMPLETED','FAILED')
                AND started_at IS NOT NULL AND jsonb_typeof(performance) = 'object'
                AND performance @> jsonb_build_object('version', 1)
                AND octet_length(performance::text) <= 4096
            )
        );
CREATE OR REPLACE FUNCTION extraction_unit_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent extraction_runs; previous extraction_work_units;
BEGIN
  IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Extraction attempts are append-only'; END IF;
  SELECT * INTO parent FROM extraction_runs WHERE id=NEW.run_id FOR UPDATE;
  IF parent.status NOT IN ('PENDING','RUNNING') THEN RAISE EXCEPTION 'Run is not active'; END
IF;
  IF TG_OP = 'UPDATE' THEN
    IF OLD.status IN ('COMPLETED','FAILED','CANCELLED') OR
       (to_jsonb(NEW) -
ARRAY['status','started_at','finished_at','lease_expires_at','heartbeat_at','error_code','error_message','output_counts','performance'])
IS DISTINCT FROM
       (to_jsonb(OLD) -
ARRAY['status','started_at','finished_at','lease_expires_at','heartbeat_at','error_code','error_message','output_counts','performance'])
THEN
      RAISE EXCEPTION 'Attempt history is immutable';
    END IF;
    IF OLD.status='PENDING' AND NEW.status='COMPLETED' THEN RAISE EXCEPTION 'Attempt was not
started'; END IF;
  ELSE
    IF NEW.status NOT IN ('PENDING','RUNNING') THEN RAISE EXCEPTION 'New attempt must be
active'; END IF;
    IF EXISTS (SELECT 1 FROM extraction_work_units WHERE run_id=NEW.run_id AND
unit_key=NEW.unit_key AND status='COMPLETED') THEN
      RAISE EXCEPTION 'Logical unit already succeeded';
    END IF;
    IF NEW.retry_of_work_unit_id IS NOT NULL THEN
      SELECT * INTO previous FROM extraction_work_units WHERE id=NEW.retry_of_work_unit_id;
      IF previous.status NOT IN ('FAILED','CANCELLED') OR NEW.attempt_number <=
previous.attempt_number
         OR NEW.stage <> previous.stage OR NEW.page_numbers <> previous.page_numbers
         OR NEW.input_artifact_ids <> previous.input_artifact_ids OR NEW.required <>
previous.required THEN
        RAISE EXCEPTION 'Invalid retry ancestry';
      END IF;
    ELSIF NEW.attempt_number <> 1 OR EXISTS (SELECT 1 FROM extraction_work_units WHERE
run_id=NEW.run_id AND unit_key=NEW.unit_key) THEN
      RAISE EXCEPTION 'Subsequent attempts require retry ancestry';
    END IF;
  END IF;
  IF NOT parent.selected_pages @> NEW.page_numbers OR NOT parent.input_artifact_ids @>
NEW.input_artifact_ids
     OR NOT parent.stages @> to_jsonb(ARRAY[NEW.stage]) THEN RAISE EXCEPTION 'Unit inputs differ
from pinned run'; END IF;
  RETURN NEW;
END $$;
    """)


def downgrade() -> None:
    raise RuntimeError("Performance telemetry migration requires backup-based rollback")
