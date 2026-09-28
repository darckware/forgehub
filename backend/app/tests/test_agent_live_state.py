"""Agent live state: webhook ingestion (metadata only) and state derivation."""
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.agent_activity import load_live_states
from app.core.agent_live_state import (
    EventView,
    classify_counterpart,
    derive_live_state,
    normalize_hermes_hook,
    verify_signature,
)
from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.agent_activity_event import AgentActivityEvent
from app.main import app

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)


def _ev(kind, minutes_ago, **kw):
    return EventView(kind=kind, occurred_at=NOW - timedelta(minutes=minutes_ago), **kw)


def test_executing_while_a_tool_is_open():
    state = derive_live_state(
        [
            _ev("turn_started", 3, turn_id="t1", platform="telegram", counterpart_kind="owner", model="m"),
            _ev("tool_started", 1, turn_id="t1", tool_call_id="c1", tool_name="terminal"),
        ],
        now=NOW,
    )
    assert state.state == "executing"
    assert state.tool_name == "terminal"
    assert state.platform == "telegram" and state.counterpart_kind == "owner"
    assert state.turns_last_hour == 1 and state.tools_last_hour == 1


def test_thinking_after_the_tool_returns():
    state = derive_live_state(
        [
            _ev("turn_started", 3, turn_id="t1"),
            _ev("tool_started", 2, turn_id="t1", tool_call_id="c1", tool_name="terminal"),
            _ev("tool_ended", 1, turn_id="t1", tool_call_id="c1", status="ok"),
        ],
        now=NOW,
    )
    assert state.state == "thinking"
    assert state.since == NOW - timedelta(minutes=1)


def test_conversing_right_after_a_completed_turn_then_idle():
    events = [_ev("turn_started", 3, turn_id="t1"), _ev("turn_ended", 1, turn_id="t1", status="completed")]
    assert derive_live_state(events, now=NOW).state == "conversing"
    assert derive_live_state(events, now=NOW + timedelta(minutes=5)).state == "idle"


def test_failed_turn_is_degraded_with_its_reason():
    state = derive_live_state(
        [
            _ev("turn_started", 3, turn_id="t1"),
            _ev("turn_ended", 1, turn_id="t1", status="failed", error_type="provider_error"),
        ],
        now=NOW,
    )
    assert state.state == "degraded" and state.reason == "provider_error"
    assert state.failures_last_hour == 1


def test_an_abandoned_turn_does_not_read_thinking_forever():
    state = derive_live_state([_ev("turn_started", 45, turn_id="t1")], now=NOW)
    assert state.state == "idle"


def test_workspace_turn_and_queue_when_the_runtime_is_quiet():
    assert derive_live_state([], now=NOW, workspace_turn_started_at=NOW).state == "thinking"
    waiting = derive_live_state([], now=NOW, pending_count=2)
    assert waiting.state == "waiting" and waiting.pending_count == 2


def test_counterpart_is_masked_and_owner_detected():
    assert classify_counterpart("telegram", "1085550644", "1085550644") == ("owner", None)
    assert classify_counterpart("whatsapp", "5511999991234", "1085550644") == ("human", "···1234")
    assert classify_counterpart("cron", None, None) == ("system", None)
    assert classify_counterpart("cli", None, None) == ("owner", None)


def test_normalize_keeps_no_conversation_content():
    body = {
        "hook_event_name": "pre_llm_call",
        "profile": "athos",
        "session_id": "s1",
        "tool_name": None,
        "extra": {
            "turn_id": "t1",
            "platform": "whatsapp",
            "sender_id": "5511999991234",
            "model": "claude-sonnet",
            "user_message": "SEGREDO do cliente",
            "conversation_history": [{"role": "user", "content": "SEGREDO do cliente"}],
        },
        "delivery_id": "d1",
        "timestamp": "2026-09-28T12:00:00+00:00",
    }
    values = normalize_hermes_hook(body, home_chat=None)
    assert values["kind"] == "turn_started" and values["counterpart_ref"] == "···1234"
    assert "SEGREDO" not in json.dumps(values, default=str)
    assert normalize_hermes_hook({**body, "hook_event_name": "transform_llm_output"}, home_chat=None) is None


def test_signature_check():
    body = b'{"a": 1}'
    sig = "sha256=" + hmac.new(b"k", body, hashlib.sha256).hexdigest()
    assert verify_signature("k", body, sig)
    assert not verify_signature("k", body, "sha256=00")
    assert not verify_signature("", body, sig)


def _signed(secret: str, payload: dict) -> tuple[bytes, dict]:
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return body, {"X-Hermes-Signature-256": sig, "Content-Type": "application/json"}


@pytest.mark.asyncio
async def test_ingest_endpoint_records_once_and_drives_live_state(monkeypatch):
    secret = "test-activity-secret"
    monkeypatch.setattr(settings, "AGENT_ACTIVITY_WEBHOOK_SECRET", secret)
    suffix = uuid.uuid4().hex[:8]
    slug = f"live-test-{suffix}"
    async with AsyncSessionLocal() as db:
        agent = Agent(name=f"Live State Test {suffix}", agent_type="executor", runtime_type="hermes", profile_slug=slug)
        db.add(agent)
        await db.commit()
        agent_id = agent.id

    now = datetime.now(timezone.utc)
    turn = {
        "hook_event_name": "pre_llm_call", "profile": slug, "session_id": "s1",
        "extra": {"turn_id": "t1", "platform": "telegram", "sender_id": "42", "model": "m",
                  "conversation_history": [{"content": "privado"}]},
        "delivery_id": f"d-turn-{suffix}", "timestamp": (now - timedelta(seconds=20)).isoformat(),
    }
    tool = {
        "hook_event_name": "pre_tool_call", "profile": slug, "session_id": "s1", "tool_name": "terminal",
        "tool_input": {"command": "rm -rf segredo"},
        "extra": {"turn_id": "t1", "tool_call_id": "c1"},
        "delivery_id": f"d-tool-{suffix}", "timestamp": now.isoformat(),
    }
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            body, headers = _signed(secret, turn)
            bad = await client.post("/api/v1/agent-activity/events", content=body,
                                    headers={**headers, "X-Hermes-Signature-256": "sha256=00"})
            assert bad.status_code == 401
            first = await client.post("/api/v1/agent-activity/events", content=body, headers=headers)
            assert first.status_code == 202 and first.json() == {"recorded": True}
            retry = await client.post("/api/v1/agent-activity/events", content=body, headers=headers)
            assert retry.json() == {"recorded": False}
            body, headers = _signed(secret, tool)
            assert (await client.post("/api/v1/agent-activity/events", content=body, headers=headers)).json() == {
                "recorded": True
            }

        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(AgentActivityEvent).where(AgentActivityEvent.profile == slug)
            )).scalars().all()
            assert len(rows) == 2 and all(r.agent_id == agent_id for r in rows)
            assert "segredo" not in json.dumps([vars(r) for r in rows], default=str).lower()
            agent = await db.get(Agent, agent_id)
            live = (await load_live_states(db, [agent], now=datetime.now(timezone.utc)))[agent_id]
            assert live.state == "executing" and live.tool_name == "terminal"
            assert live.platform == "telegram" and live.counterpart_kind == "human"
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AgentActivityEvent).where(AgentActivityEvent.profile == slug))
            await db.execute(delete(Agent).where(Agent.id == agent_id))
            await db.commit()


def test_broadcaster_coalesces_and_unsubscribes():
    from app.core.agent_activity_stream import ActivityBroadcaster

    hub = ActivityBroadcaster()
    with hub.subscribe() as queue:
        hub.publish()
        hub.publish()
        assert queue.qsize() == 2 and hub.subscriber_count == 1
    assert hub.subscriber_count == 0
    hub.publish()  # no subscribers: a no-op, never an error


def test_bucket_counts_places_events_oldest_first():
    from app.core.agent_activity_stream import _bucket_counts

    now = NOW
    times = [now - timedelta(minutes=59), now - timedelta(minutes=1), now - timedelta(seconds=10), now - timedelta(hours=2)]
    counts = _bucket_counts(times, now=now, buckets=12, width=timedelta(minutes=5))
    assert counts[0] == 1 and counts[-1] == 2 and sum(counts) == 3


@pytest.mark.asyncio
async def test_live_snapshot_reports_state_spark_and_pulse(monkeypatch):
    from app.core import agent_activity_stream

    async def no_forgerouter():
        return None

    monkeypatch.setattr(agent_activity_stream, "_cached_forgerouter_usage", no_forgerouter)
    suffix = uuid.uuid4().hex[:8]
    slug = f"live-snap-{suffix}"
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        agent = Agent(name=f"Live Snapshot Test {suffix}", agent_type="executor", runtime_type="hermes", profile_slug=slug)
        db.add(agent)
        await db.flush()
        db.add_all([
            AgentActivityEvent(agent_id=agent.id, profile=slug, runtime="hermes", kind="turn_started",
                               occurred_at=now - timedelta(seconds=30), turn_id="t1", platform="cron",
                               counterpart_kind="system", delivery_id=f"snap-a-{suffix}"),
            AgentActivityEvent(agent_id=agent.id, profile=slug, runtime="hermes", kind="tool_started",
                               occurred_at=now - timedelta(seconds=5), turn_id="t1", tool_call_id="c1",
                               tool_name="web_search", delivery_id=f"snap-b-{suffix}"),
        ])
        await db.commit()
        agent_id = agent.id
    try:
        async with AsyncSessionLocal() as db:
            snapshot = await agent_activity_stream.build_live_snapshot(db, now=now)
        item = next(i for i in snapshot.agents if i.agent_id == agent_id)
        assert item.live.state == "executing" and item.live.tool_name == "web_search"
        assert sum(item.spark) == 2 and len(item.spark) == 12
        assert snapshot.pulse.agents_in_turn >= 1 and snapshot.pulse.turns_last_hour >= 1
        assert snapshot.pulse.cost_today is None  # ForgeRouter down reads "unknown", not zero
        assert len(snapshot.pulse.turns_per_minute) == 60
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AgentActivityEvent).where(AgentActivityEvent.profile == slug))
            await db.execute(delete(Agent).where(Agent.id == agent_id))
            await db.commit()


@pytest.mark.asyncio
async def test_stream_requires_authentication():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/v1/agent-activity/stream")).status_code == 401


@pytest.mark.asyncio
async def test_external_agent_is_on_the_board_only_while_messages_runs_it(monkeypatch):
    from app.core import agent_activity_stream
    from app.db.models.demand import AgentDemand

    async def no_forgerouter():
        return None

    monkeypatch.setattr(agent_activity_stream, "_cached_forgerouter_usage", no_forgerouter)
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        external = Agent(name=f"External Exec {suffix}", agent_type="executor", runtime_type="codex",
                         profile_slug=f"ext-{suffix}")
        sender = Agent(name=f"External Sender {suffix}", agent_type="executor", runtime_type="hermes",
                       profile_slug=f"ext-sender-{suffix}")
        db.add_all([external, sender])
        await db.commit()
        external_id, sender_id = external.id, sender.id
    try:
        async with AsyncSessionLocal() as db:
            snapshot = await agent_activity_stream.build_live_snapshot(db)
        assert all(item.agent_id != external_id for item in snapshot.agents)

        async with AsyncSessionLocal() as db:
            demand = AgentDemand(
                from_agent=f"ext-sender-{suffix}", from_agent_id=sender_id, target_agent_id=external_id,
                subject="External run", body="x", origin_type="task", dispatch_status="running",
            )
            db.add(demand)
            await db.commit()
            number = demand.number
        async with AsyncSessionLocal() as db:
            snapshot = await agent_activity_stream.build_live_snapshot(db)
        item = next(item for item in snapshot.agents if item.agent_id == external_id)
        assert item.live.state == "executing" and item.live.source == "messages"
        assert item.live.message_number == number and item.live.counterpart_kind == "agent"
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AgentDemand).where(AgentDemand.target_agent_id == external_id))
            await db.execute(delete(Agent).where(Agent.id.in_([external_id, sender_id])))
            await db.commit()


@pytest.mark.asyncio
async def test_snapshot_links_show_conversations_and_messages(monkeypatch):
    from app.core import agent_activity_stream
    from app.db.models.demand import AgentDemand

    async def no_forgerouter():
        return None

    monkeypatch.setattr(agent_activity_stream, "_cached_forgerouter_usage", no_forgerouter)
    suffix = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        a = Agent(name=f"Link A {suffix}", agent_type="executor", runtime_type="hermes", profile_slug=f"link-a-{suffix}")
        b = Agent(name=f"Link B {suffix}", agent_type="executor", runtime_type="hermes", profile_slug=f"link-b-{suffix}")
        db.add_all([a, b])
        await db.flush()
        db.add_all([
            AgentActivityEvent(agent_id=a.id, profile=a.profile_slug, runtime="hermes", kind="turn_started",
                               occurred_at=now - timedelta(seconds=20), turn_id="t1", platform="telegram",
                               counterpart_kind="owner", delivery_id=f"link-1-{suffix}"),
            AgentDemand(from_agent=a.profile_slug, from_agent_id=a.id, target_agent_id=b.id,
                        subject="handoff", body="x", origin_type="task", dispatch_status="running"),
        ])
        await db.commit()
        a_id, b_id = a.id, b.id
    try:
        async with AsyncSessionLocal() as db:
            snapshot = await agent_activity_stream.build_live_snapshot(db, now=now)
        mine = [link for link in snapshot.links if link.target_agent_id in (a_id, b_id)]
        conversation = next(link for link in mine if link.kind == "conversation")
        assert conversation.source_type == "owner" and conversation.channel == "telegram" and conversation.active
        message = next(link for link in mine if link.kind == "message")
        assert message.source_agent_id == a_id and message.target_agent_id == b_id and message.active
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AgentDemand).where(AgentDemand.target_agent_id == b_id))
            await db.execute(delete(AgentActivityEvent).where(AgentActivityEvent.agent_id == a_id))
            await db.execute(delete(Agent).where(Agent.id.in_([a_id, b_id])))
            await db.commit()
