# ruff: noqa: F811
"""Stable handoff identities across API retries; no external transport is used."""
import asyncio
import uuid

import pytest
from sqlalchemy import delete, func, select

from app.db.base import AsyncSessionLocal
from app.db.models.command_receipt import AgentCommandReceipt
from app.db.models.demand import AgentDemand
from app.db.models.operations import AgentQuestion
from app.tests.test_agent_questions import agents, client, never_due  # noqa: F401


@pytest.mark.asyncio
async def test_concurrent_question_replay_creates_one_question(client, agents, never_due):
    asker, _ = agents
    body = {"agent": asker.profile_slug, "question": "Qual destino foi autorizado?", "blocking": True,
            "idempotency_key": f"question-{uuid.uuid4().hex}"}
    path = "/api/v1/operations/agent-questions"
    try:
        first, replay = await asyncio.gather(client.post(path, json=body), client.post(path, json=body))
        assert {first.status_code, replay.status_code} == {200, 201}
        assert first.json()["id"] == replay.json()["id"]
        changed = await client.post(path, json={**body, "question": "Outro destino?"})
        assert changed.status_code == 409
        async with AsyncSessionLocal() as db:
            assert await db.scalar(select(func.count(AgentQuestion.id)).where(AgentQuestion.agent_id == asker.id)) == 1
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AgentCommandReceipt).where(AgentCommandReceipt.principal_id == asker.id))
            await db.commit()


@pytest.mark.asyncio
async def test_concurrent_identical_answers_create_one_resume_task(client, agents, never_due):
    asker, relay = agents
    response = await client.post("/api/v1/operations/agent-questions", json={
        "agent": asker.profile_slug, "question": "Qual formato?", "blocking": True})
    assert response.status_code == 201
    question = response.json()
    path = f"/api/v1/operations/agent-questions/{question['number']}/relay-answer"
    body = {"agent": relay.profile_slug, "answer": "CSV"}
    first, replay = await asyncio.gather(client.post(path, json=body), client.post(path, json=body))
    assert first.status_code == replay.status_code == 200
    assert first.json()["reply_demand_id"] == replay.json()["reply_demand_id"]
    async with AsyncSessionLocal() as db:
        count = await db.scalar(select(func.count(AgentDemand.id)).where(
            AgentDemand.target_agent_id == asker.id,
            AgentDemand.subject == f"[Resposta] Pergunta #{question['number']}"))
        assert count == 1
    assert (await client.post(path, json={**body, "answer": "XLSX"})).status_code == 409


@pytest.mark.asyncio
async def test_question_identity_survives_generic_receipt_retention(client, agents, never_due):
    from datetime import datetime, timedelta, timezone
    from app.core.command_receipts import run_command_receipt_retention
    asker, _ = agents
    body = {"agent": asker.profile_slug, "question": "Decisão de longo prazo?", "blocking": True,
            "idempotency_key": f"question-{uuid.uuid4().hex}"}
    path = "/api/v1/operations/agent-questions"
    try:
        original = await client.post(path, json=body)
        assert original.status_code == 201
        async with AsyncSessionLocal() as db:
            receipt = await db.scalar(select(AgentCommandReceipt).where(
                AgentCommandReceipt.principal_id == asker.id,
                AgentCommandReceipt.idempotency_key == body["idempotency_key"]))
            receipt.created_at = datetime.now(timezone.utc) - timedelta(days=60)
            await db.commit()
            await run_command_receipt_retention(db)
        replay = await client.post(path, json=body)
        assert replay.status_code == 200
        assert replay.json()["id"] == original.json()["id"]
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AgentCommandReceipt).where(AgentCommandReceipt.principal_id == asker.id))
            await db.commit()
