"""Deliver an execution result without turning routine work into an alert.

Messages remains the canonical execution history. This module returns the
result to a concrete Workspace or explicitly requested Telegram context;
failed outcomes also create an actionable in-app alert. Normal completion
never increments the notification bell merely because execution finished.

Two rules decided with Marcelo (2026-08-13):

**Only on a terminal outcome.** "o feedback só é enviado quando for
concluido ou erro da task" -- nothing is sent while a dispatch is pending,
dispatched or running. "Failed" counts, including a dispatch that never got
to run at all: someone waiting for an answer that can never come is the
worst outcome there is.

**Whoever received the request answers it.** A Hermes agent that took the
request notifies the channel itself; an external runtime (Porthus, Aramis,
Dartan, Vector) never does -- being pure executors outside the ecosystem,
they ask the orchestrator to notify instead. This module is what runs when
nobody received the request in the first place (the dispatch broke before
reaching an agent), and what the delivery for ForgeHub's own surfaces goes
through. It is the safety net, not a replacement for that rule: an item
whose agent is expected to answer still gets its own reply the usual way.

Delivery is idempotent by `feedback_sent_at`: it is stamped only after the
requested return path succeeds (or when Messages itself is the complete
origin context), so a re-run cannot send the same outcome twice and a NULL
stamp continues to mean that requested feedback is owed.
"""
import logging
import re
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.agent import Agent
from app.db.models.demand import (
    DEMAND_TERMINAL_DISPATCH_STATUSES,
    AgentDemand,
)
from app.db.models.notification import Notification

logger = logging.getLogger(__name__)

# The bridge endpoint that forwards to Telegram/Discord/Slack (host-bridge's
# /v1/messages/send -> send_message.py -> Hermes' send_message_tool).
_BRIDGE_MESSAGES_URL = f"{settings.CHAT_BRIDGE_URL.rstrip('/')}/v1/messages/send"


# Asking for the answer on Telegram, in plain words, inside the request body
# (2026-08-13, Marcelo: "eu também posso solicitar um retorno também pelo
# telegram no corpo da tarefa").
#
# Deliberately narrow and literal: it only fires on an explicit mention of
# Telegram next to a word about answering. A looser rule -- "responda" alone,
# say -- would hijack every request that merely uses the word and start
# messaging a chat nobody asked to be messaged on. Being missed is recoverable
# (the in-app notification still happens); being wrong sends someone else's
# output to a chat.
_TELEGRAM_REPLY_PATTERNS = (
    re.compile(r"\b(respond[ae]|retorn[ae]|avis[ae]|notifiqu?e|mand[ae]|envi[ae])\b[^.\n]{0,40}\btelegram\b", re.I),
    re.compile(r"\btelegram\b[^.\n]{0,40}\b(respost|retorno|notifica)", re.I),
    re.compile(r"\bretorn[oa]\s+(?:pel[oa]|no|via)\s+telegram\b", re.I),
)

_TELEGRAM_NO_REPLY_PATTERNS = (
    re.compile(
        r"\b(?:não|nao)\s+(?:me\s+)?"
        r"(?:respond[ae]|retorn[ae]|avis[ae]|notifiqu?e|mand[ae]|envi[ae])\b"
        r"[^.\n]{0,40}\btelegram\b",
        re.I,
    ),
    re.compile(r"\bsem\s+(?:respost|retorno|notifica)[^.\n]{0,20}\btelegram\b", re.I),
)


def wants_telegram_reply(text: str | None) -> bool:
    """True when the request itself asks to be answered on Telegram."""
    if not text:
        return False
    if any(pattern.search(text) for pattern in _TELEGRAM_NO_REPLY_PATTERNS):
        return False
    return any(p.search(text) for p in _TELEGRAM_REPLY_PATTERNS)


def _outcome_line(demand: AgentDemand) -> str:
    """One line stating what happened, used by every channel."""
    if demand.dispatch_status == "completed":
        return f"✅ #{demand.number} — {demand.subject}: concluída."
    reason = demand.dispatch_error or "a execução terminou com erro."
    return f"❌ #{demand.number} — {demand.subject}: {reason}"


def _body(demand: AgentDemand, limit: int = 1500) -> str:
    """The agent's own output, trimmed. Empty when it never produced any --
    a dispatch that failed before running has nothing to show, and inventing
    filler there would read as if something had been attempted."""
    result = (demand.dispatch_result or "").strip()
    if not result:
        return ""
    return result if len(result) <= limit else f"{result[:limit].rstrip()}…"


async def _deliver_notification(db: AsyncSession, demand: AgentDemand, *, title: str) -> None:
    """Create an actionable alert for a failed task outcome."""
    # Terminal-state-scoped: a message can only be delivered once per
    # outcome, and a reprocessed one that fails again is a new event.
    event_key = f"demand-feedback:{demand.id}:{demand.dispatch_attempts}"
    # This notification survives a delivery that fails afterwards (Telegram
    # down, no Workspace channel): it is added first, on purpose, so the run
    # is recorded either way -- but `feedback_sent_at` then stays NULL and
    # the sweep picks the same message up again. Without this check the
    # second attempt re-inserts the same event_key and the UNIQUE violation
    # aborts the whole pass, taking every other owed outcome with it.
    already_notified = (
        await db.execute(
            select(Notification.id).where(Notification.event_key == event_key).limit(1)
        )
    ).scalar_one_or_none()
    if already_notified is not None:
        return
    db.add(
        Notification(
            source="system",
            severity="error",
            title=title,
            message=_outcome_line(demand),
            summary=_body(demand, limit=600) or None,
            event_key=event_key,
            occurred_at=datetime.now(timezone.utc),
        )
    )


async def _deliver_telegram(db: AsyncSession, demand: AgentDemand) -> bool:
    """Answers the Telegram chat that asked, through the right agent's bot.

    Two things have to be right, and each fails differently:

    - **which chat** -- `channel_ref` holds it; without it the bridge falls
      back to the configured home channel, which is how a reply reaches the
      wrong conversation. We do not guess.
    - **which bot** -- every agent has its own (Athos is @HermesAthosbot,
      Atlas @HermesAtlas2bot, Vector @OpenVectorbot), each with its own
      token. Sending through the wrong one makes the answer arrive from an
      agent that never ran the work. The chat id can't disambiguate this:
      it is the same value across every profile.

    The bot is chosen by the agent that *received* the request, matching the
    rule that whoever received it answers it: `from_agent_id` (who passed it
    on) before `target_agent_id` (who ran it).
    """
    if not demand.channel_ref:
        return False
    sender_id = demand.from_agent_id or demand.target_agent_id
    profile: str | None = None
    if sender_id is not None:
        agent = await db.get(Agent, sender_id)
        # Only a Hermes profile has a bot the bridge can send through; an
        # external runtime (Porthus, Aramis, Dartan) has none, and asking for
        # one would 404. Falling through with profile=None uses the global
        # install, which is the pre-2026-08-13 behaviour.
        if agent is not None and agent.telegram_account and agent.profile_slug:
            profile = agent.profile_slug
    text = _outcome_line(demand)
    body = _body(demand, limit=1200)
    if body:
        text = f"{text}\n\n{body}"
    payload = {"target": f"telegram:{demand.channel_ref}", "message": text}
    if profile:
        payload["profile"] = profile
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            _BRIDGE_MESSAGES_URL,
            json=payload,
            headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
        )
        response.raise_for_status()
    return True


async def _deliver_workspace(db: AsyncSession, demand: AgentDemand) -> bool:
    """Persist the outcome in the Conversation or Channel that requested it."""
    if not demand.channel_ref:
        return False
    try:
        scope_id = uuid.UUID(demand.channel_ref)
    except (ValueError, TypeError, AttributeError):
        return False

    from app.db.models.channel import ChatChannel, ChatChannelMessage
    from app.db.models.chat import ChatMessage, ChatSession

    text = _outcome_line(demand)
    body = _body(demand)
    if body:
        text = f"{text}\n\n{body}"

    session = await db.get(ChatSession, scope_id)
    if session is not None:
        db.add(ChatMessage(
            session_id=session.id,
            role="assistant",
            content=text,
            responding_agent_id=demand.target_agent_id,
        ))
        return True

    channel = await db.get(ChatChannel, scope_id)
    if channel is None:
        return False
    already_narrated = (
        await db.execute(
            select(ChatChannelMessage.id).where(
                ChatChannelMessage.triggered_demand_id == demand.id,
                ChatChannelMessage.author_type == "system",
            ).limit(1)
        )
    ).scalar_one_or_none()
    if already_narrated is None:
        db.add(ChatChannelMessage(
            channel_id=channel.id,
            author_type="system",
            content=text,
            triggered_demand_id=demand.id,
        ))
    return True


async def deliver_feedback(db: AsyncSession, demand: AgentDemand) -> bool:
    """Sends one message's outcome back to its channel. Caller commits.

    Returns True when the requested return was handled. Never raises: a
    channel being unreachable must not roll back the execution result that
    is already recorded, nor stop the other messages in the same sweep. It
    leaves `feedback_sent_at` NULL, so the delivery stays visibly owed.
    """
    if demand.dispatch_status not in DEMAND_TERMINAL_DISPATCH_STATUSES:
        return False
    if demand.dispatch_status == "failed" and demand.from_agent_id is not None:
        # This app disables autoflush. Preserve the caller's terminal state
        # and directory before refreshing under the delivery lock.
        await db.flush()
        demand = (await db.execute(
            select(AgentDemand).where(AgentDemand.id == demand.id)
            .with_for_update().execution_options(populate_existing=True)
        )).scalar_one()
        if demand.feedback_sent_at is None:
            marker = f"failure-feedback:{demand.id}:{demand.dispatch_attempts}"
            existing = (await db.execute(select(AgentDemand.id).where(
                AgentDemand.reply_to_id == demand.id,
                AgentDemand.command_text == marker,
            ))).scalar_one_or_none()
            if existing is None:
                db.add(AgentDemand(
                    from_agent="Messages",
                    from_agent_id=demand.target_agent_id,
                    target_agent_id=demand.from_agent_id,
                    subject=f"Falha na tarefa #{demand.number}",
                    body=(
                        f"A tarefa #{demand.number} precisa de decisão do solicitante.\n"
                        f"Diretório: {demand.working_path or 'não informado'}\n"
                        f"Tentativa: {demand.dispatch_attempts}\n"
                        "Consulte o erro e o resultado na tarefa original antes de corrigir, "
                        "autorizar nova tentativa ou informar quem solicitou.\n"
                        "Alterações parciais não foram verificadas automaticamente."
                    ),
                    origin_type="task", reply_to_id=demand.id,
                    command_text=marker, requires_response=False,
                    dispatch_status="completed", channel="agent",
                    feedback_sent_at=datetime.now(timezone.utc),
                ))
                await db.flush()
    if demand.feedback_sent_at is not None:
        return False

    now = datetime.now(timezone.utc)
    title = f"Task {'concluída' if demand.dispatch_status == 'completed' else 'falhou'}: {demand.subject}"
    failed = demand.dispatch_status != "completed"

    try:
        if demand.channel == "telegram":
            if failed:
                await _deliver_notification(db, demand, title=title)
            # Telegram feedback is opt-in from the message itself. Channel
            # metadata records where a request came from, but it is not
            # permission to push the result back out of ForgeHub. In
            # particular, a stale or malformed channel_ref must not turn an
            # ordinary completed message into an infinite external-delivery
            # retry. The same narrow language detector used at submission is
            # the canonical expression of that request.
            requested = wants_telegram_reply(f"{demand.subject}\n{demand.body}")
            delivered = await _deliver_telegram(db, demand) if requested else False
            if not requested:
                logger.info(
                    "Feedback for #%s has Telegram metadata but no explicit Telegram "
                    "reply request; result remains in Messages",
                    demand.number,
                )
            elif not delivered:
                logger.warning(
                    "Feedback for #%s has channel=telegram but no chat to answer -- "
                    "requested return remains owed", demand.number,
                )
                return False
        elif demand.channel == "workspace":
            if failed:
                await _deliver_notification(db, demand, title=title)
            if not await _deliver_workspace(db, demand):
                logger.warning(
                    "Feedback for #%s has no valid Workspace address; requested return remains owed",
                    demand.number,
                )
                return False
        elif demand.channel in ("assistant", "factory"):
            if failed:
                await _deliver_notification(db, demand, title=title)
        elif demand.channel == "agent":
            # An agent asked: the existing requires_response/reply_to_id path
            # already routes the answer back as a real message. Duplicating
            # it here would put the same outcome in the agent's inbox twice.
            if not failed or demand.from_agent_id is None:
                return False
        else:
            # Old or unattributed failures still require attention. Routine
            # successful execution remains visible in Messages without
            # creating notification noise.
            if failed:
                await _deliver_notification(db, demand, title=title)
    except httpx.HTTPError as exc:
        logger.warning("Feedback delivery for #%s failed: %s", demand.number, exc)
        return False

    demand.feedback_sent_at = now
    return True


async def run_feedback_pass(db: AsyncSession) -> int:
    """Delivers every outcome that is owed one. Returns how many were sent.

    Driven by state rather than by an event hook: a message that reached a
    terminal state without its feedback going out -- because the app
    restarted mid-delivery, or Telegram was down -- is picked up on the next
    pass instead of being lost. That is the whole reason `feedback_sent_at`
    is a column and not just a log line.
    """
    owed = (
        await db.execute(
            select(AgentDemand).where(
                AgentDemand.dispatch_status.in_(DEMAND_TERMINAL_DISPATCH_STATUSES),
                AgentDemand.feedback_sent_at.is_(None),
                # An agent's answer already routes back on its own path.
                (AgentDemand.channel.is_distinct_from("agent"))
                | ((AgentDemand.dispatch_status == "failed") & AgentDemand.from_agent_id.isnot(None)),
            )
        )
    ).scalars().all()

    sent = 0
    for demand in owed:
        if await deliver_feedback(db, demand):
            sent += 1
    # A failed channel delivery may still have produced an actionable task
    # failure alert. Commit the pass whenever it inspected owed outcomes;
    # `feedback_sent_at` remains NULL for every return that did not get out.
    if owed:
        await db.commit()
    if sent:
        logger.info("Feedback: delivered %d outcome(s) to their channels", sent)
    return sent
