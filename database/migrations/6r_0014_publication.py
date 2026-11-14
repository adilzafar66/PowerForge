"""Publish immutable page-scoped candidates and evidence with the AI stage result."""

from alembic import op

revision = "6r_0014_publication"
down_revision = "6r_0013d_validation"


def upgrade() -> None:
    op.execute("""
    ALTER TABLE extraction_stage_results ADD CONSTRAINT uq_stage_publication_scope
        UNIQUE (work_unit_id, run_id, document_page_id);

    CREATE TABLE extraction_candidates (
        id uuid PRIMARY KEY,
        run_id uuid NOT NULL,
        document_page_id uuid NOT NULL,
        work_unit_id uuid NOT NULL,
        ordinal integer NOT NULL CHECK (ordinal BETWEEN 0 AND 527),
        kind text NOT NULL CHECK (kind IN ('EQUIPMENT','ATTRIBUTE')),
        local_ref text NOT NULL CHECK (local_ref ~ '^[A-Za-z0-9_-]{1,96}$'),
        mapping_status text NOT NULL CHECK (mapping_status IN ('MAPPED','UNMAPPED','INVALID')),
        reason_code text,
        conflict boolean NOT NULL DEFAULT false,
        search_terms text[] NOT NULL CHECK (cardinality(search_terms)<=7),
        source_description text,
        registry_type text,
        tag text,
        tag_state text CHECK (tag_state IN ('PRESENT','ABSENT','UNREADABLE','AMBIGUOUS')),
        qualification text CHECK (qualification IN
            ('INSTALLED','PROPOSED','FUTURE','SPARE','REFERENCE','LEGEND_ONLY','UNKNOWN')),
        raw_qualification text,
        equipment_id uuid,
        equipment_work_unit_id uuid,
        owner_kind text GENERATED ALWAYS AS ('EQUIPMENT') STORED,
        association text CHECK (association IN ('ASSERTED','UNCERTAIN','UNASSIGNED')),
        claimed_owner_ref text,
        raw_unmapped boolean,
        raw_label text,
        raw_value text,
        raw_unit text,
        qualifiers jsonb,
        value_form text CHECK (value_form IN ('SINGLE','RANGE','MULTIPLE','QUALIFIED')),
        proposed_attribute_key text,
        proposed_enum_value text,
        normalized_type text,
        normalized_unit text,
        value_number numeric,
        value_integer bigint,
        value_text text,
        value_boolean boolean,
        UNIQUE (work_unit_id, ordinal),
        UNIQUE (work_unit_id, local_ref),
        UNIQUE (id, run_id, document_page_id, work_unit_id),
        UNIQUE (id, run_id, document_page_id, work_unit_id, kind),
        FOREIGN KEY (work_unit_id, run_id, document_page_id)
            REFERENCES extraction_stage_results(work_unit_id, run_id, document_page_id),
        FOREIGN KEY (run_id, document_page_id)
            REFERENCES run_source_enrichment_bindings(run_id, document_page_id),
        FOREIGN KEY (equipment_id, run_id, document_page_id, equipment_work_unit_id, owner_kind)
            REFERENCES extraction_candidates(id, run_id, document_page_id, work_unit_id, kind),
        CHECK ((mapping_status='MAPPED') = (reason_code IS NULL)),
        CHECK (NOT conflict OR (kind='ATTRIBUTE' AND mapping_status='MAPPED')),
        CHECK ((equipment_id IS NULL) = (equipment_work_unit_id IS NULL)),
        CHECK (
            (kind='EQUIPMENT' AND source_description IS NOT NULL
                AND tag_state IS NOT NULL AND qualification IS NOT NULL
                AND (registry_type IS NOT NULL)=(mapping_status='MAPPED')
                AND mapping_status<>'INVALID'
                AND equipment_id IS NULL AND num_nonnulls(association,claimed_owner_ref,
                    raw_unmapped,raw_label,raw_value,raw_unit,qualifiers,value_form,
                    proposed_attribute_key,proposed_enum_value)=0)
            OR
            (kind='ATTRIBUTE' AND num_nonnulls(source_description,registry_type,tag,tag_state,
                qualification,raw_qualification)=0
                AND association IS NOT NULL AND (association='UNASSIGNED')=(equipment_id IS NULL)
                AND raw_value IS NOT NULL AND raw_unmapped IS NOT NULL
                AND (raw_unmapped OR proposed_attribute_key IS NOT NULL)
                AND (NOT raw_unmapped OR (raw_label IS NOT NULL AND proposed_attribute_key IS NULL
                    AND proposed_enum_value IS NULL AND mapping_status='UNMAPPED'))
                AND qualifiers IS NOT NULL AND jsonb_typeof(qualifiers)='array'
                AND jsonb_array_length(qualifiers)<=8 AND value_form IS NOT NULL)
        ),
        CHECK (
            (kind='ATTRIBUTE' AND mapping_status='MAPPED' AND equipment_id IS NOT NULL
                AND normalized_type IS NOT NULL
                AND num_nonnulls(value_number,value_integer,value_text,value_boolean)=1
                AND CASE normalized_type
                    WHEN 'NUMBER' THEN value_number IS NOT NULL AND abs(value_number)<1e270::numeric
                    WHEN 'INTEGER' THEN value_integer IS NOT NULL
                    WHEN 'TEXT' THEN value_text IS NOT NULL AND normalized_unit IS NULL
                    WHEN 'ENUM' THEN value_text IS NOT NULL AND normalized_unit IS NULL
                    WHEN 'BOOLEAN' THEN value_boolean IS NOT NULL AND normalized_unit IS NULL
                    ELSE false END)
            OR ((kind='EQUIPMENT' OR mapping_status<>'MAPPED') AND
                num_nonnulls(normalized_type,normalized_unit,value_number,
                    value_integer,value_text,value_boolean)=0)
        )
    );
    CREATE INDEX ix_extraction_candidate_run_page
        ON extraction_candidates(run_id, document_page_id, id);
    CREATE INDEX ix_extraction_candidate_run_owner
        ON extraction_candidates(run_id, equipment_id, id);

    CREATE FUNCTION extraction_region_valid(v jsonb) RETURNS boolean
    LANGUAGE plpgsql IMMUTABLE AS $$
    DECLARE x numeric; y numeric; w numeric; h numeric;
    BEGIN
        IF jsonb_typeof(v) IS DISTINCT FROM 'object' OR NOT v ?& ARRAY['x','y','width','height']
            OR v - ARRAY['x','y','width','height'] <> '{}'::jsonb
        THEN RETURN false; END IF;
        x := (v->>'x')::numeric; y := (v->>'y')::numeric;
        w := (v->>'width')::numeric; h := (v->>'height')::numeric;
        RETURN coalesce(x>=0 AND y>=0 AND w>0 AND h>0 AND x+w<=1 AND y+h<=1, false);
    EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN
        RETURN false;
    END $$;

    CREATE TABLE extraction_evidence (
        id uuid PRIMARY KEY,
        candidate_id uuid NOT NULL,
        run_id uuid NOT NULL,
        document_page_id uuid NOT NULL,
        work_unit_id uuid NOT NULL,
        ordinal integer NOT NULL CHECK (ordinal BETWEEN 0 AND 11),
        role text NOT NULL CHECK (role IN
            ('EQUIPMENT','TAG','LABEL','HEADER','VALUE','UNIT','QUALIFIER','CONTEXT')),
        page_image_id uuid NOT NULL REFERENCES page_artifacts(id),
        localization text NOT NULL
            CHECK (localization IN ('RESOLVED','VISUAL_REPORTED','UNRESOLVED')),
        modality text CHECK (modality IN ('NATIVE_PDF','OCR')),
        text_artifact_id uuid REFERENCES source_enrichment_artifacts(id),
        start integer,
        "end" integer,
        quote text,
        regions jsonb,
        source_issues jsonb,
        region jsonb,
        reported_text text CHECK (char_length(reported_text) BETWEEN 1 AND 512),
        reason_code text,
        UNIQUE (candidate_id, ordinal),
        FOREIGN KEY (candidate_id, run_id, document_page_id, work_unit_id)
            REFERENCES extraction_candidates(id, run_id, document_page_id, work_unit_id),
        CHECK (
            (localization='RESOLVED'
                AND num_nonnulls(modality,text_artifact_id,start,"end",quote,
                    regions,source_issues)=7
                AND start>=0 AND "end">start AND "end"-start=char_length(quote)
                AND jsonb_typeof(regions)='array' AND jsonb_array_length(regions)<=32
                AND jsonb_typeof(source_issues)='array' AND jsonb_array_length(source_issues)<=7
                AND num_nonnulls(region,reported_text,reason_code)=0)
            OR (localization='VISUAL_REPORTED' AND extraction_region_valid(region)
                AND num_nonnulls(modality,text_artifact_id,start,"end",quote,regions,source_issues,
                    reason_code)=0)
            OR (localization='UNRESOLVED' AND reason_code IS NOT NULL
                AND num_nonnulls(modality,text_artifact_id,start,"end",quote,regions,source_issues,
                    region,reported_text)=0)
        )
    );

    CREATE FUNCTION extraction_candidate_assertion(
        s extraction_stage_results, assertion_index integer)
    RETURNS jsonb LANGUAGE sql IMMUTABLE AS $$
        SELECT CASE
            WHEN s.outcome<>'RESULT' THEN NULL
            WHEN s.stage='EQUIPMENT_RECOGNITION' THEN s.payload->'equipment'->assertion_index
            WHEN assertion_index < jsonb_array_length(s.payload->'attributes')
                THEN s.payload->'attributes'->assertion_index
            ELSE s.payload->'raw_unmapped'->
                (assertion_index-jsonb_array_length(s.payload->'attributes'))
        END
    $$;

    CREATE FUNCTION extraction_candidate_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE s extraction_stage_results; o extraction_candidates; assertion jsonb;
    BEGIN
        IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Published candidates are immutable'; END IF;
        SELECT * INTO s FROM extraction_stage_results WHERE work_unit_id=NEW.work_unit_id;
        assertion := extraction_candidate_assertion(s, NEW.ordinal);
        IF assertion IS NULL OR assertion->>'local_ref' IS DISTINCT FROM NEW.local_ref
            OR (s.stage='EQUIPMENT_RECOGNITION') IS DISTINCT FROM (NEW.kind='EQUIPMENT')
        THEN RAISE EXCEPTION 'Candidate requires its exact stage assertion'; END IF;
        IF NEW.kind='EQUIPMENT' THEN
            IF (NEW.source_description,NEW.registry_type,NEW.tag_state,NEW.tag,NEW.qualification,
                NEW.raw_qualification) IS DISTINCT FROM
                (assertion->>'source_description',assertion->>'registry_type',assertion->>'tag_state',
                 assertion->>'tag',assertion->>'qualification',assertion->>'raw_qualification')
            THEN RAISE EXCEPTION 'Candidate must preserve the raw equipment observation'; END IF;
        ELSE
            IF (NEW.raw_label,NEW.raw_value,NEW.raw_unit,NEW.qualifiers,NEW.value_form,
                NEW.proposed_attribute_key,NEW.proposed_enum_value,NEW.claimed_owner_ref,
                NEW.raw_unmapped) IS DISTINCT FROM
                (assertion->>'raw_label',assertion->>'raw_value',assertion->>'raw_unit',
                 assertion->'qualifiers',assertion->>'value_form',assertion->>'attribute_key',
                 assertion->>'proposed_enum_value',assertion->>'equipment_ref',
                 NOT assertion ? 'attribute_key')
            THEN RAISE EXCEPTION 'Candidate must preserve the raw attribute assertion'; END IF;
            SELECT * INTO o FROM extraction_candidates WHERE id=NEW.equipment_id;
            IF NEW.equipment_id IS NOT NULL AND (
                NEW.equipment_work_unit_id IS DISTINCT FROM s.upstream_work_unit_id
                OR o.local_ref IS DISTINCT FROM NEW.claimed_owner_ref OR o.registry_type IS NULL
                OR o.qualification='LEGEND_ONLY'
                OR assertion->>'association' IS DISTINCT FROM NEW.association)
            THEN RAISE EXCEPTION 'Attribute owner requires its exact eligible recognition result';
            END IF;
        END IF;
        RETURN NEW;
    END $$;

    CREATE FUNCTION extraction_evidence_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE src source_enrichment_page_results; c extraction_candidates;
            s extraction_stage_results; citation jsonb; a source_enrichment_artifacts;
    BEGIN
        IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Published evidence is immutable'; END IF;
        SELECT p.* INTO src FROM run_source_enrichment_bindings b
            JOIN source_enrichment_page_results p ON p.id=b.prepared_result_id
            WHERE b.run_id=NEW.run_id AND b.document_page_id=NEW.document_page_id;
        IF NOT EXISTS (
            SELECT 1 FROM jsonb_array_elements(src.manifest->'base_artifacts') d
            WHERE d->>'role'='ANALYSIS_IMAGE' AND d->>'id'=NEW.page_image_id::text
        ) THEN RAISE EXCEPTION 'Evidence requires the pinned analysis image'; END IF;
        SELECT * INTO c FROM extraction_candidates WHERE id=NEW.candidate_id;
        SELECT * INTO s FROM extraction_stage_results WHERE work_unit_id=NEW.work_unit_id;
        citation := extraction_candidate_assertion(s, c.ordinal)->'evidence'->NEW.ordinal;
        IF citation IS NULL AND (NEW.ordinal<>0 OR NEW.reason_code IS DISTINCT FROM 'NO_CITATION'
            OR NEW.role IS DISTINCT FROM (CASE c.kind
                WHEN 'EQUIPMENT' THEN 'EQUIPMENT' ELSE 'VALUE' END)
            OR jsonb_array_length(extraction_candidate_assertion(s, c.ordinal)->'evidence')<>0)
            OR citation IS NOT NULL AND (citation->>'role' IS DISTINCT FROM NEW.role
                OR NEW.reason_code IS NOT DISTINCT FROM 'NO_CITATION'
                OR NEW.localization='VISUAL_REPORTED' AND citation->>'kind'<>'VISUAL'
                OR NEW.localization='RESOLVED' AND citation->>'kind' NOT IN ('READING','QUOTE'))
            OR NEW.localization='RESOLVED' AND citation->>'kind'='QUOTE'
                AND NEW.quote IS DISTINCT FROM citation->>'quote'
            OR NEW.localization='VISUAL_REPORTED' AND (
                NEW.region IS DISTINCT FROM citation->'region'
                OR NEW.reported_text IS DISTINCT FROM citation->>'reported_text')
        THEN RAISE EXCEPTION 'Evidence must preserve the supplied fragment and its role'; END IF;
        IF NEW.localization='RESOLVED' THEN
            SELECT * INTO a FROM source_enrichment_artifacts WHERE id=NEW.text_artifact_id;
            IF a.result_id IS DISTINCT FROM src.id OR a.role IS DISTINCT FROM (
                CASE NEW.modality
                    WHEN 'NATIVE_PDF' THEN 'NATIVE_POSITIONED_TEXT' ELSE 'OCR_TEXT' END)
                OR NEW."end">a.size_bytes OR NOT EXISTS (
                    SELECT 1 FROM jsonb_array_elements(src.manifest->'representations') r
                    WHERE r->'text_artifact'->>'id'=NEW.text_artifact_id::text
                      AND r->'text_artifact'->>'sha256'=a.sha256
                )
                OR EXISTS(SELECT 1 FROM jsonb_array_elements(NEW.regions) g
                    WHERE NOT extraction_region_valid(g))
            THEN RAISE EXCEPTION 'Resolved evidence requires the exact owned text representation';
            END IF;
        END IF;
        RETURN NEW;
    END $$;

    CREATE FUNCTION extraction_publication_complete() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE expected integer;
    BEGIN
        expected := CASE WHEN NEW.outcome<>'RESULT' THEN 0
            WHEN NEW.stage='EQUIPMENT_RECOGNITION' THEN jsonb_array_length(NEW.payload->'equipment')
            ELSE jsonb_array_length(NEW.payload->'attributes')
                + jsonb_array_length(NEW.payload->'raw_unmapped') END;
        IF expected IS DISTINCT FROM (
            SELECT count(*) FROM extraction_candidates WHERE work_unit_id=NEW.work_unit_id
        ) OR EXISTS (
            SELECT 1 FROM extraction_candidates c WHERE c.work_unit_id=NEW.work_unit_id
            AND greatest(1, jsonb_array_length(
                extraction_candidate_assertion(NEW,c.ordinal)->'evidence'))
                <> (SELECT count(*) FROM extraction_evidence e WHERE e.candidate_id=c.id)
        ) THEN
            RAISE EXCEPTION 'Stage result requires atomic candidate and evidence publication';
        END IF;
        RETURN NEW;
    END $$;

    CREATE TRIGGER extraction_candidate_guard BEFORE INSERT OR UPDATE OR DELETE
        ON extraction_candidates FOR EACH ROW EXECUTE FUNCTION extraction_candidate_guard();
    CREATE TRIGGER extraction_evidence_guard BEFORE INSERT OR UPDATE OR DELETE
        ON extraction_evidence FOR EACH ROW EXECUTE FUNCTION extraction_evidence_guard();
    CREATE TRIGGER extraction_fence_guard BEFORE INSERT
        ON extraction_candidates FOR EACH ROW EXECUTE FUNCTION extraction_fence_guard();
    CREATE TRIGGER extraction_fence_guard BEFORE INSERT
        ON extraction_evidence FOR EACH ROW EXECUTE FUNCTION extraction_fence_guard();
    CREATE CONSTRAINT TRIGGER extraction_publication_complete AFTER INSERT
        ON extraction_stage_results DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
        EXECUTE FUNCTION extraction_publication_complete();
    """)


def downgrade() -> None:
    raise RuntimeError("Phase 6R uses a clean installation and backup-based recovery")
