"""add deploy installations table

Revision ID: d1e9f3a8b042
Revises: c7ed86355d46
Create Date: 2026-06-29 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'd1e9f3a8b042'
down_revision: Union[str, Sequence[str], None] = 'c7ed86355d46'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'deploy_installations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('group_name', sa.String(100), nullable=True),
        sa.Column('order_index', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('container_name', sa.String(255), nullable=True),
        sa.Column('compose_file', sa.Text(), nullable=True),
        sa.Column('restart_command', sa.Text(), nullable=True),
        sa.Column('ports', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('links', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('name', name='uq_deploy_installations_name'),
        schema='company',
    )


def downgrade() -> None:
    op.drop_table('deploy_installations', schema='company')
