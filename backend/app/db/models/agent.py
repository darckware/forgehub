"""SQLAlchemy models for the Agent domain.

Tables owned by this module (see docs/SPEC.md section 4.6 / 6.5):
    agents, sub_agents, skills, agent_skills, sub_agent_skills,
    agent_cost_rates, agent_capacities

Conventions (binding, see backend foundation notes):
    - UUID PK, Python-side default (uuid.uuid4), never server-side.
    - Both Base and TimestampMixin are inherited; created_at/updated_at
      come for free and must not be redeclared.
    - No `__table_args__ = {"schema": ...}` per-model: Base.metadata
      already fixes the schema globally.
    - Foreign keys to tables owned by OTHER domains are declared as
      string targets (e.g. "company.project_tasks.id") and that table's
      model is intentionally NOT imported here, to avoid import-order
      coupling across domains. SQLAlchemy resolves these lazily once all
      domain model modules have been imported (see app/db/models/__init__.py,
      populated centrally by the wiring step).
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

# ---------------------------------------------------------------------------
# Allowed value sets (enforced at the application layer via CHECK
# constraints + route-level validation, not via DB-native ENUM types --
# keeps migrations simple and avoids ALTER TYPE churn as the domain
# evolves during the MVP).
# ---------------------------------------------------------------------------

AGENT_STATUSES = ("active", "inactive", "retired")
AGENT_TYPES = ("coordinator", "executor", "hybrid")

SKILL_RISK_LEVELS = ("low", "medium", "high", "critical")
SKILL_ORIGINS = ("internal", "third_party", "foundation")

COST_RATE_UNITS = ("per_task", "per_hour", "per_token", "per_execution")


class Agent(Base, TimestampMixin):
    """An executor or coordinator agent (PRD 5.11).

    Hermes Foundation metadata (profile_slug, layer, runtime_tier,
    telegram_required, has_profile, mission, source_path) is populated and
    refreshed only by the Hermes sync (POST /api/v1/agents/sync/hermes-foundation,
    see app/core/hermes_sync.py). It is nullable so manually-created agents
    that have nothing to do with Hermes are unaffected. Once an agent has
    been synced once, re-syncing only refreshes these mirrored fields and
    never touches name/status/is_active/agent_type/description again --
    those become user/governance-owned in ForgeHub after first creation.
    """

    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="executor"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Hermes Foundation metadata -- see class docstring.
    profile_slug: Mapped[str | None] = mapped_column(String(50), nullable=True)
    layer: Mapped[str | None] = mapped_column(String(50), nullable=True)
    runtime_tier: Mapped[str | None] = mapped_column(String(1), nullable=True)
    telegram_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    has_profile: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    mission: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reports_to_profile_slug: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Write-only through the API and encrypted before persistence. The raw
    # ForgeRouter agent key must never appear in response schemas or audit data.
    forgerouter_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    sub_agents: Mapped[list["SubAgent"]] = relationship(
        back_populates="agent", cascade="all, delete-orphan"
    )
    agent_skills: Mapped[list["AgentSkill"]] = relationship(
        back_populates="agent", cascade="all, delete-orphan"
    )
    cost_rates: Mapped[list["AgentCostRate"]] = relationship(
        back_populates="agent", cascade="all, delete-orphan"
    )
    capacities: Mapped[list["AgentCapacity"]] = relationship(
        back_populates="agent", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            f"agent_type IN {AGENT_TYPES}", name="ck_agents_agent_type"
        ),
        CheckConstraint(f"status IN {AGENT_STATUSES}", name="ck_agents_status"),
        CheckConstraint(
            "runtime_tier IS NULL OR runtime_tier IN ('A', 'B', 'C')",
            name="ck_agents_runtime_tier",
        ),
        UniqueConstraint("profile_slug", name="uq_agents_profile_slug"),
    )

    @property
    def forgerouter_api_key_configured(self) -> bool:
        return bool(self.forgerouter_api_key_encrypted)


class AgentServiceCredential(Base, TimestampMixin):
    """Hashed, revocable bearer credential used to authenticate an agent principal."""

    __tablename__ = "agent_service_credentials"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(150), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SubAgent(Base, TimestampMixin):
    """A subordinate agent with scoped permissions and skills (PRD 5.12).

    Skills available to a sub-agent are either explicitly granted via
    sub_agent_skills, or inherited from the parent agent's agent_skills
    when that association's `inheritable` flag is set (SPEC 6.5 rule 7:
    "Sub-agents may only use skills that are explicit or inherited by
    permission"). This boundary is enforced at the route layer, not the
    DB layer, since it is a cross-row business rule.
    """

    __tablename__ = "sub_agents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )
    permission_scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    agent: Mapped["Agent"] = relationship(back_populates="sub_agents")
    sub_agent_skills: Mapped[list["SubAgentSkill"]] = relationship(
        back_populates="sub_agent", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("agent_id", "name", name="uq_sub_agents_agent_id_name"),
        CheckConstraint(f"status IN {AGENT_STATUSES}", name="ck_sub_agents_status"),
    )


class Skill(Base, TimestampMixin):
    """A versioned, governed capability (PRD 5.13, SPEC 6.5).

    Business rules encoded here / at the route layer:
      - every skill must have a version, origin, and risk_level (NOT NULL).
      - permissions must be declared (NOT NULL, defaults to empty list-as-text
        only if explicitly provided -- route layer requires non-empty).
      - critical risk_level skills require approval (is_approved must be
        explicitly set True by a separate approval action; route layer
        blocks risk_level == "critical" at creation unless approved=False
        is acknowledged -- enforced as "cannot self-approve on create").
      - third-party origin skills require security review before approval
        (route layer: cannot set is_approved=True while origin ==
        "third_party" unless security_reviewed=True).
      - approved skills must not change without a new version: route layer
        blocks PATCH on a skill where is_approved=True for any field other
        than is_approved/security_reviewed itself; callers must create a
        new Skill row with an incremented `version` instead.
    """

    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin: Mapped[str] = mapped_column(String(20), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    permissions: Mapped[str] = mapped_column(Text, nullable=False)
    is_approved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    security_reviewed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    agent_skills: Mapped[list["AgentSkill"]] = relationship(
        back_populates="skill", cascade="all, delete-orphan"
    )
    sub_agent_skills: Mapped[list["SubAgentSkill"]] = relationship(
        back_populates="skill", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_skills_name_version"),
        CheckConstraint(f"origin IN {SKILL_ORIGINS}", name="ck_skills_origin"),
        CheckConstraint(
            f"risk_level IN {SKILL_RISK_LEVELS}", name="ck_skills_risk_level"
        ),
    )


class AgentSkill(Base, TimestampMixin):
    """Association: skills granted to an agent."""

    __tablename__ = "agent_skills"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.skills.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Whether sub-agents of this agent may inherit this skill grant
    # without an explicit sub_agent_skills row (SPEC 6.5 rule 7).
    inheritable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    agent: Mapped["Agent"] = relationship(back_populates="agent_skills")
    skill: Mapped["Skill"] = relationship(back_populates="agent_skills")

    __table_args__ = (
        UniqueConstraint("agent_id", "skill_id", name="uq_agent_skills_agent_skill"),
    )


class SubAgentSkill(Base, TimestampMixin):
    """Association: skills explicitly granted to a sub-agent."""

    __tablename__ = "sub_agent_skills"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sub_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.sub_agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.skills.id", ondelete="CASCADE"),
        nullable=False,
    )

    sub_agent: Mapped["SubAgent"] = relationship(back_populates="sub_agent_skills")
    skill: Mapped["Skill"] = relationship(back_populates="sub_agent_skills")

    __table_args__ = (
        UniqueConstraint(
            "sub_agent_id", "skill_id", name="uq_sub_agent_skills_sub_agent_skill"
        ),
    )


class AgentCostRate(Base, TimestampMixin):
    """Cost rate for an agent (basic cost control, PRD section 3)."""

    __tablename__ = "agent_cost_rates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    rate_unit: Mapped[str] = mapped_column(String(20), nullable=False)
    rate_amount: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    agent: Mapped["Agent"] = relationship(back_populates="cost_rates")

    __table_args__ = (
        CheckConstraint(
            f"rate_unit IN {COST_RATE_UNITS}", name="ck_agent_cost_rates_rate_unit"
        ),
        CheckConstraint("rate_amount >= 0", name="ck_agent_cost_rates_amount_nonneg"),
    )


class AgentCapacity(Base, TimestampMixin):
    """Capacity / concurrent workload ceiling for an agent."""

    __tablename__ = "agent_capacities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    max_concurrent_tasks: Mapped[int] = mapped_column(nullable=False, default=1)
    max_daily_tasks: Mapped[int | None] = mapped_column(nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    agent: Mapped["Agent"] = relationship(back_populates="capacities")

    __table_args__ = (
        UniqueConstraint("agent_id", name="uq_agent_capacities_agent_id"),
        CheckConstraint(
            "max_concurrent_tasks >= 1",
            name="ck_agent_capacities_max_concurrent_tasks_positive",
        ),
    )
