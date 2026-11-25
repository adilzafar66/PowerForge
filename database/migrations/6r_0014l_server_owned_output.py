"""Allow the reliability-only Stage 2 output version in immutable audits."""

from alembic import op

revision = "6r_0014l_server_owned_output"
down_revision = "6r_0014k_attribute_output"


def upgrade() -> None:
    op.execute("""
    ALTER TABLE extraction_response_audits
        DROP CONSTRAINT extraction_response_audits_output_version_check,
        ADD CONSTRAINT extraction_response_audits_output_version_check CHECK (
            output_version IN ('compact-assertions-v1', 'server-owned-assertions-v1')
        );
    """)


def downgrade() -> None:
    raise RuntimeError("Phase 6R uses backup-based recovery")
