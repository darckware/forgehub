"""The re-attachable turn: what makes a run survive the browser.

Modelled on the Terminal, which already solves this with tmux (2026-08-13,
Marcelo: "não posso perder o contexto e o processamento por um erro ou
congelamento do frontend"). The run itself always survived -- it is a
subprocess on the host -- but nothing recorded that it existed, so a reload
or a crash left a blank screen while the agent kept working.

One helper serves chat and channel, and these tests pin both the shared
behaviour and the two places where the surfaces genuinely differ: a channel
runs several agents in one turn, and only a chat turn can pause for an
approval.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy import delete, select

from app.core.active_turns import (
    close_turn,
    get_active,
    mark_reattached,
    open_turn,
    record_step,
    record_text,
    set_pending_approval,
    sweep_stale,
    update_step,
)
from app.db.base import AsyncSessionLocal
from app.db.models.active_turn import ActiveTurn


@pytest_asyncio.fixture
async def scope_id():
    sid = uuid.uuid4()
    yield sid
    async with AsyncSessionLocal() as session:
        await session.execute(delete(ActiveTurn).where(ActiveTurn.scope_id == sid))
        await session.commit()


async def _open(scope_id, *, scope="chat", agent_id=None, prompt="faz isso"):
    async with AsyncSessionLocal() as session:
        turn = await open_turn(
            session, scope=scope, scope_id=scope_id, stream_id=uuid.uuid4().hex[:16],
            prompt=prompt, agent_id=agent_id,
        )
        await session.commit()
        return turn.id


async def test_a_running_turn_is_findable_again(scope_id):
    """The whole point: after the client is gone, the server still knows
    something is running here."""
    turn_id = await _open(scope_id)

    async with AsyncSessionLocal() as session:
        found = await get_active(session, scope="chat", scope_id=scope_id)
    assert found is not None and found.id == turn_id


async def test_the_trail_is_readable_mid_run(scope_id):
    """Reconnecting has to show *context*, not just a spinner -- the same
    way `tmux attach` repaints the pane instead of handing back an empty
    screen."""
    turn_id = await _open(scope_id)
    async with AsyncSessionLocal() as session:
        await record_step(session, turn_id, {"id": "s1", "name": "read", "status": "running"})
        await record_text(session, turn_id, "Analisando")
        await record_text(session, turn_id, " o código")
        await update_step(session, turn_id, "s1", {"status": "done"})
        await session.commit()

    async with AsyncSessionLocal() as session:
        found = await get_active(session, scope="chat", scope_id=scope_id)
    assert found.live_text == "Analisando o código"
    assert found.steps[0]["status"] == "done"


async def test_a_finished_turn_is_no_longer_active(scope_id):
    turn_id = await _open(scope_id)
    async with AsyncSessionLocal() as session:
        await close_turn(session, turn_id, status="completed")
        await session.commit()

    async with AsyncSessionLocal() as session:
        assert await get_active(session, scope="chat", scope_id=scope_id) is None


async def test_closing_twice_keeps_the_first_outcome(scope_id):
    """A late sweep must not overwrite a real result with a timeout."""
    turn_id = await _open(scope_id)
    async with AsyncSessionLocal() as session:
        await close_turn(session, turn_id, status="completed")
        await close_turn(session, turn_id, status="failed", error="tarde demais")
        await session.commit()

    async with AsyncSessionLocal() as session:
        turn = await session.get(ActiveTurn, turn_id)
    assert turn.status == "completed" and turn.error is None


async def test_a_dead_turn_is_swept_and_says_why(scope_id):
    """The case this exists for: the bridge keeps its subprocesses in memory,
    so a restart loses them while the row still claims to be running. Without
    the sweep every reconnect would wait on a stream with no producer."""
    turn_id = await _open(scope_id)
    async with AsyncSessionLocal() as session:
        turn = await session.get(ActiveTurn, turn_id)
        turn.deadline_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await session.commit()

    async with AsyncSessionLocal() as session:
        assert await sweep_stale(session) >= 1

    async with AsyncSessionLocal() as session:
        turn = await session.get(ActiveTurn, turn_id)
    assert turn.status == "failed"
    assert "never reported back" in turn.error


async def test_an_expired_turn_is_never_offered_for_reattach(scope_id):
    """Even before the sweep runs: handing back a turn nobody is producing
    would leave the UI waiting forever."""
    turn_id = await _open(scope_id)
    async with AsyncSessionLocal() as session:
        turn = await session.get(ActiveTurn, turn_id)
        turn.deadline_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()

    async with AsyncSessionLocal() as session:
        assert await get_active(session, scope="chat", scope_id=scope_id) is None


async def test_a_new_turn_closes_an_abandoned_one(scope_id):
    """A session streams one turn at a time, so a second open means the
    previous one died without reporting -- leaving it would make "what should
    I re-attach to?" ambiguous."""
    first = await _open(scope_id)
    second = await _open(scope_id)

    async with AsyncSessionLocal() as session:
        old = await session.get(ActiveTurn, first)
        found = await get_active(session, scope="chat", scope_id=scope_id)
    assert old.status == "failed"
    assert found.id == second


# --- particularidades de cada superfície ---------------------------------

async def test_a_channel_turn_keeps_each_agents_work_apart(scope_id):
    """A channel gathers every mentioned agent at once (and `#all`
    broadcasts). A flat trail would blend two agents' work with no way to
    tell whose is whose, and their replies would interleave into nonsense."""
    a1, a2 = uuid.uuid4(), uuid.uuid4()
    turn_id = await _open(scope_id, scope="channel")
    async with AsyncSessionLocal() as session:
        await record_step(session, turn_id, {"id": "x", "name": "grep"}, agent_id=a1)
        await record_step(session, turn_id, {"id": "y", "name": "read"}, agent_id=a2)
        await record_text(session, turn_id, "Atlas responde", agent_id=a1)
        await record_text(session, turn_id, "Scriba responde", agent_id=a2)
        await session.commit()

    async with AsyncSessionLocal() as session:
        turn = await get_active(session, scope="channel", scope_id=scope_id)
    assert {s["agent_id"] for s in turn.steps} == {str(a1), str(a2)}
    assert turn.live_text_by_agent[str(a1)] == "Atlas responde"
    assert turn.live_text_by_agent[str(a2)] == "Scriba responde"


async def test_a_chat_turn_can_be_paused_on_an_approval(scope_id):
    """Chat-only: a turn can stop mid-stream for a yes/no. Without recording
    it, a client that reconnects while paused never shows the prompt, and the
    turn waits forever on an answer nobody is asked for."""
    turn_id = await _open(scope_id)
    async with AsyncSessionLocal() as session:
        await set_pending_approval(session, turn_id, {"streamId": "s", "command": "rm -rf /tmp/x"})
        await session.commit()

    async with AsyncSessionLocal() as session:
        turn = await get_active(session, scope="chat", scope_id=scope_id)
    assert turn.pending_approval["command"] == "rm -rf /tmp/x"

    async with AsyncSessionLocal() as session:
        await set_pending_approval(session, turn_id, None)
        await session.commit()
    async with AsyncSessionLocal() as session:
        turn = await get_active(session, scope="chat", scope_id=scope_id)
    assert turn.pending_approval is None


async def test_scopes_do_not_see_each_other(scope_id):
    """Same id, different surface: a chat turn must not answer a channel's
    question. The (scope, scope_id) pair is what keeps one table honest for
    both."""
    await _open(scope_id, scope="chat")

    async with AsyncSessionLocal() as session:
        assert await get_active(session, scope="channel", scope_id=scope_id) is None


async def test_reattach_is_counted(scope_id):
    """Not used for logic -- it is how you tell "nobody came back" from
    "reconnected fine" when a report says the screen stayed empty."""
    turn_id = await _open(scope_id)
    async with AsyncSessionLocal() as session:
        await mark_reattached(session, turn_id)
        await mark_reattached(session, turn_id)
        await session.commit()

    async with AsyncSessionLocal() as session:
        turn = await session.get(ActiveTurn, turn_id)
    assert turn.reattach_count == 2
