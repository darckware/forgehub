"""The lifecycle of a re-attachable agent turn, shared by chat and channel.

One helper for both surfaces (2026-08-13, Marcelo: "um helper para os dois
chats conversation e channel"). They stream the same way, fail the same way
and are reconnected to the same way -- the only real difference is what the
turn hangs off, which the (scope, scope_id) pair carries.

Written as plain functions over an AsyncSession rather than a class: every
caller already has a session and commits on its own schedule, and a stateful
object would only add a second place to reason about transactions.

The contract, mirroring the Terminal's tmux lifecycle:

    open_turn()      ~ tmux new-session   -- a run starts, becomes findable
    record_step()    ~ output accumulating in the pane
    record_text()    ~ idem, for the reply text
    close_turn()     ~ the session ends
    get_active()     ~ tmux has-session   -- "is something running here?"
    sweep_stale()    ~ reaping a pane whose process died with the daemon

Callers commit; nothing here commits on its own, matching the rest of
app/core (see demand.py's "Caller commits" note).
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.active_turn import (
    ACTIVE_TURN_TIMEOUT_MINUTES,
    ActiveTurn,
)

logger = logging.getLogger(__name__)

# How much of the streamed reply is kept on the row. The full text lands in
# the persisted message at the end; this copy exists only so a reconnect can
# show what has been said so far, and letting it grow without bound would
# rewrite an ever-larger row on every delta.
MAX_LIVE_TEXT_CHARS = 20_000


async def open_turn(
    db: AsyncSession,
    *,
    scope: str,
    scope_id: uuid.UUID,
    stream_id: str,
    prompt: str,
    agent_id: uuid.UUID | None = None,
    hidden: bool = False,
    supersede_existing: bool = True,
) -> ActiveTurn:
    """Registers a turn as running. Caller commits.

    By default, any turn already running for the same owner is closed as
    failed first: a chat session streams one turn at a time, so a second open
    means the previous one died without reporting. Channels explicitly pass
    ``supersede_existing=False`` because their composer supports several
    independent sends in flight at once.
    """
    if supersede_existing:
        await _close_running(db, scope=scope, scope_id=scope_id, status="failed",
                             error="Superseded by a newer turn (the previous run never reported back).")
    turn = ActiveTurn(
        scope=scope,
        scope_id=scope_id,
        stream_id=stream_id,
        prompt=prompt,
        agent_id=agent_id,
        hidden=hidden,
        status="running",
        deadline_at=datetime.now(timezone.utc) + timedelta(minutes=ACTIVE_TURN_TIMEOUT_MINUTES),
    )
    db.add(turn)
    await db.flush()
    return turn


async def get_active(db: AsyncSession, *, scope: str, scope_id: uuid.UUID) -> ActiveTurn | None:
    """The turn currently running for this session/channel, if any.

    This is the question the client asks on mount -- the `tmux has-session`
    of the chat. A row past its deadline is *not* returned as running: the
    sweep may not have run yet, and handing back a turn nobody is producing
    would leave the UI waiting forever on a dead stream.
    """
    turn = (
        await db.execute(
            select(ActiveTurn)
            .where(
                ActiveTurn.scope == scope,
                ActiveTurn.scope_id == scope_id,
                ActiveTurn.status == "running",
            )
            .order_by(ActiveTurn.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if turn is None:
        return None
    if turn.deadline_at is not None and turn.deadline_at <= datetime.now(timezone.utc):
        return None
    return turn


async def get_active_all(db: AsyncSession, *, scope: str, scope_id: uuid.UUID) -> list[ActiveTurn]:
    """Return every live turn for a multi-agent Conversation.

    Channels coordinate several agents inside one row. Conversations keep
    one row per agent so each independent stream can be observed and stopped.
    """
    now = datetime.now(timezone.utc)
    turns = list((await db.execute(
        select(ActiveTurn)
        .where(
            ActiveTurn.scope == scope,
            ActiveTurn.scope_id == scope_id,
            ActiveTurn.status == "running",
        )
        .order_by(ActiveTurn.created_at.asc())
    )).scalars().all())
    return [turn for turn in turns if turn.deadline_at is None or turn.deadline_at > now]


async def record_step(
    db: AsyncSession, turn_id: uuid.UUID, step: dict, *, agent_id: uuid.UUID | None = None
) -> None:
    """Appends one tool step to the trail. Caller commits.

    `agent_id` is what lets one table serve both surfaces without lying: a
    chat turn has a single agent and it is redundant, but a channel turn
    runs several in parallel, and a flat trail would blend their work with
    no way to tell whose step is whose. Callers pass it either way, so the
    two sides read identically.

    Read-modify-write on the JSONB rather than a jsonb_set append: a chat
    turn has one writer, and a channel turn's parallel agents are gathered
    inside one request/session, so there is no cross-transaction race here.
    """
    turn = await db.get(ActiveTurn, turn_id)
    if turn is None or turn.status != "running":
        return
    entry = {**step, "agent_id": str(agent_id) if agent_id else None}
    turn.steps = [*(turn.steps or []), entry]


async def update_step(db: AsyncSession, turn_id: uuid.UUID, step_id: str, patch: dict) -> None:
    """Updates one step in place (a tool finishing, say). Caller commits."""
    turn = await db.get(ActiveTurn, turn_id)
    if turn is None or turn.status != "running":
        return
    turn.steps = [
        {**s, **patch} if s.get("id") == step_id else s
        for s in (turn.steps or [])
    ]


def _capped(text: str) -> str:
    return text[-MAX_LIVE_TEXT_CHARS:] if len(text) > MAX_LIVE_TEXT_CHARS else text


async def record_text(
    db: AsyncSession, turn_id: uuid.UUID, delta: str, *, agent_id: uuid.UUID | None = None
) -> None:
    """Appends streamed reply text. Caller commits.

    Without `agent_id` (chat) it accumulates in one place. With it (channel)
    it also accumulates per agent, because several are answering at once and
    a single blob would interleave their sentences into nonsense. Keeping
    both means a channel client can render each agent's own text while the
    chat client keeps reading the field it always read.

    Truncated at MAX_LIVE_TEXT_CHARS: this copy only has to show a
    reconnecting client what has been said so far, while the complete reply
    is persisted as a real message when the turn ends.
    """
    turn = await db.get(ActiveTurn, turn_id)
    if turn is None or turn.status != "running":
        return
    turn.live_text = _capped((turn.live_text or "") + delta)
    if agent_id is not None:
        key = str(agent_id)
        by_agent = dict(turn.live_text_by_agent or {})
        by_agent[key] = _capped(str(by_agent.get(key, "")) + delta)
        turn.live_text_by_agent = by_agent


async def set_pending_approval(
    db: AsyncSession, turn_id: uuid.UUID, approval: dict | None
) -> None:
    """Records (or clears) a privileged-action approval the run is blocked
    on. Caller commits.

    Chat-only in practice: a chat turn can pause mid-stream for a yes/no,
    and a client that reconnects while it is paused has to be shown that
    prompt again -- otherwise the turn waits forever on an answer the screen
    never asks for. Channels never pause this way, so they simply never call
    it; the helper stays the same for both.
    """
    turn = await db.get(ActiveTurn, turn_id)
    if turn is None or turn.status != "running":
        return
    turn.pending_approval = approval


async def close_turn(
    db: AsyncSession,
    turn_id: uuid.UUID,
    *,
    status: str = "completed",
    error: str | None = None,
) -> bool:
    """Marks a turn finished. Caller commits. Returns whether this call is
    the one that actually made the transition.

    Idempotent by status: a turn that already reached a terminal state is
    left alone, so the completion path and a late sweep can both run without
    the second one overwriting the real outcome with a timeout. The return
    value is what lets a caller tell "I closed it" from "someone already had"
    -- chat.py's stop route and its detached turn task both race to close the
    same turn (an explicit Stop vs. the bridge stream ending on its own), and
    only the winner should persist the interrupted-turn message; the loser
    would otherwise write a duplicate one.
    """
    turn = await db.get(ActiveTurn, turn_id)
    if turn is None or turn.status != "running":
        return False
    turn.status = status
    turn.error = error
    turn.finished_at = datetime.now(timezone.utc)
    turn.deadline_at = None
    return True


async def mark_reattached(db: AsyncSession, turn_id: uuid.UUID) -> None:
    """Counts one client coming back to this turn. Caller commits."""
    await db.execute(
        update(ActiveTurn)
        .where(ActiveTurn.id == turn_id)
        .values(reattach_count=ActiveTurn.reattach_count + 1)
    )


async def sweep_stale(db: AsyncSession) -> int:
    """Closes turns that passed their deadline without reporting back.

    The case this exists for: the bridge keeps its subprocess registry in
    memory, so restarting it loses every running process while these rows
    still claim they are running. Without the sweep those rows stay
    "running" forever and each reconnect waits on a stream that has no
    producer. Commits, since it is driven by a poll loop with no other work
    to batch with.
    """
    now = datetime.now(timezone.utc)
    stale = (
        await db.execute(
            select(ActiveTurn).where(
                ActiveTurn.status == "running",
                ActiveTurn.deadline_at.isnot(None),
                ActiveTurn.deadline_at <= now,
            )
        )
    ).scalars().all()
    for turn in stale:
        turn.status = "failed"
        turn.error = (
            f"No activity for {ACTIVE_TURN_TIMEOUT_MINUTES} minutes -- the run never reported back "
            "(the host-bridge may have restarted)."
        )
        turn.finished_at = now
        turn.deadline_at = None
    if stale:
        await db.commit()
        logger.info("Active turns: closed %d stale turn(s)", len(stale))
    return len(stale)


async def _close_running(
    db: AsyncSession, *, scope: str, scope_id: uuid.UUID, status: str, error: str
) -> None:
    await db.execute(
        update(ActiveTurn)
        .where(
            ActiveTurn.scope == scope,
            ActiveTurn.scope_id == scope_id,
            ActiveTurn.status == "running",
        )
        .values(status=status, error=error, finished_at=datetime.now(timezone.utc), deadline_at=None)
    )
