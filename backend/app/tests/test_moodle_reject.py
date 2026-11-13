"""The owner refuses a Moodle request with one button: nothing runs and it leaves the list."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.moodle_approval import MoodleApproval
from app.db.models.user import User
from app.main import app

URL = "/api/v1/personal/moodle-approvals"


@pytest_asyncio.fixture
async def proposal(monkeypatch, tmp_path):
    owner_id, agent_id, message_id, request_id = (uuid.uuid4() for _ in range(4))
    username = f"dono-{owner_id.hex[:8]}"
    async with AsyncSessionLocal() as db:
        db.add(User(id=owner_id, username=username, hashed_password="x", is_active=True, is_admin=True))
        db.add(Agent(id=agent_id, name=f"Fonte {agent_id.hex[:8]}", profile_slug=f"fonte-{agent_id.hex[:8]}"))
        await db.flush()
        db.add(AgentDemand(id=message_id, from_agent="fonte", from_agent_id=agent_id, target_agent_id=agent_id,
                           subject="Moodle: solicitação de aprovação", body="Proposta.", origin_type="task",
                           status="new", requires_approval=True, approval_status="pending"))
        await db.flush()
        db.add(MoodleApproval(message_id=message_id, request_id=request_id, source_agent_id=agent_id,
                              params_hash="a" * 64, state="pending",
                              expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        await db.commit()
        updated_at = (await db.get(AgentDemand, message_id)).updated_at
    monkeypatch.setattr(settings, "MOODLE_APPROVAL_ENABLED", True)
    monkeypatch.setattr(settings, "MOODLE_APPROVAL_OWNER_ID", str(owner_id))
    monkeypatch.setattr(settings, "MOODLE_APPROVAL_WORKING_PATH", str(tmp_path))
    monkeypatch.setattr(settings, "MOODLE_APPROVAL_SOURCE_FILES", json.dumps({str(agent_id): str(tmp_path / "p.json")}))
    yield {"username": username, "message_id": message_id,
           "item": {"request_id": str(request_id), "message_id": str(message_id), "params_hash": "a" * 64,
                    "message_updated_at": updated_at.isoformat()}}
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


def _as(username: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(subject=username)}"}


@pytest.mark.asyncio
async def test_owner_rejects_and_nothing_can_run(client, proposal):
    body = {"reason": "Pedido errado", "items": [proposal["item"]]}
    response = await client.post(f"{URL}/reject", headers=_as(proposal["username"]), json=body)
    assert response.status_code == 200, response.text
    async with AsyncSessionLocal() as db:
        demand = await db.get(AgentDemand, proposal["message_id"])
        link = await db.scalar(select(MoodleApproval).where(MoodleApproval.message_id == proposal["message_id"]))
        events = (await db.execute(select(AuditEvent.event_type).where(AuditEvent.entity_id == proposal["message_id"]))).scalars().all()
    assert link.state == "rejected" and link.approved_by is None
    assert demand.status == "archived" and demand.approval_status == "rejected" and demand.scheduled_at is None
    assert demand.decision_reason == "Pedido errado"
    assert "demand_moodle_rejected" in events
    listed = await client.get(URL, headers=_as(proposal["username"]))
    assert listed.json()["items"] == []
    again = await client.post(f"{URL}/reject", headers=_as(proposal["username"]), json=body)
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_only_the_owner_decides(client, proposal, admin_headers):
    body = {"items": [proposal["item"]]}
    assert (await client.post(f"{URL}/reject", headers=admin_headers, json=body)).status_code == 403
    authorize = {"executor_agent_id": str(uuid.uuid4()), "instruction": "", "items": [proposal["item"]]}
    assert (await client.post(f"{URL}/authorize", headers=admin_headers, json=authorize)).status_code == 403


@pytest.mark.asyncio
async def test_a_changed_message_is_not_decided_blindly(client, proposal):
    item = {**proposal["item"], "message_updated_at": "2020-01-01T00:00:00+00:00"}
    response = await client.post(f"{URL}/reject", headers=_as(proposal["username"]), json={"items": [item]})
    assert response.status_code == 409


async def _set_state(message_id, state, outcome=None):
    async with AsyncSessionLocal() as db:
        link = await db.scalar(select(MoodleApproval).where(MoodleApproval.message_id == message_id))
        link.state, link.outcome = state, outcome
        demand = await db.get(AgentDemand, message_id)
        demand.dispatch_status, demand.approval_status = "failed", "approved"
        await db.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("state,outcome", [("finished", "completed"), ("finished", "failed"), ("rejected", None)])
async def test_spent_moodle_message_can_be_archived(client, proposal, state, outcome):
    """2026-11-13: once its own flow is over, a Moodle message can leave Execução."""
    await _set_state(proposal["message_id"], state, outcome)
    response = await client.post(f"/api/v1/demands/{proposal['message_id']}/decision",
                                 headers=_as(proposal["username"]), json={"action": "archive", "reason": "encerrada"})
    assert response.status_code == 200, response.text
    async with AsyncSessionLocal() as db:
        assert (await db.get(AgentDemand, proposal["message_id"])).status == "archived"


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["pending", "approved", "claimed"])
async def test_live_moodle_message_is_not_archived(client, proposal, state):
    await _set_state(proposal["message_id"], state)
    response = await client.post(f"/api/v1/demands/{proposal['message_id']}/decision",
                                 headers=_as(proposal["username"]), json={"action": "archive"})
    assert response.status_code == 409, response.text
    async with AsyncSessionLocal() as db:
        assert (await db.get(AgentDemand, proposal["message_id"])).status != "archived"


@pytest.mark.asyncio
async def test_spent_moodle_message_still_refuses_other_decisions(client, proposal):
    await _set_state(proposal["message_id"], "finished", "failed")
    response = await client.post(f"/api/v1/demands/{proposal['message_id']}/decision",
                                 headers=_as(proposal["username"]), json={"action": "authorize_retry",
                                 "reason": "de novo", "evidence_ref": "x"})
    assert response.status_code == 409, response.text
