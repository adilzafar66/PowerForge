"""Persist the exact reasoning effort in immutable Stage 2 response audits."""

from alembic import op

revision = "6r_0014i_attribute_reasoning"
down_revision = "6r_0014h_attempt_performance"


def upgrade() -> None:
    op.execute("""
    ALTER TABLE extraction_response_audits
        ADD COLUMN attribute_reasoning_effort text
            CHECK (attribute_reasoning_effort IN ('none','low','medium'));

    CREATE OR REPLACE FUNCTION extraction_response_audit_dispatch_guard()
        RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM extraction_unit_execution e
            WHERE e.work_unit_id=NEW.work_unit_id AND e.run_id=NEW.run_id
                AND e.provider_request_hash=NEW.request_hash
        ) THEN RAISE EXCEPTION 'Response audit differs from its dispatched request'; END IF;
        IF NEW.attribute_reasoning_effort IS DISTINCT FROM (
            SELECT u.execution_metadata->>'attribute_reasoning_effort'
            FROM extraction_work_units u WHERE u.id=NEW.work_unit_id
        ) THEN RAISE EXCEPTION 'Response audit differs from its pinned reasoning effort'; END IF;
        RETURN NEW;
    END $$;
    """)


def downgrade() -> None:
    raise RuntimeError("Phase 6R uses backup-based recovery")
