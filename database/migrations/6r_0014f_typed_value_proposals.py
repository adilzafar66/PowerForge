"""Persist v6 proposals as typed JSONB while preserving historical assertions."""

from alembic import op

revision = "6r_0014f_typed_value_proposals"
down_revision = "6r_0014e_response_audit"


def upgrade() -> None:
    op.execute(r"""
    ALTER TABLE extraction_candidates
        DROP CONSTRAINT ck_extraction_candidate_shape,
        DROP CONSTRAINT extraction_candidates_value_form_check;
    -- ALTER COLUMN USING converts historical text to JSON strings, including
    -- strings that resemble numbers or booleans. SQL NULL stays SQL NULL.
    ALTER TABLE extraction_candidates
        ALTER COLUMN proposed_value TYPE jsonb USING to_jsonb(proposed_value),
        ADD COLUMN alternate_representations jsonb;
    CREATE FUNCTION extraction_alternate_representations_valid(alternates jsonb)
    RETURNS boolean LANGUAGE sql IMMUTABLE AS $$
        SELECT CASE
            WHEN alternates IS NULL THEN true
            WHEN jsonb_typeof(alternates) <> 'array' THEN false
            ELSE jsonb_array_length(alternates)<=4 AND NOT EXISTS (
                SELECT 1 FROM jsonb_array_elements(alternates) AS a(item)
                WHERE jsonb_typeof(item) <> 'object'
                    OR jsonb_typeof(item->'value') IS DISTINCT FROM 'string'
                    OR jsonb_typeof(item->'unit') IS DISTINCT FROM 'string'
                    OR CASE WHEN jsonb_typeof(item)='object'
                        THEN item - ARRAY['value','unit'] <> '{}'::jsonb ELSE true END
                    OR char_length(item->>'value') > 128
                    OR item->>'value' !~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
                    OR char_length(item->>'unit') > 256
                    OR item->>'unit' !~ '[^[:space:]]'
            )
        END
    $$;

    ALTER TABLE extraction_candidates
        ADD CONSTRAINT extraction_candidates_value_form_check CHECK (
            value_form IN ('SINGLE','RANGE','MULTIPLE','QUALIFIED','EQUIVALENT_UNITS')),
        ADD CONSTRAINT ck_extraction_candidate_proposal CHECK (
            CASE jsonb_typeof(proposed_value)
                WHEN 'string' THEN char_length(proposed_value #>> '{}') BETWEEN 1 AND 2048
                WHEN 'number' THEN proposed_value::text ~ '^-?[0-9]+$'
                WHEN 'boolean' THEN true
                ELSE proposed_value IS NULL
            END),
        ADD CONSTRAINT ck_extraction_candidate_alternates CHECK (
            extraction_alternate_representations_valid(alternate_representations));

    ALTER TABLE extraction_candidates ADD CONSTRAINT ck_extraction_candidate_shape
        CHECK (
            (kind='EQUIPMENT' AND source_description IS NOT NULL
                AND tag_state IS NOT NULL AND qualification IS NOT NULL
                AND (registry_type IS NOT NULL)=(mapping_status='MAPPED')
                AND mapping_status<>'INVALID'
                AND equipment_id IS NULL AND num_nonnulls(association,claimed_owner_ref,
                    raw_unmapped,raw_label,raw_value,raw_unit,qualifiers,value_form,
                    proposed_attribute_key,proposed_enum_value,attribute_origin,proposed_value,proposed_unit,
                    alternate_representations,
                    inference_explanation,inference_basis)=0)
            OR
            (kind='ATTRIBUTE' AND num_nonnulls(source_description,registry_type,tag,tag_state,
                qualification,raw_qualification)=0
                AND association IS NOT NULL AND (association='UNASSIGNED')=(equipment_id IS NULL)
                AND raw_unmapped IS NOT NULL
                AND (raw_unmapped OR proposed_attribute_key IS NOT NULL)
                AND (NOT raw_unmapped OR (raw_label IS NOT NULL AND proposed_attribute_key IS NULL
                    AND num_nonnulls(proposed_enum_value, proposed_value, proposed_unit,
                        alternate_representations)=0
                    AND mapping_status='UNMAPPED'))
                AND (
                    (COALESCE(attribute_origin,'EXTRACTED')='EXTRACTED'
                        AND raw_value IS NOT NULL AND qualifiers IS NOT NULL
                        AND jsonb_typeof(qualifiers)='array'
                        AND jsonb_array_length(qualifiers)<=8 AND value_form IS NOT NULL
                        AND num_nonnulls(inference_explanation,inference_basis)=0
                        AND (alternate_representations IS NOT NULL OR proposed_value IS NULL)
                        AND (proposed_enum_value IS NULL OR alternate_representations IS NULL)
                        AND (value_form='EQUIVALENT_UNITS') = COALESCE(
                            jsonb_array_length(alternate_representations)>0, false))
                    OR
                    (attribute_origin IS NOT DISTINCT FROM 'INFERRED'
                        AND NOT raw_unmapped AND proposed_value IS NOT NULL
                        AND inference_explanation IS NOT NULL
                        AND char_length(btrim(inference_explanation)) BETWEEN 1 AND 512
                        AND (inference_basis IS NULL OR inference_basis IN
                            ('DOCUMENT_CONTEXT','EQUIPMENT_CHARACTERISTICS','ENGINEERING_KNOWLEDGE'))
                        AND num_nonnulls(raw_label,raw_value,raw_unit,qualifiers,
                            value_form,proposed_enum_value,alternate_representations)=0
                        AND value_source_support IS NOT DISTINCT FROM 'UNVERIFIED')
                ))
        );

    CREATE OR REPLACE FUNCTION extraction_stage_response_audit_required()
        RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.stage='ATTRIBUTE_EXTRACTION'
           AND NEW.payload->>'version' IS DISTINCT FROM 'phase-6r-attributes-v6'
           AND EXISTS (
            SELECT 1 FROM extraction_run_execution e WHERE e.run_id=NEW.run_id
                AND e.configuration->>'schema_version'='phase-6r-wire-v6'
        ) THEN RAISE EXCEPTION 'Stage 2 result must use the pinned typed contract'; END IF;
        IF NEW.payload->>'version' IN ('phase-6r-attributes-v5','phase-6r-attributes-v6')
           AND NEW.outcome='RESULT'
           AND EXISTS (SELECT 1 FROM extraction_runs WHERE id=NEW.run_id AND provider='openai')
           AND NOT EXISTS (
            SELECT 1 FROM extraction_response_audits a WHERE a.work_unit_id=NEW.work_unit_id
              AND a.run_id=NEW.run_id AND a.document_page_id=NEW.document_page_id
              AND a.request_hash=NEW.request_hash
              AND a.fatal_diagnostics='[]'::jsonb
              AND a.accepted=jsonb_array_length(NEW.payload->'attributes')
                + jsonb_array_length(NEW.payload->'raw_unmapped')
        ) THEN RAISE EXCEPTION 'Stage 2 publication requires its retained response audit'; END IF;
        RETURN NEW;
    END $$;
    CREATE OR REPLACE FUNCTION extraction_candidate_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE s extraction_stage_results; o extraction_candidates; assertion jsonb; typed boolean;
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
            typed := s.payload->>'version' IS NOT DISTINCT FROM 'phase-6r-attributes-v6';
            IF typed AND (
                assertion ? 'proposed_enum_value'
                OR (assertion ? 'attribute_key') IS DISTINCT FROM (assertion ? 'proposed_value')
                OR (assertion ? 'alternate_representations') IS DISTINCT FROM
                    (assertion ? 'attribute_key' AND assertion->>'origin'='EXTRACTED')
                OR (jsonb_typeof(assertion->'proposed_value')='number'
                    AND assertion->>'proposed_value' !~ '^-?[0-9]+$')
                OR (assertion ? 'alternate_representations'
                    AND jsonb_typeof(assertion->'alternate_representations') <> 'array')
            ) THEN RAISE EXCEPTION 'Stage 2 assertion violates the typed proposal contract'; END IF;
            IF (NEW.raw_label,NEW.raw_value,NEW.raw_unit,NEW.qualifiers,NEW.value_form,
                NEW.proposed_attribute_key,NEW.proposed_enum_value,NEW.claimed_owner_ref,
                NEW.raw_unmapped) IS DISTINCT FROM
                (assertion->>'raw_label',assertion->>'raw_value',assertion->>'raw_unit',
                 assertion->'qualifiers',assertion->>'value_form',assertion->>'attribute_key',
                 CASE WHEN NOT typed THEN assertion->>'proposed_enum_value' END,
                 assertion->>'equipment_ref',
                 NOT assertion ? 'attribute_key')
            THEN RAISE EXCEPTION 'Candidate must preserve the raw attribute assertion'; END IF;
            IF (NEW.attribute_origin,NEW.proposed_value,NEW.proposed_unit,
                NEW.inference_explanation,NEW.inference_basis,NEW.alternate_representations)
                IS DISTINCT FROM
                (CASE WHEN typed OR s.payload->>'version'
                    IN ('phase-6r-attributes-v2','phase-6r-attributes-v3',
                     'phase-6r-attributes-v4','phase-6r-attributes-v5')
                    THEN CASE WHEN assertion ? 'attribute_key' THEN assertion->>'origin'
                        ELSE 'EXTRACTED' END END,
                 CASE WHEN typed THEN NULLIF(assertion->'proposed_value', 'null'::jsonb)
                     ELSE to_jsonb(assertion->>'proposed_value') END,
                 assertion->>'proposed_unit',assertion->>'inference_explanation',
                 assertion->>'inference_basis',
                 CASE WHEN typed THEN assertion->'alternate_representations' END)
                OR (typed OR s.payload->>'version' IN
                    ('phase-6r-attributes-v2','phase-6r-attributes-v3',
                     'phase-6r-attributes-v4','phase-6r-attributes-v5'))
                   AND NEW.attribute_origin IS NULL
                OR (typed OR s.payload->>'version'
                    IN ('phase-6r-attributes-v4','phase-6r-attributes-v5'))
                   AND assertion ? 'attribute_key'
                   AND NOT assertion ? 'proposed_unit'
            THEN RAISE EXCEPTION 'Candidate must preserve the attribute origin and proposal';
            END IF;
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
    """)


def downgrade() -> None:
    raise RuntimeError("Phase 6R uses backup-based recovery")
