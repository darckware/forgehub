"""Pydantic schemas for the ChatChannel domain (see db/models/channel.py
for the design rationale this mirrors)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.api.schemas.orchestration import ProjectAgentMembershipOut


class ChatChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = None
    project_id: uuid.UUID | None = None
    working_directory_path: str | None = Field(default=None, max_length=1024)
    # Explicit choice made by the human at creation time -- never derived
    # from the project's team, even when project_id is set (see
    # db/models/channel.py's module docstring).
    member_agent_ids: list[uuid.UUID] = Field(default_factory=list)
    # Optional per-member override of the default_role prefill, keyed by
    # agent_id (as a string -- JSON object keys can't be UUIDs). Lets the
    # human pick each specialist's function *at creation time* instead of
    # always editing it afterwards via PATCH .../members/{id} (2026-08-05,
    # Marcelo: "não seria melhor escolher as funções de cada um nesse
    # momento"). Any agent_id not present here still falls back to
    # Agent.default_role, same as before this field existed.
    member_roles: dict[str, str] | None = None
    # Must be one of member_agent_ids -- validated at the route layer (400
    # otherwise). Purely informational (see ChatChannel.orchestrator_agent_id
    # docstring) -- granting real approval authority is a separate action
    # via governance.AuthorityDelegation, not a side effect of this field.
    orchestrator_agent_id: uuid.UUID | None = None


class ChatChannelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    archived: bool | None = None
    # Same "only overwrite when a non-null value arrives" contract as
    # name/description/archived above (update_channel checks `is not
    # None`) -- pass an agent_id to (re)designate. Automatically cleared to
    # NULL if that member is later removed (FK ondelete=SET NULL), so there
    # is no separate "unset" affordance needed yet.
    orchestrator_agent_id: uuid.UUID | None = None


class ChatChannelAttachProject(BaseModel):
    project_id: uuid.UUID


class ChatChannelMemberAdd(BaseModel):
    agent_id: uuid.UUID
    # Optional override -- when omitted, the new member's role is
    # pre-filled from Agent.default_role (still just a starting point,
    # editable afterwards via ChatChannelMemberUpdate).
    role: str | None = None


class ChatChannelMemberUpdate(BaseModel):
    """Marcelo-only (JWT) -- sets/edits this member's function *in this
    channel* (see db/models/channel.py's ChatChannelMember.role docstring).
    Who can later decide an Approval involving this member is a completely
    separate concern, handled by governance.AuthorityDelegation -- there is
    no permission flag on this schema."""

    role: str | None = None


class ChatChannelMemberOut(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    agent_id: uuid.UUID | None
    is_human: bool
    hermes_session_id: str | None
    muted: bool
    role: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatChannelOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    project_id: uuid.UUID | None
    working_directory_path: str | None
    archived: bool
    turn_policy: str
    created_by: str | None
    orchestrator_agent_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatChannelWithMembersOut(ChatChannelOut):
    members: list[ChatChannelMemberOut] = Field(default_factory=list)


class ChatChannelCreateResult(BaseModel):
    """Returned by POST /channels -- the created channel plus, only when a
    project was attached at creation, the project's active memberships as a
    suggestion for the frontend's member picker. Never auto-applied."""

    channel: ChatChannelWithMembersOut
    suggested_project_members: list[ProjectAgentMembershipOut] = Field(default_factory=list)


class ChatChannelMessageCreate(BaseModel):
    content: str = Field(min_length=1)
    attachment_names: str | None = Field(default=None, max_length=500)


class ChatChannelMessageOut(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    author_type: str
    author_agent_id: uuid.UUID | None
    author_label: str | None
    content: str
    mentioned_agent_ids: list[uuid.UUID] | None
    triggered_demand_id: uuid.UUID | None
    thinking_seconds: int | None
    attachment_names: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatChannelDispatchTaskRequest(BaseModel):
    agent_id: uuid.UUID
    # Optional -- if omitted, a standalone AgentDemand is created
    # (origin_type="backlog", promotable later), same behavior as
    # demand.py's own dispatch when no task is linked.
    project_task_id: uuid.UUID | None = None


class ChatChannelTaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    assignee_agent_id: uuid.UUID | None = None
    created_message_id: uuid.UUID | None = None
    # When true and the channel already has project_id set, promotes to a
    # real ProjectTask immediately instead of staying a lightweight item.
    promote_immediately: bool = False


class ChatChannelTaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    status: str | None = None
    assignee_agent_id: uuid.UUID | None = None


class ChatChannelTaskOut(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    title: str
    status: str
    assignee_agent_id: uuid.UUID | None
    created_message_id: uuid.UUID | None
    project_task_id: uuid.UUID | None
    role_required: str | None
    created_by_agent_id: uuid.UUID | None
    approval_id: uuid.UUID | None
    # Read-only, computed at response time from the joined governance.
    # Approval row (see db/models/channel.py's approval_id docstring) --
    # never a second, potentially-diverging source of truth. Null when
    # approval_id is null (task never needed approval).
    approval_status: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatChannelTaskProposeIn(BaseModel):
    """Agent-facing (bridge-token or agt_ credential, see
    api/routes/channel.py's propose_channel_task) -- never used by the
    human UI, which goes through ChatChannelTaskCreate instead."""

    acting_agent_slug: str
    title: str = Field(min_length=1, max_length=255)
    assignee_agent_slug: str
    role_required: str | None = None
