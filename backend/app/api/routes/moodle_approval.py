"""Staging-only Moodle approval protocol. Disabled unless explicitly configured."""
import hashlib
import json
import secrets
import uuid
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.moodle_approval import AuthorizeIn, ClaimIn, FinishIn, RegisterIn
from app.core.config import settings
from app.core.deps import ActorPrincipal, get_actor_principal, get_current_user
from app.core.demand_workflow import approval_fingerprint, record_transition
from app.core.dispatch_signal import wake_scheduled_dispatch
from app.core.moodle_proposal_verification import ProposalInvalid, validate_proposal
from app.core.security import verify_password
from app.db.base import get_db
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.moodle_approval import MoodleApproval, MoodleChallenge
from app.db.models.governance import AuditEvent
from app.db.models.user import User

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


def _send_telegram(message: str):
    # The fixed Maia profile sends to the configured owner private chat.
    # The bot credential stays with the gateway and the challenge never enters argv.
    chat_id = settings.MOODLE_APPROVAL_TELEGRAM_CHAT_ID
    if not chat_id.isascii() or not chat_id.isdigit() or int(chat_id) <= 0:
        raise ValueError("Telegram destination is not a private user chat")
    request = Request(f"{settings.CHAT_BRIDGE_URL.rstrip('/')}/v1/messages/send", method="POST",
        data=json.dumps({"profile": "maia", "target": f"telegram:{chat_id}", "message": message}).encode(),
        headers={"Content-Type": "application/json", "X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN})
    with urlopen(request, timeout=70) as response:
        result = json.load(response)
        if response.status != 200 or not isinstance(result, dict) or result.get("success") is not True or result.get("skipped"):
            raise ValueError("Telegram delivery failed")


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
    demand = AgentDemand(from_agent=source.profile_slug or source.name, from_agent_id=source_id,
        target_agent_id=source_id, subject="Moodle: solicitação de aprovação", body="Proposta Moodle aguardando confirmação.",
        origin_type="task", status="new", requires_approval=True, approval_status="pending", scheduled_at=None,
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
    for link, demand in rows:
        try:
            proposal = _source(link.source_agent_id, link.request_id)
            if proposal["params_hash"] != link.params_hash:
                continue
        except HTTPException:
            continue
        items.append({"request_id": str(link.request_id), "message_id": str(demand.id), "number": demand.number,
            "summary": proposal.get("summary", ""), "operation": proposal["wsfunction"],
            "environment": proposal["environment"], "host": proposal["host"], "destructive": proposal["destructive"],
            "params": proposal["params"],
            "params_hash": link.params_hash, "message_updated_at": demand.updated_at, "expires_at": link.expires_at})
    return {"items": items}


@router.post("/telegram-challenge")
async def telegram_challenge(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _owner(user)
    url = settings.MOODLE_APPROVAL_FORM_URL
    if urlsplit(url).scheme != "https" or not urlsplit(url).netloc or urlsplit(url).fragment:
        raise HTTPException(503, "Telegram approval link is not configured")
    chat_id = settings.MOODLE_APPROVAL_TELEGRAM_CHAT_ID
    if (not settings.CHAT_BRIDGE_URL or not settings.CHAT_BRIDGE_TOKEN or not chat_id.isascii()
            or not chat_id.isdigit() or int(chat_id) <= 0):
        raise HTTPException(503, "Telegram destination is not configured")
    # Lock the owner to serialize creation and prevent unlimited challenge refresh.
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    recent = await db.scalar(select(func.count()).select_from(MoodleChallenge).where(
        MoodleChallenge.owner_id == user.id, MoodleChallenge.created_at >= datetime.now(timezone.utc) - timedelta(hours=1)))
    if recent >= 3:
        raise HTTPException(429, "Too many approval links")
    secret = secrets.token_urlsafe(32)
    challenge = MoodleChallenge(owner_id=user.id, secret_hash=hashlib.sha256(secret.encode()).hexdigest(),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5), attempts=0)
    db.add(challenge)
    await db.flush()
    db.add(AuditEvent(entity_type="moodle_challenge", entity_id=challenge.id,
        event_type="moodle_challenge_requested", actor=str(user.id), payload={}))
    await db.commit()
    try:
        await asyncio.to_thread(_send_telegram,
            f"Abra o ForgeHub para revisar as propostas Moodle: {url}#telegram_challenge={secret}")
    except Exception:
        challenge.consumed_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(502, "Telegram delivery failed") from None
    return {"sent": True}


@router.post("/authorize")
async def authorize(payload: AuthorizeIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _owner(user)
    now = datetime.now(timezone.utc)
    digest = hashlib.sha256(payload.telegram_challenge.encode()).hexdigest()
    challenge = await db.scalar(select(MoodleChallenge).where(MoodleChallenge.secret_hash == digest).with_for_update())
    if not challenge or challenge.owner_id != user.id or challenge.consumed_at or challenge.expires_at <= now or challenge.attempts >= 5:
        raise HTTPException(403, "Invalid or expired approval link")
    challenge.attempts += 1
    if not verify_password(payload.password, user.hashed_password):
        db.add(AuditEvent(entity_type="moodle_challenge", entity_id=challenge.id,
            event_type="moodle_confirmation_failed", actor=str(user.id), payload={"attempt": challenge.attempts}))
        await db.commit()
        raise HTTPException(403, "Invalid confirmation")
    executor = await db.get(Agent, payload.executor_agent_id)
    if not executor or not executor.is_active or executor.status != "active":
        await db.commit()
        raise HTTPException(409, "Executor unavailable")
    rows = (await db.execute(select(MoodleApproval, AgentDemand).join(AgentDemand, MoodleApproval.message_id == AgentDemand.id)
        .where(MoodleApproval.message_id.in_([x.message_id for x in payload.items])).order_by(MoodleApproval.message_id)
        .with_for_update(of=(MoodleApproval, AgentDemand)))).all()
    if len(rows) != len(payload.items):
        await db.commit()
        raise HTTPException(409, "Batch changed; review again")
    items = {x.message_id: x for x in payload.items}
    for link, demand in rows:
        item = items[demand.id]
        proposal = _source(link.source_agent_id, link.request_id)
        if (link.state != "pending" or link.expires_at <= now or link.request_id != item.request_id or
            link.params_hash != item.params_hash or proposal["params_hash"] != link.params_hash or
            demand.updated_at != item.message_updated_at or demand.dispatch_status is not None or demand.agent_run_id is not None):
            await db.commit()
            raise HTTPException(409, "Batch changed; review again")
    for link, demand in rows:
        demand.target_agent_id = executor.id
        demand.body = (f"Chame moodle_execute_approved com request_id={link.request_id}, message_id={demand.id} "
                       f"e params_hash={link.params_hash}. Não altere os parâmetros nem repita a chamada.\n\n"
                       f"{payload.instruction}")
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
    challenge.consumed_at = now
    await db.commit()
    wake_scheduled_dispatch()
    return {"approved": [d.number for _, d in rows]}


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
