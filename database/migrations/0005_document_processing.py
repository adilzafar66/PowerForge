"""Document pages, processing runs, and page artifacts.

Revision ID: 0005_document_processing
Revises: 0004_documents_and_lineage

Downgrade drops the three Phase 3 tables and their enum types. Documents from
Phase 2 are kept. Nothing in the running app writes these tables yet.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_document_processing"
down_revision: str | None = "0004_documents_and_lineage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Labels are a frozen snapshot, not imported from the live enum. Order is permanent.
PROCESSING_RUN_STATUS_LABELS = ("PENDING", "RUNNING", "COMPLETED", "FAILED")
PAGE_ARTIFACT_TYPE_LABELS = ("ANALYSIS_IMAGE", "THUMBNAIL", "NATIVE_TEXT")
SOURCE_UNIT_LABELS = ("POINTS", "PIXELS")

processing_run_status = postgresql.ENUM(
    *PROCESSING_RUN_STATUS_LABELS,
    name="processing_run_status",
    create_type=False,
)
page_artifact_type = postgresql.ENUM(
    *PAGE_ARTIFACT_TYPE_LABELS,
    name="page_artifact_type",
    create_type=False,
)
source_unit = postgresql.ENUM(
    *SOURCE_UNIT_LABELS,
    name="source_unit",
    create_type=False,
)


def _labels_sql(labels: Sequence[str]) -> str:
    return ", ".join(f"'{label}'" for label in labels)


def upgrade() -> None:
    op.execute(
        "CREATE TYPE processing_run_status AS ENUM "
        f"({_labels_sql(PROCESSING_RUN_STATUS_LABELS)})"
    )
    op.execute(
        "CREATE TYPE page_artifact_type AS ENUM " f"({_labels_sql(PAGE_ARTIFACT_TYPE_LABELS)})"
    )
    op.execute("CREATE TYPE source_unit AS ENUM " f"({_labels_sql(SOURCE_UNIT_LABELS)})")

    op.create_table(
        "document_pages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", name="fk_document_pages_document_id"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("source_width", sa.Numeric(), nullable=False),
        sa.Column("source_height", sa.Numeric(), nullable=False),
        sa.Column("source_unit", source_unit, nullable=False),
        sa.Column("rotation_degrees", sa.Integer(), nullable=False),
        sa.Column(
            "native_text_char_count",
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
        sa.UniqueConstraint(
            "document_id",
            "page_number",
            name="uq_document_pages_document_id_page_number",
        ),
        sa.CheckConstraint("page_number >= 1", name="ck_document_pages_page_number_positive"),
        sa.CheckConstraint(
            "rotation_degrees IN (0, 90, 180, 270)",
            name="ck_document_pages_rotation_degrees",
        ),
    )
    op.create_index("ix_document_pages_document_id", "document_pages", ["document_id"])

    op.create_table(
        "document_processing_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", name="fk_document_processing_runs_document_id"),
            nullable=False,
        ),
        sa.Column("processor_version", sa.Text(), nullable=False),
        sa.Column("profile_version", sa.Text(), nullable=False),
        sa.Column("profile_hash", sa.Text(), nullable=False),
        sa.Column(
            "status",
            processing_run_status,
            nullable=False,
            server_default=sa.text("'PENDING'::processing_run_status"),
        ),
        sa.Column("pages_total", sa.Integer(), nullable=True),
        sa.Column(
            "pages_processed",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
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
    )
    op.create_index(
        "ix_document_processing_runs_document_id",
        "document_processing_runs",
        ["document_id"],
    )
    op.create_index(
        "ix_document_processing_runs_target",
        "document_processing_runs",
        ["document_id", "processor_version", "profile_hash"],
    )
    op.create_index(
        "uq_document_processing_runs_one_live",
        "document_processing_runs",
        ["document_id", "processor_version", "profile_hash"],
        unique=True,
        postgresql_where=sa.text("status IN ('PENDING', 'RUNNING', 'COMPLETED')"),
    )

    op.create_table(
        "page_artifacts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_page_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_pages.id", name="fk_page_artifacts_document_page_id"),
            nullable=False,
        ),
        sa.Column(
            "processing_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "document_processing_runs.id",
                name="fk_page_artifacts_processing_run_id",
            ),
            nullable=False,
        ),
        sa.Column("artifact_type", page_artifact_type, nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("width_px", sa.Integer(), nullable=True),
        sa.Column("height_px", sa.Integer(), nullable=True),
        sa.Column("effective_dpi", sa.Numeric(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("storage_key", name="uq_page_artifacts_storage_key"),
        sa.UniqueConstraint(
            "processing_run_id",
            "document_page_id",
            "artifact_type",
            name="uq_page_artifacts_run_page_type",
        ),
    )
    op.create_index(
        "ix_page_artifacts_document_page_id",
        "page_artifacts",
        ["document_page_id"],
    )
    op.create_index(
        "ix_page_artifacts_processing_run_id",
        "page_artifacts",
        ["processing_run_id"],
    )


def downgrade() -> None:
    op.drop_table("page_artifacts")
    op.drop_table("document_pages")
    op.drop_table("document_processing_runs")
    op.execute("DROP TYPE page_artifact_type")
    op.execute("DROP TYPE source_unit")
    op.execute("DROP TYPE processing_run_status")
