"""The message a Messages item answers on its channel (the WhatsApp reply).

Revision ID: e4c7a2d09b16
Revises: d3b8f15a6c02
"""
import sqlalchemy as sa
from alembic import op

revision = "e4c7a2d09b16"
down_revision = "d3b8f15a6c02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_demands", sa.Column("channel_message_id", sa.String(100), nullable=True), schema="company")


def downgrade() -> None:
    op.drop_column("agent_demands", "channel_message_id", schema="company")
