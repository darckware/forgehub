"""add kanboard to tool_version_status check constraint

Revision ID: a6d95c31e7f2
Revises: f2c9d81b3a74
Create Date: 2026-07-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a6d95c31e7f2'
down_revision: Union[str, Sequence[str], None] = 'f2c9d81b3a74'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint('ck_tool_version_status_tool', 'tool_version_status', schema='company', type_='check')
    op.create_check_constraint(
        'ck_tool_version_status_tool',
        'tool_version_status',
        "tool IN ('hermes', 'claude', 'codex', 'antigravity', 'pi', 'opencode', 'kanboard')",
        schema='company',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM company.tool_version_status WHERE tool = 'kanboard'")
    op.drop_constraint('ck_tool_version_status_tool', 'tool_version_status', schema='company', type_='check')
    op.create_check_constraint(
        'ck_tool_version_status_tool',
        'tool_version_status',
        "tool IN ('hermes', 'claude', 'codex', 'antigravity', 'pi', 'opencode')",
        schema='company',
    )
