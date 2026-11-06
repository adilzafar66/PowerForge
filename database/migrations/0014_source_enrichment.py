"""Purpose-separated local source preparation on the existing leased lifecycle."""

from alembic import op

revision = "0014_source_enrichment"
down_revision = "0013_extraction_execution"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE extraction_runs ADD COLUMN execution_purpose text NOT NULL DEFAULT 'EXTRACTION'
      CHECK (execution_purpose IN ('EXTRACTION','SOURCE_ENRICHMENT'));
    ALTER TABLE extraction_runs ALTER COLUMN registry_version DROP NOT NULL,
      ALTER COLUMN model DROP NOT NULL, ALTER COLUMN prompt_version DROP NOT NULL,
      ALTER COLUMN prompt_hash DROP NOT NULL;
    ALTER TABLE extraction_runs ADD CONSTRAINT ck_extraction_purpose_metadata CHECK (
      (execution_purpose='EXTRACTION' AND registry_version IS NOT NULL AND model IS NOT NULL
       AND prompt_version IS NOT NULL AND prompt_hash IS NOT NULL) OR
      (execution_purpose='SOURCE_ENRICHMENT' AND registry_version IS NULL AND model IS NULL
       AND prompt_version IS NULL AND prompt_hash IS NULL AND provider='local'
       AND context_revision_id IS NULL AND stages='["SOURCE_PREPARE"]'::jsonb));
    CREATE INDEX ix_extraction_runs_purpose ON
      extraction_runs(document_id,execution_purpose,created_at);
    CREATE TABLE source_enrichment_page_results (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),created_at timestamptz NOT NULL DEFAULT now(),
      run_id uuid NOT NULL,document_id uuid NOT NULL,processing_run_id uuid NOT NULL,
      work_unit_id uuid NOT NULL UNIQUE,document_page_id uuid NOT NULL,
      preparation_hash text NOT NULL CHECK(preparation_hash ~ '^[a-f0-9]{64}$'),
      manifest_hash text NOT NULL CHECK(manifest_hash ~ '^[a-f0-9]{64}$'),
      manifest jsonb NOT NULL CHECK(jsonb_typeof(manifest)='object' AND
        octet_length(manifest::text)<=4194304),
      usage jsonb NOT NULL CHECK(jsonb_typeof(usage)='object' AND octet_length(usage::text)<=16000),
      UNIQUE(id,run_id,document_id),UNIQUE(id,document_id,processing_run_id,document_page_id),
      FOREIGN KEY(work_unit_id,run_id,document_id,processing_run_id)
        REFERENCES extraction_work_units(id,run_id,document_id,processing_run_id),
      FOREIGN KEY(document_page_id,document_id) REFERENCES document_pages(id,document_id));
    CREATE INDEX ix_source_enrichment_page_results_run_unit ON
      source_enrichment_page_results(run_id,work_unit_id);
    CREATE TABLE source_enrichment_artifacts (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),created_at timestamptz NOT NULL DEFAULT now(),
      result_id uuid NOT NULL,document_id uuid NOT NULL,processing_run_id uuid NOT NULL,
      document_page_id uuid NOT NULL,role text NOT NULL CHECK(role IN
        ('NATIVE_POSITIONED_TEXT','OCR_TEXT','POSITIONED_READINGS','NATIVE_ORIGINS','OCR_INPUT_IMAGE','SPATIAL_LAYOUT')),
      storage_key text NOT NULL UNIQUE,mime_type text NOT NULL,
      size_bytes integer NOT NULL CHECK(size_bytes>=0 AND size_bytes<=33554432),
      sha256 text NOT NULL CHECK(sha256 ~ '^[a-f0-9]{64}$'),width_px integer,height_px integer,
      CHECK((role='OCR_INPUT_IMAGE' AND width_px>0 AND height_px>0 AND
        width_px::bigint*height_px<=20000000 AND mime_type='image/png') OR
        (role<>'OCR_INPUT_IMAGE' AND width_px IS NULL AND height_px IS NULL)),
      FOREIGN KEY(result_id,document_id,processing_run_id,document_page_id)
        REFERENCES
          source_enrichment_page_results(id,document_id,processing_run_id,document_page_id));
    CREATE TABLE run_source_enrichment_bindings (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),created_at timestamptz NOT NULL DEFAULT now(),
      run_id uuid NOT NULL,document_id uuid NOT NULL,processing_run_id uuid NOT NULL,
      document_page_id uuid NOT NULL,prepared_result_id uuid NOT NULL,manifest_hash text NOT NULL,
      UNIQUE(run_id,document_page_id),
      FOREIGN KEY(run_id,document_id,processing_run_id) REFERENCES
        extraction_runs(id,document_id,processing_run_id),
      FOREIGN KEY(prepared_result_id,document_id,processing_run_id,document_page_id)
        REFERENCES
          source_enrichment_page_results(id,document_id,processing_run_id,document_page_id));

    CREATE FUNCTION source_json_canonical(v jsonb) RETURNS text LANGUAGE plpgsql IMMUTABLE AS $$
    DECLARE answer text;
    BEGIN
      IF jsonb_typeof(v)='object' THEN
        SELECT '{'||coalesce(string_agg(to_jsonb(key)::text||':'||source_json_canonical(value),
          ',' ORDER BY key COLLATE "C"),'')||'}' INTO answer FROM jsonb_each(v);
      ELSIF jsonb_typeof(v)='array' THEN
        SELECT '['||coalesce(string_agg(source_json_canonical(value),',' ORDER BY ord),'')||']'
          INTO answer FROM jsonb_array_elements(v) WITH ORDINALITY t(value,ord);
      ELSE answer:=v::text; END IF;
      RETURN answer;
    END $$;

    CREATE FUNCTION source_enrichment_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE result source_enrichment_page_results; unit extraction_work_units; run extraction_runs;
      a jsonb; page_number integer; supplied text; descriptor_count integer;
    BEGIN
      IF TG_TABLE_NAME='extraction_runs' THEN
        IF NEW.reextracts_run_id IS NOT NULL AND NOT EXISTS(
          SELECT 1 FROM extraction_runs r WHERE r.id=NEW.reextracts_run_id AND
            r.execution_purpose=NEW.execution_purpose) THEN
          RAISE EXCEPTION 'Run ancestry must have the same execution purpose'; END IF;
        RETURN NEW;
      END IF;
      IF TG_TABLE_NAME='extraction_work_units' THEN
        SELECT * INTO run FROM extraction_runs WHERE id=NEW.run_id;
        IF run.execution_purpose<>'SOURCE_ENRICHMENT' THEN RETURN NEW; END IF;
        IF NEW.stage<>'SOURCE_PREPARE' OR jsonb_array_length(NEW.page_numbers)<>1 THEN
          RAISE EXCEPTION 'Invalid local preparation plan'; END IF;
        IF TG_OP='INSERT' AND NEW.retry_of_work_unit_id IS NOT NULL AND NOT EXISTS(
          SELECT 1 FROM extraction_work_units p WHERE p.id=NEW.retry_of_work_unit_id
            AND p.execution_metadata=NEW.execution_metadata) THEN
          RAISE EXCEPTION 'Local retries must retain source configuration'; END IF;
        IF NEW.status='COMPLETED' THEN
          SELECT * INTO result FROM source_enrichment_page_results WHERE work_unit_id=NEW.id;
          IF NOT FOUND THEN RAISE EXCEPTION 'Local completion requires a committed
            source result'; END IF;
          descriptor_count:=0;
          FOR a IN SELECT value FROM jsonb_array_elements(result.manifest->'derived_images')
            UNION ALL SELECT value->'text_artifact' FROM
              jsonb_array_elements(result.manifest->'representations')
            UNION ALL SELECT value->'geometry_artifact' FROM
              jsonb_array_elements(result.manifest->'representations') LOOP
            descriptor_count:=descriptor_count+1;
            IF NOT EXISTS(SELECT 1 FROM source_enrichment_artifacts s WHERE s.id=(a->>'id')::uuid
              AND s.result_id=result.id AND s.sha256=a->>'sha256' AND
                s.size_bytes=(a->>'size_bytes')::int
              AND s.role=a->>'role' AND s.width_px IS NOT DISTINCT FROM (a->>'width_px')::int
              AND s.height_px IS NOT DISTINCT FROM (a->>'height_px')::int) THEN
              RAISE EXCEPTION 'Committed artifact differs from pinned descriptor'; END IF;
          END LOOP;
          IF descriptor_count<>(SELECT count(*) FROM source_enrichment_artifacts WHERE
            result_id=result.id) THEN
            RAISE EXCEPTION 'Unselected source artifacts'; END IF;
        END IF;
        RETURN NEW;
      END IF;
      IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Source enrichment history is immutable'; END IF;
      IF TG_TABLE_NAME='source_enrichment_artifacts' THEN
        SELECT * INTO result FROM source_enrichment_page_results WHERE id=NEW.result_id;
        SELECT * INTO unit FROM extraction_work_units WHERE id=result.work_unit_id FOR UPDATE;
      ELSIF TG_TABLE_NAME='source_enrichment_page_results' THEN
        SELECT * INTO unit FROM extraction_work_units WHERE id=NEW.work_unit_id FOR UPDATE;
        SELECT dp.page_number INTO page_number FROM document_pages dp WHERE
          dp.id=NEW.document_page_id;
        IF NOT coalesce(unit.page_numbers @> to_jsonb(ARRAY[page_number]),false)
          OR NEW.manifest->>'version' IS DISTINCT FROM 'prepared-source-page-v1'
          OR NEW.manifest->>'id' IS DISTINCT FROM NEW.id::text
          OR NEW.manifest->>'producer_run_id' IS DISTINCT FROM NEW.run_id::text
          OR NEW.manifest->>'producer_work_unit_id' IS DISTINCT FROM NEW.work_unit_id::text
          OR NEW.manifest->'owner'->>'document_id' IS DISTINCT FROM NEW.document_id::text
          OR NEW.manifest->'owner'->>'processing_run_id' IS DISTINCT FROM
            NEW.processing_run_id::text
          OR NEW.manifest->'owner'->>'document_page_id' IS DISTINCT FROM NEW.document_page_id::text
          OR NEW.manifest->'owner'->>'page_number' IS DISTINCT FROM page_number::text
          OR NEW.manifest->>'preparation_sha256' IS DISTINCT FROM NEW.preparation_hash
          OR NEW.preparation_hash IS DISTINCT FROM unit.execution_metadata->>'preparation_hash' THEN
          RAISE EXCEPTION 'Source manifest producer/page mismatch'; END IF;
        IF jsonb_typeof(NEW.manifest->'base_artifacts') IS DISTINCT FROM 'array'
          OR jsonb_typeof(NEW.manifest->'representations') IS DISTINCT FROM 'array'
          OR jsonb_typeof(NEW.manifest->'derived_images') IS DISTINCT FROM 'array'
          OR encode(digest(convert_to(source_json_canonical(NEW.manifest),'UTF8'),'sha256'),'hex')
             <>NEW.manifest_hash THEN
          RAISE EXCEPTION 'Invalid source manifest shape/hash'; END IF;
        IF
          jsonb_array_length(NEW.manifest->'base_artifacts')<>jsonb_array_length(unit.input_artifact_ids)
          OR NOT EXISTS(SELECT 1 FROM documents d WHERE d.id=NEW.document_id
            AND NEW.manifest->'original'->>'document_id'=d.id::text
            AND NEW.manifest->'original'->>'sha256'=d.sha256
            AND (NEW.manifest->'original'->>'size_bytes')::bigint=d.size_bytes) THEN
          RAISE EXCEPTION 'Source original/base set differs from admission'; END IF;
        FOR a IN SELECT value FROM jsonb_array_elements(NEW.manifest->'base_artifacts') LOOP
          IF NOT EXISTS(SELECT 1 FROM page_artifacts pa WHERE pa.id=(a->>'id')::uuid
            AND pa.document_page_id=NEW.document_page_id AND
              pa.processing_run_id=NEW.processing_run_id
            AND pa.sha256=a->>'sha256' AND pa.size_bytes=(a->>'size_bytes')::int
            AND pa.artifact_type::text=a->>'role'
            AND unit.input_artifact_ids @> to_jsonb(ARRAY[pa.id::text])) THEN
            RAISE EXCEPTION 'Source base artifact mismatch'; END IF;
        END LOOP;
      ELSIF TG_TABLE_NAME='run_source_enrichment_bindings' THEN
        SELECT * INTO result FROM source_enrichment_page_results WHERE id=NEW.prepared_result_id;
        IF result.manifest_hash<>NEW.manifest_hash OR NOT EXISTS(SELECT 1 FROM
          extraction_work_units WHERE id=result.work_unit_id AND status='COMPLETED')
          THEN
          RAISE EXCEPTION 'Binding requires exact successful source'; END IF;
        SELECT * INTO run FROM extraction_runs WHERE id=NEW.run_id FOR UPDATE;
        IF run.status<>'PENDING' OR NOT run.selected_pages @>
          to_jsonb(ARRAY[(result.manifest->'owner'->>'page_number')::int]) THEN
          RAISE EXCEPTION 'Bindings must be pinned before execution'; END IF;
        RETURN NEW;
      ELSE
        SELECT * INTO run FROM extraction_runs WHERE id=NEW.run_id;
        IF run.execution_purpose<>'EXTRACTION' THEN RAISE EXCEPTION 'Local jobs cannot
          publish extraction outputs or AI calls'; END IF;
        RETURN NEW;
      END IF;
      SELECT * INTO run FROM extraction_runs WHERE id=unit.run_id;
      supplied:=current_setting('powerforge.extraction_lease_token',true);
      IF run.execution_purpose<>'SOURCE_ENRICHMENT' OR run.status<>'RUNNING' OR
        unit.status<>'RUNNING'
        OR unit.lease_expires_at<=clock_timestamp() OR NOT EXISTS(
          SELECT 1 FROM extraction_unit_execution c JOIN extraction_run_execution e ON
            e.run_id=c.run_id
          WHERE c.work_unit_id=unit.id AND c.token::text=supplied AND
            c.hard_deadline_at>clock_timestamp()
          AND e.cancel_requested_at IS NULL) THEN
        RAISE EXCEPTION 'Source publication requires an authorized local lease'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER source_enrichment_guard BEFORE INSERT OR UPDATE ON extraction_runs
      FOR EACH ROW EXECUTE FUNCTION source_enrichment_guard();
    CREATE TRIGGER source_enrichment_guard BEFORE INSERT OR UPDATE ON extraction_work_units
      FOR EACH ROW EXECUTE FUNCTION source_enrichment_guard();
    """)
    for table in (
        "source_enrichment_page_results",
        "source_enrichment_artifacts",
        "run_source_enrichment_bindings",
        "extraction_source_groups",
        "extracted_tables",
        "extraction_evidence",
        "extraction_candidates",
        "candidate_evidence",
        "extraction_ai_calls",
    ):
        op.execute(
            f"CREATE TRIGGER source_enrichment_guard BEFORE INSERT OR UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION source_enrichment_guard()"
        )


def downgrade():
    op.execute(
        """
        DO $$ BEGIN IF EXISTS(SELECT 1 FROM extraction_runs WHERE
        execution_purpose='SOURCE_ENRICHMENT') THEN RAISE EXCEPTION 'Cannot discard
        source enrichment history'; END IF; END $$;
        """
    )
    for table in (
        "extraction_runs",
        "extraction_work_units",
        "source_enrichment_page_results",
        "source_enrichment_artifacts",
        "run_source_enrichment_bindings",
        "extraction_source_groups",
        "extracted_tables",
        "extraction_evidence",
        "extraction_candidates",
        "candidate_evidence",
        "extraction_ai_calls",
    ):
        op.execute(f"DROP TRIGGER source_enrichment_guard ON {table}")
    op.execute("DROP FUNCTION source_enrichment_guard()")
    op.execute("DROP FUNCTION source_json_canonical(jsonb)")
    op.execute(
        "DROP TABLE run_source_enrichment_bindings; DROP TABLE source_enrichment_artifacts; "
        "DROP TABLE source_enrichment_page_results;"
    )
    op.execute(
        "ALTER TABLE extraction_runs DROP CONSTRAINT ck_extraction_purpose_metadata; "
        "ALTER TABLE extraction_runs DROP COLUMN execution_purpose;"
    )
    for column in ("registry_version", "model", "prompt_version", "prompt_hash"):
        op.execute(f"ALTER TABLE extraction_runs ALTER COLUMN {column} SET NOT NULL")
