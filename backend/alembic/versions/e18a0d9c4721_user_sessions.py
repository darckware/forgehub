"""Create revocable user sessions.

Revision ID: e18a0d9c4721
Revises: d5e93a7b2c18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "e18a0d9c4721"
down_revision = "d5e93a7b2c18"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("company.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("ip_address", sa.String(100)),
        sa.Column("user_agent", sa.String(400)),
        sa.Column("device_summary", sa.String(400)),
        sa.Column("agent_name", sa.String(100)),
        sa.Column("remember_me", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        schema="company",
    )
    op.create_index("ix_company_user_sessions_user_id", "user_sessions", ["user_id"], schema="company")


def downgrade():
    op.drop_table("user_sessions", schema="company")
