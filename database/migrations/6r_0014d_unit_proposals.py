"""Preserve validated and unverified extracted unit proposals alongside the literal unit."""

from alembic import op

revision = "6r_0014d_unit_proposals"
down_revision = "6r_0014c_quality"


def upgrade() -> None:
    op.execute("""
    ALTER TABLE extraction_candidates DROP CONSTRAINT ck_extraction_candidate_shape;
    ALTER TABLE extraction_candidates ADD CONSTRAINT ck_extraction_candidate_shape
        CHECK (
            (kind='EQUIPMENT' AND source_description IS NOT NULL
                AND tag_state IS NOT NULL AND qualification IS NOT NULL
                AND (registry_type IS NOT NULL)=(mapping_status='MAPPED')
                AND mapping_status<>'INVALID'
                AND equipment_id IS NULL AND num_nonnulls(association,claimed_owner_ref,
                    raw_unmapped,raw_label,raw_value,raw_unit,qualifiers,value_form,
                    proposed_attribute_key,proposed_enum_value,attribute_origin,proposed_value,proposed_unit,
                    inference_explanation,inference_basis)=0)
            OR
            (kind='ATTRIBUTE' AND num_nonnulls(source_description,registry_type,tag,tag_state,
                qualification,raw_qualification)=0
                AND association IS NOT NULL AND (association='UNASSIGNED')=(equipment_id IS NULL)
                AND raw_unmapped IS NOT NULL
                AND (raw_unmapped OR proposed_attribute_key IS NOT NULL)
                AND (NOT raw_unmapped OR (raw_label IS NOT NULL AND proposed_attribute_key IS NULL
                    AND proposed_enum_value IS NULL AND proposed_unit IS NULL
                    AND mapping_status='UNMAPPED'))
                AND (
                    (COALESCE(attribute_origin,'EXTRACTED')='EXTRACTED'
                        AND raw_value IS NOT NULL AND qualifiers IS NOT NULL
                        AND jsonb_typeof(qualifiers)='array'
                        AND jsonb_array_length(qualifiers)<=8 AND value_form IS NOT NULL
                        AND num_nonnulls(proposed_value,inference_explanation,
                            inference_basis)=0)
                    OR
                    (attribute_origin IS NOT DISTINCT FROM 'INFERRED'
                        AND NOT raw_unmapped AND proposed_value IS NOT NULL
                        AND char_length(proposed_value) BETWEEN 1 AND 2048
                        AND inference_explanation IS NOT NULL
                        AND char_length(btrim(inference_explanation)) BETWEEN 1 AND 512
                        AND (inference_basis IS NULL OR inference_basis IN
                            ('DOCUMENT_CONTEXT','EQUIPMENT_CHARACTERISTICS','ENGINEERING_KNOWLEDGE'))
                        AND num_nonnulls(raw_label,raw_value,raw_unit,qualifiers,
                            value_form,proposed_enum_value)=0
                        AND value_source_support IS NOT DISTINCT FROM 'UNVERIFIED')
                ))
        );

    CREATE OR REPLACE FUNCTION extraction_candidate_guard() RETURNS trigger LANGUAGE plpgsql AS $$
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
            IF (NEW.attribute_origin,NEW.proposed_value,NEW.proposed_unit,
                NEW.inference_explanation,NEW.inference_basis) IS DISTINCT FROM
                (CASE WHEN s.payload->>'version'
                    IN ('phase-6r-attributes-v2','phase-6r-attributes-v3','phase-6r-attributes-v4')
                    THEN CASE WHEN assertion ? 'attribute_key' THEN assertion->>'origin'
                        ELSE 'EXTRACTED' END END,
                 assertion->>'proposed_value',assertion->>'proposed_unit',
                 assertion->>'inference_explanation',assertion->>'inference_basis')
                OR s.payload->>'version' IN
                    ('phase-6r-attributes-v2','phase-6r-attributes-v3','phase-6r-attributes-v4')
                   AND NEW.attribute_origin IS NULL
                OR s.payload->>'version'='phase-6r-attributes-v4' AND assertion ? 'attribute_key'
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
