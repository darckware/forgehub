"""24x7 agent operation: schedule arithmetic, occurrence generation into
Messages tasks, budget/missed handling, outcome sync and the CRUD surface.

These tests share the production database with the running backend, whose
dispatch worker would pick up any task due "now". Generated tasks are
therefore pushed one year into the future (see `far_future_tasks`): the real
insert path is exercised, nothing is ever dispatched.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api.routes import operations as ops
from app.core.deps import get_current_admin
from app.core.routine_schedule import (
    local_day_bounds,
    next_occurrences,
    occurrences_between,
    validate_schedule,
)
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.operations import AgentCharter, AgentRoutine, AgentRoutineRun

UTC = timezone.utc


# ------------------------------------------------------------ pure schedule


def test_validate_schedule_rejects_bad_input():
    validate_schedule("0 8 * * *", "America/Sao_Paulo")
    with pytest.raises(ValueError, match="timezone"):
        validate_schedule("0 8 * * *", "Mars/Olympus")
    with pytest.raises(ValueError, match="cron"):
        validate_schedule("every day", "UTC")
    with pytest.raises(ValueError, match="15 minutes"):
        validate_schedule("*/5 * * * *", "UTC")
    validate_schedule("*/15 * * * *", "UTC")


def test_occurrences_are_computed_in_routine_timezone():
    # 08:00 in Sao Paulo (UTC-3) is 11:00 UTC.
    after = datetime(2026, 10, 2, 10, 0, tzinfo=UTC)
    until = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
    found = occurrences_between("0 8 * * *", "America/Sao_Paulo", after, until)
    assert found == [datetime(2026, 10, 2, 11, 0, tzinfo=UTC), datetime(2026, 10, 3, 11, 0, tzinfo=UTC)]
    assert all(o.tzinfo is not None for o in found)


def test_occurrences_between_keeps_most_recent_when_limited():
    after = datetime(2026, 10, 1, 0, 0, tzinfo=UTC)
    until = datetime(2026, 10, 2, 0, 0, tzinfo=UTC)
    found = occurrences_between("0 * * * *", "UTC", after, until, limit=3)
    assert found == [until - timedelta(hours=2), until - timedelta(hours=1), until]


def test_next_occurrences_and_day_bounds():
    start = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    assert next_occurrences("30 2 * * *", "America/Sao_Paulo", start, 1) == [datetime(2026, 10, 3, 5, 30, tzinfo=UTC)]
    day_start, day_end = local_day_bounds(datetime(2026, 10, 3, 1, 0, tzinfo=UTC), "America/Sao_Paulo")
    assert day_start == datetime(2026, 10, 2, 3, 0, tzinfo=UTC)
    assert day_end == datetime(2026, 10, 3, 3, 0, tzinfo=UTC)


# ------------------------------------------------------------ fixtures


@pytest.fixture
def far_future_tasks(monkeypatch):
    real = ops.create_demand_and_notify

    async def deferred(db, payload, **kwargs):
        payload = payload.model_copy(update={"scheduled_at": datetime.now(UTC) + timedelta(days=365)})
        return await real(db, payload, **kwargs)

    monkeypatch.setattr(ops, "create_demand_and_notify", deferred)


@pytest_asyncio.fixture
async def agent():
    row = Agent(name=f"test-ops-{uuid.uuid4().hex[:8]}", profile_slug=f"tops{uuid.uuid4().hex[:6]}")
    async with AsyncSessionLocal() as db:
        db.add(row)
        await db.commit()
        await db.refresh(row)
    yield row
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(AgentDemand).where(
                (AgentDemand.target_agent_id == row.id) | (AgentDemand.from_agent_id == row.id)
            )
        )
        await db.execute(delete(Agent).where(Agent.id == row.id))
        await db.commit()


async def _routine(agent: Agent, **overrides) -> AgentRoutine:
    values = dict(
        agent_id=agent.id,
        title="Saúde da infra",
        instructions="Verifique containers e disco.",
        schedule="0 * * * *",
        timezone="UTC",
        deadline_minutes=30,
    )
    values.update(overrides)
    routine = AgentRoutine(**values)
    async with AsyncSessionLocal() as db:
        db.add(routine)
        await db.commit()
        await db.refresh(routine)
    return routine


async def _runs(routine_id: uuid.UUID) -> list[AgentRoutineRun]:
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(AgentRoutineRun).where(AgentRoutineRun.routine_id == routine_id).order_by(AgentRoutineRun.occurrence_at)
        )
        return list(rows.scalars())


# ------------------------------------------------------------ generation


async def test_generation_creates_one_messages_task_per_occurrence(agent, far_future_tasks):
    now = datetime.now(UTC).replace(minute=5, second=0, microsecond=0)
    routine = await _routine(agent, last_occurrence_at=now - timedelta(minutes=10))

    async with AsyncSessionLocal() as db:
        assert await ops.run_routine_generation_pass(db, now=now) >= 1
    async with AsyncSessionLocal() as db:
        # A second pass over the same window must not duplicate anything.
        await ops.run_routine_generation_pass(db, now=now)

    runs = await _runs(routine.id)
    assert len(runs) == 1
    assert runs[0].status == "scheduled"
    assert runs[0].occurrence_at == now.replace(minute=0)
    async with AsyncSessionLocal() as db:
        demand = await db.get(AgentDemand, runs[0].demand_id)
        assert demand.origin_type == "task"
        assert demand.target_agent_id == agent.id
        assert demand.subject == "[Rotina] Saúde da infra"
        assert "Verifique containers e disco." in demand.body
        assert "## Evidência esperada" in demand.body


async def test_generation_records_missed_occurrences_after_downtime(agent, far_future_tasks):
    now = datetime.now(UTC).replace(minute=5, second=0, microsecond=0)
    routine = await _routine(agent, last_occurrence_at=now - timedelta(hours=3, minutes=10))

    async with AsyncSessionLocal() as db:
        await ops.run_routine_generation_pass(db, now=now)

    runs = await _runs(routine.id)
    assert [r.status for r in runs] == ["missed", "missed", "missed", "scheduled"]
    assert all(r.demand_id is None for r in runs[:-1])


async def test_occurrence_past_its_deadline_is_missed_not_dispatched(agent, far_future_tasks):
    now = datetime.now(UTC).replace(minute=50, second=0, microsecond=0)
    routine = await _routine(agent, last_occurrence_at=now - timedelta(minutes=55), deadline_minutes=30)

    async with AsyncSessionLocal() as db:
        await ops.run_routine_generation_pass(db, now=now)

    runs = await _runs(routine.id)
    assert len(runs) == 1 and runs[0].status == "missed" and runs[0].demand_id is None


async def test_daily_run_budget_skips_instead_of_dispatching(agent, far_future_tasks):
    now = datetime.now(UTC).replace(minute=5, second=0, microsecond=0)
    async with AsyncSessionLocal() as db:
        db.add(AgentCharter(agent_id=agent.id, mission="Testar orçamento", daily_run_budget=0))
        await db.commit()
    routine = await _routine(agent, last_occurrence_at=now - timedelta(minutes=10))

    async with AsyncSessionLocal() as db:
        await ops.run_routine_generation_pass(db, now=now)

    runs = await _runs(routine.id)
    assert len(runs) == 1 and runs[0].status == "skipped_budget" and runs[0].demand_id is None


async def test_disabled_routine_is_ignored(agent, far_future_tasks):
    now = datetime.now(UTC)
    routine = await _routine(agent, enabled=False, last_occurrence_at=now - timedelta(hours=2))
    async with AsyncSessionLocal() as db:
        await ops.run_routine_generation_pass(db, now=now)
    assert await _runs(routine.id) == []


async def test_sync_copies_messages_outcome_onto_run(agent, far_future_tasks):
    now = datetime.now(UTC).replace(minute=5, second=0, microsecond=0)
    routine = await _routine(agent, last_occurrence_at=now - timedelta(minutes=10))
    async with AsyncSessionLocal() as db:
        await ops.run_routine_generation_pass(db, now=now)
    run = (await _runs(routine.id))[0]

    async with AsyncSessionLocal() as db:
        demand = await db.get(AgentDemand, run.demand_id)
        demand.dispatch_status = "failed"
        demand.dispatch_error = "runtime unavailable"
        demand.dispatched_at = now - timedelta(minutes=2)
        demand.task_execution_at = now
        demand.dispatch_result = "## Resultado\nNada a fazer.\n## Evidência\nServiço indisponível."
        await db.commit()
    async with AsyncSessionLocal() as db:
        assert await ops.run_routine_sync_pass(db) >= 1

    run = (await _runs(routine.id))[0]
    assert run.status == "failed"
    assert run.detail == "runtime unavailable"
    assert run.finished_at is not None
    assert run.duration_ms == 120_000
    assert run.cost_usd is None
    assert run.evidence_received is True
    assert run.no_action is True


def test_compose_routine_message_includes_charter_and_policy():
    agent = Agent(name="Hephaestus")
    routine = AgentRoutine(
        title="Backup", instructions="Confira o snapshot.", schedule="0 7 * * *",
        timezone="America/Sao_Paulo", kind="monitoring", deadline_minutes=60,
        linked_audit_checks=["ECO-058"], expected_evidence="ID do snapshot",
    )
    charter = AgentCharter(mission="Operar a infra", responsibilities=["Backups"], never_does=["Editar código"])
    policy = type("P", (), {"version": 3, "content": "Comunique-se pelo Messages."})()
    body = ops.compose_routine_message(routine, agent, datetime(2026, 10, 3, 10, 0, tzinfo=UTC), charter, policy)
    assert "07:00 (America/Sao_Paulo)" in body
    assert "ECO-058" in body and "ID do snapshot" in body
    assert "Editar código" in body
    assert "política v3" in body and "Comunique-se pelo Messages." in body


# ------------------------------------------------------------ API


@pytest_asyncio.fixture
async def client():
    app = FastAPI()
    app.include_router(ops.router)
    app.dependency_overrides[get_current_admin] = lambda: type("Admin", (), {"username": "tester"})()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def test_routine_api_validates_schedule_and_previews(client, agent):
    bad = await client.post("/api/v1/operations/routines", json={
        "agent_id": str(agent.id), "title": "x", "instructions": "y", "schedule": "*/5 * * * *",
    })
    assert bad.status_code == 422

    created = await client.post("/api/v1/operations/routines", json={
        "agent_id": str(agent.id), "title": "Briefing", "instructions": "Resuma o dia.",
        "schedule": "0 8 * * *", "kind": "report",
    })
    assert created.status_code == 201, created.text
    body = created.json()
    assert len(body["next_occurrences"]) == 5

    paused = await client.patch(f"/api/v1/operations/routines/{body['id']}", json={"enabled": False})
    assert paused.json()["next_occurrences"] == []
    listed = await client.get("/api/v1/operations/routines", params={"agent_id": str(agent.id)})
    assert [r["title"] for r in listed.json()] == ["Briefing"]


async def test_charter_upsert_and_overview(client, agent):
    payload = {
        "mission": "Operar a infraestrutura",
        "responsibilities": ["Containers", "Backups"],
        "never_does": ["Editar código"],
        "coordinates_with": [{"agent": "athos", "purpose": "escalada"}],
        "daily_run_budget": 10,
        "escalation": "via_athos",
    }
    first = await client.put(f"/api/v1/operations/charters/{agent.id}", json=payload)
    assert first.status_code == 200, first.text
    second = await client.put(f"/api/v1/operations/charters/{agent.id}", json={**payload, "daily_run_budget": 12})
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["daily_run_budget"] == 12

    overview = (await client.get("/api/v1/operations/overview")).json()
    row = next(a for a in overview["agents"] if a["agent_id"] == str(agent.id))
    assert row["has_charter"] is True and row["daily_run_budget"] == 12


def test_seed_catalog_is_consistent():
    from app.core.operations_seed import CHARTERS, FIRST_WAVE, HERMES_NEVER, POLICY_V1, ROUTINES

    external = {"aramis", "dartan", "porthus"}
    for slug, title, schedule, _kind, _deadline, instructions, _evidence, _checks in ROUTINES:
        assert slug in CHARTERS, f"routine {title!r} has no charter"
        validate_schedule(schedule, "America/Sao_Paulo")
        assert instructions.strip()
    for slug, charter in CHARTERS.items():
        # Only the external agents write code (Marcelo, 2026-10-02).
        assert (HERMES_NEVER in charter["never_does"]) == (slug not in external), slug
    assert FIRST_WAVE <= set(CHARTERS)
    assert "Aramis" in POLICY_V1 and "23:00" in POLICY_V1
