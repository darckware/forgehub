"""Phase 5 of Agent Activity: runtime alerts in the severity inbox."""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import delete

from app.core import agent_activity_alerts as alerts
from app.core.forgerouter_sync import ForgeRouterHealth
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.agent_activity_event import AgentActivityEvent

NOW = datetime(2026, 9, 28, 15, 0, tzinfo=timezone.utc)


def _agent(name="Athos", slug="athos", runtime="hermes"):
    return SimpleNamespace(
        id=uuid.uuid4(), name=name, profile_slug=slug, runtime_type=runtime,
        effective_home_path=None, is_active=True,
    )


def _turn(minutes_ago, **extra):
    return SimpleNamespace(
        id=uuid.uuid4(), occurred_at=NOW - timedelta(minutes=minutes_ago), turn_id="t1",
        session_id="s1", platform="telegram", model="m", **extra,
    )


def test_stuck_turn_warns_then_errors_and_ignores_ended_or_recent_turns():
    agent = _agent()
    assert alerts.stuck_turn_incidents([(agent, _turn(5), False)], now=NOW) == []
    assert alerts.stuck_turn_incidents([(agent, _turn(20), True)], now=NOW) == []
    warning = alerts.stuck_turn_incidents([(agent, _turn(12), False)], now=NOW)
    assert [(i.kind, i.severity, i.error_code) for i in warning] == [("turn_stuck", "warning", "turn_stuck")]
    error = alerts.stuck_turn_incidents([(agent, _turn(45), False)], now=NOW)
    assert [(i.severity, i.error_code) for i in error] == [("error", "turn_abandoned")]
    assert error[0].affected_agent_id == agent.id and error[0].canonical_path == f"/agents/{agent.id}"


def test_adapter_fatal_is_critical_and_unknown_bridge_gives_no_verdict(monkeypatch):
    athos, lara, atlas = _agent(), _agent("Lara", "lara"), _agent("Atlas", "atlas")
    porthus = _agent("Porthus", "porthus", runtime="claude")
    configured = {"athos", "lara", "porthus"}
    monkeypatch.setattr(
        alerts.agent_telegram, "read_profile_telegram_config",
        lambda home, runtime, slug: (slug in configured, None),
    )
    states = {"athos": "fatal", "lara": "connected", "atlas": "fatal"}
    incidents = alerts.adapter_incidents([athos, lara, atlas, porthus], states, now=NOW)
    # Atlas has no Telegram configured; Porthus isn't served by the gateway.
    assert [(i.affected_agent_id, i.severity, i.error_code) for i in incidents] == [
        (athos.id, "critical", "telegram_fatal"),
    ]
    missing = alerts.adapter_incidents([lara], {}, now=NOW)
    assert [(i.severity, i.error_code) for i in missing] == [("error", "telegram_not_running")]
    assert alerts.adapter_incidents([athos], None, now=NOW) == []


def test_cron_failing_and_overdue():
    athos = _agent()
    jobs = [
        SimpleNamespace(profile="athos", id="j1", name="backup", health="error", last_run_at=NOW.isoformat(),
                        next_run_at=None, last_error="exit 1", last_status="error"),
        SimpleNamespace(profile="themis", id="j2", name="audit", health="overdue", last_run_at=None,
                        next_run_at=(NOW - timedelta(hours=2)).isoformat(), last_error=None, last_status="ok"),
        SimpleNamespace(profile="athos", id="j3", name="fine", health="ok", last_run_at=None,
                        next_run_at=None, last_error=None, last_status="ok"),
    ]
    incidents = alerts.cron_incidents([athos], jobs, now=NOW)
    assert [(i.key, i.severity, i.affected_agent_id) for i in incidents] == [
        ("cron_failing:athos:j1", "error", athos.id),
        ("cron_failing:themis:j2", "warning", None),
    ]
    assert incidents[0].summary == "exit 1" and incidents[0].canonical_path == "/crons"
    assert alerts.cron_incidents([athos], None, now=NOW) == []


def _health(name, **extra):
    base = dict(agent_name=name, errors_recent=0, last_error_type=None, last_error_at=None, tokens_today=0,
                tokens_prev_avg=0.0, cost_today=0.0, cost_prev_avg=0.0)
    base.update(extra)
    return ForgeRouterHealth(**base)


def test_provider_errors_and_usage_anomalies():
    lara, atlas, athos = _agent("Lara", "lara"), _agent("Atlas", "atlas"), _agent()
    rows = [
        _health("Lara", errors_recent=6, last_error_type="http_503", last_error_at=NOW),
        _health("Atlas", errors_recent=2, tokens_today=345_698, tokens_prev_avg=263_187),  # normal day
        _health("Athos", tokens_today=900_000, tokens_prev_avg=100_000),
        _health("Hindsight", errors_recent=10, tokens_today=256_396, tokens_prev_avg=13_867),  # a service
    ]
    incidents = alerts.forgerouter_incidents([lara, atlas, athos], rows, now=NOW)
    assert [(i.kind, i.affected_agent_id, i.severity, i.error_code) for i in incidents] == [
        ("provider_error", lara.id, "warning", "http_503"),
        ("usage_anomaly", athos.id, "warning", "token_anomaly"),
    ]
    assert "9×" in incidents[1].title
    cost = alerts.forgerouter_incidents([athos], [_health("Athos", cost_today=6.0, cost_prev_avg=1.0)], now=NOW)
    assert [(i.severity, i.error_code) for i in cost] == [("error", "cost_anomaly")]
    assert alerts.forgerouter_incidents([athos], None, now=NOW) == []


@pytest.mark.asyncio
async def test_a_hung_turn_reaches_the_inbox(monkeypatch):
    """Plan acceptance: a stuck turn generates an incident, from the real event table."""
    async def unavailable():
        return None

    monkeypatch.setattr(alerts, "_cached", lambda key, loader: unavailable())
    suffix = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        agent = Agent(name=f"Alert Worker {suffix}", agent_type="executor", runtime_type="hermes",
                      profile_slug=f"alert-{suffix}")
        db.add(agent)
        await db.flush()
        db.add_all([
            AgentActivityEvent(agent_id=agent.id, profile=agent.profile_slug, kind="turn_started",
                               occurred_at=now - timedelta(minutes=50), turn_id="done", delivery_id=f"al-1-{suffix}"),
            AgentActivityEvent(agent_id=agent.id, profile=agent.profile_slug, kind="turn_ended", status="completed",
                               occurred_at=now - timedelta(minutes=49), turn_id="done", delivery_id=f"al-2-{suffix}"),
            AgentActivityEvent(agent_id=agent.id, profile=agent.profile_slug, kind="turn_started", platform="telegram",
                               occurred_at=now - timedelta(minutes=14), turn_id="hung", delivery_id=f"al-3-{suffix}"),
        ])
        await db.commit()
        agent_id = agent.id
    try:
        async with AsyncSessionLocal() as db:
            agent = await db.get(Agent, agent_id)
            incidents = await alerts.build_runtime_incidents(db, [agent], now=now)
        assert [(i.kind, i.severity, i.affected_agent_id) for i in incidents] == [
            ("turn_stuck", "warning", agent_id),
        ]
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AgentActivityEvent).where(AgentActivityEvent.agent_id == agent_id))
            await db.execute(delete(Agent).where(Agent.id == agent_id))
            await db.commit()
