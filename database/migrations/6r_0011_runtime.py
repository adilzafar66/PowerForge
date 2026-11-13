"""Phase 6R clean-install runtime schema."""

from alembic import op

revision = "6r_0011_runtime"
down_revision = "0010_authoring_refinement"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(r"""
CREATE TYPE extraction_run_status AS ENUM ('PENDING', 'RUNNING', 'COMPLETED',
'PARTIALLY_COMPLETED', 'FAILED', 'CANCELLED');
CREATE TYPE extraction_work_unit_status AS ENUM ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED',
'CANCELLED');
CREATE TYPE extraction_ai_call_outcome AS ENUM ('SUCCEEDED', 'FAILED', 'CANCELLED');
ALTER TABLE page_artifacts ADD CONSTRAINT uq_page_artifacts_context UNIQUE (id,
processing_run_id, document_page_id);

CREATE TABLE extraction_runs (
        document_id UUID NOT NULL,
        processing_run_id UUID NOT NULL,
        initiated_from_revision_document_id UUID,
        context_revision_id UUID,
        requested_by UUID,
        reextracts_run_id UUID,
        extractor_version TEXT NOT NULL,
        schema_version TEXT NOT NULL,
        registry_version TEXT NOT NULL,
        profile_version TEXT NOT NULL,
        profile_hash TEXT NOT NULL,
        input_identity_hash TEXT NOT NULL,
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        prompt_version TEXT NOT NULL,
        prompt_hash TEXT NOT NULL,
        context_fingerprint TEXT,
        selected_pages JSONB DEFAULT '[]'::jsonb NOT NULL,
        stages JSONB DEFAULT '[]'::jsonb NOT NULL,
        input_artifact_ids JSONB DEFAULT '[]'::jsonb NOT NULL,
        status extraction_run_status NOT NULL,
        pages_processed INTEGER DEFAULT 0 NOT NULL,
        units_total INTEGER DEFAULT 0 NOT NULL,
        units_completed INTEGER DEFAULT 0 NOT NULL,
        started_at TIMESTAMP WITH TIME ZONE,
        finished_at TIMESTAMP WITH TIME ZONE,
        error_code TEXT,
        error_message TEXT,
        id UUID DEFAULT gen_random_uuid() NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_extraction_runs_owner UNIQUE (id, document_id, processing_run_id),
        CONSTRAINT uq_extraction_runs_document UNIQUE (id, document_id),
        CONSTRAINT fk_extraction_runs_processing FOREIGN KEY(processing_run_id, document_id)
REFERENCES document_processing_runs (id, document_id),
        CONSTRAINT fk_extraction_runs_reextracts FOREIGN KEY(reextracts_run_id, document_id)
REFERENCES extraction_runs (id, document_id),
        CONSTRAINT fk_extraction_runs_initiator FOREIGN KEY(initiated_from_revision_document_id)
REFERENCES revision_documents (id),
        CONSTRAINT fk_extraction_runs_context FOREIGN KEY(context_revision_id) REFERENCES
project_revisions (id),
        CONSTRAINT ck_extraction_runs_not_self CHECK (reextracts_run_id IS NULL OR
reextracts_run_id <> id),
        CONSTRAINT ck_extraction_runs_context CHECK ((context_revision_id IS NULL) =
(context_fingerprint IS NULL)),
        CONSTRAINT ck_extraction_runs_progress CHECK (pages_processed >= 0 AND units_total >= 0
AND units_completed >= 0 AND units_completed <= units_total),
        CONSTRAINT ck_extraction_runs_inputs CHECK (jsonb_typeof(selected_pages) = 'array' AND
jsonb_array_length(selected_pages) > 0 AND jsonb_typeof(stages) = 'array' AND
jsonb_array_length(stages) > 0 AND jsonb_typeof(input_artifact_ids) = 'array' AND
jsonb_array_length(input_artifact_ids) > 0),
        CONSTRAINT ck_extraction_runs_error CHECK (error_message IS NULL OR
char_length(error_message) <= 1000)
)

;
CREATE INDEX ix_extraction_runs_history ON extraction_runs (document_id, created_at, id);
CREATE UNIQUE INDEX uq_extraction_runs_active ON extraction_runs (document_id,
input_identity_hash) WHERE status IN ('PENDING', 'RUNNING');

CREATE TABLE extraction_work_units (
        run_id UUID NOT NULL,
        document_id UUID NOT NULL,
        processing_run_id UUID NOT NULL,
        unit_key TEXT NOT NULL,
        stage TEXT NOT NULL,
        attempt_number INTEGER NOT NULL,
        retry_of_work_unit_id UUID,
        required BOOLEAN NOT NULL,
        page_numbers JSONB DEFAULT '[]'::jsonb NOT NULL,
        input_artifact_ids JSONB DEFAULT '[]'::jsonb NOT NULL,
        execution_metadata JSONB DEFAULT '{}'::jsonb NOT NULL,
        status extraction_work_unit_status NOT NULL,
        started_at TIMESTAMP WITH TIME ZONE,
        finished_at TIMESTAMP WITH TIME ZONE,
        lease_expires_at TIMESTAMP WITH TIME ZONE,
        heartbeat_at TIMESTAMP WITH TIME ZONE,
        error_code TEXT,
        error_message TEXT,
        output_counts JSONB DEFAULT '{}'::jsonb NOT NULL,
        id UUID DEFAULT gen_random_uuid() NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_extraction_work_units_owner UNIQUE (id, run_id, document_id,
processing_run_id),
        CONSTRAINT uq_extraction_work_units_retry_owner UNIQUE (id, run_id, unit_key),
        CONSTRAINT uq_extraction_work_units_attempt UNIQUE (run_id, unit_key, attempt_number),
        CONSTRAINT fk_extraction_work_units_run FOREIGN KEY(run_id, document_id,
processing_run_id) REFERENCES extraction_runs (id, document_id, processing_run_id),
        CONSTRAINT fk_extraction_work_units_retry FOREIGN KEY(retry_of_work_unit_id, run_id,
unit_key) REFERENCES extraction_work_units (id, run_id, unit_key),
        CONSTRAINT ck_extraction_work_units_attempt CHECK (attempt_number >= 1 AND
(retry_of_work_unit_id IS NULL OR retry_of_work_unit_id <> id)),
        CONSTRAINT ck_extraction_work_units_inputs CHECK (jsonb_typeof(page_numbers) = 'array'
AND jsonb_array_length(page_numbers) > 0 AND jsonb_typeof(input_artifact_ids) = 'array'),
        CONSTRAINT ck_extraction_work_units_error CHECK (error_message IS NULL OR
char_length(error_message) <= 1000)
)

;
CREATE UNIQUE INDEX uq_extraction_work_units_active ON extraction_work_units (run_id, unit_key)
WHERE status IN ('PENDING', 'RUNNING');
CREATE UNIQUE INDEX uq_extraction_work_units_success ON extraction_work_units (run_id, unit_key)
WHERE status = 'COMPLETED';

CREATE TABLE extraction_ai_calls (
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        prompt_version TEXT NOT NULL,
        prompt_hash TEXT NOT NULL,
        schema_version TEXT NOT NULL,
        request_correlation_id TEXT,
        outcome extraction_ai_call_outcome NOT NULL,
        error_code TEXT,
        started_at TIMESTAMP WITH TIME ZONE NOT NULL,
        finished_at TIMESTAMP WITH TIME ZONE NOT NULL,
        duration_ms INTEGER NOT NULL,
        input_tokens INTEGER,
        cached_input_tokens INTEGER,
        output_tokens INTEGER,
        estimated_cost_usd NUMERIC,
        pricing_basis TEXT,
        run_id UUID NOT NULL,
        document_id UUID NOT NULL,
        processing_run_id UUID NOT NULL,
        work_unit_id UUID NOT NULL,
        id UUID DEFAULT gen_random_uuid() NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_extraction_ai_calls_owner UNIQUE (id, run_id, document_id),
        CONSTRAINT fk_extraction_ai_calls_unit FOREIGN KEY(work_unit_id, run_id, document_id,
processing_run_id) REFERENCES extraction_work_units (id, run_id, document_id,
processing_run_id),
        CONSTRAINT ck_extraction_ai_calls_usage CHECK (duration_ms >= 0 AND input_tokens >= 0
AND cached_input_tokens >= 0 AND output_tokens >= 0 AND finished_at >= started_at AND
(cached_input_tokens IS NULL OR input_tokens IS NULL OR cached_input_tokens <= input_tokens)),
        CONSTRAINT ck_extraction_ai_calls_cost CHECK (estimated_cost_usd IS NULL OR
(estimated_cost_usd >= 0 AND estimated_cost_usd::text NOT IN ('NaN','Infinity','-Infinity') AND
pricing_basis IS NOT NULL))
)

;
CREATE INDEX ix_extraction_ai_calls_run_unit ON extraction_ai_calls (run_id, work_unit_id);
""")
    op.execute(r"""
CREATE FUNCTION extraction_run_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Extraction history is immutable'; END IF;
  IF TG_OP = 'UPDATE' THEN
    IF (to_jsonb(NEW) -
ARRAY['status','pages_processed','units_total','units_completed','started_at','finished_at','error_code','error_message'])
IS DISTINCT FROM
       (to_jsonb(OLD) -
ARRAY['status','pages_processed','units_total','units_completed','started_at','finished_at','error_code','error_message'])
       OR OLD.status IN ('COMPLETED','CANCELLED') THEN
      RAISE EXCEPTION 'Extraction input and terminal history are immutable';
    END IF;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM document_processing_runs p WHERE p.id=NEW.processing_run_id
                AND p.document_id=NEW.document_id AND p.status='COMPLETED') THEN
    RAISE EXCEPTION 'Extraction requires compatible completed processing';
  END IF;
  IF EXISTS (SELECT 1 FROM jsonb_array_elements_text(NEW.input_artifact_ids) a
    WHERE NOT EXISTS (SELECT 1 FROM page_artifacts pa JOIN document_pages dp ON
dp.id=pa.document_page_id
      WHERE pa.id=a::uuid AND pa.processing_run_id=NEW.processing_run_id AND
dp.document_id=NEW.document_id
      AND NEW.selected_pages @> to_jsonb(ARRAY[dp.page_number]))) THEN
    RAISE EXCEPTION 'Invalid pinned extraction artifact';
  END IF;
  IF EXISTS (SELECT 1 FROM jsonb_array_elements_text(NEW.selected_pages) n WHERE n::int < 1 OR
    NOT EXISTS (SELECT 1 FROM document_pages dp WHERE dp.document_id=NEW.document_id AND
dp.page_number=n::int)) THEN
    RAISE EXCEPTION 'Invalid selected page';
  END IF;
  IF NEW.initiated_from_revision_document_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM revision_documents rd WHERE rd.id=NEW.initiated_from_revision_document_id AND
rd.document_id=NEW.document_id) THEN
    RAISE EXCEPTION 'Invalid initiating document';
  END IF;
  IF NEW.context_revision_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM revision_documents rd WHERE rd.revision_id=NEW.context_revision_id AND
rd.document_id=NEW.document_id AND rd.status='INCLUDED') THEN
    RAISE EXCEPTION 'Invalid context revision';
  END IF;
  IF NEW.status='COMPLETED' AND (
    NOT EXISTS (SELECT 1 FROM extraction_work_units WHERE run_id=NEW.id AND required)
    OR EXISTS (SELECT 1 FROM extraction_work_units u WHERE u.run_id=NEW.id AND u.required
      AND NOT EXISTS (SELECT 1 FROM extraction_work_units ok WHERE ok.run_id=NEW.id
        AND ok.unit_key=u.unit_key AND ok.status='COMPLETED'))) THEN
    RAISE EXCEPTION 'Completion requires all required logical units to succeed';
  END IF;
  IF NEW.status='PARTIALLY_COMPLETED' AND (
    NOT EXISTS (SELECT 1 FROM extraction_work_units WHERE run_id=NEW.id AND required
      AND status='COMPLETED')
    OR NOT EXISTS (SELECT 1 FROM extraction_work_units u WHERE u.run_id=NEW.id AND u.required
      AND NOT EXISTS (SELECT 1 FROM extraction_work_units ok WHERE ok.run_id=NEW.id
        AND ok.unit_key=u.unit_key AND ok.status='COMPLETED'))) THEN
    RAISE EXCEPTION 'Partial completion requires successful and unsuccessful required units';
  END IF;
  IF NEW.status='FAILED' AND EXISTS (SELECT 1 FROM extraction_work_units WHERE run_id=NEW.id
    AND required AND status='COMPLETED') THEN
    RAISE EXCEPTION 'Useful required outputs need a partial or completed run';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER extraction_run_guard BEFORE INSERT OR UPDATE OR DELETE ON extraction_runs
FOR EACH ROW EXECUTE FUNCTION extraction_run_guard();

CREATE FUNCTION extraction_unit_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent extraction_runs; previous extraction_work_units;
BEGIN
  IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Extraction attempts are append-only'; END IF;
  SELECT * INTO parent FROM extraction_runs WHERE id=NEW.run_id FOR UPDATE;
  IF parent.status NOT IN ('PENDING','RUNNING') THEN RAISE EXCEPTION 'Run is not active'; END
IF;
  IF TG_OP = 'UPDATE' THEN
    IF OLD.status IN ('COMPLETED','FAILED','CANCELLED') OR
       (to_jsonb(NEW) -
ARRAY['status','started_at','finished_at','lease_expires_at','heartbeat_at','error_code','error_message','output_counts'])
IS DISTINCT FROM
       (to_jsonb(OLD) -
ARRAY['status','started_at','finished_at','lease_expires_at','heartbeat_at','error_code','error_message','output_counts'])
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
CREATE TRIGGER extraction_unit_guard BEFORE INSERT OR UPDATE OR DELETE ON extraction_work_units
FOR EACH ROW EXECUTE FUNCTION extraction_unit_guard();

""")
    op.execute(r"""
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
        """)
    op.execute(r"""
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
    op.execute(r"""
    CREATE TABLE extraction_stage_results (
        work_unit_id uuid PRIMARY KEY,
        run_id uuid NOT NULL REFERENCES extraction_runs(id),
        document_page_id uuid NOT NULL REFERENCES document_pages(id),
        stage text NOT NULL CHECK(stage IN ('EQUIPMENT_RECOGNITION','ATTRIBUTE_EXTRACTION')),
        outcome text NOT NULL CHECK(outcome IN ('RESULT','NO_ELIGIBLE_ATTRIBUTES')),
        page_context_hash text NOT NULL CHECK(page_context_hash ~ '^[0-9a-f]{64}$'),
        upstream_work_unit_id uuid,
        upstream_hash text,
        request_hash text NOT NULL CHECK(request_hash ~ '^[0-9a-f]{64}$'),
        result_hash text NOT NULL CHECK(result_hash ~ '^[0-9a-f]{64}$'),
        payload jsonb NOT NULL CHECK(jsonb_typeof(payload) = 'object'
            AND octet_length(payload::text) <= 1048576),
        UNIQUE(work_unit_id,run_id,document_page_id,page_context_hash,result_hash),
        FOREIGN KEY(work_unit_id) REFERENCES extraction_work_units(id),
        FOREIGN KEY(upstream_work_unit_id,run_id,document_page_id,page_context_hash,upstream_hash)
            REFERENCES extraction_stage_results
                (work_unit_id,run_id,document_page_id,page_context_hash,result_hash),
        CHECK (
            (stage='EQUIPMENT_RECOGNITION' AND outcome='RESULT'
                AND upstream_work_unit_id IS NULL AND upstream_hash IS NULL)
            OR (stage='ATTRIBUTE_EXTRACTION' AND upstream_work_unit_id IS NOT NULL
                AND upstream_hash IS NOT NULL)
        )
    );
    CREATE TRIGGER extraction_fence_guard BEFORE INSERT ON extraction_stage_results
      FOR EACH ROW EXECUTE FUNCTION extraction_fence_guard();
    CREATE TRIGGER extraction_fence_guard BEFORE INSERT ON extraction_ai_calls
      FOR EACH ROW EXECUTE FUNCTION extraction_fence_guard();
""")


def downgrade() -> None:
    raise RuntimeError("Phase 6R uses a clean installation and backup-based recovery")
