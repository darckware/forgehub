"""Workspace Explorer: per-user Quick access pins/unpins

Revision ID: f3a1c7d9e2b4
Revises: e7f8a9b0c1d2
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f3a1c7d9e2b4"
down_revision: Union[str, Sequence[str], None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
SCHEMA = "company"


def upgrade() -> None:
    op.create_table(
        "explorer_quick_access",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("path", sa.String(4096), nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("hidden", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "path", name="uq_explorer_quick_access_user_path"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_company_explorer_quick_access_user_id", "explorer_quick_access", ["user_id"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_company_explorer_quick_access_user_id", table_name="explorer_quick_access", schema=SCHEMA)
    op.drop_table("explorer_quick_access", schema=SCHEMA)
