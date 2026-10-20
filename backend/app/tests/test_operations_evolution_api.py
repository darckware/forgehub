"""Evolution history is visible and reversions require an administrator."""

import pytest_asyncio
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.api.routes import operations as ops
from app.core.deps import get_current_admin
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.operations import AgentCharter, AgentQuestion, AgentRoutine, OperationsChange
from app.db.models.notification import Notification
from app.core.config import settings


@pytest_asyncio.fixture
async def client():
    app = FastAPI()
    app.include_router(ops.router)
    app.dependency_overrides[get_current_admin] = lambda: object()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def test_evolution_lists_changes_and_daily_trend(client):
    response = await client.get("/api/v1/operations/evolution")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"changes", "trend"}
    assert isinstance(body["changes"], list)
    assert len(body["trend"]) == 7


async def test_admin_undo_restores_exact_previous_routine_state(client):
    agent = Agent(name=f"test-undo-{uuid.uuid4().hex[:8]}", profile_slug=f"tundo{uuid.uuid4().hex[:8]}")
    async with AsyncSessionLocal() as db:
        db.add(agent)
        await db.flush()
        routine = AgentRoutine(
            agent_id=agent.id, title="Test undo routine", instructions="New instruction",
            schedule="0 8 * * *", timezone="America/Sao_Paulo", kind="monitoring",
            enabled=True, priority=0, deadline_minutes=60,
        )
        db.add(routine)
        await db.flush()
        change = OperationsChange(
            routine_id=routine.id, target_type="routine", summary="Test undo",
            rationale="Test", autonomy_level="A1", status="evaluating",
            metric_name="evidence_rate", previous_state={"instructions": "Old instruction"},
            new_state={"instructions": "New instruction"},
            applied_at=datetime.now(timezone.utc),
            evaluation_ends_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db.add(change)
        await db.commit()
    try:
        response = await client.post(f"/api/v1/operations/changes/{change.id}:undo")
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "reverted"
        async with AsyncSessionLocal() as db:
            assert (await db.get(AgentRoutine, routine.id)).instructions == "Old instruction"
        again = await client.post(f"/api/v1/operations/changes/{change.id}:undo")
        assert again.status_code == 409
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(OperationsChange).where(OperationsChange.id == change.id))
            await db.execute(delete(AgentRoutine).where(AgentRoutine.id == routine.id))
            await db.execute(delete(Agent).where(Agent.id == agent.id))
            await db.commit()


async def test_a2_charter_proposal_waits_for_marcelo_answer(client, monkeypatch):
    agent = Agent(name=f"test-a2-{uuid.uuid4().hex[:8]}", profile_slug=f"ta2{uuid.uuid4().hex[:8]}")
    async with AsyncSessionLocal() as db:
        db.add(agent)
        await db.flush()
        db.add(AgentCharter(agent_id=agent.id, mission="Old mission"))
        await db.commit()

    monkeypatch.setattr(ops.agent_questions, "notify_after_for", lambda now, urgent: now + timedelta(days=365))
    change_id = None
    try:
        response = await client.post(
            "/api/v1/operations/agent-changes",
            headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
            json={
                "agent": agent.profile_slug, "target_type": "charter", "target_id": str(agent.id),
                "summary": "Change mission", "rationale": "Coverage gap",
                "metric_name": "coverage", "new_state": {"mission": "New mission"},
            },
        )
        assert response.status_code == 201, response.text
        change_id = uuid.UUID(response.json()["id"])
        assert response.json()["status"] == "awaiting_approval"
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            charter = (await db.execute(select(AgentCharter).where(AgentCharter.agent_id == agent.id))).scalar_one()
            assert charter.mission == "Old mission"
            change = await db.get(OperationsChange, change_id)
            assert change.question_id is not None
            question = await db.get(AgentQuestion, change.question_id)
            assert question.status == "pending"
            question.status = "answered"
            question.answer = "sim"
            question.answered_at = datetime.now(timezone.utc)
            question.answered_via = "screen"
            question.answered_by = "test-admin"
            await db.commit()
        async with AsyncSessionLocal() as db:
            assert await ops.run_evolution_pass(db, routine_ids=[], change_ids=[change_id]) == 1
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            charter = (await db.execute(select(AgentCharter).where(AgentCharter.agent_id == agent.id))).scalar_one()
            assert charter.mission == "New mission"
            assert (await db.get(OperationsChange, change_id)).status == "evaluating"
        undo = await client.post(f"/api/v1/operations/changes/{change_id}:undo")
        assert undo.status_code == 200, undo.text
        assert undo.json()["status"] == "reverted"
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            charter = (await db.execute(select(AgentCharter).where(AgentCharter.agent_id == agent.id))).scalar_one()
            assert charter.mission == "Old mission"
    finally:
        async with AsyncSessionLocal() as db:
            change = await db.get(OperationsChange, change_id) if change_id else None
            question_id = change.question_id if change else None
            if change:
                await db.delete(change)
                await db.flush()
            if question_id:
                await db.execute(delete(Notification).where(Notification.event_key == f"agent-question:{question_id}"))
                await db.execute(delete(AgentQuestion).where(AgentQuestion.id == question_id))
            await db.execute(delete(AgentCharter).where(AgentCharter.agent_id == agent.id))
            await db.execute(delete(Agent).where(Agent.id == agent.id))
            await db.commit()
