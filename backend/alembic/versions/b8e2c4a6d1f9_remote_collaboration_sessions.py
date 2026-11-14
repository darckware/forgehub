"""Collaborative execution in an active session with Marcelo (inactive by default).

Revision ID: b8e2c4a6d1f9
Revises: 7c004e005d3c
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "b8e2c4a6d1f9"
down_revision = "7c004e005d3c"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "remote_collaboration_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_user_id", UUID(as_uuid=True), sa.ForeignKey("company.users.id"), nullable=False),
        sa.Column("user_session_id", UUID(as_uuid=True),
                  sa.ForeignKey("company.user_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("company.agents.id"), nullable=False),
        sa.Column("agent_demand_id", UUID(as_uuid=True), sa.ForeignKey("company.agent_demands.id"), nullable=False),
        sa.Column("agent_run_id", sa.String(64), nullable=False),
        sa.Column("server_id", UUID(as_uuid=True), sa.ForeignKey("company.servers.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("operation", sa.Text, nullable=False),
        sa.Column("allow_elevation", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("ended_by", sa.String(200)),
        sa.Column("end_reason", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('active','ended','revoked')", name="ck_remote_collaboration_session_status"),
        sa.CheckConstraint("length(btrim(operation)) > 0", name="ck_remote_collaboration_session_operation"),
        schema="company",
    )
    op.create_index("ix_remote_collaboration_sessions_agent_status", "remote_collaboration_sessions",
                    ["agent_id", "status"], schema="company")
    op.create_index("uq_remote_collaboration_sessions_one_active", "remote_collaboration_sessions", ["agent_id"],
                    unique=True, schema="company", postgresql_where=sa.text("status = 'active'"))
    op.create_table(
        "remote_collaboration_commands",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True),
                  sa.ForeignKey("company.remote_collaboration_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("command", sa.Text, nullable=False),
        sa.Column("shell", sa.String(20), nullable=False),
        sa.Column("command_sha256", sa.String(64), nullable=False),
        sa.Column("allow_elevation", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("authorized_by", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="authorized"),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("execution_id", UUID(as_uuid=True),
                  sa.ForeignKey("company.host_executions.id", ondelete="SET NULL"), unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('authorized','used','revoked')", name="ck_remote_collaboration_command_status"),
        sa.CheckConstraint("shell IN ('sh','powershell')", name="ck_remote_collaboration_command_shell"),
        schema="company",
    )
    op.create_index("ix_company_remote_collaboration_commands_session_id", "remote_collaboration_commands",
                    ["session_id"], schema="company")


def downgrade():
    op.drop_table("remote_collaboration_commands", schema="company")
    op.drop_table("remote_collaboration_sessions", schema="company")
