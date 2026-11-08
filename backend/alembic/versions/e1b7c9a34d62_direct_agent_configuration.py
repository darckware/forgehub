"""Direct authority belongs to the agent configuration; existing scopes stay empty.

Revision ID: e1b7c9a34d62
Revises: d2f8a6c41e07
"""
from alembic import op
import sqlalchemy as sa

revision = "e1b7c9a34d62"
down_revision = "d2f8a6c41e07"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("authority_delegations", sa.Column("all_machines", sa.Boolean(), nullable=False, server_default=sa.false()), schema="company")
    op.add_column("authority_delegations", sa.Column("open_ended", sa.Boolean(), nullable=False, server_default=sa.false()), schema="company")
    op.add_column("authority_delegations", sa.Column("duration_hours", sa.Integer(), nullable=False, server_default="0"), schema="company")
    # Preserve history (including each machine snapshot), but grant no direct access.
    # Listed agents remain listed and need a human-confirmed configuration.
    op.execute(sa.text("""UPDATE company.authority_delegations
        SET status = 'revoked', revoked_at = COALESCE(revoked_at, now())
        WHERE allowed_actions @> '["remote_access.direct"]'::jsonb
          AND status = 'active'"""))


def downgrade():
    # Revoked historical authority must never be reactivated by a downgrade.
    op.drop_column("authority_delegations", "duration_hours", schema="company")
    op.drop_column("authority_delegations", "open_ended", schema="company")
    op.drop_column("authority_delegations", "all_machines", schema="company")
