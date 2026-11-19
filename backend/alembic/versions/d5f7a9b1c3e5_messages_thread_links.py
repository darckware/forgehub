"""Messages phase 2/3: the thread is a database link, and the "done elsewhere" check is kept.

Marcelo, 2026-11-19: "o controle das tarefas dos agentes precisa ser coeso". A
task's continuation and the task that did its work are recorded as links, not
as a "#N" in the text (MESSAGES_GUIA.md §13.2). The section-4 analysis ("já foi
feito em outro lugar?") is kept per message until the message changes (§13.3).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'd5f7a9b1c3e5'
down_revision = 'c4e6a8b0d2f3'
branch_labels = None
depends_on = None


def upgrade():
    for column in ('continues_id', 'done_by_id'):
        op.add_column('agent_demands', sa.Column(column, postgresql.UUID(as_uuid=True), nullable=True), schema='company')
        op.create_foreign_key(f'fk_agent_demands_{column}', 'agent_demands', 'agent_demands', [column], ['id'],
                              source_schema='company', referent_schema='company', ondelete='SET NULL')
        op.create_index(f'ix_agent_demands_{column}', 'agent_demands', [column], schema='company')
        op.create_check_constraint(f'ck_agent_demands_{column}_not_self', 'agent_demands',
                                   f"{column} IS NULL OR {column} <> id", schema='company')
    op.create_table(
        'message_elsewhere_checks',
        sa.Column('message_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('company.agent_demands.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('source_fingerprint', sa.String(64), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('matches', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('candidates', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('requested_by', sa.String(150), nullable=False),
        sa.Column('checked_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('done_elsewhere','partly_elsewhere','not_found','unavailable')",
                           name='ck_message_elsewhere_status'),
        schema='company',
    )


def downgrade():
    op.drop_table('message_elsewhere_checks', schema='company')
    for column in ('done_by_id', 'continues_id'):
        op.drop_constraint(f'ck_agent_demands_{column}_not_self', 'agent_demands', schema='company', type_='check')
        op.drop_index(f'ix_agent_demands_{column}', 'agent_demands', schema='company')
        op.drop_constraint(f'fk_agent_demands_{column}', 'agent_demands', schema='company', type_='foreignkey')
        op.drop_column('agent_demands', column, schema='company')
