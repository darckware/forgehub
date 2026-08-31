"""add attachment_data_urls to chat_messages

Revision ID: e8a91c2b3d4f
Revises: d4b7e91a2c63
Create Date: 2026-08-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8a91c2b3d4f"
down_revision: Union[str, Sequence[str], None] = "d4b7e91a2c63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chat_messages",
        sa.Column("attachment_data_urls", sa.Text(), nullable=True),
        schema="company",
    )


def downgrade() -> None:
    op.drop_column("chat_messages", "attachment_data_urls", schema="company")
