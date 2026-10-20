"""add compliance and knowledge_management to PROJECT_AGENT_ROLES

Revision ID: f4b8d1a6c3e9
Revises: e7a1f2c9b4d6
Create Date: 2026-08-06 05:30:00.000000

Hand-written (not autogenerate), same rationale as the prior channel
migrations: avoids sweeping in pre-existing unrelated model/DB drift. Same
pattern as 3cad0134cf1b (which added "documentation") -- recreates the four
CHECK constraints that all reference PROJECT_AGENT_ROLES so the vocabulary
never drifts into separate copies. See
docs/guides/FORGEHUB_CHANNELS_AGENT_GUIDE.md §8 for why: Themis
(legal/compliance) and Mnemosyne (knowledge base/RAG) had no function that
fit when staffing the "Projeto ForgeHub" channel.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f4b8d1a6c3e9'
down_revision: Union[str, Sequence[str], None] = 'e7a1f2c9b4d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# PROJECT_AGENT_ROLES (backend/app/db/models/orchestration.py), extended
# with "compliance" and "knowledge_management" -- the single shared
# function vocabulary reused by agents.default_role, chat_channel_members.
# role, chat_channel_tasks.role_required, and project_agent_memberships.role.
PROJECT_AGENT_ROLES = (
    "coordinator", "planner", "architect", "designer", "developer",
    "data_engineer", "qa", "security_reviewer", "reviewer",
    "release_manager", "documentation", "compliance", "knowledge_management",
)

PREVIOUS_PROJECT_AGENT_ROLES = (
    "coordinator", "planner", "architect", "designer", "developer",
    "data_engineer", "qa", "security_reviewer", "reviewer",
    "release_manager", "documentation",
)


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(
        'ck_project_agent_memberships_role', 'project_agent_memberships', schema='company', type_='check'
    )
    op.create_check_constraint(
        'ck_project_agent_memberships_role',
        'project_agent_memberships',
        f"role IN {PROJECT_AGENT_ROLES!r}",
        schema='company',
    )

    op.drop_constraint('ck_agents_default_role', 'agents', schema='company', type_='check')
    op.create_check_constraint(
        'ck_agents_default_role',
        'agents',
        f"default_role IS NULL OR default_role IN {PROJECT_AGENT_ROLES!r}",
        schema='company',
    )

    op.drop_constraint('ck_chat_channel_members_role', 'chat_channel_members', schema='company', type_='check')
    op.create_check_constraint(
        'ck_chat_channel_members_role',
        'chat_channel_members',
        f"role IS NULL OR role IN {PROJECT_AGENT_ROLES!r}",
        schema='company',
    )

    op.drop_constraint(
        'ck_chat_channel_tasks_role_required', 'chat_channel_tasks', schema='company', type_='check'
    )
    op.create_check_constraint(
        'ck_chat_channel_tasks_role_required',
        'chat_channel_tasks',
        f"role_required IS NULL OR role_required IN {PROJECT_AGENT_ROLES!r}",
        schema='company',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        'ck_chat_channel_tasks_role_required', 'chat_channel_tasks', schema='company', type_='check'
    )
    op.create_check_constraint(
        'ck_chat_channel_tasks_role_required',
        'chat_channel_tasks',
        f"role_required IS NULL OR role_required IN {PREVIOUS_PROJECT_AGENT_ROLES!r}",
        schema='company',
    )

    op.drop_constraint('ck_chat_channel_members_role', 'chat_channel_members', schema='company', type_='check')
    op.create_check_constraint(
        'ck_chat_channel_members_role',
        'chat_channel_members',
        f"role IS NULL OR role IN {PREVIOUS_PROJECT_AGENT_ROLES!r}",
        schema='company',
    )

    op.drop_constraint('ck_agents_default_role', 'agents', schema='company', type_='check')
    op.create_check_constraint(
        'ck_agents_default_role',
        'agents',
        f"default_role IS NULL OR default_role IN {PREVIOUS_PROJECT_AGENT_ROLES!r}",
        schema='company',
    )

    op.drop_constraint(
        'ck_project_agent_memberships_role', 'project_agent_memberships', schema='company', type_='check'
    )
    op.create_check_constraint(
        'ck_project_agent_memberships_role',
        'project_agent_memberships',
        f"role IN {PREVIOUS_PROJECT_AGENT_ROLES!r}",
        schema='company',
    )
