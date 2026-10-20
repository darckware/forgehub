"""Phase 4 of Agent Activity: lanes, event table and replay (core/agent_activity_timeline.py)."""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.agent_activity_stream import build_live_snapshot
from app.core.agent_activity_timeline import build_timeline, dispatch_interval, pair_runtime_events
from app.core.security import create_access_token, hash_password
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.agent_activity_event import AgentActivityEvent
from app.db.models.demand import AgentDemand
from app.db.models.user import User
from app.main import app

T0 = datetime(2026, 9, 28, 14, 0, tzinfo=timezone.utc)


def _event(kind, minute, **extra):
    base = {
        "kind": kind, "occurred_at": T0 + timedelta(minutes=minute), "agent_id": None,
        "session_id": "s1", "turn_id": "t1", "tool_call_id": None, "platform": "telegram",
        "counterpart_kind": "owner", "counterpart_ref": None, "model": "m", "tool_name": None,
        "status": None, "error_type": None, "duration_ms": None,
    }
    base.update(extra)
    return SimpleNamespace(**base)


def test_closed_turn_carries_its_tools():
    blocks = pair_runtime_events(
        [
            _event("turn_started", 0),
            _event("tool_started", 1, tool_call_id="c1", tool_name="terminal"),
            _event("tool_ended", 2, tool_call_id="c1", status="ok", duration_ms=60_000),
            # a tool_ended whose start never arrived is placed by its duration
            _event("tool_ended", 4, tool_call_id="c2", tool_name="read_file", status="error", duration_ms=30_000),
            _event("turn_ended", 5, status="completed"),
        ],
        now=T0 + timedelta(hours=1),
    )
    assert len(blocks) == 1
    block = blocks[0]
    assert (block.start, block.end, block.status) == (T0, T0 + timedelta(minutes=5), "completed")
    assert [tool.tool_name for tool in block.tools] == ["terminal", "read_file"]
    assert block.tools[1].start == T0 + timedelta(minutes=3, seconds=30)


def test_turn_without_end_is_open_then_abandoned():
    events = [_event("turn_started", 0), _event("tool_started", 1, tool_call_id="c1", tool_name="terminal")]
    open_block = pair_runtime_events(events, now=T0 + timedelta(minutes=10))[0]
    assert open_block.end is None and open_block.status == "open"
    assert open_block.tools[0].end is None
    stale = pair_runtime_events(events, now=T0 + timedelta(hours=2))[0]
    assert stale.status == "abandoned" and stale.end == T0 + timedelta(minutes=1)


def test_successive_turns_of_one_session_do_not_merge():
    blocks = pair_runtime_events(
        [
            _event("turn_started", 0, turn_id=None),
            _event("turn_ended", 1, turn_id=None, status="completed"),
            _event("turn_started", 10, turn_id=None),
            _event("turn_ended", 12, turn_id=None, status="failed", error_type="provider"),
        ],
        now=T0 + timedelta(hours=1),
    )
    assert [(b.status, b.end - b.start) for b in blocks] == [
        ("completed", timedelta(minutes=1)),
        ("failed", timedelta(minutes=2)),
    ]


def test_dispatch_interval():
    started = T0
    finished = T0 + timedelta(minutes=7)
    row = SimpleNamespace(
        dispatched_at=started, scheduled_at=T0 - timedelta(minutes=1), dispatch_status="completed",
        task_execution_at=finished, updated_at=finished + timedelta(minutes=1),
    )
    assert dispatch_interval(row) == (started, finished)
    row.dispatch_status = "running"
    assert dispatch_interval(row) == (started, None)
    # rows from before dispatched_at existed fall back to scheduled_at
    row.dispatched_at, row.dispatch_status = None, "failed"
    assert dispatch_interval(row) == (T0 - timedelta(minutes=1), finished)
    row.dispatch_status = None
    assert dispatch_interval(row) == (None, None)


@pytest.mark.asyncio
async def test_timeline_and_replay_reconstruct_a_past_hour():
    """"What did the agent do between 14h and 15h" -- lanes, table and replay all agree."""
    suffix = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc).replace(microsecond=0)
    base = now - timedelta(hours=3)
    async with AsyncSessionLocal() as db:
        worker = Agent(name=f"Timeline Worker {suffix}", agent_type="executor", runtime_type="hermes",
                       profile_slug=f"timeline-{suffix}")
        sender = Agent(name=f"Timeline Sender {suffix}", agent_type="executor", runtime_type="hermes",
                       profile_slug=f"timeline-sender-{suffix}")
        admin = User(username=f"timeline-admin-{suffix}", hashed_password=hash_password("x"), is_admin=True)
        db.add_all([worker, sender, admin])
        await db.flush()

        def ev(kind, minute, **extra):
            return AgentActivityEvent(
                agent_id=worker.id, profile=worker.profile_slug, kind=kind,
                occurred_at=base + timedelta(minutes=minute), session_id="sess", turn_id="turn-1",
                platform="telegram", counterpart_kind="owner", delivery_id=f"tl-{suffix}-{kind}-{minute}",
                **extra,
            )

        db.add_all([
            ev("turn_started", 10, model="m"),
            ev("tool_started", 11, tool_call_id="call-1", tool_name="terminal"),
            ev("tool_ended", 13, tool_call_id="call-1", status="ok", duration_ms=120_000),
            ev("turn_ended", 15, status="completed"),
        ])
        demand = AgentDemand(
            from_agent=sender.profile_slug, from_agent_id=sender.id, target_agent_id=worker.id,
            subject=f"timeline {suffix}", body="b", origin_type="task", requires_response=False,
            dispatch_status="completed", dispatched_at=base + timedelta(minutes=30),
            task_execution_at=base + timedelta(minutes=40), created_at=base + timedelta(minutes=29),
            updated_at=base + timedelta(minutes=40),
        )
        db.add(demand)
        await db.commit()
        worker_id, sender_id, demand_id, username = worker.id, sender.id, demand.id, admin.username

    try:
        async with AsyncSessionLocal() as db:
            view = await build_timeline(
                db, start=base, end=base + timedelta(hours=1), now=now, agent_id=None
            )
            # mid-turn, while the tool runs
            during_tool = await build_live_snapshot(db, now=base + timedelta(minutes=12), historical=True)
            during_dispatch = await build_live_snapshot(db, now=base + timedelta(minutes=35), historical=True)
            after = await build_live_snapshot(db, now=base + timedelta(minutes=50), historical=True)

        lane = next(lane for lane in view.lanes if lane.agent_id == worker_id)
        kinds = [(block.kind, block.status) for block in lane.blocks]
        assert kinds == [("turn", "completed"), ("dispatch", "completed")]
        turn, dispatch = lane.blocks
        assert turn.end - turn.start == timedelta(minutes=5)
        assert [tool.tool_name for tool in turn.tools] == ["terminal"]
        assert dispatch.counterpart_agent_id == sender_id
        assert dispatch.canonical_path == f"/demands?message={demand_id}"
        assert any(m.id == demand_id and m.from_agent_id == sender_id for m in view.messages)
        mine = [row.kind for row in view.events if row.agent_id == worker_id]
        assert {"turn_started", "tool_started", "tool_ended", "turn_ended", "dispatch_started",
                "dispatch_completed"} <= set(mine)

        def live_of(snapshot):
            item = next((item for item in snapshot.agents if item.agent_id == worker_id), None)
            return item.live if item else None

        assert live_of(during_tool).state == "executing"
        assert live_of(during_tool).tool_name == "terminal"
        assert during_tool.pulse.cost_today is None  # no recorded past for ForgeRouter
        assert any(link.target_agent_id == worker_id and link.active for link in during_tool.links)
        assert any(
            link.kind == "message" and link.target_agent_id == worker_id and link.active
            for link in during_dispatch.links
        )
        assert live_of(after).state == "idle"
        assert not any(link.target_agent_id == worker_id and link.active for link in after.links)

        headers = {"Authorization": f"Bearer {create_access_token(username)}"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/agent-activity/timeline",
                params={"start": base.isoformat(), "end": (base + timedelta(hours=1)).isoformat(),
                        "agent_id": str(worker_id)},
                headers=headers,
            )
            assert response.status_code == 200, response.text
            assert [lane["agent_id"] for lane in response.json()["lanes"]] == [str(worker_id)]
            too_wide = await client.get(
                "/api/v1/agent-activity/timeline",
                params={"start": (now - timedelta(hours=30)).isoformat()},
                headers=headers,
            )
            assert too_wide.status_code == 422
            replay = await client.get(
                "/api/v1/agent-activity/snapshot",
                params={"at": (base + timedelta(minutes=12)).isoformat()},
                headers=headers,
            )
            assert replay.status_code == 200, replay.text
            future = await client.get(
                "/api/v1/agent-activity/snapshot",
                params={"at": (now + timedelta(hours=1)).isoformat()},
                headers=headers,
            )
            assert future.status_code == 422
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AgentDemand).where(AgentDemand.id == demand_id))
            await db.execute(delete(AgentActivityEvent).where(AgentActivityEvent.agent_id == worker_id))
            await db.execute(delete(Agent).where(Agent.id.in_([worker_id, sender_id])))
            await db.execute(delete(User).where(User.username == username))
            await db.commit()
