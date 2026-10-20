"""add encrypted ForgeRouter credential to agents

Revision ID: b6e8f2d1a430
Revises: a4d7e1c9f520
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b6e8f2d1a430"
down_revision: Union[str, Sequence[str], None] = "a4d7e1c9f520"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("forgerouter_api_key_encrypted", sa.Text(), nullable=True),
        schema="company",
    )


def downgrade() -> None:
    op.drop_column("agents", "forgerouter_api_key_encrypted", schema="company")
