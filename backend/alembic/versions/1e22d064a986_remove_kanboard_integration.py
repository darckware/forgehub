"""remove_kanboard_integration

Kanboard was discontinued (2026-07-28, Marcelo: "preciso remover qualquer
referencia kanboard na aplicacao. Porque foi descontinuado no sistema").
Drops the three kanboard_* columns (products.kanboard_project_id/
kanboard_column_ids, project_tasks.kanboard_task_id) added by
c7ed86355d46/9e2a27998edd, and removes 'kanboard' from
tool_version_status's monitored-tool set (reverses a6d95c31e7f2, minus
the constraint-name churn since that migration already established the
final constraint name/shape).

Revision ID: 1e22d064a986
Revises: b27855f20f54
Create Date: 2026-07-28 20:45:19.565555

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '1e22d064a986'
down_revision: Union[str, Sequence[str], None] = 'b27855f20f54'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # tool_version_status: drop any persisted Kanboard row, then narrow the
    # CheckConstraint back to the host-CLI-only tool set.
    op.execute("DELETE FROM company.tool_version_status WHERE tool = 'kanboard'")
    op.drop_constraint('ck_tool_version_status_tool', 'tool_version_status', schema='company', type_='check')
    op.create_check_constraint(
        'ck_tool_version_status_tool',
        'tool_version_status',
        "tool IN ('hermes', 'claude', 'codex', 'antigravity', 'pi', 'opencode')",
        schema='company',
    )

    # products: drop the Kanboard project/column-map columns.
    op.drop_column('products', 'kanboard_column_ids', schema='company')
    op.drop_column('products', 'kanboard_project_id', schema='company')

    # project_tasks: drop the Kanboard card-id column.
    op.drop_column('project_tasks', 'kanboard_task_id', schema='company')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('project_tasks', sa.Column('kanboard_task_id', sa.Integer(), nullable=True), schema='company')

    op.add_column('products', sa.Column('kanboard_project_id', sa.Integer(), nullable=True), schema='company')
    op.add_column('products', sa.Column('kanboard_column_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=True), schema='company')

    op.drop_constraint('ck_tool_version_status_tool', 'tool_version_status', schema='company', type_='check')
    op.create_check_constraint(
        'ck_tool_version_status_tool',
        'tool_version_status',
        "tool IN ('hermes', 'claude', 'codex', 'antigravity', 'pi', 'opencode', 'kanboard')",
        schema='company',
    )
