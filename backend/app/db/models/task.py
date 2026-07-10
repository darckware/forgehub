"""SQLAlchemy models for the Task domain.

Tables owned by this module: project_tasks, task_dependencies,
task_required_skills, task_assignments, task_executions.

Foreign keys that point at tables owned by OTHER domains (planning_items,
agents, sub_agents, skills) are declared as plain string references
(ForeignKey("company.<table>.id")) rather than importing those domains'
model modules. This avoids import-order coupling between domain agents —
SQLAlchemy resolves string-based FKs lazily once every model module has
been imported (which happens centrally via app/db/models/__init__.py
during the wiring step).
"""
import uuid
from datetime import date, datetime

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
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# Lifecycle for a ProjectTask's own `status` column (distinct from any
# TaskAssignment/TaskExecution row's status -- business rule 6.4.1).
# "done" is the work-finished terminal state (dependency checks and the
# AuditEvent-on-completion rule in api/routes/task.py key off this exact
# string); "deployed" is a later, separate terminal state for "this task's
# deliverable has been released to production" -- added per user request to
# distinguish "finished" from "shipped".
TASK_STATUSES = (
    "planned",
    "assigned",
    "in_progress",
    "blocked",
    "done",
    "deployed",
    "cancelled",
)


class ProjectTask(Base, TimestampMixin):
    """A planned task or subtask within a project's plan.

    Subtasks reference their parent via `parent_task_id` (self-FK).
    `planning_item_id` links the task back to the planning item it was
    split from (owned by the Backlog domain) -- required, since a task
    with no traceable origin breaks the product->version->project->
    planning->task chain the CLAUDE.md core invariant demands. Enforced
    at the API layer (see create_task in app/api/routes/task.py), not as
    a DB-level NOT NULL, per the foundation convention that cross-row/
    existence checks belong at the route layer.
    """

    __tablename__ = "project_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    planning_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.planning_items.id", ondelete="CASCADE"), nullable=True
    )
    # Traceability: a task originates from a planning item OR a change request
    # (or both -- e.g. a CR adds scope that was previously a planning item).
    # At least one must be non-null at the API layer; see routes/task.py.
    change_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.change_requests.id", ondelete="SET NULL"), nullable=True
    )
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.project_tasks.id", ondelete="SET NULL"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # feature | bug | improvement | technical_debt | refactoring |
    # security_fix | research | documentation | other
    task_type: Mapped[str] = mapped_column(String(50), nullable=False, default="feature")

    # Business rule 6.4.1: planned, assigned, and executed must remain
    # distinct states -- status tracks the task's own lifecycle state,
    # separate from any TaskAssignment/TaskExecution row's own status.
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="planned")

    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")

    estimated_cost: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    actual_cost: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    planned_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Set once this task has been pushed to Kanboard (see
    # app/core/kanboard_client.py) -- an int because Kanboard's own task ids
    # are plain auto-increment integers, not UUIDs. Lets POST .../sync-kanboard
    # be idempotent: create on first sync, update/move on subsequent ones.
    kanboard_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Governance: optional link to the Policy this task is implementing.
    # Lets a Policy page show all tasks contributing to its compliance.
    policy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.policies.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(f"status IN {TASK_STATUSES!r}", name="ck_project_tasks_status"),
    )


class TaskDependency(Base, TimestampMixin):
    """A directed dependency: `task_id` depends on `depends_on_task_id`."""

    __tablename__ = "task_dependencies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.project_tasks.id", ondelete="CASCADE"), nullable=False
    )
    depends_on_task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.project_tasks.id", ondelete="CASCADE"), nullable=False
    )

    # finish_to_start | start_to_start | finish_to_finish | start_to_finish
    dependency_type: Mapped[str] = mapped_column(String(30), nullable=False, default="finish_to_start")


class TaskRequiredSkill(Base, TimestampMixin):
    """A skill (owned by the Agent domain) required to execute a task."""

    __tablename__ = "task_required_skills"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.project_tasks.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.skills.id"), nullable=False
    )

    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    minimum_proficiency: Mapped[str | None] = mapped_column(String(30), nullable=True)


class TaskAssignment(Base, TimestampMixin):
    """Assignment of a task to exactly one of: agent OR sub-agent.

    Business rule 6.4.1 (planned/assigned/executed stay distinct): this
    row represents the "assigned" state transition, separate from the
    task's own `status` and from any TaskExecution attempt.
    """

    __tablename__ = "task_assignments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.project_tasks.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id"), nullable=True
    )
    sub_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.sub_agents.id"), nullable=True
    )

    # active | released | revoked
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now()
    )
    unassigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TaskExecution(Base, TimestampMixin):
    """A single execution attempt of a task.

    Business rule 6.4.2/6.4.3: a task can have multiple executions, and
    every execution must have evidence (enforced at the route layer for
    terminal statuses -- see app/api/routes/task.py).
    """

    __tablename__ = "task_executions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.project_tasks.id", ondelete="CASCADE"), nullable=False
    )
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.task_assignments.id", ondelete="SET NULL"), nullable=True
    )

    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # agent | sub_agent | human | system
    executor_type: Mapped[str] = mapped_column(String(20), nullable=False, default="agent")

    # pending | running | failed | retried | verified | completed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    outcome_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    actual_cost: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
