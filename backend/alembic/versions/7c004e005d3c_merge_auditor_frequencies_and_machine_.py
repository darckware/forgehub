"""merge auditor frequencies and machine vault reconfigure

Revision ID: 7c004e005d3c
Revises: a5c7e9f1b3d5, e4a6c8d0f2b3
Create Date: 2026-11-13 22:46:14.212721

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c004e005d3c'
down_revision: Union[str, Sequence[str], None] = ('a5c7e9f1b3d5', 'e4a6c8d0f2b3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
