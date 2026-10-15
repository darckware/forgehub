"""Remove OpenClaw: no longer an agent runtime nor a monitored tool

Marcelo, 2026-10-14: "remova o openclaw do forgehub". OpenClaw was uninstalled and Vector (its only
agent) retired on 2026-10-12. Vector's row stays (retire, never delete) with runtime_type NULL.

Revision ID: a7c2e9f41b85
Revises: f3b8d2a61c47
Create Date: 2026-10-14
"""
from alembic import op

revision = "a7c2e9f41b85"
down_revision = "f3b8d2a61c47"
branch_labels = None
depends_on = None

SCHEMA = "company"


def upgrade() -> None:
    op.execute("UPDATE company.agents SET runtime_type = NULL WHERE runtime_type = 'openclaw'")
    op.execute("DELETE FROM company.tool_version_status WHERE tool = 'openclaw'")
    op.drop_constraint("ck_agents_runtime_type", "agents", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_agents_runtime_type",
        "agents",
        "runtime_type IS NULL OR runtime_type IN ('claude', 'codex', 'agy', 'hermes')",
        schema=SCHEMA,
    )
    op.drop_constraint("ck_tool_version_status_tool", "tool_version_status", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_tool_version_status_tool",
        "tool_version_status",
        "tool IN ('hermes', 'claude', 'codex', 'antigravity', 'pi', 'opencode')",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint("ck_agents_runtime_type", "agents", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_agents_runtime_type",
        "agents",
        "runtime_type IS NULL OR runtime_type IN ('claude', 'codex', 'agy', 'hermes', 'openclaw')",
        schema=SCHEMA,
    )
    op.drop_constraint("ck_tool_version_status_tool", "tool_version_status", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_tool_version_status_tool",
        "tool_version_status",
        "tool IN ('hermes', 'claude', 'codex', 'antigravity', 'pi', 'opencode', 'openclaw')",
        schema=SCHEMA,
    )
