"""Personal domain: tasks, agenda, notes -- owner (admin) and allowed agent only; reminders once."""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core import personal_schedule
from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent, AgentServiceCredential
from app.db.models.personal import PersonalEvent, PersonalNote, PersonalTask
from app.main import app

BASE = "/api/v1/personal"


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def created():
    """Ids of rows a test creates, deleted afterwards (no transaction rollback in this suite)."""
    ids: dict[str, list] = {"task": [], "event": [], "note": []}
    yield ids
    async with AsyncSessionLocal() as db:
        for model, key in ((PersonalTask, "task"), (PersonalEvent, "event"), (PersonalNote, "note")):
            if ids[key]:
                await db.execute(delete(model).where(model.id.in_(ids[key])))
        await db.commit()


async def _agent_headers(slug: str):
    token = f"agt_{secrets.token_urlsafe(24)}"
    async with AsyncSessionLocal() as db:
        agent = Agent(name=f"test-personal-{uuid.uuid4().hex[:8]}", profile_slug=slug, status="active", is_active=True)
        db.add(agent)
        await db.flush()
        db.add(AgentServiceCredential(agent_id=agent.id, label="test", token_hash=hashlib.sha256(token.encode()).hexdigest()))
        await db.commit()
        agent_id = agent.id
    return {"Authorization": f"Bearer {token}"}, agent_id


async def _drop_agent(agent_id):
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentServiceCredential).where(AgentServiceCredential.agent_id == agent_id))
        await db.execute(delete(Agent).where(Agent.id == agent_id))
        await db.commit()


async def test_owner_crud_tasks_events_notes(client, admin_headers, created):
    r = await client.post(f"{BASE}/tasks", headers=admin_headers,
                          json={"title": "Pagar IPVA", "due_at": "2030-01-10T00:00:00", "list_name": "Casa"})
    assert r.status_code == 201, r.text
    task = r.json(); created["task"].append(task["id"])
    assert task["due_has_time"] is False and task["reminders"] == [0] and task["created_by"] == "marcelo"

    r = await client.post(f"{BASE}/events", headers=admin_headers,
                          json={"title": "Dentista", "starts_at": "2030-01-10T15:00:00", "location": "Centro"})
    event = r.json(); created["event"].append(event["id"])
    assert r.status_code == 201 and event["reminders"] == [60]

    r = await client.post(f"{BASE}/notes", headers=admin_headers,
                          json={"title": "Ideias", "content": "Comprar queijo", "tags": ["casa", " casa "]})
    note = r.json(); created["note"].append(note["id"])
    assert note["tags"] == ["casa"]

    r = await client.get(f"{BASE}/notes", headers=admin_headers, params={"q": "queijo"})
    assert [n["id"] for n in r.json()] == [note["id"]]

    r = await client.patch(f"{BASE}/tasks/{task['id']}", headers=admin_headers, json={"status": "done"})
    assert r.json()["status"] == "done" and r.json()["completed_at"]

    r = await client.get(f"{BASE}/agenda", headers=admin_headers,
                         params={"start": "2030-01-10T00:00:00", "end": "2030-01-11T00:00:00"})
    assert [(i["kind"], i["title"]) for i in r.json()] == [("event", "Dentista")]

    assert (await client.delete(f"{BASE}/notes/{note['id']}", headers=admin_headers)).status_code == 204
    created["note"].remove(note["id"])


async def test_recurring_task_rolls_forward_on_complete(client, admin_headers, created):
    r = await client.post(f"{BASE}/tasks", headers=admin_headers,
                          json={"title": "Condomínio", "due_at": "2030-01-10T00:00:00", "recurrence": "monthly"})
    tid = r.json()["id"]; created["task"].append(tid)
    r = await client.post(f"{BASE}/tasks/{tid}:complete", headers=admin_headers)
    assert r.json()["status"] == "pending" and r.json()["due_at"].startswith("2030-02-10")


async def test_reminders_fire_once(client, admin_headers, created, monkeypatch):
    moment = datetime(2030, 5, 20, 15, 0)
    r = await client.post(f"{BASE}/events", headers=admin_headers,
                          json={"title": "Reunião SEMED", "starts_at": moment.isoformat(), "reminders": [60]})
    created["event"].append(r.json()["id"])
    import app.api.routes.personal as routes
    monkeypatch.setattr(routes, "now_local", lambda: moment - timedelta(minutes=59))
    first = (await client.post(f"{BASE}/reminders:due", headers=admin_headers)).json()["lines"]
    assert any("Reunião SEMED" in line and "em 1h" in line for line in first)
    again = (await client.post(f"{BASE}/reminders:due", headers=admin_headers)).json()["lines"]
    assert not any("Reunião SEMED" in line for line in again)


async def test_summary_lists_today_and_overdue():
    task_today = type("T", (), dict(title="Ligar SEMED", due_at=datetime(2030, 1, 10, 10, 0), due_has_time=True,
                                    list_name="Trabalho"))()
    late = type("T", (), dict(title="Pagar IPVA", due_at=datetime(2030, 1, 8), due_has_time=False, list_name="Casa"))()
    text = personal_schedule.day_summary(datetime(2030, 1, 10).date(), [], [task_today, late])
    assert "Hoje:\n- ✅ quinta 10/01 às 10:00: Ligar SEMED [Trabalho]" in text
    assert "Tarefas atrasadas:\n- ✅ terça 08/01: Pagar IPVA [Casa]" in text


async def test_only_allowed_agent_and_never_deletes(client, admin_headers, created, monkeypatch):
    allowed_slug, other_slug = f"pa{uuid.uuid4().hex[:6]}", f"po{uuid.uuid4().hex[:6]}"
    monkeypatch.setattr(settings, "PERSONAL_AGENT_SLUGS", allowed_slug)
    allowed, allowed_id = await _agent_headers(allowed_slug)
    other, other_id = await _agent_headers(other_slug)
    try:
        assert (await client.get(f"{BASE}/tasks", headers=other)).status_code == 403
        r = await client.post(f"{BASE}/tasks", headers=allowed, json={"title": "Lembrar o Marcelo"})
        assert r.status_code == 201 and r.json()["created_by"] == allowed_slug
        created["task"].append(r.json()["id"])
        assert (await client.delete(f"{BASE}/tasks/{r.json()['id']}", headers=allowed)).status_code == 403
        r = await client.patch(f"{BASE}/tasks/{r.json()['id']}", headers=allowed, json={"status": "cancelled"})
        assert r.json()["status"] == "cancelled"
    finally:
        await _drop_agent(allowed_id)
        await _drop_agent(other_id)


async def test_non_admin_user_is_refused(client, auth_headers):
    assert (await client.get(f"{BASE}/notes", headers=auth_headers)).status_code in (401, 403)


async def test_validation(client, admin_headers):
    r = await client.post(f"{BASE}/events", headers=admin_headers,
                          json={"title": "x", "starts_at": "2030-01-10T15:00:00", "ends_at": "2030-01-10T14:00:00"})
    assert r.status_code == 422
    r = await client.post(f"{BASE}/tasks", headers=admin_headers, json={"title": "x", "recurrence": "hourly"})
    assert r.status_code == 422
