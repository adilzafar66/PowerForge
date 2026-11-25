"""Track compact Stage 2 overflow in the existing immutable audit."""

from alembic import op

revision = "6r_0014k_attribute_output"
down_revision = "6r_0014j_source_modality"


def upgrade() -> None:
    op.execute("""
    ALTER TABLE extraction_response_audits
        ADD COLUMN output_version text CHECK (output_version = 'compact-assertions-v1'),
        ADD COLUMN overflow_indices integer[] NOT NULL DEFAULT '{}',
        DROP CONSTRAINT extraction_response_audits_received_check,
        DROP CONSTRAINT extraction_response_audits_quarantined_check,
        DROP CONSTRAINT extraction_response_audits_check2;

    ALTER TABLE extraction_response_audits
        ADD CONSTRAINT extraction_response_audit_intake_bounds CHECK (
            received BETWEEN 0 AND CASE WHEN output_version IS NULL THEN 528 ELSE 544 END
            AND quarantined BETWEEN 0 AND CASE WHEN output_version IS NULL THEN 528 ELSE 544 END
            OR received IS NULL AND quarantined = 0
        ),
        ADD CONSTRAINT extraction_response_audit_overflow_bounds CHECK (
            cardinality(overflow_indices)
                <= CASE WHEN output_version IS NULL THEN 0 ELSE 16 END
            AND array_position(overflow_indices, NULL) IS NULL
            AND 0 <= ALL (overflow_indices) AND 31 >= ALL (overflow_indices)
        ),
        ADD CONSTRAINT extraction_response_audit_result_counts CHECK (
            (received IS NULL AND accepted IS NULL AND quarantined=0
                AND cardinality(overflow_indices)=0)
            OR (received IS NOT NULL AND accepted IS NOT NULL AND (
                received=accepted+quarantined+cardinality(overflow_indices)
                OR (accepted=0 AND quarantined=0 AND cardinality(overflow_indices)=0
                    AND jsonb_array_length(fatal_diagnostics)>0)
            ))
        );

    CREATE OR REPLACE FUNCTION extraction_response_audit_dispatch_guard()
        RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM extraction_unit_execution e
            WHERE e.work_unit_id=NEW.work_unit_id AND e.run_id=NEW.run_id
                AND e.provider_request_hash=NEW.request_hash
        ) THEN RAISE EXCEPTION 'Response audit differs from its dispatched request'; END IF;
        IF NOT EXISTS (
            SELECT 1 FROM extraction_work_units u WHERE u.id=NEW.work_unit_id
            AND NEW.attribute_reasoning_effort IS NOT DISTINCT FROM
                (u.execution_metadata->>'attribute_reasoning_effort')
        ) THEN RAISE EXCEPTION 'Response audit differs from its pinned reasoning effort'; END IF;
        IF NOT EXISTS (
            SELECT 1 FROM extraction_work_units u WHERE u.id=NEW.work_unit_id
            AND NEW.output_version IS NOT DISTINCT FROM
                (u.execution_metadata->>'attribute_output_version')
        ) THEN RAISE EXCEPTION 'Response audit differs from its pinned output version'; END IF;
        IF NEW.overflow_indices <> ARRAY(
            SELECT DISTINCT i FROM unnest(NEW.overflow_indices) AS i ORDER BY i
        ) OR EXISTS (
            SELECT 1 FROM jsonb_array_elements(NEW.rejections) AS r
            CROSS JOIN unnest(NEW.overflow_indices) AS i
            WHERE r->>'collection'='raw_unmapped' AND r->>'index'=i::text
        ) THEN RAISE EXCEPTION 'Audit overflow positions must be ordered and distinct'; END IF;
        RETURN NEW;
    END $$;
    """)


def downgrade() -> None:
    raise RuntimeError("Phase 6R uses backup-based recovery")
