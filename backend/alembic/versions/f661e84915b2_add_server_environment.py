"""add server environment

Revision ID: f661e84915b2
Revises: e9ae96a2c664
Create Date: 2026-09-07 17:02:40.513245

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f661e84915b2'
down_revision: Union[str, Sequence[str], None] = 'e9ae96a2c664'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "servers",
        sa.Column(
            "environment",
            sa.String(length=50),
            server_default="semed",
            nullable=False,
        ),
        schema="company",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("servers", "environment", schema="company")
