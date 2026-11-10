"""Durable, revision-scoped consent and references to existing extraction runs."""

from alembic import op

revision = "0017_extraction_operations"
down_revision = "0016_enriched_extraction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE extraction_operations (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        project_id uuid NOT NULL,
        revision_id uuid NOT NULL,
        intent_hash text NOT NULL,
        policy jsonb NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        next_check_at timestamptz,
        cancel_requested_at timestamptz,
        UNIQUE (id, revision_id),
        FOREIGN KEY (project_id, revision_id) REFERENCES project_revisions (project_id, id),
        CHECK (length(intent_hash) = 64),
        CHECK (jsonb_typeof(policy) = 'object' AND octet_length(policy::text) <= 8192)
    );
    CREATE INDEX ix_extraction_operations_due ON extraction_operations (next_check_at, id)
        WHERE next_check_at IS NOT NULL;
    CREATE INDEX ix_extraction_operations_revision
        ON extraction_operations (revision_id, created_at DESC, id DESC);
    CREATE UNIQUE INDEX uq_extraction_operations_active_intent
        ON extraction_operations (revision_id, intent_hash)
        WHERE next_check_at IS NOT NULL AND cancel_requested_at IS NULL;

    CREATE TABLE extraction_operation_requests (
        revision_id uuid NOT NULL,
        request_key uuid NOT NULL,
        operation_id uuid NOT NULL,
        request_hash text NOT NULL CHECK (length(request_hash) = 64),
        PRIMARY KEY (revision_id, request_key),
        FOREIGN KEY (operation_id, revision_id) REFERENCES extraction_operations (id, revision_id)
    );

    CREATE TABLE extraction_operation_items (
        operation_id uuid NOT NULL REFERENCES extraction_operations (id),
        revision_document_id uuid NOT NULL REFERENCES revision_documents (id),
        document_id uuid NOT NULL,
        processing_run_id uuid NOT NULL,
        selection jsonb NOT NULL,
        layout_run_id uuid,
        engineering_run_id uuid,
        tables_run_id uuid,
        owns_engineering boolean NOT NULL DEFAULT false,
        owns_tables boolean NOT NULL DEFAULT false,
        blocked_reason text,
        PRIMARY KEY (operation_id, revision_document_id),
        FOREIGN KEY (processing_run_id, document_id)
            REFERENCES document_processing_runs (id, document_id),
        FOREIGN KEY (layout_run_id, document_id, processing_run_id)
            REFERENCES extraction_runs (id, document_id, processing_run_id),
        FOREIGN KEY (engineering_run_id, document_id, processing_run_id)
            REFERENCES extraction_runs (id, document_id, processing_run_id),
        FOREIGN KEY (tables_run_id, document_id, processing_run_id)
            REFERENCES extraction_runs (id, document_id, processing_run_id),
        CHECK (jsonb_typeof(selection) = 'object' AND octet_length(selection::text) <= 32768),
        CHECK (NOT owns_engineering OR engineering_run_id IS NOT NULL),
        CHECK (NOT owns_tables OR tables_run_id IS NOT NULL)
    );
    CREATE INDEX ix_extraction_operation_items_document
        ON extraction_operation_items (revision_document_id, operation_id);
    CREATE UNIQUE INDEX uq_extraction_operation_items_engineering_owner
        ON extraction_operation_items (engineering_run_id) WHERE owns_engineering;
    CREATE UNIQUE INDEX uq_extraction_operation_items_tables_owner
        ON extraction_operation_items (tables_run_id) WHERE owns_tables;
    """)


def downgrade() -> None:
    op.execute("""
    DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM extraction_operations) THEN
            RAISE EXCEPTION 'Cannot downgrade with retained extraction operation consent/history';
        END IF;
    END $$;
    DROP TABLE extraction_operation_items;
    DROP TABLE extraction_operation_requests;
    DROP TABLE extraction_operations;
    """)
