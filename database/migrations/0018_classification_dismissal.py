"""Persist the decision to keep a revision document's confirmed type."""

from alembic import op
from sqlalchemy import Column, Uuid

revision = "0018_classification_dismissal"
down_revision = "0017_extraction_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("revision_documents", Column("dismissed_classification_prediction_id", Uuid()))
    op.create_foreign_key(
        "fk_revision_documents_dismissed_prediction",
        "revision_documents",
        "classification_predictions",
        ["dismissed_classification_prediction_id", "document_id"],
        ["id", "document_id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_revision_documents_dismissed_prediction", "revision_documents")
    op.drop_column("revision_documents", "dismissed_classification_prediction_id")
