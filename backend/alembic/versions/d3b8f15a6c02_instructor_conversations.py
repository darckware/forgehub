"""One conversation per instructor of the WhatsApp group.

Revision ID: d3b8f15a6c02
Revises: c7e1a94d2f30
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "d3b8f15a6c02"
down_revision = "c7e1a94d2f30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "instructor_conversations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("phone", sa.String(20), nullable=False, unique=True),
        sa.Column("turns", JSONB, nullable=False, server_default="[]"),
        sa.Column("off_topic_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_demand_id", UUID(as_uuid=True), nullable=True),
        sa.Column("last_reply_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="company",
    )


def downgrade() -> None:
    op.drop_table("instructor_conversations", schema="company")
