"""Retrospectives apply safe changes once and preserve a rollback path."""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import delete, select

from app.api.routes.operations import run_evolution_pass
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.operations import AgentRoutine, AgentRoutineRun, OperationsChange
from app.db.models.notification import Notification


async def test_three_failed_runs_pause_once_and_record_previous_state():
    now = datetime.now(timezone.utc)
    agent = Agent(name=f"test-evolution-{uuid.uuid4().hex[:8]}", profile_slug=f"tevo{uuid.uuid4().hex[:8]}")
    routine = AgentRoutine(
        agent_id=agent.id, title="Test failing routine", instructions="Verify health",
        schedule="0 8 * * *", timezone="America/Sao_Paulo", kind="monitoring",
        enabled=True, priority=0, deadline_minutes=60,
    )
    async with AsyncSessionLocal() as db:
        db.add(agent)
        await db.flush()
        routine.agent_id = agent.id
        db.add(routine)
        await db.flush()
        for offset in range(3):
            db.add(AgentRoutineRun(
                routine_id=routine.id, occurrence_at=now - timedelta(hours=offset + 1),
                status="failed", finished_at=now - timedelta(hours=offset),
            ))
        await db.commit()
    try:
        async with AsyncSessionLocal() as db:
            assert await run_evolution_pass(db, now=now, routine_ids=[routine.id]) == 1
            assert await run_evolution_pass(db, now=now, routine_ids=[routine.id]) == 0
        async with AsyncSessionLocal() as db:
            saved = await db.get(AgentRoutine, routine.id)
            change = (await db.execute(select(OperationsChange).where(OperationsChange.routine_id == routine.id))).scalar_one()
            assert saved.enabled is False
            assert change.autonomy_level == "A0"
            assert change.status == "evaluating"
            assert change.previous_state == {"enabled": True}
            assert change.new_state == {"enabled": False}
            assert change.evaluation_ends_at == now + timedelta(days=7)
    finally:
        async with AsyncSessionLocal() as db:
            change_ids = list((await db.execute(select(OperationsChange.id).where(OperationsChange.routine_id == routine.id))).scalars())
            for change_id in change_ids:
                await db.execute(delete(Notification).where(Notification.event_key == f"operations-change:{change_id}"))
            await db.execute(delete(OperationsChange).where(OperationsChange.routine_id == routine.id))
            await db.execute(delete(AgentRoutine).where(AgentRoutine.id == routine.id))
            await db.execute(delete(Agent).where(Agent.id == agent.id))
            await db.commit()


async def test_worse_metric_after_seven_days_restores_previous_instructions():
    now = datetime.now(timezone.utc)
    agent = Agent(name=f"test-evolution-{uuid.uuid4().hex[:8]}", profile_slug=f"tevo{uuid.uuid4().hex[:8]}")
    routine = AgentRoutine(
        title="Test evidence routine", instructions="New instruction", schedule="0 8 * * *",
        timezone="America/Sao_Paulo", kind="monitoring", enabled=True,
        priority=0, deadline_minutes=60,
    )
    async with AsyncSessionLocal() as db:
        db.add(agent)
        await db.flush()
        routine.agent_id = agent.id
        db.add(routine)
        await db.flush()
        change = OperationsChange(
            routine_id=routine.id, target_type="routine", summary="Test evidence change",
            rationale="Test metric", autonomy_level="A1", status="evaluating",
            metric_name="evidence_rate", before_value=Decimal("1"),
            previous_state={"instructions": "Old instruction"},
            new_state={"instructions": "New instruction"},
            applied_at=now - timedelta(days=8), evaluation_ends_at=now - timedelta(days=1),
        )
        db.add(change)
        db.add(AgentRoutineRun(
            routine_id=routine.id, occurrence_at=now - timedelta(days=3),
            status="completed", evidence_received=False, finished_at=now - timedelta(days=3),
        ))
        await db.commit()
    try:
        async with AsyncSessionLocal() as db:
            assert await run_evolution_pass(db, now=now, routine_ids=[routine.id]) == 1
        async with AsyncSessionLocal() as db:
            saved = await db.get(AgentRoutine, routine.id)
            evaluated = await db.get(OperationsChange, change.id)
            assert saved.instructions == "Old instruction"
            assert evaluated.status == "reverted"
            assert evaluated.after_value == Decimal("0")
            assert evaluated.learning
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(OperationsChange).where(OperationsChange.routine_id == routine.id))
            await db.execute(delete(AgentRoutine).where(AgentRoutine.id == routine.id))
            await db.execute(delete(Agent).where(Agent.id == agent.id))
            await db.commit()
