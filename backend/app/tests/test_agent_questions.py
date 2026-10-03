"""Agents asking Marcelo: quiet hours, Telegram delivery and the answer's way
back as a Messages Task.

These tests share the production database (and its running backend, whose
routine loop delivers questions and whose dispatch worker runs due tasks).
So nothing here may become due for real: questions are created with
`notify_after` one year ahead and answer tasks are scheduled one year ahead;
the delivery pass is run with an explicit future `now`, a fake sender and
`ids=` limited to the test's own question.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api.routes import operations as ops
from app.core import agent_questions as aq
from app.core.config import settings
from app.core.deps import get_current_admin
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.notification import Notification
from app.db.models.operations import AgentQuestion

UTC = timezone.utc
FAR = datetime.now(UTC) + timedelta(days=365)


# ------------------------------------------------------------ quiet hours


@pytest.mark.parametrize(
    ("utc_now", "urgent", "expected"),
    [
        # 14:00 in São Paulo (UTC-3): daytime, goes now.
        (datetime(2026, 10, 3, 17, 0, tzinfo=UTC), False, datetime(2026, 10, 3, 17, 0, tzinfo=UTC)),
        # 23:30 local: waits for 07:00 the next day (10:00 UTC).
        (datetime(2026, 10, 4, 2, 30, tzinfo=UTC), False, datetime(2026, 10, 4, 10, 0, tzinfo=UTC)),
        # 03:00 local: waits for 07:00 the same day.
        (datetime(2026, 10, 3, 6, 0, tzinfo=UTC), False, datetime(2026, 10, 3, 10, 0, tzinfo=UTC)),
        # Urgent ignores the window.
        (datetime(2026, 10, 3, 6, 0, tzinfo=UTC), True, datetime(2026, 10, 3, 6, 0, tzinfo=UTC)),
        # 07:00 sharp is already awake.
        (datetime(2026, 10, 3, 10, 0, tzinfo=UTC), False, datetime(2026, 10, 3, 10, 0, tzinfo=UTC)),
    ],
)
def test_notify_after_respects_quiet_hours(utc_now, urgent, expected):
    assert aq.notify_after_for(utc_now, urgent) == expected


# ------------------------------------------------------------ fixtures


async def _make_agent(prefix: str) -> Agent:
    row = Agent(name=f"test-q-{prefix}-{uuid.uuid4().hex[:6]}", profile_slug=f"tq{prefix}{uuid.uuid4().hex[:6]}")
    async with AsyncSessionLocal() as db:
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


@pytest_asyncio.fixture
async def agents():
    asker, relay = await _make_agent("a"), await _make_agent("r")
    yield asker, relay
    ids = [asker.id, relay.id]
    async with AsyncSessionLocal() as db:
        questions = (await db.execute(select(AgentQuestion).where(AgentQuestion.agent_id.in_(ids)))).scalars().all()
        keys = [k for q in questions for k in (f"agent-question:{q.id}", f"agent-question-answered:{q.id}")]
        await db.execute(delete(AgentQuestion).where(AgentQuestion.agent_id.in_(ids)))
        await db.execute(delete(Notification).where(Notification.event_key.in_(keys)))
        await db.execute(
            delete(AgentDemand).where(AgentDemand.target_agent_id.in_(ids) | AgentDemand.from_agent_id.in_(ids))
        )
        await db.execute(delete(Agent).where(Agent.id.in_(ids)))
        await db.commit()


@pytest.fixture
def never_due(monkeypatch, agents):
    """Questions wait a year; answers dispatch in a year; relay is the test
    relay agent with a fake chat (never Athos's real one)."""
    _, relay = agents
    monkeypatch.setattr(aq, "notify_after_for", lambda now, urgent: FAR)

    async def fake_relay(db, asker):
        return relay, "test-chat"

    monkeypatch.setattr(aq, "resolve_relay", fake_relay)
    real_record = aq.record_answer

    async def deferred(db, question, answer, **kwargs):
        kwargs["dispatch_at"] = FAR
        return await real_record(db, question, answer, **kwargs)

    monkeypatch.setattr(aq, "record_answer", deferred)


@pytest_asyncio.fixture
async def client():
    app = FastAPI()
    app.include_router(ops.router)
    app.dependency_overrides[get_current_admin] = lambda: type("Admin", (), {"username": "tester"})()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
    ) as ac:
        yield ac


async def _ask(client, asker: Agent, **extra) -> dict:
    body = {"agent": asker.profile_slug, "question": "Posso arquivar o perfil prometheus?", **extra}
    response = await client.post("/api/v1/operations/agent-questions", json=body)
    assert response.status_code == 201, response.text
    return response.json()


# ------------------------------------------------------------ asking


async def test_ask_records_question_and_notifies(client, agents, never_due):
    asker, relay = agents
    q = await _ask(client, asker, blocking=True, recommendation="Sim, está estacionado.")
    assert q["status"] == "pending"
    assert q["relay_agent_id"] == str(relay.id)
    assert q["telegram_sent_at"] is None
    async with AsyncSessionLocal() as db:
        note = (
            await db.execute(select(Notification).where(Notification.event_key == f"agent-question:{q['id']}"))
        ).scalar_one()
        assert note.severity == "warning"  # blocking


async def test_ask_requires_bridge_token(client, agents, never_due):
    asker, _ = agents
    response = await client.post(
        "/api/v1/operations/agent-questions",
        json={"agent": asker.profile_slug, "question": "?"},
        headers={"X-Bridge-Token": "wrong"},
    )
    assert response.status_code == 401


# ------------------------------------------------------------ delivery


async def test_delivery_pass_sends_once_and_retries_failures(client, agents, never_due):
    asker, relay = agents
    q = await _ask(client, asker)
    qid = uuid.UUID(q["id"])
    later = FAR + timedelta(minutes=1)

    async def failing(profile, target, text):
        raise RuntimeError("bridge down")

    async with AsyncSessionLocal() as db:
        assert await aq.run_question_delivery_pass(db, now=later, send=failing, ids=[qid]) == 0
    async with AsyncSessionLocal() as db:
        row = await db.get(AgentQuestion, qid)
        assert row.telegram_sent_at is None and "bridge down" in row.telegram_error

    sent: list[tuple] = []

    async def fake_send(profile, target, text):
        sent.append((profile, target, text))

    async with AsyncSessionLocal() as db:
        assert await aq.run_question_delivery_pass(db, now=later, send=fake_send, ids=[qid]) == 1
    async with AsyncSessionLocal() as db:
        assert await aq.run_question_delivery_pass(db, now=later, send=fake_send, ids=[qid]) == 0

    assert len(sent) == 1
    profile, target, text = sent[0]
    assert target == "telegram:test-chat"
    assert profile is None  # the test relay has no telegram_account
    assert f"Pergunta #{q['number']}" in text and asker.name in text
    async with AsyncSessionLocal() as db:
        row = await db.get(AgentQuestion, qid)
        assert row.telegram_sent_at is not None and row.telegram_error is None


async def test_question_not_yet_due_is_not_sent(client, agents, never_due):
    asker, _ = agents
    q = await _ask(client, asker)
    sent = []

    async def fake_send(*args):
        sent.append(args)

    async with AsyncSessionLocal() as db:
        await aq.run_question_delivery_pass(db, now=FAR - timedelta(hours=1), send=fake_send, ids=[uuid.UUID(q["id"])])
    assert sent == []


# ------------------------------------------------------------ answering


async def test_relay_answer_becomes_task_for_the_asker(client, agents, never_due):
    asker, relay = agents
    q = await _ask(client, asker, blocking=True)
    url = f"/api/v1/operations/agent-questions/{q['number']}/relay-answer"

    # Only the agent whose Telegram carried the question may record a reply.
    stranger = await client.post(url, json={"agent": asker.profile_slug, "answer": "sim"})
    assert stranger.status_code == 403

    response = await client.post(url, json={"agent": relay.profile_slug, "answer": "Sim, pode arquivar."})
    assert response.status_code == 200, response.text
    answered = response.json()
    assert answered["status"] == "answered"
    assert answered["answered_via"] == "telegram"

    async with AsyncSessionLocal() as db:
        task = await db.get(AgentDemand, uuid.UUID(answered["reply_demand_id"]))
        assert task.origin_type == "task"
        assert task.target_agent_id == asker.id and task.from_agent_id == relay.id
        assert "Sim, pode arquivar." in task.body and "Retome o trabalho" in task.body
        assert task.scheduled_at > datetime.now(UTC) + timedelta(days=300)

    again = await client.post(url, json={"agent": relay.profile_slug, "answer": "não"})
    assert again.status_code == 409


async def test_screen_answer_and_cancel(client, agents, never_due):
    asker, _ = agents
    first = await _ask(client, asker)
    second = await _ask(client, asker)

    answered = await client.post(f"/api/v1/operations/questions/{first['id']}:answer", json={"answer": "Não."})
    assert answered.status_code == 200
    assert answered.json()["answered_via"] == "screen" and answered.json()["answered_by"] == "tester"

    cancelled = await client.post(f"/api/v1/operations/questions/{second['id']}:cancel")
    assert cancelled.json()["status"] == "cancelled"
    assert (await client.post(f"/api/v1/operations/questions/{second['id']}:answer", json={"answer": "x"})).status_code == 409

    listed = await client.get("/api/v1/operations/agent-questions", params={"agent": asker.profile_slug})
    assert {item["status"] for item in listed.json()} == {"answered", "cancelled"}
