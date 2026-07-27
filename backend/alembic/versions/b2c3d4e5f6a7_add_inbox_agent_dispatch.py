"""add inbox agent dispatch fields

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-23 00:00:00.000000

NOTE: same pre-existing two-heads situation noted in 8c829b7454d6 -- this
migration only extends that branch, it does not merge d718c040a4b3.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('agents', sa.Column('runtime_type', sa.String(length=20), nullable=True), schema='company')
    op.create_check_constraint(
        'ck_agents_runtime_type', 'agents', "runtime_type IS NULL OR runtime_type IN ('claude', 'codex', 'agy')", schema='company'
    )

    op.add_column('agent_demands', sa.Column('target_agent_id', postgresql.UUID(as_uuid=True), nullable=True), schema='company')
    op.add_column('agent_demands', sa.Column('from_agent_id', postgresql.UUID(as_uuid=True), nullable=True), schema='company')
    op.add_column('agent_demands', sa.Column('command_text', sa.Text(), nullable=True), schema='company')
    op.add_column('agent_demands', sa.Column('origin_type', sa.String(length=20), nullable=True), schema='company')
    op.add_column('agent_demands', sa.Column('origin_id', postgresql.UUID(as_uuid=True), nullable=True), schema='company')
    op.add_column('agent_demands', sa.Column('dispatch_status', sa.String(length=20), nullable=True), schema='company')
    op.add_column('agent_demands', sa.Column('agent_run_id', sa.String(length=64), nullable=True), schema='company')
    op.add_column('agent_demands', sa.Column('notice_sent', sa.Boolean(), server_default='false', nullable=False), schema='company')

    op.create_foreign_key(
        'fk_agent_demands_target_agent_id', 'agent_demands', 'agents',
        ['target_agent_id'], ['id'], source_schema='company', referent_schema='company', ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_agent_demands_from_agent_id', 'agent_demands', 'agents',
        ['from_agent_id'], ['id'], source_schema='company', referent_schema='company', ondelete='SET NULL',
    )
    op.create_check_constraint(
        'ck_agent_demands_dispatch_status', 'agent_demands',
        "dispatch_status IS NULL OR dispatch_status IN ('pending', 'dispatched', 'running', 'completed', 'failed')",
        schema='company',
    )
    op.create_check_constraint(
        'ck_agent_demands_origin_type', 'agent_demands',
        "origin_type IS NULL OR origin_type IN ('task', 'demand')", schema='company',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_agent_demands_origin_type', 'agent_demands', schema='company', type_='check')
    op.drop_constraint('ck_agent_demands_dispatch_status', 'agent_demands', schema='company', type_='check')
    op.drop_constraint('fk_agent_demands_from_agent_id', 'agent_demands', schema='company', type_='foreignkey')
    op.drop_constraint('fk_agent_demands_target_agent_id', 'agent_demands', schema='company', type_='foreignkey')

    op.drop_column('agent_demands', 'notice_sent', schema='company')
    op.drop_column('agent_demands', 'agent_run_id', schema='company')
    op.drop_column('agent_demands', 'dispatch_status', schema='company')
    op.drop_column('agent_demands', 'origin_id', schema='company')
    op.drop_column('agent_demands', 'origin_type', schema='company')
    op.drop_column('agent_demands', 'command_text', schema='company')
    op.drop_column('agent_demands', 'from_agent_id', schema='company')
    op.drop_column('agent_demands', 'target_agent_id', schema='company')

    op.drop_constraint('ck_agents_runtime_type', 'agents', schema='company', type_='check')
    op.drop_column('agents', 'runtime_type', schema='company')
