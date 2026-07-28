"""add demand project_id

Revision ID: b2c4d6e8f0a1
Revises: d718c040a4b3
Create Date: 2026-07-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b2c4d6e8f0a1'
down_revision: Union[str, Sequence[str], None] = 'd718c040a4b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'agent_demands',
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=True),
        schema='company',
    )
    op.create_foreign_key(
        'fk_agent_demands_project_id',
        'agent_demands',
        'projects',
        ['project_id'],
        ['id'],
        source_schema='company',
        referent_schema='company',
        ondelete='SET NULL',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_agent_demands_project_id', 'agent_demands', schema='company', type_='foreignkey')
    op.drop_column('agent_demands', 'project_id', schema='company')
