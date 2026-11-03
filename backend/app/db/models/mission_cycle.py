"""SQLAlchemy models for the orchestrator decision cycle (Plano Integrado M0.8).

Contract: docs/architecture/MISSION_ORCHESTRATOR_CYCLE_SPEC.md §3.3, §3.6, §5,
§6.3 and MCP_MISSION_TOOLS_SPEC.md §6.1. The cycle itself is
``core/mission_cycle.py``; its decisions are ``mission_decisions`` rows
(``db/models/mission.py``).

Tables owned by this module:
- agent_availability        (§3.3: an executor out of quota until a known time)
- mission_cycle_locks       (§5: Marcelo locks the cycle, or one task of it)
- mission_context_versions  (§3.6 / 04 §8: the versioned context pack)
- mission_dependencies      (§6.3: a mission starts only after another completes)
- mission_skill_proposals   (§3.6: a missing skill becomes a proposal, never a grant)

Cross-domain FKs are string-form, per the foundation convention.
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

PRINCIPAL_TYPES = ("user", "agent", "system")
SKILL_PROPOSAL_KINDS = ("assign_other_agent", "grant_to_agent", "create_skill")
SKILL_PROPOSAL_STATUSES = ("proposed", "accepted", "rejected")


def _in(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


class AgentAvailability(Base, TimestampMixin):
    """One row per agent that is known to be unavailable until a time (§3.3).

    Written only from a deterministic usage-limit match on a run's output
    (``core/agent_availability.py``) or by a person/the orchestrator with a
    reason. ``reserve_dispatch`` keeps the agent's work queued until
    ``unavailable_until`` (``AGENT_UNAVAILABLE``); a past value is inert."""

    __tablename__ = "agent_availability"
    __table_args__ = (
        CheckConstraint("length(btrim(reason)) > 0", name="ck_agent_availability_reason"),
    )

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id", ondelete="CASCADE"), primary_key=True
    )
    unavailable_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    source_demand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agent_demands.id", ondelete="SET NULL"), nullable=True
    )
    recorded_by: Mapped[str] = mapped_column(String(150), nullable=False)


class MissionCycleLock(Base, TimestampMixin):
    """Marcelo's lock on a mission's cycle (task_id NULL) or on one task (§5).
    Open while ``released_at`` is NULL and ``locked_until`` is NULL or future."""

    __tablename__ = "mission_cycle_locks"
    __table_args__ = (
        CheckConstraint("length(btrim(reason)) > 0", name="ck_mission_cycle_locks_reason"),
        Index("ix_mission_cycle_locks_mission", "mission_project_id", "released_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mission_project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.projects.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.project_tasks.id", ondelete="CASCADE"), nullable=True
    )
    locked_by: Mapped[str] = mapped_column(String(150), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_by: Mapped[str | None] = mapped_column(String(150), nullable=True)


class MissionContextVersion(Base, TimestampMixin):
    """One version of a mission's context pack (§3.6, MCP spec §6.1).

    ``sources`` lists the canonical items the version is built from -- ids and
    hashes, never the copied text of something that lives elsewhere. A new
    version is written only when ``content_hash`` changes."""

    __tablename__ = "mission_context_versions"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_mission_context_versions_version"),
        CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="ck_mission_context_versions_hash"),
        CheckConstraint("length(btrim(reason)) > 0", name="ck_mission_context_versions_reason"),
        CheckConstraint(f"created_by_type IN {_in(PRINCIPAL_TYPES)}",
                        name="ck_mission_context_versions_created_by_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.projects.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sources: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_by_type: Mapped[str] = mapped_column(String(10), nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)


class MissionDependency(Base, TimestampMixin):
    """`mission_project_id` starts (ready -> active) only after
    `depends_on_mission_project_id` is completed (§6.3)."""

    __tablename__ = "mission_dependencies"
    __table_args__ = (
        UniqueConstraint("mission_project_id", "depends_on_mission_project_id", name="uq_mission_dependencies_pair"),
        CheckConstraint("mission_project_id <> depends_on_mission_project_id", name="ck_mission_dependencies_self"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mission_project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.projects.id", ondelete="CASCADE"), nullable=False
    )
    depends_on_mission_project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.projects.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[str] = mapped_column(String(150), nullable=False)


class MissionSkillProposal(Base, TimestampMixin):
    """A missing capability turned into a proposal to the skill's owner
    (04 §8 item 3). Recording one never touches ``agent_skills``: granting or
    creating a skill stays with the owner and its approval."""

    __tablename__ = "mission_skill_proposals"
    __table_args__ = (
        CheckConstraint(f"kind IN {_in(SKILL_PROPOSAL_KINDS)}", name="ck_mission_skill_proposals_kind"),
        CheckConstraint(f"status IN {_in(SKILL_PROPOSAL_STATUSES)}", name="ck_mission_skill_proposals_status"),
        CheckConstraint("length(btrim(reason)) > 0", name="ck_mission_skill_proposals_reason"),
        Index("ix_mission_skill_proposals_mission", "mission_project_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mission_project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.projects.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.project_tasks.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    skill_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.skills.id", ondelete="SET NULL"), nullable=True
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id", ondelete="SET NULL"), nullable=True
    )
    owner_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="proposed", server_default="proposed")
    proposed_by: Mapped[str] = mapped_column(String(150), nullable=False)
    demand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agent_demands.id", ondelete="SET NULL"), nullable=True
    )
