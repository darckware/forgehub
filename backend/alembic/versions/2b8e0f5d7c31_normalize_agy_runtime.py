"""normalize agy runtime

Revision ID: 2b8e0f5d7c31
Revises: 1a7d9e4c6b20
"""
from typing import Sequence, Union

from alembic import op

revision: str = "2b8e0f5d7c31"
down_revision: Union[str, Sequence[str], None] = "1a7d9e4c6b20"
branch_labels = None
depends_on = None
SCHEMA = "company"


def upgrade() -> None:
    op.drop_constraint("ck_agent_runtime_profiles_runtime", "agent_runtime_profiles", schema=SCHEMA, type_="check")
    # The task-execution constraint must be removed before rewriting legacy
    # values; otherwise an upgrade with existing antigravity executions fails
    # before it can reach the replacement constraint.
    op.drop_constraint("ck_task_executions_runtime_type", "task_executions", schema=SCHEMA, type_="check")
    op.execute("UPDATE company.agent_runtime_profiles SET runtime_type = 'agy' WHERE runtime_type = 'antigravity'")
    op.execute("UPDATE company.project_agent_memberships SET allowed_runtimes = replace(allowed_runtimes::text, '\"antigravity\"', '\"agy\"')::jsonb WHERE allowed_runtimes IS NOT NULL AND allowed_runtimes::text LIKE '%antigravity%'")
    op.execute("UPDATE company.task_executions SET runtime_type = 'agy' WHERE runtime_type = 'antigravity'")
    op.create_check_constraint("ck_agent_runtime_profiles_runtime", "agent_runtime_profiles", "runtime_type IN ('claude','codex','agy')", schema=SCHEMA)
    op.create_check_constraint("ck_task_executions_runtime_type", "task_executions", "runtime_type IS NULL OR runtime_type IN ('claude','codex','agy')", schema=SCHEMA)


def downgrade() -> None:
    op.drop_constraint("ck_agent_runtime_profiles_runtime", "agent_runtime_profiles", schema=SCHEMA, type_="check")
    op.drop_constraint("ck_task_executions_runtime_type", "task_executions", schema=SCHEMA, type_="check")
    op.execute("UPDATE company.agent_runtime_profiles SET runtime_type = 'antigravity' WHERE runtime_type = 'agy'")
    op.execute("UPDATE company.project_agent_memberships SET allowed_runtimes = replace(allowed_runtimes::text, '\"agy\"', '\"antigravity\"')::jsonb WHERE allowed_runtimes IS NOT NULL AND allowed_runtimes::text LIKE '%agy%'")
    op.execute("UPDATE company.task_executions SET runtime_type = 'antigravity' WHERE runtime_type = 'agy'")
    op.create_check_constraint("ck_agent_runtime_profiles_runtime", "agent_runtime_profiles", "runtime_type IN ('claude','codex','antigravity')", schema=SCHEMA)
    op.create_check_constraint("ck_task_executions_runtime_type", "task_executions", "runtime_type IS NULL OR runtime_type IN ('claude','codex','antigravity')", schema=SCHEMA)
