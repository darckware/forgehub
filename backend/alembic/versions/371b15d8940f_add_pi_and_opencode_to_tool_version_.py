"""add pi and opencode to tool_version_status check constraint

Revision ID: 371b15d8940f
Revises: 9e2a27998edd
Create Date: 2026-06-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '371b15d8940f'
down_revision: Union[str, Sequence[str], None] = '9e2a27998edd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint('ck_tool_version_status_tool', 'tool_version_status', schema='company', type_='check')
    op.create_check_constraint(
        'ck_tool_version_status_tool',
        'tool_version_status',
        "tool IN ('hermes', 'claude', 'codex', 'antigravity', 'pi', 'opencode')",
        schema='company',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_tool_version_status_tool', 'tool_version_status', schema='company', type_='check')
    op.create_check_constraint(
        'ck_tool_version_status_tool',
        'tool_version_status',
        "tool IN ('hermes', 'claude', 'codex', 'antigravity')",
        schema='company',
    )
