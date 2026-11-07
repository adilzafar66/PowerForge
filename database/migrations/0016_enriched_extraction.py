"""Explicit enriched bindings, v2 evidence locators and table layouts; preserve legacy rows."""

from alembic import op

revision = "0016_enriched_extraction"
down_revision = "0015_source_spatial_layout"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE source_enrichment_artifacts ADD CONSTRAINT uq_source_artifact_owned
      UNIQUE(id,document_id,processing_run_id,document_page_id);
    ALTER TABLE run_source_enrichment_bindings
      ADD COLUMN spatial_result_id uuid REFERENCES source_spatial_results(id),
      ADD COLUMN spatial_manifest_hash text, ADD COLUMN binding_hash text;
    ALTER TABLE extraction_evidence
      ADD COLUMN enrichment_artifact_id uuid, ADD COLUMN geometry_artifact_id uuid,
      ADD COLUMN source_locator jsonb;
    ALTER TABLE extraction_evidence ADD CONSTRAINT fk_evidence_enriched_text
      FOREIGN KEY(enrichment_artifact_id,document_id,processing_run_id,document_page_id)
      REFERENCES source_enrichment_artifacts(id,document_id,processing_run_id,document_page_id);
    ALTER TABLE extraction_evidence ADD CONSTRAINT fk_evidence_enriched_geometry
      FOREIGN KEY(geometry_artifact_id,document_id,processing_run_id,document_page_id)
      REFERENCES source_enrichment_artifacts(id,document_id,processing_run_id,document_page_id);
    ALTER TABLE extraction_evidence DROP CONSTRAINT ck_extraction_evidence_offsets;
    ALTER TABLE extraction_evidence ADD CONSTRAINT ck_extraction_evidence_offsets CHECK (
      (text_start IS NULL AND text_end IS NULL AND offset_convention IS NULL) OR
      (text_start IS NOT NULL AND text_end IS NOT NULL AND text_start>=0 AND text_end>text_start
       AND num_nonnulls(page_artifact_id,enrichment_artifact_id)=1
       AND offset_convention='UNICODE_CODEPOINT'));
    ALTER TABLE extraction_evidence ADD CONSTRAINT ck_evidence_enriched_locator CHECK (
      (source_locator IS NULL AND enrichment_artifact_id IS NULL AND geometry_artifact_id IS NULL)
      OR (jsonb_typeof(source_locator)='object' AND octet_length(source_locator::text)<=32768
        AND source_locator->>'version'='source-location-v2'));
    ALTER TABLE extracted_tables DROP CONSTRAINT ck_extracted_tables_layout;
    ALTER TABLE extracted_tables ADD CONSTRAINT ck_extracted_tables_layout CHECK (
      layout_schema_version IN ('table-layout-v1','table-layout-v2')
      AND jsonb_typeof(layout)='object' AND jsonb_typeof(source_locations)='array'
      AND jsonb_array_length(source_locations)>0);
    CREATE FUNCTION enriched_extraction_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE r extraction_runs; u extraction_work_units; b run_source_enrichment_bindings;
      p source_enrichment_page_results; s source_spatial_results; a source_enrichment_artifacts;
      g source_enrichment_artifacts; config jsonb; pair jsonb; wanted text; expected text;
    BEGIN
      IF TG_TABLE_NAME='run_source_enrichment_bindings' THEN
        IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Source bindings are immutable'; END IF;
        SELECT * INTO r FROM extraction_runs WHERE id=NEW.run_id;
        IF NEW.spatial_result_id IS NULL AND NEW.binding_hash IS NULL
          AND NEW.spatial_manifest_hash IS NULL THEN
          IF r.profile_version IN ('execution-profile-v5','execution-profile-v6') THEN
            RAISE EXCEPTION 'Enhanced extraction requires a complete spatial binding'; END IF;
          RETURN NEW;
        END IF;
        SELECT * INTO p FROM source_enrichment_page_results WHERE id=NEW.prepared_result_id;
        SELECT * INTO s FROM source_spatial_results WHERE id=NEW.spatial_result_id;
        pair:=jsonb_build_object('prepared',p.id::text,'prepared_hash',p.manifest_hash,
          'spatial',s.id::text,'spatial_hash',s.manifest_hash);
        expected:=encode(digest(convert_to(source_json_canonical(pair),'UTF8'),'sha256'),'hex');
        IF r.execution_purpose IS DISTINCT FROM 'EXTRACTION'
          OR r.profile_version NOT IN ('execution-profile-v5','execution-profile-v6')
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
      END IF;
      IF TG_TABLE_NAME='extraction_runs' THEN
        r:=NEW;
      ELSE
        SELECT * INTO r FROM extraction_runs WHERE id=NEW.run_id;
      END IF;
      IF TG_TABLE_NAME='extraction_evidence' THEN
        IF r.profile_version NOT IN ('execution-profile-v5','execution-profile-v6') THEN
          IF NEW.source_locator IS NOT NULL OR NEW.enrichment_artifact_id IS NOT NULL
            OR NEW.geometry_artifact_id IS NOT NULL THEN
            RAISE EXCEPTION 'Legacy extraction cannot publish enriched locators'; END IF;
          RETURN NEW;
        END IF;
        SELECT * INTO b FROM run_source_enrichment_bindings
          WHERE run_id=NEW.run_id AND document_page_id=NEW.document_page_id;
        IF b.id IS NULL OR NEW.source_locator IS NULL
          OR NEW.source_locator->>'version' IS DISTINCT FROM 'source-location-v2'
          OR NEW.source_locator->>'document_page_id' IS DISTINCT FROM NEW.document_page_id::text
          OR NEW.source_locator->>'prepared_result_id' IS DISTINCT FROM b.prepared_result_id::text
          OR NEW.source_locator->>'spatial_result_id' IS DISTINCT FROM b.spatial_result_id::text
          OR NEW.source_locator->'printed_text_independently_verified'
            IS DISTINCT FROM 'false'::jsonb
          OR NEW.source_locator->>'page_artifact_id' IS DISTINCT FROM NEW.page_artifact_id::text
          OR NEW.source_locator->>'enrichment_artifact_id'
            IS DISTINCT FROM NEW.enrichment_artifact_id::text
          OR NEW.source_locator->>'geometry_artifact_id'
            IS DISTINCT FROM NEW.geometry_artifact_id::text
          THEN RAISE EXCEPTION 'Evidence differs from its exact enriched binding'; END IF;
        IF NEW.enrichment_artifact_id IS NOT NULL THEN
          SELECT * INTO p FROM source_enrichment_page_results WHERE id=b.prepared_result_id;
          SELECT * INTO s FROM source_spatial_results WHERE id=b.spatial_result_id;
          SELECT * INTO a FROM source_enrichment_artifacts WHERE id=NEW.enrichment_artifact_id;
          SELECT * INTO g FROM source_enrichment_artifacts WHERE id=NEW.geometry_artifact_id;
          IF NEW.page_artifact_id IS NOT NULL OR a.result_id IS DISTINCT FROM b.prepared_result_id
            OR a.role NOT IN ('OCR_TEXT','NATIVE_POSITIONED_TEXT')
            OR g.result_id IS DISTINCT FROM b.prepared_result_id OR g.role<>'POSITIONED_READINGS'
            OR NEW.text_start IS NULL OR NEW.source_snippet IS NULL
            OR NEW.source_locator->>'reading_basis' IS DISTINCT FROM
              (CASE WHEN a.role='OCR_TEXT' THEN 'OCR' ELSE 'NATIVE_PDF' END)
            OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(p.manifest->'representations') d
              WHERE d->'text_artifact'->>'id'=a.id::text
                AND d->'geometry_artifact'->>'id'=g.id::text
                AND NEW.text_end<=(d->>'character_count')::int)
            OR jsonb_typeof(NEW.source_locator->'support') IS DISTINCT FROM 'array'
            OR jsonb_array_length(NEW.source_locator->'support')<>1
            OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(s.manifest->'readings') q
              WHERE q->'preferred'=NEW.source_locator->'support'->0
                AND q->'region'=NEW.source_locator->'region')
            OR NEW.source_locator->>'geometry_basis' IS DISTINCT FROM
              (CASE WHEN NEW.x IS NULL THEN 'NONE' WHEN a.role='OCR_TEXT' THEN 'OCR_ENGINE'
                ELSE 'NATIVE_DOCUMENT' END)
            THEN RAISE EXCEPTION 'Offsets require exact bound text and geometry artifacts'; END IF;
        ELSIF NEW.geometry_artifact_id IS NOT NULL OR NEW.text_start IS NOT NULL
          OR NEW.text_end IS NOT NULL OR NEW.source_snippet IS NOT NULL
          OR NEW.source_locator->>'reading_basis' IS DISTINCT FROM 'VISUAL_REPORTED'
          OR NEW.page_artifact_id IS NULL OR NOT EXISTS(SELECT 1 FROM page_artifacts pa
            WHERE pa.id=NEW.page_artifact_id AND pa.artifact_type='ANALYSIS_IMAGE') THEN
          RAISE EXCEPTION 'Visual fallback cannot claim recognized characters or geometry';
        END IF;
        IF (NEW.source_locator->'region'='null'::jsonb) IS DISTINCT FROM (NEW.x IS NULL)
          OR (NEW.x IS NOT NULL AND (
            (NEW.source_locator->'region'->>'x')::numeric IS DISTINCT FROM NEW.x OR
            (NEW.source_locator->'region'->>'y')::numeric IS DISTINCT FROM NEW.y OR
            (NEW.source_locator->'region'->>'width')::numeric IS DISTINCT FROM NEW.width OR
            (NEW.source_locator->'region'->>'height')::numeric IS DISTINCT FROM NEW.height))
          THEN RAISE EXCEPTION 'Evidence coordinates differ from explicit support'; END IF;
        IF NEW.source_locator->>'reading_basis'='VISUAL_REPORTED' AND NEW.x IS NOT NULL THEN
          RAISE EXCEPTION 'Visual fallback must retain page-level grounding'; END IF;
        IF NEW.source_kind='TABLE_CELL' AND (NEW.table_id IS NULL OR NEW.cell_id IS NULL) THEN
          RAISE EXCEPTION 'Table-cell evidence requires its table and cell'; END IF;
        IF NEW.table_id IS NULL AND NEW.enrichment_artifact_id IS NOT NULL
          AND NEW.source_locator->>'structure_basis' IS DISTINCT FROM 'UNRESOLVED' THEN
          RAISE EXCEPTION 'Text structure requires its bound table'; END IF;
        RETURN NEW;
      END IF;
      IF TG_TABLE_NAME='extracted_tables' THEN
        IF (r.profile_version IN ('execution-profile-v5','execution-profile-v6'))
          IS DISTINCT FROM (NEW.layout_schema_version='table-layout-v2') THEN
          RAISE EXCEPTION 'Table layout version differs from producing profile'; END IF;
        RETURN NEW;
      END IF;
      IF r.profile_version NOT IN ('execution-profile-v5','execution-profile-v6') THEN
        RETURN NEW; END IF;
      IF r.execution_purpose<>'EXTRACTION' OR r.stages IS DISTINCT FROM
        (CASE WHEN r.profile_version='execution-profile-v5' THEN
          '["EQUIPMENT_RECOGNITION","ATTRIBUTE_EXTRACTION"]'::jsonb ELSE
          '["TABLE_RECONSTRUCTION","TABLE_INTERPRETATION"]'::jsonb END) THEN
        RAISE EXCEPTION 'Invalid enhanced extraction stage plan'; END IF;
      IF TG_TABLE_NAME='extraction_runs' AND r.status='RUNNING' THEN
        SELECT encode(digest(convert_to(source_json_canonical(jsonb_build_object(
          'profile',r.profile_hash,'pages',r.selected_pages,'bindings',coalesce(jsonb_agg(
            jsonb_build_object('prepared',bound.prepared_result_id::text,
              'prepared_hash',bound.manifest_hash,'spatial',bound.spatial_result_id::text,
              'spatial_hash',bound.spatial_manifest_hash) ORDER BY page.page_number),'[]'::jsonb)
          )),'UTF8'),'sha256'),'hex') INTO expected
          FROM run_source_enrichment_bindings bound JOIN document_pages page
            ON page.id=bound.document_page_id WHERE bound.run_id=r.id;
        IF (SELECT count(*) FROM run_source_enrichment_bindings WHERE run_id=r.id)
            <>jsonb_array_length(r.selected_pages)
            OR expected IS DISTINCT FROM r.input_identity_hash THEN
          RAISE EXCEPTION 'All selected enrichment bindings must be pinned before admission';
        END IF;
      END IF;
      IF TG_TABLE_NAME='extraction_work_units' THEN
        u:=NEW;
        SELECT * INTO b FROM run_source_enrichment_bindings
          WHERE run_id=u.run_id
            AND document_page_id=(u.execution_metadata->>'source_page_id')::uuid;
        SELECT * INTO p FROM source_enrichment_page_results WHERE id=b.prepared_result_id;
        SELECT configuration INTO config FROM extraction_run_execution WHERE run_id=u.run_id;
        wanted:=CASE WHEN u.stage='ATTRIBUTE_EXTRACTION' THEN 'EQUIPMENT_RECOGNITION'
          WHEN u.stage='TABLE_INTERPRETATION' THEN 'TABLE_RECONSTRUCTION' ELSE NULL END;
        IF b.id IS NULL OR u.execution_metadata->>'binding_hash' IS DISTINCT FROM b.binding_hash
          OR jsonb_array_length(u.page_numbers)<>1
          OR u.page_numbers IS DISTINCT FROM
            jsonb_build_array((p.manifest->'owner'->>'page_number')::int)
          OR u.input_artifact_ids IS DISTINCT FROM
            (SELECT jsonb_agg(value->'id') FROM jsonb_array_elements(p.manifest->'base_artifacts'))
          OR u.unit_key IS DISTINCT FROM u.stage||':page:'||lpad(u.page_numbers->>0,6,'0')
          OR u.execution_metadata->>'prerequisite_key' IS DISTINCT FROM
            (CASE WHEN wanted IS NULL THEN NULL
              ELSE wanted||':page:'||lpad(u.page_numbers->>0,6,'0') END)
          OR u.execution_metadata->>'stage_manifest_version' IS DISTINCT FROM r.schema_version
          OR u.execution_metadata->'stage_identity' IS DISTINCT FROM
            (SELECT value FROM jsonb_array_elements(config->'manifest'->'stages')
              WHERE value->>'stage'=u.stage)
          OR (u.retry_of_work_unit_id IS NOT NULL AND NOT EXISTS(
            SELECT 1 FROM extraction_work_units parent WHERE id=u.retry_of_work_unit_id
              AND parent.execution_metadata=u.execution_metadata)) THEN
          RAISE EXCEPTION 'Enhanced work unit differs from its immutable bound plan'; END IF;
      END IF;
      RETURN NEW;
    END $$;
    """)
    for table in (
        "run_source_enrichment_bindings",
        "extraction_runs",
        "extraction_work_units",
        "extraction_evidence",
        "extracted_tables",
    ):
        op.execute(
            f"CREATE TRIGGER enriched_extraction_guard BEFORE INSERT OR UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION enriched_extraction_guard()"
        )


def downgrade():
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM extraction_runs WHERE profile_version IN
      ('execution-profile-v5','execution-profile-v6')) THEN
      RAISE EXCEPTION 'Cannot discard enhanced extraction history'; END IF; END $$;""")
    for table in (
        "run_source_enrichment_bindings",
        "extraction_runs",
        "extraction_work_units",
        "extraction_evidence",
        "extracted_tables",
    ):
        op.execute(f"DROP TRIGGER enriched_extraction_guard ON {table}")
    op.execute("DROP FUNCTION enriched_extraction_guard()")
    op.execute("""
    ALTER TABLE extraction_evidence DROP CONSTRAINT fk_evidence_enriched_text,
      DROP CONSTRAINT fk_evidence_enriched_geometry, DROP CONSTRAINT ck_evidence_enriched_locator,
      DROP CONSTRAINT ck_extraction_evidence_offsets, DROP COLUMN source_locator,
      DROP COLUMN enrichment_artifact_id, DROP COLUMN geometry_artifact_id;
    ALTER TABLE extraction_evidence ADD CONSTRAINT ck_extraction_evidence_offsets CHECK (
      (text_start IS NULL AND text_end IS NULL AND offset_convention IS NULL) OR
      (text_start IS NOT NULL AND text_end IS NOT NULL AND text_start>=0 AND text_end>text_start
       AND page_artifact_id IS NOT NULL AND offset_convention='UNICODE_CODEPOINT'));
    ALTER TABLE extracted_tables DROP CONSTRAINT ck_extracted_tables_layout;
    ALTER TABLE extracted_tables ADD CONSTRAINT ck_extracted_tables_layout CHECK (
      layout_schema_version='table-layout-v1' AND jsonb_typeof(layout)='object'
      AND jsonb_typeof(source_locations)='array' AND jsonb_array_length(source_locations)>0);
    ALTER TABLE run_source_enrichment_bindings DROP COLUMN spatial_result_id,
      DROP COLUMN spatial_manifest_hash, DROP COLUMN binding_hash;
    ALTER TABLE source_enrichment_artifacts DROP CONSTRAINT uq_source_artifact_owned;
    """)
