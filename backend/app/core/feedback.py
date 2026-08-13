"""Delivering an execution's outcome back to where it was asked for.

Messages executes everything, but until now the result stayed inside
Messages: someone who asked from the Workspace, from the Assistant panel or
from Telegram had no way of learning that their task finished. This module
is the return path.

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

Delivery is idempotent by `feedback_sent_at`: it is stamped in the same
transaction as the delivery, so a re-run can never send the same outcome
twice, and a NULL stamp on a terminal message is exactly the signal that
feedback is still owed.
"""
import logging
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
    """The Assistant's return path, and the fallback for every channel.

    The Assistant lives on every screen outside the Workspace, so there is no
    conversation to answer into -- and by the time a run finishes the user
    may well be on another page entirely. A notification is the only thing
    that reaches them wherever they are.

    Severity mirrors the outcome so a failure can be told apart from a
    success without opening it -- the bell holds thousands of routine info
    rows, and an error that looks like all of them is invisible.
    """
    db.add(
        Notification(
            source="system",
            severity="success" if demand.dispatch_status == "completed" else "error",
            title=title,
            message=_outcome_line(demand),
            summary=_body(demand, limit=600) or None,
            # Terminal-state-scoped: a message can only be delivered once per
            # outcome, and a reprocessed one that fails again is a new event.
            event_key=f"demand-feedback:{demand.id}:{demand.dispatch_attempts}",
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
        response = await client.post(_BRIDGE_MESSAGES_URL, json=payload)
        response.raise_for_status()
    return True


async def deliver_feedback(db: AsyncSession, demand: AgentDemand) -> bool:
    """Sends one message's outcome back to its channel. Caller commits.

    Returns True when something was delivered. Never raises: a channel being
    unreachable must not roll back the execution result that is already
    recorded, nor stop the other messages in the same sweep. What it does
    instead is leave `feedback_sent_at` NULL, so the delivery stays visibly
    owed rather than silently lost.
    """
    if demand.dispatch_status not in DEMAND_TERMINAL_DISPATCH_STATUSES:
        return False
    if demand.feedback_sent_at is not None:
        return False

    now = datetime.now(timezone.utc)
    title = f"Task {'concluída' if demand.dispatch_status == 'completed' else 'falhou'}: {demand.subject}"

    try:
        if demand.channel == "telegram":
            # Notify in the app as well: the Telegram send can fail, and this
            # is the record that the run finished either way.
            await _deliver_notification(db, demand, title=title)
            delivered = await _deliver_telegram(db, demand)
            if not delivered:
                logger.warning(
                    "Feedback for #%s has channel=telegram but no chat to answer -- "
                    "notified in-app only", demand.number,
                )
        elif demand.channel in ("workspace", "assistant", "factory"):
            # All three surface in-app. Workspace and Factory additionally
            # show the outcome in their own screens, which read the message
            # (and, for Factory, the linked task) directly -- so the
            # notification is what tells the person to go look, not the only
            # place the result exists.
            await _deliver_notification(db, demand, title=title)
        elif demand.channel == "agent":
            # An agent asked: the existing requires_response/reply_to_id path
            # already routes the answer back as a real message. Duplicating
            # it here would put the same outcome in the agent's inbox twice.
            return False
        else:
            # No channel recorded (filed before this existed, or by a writer
            # that doesn't set one). Still notify: an unattributed outcome is
            # better than a silent one.
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
                AgentDemand.channel.is_distinct_from("agent"),
            )
        )
    ).scalars().all()

    sent = 0
    for demand in owed:
        if await deliver_feedback(db, demand):
            sent += 1
    if sent:
        await db.commit()
        logger.info("Feedback: delivered %d outcome(s) to their channels", sent)
    return sent
