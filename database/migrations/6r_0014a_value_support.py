"""Persist attribute value support alongside immutable publication."""

from alembic import op

revision = "6r_0014a_value_support"
down_revision = "6r_0014_publication"


def upgrade() -> None:
    op.execute("""
        ALTER TABLE extraction_candidates ADD COLUMN value_source_support text;
        ALTER TABLE extraction_candidates ADD CONSTRAINT ck_extraction_value_source_support
            CHECK (value_source_support IS NULL OR (
                kind = 'ATTRIBUTE' AND value_source_support IN
                    ('TEXT_MATCH', 'TEXT_MISMATCH', 'UNVERIFIED')
            ));
    """)


def downgrade() -> None:
    raise RuntimeError("Phase 6R uses a clean installation and backup-based recovery")
