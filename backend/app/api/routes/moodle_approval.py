"""Staging-only Moodle approval protocol. Disabled unless explicitly configured."""
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.moodle_approval import (
    ApprovalItem, AuthorizeIn, ClaimIn, FinishIn, RegisterIn, RejectIn, StatusIn, TelegramDecisionIn,
)
from app.core.config import settings
from app.core.deps import ActorPrincipal, get_actor_principal, get_current_user
from app.core.demand_workflow import approval_fingerprint, record_transition
from app.core.dispatch_signal import wake_scheduled_dispatch
from app.core.instructor_group import GROUP_CHANNEL, REJECTED_REPLY, result_note, send_to_group
from app.core.moodle_proposal_verification import STUDENT_BATCH_FUNCTION, ProposalInvalid, operation_view, student_batch_view, validate_proposal
from app.db.base import get_db
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.moodle_approval import MoodleApproval
from app.db.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/personal/moodle-approvals", tags=["moodle-approval"])


def _config():
    if not settings.MOODLE_APPROVAL_ENABLED:
        raise HTTPException(503, "Moodle approval is not enabled")
    try:
        owner = uuid.UUID(settings.MOODLE_APPROVAL_OWNER_ID)
        sources = json.loads(settings.MOODLE_APPROVAL_SOURCE_FILES)
        if not isinstance(sources, dict) or not sources:
            raise ValueError
        sources = {uuid.UUID(key): Path(value) for key, value in sources.items()}
        if any(not path.is_absolute() for path in sources.values()) or not Path(settings.MOODLE_APPROVAL_WORKING_PATH).is_absolute():
            raise ValueError
    except (ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(503, "Moodle approval configuration is incomplete") from None
    return owner, sources


def _owner(user: User):
    owner, _ = _config()
    if user.id != owner or not user.is_active or not user.is_admin:
        raise HTTPException(403, "Only the configured owner may authorize")


def _source(agent_id: uuid.UUID, request_id: uuid.UUID):
    _, sources = _config()
    path = sources.get(agent_id)
    if path is None:
        raise HTTPException(403, "Proposal source is not authorized")
    try:
        # Configuration supplies the store path, never the caller. A bounded
        # read also prevents an agent-controlled file exhausting the API.
        with path.open("rb") as source:
            content = source.read(10_000_001)
        if len(content) > 10_000_000:
            raise ValueError
        store = json.loads(content)
        proposal = store["proposals"][str(request_id)]
        return validate_proposal(proposal, str(request_id))
    except (OSError, ValueError, KeyError, TypeError, ProposalInvalid):
        raise HTTPException(409, "Proposal unavailable or invalid") from None


def _agent(principal: ActorPrincipal):
    if principal.principal_type != "agent":
        raise HTTPException(403, "Individual agent credential required")
    return principal.principal_id


@router.post("/register", status_code=201)
async def register(payload: RegisterIn, principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db)):
    _config()
    source_id = _agent(principal)
    source = await db.get(Agent, source_id)
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(str(payload.request_id), 0))))
    existing = await db.scalar(select(MoodleApproval).where(MoodleApproval.request_id == payload.request_id))
    if existing:
        if existing.source_agent_id != source_id:
            raise HTTPException(409, "Proposal already registered")
        message = await db.get(AgentDemand, existing.message_id)
        return {"request_id": str(existing.request_id), "message_id": str(message.id), "number": message.number}
    proposal = _source(source_id, payload.request_id)
    # A group capture in flight owns what is registered now: forgetting the number must not
    # leave a proposal that would run with every tool. Fails closed for a parallel Telegram turn.
    origin = await db.scalar(select(AgentDemand).where(
        AgentDemand.channel == GROUP_CHANNEL, AgentDemand.requires_approval.is_(False), AgentDemand.target_agent_id == source_id,
        AgentDemand.dispatch_status.in_(("dispatched", "running"))))
    if payload.origin_number is not None and (origin is None or origin.number != payload.origin_number):
        raise HTTPException(409, "origin_number is not the capture in flight")
    if origin is not None:
        if payload.origin_number is None:
            raise HTTPException(409, "A group capture is running: origin_number is required")
        created = datetime.fromisoformat(proposal["created_at"].replace("Z", "+00:00"))
        if origin.dispatched_at is None or created < origin.dispatched_at:
            raise HTTPException(409, "This proposal is older than the capture")
    demand = AgentDemand(from_agent=source.profile_slug or source.name, from_agent_id=source_id,
        target_agent_id=source_id, subject="Moodle: solicitação de aprovação", body="Proposta Moodle aguardando confirmação.",
        origin_type="task", status="new", requires_approval=True, approval_status="pending", scheduled_at=None,
        channel=origin.channel if origin else None, channel_ref=origin.channel_ref if origin else None,
        channel_message_id=origin.channel_message_id if origin else None,
        working_path=settings.MOODLE_APPROVAL_WORKING_PATH, requires_response=False)
    db.add(demand)
    await db.flush()
    link = MoodleApproval(message_id=demand.id, request_id=payload.request_id, source_agent_id=source_id,
        params_hash=proposal["params_hash"], expires_at=datetime.fromisoformat(proposal["expires_at"].replace("Z", "+00:00")), state="pending")
    db.add(link)
    record_transition(db, demand, "moodle_registered", actor=str(source_id), extra={"request_id": str(payload.request_id)})
    await db.commit()
    await db.refresh(demand)
    return {"request_id": str(payload.request_id), "message_id": str(demand.id), "number": demand.number}


@router.get("")
async def list_approvals(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _owner(user)
    rows = (await db.execute(select(MoodleApproval, AgentDemand).join(AgentDemand, MoodleApproval.message_id == AgentDemand.id)
        .where(MoodleApproval.state == "pending").order_by(MoodleApproval.created_at))).all()
    items = []
    unavailable_count = 0
    for link, demand in rows:
        try:
            proposal = _source(link.source_agent_id, link.request_id)
            if proposal["params_hash"] != link.params_hash:
                unavailable_count += 1
                continue
        except HTTPException:
            unavailable_count += 1
            continue
        batch = student_batch_view(proposal["params"]) if proposal["wsfunction"] == STUDENT_BATCH_FUNCTION else None
        items.append({"request_id": str(link.request_id), "message_id": str(demand.id), "number": demand.number,
            "summary": proposal.get("summary", ""), "operation": proposal["wsfunction"],
            "environment": proposal["environment"], "host": proposal["host"], "destructive": proposal["destructive"],
            "params": {} if batch else proposal["params"], "batch": batch, "operation_view": operation_view(proposal),
            "params_hash": link.params_hash, "message_updated_at": demand.updated_at, "expires_at": link.expires_at})
    recent = (await db.execute(select(MoodleApproval, AgentDemand).join(AgentDemand, MoodleApproval.message_id == AgentDemand.id)
        .where(MoodleApproval.state != "pending").order_by(MoodleApproval.updated_at.desc()).limit(20))).all()
    activity = [{"number": demand.number, "message_id": str(demand.id), "request_id": str(link.request_id),
        "state": link.state, "outcome": link.outcome, "approved_at": link.approved_at,
        "finished_at": link.finished_at, "dispatch_status": demand.dispatch_status, "archived": demand.status == "archived"}
        for link, demand in recent]
    return {"items": items, "unavailable_count": unavailable_count, "activity": activity}


@router.post("/authorize")
async def authorize(payload: AuthorizeIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _owner(user)
    now = datetime.now(timezone.utc)
    executor = await db.get(Agent, payload.executor_agent_id)
    if not executor or not executor.is_active or executor.status != "active":
        raise HTTPException(409, "Executor unavailable")
    rows = (await db.execute(select(MoodleApproval, AgentDemand).join(AgentDemand, MoodleApproval.message_id == AgentDemand.id)
        .where(MoodleApproval.message_id.in_([x.message_id for x in payload.items])).order_by(MoodleApproval.message_id)
        .with_for_update(of=(MoodleApproval, AgentDemand)).execution_options(populate_existing=True))).all()
    if len(rows) != len(payload.items):
        raise HTTPException(409, "Batch changed; review again")
    items = {x.message_id: x for x in payload.items}
    for link, demand in rows:
        item = items[demand.id]
        proposal = _source(link.source_agent_id, link.request_id)
        if (link.state != "pending" or link.expires_at <= now or link.request_id != item.request_id or
            link.params_hash != item.params_hash or proposal["params_hash"] != link.params_hash or
            demand.updated_at != item.message_updated_at or demand.dispatch_status is not None or demand.agent_run_id is not None):
            raise HTTPException(409, "Batch changed; review again")
    for link, demand in rows:
        demand.target_agent_id = executor.id
        demand.body = (f"Chame moodle_execute_approved com request_id={link.request_id}, message_id={demand.id} "
                       f"e params_hash={link.params_hash}. Não altere os parâmetros nem repita a chamada.\n\n"
                       f"{payload.instruction}")
        if demand.channel == GROUP_CHANNEL:
            demand.body += f"\n\n{result_note(demand.channel_ref)}"
        demand.command_text = None
        demand.requires_approval = True
        demand.approval_status = "approved"
        demand.approved_content_hash = approval_fingerprint(demand)
        demand.scheduled_at = now
        link.state = "approved"
        link.approved_by = user.id
        link.approved_at = now
        link.executor_id = executor.id
        link.message_hash = demand.approved_content_hash
        record_transition(db, demand, "moodle_authorized", actor=str(user.id), extra={"request_id": str(link.request_id)})
    await db.commit()
    wake_scheduled_dispatch()
    return {"approved": [d.number for _, d in rows]}


@router.post("/reject")
async def reject(payload: RejectIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Nothing runs, so this works even for a proposal whose source file is gone or expired."""
    _owner(user)
    rows = (await db.execute(select(MoodleApproval, AgentDemand).join(AgentDemand, MoodleApproval.message_id == AgentDemand.id)
        .where(MoodleApproval.message_id.in_([x.message_id for x in payload.items])).order_by(MoodleApproval.message_id)
        .with_for_update(of=(MoodleApproval, AgentDemand)).execution_options(populate_existing=True))).all()
    if len(rows) != len(payload.items):
        raise HTTPException(409, "Batch changed; review again")
    items = {x.message_id: x for x in payload.items}
    for link, demand in rows:
        item = items[demand.id]
        if (link.state != "pending" or link.request_id != item.request_id or demand.updated_at != item.message_updated_at
                or demand.dispatch_status is not None or demand.agent_run_id is not None):
            raise HTTPException(409, "Batch changed; review again")
    for link, demand in rows:
        link.state = "rejected"
        demand.approval_status = "rejected"
        demand.status = "archived"
        demand.scheduled_at = None
        demand.decision_reason = payload.reason
        record_transition(db, demand, "moodle_rejected", actor=str(user.id),
                          extra={"request_id": str(link.request_id), "reason": payload.reason})
    await db.commit()
    for _, demand in rows:
        if demand.channel == GROUP_CHANNEL:
            try:
                await send_to_group(demand.channel_ref, REJECTED_REPLY, reply_to=demand.channel_message_id)
            except httpx.HTTPError:
                logger.warning("Could not tell the group about rejected #%s", demand.number)
    return {"rejected": [d.number for _, d in rows]}


@router.post("/telegram-decision")
async def telegram_decision(payload: TelegramDecisionIn, x_decision_secret: str | None = Header(default=None),
                            db: AsyncSession = Depends(get_db)):
    """A tap on the Maia's Telegram buttons. The plugin vouches for the tap with a secret the agent
    cannot read, and authorize/reject below stay the only code that decides."""
    secret = settings.MOODLE_TELEGRAM_DECISION_SECRET
    if not secret or not x_decision_secret or not hmac.compare_digest(secret.encode(), x_decision_secret.encode()):
        raise HTTPException(401, "Not authenticated")
    owner, _ = _config()
    chat = settings.MOODLE_APPROVAL_TELEGRAM_CHAT_ID
    if not chat or str(payload.telegram_user_id) != chat:
        raise HTTPException(403, "Only the configured owner may authorize")
    user = await db.get(User, owner)
    if user is None:
        raise HTTPException(403, "Only the configured owner may authorize")
    _owner(user)
    # Locked and read fresh: a decision on the screen at the same moment waits or is seen here.
    row = (await db.execute(select(MoodleApproval, AgentDemand).join(AgentDemand, MoodleApproval.message_id == AgentDemand.id)
        .where(MoodleApproval.message_id == payload.message_id)
        .with_for_update(of=(MoodleApproval, AgentDemand)).execution_options(populate_existing=True))).one_or_none()
    if not row:
        raise HTTPException(404, "Request not found")
    link, demand = row
    number = demand.number
    if link.state != "pending":
        return {"result": "already_decided", "state": link.state, "number": number}
    if payload.action == "approve" and link.expires_at <= datetime.now(timezone.utc):
        return {"result": "expired", "number": number}
    if payload.action == "approve":
        # He asked on Telegram, so the result goes back there. Part of what the approval freezes.
        if demand.channel != GROUP_CHANNEL:
            demand.channel, demand.channel_ref = "telegram", chat
        await db.flush()
        await db.refresh(demand)
    item = ApprovalItem(request_id=link.request_id, message_id=demand.id, params_hash=link.params_hash,
                        message_updated_at=demand.updated_at)
    try:
        if payload.action == "approve":
            await authorize(AuthorizeIn(executor_agent_id=link.source_agent_id, instruction="Retorno pelo Telegram.", items=[item]), user, db)
        else:
            await reject(RejectIn(reason="Recusada pelo Telegram", items=[item]), user, db)
    except HTTPException:
        await db.rollback()  # A refused approval leaves no channel behind.
        raise
    record_transition(db, demand, "moodle_telegram_decision", actor=str(user.id),
                      extra={"request_id": str(link.request_id), "action": payload.action})
    await db.commit()
    return {"result": "approved" if payload.action == "approve" else "rejected", "number": number}


@router.post("/status")
async def claim_status(payload: StatusIn, principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db)):
    """Tells the MCP whether this was already done. Reads only: /claim stays the one step that prevents a second run."""
    _config()
    agent_id = _agent(principal)
    link = await db.scalar(select(MoodleApproval).where(MoodleApproval.message_id == payload.message_id,
        MoodleApproval.request_id == payload.request_id))
    if not link:
        raise HTTPException(409, "Authorization unavailable")
    if agent_id not in (link.executor_id, link.source_agent_id):
        raise HTTPException(403, "Executor does not match")
    return {"state": link.state, "outcome": link.outcome, "params_hash": link.params_hash,
            "expired": link.expires_at <= datetime.now(timezone.utc)}


@router.post("/claim")
async def claim(payload: ClaimIn, principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db)):
    _config()
    agent_id = _agent(principal)
    row = (await db.execute(select(MoodleApproval, AgentDemand).join(AgentDemand, MoodleApproval.message_id == AgentDemand.id)
        .where(MoodleApproval.message_id == payload.message_id, MoodleApproval.request_id == payload.request_id)
        .with_for_update(of=(MoodleApproval, AgentDemand)))).one_or_none()
    if not row:
        raise HTTPException(409, "Authorization unavailable")
    link, demand = row
    if link.executor_id != agent_id:
        raise HTTPException(403, "Executor does not match")
    proposal = _source(link.source_agent_id, link.request_id)
    if (link.state != "approved" or link.expires_at <= datetime.now(timezone.utc) or not demand.agent_run_id or
        demand.target_agent_id != agent_id or demand.approval_status != "approved" or
        not demand.requires_approval or demand.status == "archived" or demand.consolidated_into_id is not None or
        demand.dispatch_status not in (None, "dispatched", "running") or
        link.params_hash != payload.params_hash or proposal["params_hash"] != link.params_hash or
        demand.approved_content_hash != link.message_hash or approval_fingerprint(demand) != link.message_hash):
        raise HTTPException(409, "Authorization invalid, expired or consumed")
    link.state = "claimed"
    link.claimed_at = datetime.now(timezone.utc)
    record_transition(db, demand, "moodle_claimed", actor=str(agent_id), extra={"request_id": str(link.request_id)})
    await db.commit()
    return {key: proposal[key] for key in ("wsfunction", "params", "environment", "host")}


@router.post("/finish")
async def finish(payload: FinishIn, principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db)):
    _config()
    agent_id = _agent(principal)
    link = await db.scalar(select(MoodleApproval).where(MoodleApproval.message_id == payload.message_id,
        MoodleApproval.request_id == payload.request_id).with_for_update())
    if not link or link.executor_id != agent_id:
        raise HTTPException(403, "Executor does not match")
    if link.state != "claimed":
        raise HTTPException(409, "Claim not active")
    demand = await db.get(AgentDemand, link.message_id)
    link.state = "finished"
    link.finished_at = datetime.now(timezone.utc)
    link.outcome = payload.outcome
    record_transition(db, demand, "moodle_finished", actor=str(agent_id), extra={"request_id": str(link.request_id), "outcome": payload.outcome})
    await db.commit()
    return {"recorded": True}
