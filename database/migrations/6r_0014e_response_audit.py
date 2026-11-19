"""Record immutable Stage 2 response audit metadata and atomic admission."""

from alembic import op

revision = "6r_0014e_response_audit"
down_revision = "6r_0014d_unit_proposals"


def upgrade() -> None:
    op.execute(r"""
    CREATE TABLE extraction_response_audits (
        work_unit_id uuid PRIMARY KEY REFERENCES extraction_work_units(id),
        run_id uuid NOT NULL REFERENCES extraction_runs(id),
        document_page_id uuid NOT NULL REFERENCES document_pages(id),
        request_hash text NOT NULL CHECK (request_hash ~ '^[a-f0-9]{64}$'),
        object_key text NOT NULL UNIQUE CHECK (
            object_key ~ '^stage2/[1-9][0-9]{0,2}d/[a-f0-9-]{36}/[a-f0-9]{64}[.]json$'
            AND object_key LIKE '%/' || work_unit_id::text || '/' || output_sha256 || '.json'
        ),
        output_sha256 text NOT NULL CHECK (output_sha256 ~ '^[a-f0-9]{64}$'),
        output_bytes integer NOT NULL CHECK (output_bytes BETWEEN 0 AND 524288),
        expires_at timestamptz NOT NULL,
        received integer CHECK (received BETWEEN 0 AND 528),
        accepted integer CHECK (accepted BETWEEN 0 AND 528),
        quarantined integer NOT NULL CHECK (quarantined BETWEEN 0 AND 528),
        rejections jsonb NOT NULL CHECK (jsonb_typeof(rejections)='array'
            AND jsonb_array_length(rejections)=quarantined
            AND octet_length(rejections::text)<=1048576),
        fatal_diagnostics jsonb NOT NULL CHECK (jsonb_typeof(fatal_diagnostics)='array'
            AND jsonb_array_length(fatal_diagnostics)<=8
            AND octet_length(fatal_diagnostics::text)<=4096),
        CHECK ((received IS NULL AND accepted IS NULL AND quarantined=0)
            OR (received IS NOT NULL AND accepted IS NOT NULL AND (
                received=accepted+quarantined OR
                (accepted=0 AND quarantined=0 AND jsonb_array_length(fatal_diagnostics)>0)
            )))
    );
    CREATE INDEX ix_extraction_response_audits_run ON extraction_response_audits(run_id);

    CREATE FUNCTION extraction_response_audit_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF TG_OP <> 'INSERT' THEN
            RAISE EXCEPTION 'Extraction response audit records are immutable';
        END IF;
        IF NEW.expires_at <= clock_timestamp() OR NOT EXISTS (
            SELECT 1 FROM extraction_work_units u
            JOIN extraction_unit_execution e ON e.work_unit_id=u.id AND e.run_id=u.run_id
            WHERE u.id=NEW.work_unit_id AND u.run_id=NEW.run_id
              AND u.stage='ATTRIBUTE_EXTRACTION' AND e.provider_started_at IS NOT NULL
              AND u.execution_metadata->>'source_page_id'=NEW.document_page_id::text
        ) THEN RAISE EXCEPTION 'Response audit requires its dispatched Stage 2 attempt'; END IF;
        RETURN NEW;
    END $$;

    CREATE TRIGGER extraction_response_audit_guard BEFORE INSERT OR UPDATE OR DELETE
        ON extraction_response_audits FOR EACH ROW
        EXECUTE FUNCTION extraction_response_audit_guard();
    CREATE TRIGGER extraction_fence_guard BEFORE INSERT ON extraction_response_audits
        FOR EACH ROW EXECUTE FUNCTION extraction_fence_guard();

    CREATE FUNCTION extraction_response_audit_requires_terminal_attempt()
        RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM extraction_work_units u WHERE u.id=NEW.work_unit_id
                AND u.status IN ('COMPLETED','FAILED')
        ) THEN RAISE EXCEPTION 'Response audit requires atomic attempt settlement'; END IF;
        RETURN NEW;
    END $$;
    CREATE CONSTRAINT TRIGGER extraction_response_audit_terminal AFTER INSERT
        ON extraction_response_audits DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
        EXECUTE FUNCTION extraction_response_audit_requires_terminal_attempt();

    CREATE TABLE extraction_response_audit_reads (
        id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        work_unit_id uuid NOT NULL REFERENCES extraction_response_audits(work_unit_id),
        operator_name text NOT NULL DEFAULT current_user,
        accessed_at timestamptz NOT NULL DEFAULT clock_timestamp()
    );
    CREATE FUNCTION extraction_response_audit_read_identity() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        NEW.operator_name := current_user;
        NEW.accessed_at := clock_timestamp();
        IF NOT EXISTS (
            SELECT 1 FROM extraction_response_audits WHERE work_unit_id=NEW.work_unit_id
                AND expires_at > NEW.accessed_at
        ) THEN RAISE EXCEPTION 'Response audit is unavailable or has expired'; END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER extraction_response_audit_read_identity BEFORE INSERT
        ON extraction_response_audit_reads FOR EACH ROW
        EXECUTE FUNCTION extraction_response_audit_read_identity();
    CREATE TRIGGER extraction_response_audit_reads_immutable BEFORE UPDATE OR DELETE
        ON extraction_response_audit_reads FOR EACH ROW
        EXECUTE FUNCTION extraction_response_audit_guard();

    CREATE FUNCTION extraction_stage_response_audit_required()
        RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.payload->>'version'='phase-6r-attributes-v5' AND NEW.outcome='RESULT'
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
    CREATE CONSTRAINT TRIGGER extraction_stage_response_audit_required AFTER INSERT ON
        extraction_stage_results DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
        EXECUTE FUNCTION extraction_stage_response_audit_required();

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
                    IN ('phase-6r-attributes-v2','phase-6r-attributes-v3',
                     'phase-6r-attributes-v4','phase-6r-attributes-v5')
                    THEN CASE WHEN assertion ? 'attribute_key' THEN assertion->>'origin'
                        ELSE 'EXTRACTED' END END,
                 assertion->>'proposed_value',assertion->>'proposed_unit',
                 assertion->>'inference_explanation',assertion->>'inference_basis')
                OR s.payload->>'version' IN
                    ('phase-6r-attributes-v2','phase-6r-attributes-v3',
                     'phase-6r-attributes-v4','phase-6r-attributes-v5')
                   AND NEW.attribute_origin IS NULL
                OR s.payload->>'version' IN ('phase-6r-attributes-v4','phase-6r-attributes-v5')
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
