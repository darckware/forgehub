"""SQLAlchemy models for the Mission domain (Plano Integrado M0.0).

A mission is a Project with ``project_type='mission'`` plus a 1:1 extension
row in ``project_missions`` that holds the mission's single state machine
(docs/architecture/MCP_MISSION_TOOLS_SPEC.md §2-§3). ``Project.status`` is
only a projection of ``ProjectMission.state``, written in the same
transaction by ``POST /api/v1/missions/{id}:transition``; nothing infers a
mission's state from ``Project.status``.

Tables owned by this domain:
- project_missions             (§2.2, §3.1 planning pipeline columns)
- mission_project_links        (§2.3, coordinator -> executor projects)
- mission_acceptance_criteria  (§2.4)
- mission_criterion_tasks      (§2.4)
- mission_decisions            (MISSION_ORCHESTRATOR_CYCLE_SPEC.md §4)
- mission_plan_versions, mission_plan_reviews, mission_review_waivers,
  mission_review_items, mission_plan_verifications, mission_dossiers
                               (§2.6, M0.0b planning records)
- mission_plan_submissions     (§5.3/§7, M0.2b governed plan approval)

Cross-domain FKs are string-form, per the foundation convention.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

MISSION_STATES = (
    "draft", "planning", "ready", "active", "verifying",
    "awaiting_acceptance", "paused", "completed", "cancelled",
)
MISSION_TERMINAL_STATES = ("completed", "cancelled")

# Mission state -> Project.status, written in the same transaction (§3).
MISSION_STATUS_PROJECTION = {
    "draft": "planned",
    "planning": "planned",
    "ready": "planned",
    "active": "active",
    "verifying": "active",
    "awaiting_acceptance": "active",
    "paused": "on_hold",
    "completed": "completed",
    "cancelled": "cancelled",
}

AUTONOMY_LEVELS = ("N0", "N1", "N2", "N3")

# Planning pipeline inside `planning` (§3.1, 04 "Validação do plano" P1-P8).
# Order matters: a stage only advances to the next one.
PLANNING_STAGES = (
    "draft_plan", "auto_check", "critical_review", "consolidation",
    "cross_review", "decisions", "application", "baseline",
)
MISSION_RISK_LEVELS = ("low", "medium", "high")
REVIEW_LAYERS = (
    "architecture", "backend", "frontend", "security", "lgpd",
    "infrastructure", "documentation", "business",
)

CRITERION_STATUSES = ("open", "proven", "failed")

# Cycle spec §4 plus `advance_planning` (M0.0 records every planning stage
# change here, §3.1; the cycle's own actions arrive with M0.8).
MISSION_DECISION_ACTIONS = (
    "dispatch", "schedule", "reassign", "request_review", "return", "reprocess",
    "integrate", "reverify", "ask_marcelo", "pause", "defer", "undo", "lock",
    "unlock", "advance_planning",
)
MISSION_DECISION_STATUSES = ("applied", "refused", "deferred", "undone")

# Planning records (§2.6, M0.0b).
PRINCIPAL_TYPES = ("user", "agent")
PLAN_REVIEW_KINDS = ("layer", "cross")
REVIEW_DISPOSITIONS = ("accept", "adjust", "reject")
PLAN_VERIFICATION_RESULTS = ("confirmed", "discrepancies")


def _in(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


class ProjectMission(Base, TimestampMixin):
    """1:1 extension of a mission Project: the mission's state machine."""

    __tablename__ = "project_missions"
    __table_args__ = (
        CheckConstraint(f"state IN {_in(MISSION_STATES)}", name="ck_project_missions_state"),
        CheckConstraint(
            "(state = 'paused') = (paused_from_state IS NOT NULL)",
            name="ck_project_missions_paused_from_state",
        ),
        CheckConstraint(
            f"paused_from_state IS NULL OR paused_from_state IN {_in(MISSION_STATES)}",
            name="ck_project_missions_paused_from_state_value",
        ),
        CheckConstraint("priority BETWEEN 1 AND 1000", name="ck_project_missions_priority"),
        CheckConstraint(
            f"autonomy_level IN {_in(AUTONOMY_LEVELS)}", name="ck_project_missions_autonomy_level"
        ),
        CheckConstraint(
            f"planning_stage IS NULL OR planning_stage IN {_in(PLANNING_STAGES)}",
            name="ck_project_missions_planning_stage",
        ),
        CheckConstraint(
            f"risk_level IS NULL OR risk_level IN {_in(MISSION_RISK_LEVELS)}",
            name="ck_project_missions_risk_level",
        ),
        CheckConstraint(
            f"required_review_layers <@ ARRAY{list(REVIEW_LAYERS)!r}::varchar[]",
            name="ck_project_missions_review_layers",
        ),
        CheckConstraint("paused_seconds >= 0", name="ck_project_missions_paused_seconds"),
        Index("ix_project_missions_orchestrator_state", "orchestrator_agent_id", "state"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.projects.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    state: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    paused_from_state: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Lower = more urgent (cycle spec §6.1).
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100, server_default="100")
    orchestrator_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id"), nullable=False
    )
    # Routes refuse anything but N0 in Onda 1 (08 "Onda 1 opera em N0").
    autonomy_level: Mapped[str] = mapped_column(
        String(2), nullable=False, default="N0", server_default="N0"
    )
    brief_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.artifacts.id", ondelete="SET NULL"), nullable=True
    )
    current_baseline_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.plan_baselines.id", ondelete="SET NULL"), nullable=True
    )
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    budget_limit: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    paused_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    state_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    state_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    acceptance_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.approval_requests.id", ondelete="SET NULL"), nullable=True
    )
    # Only meaningful while state='planning'; set to draft_plan on entering it.
    planning_stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Fixed in P1 (draft_plan) and locked afterwards (change request to alter).
    risk_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    required_review_layers: Mapped[list[str]] = mapped_column(
        ARRAY(String(20)), nullable=False, default=list, server_default="{}"
    )
    # Optimistic lock: every transition/advance sends expected_row_version.
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


class MissionProjectLink(Base, TimestampMixin):
    """Coordinator mission -> executor project (D-3). An executor project may
    serve several missions; a mission is never an executor (no nesting in M0)."""

    __tablename__ = "mission_project_links"
    __table_args__ = (
        UniqueConstraint(
            "mission_project_id", "executor_project_id", name="uq_mission_project_links_pair"
        ),
        CheckConstraint(
            "mission_project_id <> executor_project_id", name="ck_mission_project_links_distinct"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mission_project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.projects.id", ondelete="CASCADE"), nullable=False
    )
    executor_project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.projects.id", ondelete="RESTRICT"), nullable=False
    )
    linked_by: Mapped[str] = mapped_column(String(150), nullable=False)


class MissionAcceptanceCriterion(Base, TimestampMixin):
    __tablename__ = "mission_acceptance_criteria"
    __table_args__ = (
        UniqueConstraint("mission_project_id", "code", name="uq_mission_acceptance_criteria_code"),
        CheckConstraint(
            "(verifier_agent_id IS NOT NULL) <> verifier_is_marcelo",
            name="ck_mission_acceptance_criteria_one_verifier",
        ),
        CheckConstraint(
            f"status IN {_in(CRITERION_STATUSES)}", name="ck_mission_acceptance_criteria_status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mission_project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.projects.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    verification_method: Mapped[str] = mapped_column(Text, nullable=False)
    verifier_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id"), nullable=True
    )
    verifier_is_marcelo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", server_default="open")
    evidence_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(150), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MissionCriterionTask(Base, TimestampMixin):
    """Route rule: the task belongs to the mission or to a linked executor project."""

    __tablename__ = "mission_criterion_tasks"
    __table_args__ = (
        UniqueConstraint("criterion_id", "task_id", name="uq_mission_criterion_tasks_pair"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    criterion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.mission_acceptance_criteria.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.project_tasks.id", ondelete="RESTRICT"), nullable=False
    )


class MissionDecision(Base, TimestampMixin):
    """One recorded decision on a mission, applied or refused (cycle spec §4).

    M0.0 writes only ``advance_planning`` rows; refused attempts are recorded
    too, with the guard's code in ``refusal_code``."""

    __tablename__ = "mission_decisions"
    __table_args__ = (
        CheckConstraint(
            f"action IN {_in(MISSION_DECISION_ACTIONS)}", name="ck_mission_decisions_action"
        ),
        CheckConstraint(
            f"status IN {_in(MISSION_DECISION_STATUSES)}", name="ck_mission_decisions_status"
        ),
        CheckConstraint(
            f"autonomy_level IN {_in(AUTONOMY_LEVELS)}", name="ck_mission_decisions_autonomy_level"
        ),
        CheckConstraint("length(btrim(reason)) > 0", name="ck_mission_decisions_reason"),
        UniqueConstraint(
            "actor_type", "actor_id", "idempotency_key", name="uq_mission_decisions_actor_key"
        ),
        Index("ix_mission_decisions_mission", "mission_project_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mission_project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.projects.id", ondelete="CASCADE"), nullable=False
    )
    cycle_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.project_tasks.id", ondelete="SET NULL"), nullable=True
    )
    demand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agent_demands.id", ondelete="SET NULL"), nullable=True
    )
    review_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.task_execution_reviews.id", ondelete="SET NULL"),
        nullable=True,
    )
    question_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agent_questions.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    facts: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    autonomy_level: Mapped[str] = mapped_column(String(2), nullable=False, default="N0")
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    actor_name: Mapped[str] = mapped_column(String(150), nullable=False)
    authority_source: Mapped[str] = mapped_column(String(30), nullable=False)
    delegation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.authority_delegations.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    refusal_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    undone_by_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.mission_decisions.id", ondelete="SET NULL"), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(150), nullable=False)


# ---------------------------------------------------------------------------
# Planning records (§2.6, M0.0b). Every record carries the plan version it was
# written against; only the current version's records count for a stage exit.
# ---------------------------------------------------------------------------
class MissionPlanVersion(Base, TimestampMixin):
    """The author of a mission's ProjectPlan version (ProjectPlan has none).
    The author and the orchestrator are the plan's planners (§2.6)."""

    __tablename__ = "mission_plan_versions"
    __table_args__ = (
        CheckConstraint(f"author_type IN {_in(PRINCIPAL_TYPES)}", name="ck_mission_plan_versions_author_type"),
    )

    project_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.project_plans.id", ondelete="CASCADE"), primary_key=True
    )
    mission_project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.projects.id", ondelete="CASCADE"), nullable=False
    )
    author_type: Mapped[str] = mapped_column(String(10), nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    author_name: Mapped[str] = mapped_column(String(150), nullable=False)


class MissionPlanReview(Base, TimestampMixin):
    """A reviewer's opinion on one plan version: per layer (P3) or cross (P5).
    The reviewer is always the authenticated agent."""

    __tablename__ = "mission_plan_reviews"
    __table_args__ = (
        CheckConstraint(f"kind IN {_in(PLAN_REVIEW_KINDS)}", name="ck_mission_plan_reviews_kind"),
        CheckConstraint(f"layer IN {_in(REVIEW_LAYERS)}", name="ck_mission_plan_reviews_layer"),
        UniqueConstraint(
            "project_plan_id", "kind", "layer", "reviewer_agent_id", name="uq_mission_plan_reviews_reviewer"
        ),
        Index("ix_mission_plan_reviews_plan", "project_plan_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mission_project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.projects.id", ondelete="CASCADE"), nullable=False
    )
    project_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.project_plans.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    layer: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewer_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id"), nullable=False
    )
    artifact_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.artifact_versions.id"), nullable=False
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class MissionReviewWaiver(Base, TimestampMixin):
    """Marcelo's recorded decision that a required layer goes without an opinion."""

    __tablename__ = "mission_review_waivers"
    __table_args__ = (
        CheckConstraint(f"layer IN {_in(REVIEW_LAYERS)}", name="ck_mission_review_waivers_layer"),
        CheckConstraint("length(btrim(reason)) > 0", name="ck_mission_review_waivers_reason"),
        UniqueConstraint("project_plan_id", "layer", name="uq_mission_review_waivers_layer"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mission_project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.projects.id", ondelete="CASCADE"), nullable=False
    )
    project_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.project_plans.id", ondelete="CASCADE"), nullable=False
    )
    layer: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    decided_by: Mapped[str] = mapped_column(String(150), nullable=False)
    decided_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.users.id"), nullable=False
    )


class MissionReviewItem(Base, TimestampMixin):
    """One point a review raised, its disposition (P4) and, when flagged,
    Marcelo's decision (P6). Effective disposition = Marcelo's when set."""

    __tablename__ = "mission_review_items"
    __table_args__ = (
        CheckConstraint("length(btrim(text)) > 0", name="ck_mission_review_items_text"),
        CheckConstraint(
            f"disposition IS NULL OR disposition IN {_in(REVIEW_DISPOSITIONS)}",
            name="ck_mission_review_items_disposition",
        ),
        CheckConstraint(
            "(disposition IS NULL) = (disposition_reason IS NULL) "
            "AND (disposition_reason IS NULL OR length(btrim(disposition_reason)) > 0)",
            name="ck_mission_review_items_disposition_reason",
        ),
        CheckConstraint(
            f"marcelo_decision IS NULL OR (needs_marcelo_decision AND marcelo_decision IN "
            f"{_in(REVIEW_DISPOSITIONS)})",
            name="ck_mission_review_items_marcelo_decision",
        ),
        CheckConstraint(
            "(marcelo_decision IS NULL) = (marcelo_reason IS NULL) "
            "AND (marcelo_decision IS NULL) = (marcelo_decided_by IS NULL) "
            "AND (marcelo_decision IS NULL) = (marcelo_user_id IS NULL) "
            "AND (marcelo_decision IS NULL) = (marcelo_decided_at IS NULL) "
            "AND (marcelo_reason IS NULL OR length(btrim(marcelo_reason)) > 0)",
            name="ck_mission_review_items_marcelo_fields",
        ),
        Index("ix_mission_review_items_review", "review_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.mission_plan_reviews.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    disposition: Mapped[str | None] = mapped_column(String(10), nullable=True)
    disposition_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    disposed_by: Mapped[str | None] = mapped_column(String(150), nullable=True)
    disposed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    needs_marcelo_decision: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    marcelo_decision: Mapped[str | None] = mapped_column(String(10), nullable=True)
    marcelo_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    marcelo_decided_by: Mapped[str | None] = mapped_column(String(150), nullable=True)
    marcelo_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.users.id"), nullable=True
    )
    marcelo_decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MissionPlanVerification(Base, TimestampMixin):
    """An independent verifier's check that sampled corrections are in the text (P7)."""

    __tablename__ = "mission_plan_verifications"
    __table_args__ = (
        CheckConstraint(
            f"result IN {_in(PLAN_VERIFICATION_RESULTS)}", name="ck_mission_plan_verifications_result"
        ),
        Index("ix_mission_plan_verifications_plan", "project_plan_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mission_project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.projects.id", ondelete="CASCADE"), nullable=False
    )
    project_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.project_plans.id", ondelete="CASCADE"), nullable=False
    )
    verifier_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id"), nullable=False
    )
    sampled_item_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list, server_default="{}"
    )
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class MissionDossier(Base, TimestampMixin):
    """The dossier artifact version and file hash registered while verifying (§8 item 1)."""

    __tablename__ = "mission_dossiers"
    __table_args__ = (
        CheckConstraint("file_sha256 ~ '^[0-9a-f]{64}$'", name="ck_mission_dossiers_file_sha256"),
        CheckConstraint(
            f"registered_by_type IN {_in(PRINCIPAL_TYPES)}", name="ck_mission_dossiers_registered_by_type"
        ),
        Index("ix_mission_dossiers_mission", "mission_project_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mission_project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.projects.id", ondelete="CASCADE"), nullable=False
    )
    artifact_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.artifact_versions.id"), nullable=False
    )
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    registered_by_type: Mapped[str] = mapped_column(String(10), nullable=False)
    registered_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    registered_by: Mapped[str] = mapped_column(String(150), nullable=False)


# ---------------------------------------------------------------------------
# Governed plan approval (§5.3, §7, M0.2b)
# ---------------------------------------------------------------------------
class MissionPlanSubmission(Base, TimestampMixin):
    """What a submit_project_plan put up for Marcelo's approval: one row per
    governed ``ApprovalRequest(target_type='project_plan')``. ``task_ids`` are
    the tasks the baseline will authorize and ``plan_hash`` covers the plan
    and each task's content as the baseline would freeze it, so the decision
    recomputes it and refuses a plan that changed after submission."""

    __tablename__ = "mission_plan_submissions"
    __table_args__ = (
        CheckConstraint(f"submitted_by_type IN {_in(PRINCIPAL_TYPES)}",
                        name="ck_mission_plan_submissions_submitted_by_type"),
        CheckConstraint("cardinality(task_ids) > 0", name="ck_mission_plan_submissions_task_ids"),
        Index("ix_mission_plan_submissions_mission", "mission_project_id", "created_at"),
    )

    approval_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.approval_requests.id", ondelete="CASCADE"), primary_key=True
    )
    mission_project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.projects.id", ondelete="CASCADE"), nullable=False
    )
    project_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.project_plans.id", ondelete="CASCADE"), nullable=False
    )
    change_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.change_requests.id", ondelete="SET NULL"), nullable=True
    )
    task_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False)
    plan_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    checks: Mapped[list] = mapped_column(JSONB, nullable=False)
    submitted_by_type: Mapped[str] = mapped_column(String(10), nullable=False)
    submitted_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    submitted_by: Mapped[str] = mapped_column(String(150), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(150), nullable=True)
    # The baseline the approval created (set once, by the decision).
    baseline_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.plan_baselines.id", ondelete="SET NULL"), nullable=True
    )
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    withdrawn_by: Mapped[str | None] = mapped_column(String(150), nullable=True)
    withdrawn_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
