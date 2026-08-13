"""Pydantic schemas for the agent-demand inbox and its conversions."""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.conversions import CONVERT_TARGETS
from app.db.models.demand import DEMAND_ORIGIN_TYPES, DEMAND_STATUSES


def _check_origin_type(v: str | None) -> str | None:
    if v is not None and v not in DEMAND_ORIGIN_TYPES:
        raise ValueError(f"origin_type must be one of {DEMAND_ORIGIN_TYPES}")
    return v


def _check_status_value(v: str | None) -> str | None:
    if v is not None and v not in DEMAND_STATUSES:
        raise ValueError(f"status must be one of {DEMAND_STATUSES}")
    return v


class DemandSubmitIn(BaseModel):
    """Body for POST /demands/submit (agents, via the shared bridge token)
    and POST /demands (the "New note" panel)."""

    from_agent: str = Field(min_length=1, max_length=50)
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)
    # Optional at creation time -- set the dispatch target right away
    # instead of a separate PATCH afterward.
    target_agent_id: uuid.UUID | None = None
    # Alternative to target_agent_id for callers that only know the Hermes
    # profile slug, not the ForgeHub UUID -- namely send_demand.sh (bridge
    # token only, can't call the JWT-gated GET /agents to look the UUID up
    # itself). Resolved against Agent.profile_slug at the route layer;
    # ignored if target_agent_id is also given.
    target_agent_slug: str | None = None
    # Lets the compose panel pick a real registered Agent as the sender
    # ("From (agent)") instead of leaving from_agent_id null (the case for
    # every other human-composed item, only ever set server-side on an
    # auto-generated reply -- see get_dispatch_status's reply-creation docstring).
    # Validated same as target_agent_id. Needed for the requires_response relay: see
    # get_dispatch_status's reply-creation docstring. When omitted, the
    # route layer still tries an automatic match: from_agent against
    # Agent.profile_slug (best-effort, no error on a miss -- covers
    # send_demand.sh, which already sends the sending profile's slug as
    # from_agent for display and shouldn't need a second field for the
    # same value).
    from_agent_id: uuid.UUID | None = None
    # Which project this message is about -- see AgentDemand.project_id's
    # docstring for how this differs from ConvertIn.project_id below.
    project_id: uuid.UUID | None = None
    # Working directory path for agent execution -- when dispatching to
    # external agents (claude, codex, agy, openclaw), this specifies the
    # cwd where the agent should run. If not provided, falls back to
    # AGENT_RUNTIME_PATHS or /root.
    working_path: str | None = None
    # Links this new item to an existing Task or Demand as its origin,
    # resolved from a human-typed number rather than a UUID (§4.1 of the
    # dispatch proposal): "task" -> ProjectTask.number,
    # "demand" -> AgentDemand.number. Both origin_type and origin_number
    # must be given together, or neither.
    origin_type: str | None = None
    origin_number: int | None = None
    # "Retorno" -- whether this message expects a response back from the
    # recipient. Defaults to False (no response expected).
    requires_response: bool = False
    # Scheduled send -- if set, target_agent_id must be given too (checked
    # at the route layer, same as origin_type/origin_number pairing above).
    # See AgentDemand.scheduled_at's docstring for how the actual dispatch
    # gets triggered.
    scheduled_at: datetime | None = None
    # Lets the compose panel file a new item straight into the Notes
    # (Archived) tree instead of Incoming -- e.g. Origin="Note" messages,
    # per the Inbox sidebar's direction-first grouping (see
    # DemandsPage's SelectedFolder docstring). Defaults to "new" (Incoming)
    # when omitted, same as before this field existed.
    status: str | None = None

    @field_validator("origin_type")
    @classmethod
    def _check_origin_type(cls, v: str | None) -> str | None:
        return _check_origin_type(v)

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str | None) -> str | None:
        return _check_status_value(v)


class DemandUpdateIn(BaseModel):
    """Partial update -- only fields actually sent by the client are
    applied (route uses `model_dump(exclude_unset=True)`, same convention
    as artifact.py/backlog.py/product.py's PATCH routes). Lets the Inbox's
    drag-and-drop send `group_id` alone without touching `status`, while
    still supporting the plain "mark as read"/"archive" `status`-only
    calls the reading pane already made before groups existed."""

    status: str | None = None
    # Only meaningful once archived -- see AgentDemand.group_id's docstring.
    # Sending group_id (non-null) without an explicit status forces
    # status="archived" at the route layer.
    group_id: uuid.UUID | None = None
    # Associates an item with an agent without dispatching yet (§3.1 of the
    # dispatch proposal) -- lets Marcelo pick a target before writing the
    # command_text that actually triggers POST .../dispatch.
    target_agent_id: uuid.UUID | None = None
    # Lets "Alterar" fix up the sender identity too -- e.g. a message that
    # arrived with no From (agent) picked. See DemandSubmitIn.from_agent_id's
    # docstring for what this feeds (the requires_response relay).
    from_agent_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    # Working directory path for agent execution -- when dispatching to
    # external agents (claude, codex, agy, openclaw), this specifies the
    # cwd where the agent should run.
    working_path: str | None = None
    # Full edit support ("Alterar" button) -- subject/body plus re-pointing
    # the origin, same resolution as DemandSubmitIn.origin_number above.
    subject: str | None = Field(default=None, min_length=1, max_length=255)
    body: str | None = Field(default=None, min_length=1)
    origin_type: str | None = None
    origin_number: int | None = None
    requires_response: bool | None = None
    scheduled_at: datetime | None = None

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str | None) -> str | None:
        return _check_status_value(v)

    @field_validator("origin_type")
    @classmethod
    def _check_origin_type_update(cls, v: str | None) -> str | None:
        return _check_origin_type(v)


class DemandGroupCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: uuid.UUID | None = None


class DemandGroupUpdateIn(BaseModel):
    """Partial update (rename and/or reparent) -- `exclude_unset=True` at
    the route layer, so `{"parent_id": null}` (move to the Arquivados root)
    is distinguishable from omitting parent_id entirely (leave it alone)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    parent_id: uuid.UUID | None = None


class DemandGroupOut(BaseModel):
    class Config:
        from_attributes = True

    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class DemandAttachmentOut(BaseModel):
    class Config:
        from_attributes = True

    id: uuid.UUID
    filename: str
    size_bytes: int
    content_type: str | None
    created_at: datetime
    # Optional caption supplied at upload time; None when none was given.
    description: str | None = None


class DemandOut(BaseModel):
    class Config:
        from_attributes = True

    id: uuid.UUID
    number: int
    from_agent: str
    subject: str
    body: str
    status: str
    group_id: uuid.UUID | None
    converted_entity_type: str | None
    converted_reference: str | None
    created_at: datetime
    updated_at: datetime
    attachments: list[DemandAttachmentOut] = []
    target_agent_id: uuid.UUID | None
    from_agent_id: uuid.UUID | None
    project_id: uuid.UUID | None
    command_text: str | None
    # cwd the recipient agent's run starts in; None means fall back to the
    # runtime default (see AgentDemand.working_path's docstring).
    working_path: str | None = None
    origin_type: str
    # ProjectTask.id for origin_type="task" -- see AgentDemand.origin_id's
    # docstring. Always None for origin_type="incubation".
    origin_id: uuid.UUID | None
    # --- Incubation (2026-08-13) ---
    # All four are server-owned: set together when an item is created as (or
    # edited into) an incubation, and all None for a task. Read-only here --
    # DemandSubmitIn/DemandUpdateIn deliberately don't accept them, since the
    # three invariants they encode (an owner, an explicit state, a deadline
    # to decide) are resolved at the route layer and enforced by DB
    # constraints. See AgentDemand's own docstrings.
    incubation_owner_id: uuid.UUID | None = None
    incubation_state: str | None = None
    matures_at: datetime | None = None
    drop_reason: str | None = None
    # When this message actually finished running -- stamped server-side by
    # get_dispatch_status (the recipient agent's run reached a terminal
    # state) or by task.py (a linked ProjectTask completed). See
    # AgentDemand.task_execution_at's docstring for both writers. Never
    # sent by the compose form; not accepted by DemandSubmitIn/DemandUpdateIn.
    task_execution_at: datetime | None
    # The agent's raw output once dispatch finishes -- recorded on this same
    # message regardless of requires_response ("processamento"). See
    # AgentDemand.dispatch_result's docstring.
    dispatch_result: str | None
    requires_response: bool
    # Set only on an auto-generated return message (requires_response=true
    # on the original) -- points back at the message it answers. See
    # AgentDemand.reply_to_id's docstring.
    reply_to_id: uuid.UUID | None
    scheduled_at: datetime | None
    # Set once the target agent itself pulls this item via GET
    # .../pending -- see AgentDemand.agent_processed_at's docstring. Never
    # sent by the compose form.
    agent_processed_at: datetime | None
    dispatch_status: str | None
    agent_run_id: str | None


class DispatchIn(BaseModel):
    """Body for POST /demands/{id}/dispatch. Either target_agent_id or
    reply_to_sender=True must resolve to an agent -- the route rejects both
    missing and both present as ambiguous."""

    target_agent_id: uuid.UUID | None = None
    reply_to_sender: bool = False
    # Marcelo's instruction, combined with the item's body as the prompt.
    # Not required -- for a reply continuing an existing thread, the body
    # (Marcelo's own reply text) is already the full prompt on its own.
    command_text: str | None = None


class DispatchStatusOut(BaseModel):
    dispatch_status: str | None
    agent_run_id: str | None
    reply_demand_id: uuid.UUID | None = None


class ConvertIn(BaseModel):
    """Body for POST /demands/{id}/convert and POST /docs/convert.

    Which extra fields are required depends on `target` -- validated in
    the route layer (the error message can name the missing field), same
    pattern as ProjectTaskCreate's cross-field check.
    """

    target: str
    title: str | None = Field(default=None, max_length=255)
    # Which existing /root/docs note to convert -- only used by
    # POST /docs/convert (demand.py's /demands/{id}/convert gets its
    # content from the demand row instead).
    source_path: str | None = Field(default=None, max_length=500)
    # task (existing planning item)
    planning_item_id: uuid.UUID | None = None
    # Destination path for target=doc / knowledge_base / artifact's
    # backing doc file. Defaulted per-target when omitted (see the routes).
    path: str | None = Field(default=None, max_length=500)
    # artifact
    artifact_type: str | None = None
    # planning_item / project_doc / quick_task -- which project this demand
    # becomes work for.
    project_id: uuid.UUID | None = None
    # planning_item / quick_task -- one of PLANNING_ITEM_TYPES; defaulted to
    # "documentation" at the route layer when omitted (matches the common
    # case: a procedure doc sent to a project).
    item_type: str | None = None
    # doc (Inbox only) -- which "área de criação" (docs_creation_areas) to
    # write into, per docs.py's multi-area model. Omitted = the original
    # single /root/docs mount (DOCS_ROOT), kept for docs.py's own /convert
    # entry point which isn't area-aware yet.
    area_id: uuid.UUID | None = None

    @field_validator("target")
    @classmethod
    def _check_target(cls, v: str) -> str:
        if v not in CONVERT_TARGETS:
            raise ValueError(f"target must be one of {CONVERT_TARGETS}")
        return v


class ConvertOut(BaseModel):
    entity_type: str
    entity_id: str | None = None
    reference: str
