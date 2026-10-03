"""Agents asking Marcelo (MCP `ask_marcelo`): delivery and the answer's way back.

Spec: docs/superpowers/specs/2026-10-02-agent-operations-24x7-design.md §5.

Three rules shape this module:

- **Quiet hours.** 23:00-07:00 (America/Sao_Paulo) only urgent questions reach
  Telegram (decision 8, 2026-10-02). A non-urgent one asked at night gets
  `notify_after` = 07:00 and waits; the 08:00 briefing lists it anyway.
- **Which bot.** A Telegram reply lands in the conversation of the bot that
  sent the question, so that bot's agent is the only one who can record it.
  An agent whose charter escalates `telegram_direct` (and has a home chat)
  uses its own bot; everyone else goes through Athos's, with the asker named.
- **The answer is a Task.** It reaches the asker as an ordinary Messages Task
  (from the relay agent, or self-addressed when the asker relayed itself), so
  it wakes the agent through the same executor, deadline and failure path as
  any work -- not a side channel the agent has to remember to poll.
"""
import logging
import uuid
from collections.abc import Awaitable, Callable, Collection
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.notification import Notification
from app.db.models.operations import AgentCharter, AgentQuestion

logger = logging.getLogger(__name__)

QUIET_TZ = ZoneInfo("America/Sao_Paulo")
QUIET_START = time(23, 0)
QUIET_END = time(7, 0)
COORDINATOR_SLUG = "athos"
_BRIDGE_MESSAGES_URL = f"{settings.CHAT_BRIDGE_URL.rstrip('/')}/v1/messages/send"

# (profile_slug or None, "telegram:<chat>", text) -> raises on failure.
TelegramSender = Callable[[str | None, str, str], Awaitable[None]]


def notify_after_for(now: datetime, urgent: bool) -> datetime:
    """When a question may reach Telegram: now, unless it is quiet time and
    the question isn't urgent -- then the end of the quiet window."""
    if urgent:
        return now
    local = now.astimezone(QUIET_TZ)
    clock = local.time()
    if clock >= QUIET_START:
        wake_day = local.date() + timedelta(days=1)
    elif clock < QUIET_END:
        wake_day = local.date()
    else:
        return now
    return datetime.combine(wake_day, QUIET_END, tzinfo=QUIET_TZ).astimezone(timezone.utc)


def _home_chat(agent: Agent | None) -> str | None:
    if agent is None or not agent.profile_slug:
        return None
    from app.core.agent_telegram import read_profile_home_chat

    try:
        return read_profile_home_chat(agent.home_path, agent.runtime_type, agent.profile_slug)
    except Exception:  # an unreadable profile must not break asking
        return None


async def resolve_relay(db: AsyncSession, asker: Agent) -> tuple[Agent | None, str | None]:
    """(relay agent, Telegram chat id). The asker itself when its charter says
    `telegram_direct` and it has a home chat; otherwise Athos. (None, None)
    when nobody can send -- the question stays on the screen only."""
    charter = (
        await db.execute(select(AgentCharter).where(AgentCharter.agent_id == asker.id))
    ).scalar_one_or_none()
    if charter is not None and charter.escalation == "telegram_direct" and asker.telegram_account:
        chat = _home_chat(asker)
        if chat:
            return asker, chat
    coordinator = (
        await db.execute(select(Agent).where(Agent.profile_slug == COORDINATOR_SLUG))
    ).scalar_one_or_none()
    chat = _home_chat(coordinator)
    if coordinator is not None and chat:
        return coordinator, chat
    return None, None


def compose_telegram_text(question: AgentQuestion, asker: Agent) -> str:
    flags = []
    if question.urgent:
        flags.append("URGENTE")
    if question.blocking:
        flags.append("bloqueante")
    header = f"❓ Pergunta #{question.number} de {asker.name}"
    if flags:
        header += f" [{', '.join(flags)}]"
    parts = [header, "", question.question.strip()]
    if question.context:
        parts += ["", f"Contexto: {question.context.strip()}"]
    if question.recommendation:
        parts += ["", f"Recomendação: {question.recommendation.strip()}"]
    parts += [
        "",
        f"Responda aqui começando com #{question.number} (ex.: \"#{question.number} sim\") "
        "ou pela tela Operação → Dúvidas.",
    ]
    return "\n".join(parts)


async def _bridge_send(profile: str | None, target: str, text: str) -> None:
    payload = {"target": target, "message": text}
    if profile:
        payload["profile"] = profile
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            _BRIDGE_MESSAGES_URL, json=payload, headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN}
        )
        response.raise_for_status()


async def run_question_delivery_pass(
    db: AsyncSession,
    now: datetime | None = None,
    send: TelegramSender | None = None,
    ids: Collection[uuid.UUID] | None = None,
) -> int:
    """Send every pending question whose `notify_after` has come and that no
    Telegram message has carried yet. A failed send keeps `telegram_sent_at`
    NULL (the next pass retries) and records why in `telegram_error`.
    `ids` restricts the pass to those questions (tests share the production
    database and must never touch a real question). Returns how many were
    sent."""
    now = now or datetime.now(timezone.utc)
    send = send or _bridge_send
    query = select(AgentQuestion).where(
        AgentQuestion.status == "pending",
        AgentQuestion.telegram_sent_at.is_(None),
        AgentQuestion.notify_after <= now,
    )
    if ids is not None:
        query = query.where(AgentQuestion.id.in_(list(ids)))
    rows = await db.execute(query.order_by(AgentQuestion.number).limit(20))
    sent = 0
    for question in rows.scalars():
        asker = await db.get(Agent, question.agent_id)
        relay = await db.get(Agent, question.relay_agent_id) if question.relay_agent_id else None
        if asker is None:
            continue
        if relay is None or not question.telegram_chat:
            relay, chat = await resolve_relay(db, asker)
            if relay is None:
                question.telegram_error = "no agent with a Telegram home chat can relay this question"
                continue
            question.relay_agent_id, question.telegram_chat = relay.id, chat
        profile = relay.profile_slug if relay.telegram_account else None
        try:
            await send(profile, f"telegram:{question.telegram_chat}", compose_telegram_text(question, asker))
        except Exception as exc:
            logger.warning("Question #%s: Telegram delivery failed: %s", question.number, exc)
            question.telegram_error = str(exc)[:1000]
            continue
        question.telegram_sent_at, question.telegram_error = now, None
        sent += 1
    await db.commit()
    return sent


def compose_answer_message(question: AgentQuestion) -> str:
    lines = [
        f"O Marcelo respondeu a sua pergunta #{question.number}.",
        "",
        "## Pergunta",
        question.question.strip(),
        "",
        "## Resposta",
        (question.answer or "").strip(),
        "",
    ]
    if question.blocking:
        lines.append("Retome o trabalho que estava bloqueado por esta pergunta, seguindo a resposta.")
    else:
        lines.append("Aplique a resposta ao trabalho a que ela se refere.")
    return "\n".join(lines)


async def record_answer(
    db: AsyncSession,
    question: AgentQuestion,
    answer: str,
    *,
    via: str,
    by: str,
    dispatch_at: datetime | None = None,
) -> AgentDemand:
    """Store the answer and hand it to the asker as a Messages Task. The
    caller has already checked the question is still pending. Commits."""
    # Local import: demand.py's routes module imports a lot; keep this
    # module importable from main.py's loops without pulling it in early.
    from app.api.routes.demand import create_demand_and_notify
    from app.api.schemas.demand import DemandSubmitIn

    now = datetime.now(timezone.utc)
    question.answer = answer.strip()
    question.answered_at = now
    question.answered_via = via
    question.answered_by = by
    question.status = "answered"

    asker = await db.get(Agent, question.agent_id)
    sender = (await db.get(Agent, question.relay_agent_id) if question.relay_agent_id else None) or asker
    demand = await create_demand_and_notify(
        db,
        DemandSubmitIn(
            from_agent=sender.profile_slug or sender.name,
            from_agent_id=sender.id,
            target_agent_id=asker.id,
            subject=f"[Resposta] Pergunta #{question.number}"[:255],
            body=compose_answer_message(question),
            origin_type="task",
            scheduled_at=dispatch_at or now,
        ),
        commit=False,
        notify=False,
    )
    demand.reply_to_id = question.origin_demand_id
    question.reply_demand_id = demand.id
    db.add(
        Notification(
            source="system",
            severity="info",
            title=f"Pergunta #{question.number} respondida",
            message=f"{asker.name}: {question.question[:200]}",
            event_key=f"agent-question-answered:{question.id}",
            occurred_at=now,
        )
    )
    await db.commit()
    await db.refresh(demand)
    if demand.scheduled_at is not None and demand.scheduled_at <= datetime.now(timezone.utc):
        from app.core.dispatch_signal import wake_scheduled_dispatch

        wake_scheduled_dispatch()
    return demand
