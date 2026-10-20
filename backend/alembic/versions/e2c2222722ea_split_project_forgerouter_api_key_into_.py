"""split project forgerouter api_key into per-tool columns

Revision ID: e2c2222722ea
Revises: cb05a570d0c9
Create Date: 2026-07-17 15:58:33.429437

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e2c2222722ea'
down_revision: Union[str, Sequence[str], None] = 'cb05a570d0c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# NOTE: autogenerate also picked up unrelated drift from other in-progress,
# uncommitted work (approval_requests index, chat_messages.steps,
# users.ui_language) -- those are intentionally excluded here; this
# migration only covers the project_forgerouter_configs api_key split.


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('project_forgerouter_configs', sa.Column('claude_api_key', sa.String(length=500), nullable=True), schema='company')
    op.add_column('project_forgerouter_configs', sa.Column('codex_api_key', sa.String(length=500), nullable=True), schema='company')
    op.add_column('project_forgerouter_configs', sa.Column('antigravity_api_key', sa.String(length=500), nullable=True), schema='company')
    # Preserve any existing shared key: apply it as each currently-enabled
    # tool's own key, since previously ALL enabled tools were using it.
    op.execute("""
        UPDATE company.project_forgerouter_configs
        SET claude_api_key = CASE WHEN claude_enabled THEN api_key ELSE claude_api_key END,
            codex_api_key = CASE WHEN codex_enabled THEN api_key ELSE codex_api_key END,
            antigravity_api_key = CASE WHEN antigravity_enabled THEN api_key ELSE antigravity_api_key END
        WHERE api_key IS NOT NULL
    """)
    op.drop_column('project_forgerouter_configs', 'api_key', schema='company')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('project_forgerouter_configs', sa.Column('api_key', sa.VARCHAR(length=500), autoincrement=False, nullable=True), schema='company')
    op.execute("""
        UPDATE company.project_forgerouter_configs
        SET api_key = COALESCE(claude_api_key, codex_api_key, antigravity_api_key)
    """)
    op.drop_column('project_forgerouter_configs', 'antigravity_api_key', schema='company')
    op.drop_column('project_forgerouter_configs', 'codex_api_key', schema='company')
    op.drop_column('project_forgerouter_configs', 'claude_api_key', schema='company')
