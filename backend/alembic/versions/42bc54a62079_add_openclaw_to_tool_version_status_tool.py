"""add openclaw to tool version status tool

Revision ID: 42bc54a62079
Revises: 1e22d064a986
Create Date: 2026-07-28 21:27:18.727974

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '42bc54a62079'
down_revision: Union[str, Sequence[str], None] = '1e22d064a986'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint('ck_tool_version_status_tool', 'tool_version_status', schema='company', type_='check')
    op.create_check_constraint(
        'ck_tool_version_status_tool',
        'tool_version_status',
        "tool IN ('hermes', 'claude', 'codex', 'antigravity', 'pi', 'opencode', 'openclaw')",
        schema='company',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM company.tool_version_status WHERE tool = 'openclaw'")
    op.drop_constraint('ck_tool_version_status_tool', 'tool_version_status', schema='company', type_='check')
    op.create_check_constraint(
        'ck_tool_version_status_tool',
        'tool_version_status',
        "tool IN ('hermes', 'claude', 'codex', 'antigravity', 'pi', 'opencode')",
        schema='company',
    )
