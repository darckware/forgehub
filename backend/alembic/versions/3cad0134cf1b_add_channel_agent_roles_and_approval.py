"""add channel agent roles and approval linkage

Revision ID: 3cad0134cf1b
Revises: baae38db829b
Create Date: 2026-08-05 12:00:00.000000

Hand-written (not autogenerate), same rationale as baae38db829b: avoids
sweeping in pre-existing unrelated model/DB drift. See
docs/architecture/CHANNEL_AGENT_ROLES_AND_ORCHESTRATION.md for the design
this implements.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '3cad0134cf1b'
down_revision: Union[str, Sequence[str], None] = 'baae38db829b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# PROJECT_AGENT_ROLES (backend/app/db/models/orchestration.py), extended
# with "documentation" -- the single shared function vocabulary reused by
# agents.default_role, chat_channel_members.role, chat_channel_tasks.
# role_required, and project_agent_memberships.role.
PROJECT_AGENT_ROLES = (
    "coordinator", "planner", "architect", "designer", "developer",
    "data_engineer", "qa", "security_reviewer", "reviewer",
    "release_manager", "documentation",
)


def upgrade() -> None:
    """Upgrade schema."""
    # project_agent_memberships.role CHECK grows to include "documentation".
    op.drop_constraint(
        'ck_project_agent_memberships_role', 'project_agent_memberships', schema='company', type_='check'
    )
    op.create_check_constraint(
        'ck_project_agent_memberships_role',
        'project_agent_memberships',
        f"role IN {PROJECT_AGENT_ROLES!r}",
        schema='company',
    )

    op.add_column('agents', sa.Column('default_role', sa.String(length=30), nullable=True), schema='company')
    op.create_check_constraint(
        'ck_agents_default_role',
        'agents',
        f"default_role IS NULL OR default_role IN {PROJECT_AGENT_ROLES!r}",
        schema='company',
    )

    op.add_column('chat_channel_members', sa.Column('role', sa.String(length=30), nullable=True), schema='company')
    op.create_check_constraint(
        'ck_chat_channel_members_role',
        'chat_channel_members',
        f"role IS NULL OR role IN {PROJECT_AGENT_ROLES!r}",
        schema='company',
    )

    op.add_column('chat_channel_tasks', sa.Column('role_required', sa.String(length=30), nullable=True), schema='company')
    op.add_column(
        'chat_channel_tasks',
        sa.Column('created_by_agent_id', postgresql.UUID(as_uuid=True), nullable=True),
        schema='company',
    )
    op.add_column(
        'chat_channel_tasks',
        sa.Column('approval_id', postgresql.UUID(as_uuid=True), nullable=True),
        schema='company',
    )
    op.create_check_constraint(
        'ck_chat_channel_tasks_role_required',
        'chat_channel_tasks',
        f"role_required IS NULL OR role_required IN {PROJECT_AGENT_ROLES!r}",
        schema='company',
    )
    op.create_foreign_key(
        'fk_chat_channel_tasks_created_by_agent_id',
        'chat_channel_tasks', 'agents',
        ['created_by_agent_id'], ['id'],
        source_schema='company', referent_schema='company', ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_chat_channel_tasks_approval_id',
        'chat_channel_tasks', 'approvals',
        ['approval_id'], ['id'],
        source_schema='company', referent_schema='company', ondelete='SET NULL',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_chat_channel_tasks_approval_id', 'chat_channel_tasks', schema='company', type_='foreignkey')
    op.drop_constraint(
        'fk_chat_channel_tasks_created_by_agent_id', 'chat_channel_tasks', schema='company', type_='foreignkey'
    )
    op.drop_constraint(
        'ck_chat_channel_tasks_role_required', 'chat_channel_tasks', schema='company', type_='check'
    )
    op.drop_column('chat_channel_tasks', 'approval_id', schema='company')
    op.drop_column('chat_channel_tasks', 'created_by_agent_id', schema='company')
    op.drop_column('chat_channel_tasks', 'role_required', schema='company')

    op.drop_constraint('ck_chat_channel_members_role', 'chat_channel_members', schema='company', type_='check')
    op.drop_column('chat_channel_members', 'role', schema='company')

    op.drop_constraint('ck_agents_default_role', 'agents', schema='company', type_='check')
    op.drop_column('agents', 'default_role', schema='company')

    op.drop_constraint('ck_project_agent_memberships_role', 'project_agent_memberships', schema='company', type_='check')
    op.create_check_constraint(
        'ck_project_agent_memberships_role',
        'project_agent_memberships',
        "role IN ('coordinator', 'planner', 'architect', 'designer', 'developer', "
        "'data_engineer', 'qa', 'security_reviewer', 'reviewer', 'release_manager')",
        schema='company',
    )
