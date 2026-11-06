"""Single-use maintenance proposals approved by content hash.

Revision ID: f7a1b2c3d4e5
Revises: f6a1b2c3d4e5
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "f7a1b2c3d4e5"
down_revision = "f6a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('maintenance_proposals',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('agent_id', UUID(as_uuid=True), sa.ForeignKey('company.agents.id'), nullable=False),
        sa.Column('agent_demand_id', UUID(as_uuid=True), sa.ForeignKey('company.agent_demands.id'), nullable=False),
        sa.Column('server_ids', JSONB, nullable=False),
        sa.Column('shell', sa.String(20), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('risk', sa.String(20), nullable=False),
        sa.Column('timeout_seconds', sa.Integer, nullable=False),
        sa.Column('requires_elevation', sa.Boolean, nullable=False),
        sa.Column('parameters', JSONB, nullable=False),
        sa.Column('reason', sa.Text, nullable=False),
        sa.Column('expected_effect', sa.Text, nullable=False),
        sa.Column('rollback', sa.Text, nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('approved_by', UUID(as_uuid=True), sa.ForeignKey('company.users.id')),
        sa.Column('approved_at', sa.DateTime(timezone=True)),
        sa.Column('expires_at', sa.DateTime(timezone=True)),
        sa.Column('decision_reason', sa.Text),
        sa.Column('claimed_at', sa.DateTime(timezone=True)),
        sa.Column('execution_id', UUID(as_uuid=True), sa.ForeignKey('company.host_executions.id'), unique=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('proposed','approved','rejected','expired','claimed','succeeded','failed')", name='ck_maintenance_proposal_status'),
        schema='company')


def downgrade():
    op.drop_table('maintenance_proposals', schema='company')
