"""merge heads

Revision ID: 7768a936e179
Revises: c4a9e2b7d1f6, f1b3d5a7c9e2
Create Date: 2026-07-28 08:26:10.876172

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7768a936e179'
down_revision: Union[str, Sequence[str], None] = ('c4a9e2b7d1f6', 'f1b3d5a7c9e2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
