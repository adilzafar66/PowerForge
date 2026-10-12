"""Classification runs, predictions, usage, and MIXED_DOCUMENT.

Revision ID: 0006_document_classification
Revises: 0005_document_processing

Downgrade drops the new tables, the accepted-prediction column, the new enum
types, and the unique constraints this revision adds to Phase 3 tables.
PostgreSQL cannot remove an enum label, so MIXED_DOCUMENT stays on
document_classification after downgrade. Upgrade skips ADD VALUE when that
label is already present, which is what makes downgrade-then-upgrade work.

ADD VALUE runs in its own autocommit block. PostgreSQL will not let a later
statement in the same transaction use a value that was just added, and
ADD VALUE IF NOT EXISTS cannot be combined with BEFORE.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_document_classification"
down_revision: str | None = "0005_document_processing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen snapshots. create_type=False: document_classification already exists.
DOCUMENT_CLASSIFICATION_LABELS = (
    "SINGLE_LINE_DIAGRAM",
    "ELECTRICAL_DRAWING",
    "PANEL_SCHEDULE",
    "EQUIPMENT_SCHEDULE",
    "CABLE_SCHEDULE",
    "TRANSFORMER_SHOP_DRAWING",
    "SWITCHGEAR_SHOP_DRAWING",
    "BREAKER_DOCUMENT",
    "MOTOR_DATA",
    "FAULT_DATA",
    "SPECIFICATION",
    "EQUIPMENT_PHOTO",
    "NAMEPLATE_PHOTO",
    "STUDY_DOCUMENT",
    "MIXED_DOCUMENT",
    "OTHER",
    "UNKNOWN",
)
CLASSIFICATION_RUN_STATUS_LABELS = ("PENDING", "RUNNING", "COMPLETED", "FAILED")
CLASSIFICATION_STAGE_LABELS = ("DOCUMENT", "PAGES")
CLASSIFICATION_SCOPE_LABELS = ("DOCUMENT", "PAGE")
CONFIDENCE_BAND_LABELS = ("HIGH", "MEDIUM", "LOW")
CLASSIFICATION_CALL_KIND_LABELS = ("DOCUMENT", "PAGE_BATCH")

document_classification = postgresql.ENUM(
    *DOCUMENT_CLASSIFICATION_LABELS,
    name="document_classification",
    create_type=False,
)
classification_run_status = postgresql.ENUM(
    *CLASSIFICATION_RUN_STATUS_LABELS,
    name="classification_run_status",
    create_type=False,
)
classification_stage = postgresql.ENUM(
    *CLASSIFICATION_STAGE_LABELS,
    name="classification_stage",
    create_type=False,
)
classification_scope = postgresql.ENUM(
    *CLASSIFICATION_SCOPE_LABELS,
    name="classification_scope",
    create_type=False,
)
confidence_band = postgresql.ENUM(
    *CONFIDENCE_BAND_LABELS,
    name="confidence_band",
    create_type=False,
)
classification_call_kind = postgresql.ENUM(
    *CLASSIFICATION_CALL_KIND_LABELS,
    name="classification_call_kind",
    create_type=False,
)


def _labels_sql(labels: Sequence[str]) -> str:
    return ", ".join(f"'{label}'" for label in labels)


def _mixed_document_exists() -> bool:
    connection = op.get_bind()
    found = connection.execute(
        sa.text(
            "SELECT 1 FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
            "WHERE t.typname = 'document_classification' AND e.enumlabel = 'MIXED_DOCUMENT'"
        )
    ).scalar()
    return found is not None


def upgrade() -> None:
    if not _mixed_document_exists():
        with op.get_context().autocommit_block():
            op.execute(
                "ALTER TYPE document_classification ADD VALUE 'MIXED_DOCUMENT' BEFORE 'OTHER'"
            )

    op.execute(
        "CREATE TYPE classification_run_status AS ENUM "
        f"({_labels_sql(CLASSIFICATION_RUN_STATUS_LABELS)})"
    )
    op.execute(
        "CREATE TYPE classification_stage AS ENUM " f"({_labels_sql(CLASSIFICATION_STAGE_LABELS)})"
    )
    op.execute(
        "CREATE TYPE classification_scope AS ENUM " f"({_labels_sql(CLASSIFICATION_SCOPE_LABELS)})"
    )
    op.execute(
        "CREATE TYPE confidence_band AS ENUM " f"({_labels_sql(CONFIDENCE_BAND_LABELS)})"
    )
    op.execute(
        "CREATE TYPE classification_call_kind AS ENUM "
        f"({_labels_sql(CLASSIFICATION_CALL_KIND_LABELS)})"
    )

    op.create_unique_constraint(
        "uq_document_pages_id_document_id",
        "document_pages",
        ["id", "document_id"],
    )
    op.create_unique_constraint(
        "uq_document_processing_runs_id_document_id",
        "document_processing_runs",
        ["id", "document_id"],
    )

    op.create_table(
        "document_classification_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", name="fk_document_classification_runs_document_id"),
            nullable=False,
        ),
        sa.Column("processing_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("retry_of_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "attempt_number",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("classifier_version", sa.Text(), nullable=False),
        sa.Column("taxonomy_version", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("sampling_profile_version", sa.Text(), nullable=False),
        sa.Column("sampling_profile_hash", sa.Text(), nullable=False),
        sa.Column("classifier_identity_hash", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column(
            "status",
            classification_run_status,
            nullable=False,
            server_default=sa.text("'PENDING'::classification_run_status"),
        ),
        sa.Column("stage", classification_stage, nullable=True),
        sa.Column("requires_page_classification", sa.Boolean(), nullable=True),
        sa.Column(
            "pages_total",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "pages_classified",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "id",
            "document_id",
            name="uq_document_classification_runs_id_document_id",
        ),
        sa.ForeignKeyConstraint(
            ["processing_run_id", "document_id"],
            ["document_processing_runs.id", "document_processing_runs.document_id"],
            name="fk_document_classification_runs_processing_run",
        ),
        sa.ForeignKeyConstraint(
            ["retry_of_run_id", "document_id"],
            ["document_classification_runs.id", "document_classification_runs.document_id"],
            name="fk_document_classification_runs_retry_of",
        ),
        sa.CheckConstraint(
            "pages_total >= 0",
            name="ck_document_classification_runs_pages_total_nonnegative",
        ),
        sa.CheckConstraint(
            "pages_classified >= 0",
            name="ck_document_classification_runs_pages_classified_nonnegative",
        ),
        sa.CheckConstraint(
            "attempt_number >= 1",
            name="ck_document_classification_runs_attempt_positive",
        ),
    )
    op.create_index(
        "ix_document_classification_runs_document_id",
        "document_classification_runs",
        ["document_id"],
    )
    op.create_index(
        "ix_document_classification_runs_processing_run_id",
        "document_classification_runs",
        ["processing_run_id"],
    )
    op.create_index(
        "ix_document_classification_runs_identity",
        "document_classification_runs",
        ["classifier_identity_hash"],
    )
    op.create_index(
        "uq_document_classification_runs_one_live",
        "document_classification_runs",
        ["classifier_identity_hash"],
        unique=True,
        postgresql_where=sa.text("status IN ('PENDING', 'RUNNING')"),
    )

    op.create_table(
        "classification_predictions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("classification_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", name="fk_classification_predictions_document_id"),
            nullable=False,
        ),
        sa.Column("scope", classification_scope, nullable=False),
        sa.Column("document_page_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("predicted_type", document_classification, nullable=False),
        sa.Column("confidence_score", sa.Numeric(), nullable=False),
        sa.Column("confidence_band", confidence_band, nullable=False),
        sa.Column(
            "alternatives",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "id",
            "document_id",
            name="uq_classification_predictions_id_document_id",
        ),
        sa.ForeignKeyConstraint(
            ["classification_run_id", "document_id"],
            ["document_classification_runs.id", "document_classification_runs.document_id"],
            name="fk_classification_predictions_run",
        ),
        sa.ForeignKeyConstraint(
            ["document_page_id", "document_id"],
            ["document_pages.id", "document_pages.document_id"],
            name="fk_classification_predictions_page",
        ),
        sa.CheckConstraint(
            "(scope = 'DOCUMENT' AND document_page_id IS NULL) "
            "OR (scope = 'PAGE' AND document_page_id IS NOT NULL)",
            name="ck_classification_predictions_scope_page",
        ),
        sa.CheckConstraint(
            "scope <> 'PAGE' OR predicted_type <> 'MIXED_DOCUMENT'",
            name="ck_classification_predictions_page_not_mixed",
        ),
        sa.CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_classification_predictions_score",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(alternatives) = 'array' AND jsonb_array_length(alternatives) <= 3",
            name="ck_classification_predictions_alternatives",
        ),
        sa.CheckConstraint(
            "rationale IS NULL OR char_length(rationale) <= 500",
            name="ck_classification_predictions_rationale",
        ),
    )
    op.create_index(
        "ix_classification_predictions_document_id",
        "classification_predictions",
        ["document_id"],
    )
    op.create_index(
        "ix_classification_predictions_document_page_id",
        "classification_predictions",
        ["document_page_id"],
    )
    op.create_index(
        "uq_classification_predictions_one_document",
        "classification_predictions",
        ["classification_run_id"],
        unique=True,
        postgresql_where=sa.text("scope = 'DOCUMENT'"),
    )
    op.create_index(
        "uq_classification_predictions_run_page",
        "classification_predictions",
        ["classification_run_id", "document_page_id"],
        unique=True,
        postgresql_where=sa.text("scope = 'PAGE'"),
    )

    op.create_table(
        "classification_ai_calls",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "classification_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "document_classification_runs.id",
                name="fk_classification_ai_calls_classification_run_id",
            ),
            nullable=False,
        ),
        sa.Column("call_kind", classification_call_kind, nullable=False),
        sa.Column("page_numbers", postgresql.JSONB(), nullable=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("provider_response_id", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=True),
        sa.Column("image_count", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "(input_tokens IS NULL OR input_tokens >= 0) "
            "AND (cached_input_tokens IS NULL OR cached_input_tokens >= 0) "
            "AND (output_tokens IS NULL OR output_tokens >= 0) "
            "AND (reasoning_tokens IS NULL OR reasoning_tokens >= 0) "
            "AND image_count >= 0 AND latency_ms >= 0",
            name="ck_classification_ai_calls_usage_nonnegative",
        ),
        sa.CheckConstraint(
            "page_numbers IS NULL OR jsonb_typeof(page_numbers) = 'array'",
            name="ck_classification_ai_calls_page_numbers",
        ),
    )
    op.create_index(
        "ix_classification_ai_calls_classification_run_id",
        "classification_ai_calls",
        ["classification_run_id"],
    )

    op.add_column(
        "revision_documents",
        sa.Column(
            "accepted_classification_prediction_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_revision_documents_accepted_prediction",
        "revision_documents",
        "classification_predictions",
        ["accepted_classification_prediction_id", "document_id"],
        ["id", "document_id"],
    )
    op.create_index(
        "ix_revision_documents_accepted_prediction",
        "revision_documents",
        ["accepted_classification_prediction_id"],
        postgresql_where=sa.text("accepted_classification_prediction_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_revision_documents_accepted_prediction",
        table_name="revision_documents",
    )
    op.drop_constraint(
        "fk_revision_documents_accepted_prediction",
        "revision_documents",
        type_="foreignkey",
    )
    op.drop_column("revision_documents", "accepted_classification_prediction_id")
    op.drop_table("classification_ai_calls")
    op.drop_table("classification_predictions")
    op.drop_table("document_classification_runs")
    op.execute("DROP TYPE classification_call_kind")
    op.execute("DROP TYPE confidence_band")
    op.execute("DROP TYPE classification_scope")
    op.execute("DROP TYPE classification_stage")
    op.execute("DROP TYPE classification_run_status")
    op.drop_constraint(
        "uq_document_pages_id_document_id",
        "document_pages",
        type_="unique",
    )
    op.drop_constraint(
        "uq_document_processing_runs_id_document_id",
        "document_processing_runs",
        type_="unique",
    )
