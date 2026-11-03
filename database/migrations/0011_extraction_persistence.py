"""Evidence and extraction persistence foundation. Frozen DDL; no runtime registry imports."""

from alembic import op

revision = "0011_extraction_persistence"
down_revision = "0010_authoring_refinement"
branch_labels = None
depends_on = None

SCHEMA_SQL = r"""
CREATE TYPE extraction_run_status AS ENUM ('PENDING', 'RUNNING', 'COMPLETED',
'PARTIALLY_COMPLETED', 'FAILED', 'CANCELLED');
CREATE TYPE extraction_work_unit_status AS ENUM ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED',
'CANCELLED');
CREATE TYPE extraction_table_kind AS ENUM ('ATTRIBUTE_ROWS', 'EQUIPMENT_ROWS', 'MIXED',
'UNCLASSIFIED');
CREATE TYPE extraction_source_kind AS ENUM ('NATIVE_TEXT', 'OCR_TEXT', 'VISUAL_REGION',
'TABLE_CELL');
CREATE TYPE extraction_method AS ENUM ('AI_VISION', 'AI_TEXT', 'OCR', 'TABLE', 'MANUAL');
CREATE TYPE extraction_candidate_kind AS ENUM ('EQUIPMENT_MENTION', 'ATTRIBUTE_VALUE',
'UNMAPPED_OBSERVATION');
CREATE TYPE extraction_mapping_status AS ENUM ('MAPPED', 'UNMAPPED', 'INVALID');
CREATE TYPE extraction_evidence_role AS ENUM ('PRIMARY', 'SUPPORTING', 'CONTRADICTING');
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

CREATE TABLE extraction_source_groups (
        local_key TEXT NOT NULL,
        equipment_type_hint TEXT,
        tag_text TEXT,
        label TEXT,
        evidence_ids JSONB DEFAULT '[]'::jsonb NOT NULL,
        run_id UUID NOT NULL,
        document_id UUID NOT NULL,
        processing_run_id UUID NOT NULL,
        work_unit_id UUID NOT NULL,
        id UUID DEFAULT gen_random_uuid() NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_extraction_source_groups_owner UNIQUE (id, run_id, document_id),
        CONSTRAINT fk_extraction_source_groups_unit FOREIGN KEY(work_unit_id, run_id,
document_id, processing_run_id) REFERENCES extraction_work_units (id, run_id, document_id,
processing_run_id),
        CONSTRAINT uq_extraction_source_groups_local_key UNIQUE (run_id, local_key)
)

;
CREATE INDEX ix_extraction_source_groups_run_unit ON extraction_source_groups (run_id,
work_unit_id);

CREATE TABLE extracted_tables (
        layout_schema_version TEXT NOT NULL,
        table_kind extraction_table_kind NOT NULL,
        source_locations JSONB DEFAULT '[]'::jsonb NOT NULL,
        evidence_ids JSONB DEFAULT '[]'::jsonb NOT NULL,
        layout JSONB NOT NULL,
        run_id UUID NOT NULL,
        document_id UUID NOT NULL,
        processing_run_id UUID NOT NULL,
        work_unit_id UUID NOT NULL,
        id UUID DEFAULT gen_random_uuid() NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_extracted_tables_owner UNIQUE (id, run_id, document_id),
        CONSTRAINT fk_extracted_tables_unit FOREIGN KEY(work_unit_id, run_id, document_id,
processing_run_id) REFERENCES extraction_work_units (id, run_id, document_id,
processing_run_id),
        CONSTRAINT ck_extracted_tables_layout CHECK (layout_schema_version = 'table-layout-v1'
AND jsonb_typeof(layout) = 'object' AND jsonb_typeof(source_locations) = 'array' AND
jsonb_array_length(source_locations) > 0)
)

;
CREATE INDEX ix_extracted_tables_run_unit ON extracted_tables (run_id, work_unit_id);

CREATE TABLE extraction_evidence (
        document_page_id UUID NOT NULL,
        page_artifact_id UUID,
        source_kind extraction_source_kind NOT NULL,
        extraction_method extraction_method NOT NULL,
        source_snippet TEXT,
        text_start INTEGER,
        text_end INTEGER,
        offset_convention TEXT,
        x NUMERIC,
        y NUMERIC,
        width NUMERIC,
        height NUMERIC,
        table_id UUID,
        cell_id TEXT,
        run_id UUID NOT NULL,
        document_id UUID NOT NULL,
        processing_run_id UUID NOT NULL,
        work_unit_id UUID NOT NULL,
        id UUID DEFAULT gen_random_uuid() NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_extraction_evidence_owner UNIQUE (id, run_id, document_id),
        CONSTRAINT fk_extraction_evidence_unit FOREIGN KEY(work_unit_id, run_id, document_id,
processing_run_id) REFERENCES extraction_work_units (id, run_id, document_id,
processing_run_id),
        CONSTRAINT fk_extraction_evidence_page FOREIGN KEY(document_page_id, document_id)
REFERENCES document_pages (id, document_id),
        CONSTRAINT fk_extraction_evidence_artifact FOREIGN KEY(page_artifact_id,
processing_run_id, document_page_id) REFERENCES page_artifacts (id, processing_run_id,
document_page_id),
        CONSTRAINT fk_extraction_evidence_table FOREIGN KEY(table_id, run_id, document_id)
REFERENCES extracted_tables (id, run_id, document_id),
        CONSTRAINT ck_extraction_evidence_snippet CHECK (source_snippet IS NULL OR
char_length(source_snippet) <= 2000),
        CONSTRAINT ck_extraction_evidence_offsets CHECK ((text_start IS NULL AND text_end IS
NULL AND offset_convention IS NULL) OR (text_start IS NOT NULL AND text_end IS NOT NULL AND
text_start >= 0 AND text_end > text_start AND page_artifact_id IS NOT NULL AND offset_convention
IS NOT NULL AND offset_convention = 'UNICODE_CODEPOINT')),
        CONSTRAINT ck_extraction_evidence_region CHECK ((x IS NULL AND y IS NULL AND width IS
NULL AND height IS NULL) OR (x IS NOT NULL AND y IS NOT NULL AND width IS NOT NULL AND height IS
NOT NULL AND x >= 0 AND y >= 0 AND width > 0 AND height > 0 AND x + width <= 1 AND y + height <=
1)),
        CONSTRAINT ck_extraction_evidence_cell CHECK (cell_id IS NULL OR table_id IS NOT NULL)
)

;
CREATE INDEX ix_extraction_evidence_page ON extraction_evidence (document_page_id);
CREATE INDEX ix_extraction_evidence_run_unit ON extraction_evidence (run_id, work_unit_id);

CREATE TABLE extraction_candidates (
        kind extraction_candidate_kind NOT NULL,
        mapping_status extraction_mapping_status NOT NULL,
        raw_text TEXT NOT NULL,
        raw_value TEXT,
        raw_unit TEXT,
        observed_tag TEXT,
        equipment_type_key TEXT,
        attribute_key TEXT,
        value_type TEXT,
        unit TEXT,
        source_group_id UUID,
        equipment_mention_candidate_id UUID,
        numeric_value NUMERIC,
        integer_value BIGINT,
        text_value TEXT,
        boolean_value BOOLEAN,
        confidence NUMERIC,
        confidence_band TEXT,
        confidence_method TEXT,
        reason_code TEXT,
        explanation TEXT,
        diagnostics JSONB DEFAULT '{}'::jsonb NOT NULL,
        run_id UUID NOT NULL,
        document_id UUID NOT NULL,
        processing_run_id UUID NOT NULL,
        work_unit_id UUID NOT NULL,
        id UUID DEFAULT gen_random_uuid() NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_extraction_candidates_owner UNIQUE (id, run_id, document_id),
        CONSTRAINT fk_extraction_candidates_unit FOREIGN KEY(work_unit_id, run_id, document_id,
processing_run_id) REFERENCES extraction_work_units (id, run_id, document_id,
processing_run_id),
        CONSTRAINT fk_extraction_candidates_group FOREIGN KEY(source_group_id, run_id,
document_id) REFERENCES extraction_source_groups (id, run_id, document_id),
        CONSTRAINT fk_extraction_candidates_mention FOREIGN KEY(equipment_mention_candidate_id,
run_id, document_id) REFERENCES extraction_candidates (id, run_id, document_id),
        CONSTRAINT ck_extraction_candidates_confidence CHECK (confidence >= 0 AND confidence <=
1),
        CONSTRAINT ck_extraction_candidates_finite CHECK (numeric_value IS NULL OR
numeric_value::text NOT IN ('NaN','Infinity','-Infinity')),
        CONSTRAINT ck_extraction_candidates_bounded CHECK (char_length(raw_text) BETWEEN 1 AND
2000 AND (raw_value IS NULL OR char_length(raw_value) <= 2000) AND (explanation IS NULL OR
char_length(explanation) <= 1000) AND octet_length(diagnostics::text) <= 16000),
        CONSTRAINT ck_extraction_candidates_typed CHECK ((mapping_status = 'MAPPED' AND kind =
'ATTRIBUTE_VALUE' AND equipment_type_key IS NOT NULL AND attribute_key IS NOT NULL AND
value_type IS NOT NULL AND num_nonnulls(numeric_value, integer_value, text_value, boolean_value)
= 1 AND ((value_type = 'NUMBER' AND numeric_value IS NOT NULL) OR (value_type = 'INTEGER' AND
integer_value IS NOT NULL) OR (value_type IN ('TEXT','ENUM') AND text_value IS NOT NULL) OR
(value_type = 'BOOLEAN' AND boolean_value IS NOT NULL))) OR (num_nonnulls(numeric_value,
integer_value, text_value, boolean_value) = 0 AND value_type IS NULL AND unit IS NULL AND
attribute_key IS NULL AND (mapping_status <> 'MAPPED' OR (kind = 'EQUIPMENT_MENTION' AND
equipment_type_key IS NOT NULL)))),
        CONSTRAINT ck_extraction_candidates_not_self CHECK (equipment_mention_candidate_id IS
NULL OR (equipment_mention_candidate_id <> id AND kind <> 'EQUIPMENT_MENTION'))
)

;
CREATE INDEX ix_extraction_candidates_filters ON extraction_candidates (run_id, mapping_status,
kind, id);
CREATE INDEX ix_extraction_candidates_group ON extraction_candidates (source_group_id);
CREATE INDEX ix_extraction_candidates_run_unit ON extraction_candidates (run_id, work_unit_id);

CREATE TABLE candidate_evidence (
        candidate_id UUID NOT NULL,
        evidence_id UUID NOT NULL,
        role extraction_evidence_role NOT NULL,
        position INTEGER NOT NULL,
        run_id UUID NOT NULL,
        document_id UUID NOT NULL,
        processing_run_id UUID NOT NULL,
        work_unit_id UUID NOT NULL,
        id UUID DEFAULT gen_random_uuid() NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_candidate_evidence_owner UNIQUE (id, run_id, document_id),
        CONSTRAINT fk_candidate_evidence_unit FOREIGN KEY(work_unit_id, run_id, document_id,
processing_run_id) REFERENCES extraction_work_units (id, run_id, document_id,
processing_run_id),
        CONSTRAINT uq_candidate_evidence_link UNIQUE (candidate_id, evidence_id),
        CONSTRAINT fk_candidate_evidence_candidate FOREIGN KEY(candidate_id, run_id,
document_id) REFERENCES extraction_candidates (id, run_id, document_id),
        CONSTRAINT fk_candidate_evidence_evidence FOREIGN KEY(evidence_id, run_id, document_id)
REFERENCES extraction_evidence (id, run_id, document_id),
        CONSTRAINT ck_candidate_evidence_position CHECK (position >= 0)
)

;
CREATE INDEX ix_candidate_evidence_evidence ON candidate_evidence (evidence_id);
CREATE INDEX ix_candidate_evidence_run_unit ON candidate_evidence (run_id, work_unit_id);

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
"""

GUARD_SQL = r"""
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

CREATE FUNCTION extraction_output_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE unit extraction_work_units; page_number integer; artifact page_artifacts; loc jsonb;
BEGIN
  IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'Extraction output is immutable'; END IF;
  SELECT * INTO unit FROM extraction_work_units WHERE id=NEW.work_unit_id FOR UPDATE;
  IF unit.status <> 'RUNNING' THEN RAISE EXCEPTION 'Output requires a running unit'; END IF;
  IF TG_TABLE_NAME='extraction_evidence' THEN
    SELECT dp.page_number INTO page_number FROM document_pages dp WHERE
dp.id=NEW.document_page_id AND dp.document_id=NEW.document_id;
    IF page_number IS NULL OR NOT unit.page_numbers @> to_jsonb(ARRAY[page_number]) THEN RAISE
EXCEPTION 'Evidence outside unit pages'; END IF;
    IF NEW.page_artifact_id IS NOT NULL THEN
      SELECT * INTO artifact FROM page_artifacts WHERE id=NEW.page_artifact_id;
      IF NOT unit.input_artifact_ids @> to_jsonb(ARRAY[NEW.page_artifact_id::text]) THEN RAISE
EXCEPTION 'Evidence artifact not pinned'; END IF;
      IF NEW.text_start IS NOT NULL AND artifact.artifact_type::text NOT IN
('NATIVE_TEXT','OCR_TEXT') THEN RAISE EXCEPTION 'Offsets require text artifact'; END IF;
    END IF;
  ELSIF TG_TABLE_NAME='extracted_tables' THEN
    FOR loc IN SELECT value FROM jsonb_array_elements(NEW.source_locations) LOOP
      IF NOT EXISTS (SELECT 1 FROM document_pages dp WHERE
dp.id=(loc->>'document_page_id')::uuid
        AND dp.document_id=NEW.document_id AND unit.page_numbers @>
to_jsonb(ARRAY[dp.page_number])) THEN RAISE EXCEPTION 'Table outside unit pages'; END IF;
      IF loc->>'page_artifact_id' IS NOT NULL AND NOT EXISTS (SELECT 1 FROM page_artifacts pa
WHERE pa.id=(loc->>'page_artifact_id')::uuid
        AND pa.document_page_id=(loc->>'document_page_id')::uuid AND
pa.processing_run_id=NEW.processing_run_id
        AND unit.input_artifact_ids @> to_jsonb(ARRAY[pa.id::text])) THEN RAISE EXCEPTION
'Invalid table artifact'; END IF;
    END LOOP;
  ELSIF TG_TABLE_NAME='extraction_candidates' THEN
    IF NEW.equipment_mention_candidate_id IS NOT NULL AND NOT EXISTS (
      SELECT 1 FROM extraction_candidates c WHERE c.id=NEW.equipment_mention_candidate_id AND
c.kind='EQUIPMENT_MENTION') THEN
      RAISE EXCEPTION 'Association must reference an equipment mention'; END IF;
  ELSIF TG_TABLE_NAME='candidate_evidence' THEN
    IF NOT EXISTS (SELECT 1 FROM extraction_candidates c WHERE c.id=NEW.candidate_id AND
c.work_unit_id=NEW.work_unit_id) THEN
      RAISE EXCEPTION 'Links belong to the producing candidate unit'; END IF;
  END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION extraction_publication_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM extraction_work_units WHERE id=NEW.work_unit_id AND
status='COMPLETED') THEN
    RAISE EXCEPTION 'Output and successful completion must commit together';
  END IF;
  RETURN NULL;
END $$;
"""

OUTPUT_TABLES = (
    "extraction_source_groups",
    "extracted_tables",
    "extraction_evidence",
    "extraction_candidates",
    "candidate_evidence",
    "extraction_ai_calls",
)


def upgrade() -> None:
    op.execute(SCHEMA_SQL)
    op.execute(GUARD_SQL)
    for table in OUTPUT_TABLES:
        op.execute(
            f"CREATE TRIGGER extraction_output_guard BEFORE INSERT OR UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION extraction_output_guard()"
        )
        if table == "extraction_ai_calls":
            continue  # Technical failures survive independently of successful result publication.
        op.execute(
            f"CREATE CONSTRAINT TRIGGER extraction_publication_guard AFTER INSERT ON {table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            "EXECUTE FUNCTION extraction_publication_guard()"
        )


def downgrade() -> None:
    op.execute("DROP TABLE extraction_ai_calls")
    op.execute("DROP TABLE candidate_evidence")
    op.execute("DROP TABLE extraction_candidates")
    op.execute("DROP TABLE extraction_evidence")
    op.execute("DROP TABLE extracted_tables")
    op.execute("DROP TABLE extraction_source_groups")
    op.execute("DROP TABLE extraction_work_units")
    op.execute("DROP TABLE extraction_runs")
    op.execute("ALTER TABLE page_artifacts DROP CONSTRAINT uq_page_artifacts_context")
    op.execute("DROP TYPE extraction_ai_call_outcome")
    op.execute("DROP TYPE extraction_evidence_role")
    op.execute("DROP TYPE extraction_mapping_status")
    op.execute("DROP TYPE extraction_candidate_kind")
    op.execute("DROP TYPE extraction_method")
    op.execute("DROP TYPE extraction_source_kind")
    op.execute("DROP TYPE extraction_table_kind")
    op.execute("DROP TYPE extraction_work_unit_status")
    op.execute("DROP TYPE extraction_run_status")
    op.execute("DROP FUNCTION extraction_publication_guard()")
    op.execute("DROP FUNCTION extraction_output_guard()")
    op.execute("DROP FUNCTION extraction_unit_guard()")
    op.execute("DROP FUNCTION extraction_run_guard()")
