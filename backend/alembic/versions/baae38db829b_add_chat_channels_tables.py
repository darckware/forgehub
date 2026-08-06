"""add chat_channels tables

Revision ID: baae38db829b
Revises: 79ff53f1772c
Create Date: 2026-08-05 00:00:00.000000

Hand-written (not autogenerate) to avoid sweeping in the pre-existing,
unrelated model/DB drift noted in prior migrations (see e.g.
ff98a10e7daa_add_chat_sessions_working_directory_path.py's own note) and to
express the partial "one human member per channel" unique index, which
SQLAlchemy's UniqueConstraint cannot represent (no WHERE clause support).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'baae38db829b'
down_revision: Union[str, Sequence[str], None] = '79ff53f1772c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'chat_channels',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('working_directory_path', sa.String(length=1024), nullable=True),
        sa.Column('archived', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('turn_policy', sa.String(length=20), nullable=False, server_default='mention_only'),
        sa.Column('created_by', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['company.projects.id'], ondelete='SET NULL'),
        sa.CheckConstraint("turn_policy IN ('mention_only')", name='ck_chat_channels_turn_policy'),
        schema='company',
    )

    op.create_table(
        'chat_channel_members',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('channel_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('is_human', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('hermes_session_id', sa.String(length=100), nullable=True),
        sa.Column('muted', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['channel_id'], ['company.chat_channels.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['agent_id'], ['company.agents.id'], ondelete='CASCADE'),
        sa.CheckConstraint(
            "(is_human AND agent_id IS NULL) OR (NOT is_human AND agent_id IS NOT NULL)",
            name='ck_chat_channel_members_human_xor_agent',
        ),
        sa.UniqueConstraint('channel_id', 'agent_id', name='uq_chat_channel_members_channel_agent'),
        schema='company',
    )
    # Partial unique index: at most one is_human=True row per channel.
    # agent_id is NULL for every human row, so the plain UniqueConstraint
    # above (channel_id, agent_id) does not catch a second human row --
    # NULLs are never considered equal in a standard unique constraint.
    op.create_index(
        'uq_chat_channel_members_one_human_per_channel',
        'chat_channel_members',
        ['channel_id'],
        unique=True,
        schema='company',
        postgresql_where=sa.text('is_human'),
    )

    op.create_table(
        'chat_channel_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('channel_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('author_type', sa.String(length=10), nullable=False),
        sa.Column('author_agent_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('author_label', sa.String(length=150), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('mentioned_agent_ids', postgresql.JSONB(), nullable=True),
        sa.Column('triggered_demand_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('thinking_seconds', sa.Integer(), nullable=True),
        sa.Column('attachment_names', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['channel_id'], ['company.chat_channels.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['author_agent_id'], ['company.agents.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['triggered_demand_id'], ['company.agent_demands.id'], ondelete='SET NULL'),
        sa.CheckConstraint(
            "author_type IN ('human', 'agent', 'system')", name='ck_chat_channel_messages_author_type'
        ),
        sa.CheckConstraint(
            "(author_type = 'agent') = (author_agent_id IS NOT NULL)",
            name='ck_chat_channel_messages_agent_author_id',
        ),
        schema='company',
    )
    op.create_index(
        'ix_chat_channel_messages_channel_id',
        'chat_channel_messages',
        ['channel_id'],
        schema='company',
    )

    op.create_table(
        'chat_channel_artifacts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('channel_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('author_agent_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('path', sa.String(length=1000), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['channel_id'], ['company.chat_channels.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['author_agent_id'], ['company.agents.id'], ondelete='SET NULL'),
        schema='company',
    )

    op.create_table(
        'chat_channel_tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('channel_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='todo'),
        sa.Column('assignee_agent_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_message_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('project_task_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['channel_id'], ['company.chat_channels.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assignee_agent_id'], ['company.agents.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_message_id'], ['company.chat_channel_messages.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_task_id'], ['company.project_tasks.id'], ondelete='SET NULL'),
        sa.CheckConstraint("status IN ('todo', 'doing', 'done')", name='ck_chat_channel_tasks_status'),
        schema='company',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('chat_channel_tasks', schema='company')
    op.drop_table('chat_channel_artifacts', schema='company')
    op.drop_index('ix_chat_channel_messages_channel_id', table_name='chat_channel_messages', schema='company')
    op.drop_table('chat_channel_messages', schema='company')
    op.drop_index(
        'uq_chat_channel_members_one_human_per_channel', table_name='chat_channel_members', schema='company'
    )
    op.drop_table('chat_channel_members', schema='company')
    op.drop_table('chat_channels', schema='company')
