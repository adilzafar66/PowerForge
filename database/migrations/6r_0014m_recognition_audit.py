"""Retain both AI stages in the existing immutable audit."""

from alembic import op

revision = "6r_0014m_recognition_audit"
down_revision = "6r_0014l_server_owned_output"


def upgrade() -> None:
    op.execute(r"""
    ALTER TABLE extraction_work_units DROP CONSTRAINT ck_extraction_attempt_performance,
        ADD CONSTRAINT ck_extraction_attempt_performance CHECK (performance IS NULL OR (
            stage IN ('EQUIPMENT_RECOGNITION', 'ATTRIBUTE_EXTRACTION')
            AND status IN ('COMPLETED','FAILED')
            AND started_at IS NOT NULL AND jsonb_typeof(performance) = 'object'
            AND (performance @> '{"version": 1}' OR performance @> '{"version": 2}')
            AND octet_length(performance::text) <= 4096));

    ALTER TABLE extraction_response_audits
        ADD COLUMN stage text NOT NULL DEFAULT 'ATTRIBUTE_EXTRACTION',
        DROP CONSTRAINT extraction_response_audits_check,
        ADD CONSTRAINT extraction_response_audit_stage_key CHECK (
            object_key ~ '^(stage1|stage2)/[1-9][0-9]{0,2}d/[a-f0-9-]{36}/[a-f0-9]{64}[.]json$'
            AND object_key LIKE '%/' || work_unit_id::text || '/' || output_sha256 || '.json'
            AND (
                (stage='ATTRIBUTE_EXTRACTION' AND object_key LIKE 'stage2/%')
                OR (stage='EQUIPMENT_RECOGNITION' AND object_key LIKE 'stage1/%'
                    AND received IS NULL AND accepted IS NULL AND quarantined=0
                    AND attribute_reasoning_effort IS NULL AND output_version IS NULL)
            )
        );

    CREATE OR REPLACE FUNCTION extraction_response_audit_guard()
        RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF TG_OP <> 'INSERT' THEN
            RAISE EXCEPTION 'Extraction response audit records are immutable';
        END IF;
        IF NEW.expires_at <= clock_timestamp() OR NOT EXISTS (
            SELECT 1 FROM extraction_work_units u
            JOIN extraction_unit_execution e ON e.work_unit_id=u.id AND e.run_id=u.run_id
            WHERE u.id=NEW.work_unit_id AND u.run_id=NEW.run_id
              AND u.stage=NEW.stage AND e.provider_started_at IS NOT NULL
              AND u.execution_metadata->>'source_page_id'=NEW.document_page_id::text
        ) THEN RAISE EXCEPTION 'Response audit requires its dispatched stage attempt'; END IF;
        RETURN NEW;
    END $$;

    CREATE FUNCTION extraction_recognition_audit_required() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.stage='EQUIPMENT_RECOGNITION' AND NEW.outcome='RESULT'
           AND EXISTS (SELECT 1 FROM extraction_runs WHERE id=NEW.run_id AND provider='openai')
           AND NOT EXISTS (
            SELECT 1 FROM extraction_response_audits a WHERE a.work_unit_id=NEW.work_unit_id
               AND a.stage=NEW.stage AND a.run_id=NEW.run_id
               AND a.document_page_id=NEW.document_page_id AND a.request_hash=NEW.request_hash
               AND a.fatal_diagnostics='[]'::jsonb
        ) THEN RAISE EXCEPTION 'Stage 1 publication requires its retained response audit'; END IF;
        RETURN NEW;
    END $$;

    CREATE CONSTRAINT TRIGGER extraction_recognition_audit_required AFTER INSERT ON
        extraction_stage_results DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
        EXECUTE FUNCTION extraction_recognition_audit_required();
    """)


def downgrade() -> None:
    raise RuntimeError("Phase 6R uses backup-based recovery")
