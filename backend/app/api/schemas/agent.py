"""Pydantic Create/Update/Read schemas for the Agent domain.

Covers: agents (primary, full CRUD + nested sub_agents/skills), sub_agents,
skills, agent_skills, sub_agent_skills, agent_cost_rates, agent_capacities.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models.agent import (
    AGENT_RUNTIME_TYPES,
    AGENT_STATUSES,
    AGENT_TYPES,
    COST_RATE_UNITS,
    SKILL_ORIGINS,
    SKILL_RISK_LEVELS,
)
from app.db.models.orchestration import PROJECT_AGENT_ROLES


def _validate_choice(value: str, choices: tuple[str, ...], field_name: str) -> str:
    if value not in choices:
        raise ValueError(f"{field_name} must be one of {choices}")
    return value


# ---------------------------------------------------------------------------
# Skill
# ---------------------------------------------------------------------------


class SkillBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    version: str = Field(min_length=1, max_length=50)
    description: str | None = None
    origin: str
    risk_level: str
    permissions: str = Field(min_length=1)

    @field_validator("origin")
    @classmethod
    def _check_origin(cls, v: str) -> str:
        return _validate_choice(v, SKILL_ORIGINS, "origin")

    @field_validator("risk_level")
    @classmethod
    def _check_risk_level(cls, v: str) -> str:
        return _validate_choice(v, SKILL_RISK_LEVELS, "risk_level")


class SkillCreate(SkillBase):
    # Skills cannot be self-approved at creation time (SPEC 6.5 rule 5/6).
    pass


class SkillUpdate(BaseModel):
    """Partial update. If the target skill is already approved, the route
    layer rejects any field here except is_approved/security_reviewed
    (SPEC 6.5 rule 8: approved skills must not change without a new
    version)."""

    name: str | None = Field(default=None, min_length=1, max_length=150)
    version: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = None
    origin: str | None = None
    risk_level: str | None = None
    permissions: str | None = Field(default=None, min_length=1)
    is_approved: bool | None = None
    security_reviewed: bool | None = None

    @field_validator("origin")
    @classmethod
    def _check_origin(cls, v: str | None) -> str | None:
        return v if v is None else _validate_choice(v, SKILL_ORIGINS, "origin")

    @field_validator("risk_level")
    @classmethod
    def _check_risk_level(cls, v: str | None) -> str | None:
        return (
            v if v is None else _validate_choice(v, SKILL_RISK_LEVELS, "risk_level")
        )


class SkillOut(SkillBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    is_approved: bool
    security_reviewed: bool
    created_at: datetime
    updated_at: datetime


class SkillAgentRef(BaseModel):
    """Agent granted a skill (via agent_skills), embedded in skill listings
    so the Skills page can show/filter by the agents that hold each skill
    without one request per skill."""

    agent_id: uuid.UUID
    agent_name: str


class SkillWithAgentsOut(SkillOut):
    agents: list[SkillAgentRef] = []


# ---------------------------------------------------------------------------
# AgentSkill / SubAgentSkill (associations)
# ---------------------------------------------------------------------------


class AgentSkillCreate(BaseModel):
    skill_id: uuid.UUID
    inheritable: bool = False


class AgentSkillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    skill_id: uuid.UUID
    inheritable: bool
    created_at: datetime
    updated_at: datetime


class SubAgentSkillCreate(BaseModel):
    skill_id: uuid.UUID


class SubAgentSkillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sub_agent_id: uuid.UUID
    skill_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# SubAgent
# ---------------------------------------------------------------------------


class SubAgentBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = None
    status: str = "active"
    permission_scope: str | None = None
    is_active: bool = True

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str) -> str:
        return _validate_choice(v, AGENT_STATUSES, "status")


class SubAgentCreate(SubAgentBase):
    skill_ids: list[uuid.UUID] = Field(default_factory=list)


class SubAgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    status: str | None = None
    permission_scope: str | None = None
    is_active: bool | None = None

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str | None) -> str | None:
        return v if v is None else _validate_choice(v, AGENT_STATUSES, "status")


class SubAgentOut(SubAgentBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# AgentCostRate
# ---------------------------------------------------------------------------


class AgentCostRateBase(BaseModel):
    rate_unit: str
    rate_amount: float = Field(ge=0)
    currency: str = Field(default="USD", min_length=1, max_length=10)
    is_active: bool = True

    @field_validator("rate_unit")
    @classmethod
    def _check_rate_unit(cls, v: str) -> str:
        return _validate_choice(v, COST_RATE_UNITS, "rate_unit")


class AgentCostRateCreate(AgentCostRateBase):
    pass


class AgentCostRateOut(AgentCostRateBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# AgentCapacity
# ---------------------------------------------------------------------------


class AgentCapacityBase(BaseModel):
    max_concurrent_tasks: int = Field(default=1, ge=1)
    max_daily_tasks: int | None = Field(default=None, ge=1)
    notes: str | None = None


class AgentCapacityCreate(AgentCapacityBase):
    pass


class AgentCapacityUpdate(BaseModel):
    max_concurrent_tasks: int | None = Field(default=None, ge=1)
    max_daily_tasks: int | None = Field(default=None, ge=1)
    notes: str | None = None


class AgentCapacityOut(AgentCapacityBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Agent (primary entity)
# ---------------------------------------------------------------------------


class AgentBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = None
    agent_type: str = "executor"
    status: str = "active"
    is_active: bool = True

    @field_validator("agent_type")
    @classmethod
    def _check_agent_type(cls, v: str) -> str:
        return _validate_choice(v, AGENT_TYPES, "agent_type")

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str) -> str:
        return _validate_choice(v, AGENT_STATUSES, "status")


class AgentCreate(AgentBase):
    forgerouter_api_key: str | None = Field(default=None, min_length=1, max_length=1000)


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    agent_type: str | None = None
    status: str | None = None
    is_active: bool | None = None
    forgerouter_api_key: str | None = Field(default=None, min_length=1, max_length=1000)
    clear_forgerouter_api_key: bool = False
    runtime_type: str | None = None
    # Editable since 2026-07-26. It used to be set only by the Hermes
    # Foundation sync, which walks /root/.hermes/profiles/ -- so the four
    # agents that are external CLI runtimes rather than Hermes profiles
    # (Porthus/claude, Aramis/codex, Dartan/agy, Vector/openclaw) had no
    # directory to be discovered from and stayed NULL forever, with no way
    # to fix it short of raw SQL. That's not cosmetic: profile_slug is the
    # *addressing key* of the message channel -- `--to <profile>` and
    # `check_agent_inbox.sh <profile>` both resolve against it (see
    # demand.py's _get_agent_by_slug_or_404), so a NULL slug means that
    # agent simply can't be reached or read its own mail by name. Only
    # required by dispatch itself for runtime_type="hermes"
    # (agent_runs.py), which is why the gap stayed invisible: those four
    # dispatch fine by UUID from the UI.
    profile_slug: str | None = Field(default=None, min_length=1, max_length=50)
    # The agent's own Telegram bot account (@username, e.g. "HermesAthosbot").
    # Empty string clears it, so no min_length: an agent may legitimately have
    # no Telegram bot. Editable because every agent speaks through a different
    # bot, and only this says which one answers for it.
    telegram_account: str | None = Field(default=None, max_length=100)
    # Absolute host path of the agent's profile-file directory. Empty string
    # clears the override and falls back to the runtime convention (see
    # core/agent_profile_files.py); that is why it is not min_length=1.
    home_path: str | None = Field(default=None, max_length=1000)
    # The agent's declared specialty (2026-08-05, see
    # docs/architecture/CHANNEL_AGENT_ROLES_AND_ORCHESTRATION.md) -- a
    # channel only ever suggests this when adding the agent as a member,
    # never imposes it.
    default_role: str | None = None

    @field_validator("default_role")
    @classmethod
    def _check_default_role(cls, v: str | None) -> str | None:
        return v if v is None else _validate_choice(v, PROJECT_AGENT_ROLES, "default_role")

    @field_validator("home_path")
    @classmethod
    def _check_home_path(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if not v.startswith("/"):
            raise ValueError("home_path must be an absolute path")
        return v.rstrip("/") or "/"

    @field_validator("agent_type")
    @classmethod
    def _check_agent_type(cls, v: str | None) -> str | None:
        return v if v is None else _validate_choice(v, AGENT_TYPES, "agent_type")

    @field_validator("runtime_type")
    @classmethod
    def _check_runtime_type(cls, v: str | None) -> str | None:
        return v if v is None else _validate_choice(v, AGENT_RUNTIME_TYPES, "runtime_type")

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str | None) -> str | None:
        return v if v is None else _validate_choice(v, AGENT_STATUSES, "status")


class AgentOut(AgentBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    # Hermes Foundation metadata -- read-only, populated/refreshed only by
    # POST /api/v1/agents/sync/hermes-foundation (app/core/hermes_sync.py).
    # Not part of AgentCreate/AgentUpdate.
    profile_slug: str | None = None
    layer: str | None = None
    runtime_tier: str | None = None
    telegram_required: bool = False
    # The agent's own Telegram bot account (@username). Editable, unlike the
    # sync-owned fields above: it identifies which bot answers for this agent,
    # and every agent has a different one.
    telegram_account: str | None = None
    has_profile: bool = False
    mission: str | None = None
    source_path: str | None = None
    department: str | None = None
    sector: str | None = None
    reports_to_profile_slug: str | None = None
    forgerouter_api_key_configured: bool = False
    # See AGENT_RUNTIME_TYPES (db/models/agent.py) -- only set for agents
    # with a stateless single-shot CLI dispatch mode (Inbox dispatch target
    # eligibility, api/routes/demand.py's /dispatch).
    runtime_type: str | None = None
    # Registered override for where this agent's profile Markdown files live
    # (host path). `effective_home_path` is what the UI should show and what
    # the profile-file endpoints actually read: the override when set, the
    # runtime convention otherwise. See core/agent_profile_files.py.
    home_path: str | None = None
    effective_home_path: str | None = None
    default_role: str | None = None


class AgentListItemOut(AgentOut):
    """Agent as returned by the list endpoint -- includes sub_agents (for
    rendering the parent/child hierarchy in the Agents list) but, unlike
    AgentDetailOut, omits agent_skills/cost_rates/capacities to keep the
    list query light (an agent can have 100+ skill grants)."""

    sub_agents: list[SubAgentOut] = Field(default_factory=list)


class AgentDetailOut(AgentOut):
    """Agent with nested sub_agents and granted skills (agent_skills)."""

    sub_agents: list[SubAgentOut] = Field(default_factory=list)
    agent_skills: list[AgentSkillOut] = Field(default_factory=list)
    cost_rates: list[AgentCostRateOut] = Field(default_factory=list)
    capacities: list[AgentCapacityOut] = Field(default_factory=list)
    # Decrypted ForgeRouter key -- admin-only, detail-endpoint-only (see
    # GET /{agent_id} in api/routes/agent.py). Reverses the column's
    # original "never displayed again" design (db/models/agent.py) per
    # Marcelo's explicit 2026-07-29 request; None for a non-admin caller or
    # an agent with no key configured, never the raw
    # forgerouter_api_key_encrypted column itself, and never present on
    # AgentListItemOut/AgentOut (the roster list keeps the boolean only).
    forgerouter_api_key: str | None = None


# ---------------------------------------------------------------------------
# Profile Markdown files (SOUL.md, IDENTITY.md, TOOLS.md, ...)
# ---------------------------------------------------------------------------


class AgentProfileFileInfo(BaseModel):
    """One profile file's presence and stats. `path` is always the host path,
    even when the backend reads it through a container mount."""

    filename: str
    path: str
    exists: bool
    size: int | None = None
    modified_at: datetime | None = None


class AgentProfileFilesOut(BaseModel):
    """The agent's whole profile-file directory as one payload.

    `home_resolved` False means the directory named by `home_path` is not
    reachable from the backend process -- under Docker that is a missing bind
    mount, not a missing agent, so the UI must say which path it tried."""

    agent_id: uuid.UUID
    home_path: str | None = None
    home_resolved: bool = False
    files: list[AgentProfileFileInfo] = Field(default_factory=list)


class AgentProfileFileOut(BaseModel):
    """Content of a single profile file. `content` is None when the file does
    not exist yet -- distinct from an empty file."""

    agent_id: uuid.UUID
    filename: str
    path: str
    content: str | None = None


class AgentProfileFileUpdateIn(BaseModel):
    content: str


# ---------------------------------------------------------------------------
# MCP servers
# ---------------------------------------------------------------------------


class AgentMcpServerOut(BaseModel):
    """One MCP server as configured for this agent's runtime.

    `enabled` is always meaningful to read (a runtime with no toggle reports
    True), but only writable when the runtime's format has a field for it --
    see `supports_toggle` on the list payload."""

    name: str
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    enabled: bool = True


class AgentMcpServersOut(BaseModel):
    """Every MCP server configured for one agent, plus where that came from.

    `config_path` is the host path of the runtime's own config file (a Hermes
    `config.yaml`, `~/.claude.json`, ...) -- ForgeHub edits that file in place
    rather than keeping its own copy, so an operator can always check the
    result outside the app. `config_exists` False with a non-null path means
    the runtime simply has no MCP config yet, which is the normal state before
    the first server is added, not an error."""

    agent_id: uuid.UUID
    runtime_type: str | None = None
    config_path: str | None = None
    config_exists: bool = False
    supports_toggle: bool = False
    error: str | None = None
    servers: list[AgentMcpServerOut] = Field(default_factory=list)


class AgentRuntimeSyncAgentOut(BaseModel):
    """One agent's reconciliation against the filesystem."""

    agent_id: uuid.UUID
    agent_name: str
    profile_slug: str | None = None
    runtime_type: str | None = None
    detected_runtime_type: str | None = None
    evidence: str | None = None
    home_path: str | None = None
    home_resolved: bool = False
    mcp_config_path: str | None = None
    mcp_config_exists: bool = False
    # Set when this sync filled a missing runtime_type in this run.
    applied: bool = False
    issues: list[str] = Field(default_factory=list)


class AgentRuntimeSyncOut(BaseModel):
    """Result of the real (filesystem) sync, as opposed to the doc-driven one.

    `updated` counts agents whose missing `runtime_type` was filled in from
    disk evidence; an existing value is never overwritten, so a registry that
    contradicts the disk shows up in `issues` instead."""

    checked: int = 0
    updated: int = 0
    agents: list[AgentRuntimeSyncAgentOut] = Field(default_factory=list)
    # Hermes profile directories with no agent registered against them.
    unregistered_profiles: list[str] = Field(default_factory=list)


class ForgeRouterKeyImportOut(BaseModel):
    """Result of importing one agent's key from ai_router.agents."""

    matched: bool = False
    updated: bool = False
    forgerouter_api_key_configured: bool = False


class ForgeRouterServiceOut(BaseModel):
    """One service-kind entry in ai_router.agents (e.g. "Hindsight") --
    name only, never the key (see ForgeRouterServiceKeyOut for that)."""

    name: str


class ForgeRouterServiceKeyOut(BaseModel):
    """Single service's plaintext key, straight from ai_router.agents --
    that table is ForgeRouter's own storage, not ForgeHub's, so there is
    nothing to decrypt here (unlike Agent.forgerouter_api_key_encrypted)."""

    name: str
    api_key: str


class ForgeRouterKeySyncAgentOut(BaseModel):
    """One agent's ForgeRouter-key reconciliation against ai_router.agents."""

    agent_id: uuid.UUID
    agent_name: str
    matched: bool = False
    updated: bool = False


class ForgeRouterKeySyncOut(BaseModel):
    """Result of pulling each agent's already-issued key straight from
    ForgeRouter's own registry (ai_router.agents), keyed by exact agent
    name -- the authoritative source ForgeRouter itself hands out and
    writes into that agent's own config (see core/forgerouter_sync.py)."""

    checked: int = 0
    matched: int = 0
    updated: int = 0
    agents: list[ForgeRouterKeySyncAgentOut] = Field(default_factory=list)
    # Rows in ai_router.agents (kind='agent') with no matching ForgeHub
    # agent name -- surfaced so a naming drift is visible, not silent.
    unmatched_forgerouter_agents: list[str] = Field(default_factory=list)


class AgentMcpOverviewItem(AgentMcpServersOut):
    """One agent's row on the ecosystem-wide MCP screen.

    `supported` False is the Kairos case: a registered agent with no
    `runtime_type`, so nothing would ever load an MCP server for it. It is
    listed rather than hidden — an operator looking for "who can use the
    messages MCP" needs to see the agent that cannot."""

    agent_name: str
    profile_slug: str | None = None
    supported: bool = True


class AgentMcpOverviewOut(BaseModel):
    agents: list[AgentMcpOverviewItem] = Field(default_factory=list)


class AgentMcpServerIn(BaseModel):
    """Upsert payload. Either `command` (stdio) or `url` (HTTP) -- the runtimes
    all treat a server carrying both as HTTP, so requiring exactly one here
    keeps the stored config unambiguous."""

    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    enabled: bool = True


# ---------------------------------------------------------------------------
# Telegram channel status
# ---------------------------------------------------------------------------


class AgentTelegramStatusOut(BaseModel):
    """Whether an agent's Telegram channel is installed *and* running.

    Two independent signals (see core/agent_telegram.py): `installed` reads
    the profile's own .env (bot token + home channel; the token itself never
    leaves the backend), `running` is the `hermes-gateway-<profile>.service`
    systemd state. `running` is None when the host-bridge could not be
    reached -- "not checked" must not render as "broken"."""

    agent_id: uuid.UUID
    agent_name: str
    profile_slug: str | None = None
    required: bool = False
    installed: bool = False
    home_channel_name: str | None = None
    service: str | None = None
    running: bool | None = None
    # ok | not_running | not_configured | unknown | not_applicable
    status: str


class AgentTelegramStatusListOut(BaseModel):
    """Whole-roster view, so the list page and org chart need one request
    instead of one per agent."""

    agents: list[AgentTelegramStatusOut] = Field(default_factory=list)
    # Populated when the systemd check could not run at all; every entry then
    # carries running=None / status="unknown".
    check_error: str | None = None


class AgentTelegramMessageOut(BaseModel):
    id: int
    role: str
    content: str
    timestamp: float
    platform_message_id: str | None = None


class AgentTelegramConversationOut(BaseModel):
    agent_id: uuid.UUID
    agent_name: str
    profile_slug: str
    session_id: str | None = None
    chat_id: str | None = None
    messages: list[AgentTelegramMessageOut] = Field(default_factory=list)
    delivery_error: str | None = None


class AgentTelegramSendIn(BaseModel):
    message: str = Field(min_length=1, max_length=50_000)

    @field_validator("message")
    @classmethod
    def _strip_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value


# ---------------------------------------------------------------------------
# Hermes Foundation sync result
# ---------------------------------------------------------------------------


class SyncCounts(BaseModel):
    created: int = 0
    updated: int = 0


class HermesSyncResultOut(BaseModel):
    agents: SyncCounts
    sub_agents: SyncCounts
    skills: SyncCounts
    agent_skills: SyncCounts
    warnings: list[str] = Field(default_factory=list)
