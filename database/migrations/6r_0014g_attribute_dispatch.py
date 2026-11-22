"""Bind new Stage 2 results to their dispatched server-owned request."""

from alembic import op

revision = "6r_0014g_attribute_dispatch"
down_revision = "6r_0014f_typed_value_proposals"


def upgrade() -> None:
    op.execute(r"""
    ALTER TABLE extraction_unit_execution
        ADD COLUMN provider_request_hash text CHECK (
            provider_request_hash IS NULL OR (
                provider_request_hash ~ '^[0-9a-f]{64}$' AND provider_started_at IS NOT NULL
            )
        );

    CREATE FUNCTION extraction_dispatched_request_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF OLD.provider_started_at IS NOT NULL
           AND NEW.provider_request_hash IS DISTINCT FROM OLD.provider_request_hash
        THEN RAISE EXCEPTION 'Dispatched extraction request identity is immutable'; END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER extraction_dispatched_request_immutable BEFORE UPDATE ON
        extraction_unit_execution FOR EACH ROW
        EXECUTE FUNCTION extraction_dispatched_request_immutable();

    CREATE FUNCTION extraction_response_audit_dispatch_guard()
        RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM extraction_unit_execution e WHERE e.work_unit_id=NEW.work_unit_id
                AND e.run_id=NEW.run_id AND e.provider_request_hash=NEW.request_hash
        ) THEN RAISE EXCEPTION 'Response audit differs from its dispatched request'; END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER extraction_response_audit_dispatch_guard BEFORE INSERT ON
        extraction_response_audits FOR EACH ROW
        EXECUTE FUNCTION extraction_response_audit_dispatch_guard();

    CREATE OR REPLACE FUNCTION extraction_stage_response_audit_required()
        RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.stage='ATTRIBUTE_EXTRACTION'
           AND NEW.payload->>'version' IS DISTINCT FROM 'phase-6r-attributes-v7'
        THEN RAISE EXCEPTION 'Stage 2 result must use the pinned typed contract'; END IF;
        IF NEW.stage='ATTRIBUTE_EXTRACTION' AND NEW.outcome='RESULT' AND NOT EXISTS (
            SELECT 1 FROM extraction_unit_execution e WHERE e.work_unit_id=NEW.work_unit_id
                AND e.run_id=NEW.run_id AND e.provider_started_at IS NOT NULL
                AND e.provider_request_hash=NEW.request_hash
        ) THEN RAISE EXCEPTION 'Stage 2 result differs from its dispatched request'; END IF;
        IF NEW.stage='ATTRIBUTE_EXTRACTION'
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
            IF s.payload->>'version' IS DISTINCT FROM 'phase-6r-attributes-v7'
                OR NEW.proposed_enum_value IS NOT NULL
                OR assertion ? 'proposed_enum_value'
                OR (assertion ? 'attribute_key') IS DISTINCT FROM (assertion ? 'proposed_value')
                OR (assertion ? 'alternate_representations') IS DISTINCT FROM
                    (assertion ? 'attribute_key' AND assertion->>'origin'='EXTRACTED')
                OR (jsonb_typeof(assertion->'proposed_value')='number'
                    AND assertion->>'proposed_value' !~ '^-?[0-9]+$')
                OR (assertion ? 'alternate_representations'
                    AND jsonb_typeof(assertion->'alternate_representations') <> 'array')
            THEN RAISE EXCEPTION 'Stage 2 assertion violates the typed proposal contract'; END IF;
            IF (NEW.raw_label,NEW.raw_value,NEW.raw_unit,NEW.qualifiers,NEW.value_form,
                NEW.proposed_attribute_key,NEW.claimed_owner_ref,
                NEW.raw_unmapped) IS DISTINCT FROM
                (assertion->>'raw_label',assertion->>'raw_value',assertion->>'raw_unit',
                 assertion->'qualifiers',assertion->>'value_form',assertion->>'attribute_key',
                 assertion->>'equipment_ref',
                 NOT assertion ? 'attribute_key')
            THEN RAISE EXCEPTION 'Candidate must preserve the raw attribute assertion'; END IF;
            IF (NEW.attribute_origin,NEW.proposed_value,NEW.proposed_unit,
                NEW.inference_explanation,NEW.inference_basis,NEW.alternate_representations)
                IS DISTINCT FROM
                (CASE WHEN assertion ? 'attribute_key' THEN assertion->>'origin'
                      ELSE 'EXTRACTED' END,
                 NULLIF(assertion->'proposed_value', 'null'::jsonb),
                 assertion->>'proposed_unit',assertion->>'inference_explanation',
                 assertion->>'inference_basis',
                 assertion->'alternate_representations')
                OR NEW.attribute_origin IS NULL
                OR (assertion ? 'attribute_key' AND NOT assertion ? 'proposed_unit')
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
