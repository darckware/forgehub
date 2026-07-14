"""add product application URL

Revision ID: 3d7a1c9e5b42
Revises: 2b8e0f5d7c31
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "3d7a1c9e5b42"
down_revision: Union[str, Sequence[str], None] = "2b8e0f5d7c31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("application_url", sa.String(length=2048), nullable=True),
        schema="company",
    )


def downgrade() -> None:
    op.drop_column("products", "application_url", schema="company")
