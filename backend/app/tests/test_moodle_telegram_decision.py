"""The owner decides a Moodle request with the Maia's Telegram buttons."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api.routes import moodle_approval
from app.core.config import settings
from app.core.demand_workflow import approval_fingerprint
from app.core.feedback import wants_telegram_reply
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.moodle_approval import MoodleApproval
from app.db.models.user import User
from app.main import app

URL = "/api/v1/personal/moodle-approvals/telegram-decision"
SECRET = "segredo-de-teste-" + "x" * 32
OWNER_CHAT = 123456789
HEADERS = {"X-Decision-Secret": SECRET}


@pytest_asyncio.fixture
async def request_row(monkeypatch, tmp_path):
    owner_id, agent_id, message_id, request_id = (uuid.uuid4() for _ in range(4))
    async with AsyncSessionLocal() as db:
        db.add(User(id=owner_id, username=f"dono-{owner_id.hex[:8]}", hashed_password="x", is_active=True, is_admin=True))
        db.add(Agent(id=agent_id, name=f"Maia {agent_id.hex[:8]}", profile_slug=f"maia-{agent_id.hex[:8]}"))
        await db.flush()
        db.add(AgentDemand(id=message_id, from_agent="maia", from_agent_id=agent_id, target_agent_id=agent_id,
                           subject="Moodle: solicitação de aprovação", body="Proposta.", origin_type="task",
                           status="new", requires_approval=True, approval_status="pending",
                           working_path=str(tmp_path)))
        await db.flush()
        db.add(MoodleApproval(message_id=message_id, request_id=request_id, source_agent_id=agent_id,
                              params_hash="a" * 64, state="pending",
                              expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        await db.commit()
    monkeypatch.setattr(settings, "MOODLE_APPROVAL_ENABLED", True)
    monkeypatch.setattr(settings, "MOODLE_APPROVAL_OWNER_ID", str(owner_id))
    monkeypatch.setattr(settings, "MOODLE_APPROVAL_WORKING_PATH", str(tmp_path))
    monkeypatch.setattr(settings, "MOODLE_APPROVAL_SOURCE_FILES", json.dumps({str(agent_id): str(tmp_path / "p.json")}))
    monkeypatch.setattr(settings, "MOODLE_APPROVAL_TELEGRAM_CHAT_ID", str(OWNER_CHAT))
    monkeypatch.setattr(settings, "MOODLE_TELEGRAM_DECISION_SECRET", SECRET)
    monkeypatch.setattr(moodle_approval, "_source", lambda *_: {"params_hash": "a" * 64})
    monkeypatch.setattr(moodle_approval, "wake_scheduled_dispatch", lambda: None)
    yield {"message_id": message_id, "agent_id": agent_id, "owner_id": owner_id}
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_id == message_id))
        await db.execute(delete(MoodleApproval).where(MoodleApproval.message_id == message_id))
        await db.execute(delete(AgentDemand).where(AgentDemand.id == message_id))
        await db.execute(delete(Agent).where(Agent.id == agent_id))
        await db.execute(delete(User).where(User.id == owner_id))
        await db.commit()


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


def _body(row, action="approve", user=OWNER_CHAT):
    return {"message_id": str(row["message_id"]), "action": action, "telegram_user_id": user}


async def _state(message_id):
    async with AsyncSessionLocal() as db:
        link = await db.scalar(select(MoodleApproval).where(MoodleApproval.message_id == message_id))
        return link, await db.get(AgentDemand, message_id)


@pytest.mark.asyncio
async def test_a_tap_approves_for_the_owner_and_the_run_can_claim_it(client, request_row):
    resp = await client.post(URL, json=_body(request_row), headers=HEADERS)
    assert resp.status_code == 200, resp.text
    assert resp.json()["result"] == "approved"
    link, demand = await _state(request_row["message_id"])
    assert link.state == "approved" and link.approved_by == request_row["owner_id"]
    assert link.executor_id == request_row["agent_id"] and demand.target_agent_id == request_row["agent_id"]
    # What /claim compares: recording the tap must not void the approval.
    assert approval_fingerprint(demand) == link.message_hash == demand.approved_content_hash
    assert demand.channel == "telegram" and demand.channel_ref == str(OWNER_CHAT) and wants_telegram_reply(demand.body)


@pytest.mark.asyncio
async def test_a_tap_rejects_and_nothing_can_run(client, request_row):
    resp = await client.post(URL, json=_body(request_row, "reject"), headers=HEADERS)
    assert resp.json()["result"] == "rejected"
    link, demand = await _state(request_row["message_id"])
    assert link.state == "rejected" and demand.status == "archived" and demand.scheduled_at is None


@pytest.mark.asyncio
async def test_a_second_tap_changes_nothing(client, request_row):
    await client.post(URL, json=_body(request_row, "reject"), headers=HEADERS)
    resp = await client.post(URL, json=_body(request_row), headers=HEADERS)
    assert resp.json() == {"result": "already_decided", "state": "rejected", "number": resp.json()["number"]}
    link, _ = await _state(request_row["message_id"])
    assert link.state == "rejected"


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [{}, {"X-Decision-Secret": "errado"}])
async def test_refuses_without_the_secret(client, request_row, headers):
    assert (await client.post(URL, json=_body(request_row), headers=headers)).status_code == 401
    link, _ = await _state(request_row["message_id"])
    assert link.state == "pending"


@pytest.mark.asyncio
async def test_an_empty_secret_closes_the_path(client, request_row, monkeypatch):
    monkeypatch.setattr(settings, "MOODLE_TELEGRAM_DECISION_SECRET", "")
    assert (await client.post(URL, json=_body(request_row), headers={"X-Decision-Secret": ""})).status_code == 401


@pytest.mark.asyncio
async def test_refuses_another_telegram_user_even_with_the_secret(client, request_row):
    assert (await client.post(URL, json=_body(request_row, user=987), headers=HEADERS)).status_code == 403
    link, _ = await _state(request_row["message_id"])
    assert link.state == "pending"


@pytest.mark.asyncio
async def test_an_expired_request_is_not_approved_but_can_be_rejected(client, request_row):
    async with AsyncSessionLocal() as db:
        link = await db.scalar(select(MoodleApproval).where(MoodleApproval.message_id == request_row["message_id"]))
        link.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db.commit()
    assert (await client.post(URL, json=_body(request_row), headers=HEADERS)).json()["result"] == "expired"
    assert (await client.post(URL, json=_body(request_row, "reject"), headers=HEADERS)).json()["result"] == "rejected"


@pytest.mark.asyncio
async def test_an_unknown_request_is_a_404(client, request_row):
    body = {**_body(request_row), "message_id": str(uuid.uuid4())}
    assert (await client.post(URL, json=body, headers=HEADERS)).status_code == 404
