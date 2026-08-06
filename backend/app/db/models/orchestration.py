"""Agent/project orchestration models.

This domain connects the global Agent catalog to a concrete Project and keeps
the logical agent separate from the CLI/model runtime used for an execution.
It also stores the bounded producer/reviewer loop policy used by planning,
documentation, implementation, and verification work.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

RUNTIME_TYPES = ("claude", "codex", "agy")
RUNTIME_PURPOSES = ("general", "draft", "review", "implementation", "testing")
MEMBERSHIP_STATUSES = ("proposed", "active", "suspended", "released")
PROJECT_AGENT_ROLES = (
    "coordinator",
    "planner",
    "architect",
    "designer",
    "developer",
    "data_engineer",
    "qa",
    "security_reviewer",
    "reviewer",
    "release_manager",
    # 2026-08-05: added for the channel/agent-function pass -- see
    # docs/architecture/CHANNEL_AGENT_ROLES_AND_ORCHESTRATION.md. This same
    # tuple is now also imported (not duplicated) by db/models/agent.py
    # (Agent.default_role) and db/models/channel.py (ChatChannelMember.role)
    # so the ForgeHub-wide "what does this agent do" vocabulary never
    # drifts into three versions.
    "documentation",
)
LOOP_PHASES = ("documentation", "planning", "implementation", "testing", "review")
REVIEW_STATUSES = ("pending", "running", "approved", "changes_requested", "rejected", "failed")
FORGEROUTER_ROUTING_GROUPS = (
    "auto", "simple", "standard", "complex", "reasoning", "vision", "audio", "code"
)


class AgentRuntimeProfile(Base, TimestampMixin):
    """One ForgeRouter-backed CLI/model profile owned by an Agent/SubAgent."""

    __tablename__ = "agent_runtime_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id", ondelete="CASCADE"), nullable=True
    )
    sub_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.sub_agents.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    runtime_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # ForgeRouter model identifier. "forgerouter/auto" delegates model
    # selection to the router; a concrete identifier pins the profile.
    model_ref: Mapped[str] = mapped_column(String(255), nullable=False, default="forgerouter/auto")
    # Semantic ForgeRouter virtual model used when model_ref is auto. Keeping
    # this separate from a concrete model pin makes profiles portable as the
    # router's provider catalog changes.
    routing_group: Mapped[str] = mapped_column(String(32), nullable=False, default="auto")
    purpose: Mapped[str] = mapped_column(String(30), nullable=False, default="general")
    intelligence_level: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    capability_scope: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    max_budget_usd: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint(
            "((agent_id IS NOT NULL)::int + (sub_agent_id IS NOT NULL)::int) = 1",
            name="ck_agent_runtime_profiles_exactly_one_owner",
        ),
        CheckConstraint(f"runtime_type IN {RUNTIME_TYPES}", name="ck_agent_runtime_profiles_runtime"),
        CheckConstraint(f"purpose IN {RUNTIME_PURPOSES}", name="ck_agent_runtime_profiles_purpose"),
        CheckConstraint(
            f"routing_group IN {FORGEROUTER_ROUTING_GROUPS}",
            name="ck_agent_runtime_profiles_routing_group",
        ),
        CheckConstraint(
            "intelligence_level BETWEEN 1 AND 5",
            name="ck_agent_runtime_profiles_intelligence",
        ),
        CheckConstraint(
            "max_budget_usd IS NULL OR max_budget_usd >= 0",
            name="ck_agent_runtime_profiles_budget_nonnegative",
        ),
        UniqueConstraint("agent_id", "name", name="uq_agent_runtime_profiles_agent_name"),
        UniqueConstraint("sub_agent_id", "name", name="uq_agent_runtime_profiles_sub_agent_name"),
    )


class ProjectAgentMembership(Base, TimestampMixin):
    """Authorization and allocation of one registered agent in one project."""

    __tablename__ = "project_agent_memberships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.projects.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id", ondelete="CASCADE"), nullable=True
    )
    sub_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.sub_agents.id", ondelete="CASCADE"), nullable=True
    )
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    responsibilities: Mapped[str | None] = mapped_column(Text, nullable=True)
    allowed_runtimes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    allocation_percent: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=lambda: Decimal("100.00")
    )
    max_concurrent_tasks_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    can_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_approve: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "((agent_id IS NOT NULL)::int + (sub_agent_id IS NOT NULL)::int) = 1",
            name="ck_project_agent_memberships_exactly_one_member",
        ),
        CheckConstraint(f"role IN {PROJECT_AGENT_ROLES}", name="ck_project_agent_memberships_role"),
        CheckConstraint(
            f"status IN {MEMBERSHIP_STATUSES}", name="ck_project_agent_memberships_status"
        ),
        CheckConstraint(
            "allocation_percent > 0 AND allocation_percent <= 100",
            name="ck_project_agent_memberships_allocation",
        ),
        CheckConstraint(
            "max_concurrent_tasks_override IS NULL OR max_concurrent_tasks_override >= 1",
            name="ck_project_agent_memberships_capacity",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_project_agent_memberships_dates",
        ),
        UniqueConstraint("project_id", "agent_id", name="uq_project_agent_memberships_agent"),
        UniqueConstraint("project_id", "sub_agent_id", name="uq_project_agent_memberships_sub_agent"),
    )


class ProjectLoopPolicy(Base, TimestampMixin):
    """Bounded producer/reviewer loop for one phase of a project."""

    __tablename__ = "project_loop_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    phase: Mapped[str] = mapped_column(String(30), nullable=False)
    producer_membership_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.project_agent_memberships.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reviewer_membership_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.project_agent_memberships.id", ondelete="RESTRICT"),
        nullable=False,
    )
    producer_runtime_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agent_runtime_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    reviewer_runtime_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agent_runtime_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    max_iterations: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    min_review_score: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    requires_human_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auto_dispatch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_project_loop_policies_project_name"),
        CheckConstraint(f"phase IN {LOOP_PHASES}", name="ck_project_loop_policies_phase"),
        CheckConstraint("max_iterations BETWEEN 1 AND 20", name="ck_project_loop_policies_iterations"),
        CheckConstraint("min_review_score BETWEEN 0 AND 100", name="ck_project_loop_policies_score"),
        CheckConstraint(
            "producer_membership_id <> reviewer_membership_id",
            name="ck_project_loop_policies_separation",
        ),
    )


class TaskExecutionReview(Base, TimestampMixin):
    """Human or model-assisted review of one concrete TaskExecution."""

    __tablename__ = "task_execution_reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.task_executions.id", ondelete="CASCADE"), nullable=False
    )
    reviewer_membership_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.project_agent_memberships.id", ondelete="RESTRICT"),
        nullable=False,
    )
    runtime_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agent_runtime_profiles.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    runtime_session_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(f"status IN {REVIEW_STATUSES}", name="ck_task_execution_reviews_status"),
        CheckConstraint("score IS NULL OR score BETWEEN 0 AND 100", name="ck_task_execution_reviews_score"),
    )
