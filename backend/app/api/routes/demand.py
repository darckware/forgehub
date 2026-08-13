"""Agent demand inbox routes -- ForgeHub's "console de desenvolvimento"
intake: agents (and the logged-in user, via the compose path) send a
note here, a human reads it and converts it into a Task, a Docs document,
an Artifact, a Knowledge Base note, or straight into project work (a new
planning item, a project-linked doc, or a "task avulsa" shortcut that
creates a planning item + task together) -- see core/conversions.py for
the full CONVERT_TARGETS list. Existing /root/docs notes/annotations get
the same conversion menu through docs.py's /convert -- no demand row
needed for those, they already have a body (the file content).
"""
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.demand import (
    ConvertIn,
    ConvertOut,
    DemandAttachmentOut,
    DemandGroupCreateIn,
    DemandGroupOut,
    DemandGroupUpdateIn,
    DemandOut,
    DemandSubmitIn,
    DemandUpdateIn,
    DispatchIn,
    DispatchStatusOut,
)
from app.core import conversions
from app.core.agent_runs import AgentRunDispatchError, dispatch_agent_run, poll_agent_run
from app.core.config import settings
from app.core.demand_thread import build_thread_prompt
from app.core.feedback import deliver_feedback
from app.core.localtime import format_local
from app.core.markdown_docs import resolve_doc_path
from app.db.base import get_db
from app.db.models.agent import Agent
from app.db.models.backlog import PLANNING_ITEM_TYPES
from app.db.models.demand import (
    DEMAND_DISPATCH_STATUSES,
    DEMAND_LINKED_ORIGIN_TYPES,
    DEMAND_ORIGIN_TYPES,
    DEMAND_STATUSES,
    DISPATCH_MAX_ATTEMPTS,
    DISPATCH_TIMEOUT_MINUTES,
    INCUBATION_DEFAULT_MATURATION_DAYS,
    AgentDemand,
    DemandAttachment,
    DemandGroup,
)
from app.db.models.notification import Notification
from app.db.models.project import Project
from app.db.models.task import ProjectTask

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/demands", tags=["demands"])

# The Docs mount, still used by the conversion targets that write documents.
DOCS_ROOT = Path("/docs")
# Legacy attachment location, kept only for reading: everything uploaded
# before 2026-07-27 lives under /docs/anexos/demandas/<demand_id>/<original
# name>. Nothing is written there anymore (see MESSAGES_ROOT below).
ATTACHMENTS_SUBDIR = "anexos/demandas"
# Message attachments now have their own root instead of borrowing the Docs
# mount -- they are message payloads, not documents someone browses or edits
# in the Docs tree, and mixing them made "área de criação" listings show
# files nobody put there. Settable via .env (see config.py) so a backend run
# outside the container writes somewhere real.
MESSAGES_ROOT = Path(settings.MESSAGE_ATTACHMENTS_ROOT)
MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024


async def _get_demand_or_404(db: AsyncSession, demand_id: uuid.UUID) -> AgentDemand:
    demand = (
        await db.execute(select(AgentDemand).where(AgentDemand.id == demand_id))
    ).scalar_one_or_none()
    if demand is None:
        raise HTTPException(status_code=404, detail="Demand not found")
    return demand


async def _get_agent_or_404(db: AsyncSession, agent_id: uuid.UUID) -> Agent:
    agent = await db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


async def _get_agent_by_slug_or_404(db: AsyncSession, profile_slug: str) -> Agent:
    agent = (
        await db.execute(select(Agent).where(Agent.profile_slug == profile_slug))
    ).scalar_one_or_none()
    if agent is None:
        raise HTTPException(404, f"No registered agent with profile_slug {profile_slug!r}")
    return agent


async def _get_project_or_404(db: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _find_agent_by_slug(db: AsyncSession, profile_slug: str) -> Agent | None:
    """Best-effort match, no 404 -- used to auto-resolve from_agent_id from
    the free-text from_agent (see DemandSubmitIn.from_agent_id's docstring).
    A miss is expected and fine (a human note's from_agent is a username,
    not a profile slug)."""
    return (
        await db.execute(select(Agent).where(Agent.profile_slug == profile_slug))
    ).scalar_one_or_none()


async def _get_group_or_404(db: AsyncSession, group_id: uuid.UUID) -> DemandGroup:
    group = (
        await db.execute(select(DemandGroup).where(DemandGroup.id == group_id))
    ).scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=404, detail="Demand group not found")
    return group


async def _would_create_cycle(db: AsyncSession, group_id: uuid.UUID, new_parent_id: uuid.UUID) -> bool:
    """True if reparenting `group_id` under `new_parent_id` would create a
    cycle -- walks up from new_parent_id toward the root, bailing out if it
    reaches group_id itself (moving a folder into its own descendant)."""
    current_id: uuid.UUID | None = new_parent_id
    while current_id is not None:
        if current_id == group_id:
            return True
        current_id = (
            await db.execute(select(DemandGroup.parent_id).where(DemandGroup.id == current_id))
        ).scalar_one_or_none()
    return False


def _demand_preview(body: str, limit: int = 200) -> str:
    body = body.strip()
    return body if len(body) <= limit else f"{body[:limit].rstrip()}…"


async def _resolve_origin(
    db: AsyncSession, origin_type: str | None, origin_number: int | None
) -> tuple[str | None, uuid.UUID | None]:
    """(origin_type, origin_number) -> (origin_type, origin_id UUID).
    origin_number is never hand-typed by a person -- the compose form's ID
    field is disabled, display-only (both AgentDemand.number and
    ProjectTask.number are server-assigned IDENTITY columns). So
    origin_type alone (no number yet) is valid -- a category with no
    specific link yet. origin_id is meaningful only for origin_type="task"
    (a ProjectTask.number lookup, real and existing, 404 if it doesn't
    resolve) -- "backlog" never carries one. Caller (_reconcile_task_origin)
    guarantees a non-None origin_type before insert/update; None here just
    means "nothing given in this request", resolved to a default downstream."""
    if origin_type is None:
        return None, None
    if origin_type not in DEMAND_LINKED_ORIGIN_TYPES:
        # "backlog" é classificação, não vínculo -- nunca tem origin_id.
        return origin_type, None
    if origin_number is None:
        return origin_type, None
    task = (
        await db.execute(select(ProjectTask.id).where(ProjectTask.number == origin_number))
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(404, f"No task numbered #{origin_number}")
    return origin_type, task


def _resolve_incubation_owner(
    target_agent_id: uuid.UUID | None,
    from_agent_id: uuid.UUID | None,
) -> uuid.UUID:
    """Who decides an incubated thought's fate -- receive it or drop it.

    Cascade, not a single field: an item addressed to an agent is that
    agent's to decide; one addressed to nobody belongs to whoever thought
    it. Only when neither exists is there genuinely no owner, and that is
    refused rather than stored -- invariant 1 (see AgentDemand's
    incubation_owner_id docstring). Before this, such an item landed in the
    System group with no agent at all and no one to review it, which is how
    #8971 sat for four days until Athos re-filed the same problem as #9001.

    Refusing is the deliberate behaviour change here: the old code silently
    downgraded a Task with no agent into an ownerless Backlog row. The
    caller now has to name someone, which is the whole point."""
    owner = target_agent_id or from_agent_id
    if owner is None:
        raise HTTPException(
            400,
            "Incubation requires an owning agent: set To (target agent) or From "
            "(a registered sender). A thought nobody owns is never reviewed.",
        )
    return owner


def _reconcile_task_origin(
    origin_type: str | None,
    origin_id: uuid.UUID | None,
    target_agent_id: uuid.UUID | None,
    from_agent_id: uuid.UUID | None,
) -> tuple[str, uuid.UUID | None]:
    """Guarantees a non-None, valid Tipo before every insert/update
    (2026-07-28, Marcelo: "no type só sistem dois tipo task ou backlog e o
    campo é obrigatório... então não tem None") -- the single choke point
    both create_demand_and_notify and update_demand funnel through.

    No Tipo given at all defaults to Backlog: parked work, addressed or
    not, is the safe default for "caller didn't say" -- never silently
    promotes something to trackable/dispatchable work it never asked to be.

    Task is work to execute -- unlike Backlog (parked, possibly not even
    assigned yet), it must always have **both** a target agent (who runs
    it) and a From agent (who it's for) on the record. Missing target: a
    Task chegando em Incoming precisa ser executada pelo seu agente
    (2026-07-27). Missing From: "se o agente não tem (to), não tem
    retorno. Preciso ter agente (from) no tipo task. Isso é regra"
    (2026-07-28, Marcelo -- a Task addressed to someone but from no known
    agent has nobody for its `dispatch_result`/return message to belong
    to, and can never carry `requires_response` meaningfully). Rather than
    reject either case, it is silently downgraded to Backlog -- landing in
    Incoming/Sistema exactly like a Backlog item always has, guaranteed
    never to run (the scheduled loop only ever picks up a target'd item
    with a real sender -- see run_scheduled_dispatch_pass's query -- and
    the manual dispatch route already refuses a Backlog item with no
    sender -- see the dispatch route's docstring), until someone sets both
    and promotes it back to Task.

    `origin_id` is cleared alongside either downgrade: Backlog is a
    classification, never a link (see AgentDemand.origin_id's docstring) --
    a Task-with-no-agent that happened to reference a real ProjectTask by
    number must not carry that link into Backlog, which structurally never
    has one.

    Checked on both create and update, since the reading pane's "Promover a
    Task" button flips origin_type through the same PATCH as any other
    edit."""
    if origin_type is None or (
        origin_type == "task" and (target_agent_id is None or from_agent_id is None)
    ):
        return "incubation", None
    return origin_type, origin_id


async def create_demand_and_notify(db: AsyncSession, payload: DemandSubmitIn) -> AgentDemand:
    """Every new inbox item also surfaces in the system Notifications bell
    (source="system", not "cron") -- so arriving mail doesn't go unnoticed
    unless the user happens to have the Inbox page open. event_key is
    demand-id-scoped so re-notifying the same demand is impossible."""
    origin_type, origin_id = await _resolve_origin(db, payload.origin_type, payload.origin_number)

    target_agent_id = payload.target_agent_id
    if target_agent_id is not None:
        await _get_agent_or_404(db, target_agent_id)
    elif payload.target_agent_slug is not None:
        target_agent_id = (await _get_agent_by_slug_or_404(db, payload.target_agent_slug)).id

    from_agent_id = payload.from_agent_id
    if from_agent_id is not None:
        await _get_agent_or_404(db, from_agent_id)
    else:
        auto_matched = await _find_agent_by_slug(db, payload.from_agent)
        if auto_matched is not None:
            from_agent_id = auto_matched.id

    if payload.scheduled_at is not None and target_agent_id is None:
        raise HTTPException(400, "scheduled_at requires target_agent_id")
    origin_type, origin_id = _reconcile_task_origin(origin_type, origin_id, target_agent_id, from_agent_id)
    scheduled_at = payload.scheduled_at
    if origin_type == "task" and target_agent_id is not None and scheduled_at is None:
        # A Task is work to execute, not filed for later -- unlike Backlog/
        # Nota it must actually run. Defaulting Send-at to now here (not just
        # in the compose form) is what closes the gap for every other writer
        # of this endpoint: the bridge-token /submit path (an agent, or the
        # MCP's send_agent_message without to_agent's scheduling logic) and
        # any future caller that forgets to set it. See
        # AgentDemand.scheduled_at's docstring for how the background loop
        # actually dispatches it.
        scheduled_at = datetime.now(timezone.utc)
    if payload.project_id is not None:
        await _get_project_or_404(db, payload.project_id)

    # The three incubation invariants, applied at the single choke point
    # every insert goes through: an owner, an explicit state, and a
    # deadline to decide. A task carries none of them (all NULL).
    incubation_owner_id: uuid.UUID | None = None
    incubation_state: str | None = None
    matures_at: datetime | None = None
    if origin_type == "incubation":
        incubation_owner_id = _resolve_incubation_owner(target_agent_id, from_agent_id)
        incubation_state = "incubating"
        matures_at = datetime.now(timezone.utc) + timedelta(
            days=INCUBATION_DEFAULT_MATURATION_DAYS
        )

    demand = AgentDemand(
        from_agent=payload.from_agent,
        from_agent_id=from_agent_id,
        subject=payload.subject,
        body=payload.body,
        status=payload.status or "new",
        target_agent_id=target_agent_id,
        project_id=payload.project_id,
        origin_type=origin_type,
        origin_id=origin_id,
        incubation_owner_id=incubation_owner_id,
        incubation_state=incubation_state,
        matures_at=matures_at,
        working_path=payload.working_path,
        # Meio de comunicação: por onde o pedido entrou e, portanto, por onde
        # o resultado tem de voltar (2026-08-13). Sem isto o resultado fica
        # preso no Messages -- é o que o feedback lê para saber o destino.
        channel=payload.channel,
        channel_ref=payload.channel_ref,
        requires_response=payload.requires_response,
        scheduled_at=scheduled_at,
    )
    db.add(demand)
    await db.flush()  # assigns demand.id (Python-side default) before the notification references it

    notification = Notification(
        source="system",
        severity="info",
        title=f"New in Inbox: {demand.subject}",
        message=_demand_preview(payload.body),
        event_key=f"demand:{demand.id}",
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(notification)

    await db.commit()
    await db.refresh(demand)
    return demand


@router.post("/submit", response_model=DemandOut, status_code=status.HTTP_201_CREATED)
async def submit_demand(
    payload: DemandSubmitIn,
    x_bridge_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> AgentDemand:
    """Public path (see main.py's _PUBLIC_API_PATHS) guarded by the shared
    bridge token -- the same trust boundary the chat bridge and the
    Auditor's cron trigger use, so any Hermes agent on the host can submit
    a demand with a plain curl (no user JWT available to a cron/agent)."""
    if not settings.CHAT_BRIDGE_TOKEN or x_bridge_token != settings.CHAT_BRIDGE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid bridge token")
    return await create_demand_and_notify(db, payload)


@router.get("/pending", response_model=list[DemandOut])
async def list_pending_for_agent(
    agent: str,
    x_bridge_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[AgentDemand]:
    """Public path (bridge-token, see main.py's _PUBLIC_API_PATHS) for an
    agent's own cron/loop to pull its unprocessed inbox mail. Most Hermes
    profiles have no runtime_type and so can never be reached by the
    scheduled-dispatch background loop's CLI spawn (see
    run_scheduled_dispatch_pass) -- this is how they're meant to notice a
    message addressed to them instead: check in, on their own schedule,
    rather than be dispatched. `agent` is a Hermes profile_slug, resolved
    the same way target_agent_slug is on submit.

    Pulling a message here IS the acknowledgment (agent_processed_at gets
    stamped in the same call) -- there's no separate ack endpoint, since a
    cron-driven caller isn't guaranteed to come back afterward. A message
    only shows up here once (per agent), the same way a queue dequeues,
    so the caller's own loop body is the only record of what it decided to
    do with it."""
    if not settings.CHAT_BRIDGE_TOKEN or x_bridge_token != settings.CHAT_BRIDGE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid bridge token")
    resolved = await _get_agent_by_slug_or_404(db, agent)
    result = await db.execute(
        select(AgentDemand)
        .where(
            AgentDemand.target_agent_id == resolved.id,
            AgentDemand.agent_processed_at.is_(None),
        )
        .order_by(AgentDemand.created_at)
    )
    pending = list(result.scalars().all())
    now = datetime.now(timezone.utc)
    for demand in pending:
        demand.agent_processed_at = now
    await db.commit()
    for demand in pending:
        await db.refresh(demand)
    return pending


@router.get("/for-agent", response_model=list[DemandOut])
async def list_for_agent(
    agent: str,
    direction: str = "all",
    status_filter: str | None = None,
    dispatch_status: str | None = None,
    number: int | None = None,
    origin_type: str | None = None,
    owned_only: bool = False,
    limit: int = 50,
    x_bridge_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[AgentDemand]:
    """An agent's own messages, filtered, **without consuming anything**.

    Deliberately separate from /pending, which is a queue: pulling there
    stamps `agent_processed_at` and the message is never handed out again.
    That makes it useless for the question this endpoint answers -- "what is
    the state of the messages I sent / received?" -- because merely looking
    would swallow the unread ones. Here nothing is mutated, so it is safe to
    poll.

    Two independent status axes, both optional (see the model): `status_filter`
    is the human read/convert lifecycle (new/read/converted/archived) and
    `dispatch_status` is the execution one (pending/dispatched/running/
    completed/failed, plus the literal "none" for messages that were never
    dispatched -- NULL is a meaningful state here, not a missing filter).

    `direction` is relative to `agent`: "outgoing" is what it sent
    (from_agent_id), "incoming" what was addressed to it (target_agent_id),
    "all" either. Public path guarded by the shared bridge token, same as
    /submit and /pending -- an agent has no user JWT."""
    if not settings.CHAT_BRIDGE_TOKEN or x_bridge_token != settings.CHAT_BRIDGE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid bridge token")
    if direction not in {"all", "incoming", "outgoing"}:
        raise HTTPException(
            status_code=400, detail="direction must be one of: all, incoming, outgoing"
        )
    if status_filter is not None and status_filter not in DEMAND_STATUSES:
        raise HTTPException(
            status_code=400, detail=f"status must be one of: {', '.join(DEMAND_STATUSES)}"
        )
    if dispatch_status is not None and dispatch_status not in (*DEMAND_DISPATCH_STATUSES, "none"):
        raise HTTPException(
            status_code=400,
            detail=f"dispatch_status must be one of: {', '.join(DEMAND_DISPATCH_STATUSES)}, none",
        )
    resolved = await _get_agent_by_slug_or_404(db, agent)

    query = select(AgentDemand)
    if direction == "incoming":
        query = query.where(AgentDemand.target_agent_id == resolved.id)
    elif direction == "outgoing":
        query = query.where(AgentDemand.from_agent_id == resolved.id)
    else:
        query = query.where(
            or_(
                AgentDemand.target_agent_id == resolved.id,
                AgentDemand.from_agent_id == resolved.id,
            )
        )
    if status_filter is not None:
        query = query.where(AgentDemand.status == status_filter)
    if dispatch_status == "none":
        query = query.where(AgentDemand.dispatch_status.is_(None))
    elif dispatch_status is not None:
        query = query.where(AgentDemand.dispatch_status == dispatch_status)
    if number is not None:
        query = query.where(AgentDemand.number == number)
    if origin_type is not None:
        if origin_type not in DEMAND_ORIGIN_TYPES:
            raise HTTPException(400, f"origin_type must be one of {DEMAND_ORIGIN_TYPES}")
        query = query.where(AgentDemand.origin_type == origin_type)
    if owned_only:
        # Whose thought it is to decide -- a different question from who sent
        # or received it, which is what `direction` answers. An incubation
        # addressed to A by B is owned by A, and only shows up here for A.
        query = query.where(AgentDemand.incubation_owner_id == resolved.id)

    # number breaks the tie: rows written in the same transaction share a
    # created_at, and an unstable order would make paging/limit arbitrary.
    query = query.order_by(AgentDemand.created_at.desc(), AgentDemand.number.desc()).limit(
        max(1, min(limit, 200))
    )
    result = await db.execute(query)
    return list(result.scalars().all())


async def _get_owned_incubation_or_error(
    db: AsyncSession, demand_id: uuid.UUID, agent_slug: str
) -> AgentDemand:
    """The item, if it is an incubation this agent actually owns.

    Ownership is checked rather than assumed: these two routes are the
    agent's own decision surface, and one agent deciding another's thoughts
    would make "owner" meaningless. A wrong agent gets 403, not 404 -- the
    item does exist, it just isn't theirs to decide."""
    demand = await _get_demand_or_404(db, demand_id)
    if demand.origin_type != "incubation":
        raise HTTPException(400, "This message is not incubating -- only an incubation can be received or dropped")
    if demand.incubation_state in ("promoted", "dropped"):
        raise HTTPException(
            409, f"Already decided: this thought was {demand.incubation_state}"
        )
    owner = await _get_agent_or_404(db, demand.incubation_owner_id) if demand.incubation_owner_id else None
    if owner is None or owner.profile_slug != agent_slug:
        raise HTTPException(
            403,
            f"Only the owning agent decides this thought "
            f"(owner: {owner.profile_slug if owner else 'none'})",
        )
    return demand


@router.post("/{demand_id}:reprocess", response_model=DemandOut)
async def reprocess_demand(
    demand_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> AgentDemand:
    """Puts a failed dispatch back in the queue (2026-08-13).

    Manual on purpose -- an automatic retry on a permanent failure (an agent
    with no runtime, a target that no longer exists) would burn cycles every
    30 seconds and hide the problem instead of surfacing it. Someone looks,
    fixes the cause, and asks for it again.

    Clears the execution state rather than dispatching inline: with
    `dispatch_status` back to NULL and `scheduled_at` due, the existing
    scheduled pass picks it up on its next cycle -- and, importantly, does so
    under the concurrency cap. Reprocessing a whole group would otherwise be
    a way to start dozens of runs at once, which is exactly what the cap is
    there to prevent.

    `dispatch_attempts` is deliberately NOT reset: it is the record of how
    many times this was tried, and resetting it would turn the limit below
    into something that can never be reached.
    """
    demand = await _get_demand_or_404(db, demand_id)
    if demand.dispatch_status != "failed":
        raise HTTPException(400, "Only a failed dispatch can be reprocessed")
    if (demand.dispatch_attempts or 0) >= DISPATCH_MAX_ATTEMPTS:
        raise HTTPException(
            409,
            f"This message already failed {demand.dispatch_attempts} times "
            f"(limit {DISPATCH_MAX_ATTEMPTS}). Fix the cause rather than retrying it again.",
        )
    if demand.target_agent_id is None:
        raise HTTPException(400, "This message has no target agent to dispatch to")

    demand.dispatch_status = None
    demand.agent_run_id = None
    demand.dispatch_deadline_at = None
    demand.notice_sent = False
    demand.scheduled_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(demand)
    return demand


@router.post("/{demand_id}/incubation:receive", response_model=DemandOut)
async def receive_incubation(
    demand_id: uuid.UUID,
    agent: str,
    x_bridge_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> AgentDemand:
    """The owning agent takes the thought on: it becomes a Task (2026-08-13).

    One of the two real outcomes of incubation -- the other is
    /incubation:drop. Together they are what closes the loop the maturation
    sweep opens, and without them an agent handed a decision has no way to
    answer it.

    Promotion needs both agents on the record (the 2026-07-28 Task rule), so
    a thought with no sender stays incubating and says so rather than
    becoming a Task nobody can run. Deliberately does not dispatch here:
    scheduling is _reconcile_task_origin's job on the next write, and an
    agent deciding "yes, this is work" is a separate act from that work
    starting."""
    if not settings.CHAT_BRIDGE_TOKEN or x_bridge_token != settings.CHAT_BRIDGE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid bridge token")
    demand = await _get_owned_incubation_or_error(db, demand_id, agent)

    if demand.target_agent_id is None or demand.from_agent_id is None:
        raise HTTPException(
            400,
            "A Task needs both a sender (From) and a target (To). Set the missing "
            "one before receiving this thought, or drop it.",
        )
    demand.origin_type = "task"
    # The listener clears owner/state/matures_at on the type change; the row
    # is a Task now and its own lifecycle takes over (see the model's
    # _fill_incubation_defaults).
    if demand.scheduled_at is None and demand.dispatch_status is None:
        demand.scheduled_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(demand)
    return demand


@router.post("/{demand_id}/incubation:drop", response_model=DemandOut)
async def drop_incubation(
    demand_id: uuid.UUID,
    agent: str,
    reason: str,
    x_bridge_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> AgentDemand:
    """The owning agent declines the thought, with a reason (2026-08-13).

    `reason` is required by the route and by a DB constraint, not merely
    encouraged: a drop without one is indistinguishable from the item having
    been forgotten, and there would be no way to notice an agent
    systematically discarding what mattered. Never a DELETE for the same
    reason -- the row stays, archived, as the record that this was
    considered and declined."""
    if not settings.CHAT_BRIDGE_TOKEN or x_bridge_token != settings.CHAT_BRIDGE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid bridge token")
    if not reason.strip():
        raise HTTPException(400, "A drop needs a reason -- say why this thought isn't worth taking on")
    demand = await _get_owned_incubation_or_error(db, demand_id, agent)

    demand.incubation_state = "dropped"
    demand.drop_reason = reason.strip()
    demand.status = "archived"
    await db.commit()
    await db.refresh(demand)
    return demand


@router.post("", response_model=DemandOut, status_code=status.HTTP_201_CREATED)
async def create_demand(
    payload: DemandSubmitIn, db: AsyncSession = Depends(get_db)
) -> AgentDemand:
    """Authenticated (JWT, normal RequireAuthMiddleware) counterpart to
    /submit's bridge-token path -- backs the chat's "/demanda" command:
    ForgeHub itself (on the logged-in user's behalf) files the agent's
    reply into the inbox, as opposed to an autonomous host-side agent
    submitting on its own."""
    return await create_demand_and_notify(db, payload)


@router.get("", response_model=list[DemandOut])
async def list_demands(
    status_filter: str | None = None, db: AsyncSession = Depends(get_db)
) -> list[AgentDemand]:
    query = select(AgentDemand).order_by(AgentDemand.created_at.desc())
    if status_filter is not None:
        query = query.where(AgentDemand.status == status_filter)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/groups", response_model=list[DemandGroupOut])
async def list_demand_groups(db: AsyncSession = Depends(get_db)) -> list[DemandGroup]:
    """Flat list -- the frontend builds the tree from parent_id, same as
    DocTree builds its tree from filesystem path segments."""
    result = await db.execute(select(DemandGroup).order_by(DemandGroup.name))
    return list(result.scalars().all())


@router.post("/groups", response_model=DemandGroupOut, status_code=status.HTTP_201_CREATED)
async def create_demand_group(
    payload: DemandGroupCreateIn, db: AsyncSession = Depends(get_db)
) -> DemandGroup:
    if payload.parent_id is not None:
        await _get_group_or_404(db, payload.parent_id)
    group = DemandGroup(name=payload.name, parent_id=payload.parent_id)
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return group


@router.patch("/groups/{group_id}", response_model=DemandGroupOut)
async def update_demand_group(
    group_id: uuid.UUID, payload: DemandGroupUpdateIn, db: AsyncSession = Depends(get_db)
) -> DemandGroup:
    """Rename and/or reparent (drag a folder onto another folder, or onto
    the Arquivados root by sending parent_id: null explicitly)."""
    group = await _get_group_or_404(db, group_id)
    data = payload.model_dump(exclude_unset=True)
    if "parent_id" in data:
        new_parent_id = data["parent_id"]
        if new_parent_id is not None:
            await _get_group_or_404(db, new_parent_id)
            if await _would_create_cycle(db, group_id, new_parent_id):
                raise HTTPException(status_code=400, detail="Cannot move a folder into its own descendant")
        group.parent_id = new_parent_id
    if "name" in data:
        group.name = data["name"]
    await db.commit()
    await db.refresh(group)
    return group


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_demand_group(group_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    """Cascades to subfolders (DemandGroup.parent_id's ondelete=CASCADE);
    demands filed directly under this folder fall back to the Arquivados
    root instead of being deleted (AgentDemand.group_id's ondelete=SET NULL)."""
    group = await _get_group_or_404(db, group_id)
    await db.delete(group)
    await db.commit()


@router.get("/{demand_id}", response_model=DemandOut)
async def get_demand(demand_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> AgentDemand:
    """A single message. Added 2026-07-26 to close a real hole in the
    resource: it only ever exposed GET on the collection, so anything that
    wanted the current state of *one* message -- an agent checking whether
    its own dispatch finished, a caller following up on a `/submit`
    response -- had to download every demand in the system and filter
    client-side. Registered after every literal-path route above
    (/pending, /groups, ...) so those aren't swallowed by {demand_id}."""
    return await _get_demand_or_404(db, demand_id)


@router.patch("/{demand_id}", response_model=DemandOut)
async def update_demand(
    demand_id: uuid.UUID, payload: DemandUpdateIn, db: AsyncSession = Depends(get_db)
) -> AgentDemand:
    demand = await _get_demand_or_404(db, demand_id)
    data = payload.model_dump(exclude_unset=True)
    if "group_id" in data:
        if data["group_id"] is not None:
            await _get_group_or_404(db, data["group_id"])
        demand.group_id = data["group_id"]
    if "target_agent_id" in data:
        if data["target_agent_id"] is not None:
            await _get_agent_or_404(db, data["target_agent_id"])
        demand.target_agent_id = data["target_agent_id"]
    if "from_agent_id" in data:
        if data["from_agent_id"] is not None:
            await _get_agent_or_404(db, data["from_agent_id"])
        demand.from_agent_id = data["from_agent_id"]
    if "project_id" in data:
        if data["project_id"] is not None:
            await _get_project_or_404(db, data["project_id"])
        demand.project_id = data["project_id"]
    if "subject" in data:
        demand.subject = data["subject"]
    if "body" in data:
        demand.body = data["body"]
    if "working_path" in data:
        # Editable after the fact on purpose: the cwd a run should start in
        # is usually discovered when the message is read, not when it is
        # filed. Only affects dispatches that haven't happened yet.
        demand.working_path = data["working_path"]
    if "origin_type" in data or "origin_number" in data:
        origin_type, origin_id = await _resolve_origin(
            db, data.get("origin_type"), data.get("origin_number")
        )
        demand.origin_type = origin_type
        demand.origin_id = origin_id
    if "requires_response" in data:
        demand.requires_response = data["requires_response"]
    if "scheduled_at" in data and data["scheduled_at"] != demand.scheduled_at:
        # Once a dispatch has happened, "Send at" is history, not a knob:
        # the scheduled-send loop only ever picks up items with
        # dispatch_status IS NULL, so rewriting the time can't re-send
        # anything -- it would only falsify the record of when this message
        # was actually sent (2026-07-26). Rejected server-side and not just
        # disabled in the form, since the form isn't the only writer.
        if demand.dispatch_status is not None:
            raise HTTPException(
                400, "This message was already dispatched -- its scheduled send time can't be changed"
            )
        new_target_agent_id = data.get("target_agent_id", demand.target_agent_id)
        if data["scheduled_at"] is not None and new_target_agent_id is None:
            raise HTTPException(400, "scheduled_at requires target_agent_id")
        demand.scheduled_at = data["scheduled_at"]
    if "status" in data:
        demand.status = data["status"]
    elif "group_id" in data and data["group_id"] is not None:
        # Filing a demand into an Arquivados subfolder always archives it,
        # even if the caller only sent group_id (the Inbox drag-and-drop
        # case -- see InboxGroupTree's drop handler).
        demand.status = "archived"

    # Reconciled against the *final* merged state, not just this request's
    # fields: promoting Incubation -> Task (the reading pane's "Promover a
    # Task" button) goes through this same PATCH, and clearing To or From
    # on an already-Task message (or any other edit that leaves it missing
    # either agent) must downgrade it back to Incubation rather than leave a
    # Task with nobody to run it or nobody it belongs to.
    was_incubation = demand.origin_type == "incubation"
    demand.origin_type, demand.origin_id = _reconcile_task_origin(
        demand.origin_type, demand.origin_id, demand.target_agent_id, demand.from_agent_id
    )
    # Keep the incubation invariants true across a Tipo change in either
    # direction -- the DB constraints enforce them, so an edit that flips
    # the type without carrying the fields would fail the insert rather
    # than silently store a half-state.
    if demand.origin_type == "incubation":
        demand.incubation_owner_id = _resolve_incubation_owner(
            demand.target_agent_id, demand.from_agent_id
        )
        if demand.incubation_state is None:
            demand.incubation_state = "incubating"
        if demand.matures_at is None:
            demand.matures_at = datetime.now(timezone.utc) + timedelta(
                days=INCUBATION_DEFAULT_MATURATION_DAYS
            )
    elif was_incubation:
        # Promoted to Task: the thought was received, which is one of the
        # two real outcomes. The owner/state/deadline stop applying, but
        # "promoted" is not recorded here as a lingering state -- the row
        # is now a Task and its own lifecycle takes over.
        demand.incubation_owner_id = None
        demand.incubation_state = None
        demand.matures_at = None
    if (
        demand.origin_type == "task"
        and demand.target_agent_id is not None
        and demand.dispatch_status is None
        and demand.scheduled_at is None
    ):
        # Never dispatched and never scheduled -- auto-schedule now so the
        # background loop actually runs it, same reasoning as
        # create_demand_and_notify. Only fires once: after this, scheduled_at
        # is no longer None, so a later unrelated edit won't re-trigger it.
        demand.scheduled_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(demand)
    return demand


@router.delete("/{demand_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_demand(demand_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    """Delete a message and the files attached to it.

    The attachment *rows* go with the message on their own (ON DELETE CASCADE),
    but the bytes on disk do not -- until 2026-07-27 they were simply left
    behind, so every deleted message leaked its attachments into the storage
    root forever. Files are removed before the row so a failure here surfaces
    instead of orphaning them silently; a file already gone is not an error."""
    demand = await _get_demand_or_404(db, demand_id)
    attachments = (
        await db.execute(
            select(DemandAttachment).where(DemandAttachment.demand_id == demand_id)
        )
    ).scalars().all()
    for attachment in attachments:
        target = _resolve_attachment_file(attachment)
        if target is not None and target.is_file():
            target.unlink()
    await db.delete(demand)
    await db.commit()


def _resolve_attachment_file(attachment: DemandAttachment) -> Path | None:
    """Locate an attachment's bytes, new root first then the legacy one.

    `path` is stored relative to whichever root was in use when the file was
    written, and rows created before 2026-07-27 are relative to /docs. Rather
    than rewriting those rows (and moving files a user may have open, for a
    handful of historical attachments), reads try the current root and fall
    back -- an old attachment keeps downloading, a new one never touches the
    Docs tree. The legacy paths are recognisable: they carry the
    `anexos/demandas/` prefix, which a new flat name can never have.
    """
    target = resolve_doc_path(MESSAGES_ROOT, attachment.path)
    if target is not None and target.is_file():
        return target
    legacy = resolve_doc_path(DOCS_ROOT, attachment.path)
    if legacy is not None and legacy.is_file():
        return legacy
    return target


def _stored_attachment_name(attachment_id: uuid.UUID, demand_number: int, original: str) -> str:
    """The on-disk name for an attachment: `<attachment id>_<message number>_
    <UTC timestamp><extension>`.

    The uploaded name is kept in the `filename` column and is what the UI
    shows and what a download is served as -- it is deliberately *not* what
    lands on disk. Attachments used to be written under their original name in
    a per-message folder, so uploading two files called `report.pdf` to the
    same message left one file on disk and two rows pointing at it: the first
    upload's bytes were silently replaced and its recorded size no longer
    matched what would be downloaded. The attachment UUID alone already makes
    the name unique; the message number and timestamp are there so a human
    listing the directory can tell what a file belongs to without a DB lookup.
    """
    suffix = Path(original).suffix.lower()[:16]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{attachment_id}_{demand_number}_{stamp}{suffix}"


@router.post("/{demand_id}/attachments", response_model=DemandAttachmentOut, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    demand_id: uuid.UUID,
    file: UploadFile = File(...),
    description: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
) -> DemandAttachment:
    """Attach one file to a message. Call it once per file -- multipart with a
    caption per file is far simpler as N requests than as one request with
    parallel file/description arrays, and the UI already uploads in a loop, so
    a failed file doesn't take the others down with it."""
    demand = await _get_demand_or_404(db, demand_id)
    name = Path(file.filename or "").name
    if not name:
        raise HTTPException(status_code=400, detail="Missing filename")
    content = await file.read()
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 50MB upload limit")
    attachment_id = uuid.uuid4()
    rel_path = _stored_attachment_name(attachment_id, demand.number, name)
    target = resolve_doc_path(MESSAGES_ROOT, rel_path)
    if target is None:
        raise HTTPException(status_code=400, detail="Invalid filename")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    caption = (description or "").strip()
    attachment = DemandAttachment(
        id=attachment_id,
        demand_id=demand.id,
        filename=name,
        path=rel_path,
        size_bytes=len(content),
        content_type=file.content_type,
        # Empty stays NULL: "no description" and "description cleared to
        # blank" must not be two different states in the column.
        description=caption[:500] or None,
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)
    return attachment


@router.get("/{demand_id}/attachments/{attachment_id}/download")
async def download_attachment(
    demand_id: uuid.UUID, attachment_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> FileResponse:
    attachment = (
        await db.execute(
            select(DemandAttachment).where(
                DemandAttachment.id == attachment_id, DemandAttachment.demand_id == demand_id
            )
        )
    ).scalar_one_or_none()
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    target = _resolve_attachment_file(attachment)
    if target is None or not target.is_file():
        raise HTTPException(status_code=404, detail="Attachment file missing on disk")
    return FileResponse(target, filename=attachment.filename)


@router.delete("/{demand_id}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment(
    demand_id: uuid.UUID, attachment_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> None:
    attachment = (
        await db.execute(
            select(DemandAttachment).where(
                DemandAttachment.id == attachment_id, DemandAttachment.demand_id == demand_id
            )
        )
    ).scalar_one_or_none()
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    target = _resolve_attachment_file(attachment)
    if target is not None and target.is_file():
        target.unlink()
    await db.delete(attachment)
    await db.commit()


@router.post("/{demand_id}/notify-telegram")
async def notify_telegram(demand_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """"Encaminhar pro Telegram": proxies the host-bridge's
    /v1/messages/send (see host-bridge/send_message.py), which forwards
    through Hermes's already-configured cross-channel gateway -- no
    target/chat_id needed, "telegram" alone resolves to the home channel
    (the user's own Telegram) via ~/.hermes/config.yaml."""
    demand = await _get_demand_or_404(db, demand_id)
    text = f"*{demand.subject}*\n\n{demand.body}"[:4000]
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.CHAT_BRIDGE_URL}/v1/messages/send",
            headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
            json={"target": "telegram", "message": text},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Host-bridge error: {resp.text[:500]}")
    return resp.json()


def _extract_run_result_text(run: dict[str, Any]) -> str:
    """Best-effort human-readable text from a finished agent-runs output --
    each CLI's --json/--output-format json shape is different, verified
    against real runs (dates below) rather than guessed:
    - claude --output-format json: one object, top-level "result" string
      (2026-07-23).
    - openclaw agent --json: one object, answer at
      result.meta.finalAssistantVisibleText (2026-07-25).
    - codex exec --json: newline-delimited events; the answer is the last
      {"item": {"type": "agent_message", "text": ...}} event (2026-07-25).
    - hermes chat -q ... -Q and agy --print: plain text already, no JSON
      to unwrap.
    Falls back to the raw output/error when none of these shapes match."""
    output = (run.get("output") or "").strip()
    if not output:
        return (run.get("error") or "").strip() or "(no output)"

    try:
        parsed = json.loads(output)
    except (json.JSONDecodeError, ValueError):
        parsed = None
    if isinstance(parsed, dict):
        if isinstance(parsed.get("result"), str):
            return parsed["result"]
        result = parsed.get("result")
        if isinstance(result, dict):
            meta = result.get("meta")
            if isinstance(meta, dict) and isinstance(meta.get("finalAssistantVisibleText"), str):
                return meta["finalAssistantVisibleText"]

    last_message: str | None = None
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        item = event.get("item") if isinstance(event, dict) else None
        if isinstance(item, dict) and item.get("type") == "agent_message" and isinstance(item.get("text"), str):
            last_message = item["text"]
    if last_message is not None:
        return last_message

    return output


async def _send_notice(text: str) -> None:
    """Best-effort Telegram notice for an "independent" dispatch (§5 of the
    dispatch proposal) -- same proxy notify_telegram above already uses.
    Never blocks/fails the dispatch itself: the run already started, a
    notice delivery hiccup shouldn't roll that back."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.post(
                f"{settings.CHAT_BRIDGE_URL}/v1/messages/send",
                headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
                json={"target": "telegram", "message": text[:4000]},
            )
    except httpx.HTTPError:
        pass


async def _execute_dispatch(
    db: AsyncSession, demand: AgentDemand, target_agent_id: uuid.UUID, command_text: str | None
) -> AgentDemand:
    """Shared core of a dispatch -- sends this item's context (+ an
    instruction, if any) as a prompt to a target agent's CLI via the
    host-bridge's governed runner (app/core/agent_runs.py). Used by both
    the manual POST .../dispatch route and the scheduled-send background
    loop (main.py's _scheduled_dispatch_poll_loop, triggered once
    AgentDemand.scheduled_at is reached). Caller commits."""
    agent = await _get_agent_or_404(db, target_agent_id)

    # Independent vs. descendant: no origin, a task origin (not yet
    # cross-referenced against an assignee -- v1 always treats these as
    # independent), or an origin dispatched to a DIFFERENT agent all count
    # as independent. Staying with the same already-notified target agent
    # never re-notifies.
    independent = True
    if demand.reply_to_id is not None:
        origin = await db.get(AgentDemand, demand.reply_to_id)
        if origin is not None and origin.target_agent_id == target_agent_id:
            independent = False

    prompt = build_thread_prompt(demand, command_text)
    # Use working_path from demand if provided, otherwise fall back to AGENT_RUNTIME_PATHS
    project_path = demand.working_path or settings.AGENT_RUNTIME_PATHS.get(agent.runtime_type, "/root")

    run_id = str(uuid.uuid4())
    run = await dispatch_agent_run(run_id, agent, prompt, project_path)

    demand.target_agent_id = target_agent_id
    demand.command_text = command_text
    demand.agent_run_id = run["run_id"]
    demand.dispatch_status = "dispatched"
    # Contingency bookkeeping (2026-08-13): every dispatch carries a deadline
    # and counts as an attempt, so a run that hangs can be failed by the
    # timeout sweep and a message that keeps failing can stop being retried.
    demand.dispatch_deadline_at = datetime.now(timezone.utc) + timedelta(
        minutes=DISPATCH_TIMEOUT_MINUTES
    )
    demand.dispatch_attempts = (demand.dispatch_attempts or 0) + 1
    demand.dispatch_error = None

    if independent and not demand.notice_sent:
        await _send_notice(f"*Disparo para {agent.name}*\n\n{prompt}")
        demand.notice_sent = True

    return demand


def _assert_dispatchable(demand: AgentDemand) -> None:
    """Backlog work cannot be executed without a registered sender.

    `backlog` is parked work: not a task yet, and by definition nobody has
    taken it on. Dispatching one anyway produces a run with no agent on the
    record to answer for it -- the reply has nowhere to route back to
    (`requires_response` needs `from_agent_id`), and the execution shows up
    owned by a free-text label like "marcelo" that resolves to no agent at
    all. So a backlog item runs only once it has a real sender; setting From
    on the message is what puts it in play.

    Deliberately not extended to `task`: since 2026-07-28, `_reconcile_task_origin`
    already guarantees a Task can't exist without `from_agent_id` (downgraded
    to Backlog otherwise), so this guard structurally never fires for one --
    this check exists for Backlog specifically because that Tipo doesn't
    require an agent by default.
    """
    if demand.origin_type == "incubation" and demand.from_agent_id is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "A Backlog item cannot be dispatched without a registered sender (From). "
                "Set From to an agent, or promote it to Task first."
            ),
        )


async def _dispatch_slots(db: AsyncSession) -> int:
    """How many more dispatches may start right now.

    Counts what is **already in flight** (dispatched/running), not just what
    this pass is about to send: a limit applied per pass would let every
    30-second cycle add another batch on top of the runs still going, which
    is no limit at all. Each in-flight run is a real agent CLI on the host.

    The configured value is clamped to MAX_CONCURRENT_DISPATCHES_CEILING --
    forgehub.config is operator-editable and can hold any number, and this
    is the point where a typo stops being able to swamp the machine.
    """
    limit = max(1, min(settings.MAX_CONCURRENT_DISPATCHES, settings.MAX_CONCURRENT_DISPATCHES_CEILING))
    in_flight = (
        await db.execute(
            select(func.count())
            .select_from(AgentDemand)
            .where(AgentDemand.dispatch_status.in_(("dispatched", "running")))
        )
    ).scalar_one()
    return max(0, limit - int(in_flight))


async def _agents_already_running(db: AsyncSession) -> set[uuid.UUID]:
    """Agents with a run already in flight, which must not get a second one.

    One run per agent at a time (2026-08-13, Marcelo: "para os processos não
    misturar"). The global cap alone doesn't give this: five free slots all
    landing on the same agent would start five sessions of the same CLI
    against the same profile directory and the same working path, and their
    contexts would overlap -- the runtime keeps per-session state, so
    concurrent runs of one agent interfere with each other rather than
    simply queueing.

    Serialising per agent while staying parallel across agents is what makes
    the cap safe to raise: the machine bounds the total, and this bounds what
    any single agent is doing.
    """
    rows = (
        await db.execute(
            select(AgentDemand.target_agent_id).where(
                AgentDemand.dispatch_status.in_(("dispatched", "running")),
                AgentDemand.target_agent_id.isnot(None),
            )
        )
    ).scalars().all()
    return set(rows)


async def _fail_dispatch(
    db: AsyncSession, demand: AgentDemand, reason: str, *, title: str
) -> None:
    """Marks a dispatch failed and tells the user, whatever broke.

    One place for every failure mode (never dispatched, timed out, run
    errored) so "notificação de todas as falhas" can't be true for one path
    and quietly false for the others -- before this, only the
    AgentRunDispatchError path notified anyone at all.

    Deliberately does not commit: callers batch this with their own state
    changes, matching the rest of this module ("Caller commits").
    """
    demand.dispatch_status = "failed"
    demand.dispatch_error = reason
    demand.dispatch_deadline_at = None
    db.add(
        Notification(
            source="system",
            severity="error",
            title=title,
            message=f"#{demand.number}: {reason}",
            # Attempt-scoped, not just demand-scoped: a reprocess that fails
            # again is a new event the user has to hear about, and a plain
            # demand-scoped key would silently swallow it.
            event_key=f"demand-dispatch-failed:{demand.id}:{demand.dispatch_attempts}",
            occurred_at=datetime.now(timezone.utc),
        )
    )


async def run_dispatch_timeout_pass(db: AsyncSession) -> int:
    """Fails dispatches that never came back within the deadline.

    The failure mode this closes is the worst of the five: a run that hangs
    stays at "running" forever, never reaches a terminal state, and so never
    fires the feedback that only triggers on completed/failed -- whoever
    asked waits indefinitely with no error to show. The host-bridge's own
    max_seconds cannot cover it, since a dead bridge enforces nothing.
    """
    now = datetime.now(timezone.utc)
    stalled = (
        await db.execute(
            select(AgentDemand).where(
                AgentDemand.dispatch_deadline_at.isnot(None),
                AgentDemand.dispatch_deadline_at <= now,
                AgentDemand.dispatch_status.in_(("dispatched", "running")),
            )
        )
    ).scalars().all()
    for demand in stalled:
        await _fail_dispatch(
            db,
            demand,
            f"No response within {DISPATCH_TIMEOUT_MINUTES} minutes -- the run never reported back.",
            title=f"Dispatch timed out: {demand.subject}",
        )
        # Terminal now, so whoever asked has to hear about it -- a timeout is
        # precisely the case where someone is still waiting.
        await deliver_feedback(db, demand)
    if stalled:
        await db.commit()
        logger.info("Dispatch timeout: failed %d stalled dispatch(es)", len(stalled))
    return len(stalled)


async def run_incubation_maturation_pass(db: AsyncSession) -> int:
    """Hands the receive-or-drop decision to each owner whose thought has
    matured (2026-08-13). Returns how many were handed over.

    This is invariant 3 actually happening: without it `matures_at` is only
    a column, and an incubation still waits for its owner to remember to
    look -- which is the failure the whole redesign exists to remove (#8971
    sat parked four days; nothing noticed).

    **How the decision is delivered:** `agent_processed_at` is cleared, which
    puts the item back into `GET /demands/pending` -- the queue agents
    already pull from their own cron loop (42 messages had been taken that
    way before this). Deliberately *not* a new dispatch and *not* a new
    message: dispatching would spawn a whole agent run just to ask a
    question, and a new message would need its own owner and deadline,
    making a second item to forget. Reusing the pull queue means the
    decision reaches the agent through the path it already checks.

    Idempotent by state, not by timestamp: only "incubating" rows are picked
    up, and each becomes "decision_pending" in the same transaction, so a
    second pass (or an overlapping one) can't hand the same thought over
    twice. `matures_at` is left as the historical record of when it was due.
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(AgentDemand).where(
            AgentDemand.origin_type == "incubation",
            AgentDemand.incubation_state == "incubating",
            AgentDemand.matures_at.isnot(None),
            AgentDemand.matures_at <= now,
        )
    )
    matured = list(result.scalars().all())
    for demand in matured:
        demand.incubation_state = "decision_pending"
        # Back into the pull queue -- see this function's docstring.
        demand.agent_processed_at = None
        # Also surface it to the human, once per thought: event_key is
        # id-scoped so a re-run can never duplicate the row.
        db.add(
            Notification(
                source="system",
                severity="warning",
                title=f"Decision due: {demand.subject}",
                message=(
                    f"#{demand.number} has been incubating since "
                    f"{format_local(demand.created_at, '%Y-%m-%d')} and is waiting on its owner to "
                    f"receive or drop it."
                ),
                event_key=f"incubation-due:{demand.id}",
                occurred_at=now,
            )
        )
    if matured:
        await db.commit()
        logger.info("Incubation maturation: handed %d decision(s) to their owners", len(matured))
    return len(matured)


async def run_scheduled_dispatch_pass(db: AsyncSession) -> None:
    """Polled by main.py's _scheduled_dispatch_poll_loop -- finds every item
    whose scheduled_at has come due and hasn't been dispatched yet (this
    loop or a human, whichever gets there first, since dispatch_status
    moving off NULL is the guard against double-dispatch either way), and
    fires it through the same path a manual dispatch takes. scheduled_at
    itself is left set afterward as a historical record."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(AgentDemand).where(
            AgentDemand.scheduled_at.isnot(None),
            AgentDemand.scheduled_at <= now,
            AgentDemand.dispatch_status.is_(None),
            AgentDemand.target_agent_id.isnot(None),
            # Backlog with no registered sender stays parked -- see
            # _assert_dispatchable. Skipped, not failed: nothing was tried.
            or_(
                AgentDemand.origin_type.is_distinct_from("incubation"),
                AgentDemand.from_agent_id.isnot(None),
            ),
        )
        # Oldest first: with a concurrency cap, what is left out of this pass
        # waits for the next one, and a due message must not be overtaken by
        # a newer one just because the cap happened to cut there.
        .order_by(AgentDemand.scheduled_at)
    )
    due = list(result.scalars().all())
    slots = await _dispatch_slots(db)
    busy = await _agents_already_running(db)

    # Two independent limits, both applied while picking: the global cap
    # (what the machine can take) and one run per agent (so an agent's
    # sessions never overlap). An agent that is busy is *skipped*, not
    # stopped -- the queue keeps moving for everyone else, and the skipped
    # message is picked up by a later pass once its agent is free.
    selected: list[AgentDemand] = []
    deferred = 0
    for demand in due:
        if len(selected) >= slots:
            deferred += len(due) - len(selected) - deferred
            break
        if demand.target_agent_id in busy:
            deferred += 1
            continue
        selected.append(demand)
        busy.add(demand.target_agent_id)
    if deferred:
        logger.info(
            "Dispatch queue: %d due, %d starting, %d deferred (cap %d, one run per agent)",
            len(due), len(selected), deferred, slots,
        )
    for demand in selected:
        # Captured up front: db.rollback() expires every attribute on
        # objects in the session, so demand.id after a rollback needs a
        # fresh lazy-load -- which needs an awaited context this except
        # block doesn't have, and raises MissingGreenlet instead of
        # logging the actual dispatch failure.
        demand_id = demand.id
        try:
            await _execute_dispatch(db, demand, demand.target_agent_id, demand.command_text)
            await db.commit()
        except AgentRunDispatchError:
            # Not transient -- e.g. the target agent has no runtime_type
            # configured for CLI dispatch, so this can never succeed as-is.
            # Retrying it silently every 30s forever would both waste the
            # loop's time and, worse, leave the failure invisible to a
            # human (dispatch_status stays NULL, so the reading pane's
            # dispatch-status banner never renders) -- exactly the
            # "message received, nothing ever tells anyone it can't be
            # processed" gap this marks "failed" to close. A genuinely
            # dispatchable agent can still be retried by hand via the
            # reading pane's Dispatch button once fixed.
            await _fail_dispatch(
                db,
                demand,
                "Target agent can't run this automatically (no CLI runtime_type configured) "
                "-- needs manual handling.",
                title=f"Dispatch failed: {demand.subject}",
            )
            await db.commit()
            logger.exception("Scheduled dispatch permanently failed for demand %s", demand_id)
        except Exception:
            # Transient (e.g. the host-bridge unreachable) -- leave
            # dispatch_status NULL so the next poll retries it.
            await db.rollback()
            logger.exception("Scheduled dispatch failed for demand %s", demand_id)


@router.post("/{demand_id}/dispatch", response_model=DemandOut)
async def dispatch_demand(
    demand_id: uuid.UUID, payload: DispatchIn, db: AsyncSession = Depends(get_db)
) -> AgentDemand:
    """Sends this item's context (+ Marcelo's command_text, if any) as a
    prompt to a target agent's CLI via the host-bridge's governed runner.
    Never blocks: the dispatch always proceeds; a Telegram notice is sent
    only when the action is "independent" -- see
    PROPOSTA-INBOX-DISPATCH-E-DIALOGO-ENTRE-AGENTES.md §5 for the full
    governance model this implements."""
    demand = await _get_demand_or_404(db, demand_id)
    _assert_dispatchable(demand)

    if payload.reply_to_sender:
        if payload.target_agent_id is not None:
            raise HTTPException(400, "Send either target_agent_id or reply_to_sender, not both")
        if demand.from_agent_id is None:
            raise HTTPException(400, "This item has no registered agent sender to reply to")
        target_agent_id = demand.from_agent_id
    else:
        if payload.target_agent_id is None:
            raise HTTPException(400, "target_agent_id or reply_to_sender is required")
        target_agent_id = payload.target_agent_id

    try:
        demand = await _execute_dispatch(db, demand, target_agent_id, payload.command_text)
    except AgentRunDispatchError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Host-bridge dispatch failed: {exc}") from exc

    await db.commit()
    await db.refresh(demand)
    return demand


def _format_execution_header(demand: AgentDemand, agent_name: str) -> str:
    """Data/Agente/Ticket/Assunto/Status -- the canonical execution-report
    header (Foundation's governance/athos-orchestration-model.md, "When
    reporting or logging execution, use this header format"), applied to
    Messages' own dispatch_result (2026-07-28, Marcelo: "precisamos seguir
    o mesmo cabeça que era utilizado no kanboard... Analise se tem todos os
    atributos necessários"). Ticket is this message's own #number, never a
    Kanboard task id (Marcelo, same session: "remova o kanboard do
    forgehub") -- ForgeHub's own display number is the referable identifier
    now. Status uses AgentDemand's own dispatch_status vocabulary
    (completed/failed), not Kanboard's (executing/in_progress/completed/
    blocked) -- the two don't map 1:1 ("blocked" has no ForgeHub
    equivalent, "failed" has no Kanboard one), and this header is only ever
    written on a terminal transition, so only completed/failed ever appear
    here anyway."""
    return (
        # Wall-clock in settings.TIMEZONE, not UTC: this line is read by a
        # person, and a header three hours ahead of their own clock can't be
        # matched against anything else on the machine (2026-08-13).
        f"Data: {format_local(demand.task_execution_at)}\n"
        f"Agente: {agent_name}\n"
        f"Ticket: #{demand.number}\n"
        f"Assunto: {demand.subject}\n"
        f"Status: {demand.dispatch_status}\n"
        "---\n"
    )


async def _finalize_dispatch(db: AsyncSession, demand_id: uuid.UUID, run: dict[str, Any]) -> AgentDemand | None:
    """The terminal transition of a dispatch, shared by the frontend's
    GET .../dispatch-status and the background completion pass: flips
    dispatch_status, stamps the execution time, and records the agent's
    output as `dispatch_result` on this SAME message -- "processamento",
    not a new message (2026-07-28, Marcelo: "não temos resposta
    automática. somente processamento" + "gravado na própria mensagem").
    Only when the original explicitly asked for one
    (`requires_response=true`) does a real return message also get created
    (+ its bell notification) -- see reply_to_id's docstring. Caller
    commits.

    Returns None when either someone else already finalized this dispatch,
    or this dispatch simply didn't request a return message. The row is
    re-read FOR UPDATE and re-checked here rather than trusting the
    caller's earlier read, because there are genuinely concurrent
    finalizers: a reading pane polling, run_dispatch_completion_pass, and
    -- since ./dev.sh and the Docker deploy share one database -- a second
    app instance running its own copy of that pass. Without the lock each
    of them would create its own duplicate return message for the same run."""
    locked = (
        await db.execute(select(AgentDemand).where(AgentDemand.id == demand_id).with_for_update())
    ).scalar_one_or_none()
    if locked is None or locked.dispatch_status in ("completed", "failed"):
        return None

    run_status = run.get("status")
    # Terminal: completed / failed / timed_out / cancelled / stale.
    locked.dispatch_status = "completed" if run_status == "completed" else "failed"
    # Reached a terminal state, so the deadline no longer applies -- leaving
    # it set would let the timeout sweep re-fail an already-finished run.
    locked.dispatch_deadline_at = None
    if locked.dispatch_status == "failed":
        locked.dispatch_error = f"The agent run ended as {run_status!r}."
        db.add(
            Notification(
                source="system",
                severity="error",
                title=f"Dispatch failed: {locked.subject}",
                message=f"#{locked.number}: the agent run ended as {run_status!r}.",
                event_key=f"demand-dispatch-failed:{locked.id}:{locked.dispatch_attempts}",
                occurred_at=datetime.now(timezone.utc),
            )
        )
    # "Execução" -- when the recipient agent actually finished running this
    # message, stamped on either terminal outcome (a failed run still ran).
    # Deliberately NOT stamped by run_scheduled_dispatch_pass's
    # AgentRunDispatchError path: that marks dispatch_status="failed"
    # without ever starting a run, so there's no execution to date.
    # See AgentDemand.task_execution_at's docstring for how this coexists
    # with task.py's own stamping of the same column.
    locked.task_execution_at = datetime.now(timezone.utc)

    agent = await db.get(Agent, locked.target_agent_id) if locked.target_agent_id else None
    reply_body = _extract_run_result_text(run)
    # Always recorded, regardless of requires_response -- see
    # AgentDemand.dispatch_result's docstring. Prefixed with the canonical
    # execution-report header (Foundation's governance/athos-orchestration-
    # model.md, "When reporting or logging execution, use this header
    # format") so a dispatch's result reads the same way Kanboard-tracked
    # execution reports already do. Ticket references this message's own
    # #number, never Kanboard (2026-07-28, Marcelo: "remova o kanboard do
    # forgehub").
    locked.dispatch_result = _format_execution_header(locked, agent.name if agent else "agent") + reply_body

    # Channel narration (see db/models/channel.py's module docstring): a
    # ChatChannel message can trigger a real dispatch via this exact
    # pipeline (POST /channels/{id}/messages/{message_id}:dispatch-task,
    # api/routes/channel.py) without ever becoming a second source of
    # execution truth -- it only points at this AgentDemand via
    # triggered_demand_id. When one exists for this demand, post the
    # result back into that channel's transcript as a "system" message.
    # Cross-domain read only (no write coupling back into demand.py's own
    # state), same spirit as foundation.py's audit_checks lookup.
    from app.db.models.channel import ChatChannelMessage
    triggering_message = (
        await db.execute(
            select(ChatChannelMessage).where(ChatChannelMessage.triggered_demand_id == locked.id)
        )
    ).scalar_one_or_none()
    if triggering_message is not None:
        db.add(ChatChannelMessage(
            channel_id=triggering_message.channel_id,
            author_type="system",
            content=(
                f"Execução de #{locked.number} concluída ({locked.dispatch_status}) "
                f"por {agent.name if agent else 'agent'}:\n\n{reply_body}"
            ),
            triggered_demand_id=locked.id,
        ))

    if not locked.requires_response or locked.from_agent_id is None:
        return None

    reply = AgentDemand(
        from_agent=agent.name if agent else "agent",
        from_agent_id=locked.target_agent_id,
        subject=f"Re: {locked.subject}",
        body=locked.dispatch_result,
        # "demand" no longer exists as a Tipo value (2026-07-28, Marcelo:
        # "Tipo=task") -- the return message is itself trackable work
        # (already done: dispatch_status is set completed below, never
        # picked up by the scheduled-send loop since scheduled_at stays
        # NULL), not Backlog.
        origin_type="task",
        reply_to_id=locked.id,
        # Doesn't itself request a further response -- avoids a reply loop.
        requires_response=False,
        target_agent_id=locked.from_agent_id,
        # Already done -- set directly rather than left NULL/pending, both
        # so it never gets picked up by run_scheduled_dispatch_pass (which
        # only fires on target_agent_id set + scheduled_at reached; this
        # row's scheduled_at stays NULL, but dispatch_status=NULL would
        # also read as eligible once something else set it) and so it
        # immediately shows as *arrived* in the requester's Incoming (the
        # "letter model" gate needs dispatch_status non-NULL, see
        # pages/demands/index.tsx's isIncomingItem).
        dispatch_status="completed",
        task_execution_at=locked.task_execution_at,
    )
    db.add(reply)
    await db.flush()

    db.add(Notification(
        source="system",
        severity="info",
        title=f"Reply in Inbox: {reply.subject}",
        message=_demand_preview(reply_body),
        event_key=f"demand-reply:{locked.id}",
        occurred_at=datetime.now(timezone.utc),
    ))
    return reply


async def run_dispatch_completion_pass(db: AsyncSession) -> None:
    """Polled by main.py's _dispatch_completion_poll_loop -- finishes every
    dispatch that's still in flight, without anyone having to open it.

    Before this pass existed (2026-07-25), the *only* caller of the terminal
    transition was the reading pane's own useDispatchStatus query. A message
    dispatched to an agent that nobody happened to have selected on screen
    stayed `dispatch_status="dispatched"` forever: the run finished, produced
    a real answer, and the reply item was never created -- so an
    agent-to-agent exchange silently depended on a human watching it. That
    defeats the point of the auto-dispatch loop next door
    (run_scheduled_dispatch_pass), which fires messages with no human in the
    loop at all.

    Failure handling mirrors that sibling pass: a run the host-bridge no
    longer knows about (404 -- it restarted, or the run aged out of its
    table) can never be polled again, so it's marked failed once with a bell
    notification instead of being retried every 30s forever. Any other
    host-bridge error is treated as transient and simply retried next pass.
    """
    result = await db.execute(
        select(AgentDemand).where(
            AgentDemand.dispatch_status.in_(("dispatched", "running")),
            AgentDemand.agent_run_id.isnot(None),
        )
    )
    for demand in result.scalars().all():
        # Captured up front for the same reason run_scheduled_dispatch_pass
        # does it: after a rollback, reading demand.id needs a lazy-load
        # that raises MissingGreenlet instead of logging the real failure.
        demand_id = demand.id
        run_id = demand.agent_run_id
        subject = demand.subject
        try:
            run = await poll_agent_run(run_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                logger.warning("Dispatch completion poll failed for demand %s: %s", demand_id, exc)
                continue
            demand.dispatch_status = "failed"
            db.add(Notification(
                source="system",
                severity="warning",
                title=f"Dispatch lost: {subject}",
                message="The host-bridge no longer knows this run (restarted?) -- its result can't be recovered. Re-dispatch by hand if it still matters.",
                event_key=f"demand-dispatch-lost:{demand_id}",
                occurred_at=datetime.now(timezone.utc),
            ))
            await db.commit()
            continue
        except httpx.HTTPError as exc:
            # Transient (bridge down/unreachable) -- leave it in flight and
            # try again on the next pass.
            logger.warning("Dispatch completion poll failed for demand %s: %s", demand_id, exc)
            continue

        try:
            if run.get("status") in ("starting", "running"):
                if demand.dispatch_status != "running":
                    demand.dispatch_status = "running"
                    await db.commit()
                continue
            await _finalize_dispatch(db, demand_id, run)
            # Terminal now: send the outcome back to the channel that asked
            # (2026-08-13). In the same transaction as the state change, so a
            # crash between the two can't leave it delivered-but-unrecorded
            # or recorded-but-undelivered; the feedback sweep picks up
            # whatever this misses.
            refreshed = await db.get(AgentDemand, demand_id)
            if refreshed is not None:
                await deliver_feedback(db, refreshed)
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Dispatch completion failed for demand %s", demand_id)


@router.get("/{demand_id}/dispatch-status", response_model=DispatchStatusOut)
async def get_dispatch_status(
    demand_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> DispatchStatusOut:
    """Polled by the frontend while a dispatch is dispatched/running. No
    longer the only thing that finishes a dispatch -- the background
    completion pass (run_dispatch_completion_pass) does the same work on a
    timer, so this route now mostly reports a transition that already
    happened. Idempotent either way: _finalize_dispatch locks the row and
    re-checks, so the reply item is created exactly once no matter how many
    pollers race."""
    demand = await _get_demand_or_404(db, demand_id)
    if demand.agent_run_id is None:
        raise HTTPException(status_code=400, detail="This item has not been dispatched")

    if demand.dispatch_status in ("completed", "failed"):
        return DispatchStatusOut(dispatch_status=demand.dispatch_status, agent_run_id=demand.agent_run_id)

    try:
        run = await poll_agent_run(demand.agent_run_id)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Host-bridge poll failed: {exc}") from exc

    if run.get("status") in ("starting", "running"):
        demand.dispatch_status = "running"
        await db.commit()
        return DispatchStatusOut(dispatch_status=demand.dispatch_status, agent_run_id=demand.agent_run_id)

    reply = await _finalize_dispatch(db, demand_id, run)
    await db.commit()
    await db.refresh(demand)
    if reply is not None:
        await db.refresh(reply)
    return DispatchStatusOut(
        dispatch_status=demand.dispatch_status,
        agent_run_id=demand.agent_run_id,
        reply_demand_id=reply.id if reply is not None else None,
    )


@router.post("/{demand_id}/convert", response_model=ConvertOut)
async def convert_demand(
    demand_id: uuid.UUID, payload: ConvertIn, db: AsyncSession = Depends(get_db)
) -> ConvertOut:
    demand = await _get_demand_or_404(db, demand_id)
    title = payload.title or demand.subject

    try:
        if payload.target == "task":
            if payload.planning_item_id is None:
                raise HTTPException(400, "planning_item_id is required for target=task")
            entity_id, reference = await conversions.convert_to_task(
                db, title=title, content=demand.body, planning_item_id=payload.planning_item_id
            )
        elif payload.target == "doc":
            if not payload.path:
                raise HTTPException(400, "path is required for target=doc")
            doc_root = (
                await conversions.resolve_area_root(db, payload.area_id)
                if payload.area_id is not None
                else conversions.DOCS_ROOT
            )
            reference = await conversions.convert_to_doc(path=payload.path, content=demand.body, root=doc_root)
            entity_id = None
            if demand.attachments:
                # Attached files land next to the note itself, not just the
                # markdown body -- see copy_attachments_to_folder's docstring.
                await conversions.copy_attachments_to_folder(
                    attachments=[(a.filename, _resolve_attachment_file(a)) for a in demand.attachments],
                    dest_path=payload.path,
                    dest_root=doc_root,
                )
        elif payload.target == "artifact":
            if not payload.artifact_type:
                raise HTTPException(400, "artifact_type is required for target=artifact")
            doc_path = payload.path or f"anotacoes/demandas/{demand.id}.md"
            entity_id, reference = await conversions.convert_to_artifact(
                db,
                name=title,
                content=demand.body,
                artifact_type=payload.artifact_type,
                doc_path=doc_path,
            )
        elif payload.target == "knowledge_base":
            if not payload.path:
                raise HTTPException(400, "path is required for target=knowledge_base")
            reference = await conversions.convert_to_knowledge_base(
                path=payload.path, content=demand.body
            )
            entity_id = None
        elif payload.target == "planning_item":
            if payload.project_id is None:
                raise HTTPException(400, "project_id is required for target=planning_item")
            item_type = payload.item_type or conversions.DEFAULT_ITEM_TYPE
            if item_type not in PLANNING_ITEM_TYPES:
                raise HTTPException(400, f"item_type must be one of {PLANNING_ITEM_TYPES}")
            entity_id, reference = await conversions.convert_to_planning_item(
                db, title=title, content=demand.body, project_id=payload.project_id, item_type=item_type
            )
        elif payload.target == "project_doc":
            if payload.project_id is None:
                raise HTTPException(400, "project_id is required for target=project_doc")
            doc_path = payload.path or f"projetos/{payload.project_id}/{demand.id}.md"
            reference = await conversions.convert_to_project_doc(
                db, project_id=payload.project_id, path=doc_path, content=demand.body
            )
            entity_id = None
        else:  # quick_task
            if payload.project_id is None:
                raise HTTPException(400, "project_id is required for target=quick_task")
            item_type = payload.item_type or conversions.DEFAULT_ITEM_TYPE
            if item_type not in PLANNING_ITEM_TYPES:
                raise HTTPException(400, f"item_type must be one of {PLANNING_ITEM_TYPES}")
            entity_id, reference = await conversions.convert_to_quick_task(
                db, title=title, content=demand.body, project_id=payload.project_id, item_type=item_type
            )
    except conversions.ConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    demand.status = "converted"
    demand.converted_entity_type = payload.target
    demand.converted_reference = reference
    await db.commit()

    return ConvertOut(
        entity_type=payload.target,
        entity_id=str(entity_id) if entity_id else None,
        reference=reference,
    )
