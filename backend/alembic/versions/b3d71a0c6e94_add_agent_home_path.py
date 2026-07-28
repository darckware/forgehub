"""add agents.home_path

Revision ID: b3d71a0c6e94
Revises: f5bd6aa4aff8
Create Date: 2026-07-26 12:00:00.000000

Registers where each agent's profile Markdown files (SOUL.md, IDENTITY.md,
TOOLS.md, ...) actually live on the host.

Nullable on purpose: it is an override, not a requirement. When NULL,
core/agent_profile_files.py derives the directory from the runtime
convention, so the eight Hermes profiles and the four external CLI runtimes
(Porthos/claude, Aramis/codex, Dartan/agy, Vector/openclaw) all resolve
without any backfill. The column exists for the cases the convention cannot
cover -- a runtime that moves its config directory, or a second agent
sharing one runtime.

Chains onto f5bd6aa4aff8 (the agent lineage). The repo has had two
independent Alembic heads since before this change -- this keeps the count
at two rather than adding a third.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3d71a0c6e94'
down_revision: Union[str, Sequence[str], None] = 'f5bd6aa4aff8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'agents',
        sa.Column('home_path', sa.Text(), nullable=True),
        schema='company',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('agents', 'home_path', schema='company')
