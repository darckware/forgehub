"""add web automation routines

Revision ID: 4e8b2d0f6c53
Revises: 3d7a1c9e5b42
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "4e8b2d0f6c53"
down_revision: Union[str, Sequence[str], None] = "3d7a1c9e5b42"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "web_automation_routines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("steps", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["company.products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "name", name="uq_web_automation_routine_product_name"),
        schema="company",
    )


def downgrade() -> None:
    op.drop_table("web_automation_routines", schema="company")
