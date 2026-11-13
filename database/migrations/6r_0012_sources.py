"""Phase 6R clean-install sources schema."""

from alembic import op

revision = "6r_0012_sources"
down_revision = "6r_0011_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(r"""
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

""")
    op.execute(r"""
    ALTER TABLE extraction_runs DROP CONSTRAINT ck_extraction_purpose_metadata;
    ALTER TABLE extraction_runs ADD CONSTRAINT ck_extraction_purpose_metadata CHECK (
      (execution_purpose='EXTRACTION' AND profile_version='phase-6r-profile-v1'
       AND stages='["EQUIPMENT_RECOGNITION","ATTRIBUTE_EXTRACTION"]'::jsonb
       AND registry_version IS NOT NULL AND model IS NOT NULL
       AND prompt_version IS NOT NULL AND prompt_hash IS NOT NULL) OR
      (execution_purpose='SOURCE_ENRICHMENT' AND registry_version IS NULL AND model IS NULL
       AND prompt_version IS NULL AND prompt_hash IS NULL AND provider='local'
       AND context_revision_id IS NULL AND
         ((stages='["SOURCE_PREPARE"]'::jsonb AND profile_version<>'source-layout-profile-v1') OR
           (profile_version='source-layout-profile-v1'
             AND stages='["SOURCE_PREPARE","SPATIAL_LAYOUT"]'::jsonb))));
    CREATE INDEX ix_source_prepared_compatible ON source_enrichment_page_results
      (document_id,processing_run_id,document_page_id,preparation_hash,created_at,id);
    CREATE TABLE source_preparation_receipts (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),created_at timestamptz NOT NULL DEFAULT now(),
      run_id uuid NOT NULL,document_id uuid NOT NULL,processing_run_id uuid NOT NULL,
      work_unit_id uuid NOT NULL UNIQUE,document_page_id uuid NOT NULL,
      prepared_result_id uuid NOT NULL,preparation_hash text NOT NULL,manifest_hash text NOT NULL,
      UNIQUE(id,run_id,document_id),
      FOREIGN KEY(work_unit_id,run_id,document_id,processing_run_id)
        REFERENCES extraction_work_units(id,run_id,document_id,processing_run_id),
      FOREIGN KEY(prepared_result_id,document_id,processing_run_id,document_page_id)
        REFERENCES source_enrichment_page_results
          (id,document_id,processing_run_id,document_page_id));
    CREATE INDEX ix_source_preparation_receipts_run_unit ON source_preparation_receipts
      (run_id,work_unit_id);
    CREATE TABLE source_spatial_results (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),created_at timestamptz NOT NULL DEFAULT now(),
      run_id uuid NOT NULL,document_id uuid NOT NULL,processing_run_id uuid NOT NULL,
      work_unit_id uuid NOT NULL UNIQUE,document_page_id uuid NOT NULL,
      prepared_result_id uuid NOT NULL,layout_hash text NOT NULL,manifest_hash text NOT NULL,
      manifest jsonb NOT NULL CHECK(jsonb_typeof(manifest)='object'
        AND octet_length(manifest::text)<=4194304),storage_key text NOT NULL UNIQUE,
      size_bytes integer NOT NULL CHECK(size_bytes>0 AND size_bytes<=4194304),
      usage jsonb NOT NULL CHECK(jsonb_typeof(usage)='object' AND octet_length(usage::text)<=16000),
      UNIQUE(id,run_id,document_id),
      FOREIGN KEY(work_unit_id,run_id,document_id,processing_run_id)
        REFERENCES extraction_work_units(id,run_id,document_id,processing_run_id),
      FOREIGN KEY(prepared_result_id,document_id,processing_run_id,document_page_id)
        REFERENCES source_enrichment_page_results
          (id,document_id,processing_run_id,document_page_id));
    CREATE INDEX ix_source_spatial_results_run_unit ON source_spatial_results(run_id,work_unit_id);
    CREATE FUNCTION source_spatial_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE u extraction_work_units; r extraction_runs; p source_enrichment_page_results;
      ancestor uuid; expected_hash text; config jsonb;
    BEGIN
      IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Spatial source history is immutable'; END IF;
      SELECT * INTO u FROM extraction_work_units WHERE id=NEW.work_unit_id FOR UPDATE;
      SELECT * INTO r FROM extraction_runs WHERE id=u.run_id;
      IF r.execution_purpose IS DISTINCT FROM 'SOURCE_ENRICHMENT'
        OR r.profile_version IS DISTINCT FROM 'source-layout-profile-v1'
        OR u.status IS DISTINCT FROM 'RUNNING' OR r.status IS DISTINCT FROM 'RUNNING' THEN
        RAISE EXCEPTION 'Spatial output requires a running source layout producer'; END IF;
      SELECT * INTO p FROM source_enrichment_page_results WHERE id=NEW.prepared_result_id;
      IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM extraction_work_units ok
        JOIN extraction_runs original ON original.id=ok.run_id WHERE ok.id=p.work_unit_id
        AND ok.status='COMPLETED' AND ok.stage='SOURCE_PREPARE'
        AND original.execution_purpose='SOURCE_ENRICHMENT')
        OR p.document_id<>NEW.document_id OR p.processing_run_id<>NEW.processing_run_id
        OR p.document_page_id<>NEW.document_page_id
        OR NOT u.page_numbers @> to_jsonb(ARRAY[(p.manifest->'owner'->>'page_number')::int]) THEN
        RAISE EXCEPTION 'Spatial prerequisite must be an exact successful original preparation';
      END IF;
      IF TG_TABLE_NAME='source_preparation_receipts' THEN
        IF u.stage<>'SOURCE_PREPARE' OR NEW.manifest_hash<>p.manifest_hash
          OR NEW.preparation_hash<>p.preparation_hash
          OR u.execution_metadata->>'preparation_hash' IS DISTINCT FROM p.preparation_hash
          OR u.execution_metadata->>'reuse_result_id' IS DISTINCT FROM p.id::text
          OR u.execution_metadata->>'reuse_manifest_hash' IS DISTINCT FROM p.manifest_hash
          OR EXISTS(SELECT 1 FROM source_enrichment_page_results s WHERE s.work_unit_id=u.id) THEN
          RAISE EXCEPTION 'Receipt must retain its exact original producer/configuration'; END IF;
      ELSE
        SELECT coalesce(s.id,c.prepared_result_id) INTO ancestor FROM extraction_work_units parent
          LEFT JOIN source_enrichment_page_results s ON s.work_unit_id=parent.id
          LEFT JOIN source_preparation_receipts c ON c.work_unit_id=parent.id
          WHERE parent.run_id=u.run_id AND parent.unit_key=u.execution_metadata->>'prerequisite_key'
            AND parent.status='COMPLETED' AND parent.stage='SOURCE_PREPARE'
            AND parent.page_numbers=u.page_numbers
            AND parent.input_artifact_ids=u.input_artifact_ids;
        SELECT configuration INTO config FROM extraction_run_execution WHERE run_id=u.run_id;
        expected_hash:=encode(digest(convert_to(source_json_canonical(NEW.manifest),'UTF8'),
          'sha256'),'hex');
        IF u.stage<>'SPATIAL_LAYOUT' OR ancestor IS DISTINCT FROM p.id
          OR NEW.layout_hash IS DISTINCT FROM config->>'algorithm_sha256'
          OR NEW.manifest->>'algorithm_sha256' IS DISTINCT FROM NEW.layout_hash
          OR NEW.manifest->>'version' IS DISTINCT FROM 'source-spatial-layout-v1'
          OR NEW.manifest->>'id' IS DISTINCT FROM NEW.id::text
          OR NEW.manifest->>'producer_run_id' IS DISTINCT FROM NEW.run_id::text
          OR NEW.manifest->>'producer_work_unit_id' IS DISTINCT FROM NEW.work_unit_id::text
          OR NEW.manifest->'owner' IS DISTINCT FROM p.manifest->'owner'
          OR NEW.manifest->'prepared'->>'result_kind' IS DISTINCT FROM 'PREPARED'
          OR NEW.manifest->'prepared'->>'producer_purpose' IS DISTINCT FROM 'SOURCE_ENRICHMENT'
          OR NEW.manifest->'prepared'->'owner' IS DISTINCT FROM p.manifest->'owner'
          OR NEW.manifest->'prepared'->>'id' IS DISTINCT FROM p.id::text
          OR NEW.manifest->'prepared'->>'producer_run_id' IS DISTINCT FROM p.run_id::text
          OR NEW.manifest->'prepared'->>'producer_work_unit_id'
            IS DISTINCT FROM p.work_unit_id::text
          OR NEW.manifest->'prepared'->>'manifest_sha256' IS DISTINCT FROM p.manifest_hash
          OR NEW.manifest->'prepared'->>'producer_sha256' IS DISTINCT FROM p.preparation_hash
          OR NEW.manifest->'printed_text_independently_verified' IS DISTINCT FROM 'false'::jsonb
          OR NEW.manifest_hash<>expected_hash
          OR NEW.size_bytes<>octet_length(convert_to(source_json_canonical(NEW.manifest),'UTF8'))
          OR NEW.storage_key<>
            'source-spatial/'||NEW.document_id::text||'/'||NEW.id::text||'.json' THEN
          RAISE EXCEPTION 'Spatial result differs from exact source/plan/manifest'; END IF;
      END IF;
      RETURN NEW;
    END $$;
    """)
    op.execute(r"""
CREATE OR REPLACE FUNCTION source_enrichment_guard() RETURNS trigger LANGUAGE plpgsql AS $$
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
        IF run.profile_version='source-layout-profile-v1' THEN
          IF jsonb_array_length(NEW.page_numbers)<>1
            OR NEW.stage NOT IN ('SOURCE_PREPARE','SPATIAL_LAYOUT')
            OR NEW.unit_key IS DISTINCT FROM NEW.stage||':page:'||lpad(NEW.page_numbers->>0,6,'0')
            OR NEW.execution_metadata->>'plan_hash' IS DISTINCT FROM run.profile_hash
            OR jsonb_typeof(NEW.execution_metadata->'force_ocr') IS DISTINCT FROM 'boolean'
            OR (NEW.stage='SPATIAL_LAYOUT' AND NEW.execution_metadata->>'prerequisite_key'
              IS DISTINCT FROM 'SOURCE_PREPARE:page:'||lpad(NEW.page_numbers->>0,6,'0'))
            OR (NEW.stage='SOURCE_PREPARE' AND
              NEW.execution_metadata->>'prerequisite_key' IS NOT NULL) THEN
            RAISE EXCEPTION 'Invalid fixed source layout plan'; END IF;
          IF TG_OP='INSERT' AND NEW.retry_of_work_unit_id IS NOT NULL AND NOT EXISTS(
            SELECT 1 FROM extraction_work_units p WHERE p.id=NEW.retry_of_work_unit_id
              AND p.execution_metadata=NEW.execution_metadata) THEN
            RAISE EXCEPTION 'Layout retries must retain exact source plan'; END IF;
          IF NEW.stage='SPATIAL_LAYOUT' THEN
            IF NEW.status='COMPLETED' AND NOT EXISTS(
              SELECT 1 FROM source_spatial_results s WHERE s.work_unit_id=NEW.id) THEN
              RAISE EXCEPTION 'Layout completion requires committed spatial output'; END IF;
            RETURN NEW;
          END IF;
          IF NEW.status='COMPLETED' AND EXISTS(
            SELECT 1 FROM source_preparation_receipts c WHERE c.work_unit_id=NEW.id) THEN
            IF EXISTS(SELECT 1 FROM source_enrichment_page_results p
              WHERE p.work_unit_id=NEW.id) THEN
              RAISE EXCEPTION 'Preparation cannot be both original and reused'; END IF;
            RETURN NEW;
          END IF;
        END IF;
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
""")
    op.execute(r"""
    ALTER TABLE source_enrichment_artifacts ADD CONSTRAINT uq_source_artifact_owned
      UNIQUE(id,document_id,processing_run_id,document_page_id);
    ALTER TABLE run_source_enrichment_bindings
      ADD COLUMN spatial_result_id uuid REFERENCES source_spatial_results(id),
      ADD COLUMN spatial_manifest_hash text, ADD COLUMN binding_hash text;

    ALTER TABLE run_source_enrichment_bindings
        ALTER COLUMN spatial_result_id SET NOT NULL,
        ALTER COLUMN spatial_manifest_hash SET NOT NULL,
        ALTER COLUMN binding_hash SET NOT NULL;
    CREATE FUNCTION extraction_binding_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE r extraction_runs; p source_enrichment_page_results; s source_spatial_results;
            pair jsonb; expected text;
    BEGIN

        IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Source bindings are immutable'; END IF;
        SELECT * INTO r FROM extraction_runs WHERE id=NEW.run_id FOR UPDATE;
        SELECT * INTO p FROM source_enrichment_page_results WHERE id=NEW.prepared_result_id;
        SELECT * INTO s FROM source_spatial_results WHERE id=NEW.spatial_result_id;
        pair:=jsonb_build_object('prepared',p.id::text,'prepared_hash',p.manifest_hash,
          'spatial',s.id::text,'spatial_hash',s.manifest_hash);
        expected:=encode(digest(convert_to(source_json_canonical(pair),'UTF8'),'sha256'),'hex');
        IF r.execution_purpose IS DISTINCT FROM 'EXTRACTION'
          OR r.profile_version IS DISTINCT FROM 'phase-6r-profile-v1'
          OR r.status IS DISTINCT FROM 'PENDING'
          OR NOT r.selected_pages @> to_jsonb(ARRAY[(p.manifest->'owner'->>'page_number')::int])
          OR s.id IS NULL OR s.prepared_result_id IS DISTINCT FROM p.id
          OR s.document_id IS DISTINCT FROM NEW.document_id
          OR s.processing_run_id IS DISTINCT FROM NEW.processing_run_id
          OR s.document_page_id IS DISTINCT FROM NEW.document_page_id
          OR s.manifest_hash IS DISTINCT FROM NEW.spatial_manifest_hash
          OR p.manifest_hash IS DISTINCT FROM NEW.manifest_hash
          OR NEW.binding_hash IS DISTINCT FROM expected
          OR NOT EXISTS(SELECT 1 FROM extraction_work_units ok JOIN extraction_runs original
            ON original.id=ok.run_id WHERE ok.id=s.work_unit_id AND ok.status='COMPLETED'
            AND ok.stage='SPATIAL_LAYOUT' AND original.execution_purpose='SOURCE_ENRICHMENT') THEN
          RAISE EXCEPTION 'Binding must pin exact owned successful original sources'; END IF;
        RETURN NEW;

    END $$;
    CREATE TRIGGER extraction_binding_guard BEFORE INSERT OR UPDATE OR DELETE
        ON run_source_enrichment_bindings FOR EACH ROW EXECUTE FUNCTION extraction_binding_guard();
""")
    op.execute(r"""
    CREATE TRIGGER source_enrichment_guard BEFORE INSERT OR UPDATE ON extraction_runs
        FOR EACH ROW EXECUTE FUNCTION source_enrichment_guard();
    CREATE TRIGGER source_enrichment_guard BEFORE INSERT OR UPDATE ON extraction_work_units
        FOR EACH ROW EXECUTE FUNCTION source_enrichment_guard();
    CREATE TRIGGER source_enrichment_guard BEFORE INSERT OR UPDATE OR DELETE
        ON source_enrichment_page_results FOR EACH ROW EXECUTE FUNCTION source_enrichment_guard();
    CREATE TRIGGER source_enrichment_guard BEFORE INSERT OR UPDATE OR DELETE
        ON source_enrichment_artifacts FOR EACH ROW EXECUTE FUNCTION source_enrichment_guard();
    CREATE TRIGGER source_enrichment_guard BEFORE INSERT OR UPDATE OR DELETE
        ON extraction_ai_calls FOR EACH ROW EXECUTE FUNCTION source_enrichment_guard();
    CREATE TRIGGER source_spatial_guard BEFORE INSERT OR UPDATE OR DELETE
        ON source_preparation_receipts FOR EACH ROW EXECUTE FUNCTION source_spatial_guard();
    CREATE TRIGGER source_spatial_guard BEFORE INSERT OR UPDATE OR DELETE
        ON source_spatial_results FOR EACH ROW EXECUTE FUNCTION source_spatial_guard();
    CREATE TRIGGER extraction_fence_guard BEFORE INSERT ON source_preparation_receipts
        FOR EACH ROW EXECUTE FUNCTION extraction_fence_guard();
    CREATE TRIGGER extraction_fence_guard BEFORE INSERT ON source_spatial_results
        FOR EACH ROW EXECUTE FUNCTION extraction_fence_guard();

    ALTER TABLE extraction_stage_results ADD FOREIGN KEY (run_id,document_page_id)
        REFERENCES run_source_enrichment_bindings(run_id,document_page_id);
    CREATE FUNCTION extraction_stage_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE u extraction_work_units; b run_source_enrichment_bindings;
            p extraction_stage_results; page integer; page_key text;
    BEGIN
        IF TG_TABLE_NAME='extraction_work_units' THEN
            IF NEW.stage NOT IN ('EQUIPMENT_RECOGNITION','ATTRIBUTE_EXTRACTION') THEN
                RETURN NEW;
            END IF;
            IF TG_OP='INSERT' THEN
                SELECT binding.* INTO b FROM run_source_enrichment_bindings binding
                    WHERE binding.run_id=NEW.run_id
                    AND binding.document_page_id::text=NEW.execution_metadata->>'source_page_id';
                SELECT page_number INTO page FROM document_pages WHERE id=b.document_page_id;
                page_key := ':page:'||lpad(page::text,6,'0');
                IF page IS NULL OR NEW.page_numbers IS DISTINCT FROM to_jsonb(ARRAY[page])
                    OR NEW.unit_key IS DISTINCT FROM NEW.stage||page_key
                    OR NEW.execution_metadata->>'binding_hash' IS DISTINCT FROM b.binding_hash
                    OR NEW.execution_metadata->>'prerequisite_key' IS DISTINCT FROM
                        (CASE WHEN NEW.stage='ATTRIBUTE_EXTRACTION'
                              THEN 'EQUIPMENT_RECOGNITION'||page_key ELSE NULL END)
                    OR (NEW.retry_of_work_unit_id IS NOT NULL AND NOT EXISTS (
                        SELECT 1 FROM extraction_work_units previous
                        WHERE previous.id=NEW.retry_of_work_unit_id
                        AND previous.execution_metadata=NEW.execution_metadata
                    ))
                THEN RAISE EXCEPTION 'AI work unit requires its exact pinned page plan'; END IF;
            ELSIF NEW.status='COMPLETED' AND NOT EXISTS (
                SELECT 1 FROM extraction_stage_results WHERE work_unit_id=NEW.id
            ) THEN RAISE EXCEPTION 'AI stage completion requires a committed result'; END IF;
            RETURN NEW;
        END IF;
        IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Stage results are immutable'; END IF;
        SELECT * INTO u FROM extraction_work_units WHERE id=NEW.work_unit_id;
        SELECT * INTO b FROM run_source_enrichment_bindings
            WHERE run_id=NEW.run_id AND document_page_id=NEW.document_page_id;
        IF u.run_id IS DISTINCT FROM NEW.run_id OR u.stage IS DISTINCT FROM NEW.stage
            OR u.execution_metadata->>'source_page_id' IS DISTINCT FROM NEW.document_page_id::text
            OR u.execution_metadata->>'binding_hash' IS DISTINCT FROM b.binding_hash
            OR NEW.payload->>'stage' IS DISTINCT FROM NEW.stage
            OR NEW.payload->>'page_context_hash' IS DISTINCT FROM NEW.page_context_hash
            OR NEW.result_hash <> encode(
                digest(convert_to(source_json_canonical(NEW.payload),'UTF8'),'sha256'),'hex')
        THEN RAISE EXCEPTION 'Stage result differs from its pinned work unit'; END IF;
        IF NEW.stage='ATTRIBUTE_EXTRACTION' THEN
            SELECT * INTO p FROM extraction_stage_results
                WHERE work_unit_id=NEW.upstream_work_unit_id;
            IF p.stage IS DISTINCT FROM 'EQUIPMENT_RECOGNITION' OR NOT EXISTS(
                SELECT 1 FROM extraction_work_units WHERE id=p.work_unit_id AND status='COMPLETED'
                AND unit_key=u.execution_metadata->>'prerequisite_key'
            ) OR NEW.payload->>'upstream_hash' IS DISTINCT FROM NEW.upstream_hash
            THEN RAISE EXCEPTION 'Attribute stage requires successful pinned recognition'; END IF;
        END IF;
        IF (NEW.outcome='RESULT') IS DISTINCT FROM EXISTS(
            SELECT 1 FROM extraction_unit_execution
            WHERE work_unit_id=u.id AND provider_started_at IS NOT NULL
        ) THEN RAISE EXCEPTION 'Stage result differs from its provider call boundary'; END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER extraction_stage_guard BEFORE INSERT OR UPDATE OR DELETE
        ON extraction_stage_results FOR EACH ROW EXECUTE FUNCTION extraction_stage_guard();
    CREATE TRIGGER extraction_stage_guard BEFORE INSERT OR UPDATE ON extraction_work_units
        FOR EACH ROW EXECUTE FUNCTION extraction_stage_guard();
    CREATE FUNCTION extraction_stage_terminal_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM extraction_work_units WHERE id=NEW.work_unit_id AND status='COMPLETED'
        ) THEN RAISE EXCEPTION 'Stage output requires atomic completion'; END IF;
        RETURN NEW;
    END $$;
    CREATE CONSTRAINT TRIGGER extraction_stage_terminal_guard AFTER INSERT
        ON extraction_stage_results DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
        EXECUTE FUNCTION extraction_stage_terminal_guard();
""")


def downgrade() -> None:
    raise RuntimeError("Phase 6R uses a clean installation and backup-based recovery")
