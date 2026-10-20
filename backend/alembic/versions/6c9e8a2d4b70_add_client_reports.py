"""add persistent client reports and read credentials

Revision ID: 6c9e8a2d4b70
Revises: 5a8c1e7d9f20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "6c9e8a2d4b70"
down_revision: Union[str, Sequence[str], None] = "5a8c1e7d9f20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
SCHEMA = "company"


def upgrade() -> None:
    op.create_table(
        "client_reports",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("client_id", sa.UUID(), sa.ForeignKey("company.clients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("irregularity_id", sa.UUID(), sa.ForeignKey("company.irregularities.id", ondelete="SET NULL")),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.Column("html_content", sa.Text(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_by_user_id", sa.UUID(), sa.ForeignKey("company.users.id", ondelete="SET NULL")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_by_user_id", sa.UUID(), sa.ForeignKey("company.users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("kind IN ('monthly', 'on_demand')", name="ck_client_reports_kind"),
        sa.CheckConstraint("period_end >= period_start", name="ck_client_reports_period"),
        schema=SCHEMA,
    )
    op.create_index("uq_client_reports_monthly", "client_reports", ["client_id", "period_start"], unique=True, postgresql_where=sa.text("kind = 'monthly'"), schema=SCHEMA)
    op.create_index("ix_client_reports_client_generated", "client_reports", ["client_id", "generated_at"], schema=SCHEMA)
    op.create_table(
        "client_read_credentials",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("client_id", sa.UUID(), sa.ForeignKey("company.clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_by_user_id", sa.UUID(), sa.ForeignKey("company.users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("client_read_credentials", schema=SCHEMA)
    op.drop_index("ix_client_reports_client_generated", table_name="client_reports", schema=SCHEMA)
    op.drop_index("uq_client_reports_monthly", table_name="client_reports", schema=SCHEMA)
    op.drop_table("client_reports", schema=SCHEMA)
