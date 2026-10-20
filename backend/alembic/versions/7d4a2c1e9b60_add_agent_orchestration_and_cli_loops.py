"""add agent orchestration and governed CLI loops

Revision ID: 7d4a2c1e9b60
Revises: 56d8b83f8286
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "7d4a2c1e9b60"
down_revision: Union[str, Sequence[str], None] = "56d8b83f8286"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_runtime_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sub_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("runtime_type", sa.String(length=20), nullable=False),
        sa.Column("model_ref", sa.String(length=255), nullable=False),
        sa.Column("purpose", sa.String(length=30), nullable=False),
        sa.Column("intelligence_level", sa.Integer(), nullable=False),
        sa.Column("capability_scope", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("max_budget_usd", sa.Numeric(12, 4), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "((agent_id IS NOT NULL)::int + (sub_agent_id IS NOT NULL)::int) = 1",
            name="ck_agent_runtime_profiles_exactly_one_owner",
        ),
        sa.CheckConstraint(
            "runtime_type IN ('claude', 'codex', 'antigravity')",
            name="ck_agent_runtime_profiles_runtime",
        ),
        sa.CheckConstraint(
            "purpose IN ('general', 'draft', 'review', 'implementation', 'testing')",
            name="ck_agent_runtime_profiles_purpose",
        ),
        sa.CheckConstraint(
            "intelligence_level BETWEEN 1 AND 5",
            name="ck_agent_runtime_profiles_intelligence",
        ),
        sa.CheckConstraint(
            "max_budget_usd IS NULL OR max_budget_usd >= 0",
            name="ck_agent_runtime_profiles_budget_nonnegative",
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["company.agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sub_agent_id"], ["company.sub_agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "name", name="uq_agent_runtime_profiles_agent_name"),
        sa.UniqueConstraint(
            "sub_agent_id", "name", name="uq_agent_runtime_profiles_sub_agent_name"
        ),
        schema="company",
    )

    op.create_table(
        "project_agent_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sub_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("responsibilities", sa.Text(), nullable=True),
        sa.Column("allowed_runtimes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("allocation_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("max_concurrent_tasks_override", sa.Integer(), nullable=True),
        sa.Column("can_review", sa.Boolean(), nullable=False),
        sa.Column("can_approve", sa.Boolean(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "((agent_id IS NOT NULL)::int + (sub_agent_id IS NOT NULL)::int) = 1",
            name="ck_project_agent_memberships_exactly_one_member",
        ),
        sa.CheckConstraint(
            "role IN ('coordinator', 'planner', 'architect', 'designer', 'developer', "
            "'data_engineer', 'qa', 'security_reviewer', 'reviewer', 'release_manager')",
            name="ck_project_agent_memberships_role",
        ),
        sa.CheckConstraint(
            "status IN ('proposed', 'active', 'suspended', 'released')",
            name="ck_project_agent_memberships_status",
        ),
        sa.CheckConstraint(
            "allocation_percent > 0 AND allocation_percent <= 100",
            name="ck_project_agent_memberships_allocation",
        ),
        sa.CheckConstraint(
            "max_concurrent_tasks_override IS NULL OR max_concurrent_tasks_override >= 1",
            name="ck_project_agent_memberships_capacity",
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_project_agent_memberships_dates",
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["company.agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["company.projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sub_agent_id"], ["company.sub_agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "agent_id", name="uq_project_agent_memberships_agent"),
        sa.UniqueConstraint(
            "project_id", "sub_agent_id", name="uq_project_agent_memberships_sub_agent"
        ),
        schema="company",
    )

    op.create_table(
        "project_loop_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("phase", sa.String(length=30), nullable=False),
        sa.Column("producer_membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("producer_runtime_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_runtime_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("max_iterations", sa.Integer(), nullable=False),
        sa.Column("min_review_score", sa.Integer(), nullable=False),
        sa.Column("requires_human_approval", sa.Boolean(), nullable=False),
        sa.Column("auto_dispatch", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "phase IN ('documentation', 'planning', 'implementation', 'testing', 'review')",
            name="ck_project_loop_policies_phase",
        ),
        sa.CheckConstraint(
            "max_iterations BETWEEN 1 AND 20", name="ck_project_loop_policies_iterations"
        ),
        sa.CheckConstraint(
            "min_review_score BETWEEN 0 AND 100", name="ck_project_loop_policies_score"
        ),
        sa.CheckConstraint(
            "producer_membership_id <> reviewer_membership_id",
            name="ck_project_loop_policies_separation",
        ),
        sa.ForeignKeyConstraint(
            ["producer_membership_id"],
            ["company.project_agent_memberships.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["producer_runtime_profile_id"],
            ["company.agent_runtime_profiles.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["company.projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["reviewer_membership_id"],
            ["company.project_agent_memberships.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_runtime_profile_id"],
            ["company.agent_runtime_profiles.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", name="uq_project_loop_policies_project_name"),
        schema="company",
    )

    op.add_column(
        "task_assignments",
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="company",
    )
    op.create_foreign_key(
        "fk_task_assignments_membership_id",
        "task_assignments",
        "project_agent_memberships",
        ["membership_id"],
        ["id"],
        source_schema="company",
        referent_schema="company",
        ondelete="SET NULL",
    )

    for column in (
        sa.Column("runtime_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("loop_policy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("parent_execution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("runtime_type", sa.String(length=20), nullable=True),
        sa.Column("runtime_session_ref", sa.String(length=255), nullable=True),
        sa.Column("loop_iteration", sa.Integer(), nullable=False, server_default="1"),
    ):
        op.add_column("task_executions", column, schema="company")
    op.create_check_constraint(
        "ck_task_executions_runtime_type",
        "task_executions",
        "runtime_type IS NULL OR runtime_type IN ('claude', 'codex', 'antigravity')",
        schema="company",
    )
    op.create_check_constraint(
        "ck_task_executions_loop_iteration",
        "task_executions",
        "loop_iteration >= 1",
        schema="company",
    )
    op.create_foreign_key(
        "fk_task_executions_runtime_profile_id",
        "task_executions",
        "agent_runtime_profiles",
        ["runtime_profile_id"],
        ["id"],
        source_schema="company",
        referent_schema="company",
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_task_executions_loop_policy_id",
        "task_executions",
        "project_loop_policies",
        ["loop_policy_id"],
        ["id"],
        source_schema="company",
        referent_schema="company",
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_task_executions_parent_execution_id",
        "task_executions",
        "task_executions",
        ["parent_execution_id"],
        ["id"],
        source_schema="company",
        referent_schema="company",
        ondelete="SET NULL",
    )

    op.create_table(
        "task_execution_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("runtime_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("evidence_ref", sa.String(length=500), nullable=True),
        sa.Column("runtime_session_ref", sa.String(length=255), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'approved', 'changes_requested', 'rejected', 'failed')",
            name="ck_task_execution_reviews_status",
        ),
        sa.CheckConstraint(
            "score IS NULL OR score BETWEEN 0 AND 100",
            name="ck_task_execution_reviews_score",
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"], ["company.task_executions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_membership_id"],
            ["company.project_agent_memberships.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["runtime_profile_id"], ["company.agent_runtime_profiles.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="company",
    )


def downgrade() -> None:
    op.drop_table("task_execution_reviews", schema="company")
    op.drop_constraint(
        "fk_task_executions_parent_execution_id", "task_executions", schema="company", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_task_executions_loop_policy_id", "task_executions", schema="company", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_task_executions_runtime_profile_id", "task_executions", schema="company", type_="foreignkey"
    )
    op.drop_constraint(
        "ck_task_executions_loop_iteration", "task_executions", schema="company", type_="check"
    )
    op.drop_constraint(
        "ck_task_executions_runtime_type", "task_executions", schema="company", type_="check"
    )
    for column in (
        "loop_iteration",
        "runtime_session_ref",
        "runtime_type",
        "parent_execution_id",
        "loop_policy_id",
        "runtime_profile_id",
    ):
        op.drop_column("task_executions", column, schema="company")
    op.drop_constraint(
        "fk_task_assignments_membership_id", "task_assignments", schema="company", type_="foreignkey"
    )
    op.drop_column("task_assignments", "membership_id", schema="company")
    op.drop_table("project_loop_policies", schema="company")
    op.drop_table("project_agent_memberships", schema="company")
    op.drop_table("agent_runtime_profiles", schema="company")
