"""Admit versioned quality-correction assertions under the immutable origin guard."""

from alembic import op

revision = "6r_0014c_quality"
down_revision = "6r_0014b_attribute_origin"


def upgrade() -> None:
    op.execute("""
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
                    IN ('phase-6r-attributes-v2','phase-6r-attributes-v3')
                    THEN CASE WHEN assertion ? 'attribute_key' THEN assertion->>'origin'
                        ELSE 'EXTRACTED' END END,
                 assertion->>'proposed_value',assertion->>'proposed_unit',
                 assertion->>'inference_explanation',assertion->>'inference_basis')
                OR s.payload->>'version' IN ('phase-6r-attributes-v2','phase-6r-attributes-v3')
                   AND NEW.attribute_origin IS NULL
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
