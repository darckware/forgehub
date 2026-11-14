"""merge quota wait and current release heads

Revision ID: 49707c727f82
Revises: d3f6a8b2c901, e5a7c9d1f3b4
Create Date: 2026-11-14 19:42:01.274450

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = '49707c727f82'
down_revision: Union[str, Sequence[str], None] = ('d3f6a8b2c901', 'e5a7c9d1f3b4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
