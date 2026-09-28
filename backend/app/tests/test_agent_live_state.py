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
