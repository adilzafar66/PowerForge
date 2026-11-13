"""Phase 6R clean-install operations schema."""

from alembic import op

revision = "6r_0013_operations"
down_revision = "6r_0012_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(r"""
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
        extraction_run_id uuid,
        owns_extraction boolean NOT NULL DEFAULT false,
        blocked_reason text,
        PRIMARY KEY (operation_id, revision_document_id),
        FOREIGN KEY (processing_run_id, document_id)
            REFERENCES document_processing_runs (id, document_id),
        FOREIGN KEY (layout_run_id, document_id, processing_run_id)
            REFERENCES extraction_runs (id, document_id, processing_run_id),
        FOREIGN KEY (extraction_run_id, document_id, processing_run_id)
            REFERENCES extraction_runs (id, document_id, processing_run_id),
        CHECK (jsonb_typeof(selection) = 'object' AND octet_length(selection::text) <= 32768),
        CHECK (NOT owns_extraction OR extraction_run_id IS NOT NULL)
    );
    CREATE INDEX ix_extraction_operation_items_document
        ON extraction_operation_items (revision_document_id, operation_id);
    CREATE UNIQUE INDEX uq_extraction_operation_items_extraction_owner
        ON extraction_operation_items (extraction_run_id) WHERE owns_extraction;
    """)


def downgrade() -> None:
    raise RuntimeError("Phase 6R uses a clean installation and backup-based recovery")
