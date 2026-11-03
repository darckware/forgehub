"""A.2: routine occurrences on the Agent Activity timeline, and the missed-routine alert.

Nothing here runs a routine: rows are fixtures (AgentRoutine/AgentRoutineRun written
directly) and the generator pass is never called.
"""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core import agent_activity_alerts as alerts
from app.core.agent_activity_routines import (
    classify_occurrences,
    collect_routine_occurrences,
    routine_missed_incidents,
)
from app.core.agent_activity_timeline import build_timeline
from app.core.security import create_access_token, hash_password
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.operations import AgentRoutine, AgentRoutineRun
from app.db.models.user import User
from app.main import app

NOW = datetime(2026, 11, 3, 15, 0, tzinfo=timezone.utc)


def _routine(**extra):
    base = {
        "id": uuid.uuid4(), "agent_id": uuid.uuid4(), "title": "Briefing", "kind": "report",
        "schedule": "0 * * * *", "timezone": "UTC", "deadline_minutes": 30, "enabled": True,
        "created_at": NOW - timedelta(days=10),
    }
    base.update(extra)
    return SimpleNamespace(**base)


def _run(routine, at, status, **extra):
    base = {
        "id": uuid.uuid4(), "routine_id": routine.id, "occurrence_at": at, "status": status,
        "detail": None, "finished_at": None, "duration_ms": None, "demand_id": None,
    }
    base.update(extra)
    return SimpleNamespace(**base)


def _by_instant(items):
    return {item.occurrence_at: item.outcome for item in items}


def test_outcomes_from_runs_and_schedule():
    routine = _routine()
    h = lambda n: NOW.replace(minute=0) + timedelta(hours=n)  # noqa: E731
    runs = [
        (_run(routine, h(-4), "completed", finished_at=h(-4) + timedelta(minutes=3), duration_ms=180_000), None),
        (_run(routine, h(-3), "failed", detail="boom"), None),
        (_run(routine, h(-2), "missed", detail="occurrence window closed before generation"), None),
        (_run(routine, h(-1), "skipped_budget"), None),
    ]
    items = classify_occurrences(
        [routine], runs, start=h(-6), end=NOW, now=NOW, horizon=NOW + timedelta(hours=24)
    )
    outcomes = _by_instant(items)
    assert outcomes[h(-4)] == "done"
    assert outcomes[h(-3)] == "failed"
    assert outcomes[h(-2)] == "missed"
    assert outcomes[h(-1)] == "skipped"
    # no run at all, deadline (30 min) long gone: missed, computed, not recorded
    assert outcomes[h(-6)] == "missed" and outcomes[h(-5)] == "missed"
    computed = next(item for item in items if item.occurrence_at == h(-5))
    assert computed.recorded is False and computed.run_id is None
    # the current hour (15:00) is due right now, inside its deadline
    assert outcomes[h(0)] == "pending"
    # next 24 h: scheduled, oldest first
    future = [item for item in items if item.outcome == "scheduled"]
    assert len(future) == 24 and future[0].occurrence_at == h(1) and future[-1].occurrence_at == h(24)
    assert all(item.deadline_at - item.occurrence_at == timedelta(minutes=30) for item in items)


def test_one_entry_per_routine_and_instant():
    routine = _routine()
    at = NOW.replace(minute=0) - timedelta(hours=2)
    run = _run(routine, at, "completed")
    # the same run read twice (e.g. two joins), plus the schedule computing that instant
    items = classify_occurrences(
        [routine], [(run, None), (run, None)], start=at - timedelta(minutes=1), end=NOW,
        now=NOW, horizon=NOW,
    )
    keys = [item.key for item in items]
    assert len(keys) == len(set(keys))
    assert [item.outcome for item in items if item.occurrence_at == at] == ["done"]


def test_scheduled_run_past_its_deadline_never_started_is_missed():
    routine = _routine(deadline_minutes=20)
    at = NOW - timedelta(minutes=45)
    queued = SimpleNamespace(number=4242, dispatch_status=None)
    started = SimpleNamespace(number=4243, dispatch_status="running")
    items = classify_occurrences(
        [routine],
        [(_run(routine, at, "scheduled"), queued), (_run(routine, at + timedelta(minutes=5), "scheduled"), started)],
        start=NOW - timedelta(hours=1), end=NOW, now=NOW, horizon=NOW,
    )
    by_at = {item.occurrence_at: item for item in items}
    assert by_at[at].outcome == "missed" and by_at[at].message_number == 4242
    # its Messages run already started: the sync pass is just behind, not a miss
    assert by_at[at + timedelta(minutes=5)].outcome == "running"


def test_occurrences_follow_the_routine_timezone():
    # 08:00 in Sao Paulo (UTC-3, no DST since 2019) is 11:00 UTC
    routine = _routine(schedule="0 8 * * *", timezone="America/Sao_Paulo", deadline_minutes=60)
    now = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)
    items = classify_occurrences(
        [routine], [], start=now - timedelta(hours=24), end=now, now=now, horizon=now + timedelta(hours=24)
    )
    assert _by_instant(items) == {
        datetime(2026, 11, 2, 11, 0, tzinfo=timezone.utc): "missed",
        datetime(2026, 11, 3, 11, 0, tzinfo=timezone.utc): "scheduled",
    }
    assert {item.timezone for item in items} == {"America/Sao_Paulo"}


def test_disabled_or_new_routine_owes_nothing_but_keeps_its_history():
    disabled = _routine(enabled=False)
    at = NOW.replace(minute=0) - timedelta(hours=2)
    items = classify_occurrences(
        [disabled], [(_run(disabled, at, "completed"), None)], start=NOW - timedelta(hours=6),
        end=NOW, now=NOW, horizon=NOW + timedelta(hours=24),
    )
    # the recorded run stays (history), nothing is computed missed, nothing scheduled
    assert _by_instant(items) == {at: "done"}
    fresh = _routine(created_at=NOW - timedelta(minutes=90))
    items = classify_occurrences(
        [fresh], [], start=NOW - timedelta(hours=6), end=NOW, now=NOW, horizon=NOW,
    )
    # only occurrences after it was created can be missed
    assert sorted(_by_instant(items)) == [NOW - timedelta(hours=1), NOW]


def test_missed_alert_is_one_per_routine_and_never_a_channel_alert():
    agent = SimpleNamespace(id=uuid.uuid4(), name="Porthus", runtime_type="claude", profile_slug="porthus",
                            effective_home_path=None, is_active=True)
    routine = _routine(agent_id=agent.id)
    h = lambda n: NOW.replace(minute=0) + timedelta(hours=n)  # noqa: E731
    items = classify_occurrences(
        [routine], [(_run(routine, h(-1), "completed"), None)], start=h(-4), end=NOW, now=NOW, horizon=NOW,
    )
    incidents = routine_missed_incidents(items, {agent.id: agent}, now=NOW)
    assert len(incidents) == 1
    incident = incidents[0]
    assert incident.kind == "routine_missed" and incident.affected_agent_id == agent.id
    assert incident.source_id == routine.id and incident.occurred_at == h(-2)
    assert incident.key == f"routine_missed:{routine.id}:{h(-2).isoformat()}"
    assert "3" in incident.title  # h(-4), h(-3), h(-2)
    # same input twice: same key (the inbox dedups by key), no channel verdict at all
    assert routine_missed_incidents(items, {agent.id: agent}, now=NOW)[0].key == incident.key
    assert all(i.kind != "adapter_fatal" for i in incidents)
    assert alerts.adapter_incidents([agent], {}, now=NOW) == []  # no Telegram is not "offline"
    # nothing missed -> no alert
    ok = classify_occurrences([routine], [(_run(routine, NOW, "running"), None)], start=NOW, end=NOW, now=NOW, horizon=NOW)
    assert routine_missed_incidents(ok, {agent.id: agent}, now=NOW) == []


@pytest.mark.asyncio
async def test_timeline_and_inbox_show_a_missed_routine(monkeypatch):
    suffix = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    hour = now.replace(minute=0)
    async with AsyncSessionLocal() as db:
        agent = Agent(name=f"Routine Agent {suffix}", agent_type="executor", runtime_type="claude",
                      profile_slug=f"routine-{suffix}")
        admin = User(username=f"routine-admin-{suffix}", hashed_password=hash_password("x"), is_admin=True)
        db.add_all([agent, admin])
        await db.flush()
        routine = AgentRoutine(
            agent_id=agent.id, title=f"Hourly check {suffix}", instructions="fixture -- never dispatched",
            schedule="0 * * * *", timezone="America/Sao_Paulo", deadline_minutes=30,
            last_occurrence_at=hour - timedelta(hours=1),
        )
        db.add(routine)
        await db.flush()
        routine.created_at = now - timedelta(days=2)
        db.add_all([
            AgentRoutineRun(routine_id=routine.id, occurrence_at=hour - timedelta(hours=3), status="completed",
                            finished_at=hour - timedelta(hours=3) + timedelta(minutes=2)),
            AgentRoutineRun(routine_id=routine.id, occurrence_at=hour - timedelta(hours=2), status="failed",
                            detail="fixture failure"),
            # hour - 1h: no row at all, deadline gone -> missed (computed)
        ])
        await db.commit()
        agent_id, routine_id, username = agent.id, routine.id, admin.username

    try:
        async with AsyncSessionLocal() as db:
            view = await build_timeline(db, start=now - timedelta(hours=4), end=now, now=now, agent_id=agent_id)
            items = await collect_routine_occurrences(
                db, {agent_id}, start=now - timedelta(hours=4), end=now, now=now, horizon=now
            )
            monkeypatch.setattr(alerts, "_cached", _no_source)
            incidents = await alerts.build_runtime_incidents(db, [await db.get(Agent, agent_id)], now=now)

        mine = [item for item in view.routines if item.routine_id == routine_id]
        outcomes = {item.occurrence_at: item.outcome for item in mine}
        assert outcomes[hour - timedelta(hours=3)] == "done"
        assert outcomes[hour - timedelta(hours=2)] == "failed"
        assert outcomes[hour - timedelta(hours=1)] == "missed"
        assert sum(1 for item in mine if item.outcome == "scheduled") == 24
        assert view.routines_until == now + timedelta(hours=24)
        assert len({item.key for item in mine}) == len(mine)
        assert {item.occurrence_at for item in items} <= {item.occurrence_at for item in mine}
        # an agent with only routine occurrences keeps the response's lanes unchanged
        assert all(lane.agent_id != agent_id or lane.blocks for lane in view.lanes)

        missed = [i for i in incidents if i.kind == "routine_missed" and i.source_id == routine_id]
        assert len(missed) == 1 and missed[0].affected_agent_id == agent_id
        assert not [i for i in incidents if i.kind == "adapter_fatal" and i.affected_agent_id == agent_id]

        headers = {"Authorization": f"Bearer {create_access_token(username)}"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/agent-activity/timeline",
                params={"start": (now - timedelta(hours=4)).isoformat(), "agent_id": str(agent_id)},
                headers=headers,
            )
        assert response.status_code == 200, response.text
        body = response.json()
        assert {"lanes", "messages", "events", "truncated"} <= set(body)  # shape unchanged
        assert any(item["outcome"] == "missed" and item["routine_id"] == str(routine_id) for item in body["routines"])
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AgentRoutineRun).where(AgentRoutineRun.routine_id == routine_id))
            await db.execute(delete(AgentRoutine).where(AgentRoutine.id == routine_id))
            await db.execute(delete(Agent).where(Agent.id == agent_id))
            await db.execute(delete(User).where(User.username == username))
            await db.commit()


async def _no_source(key, loader):
    """Host sources (bridge, ForgeRouter, cron files) are unreachable in this test."""
    return None
