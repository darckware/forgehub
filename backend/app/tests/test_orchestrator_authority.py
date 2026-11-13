"""The orchestrator's authority (2026-11-13): it asks Marcelo's authorization
through Pessoal → Tarefas dos agentes, Marcelo's mission decisions share that
inbox, and it programs Operação 24x7 with its own agt_.

Runs only against the isolated test database; every route and guard is real.
Each test removes the rows it created.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.core import dispatch_signal
from app.core.demand_workflow import WorkflowBlocked, assert_execution_allowed, ensure_workflow_allowed
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.notification import Notification
from app.db.models.operations import AgentCharter, AgentRoutine, AgentRoutineRun
from app.mcp import factory_server
from app.tests.test_mission_base import _force
from app.tests.test_mission_phases import _set_phase
from app.tests.test_mission_plan_approval import (  # noqa: F401  (fixtures)
    Plan,
    _clean_stale_mission_fixtures,
    mcp_as,
    world,
)


def _key() -> str:
    return f"mission-test-{uuid.uuid4()}"


def _code(response) -> str | None:
    detail = response.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


@pytest.fixture(autouse=True)
def _no_wake(monkeypatch):
    """No dispatch worker runs under test; keep the signal inert anyway."""
    monkeypatch.setattr(dispatch_signal, "wake_scheduled_dispatch", lambda: None)


async def _drop_mission_demands(project_id) -> None:
    async with AsyncSessionLocal() as db:
        ids = list((await db.execute(select(AgentDemand.id).where(
            AgentDemand.project_id == uuid.UUID(str(project_id))))).scalars())
        if ids:
            await db.execute(text("DELETE FROM company.notifications WHERE event_key = ANY(:keys)"),
                             {"keys": [f"mission-authorization:{i}" for i in ids]})
            await db.execute(text("DELETE FROM company.audit_events WHERE entity_id = ANY(:ids)"), {"ids": ids})
            await db.execute(text("DELETE FROM company.agent_demands WHERE id = ANY(:ids)"), {"ids": ids})
        await db.commit()


# ---------------------------------------------------------------------------
# Feature A: request_marcelo_approval
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_authorization_request_is_held_until_marcelo_approves(world, mcp_as):  # noqa: F811
    mission = await world.create_mission(working_directory_path=f"/srv/forgehub-test/auth-{world.tag}")
    pid = mission["project_id"]
    world.mission_ids.append(pid)
    orchestrator = uuid.UUID(mission["orchestrator_agent_id"])
    orch_h = await world.agent_token(orchestrator, ["mission.orchestrate"], uuid.UUID(pid))
    stranger_h = await world.agent_token(await world.agent("x"), ["mission.orchestrate"], uuid.UUID(pid))
    url = f"/api/v1/missions/{pid}/approval-requests"
    body = {"action": "Contratar storage extra", "justification": "O disco de teste esgota em 2 dias",
            "instructions": "Ampliar o volume para 200 GB e verificar com df -h."}
    try:
        async with world.client(stranger_h) as client:
            assert (await client.post(url, json={**body, "idempotency_key": _key()})).status_code == 403
        async with world.client(orch_h) as client:
            no_key = await client.post(url, json=body)
            assert no_key.status_code == 422 and _code(no_key) == "IDEMPOTENCY_KEY_REQUIRED"
            key = _key()
            created = await client.post(url, json={**body, "idempotency_key": key})
            assert created.status_code == 201, created.text
            replay = await client.post(url, json={**body, "idempotency_key": key})
            assert replay.headers.get("idempotent-replay") == "true"
            assert replay.json()["demand_id"] == created.json()["demand_id"]
        demand_id = uuid.UUID(created.json()["demand_id"])
        async with AsyncSessionLocal() as db:
            demand = await db.get(AgentDemand, demand_id)
            assert (demand.from_agent_id, demand.target_agent_id) == (orchestrator, orchestrator)
            assert demand.requires_approval and demand.approval_status == "pending"
            assert demand.scheduled_at is None and demand.dispatch_status is None and demand.fixed_agent
            assert demand.origin_type == "task" and demand.context_area == f"mission:{pid}"
            assert demand.working_path == f"/srv/forgehub-test/auth-{world.tag}"
            assert demand.subject == "[Autorização] Contratar storage extra"
            assert "df -h" in demand.body and "O disco de teste" in demand.body
            # Held at the runner boundary, whatever path reaches it.
            with pytest.raises(WorkflowBlocked):
                assert_execution_allowed(demand)
            assert await db.scalar(select(Notification.id).where(
                Notification.event_key == f"mission-authorization:{demand_id}"))
            event = (await db.execute(select(AuditEvent).where(
                AuditEvent.entity_id == uuid.UUID(pid),
                AuditEvent.event_type == "mission_authorization_requested"))).scalar_one()
            orchestrator_row = await db.get(Agent, orchestrator)
            assert event.actor == orchestrator_row.name and event.payload["principal_type"] == "agent"

        async with world.client() as client:
            work = await client.get("/api/v1/demands/agent-work",
                                    params={"view": "decision", "search": f"#{demand.number}"})
            item = next(i for i in work.json()["items"] if i["id"] == str(demand_id))
            assert "approve" in item["allowed_actions"] and "reject" in item["allowed_actions"]
            approved = await client.post(f"/api/v1/demands/{demand_id}/decision", json={"action": "approve"})
            assert approved.status_code == 200, approved.text
        async with AsyncSessionLocal() as db:
            demand = await db.get(AgentDemand, demand_id)
            assert demand.approval_status == "approved" and demand.scheduled_at is not None
            assert demand.target_agent_id == orchestrator
            assert_execution_allowed(demand)
            await ensure_workflow_allowed(db, demand)
            # Keep it out of any real queue during the rest of the run.
            demand.scheduled_at = datetime.now(timezone.utc) + timedelta(days=365)
            await db.commit()

        # MCP tool, and the refusals.
        mcp_as(orch_h["Authorization"][7:])
        via_mcp = await factory_server.request_marcelo_approval(pid, "Publicar", "Fim da fase", "Publicar v1",
                                                                idempotency_key=_key())
        assert via_mcp["approval_status"] == "pending" and via_mcp["replayed"] is False
        await _force(pid, state="cancelled")
        async with world.client(orch_h) as client:
            terminal = await client.post(url, json={**body, "idempotency_key": _key()})
        assert terminal.status_code == 409 and _code(terminal) == "MISSION_TERMINAL"
    finally:
        await _drop_mission_demands(pid)


@pytest.mark.asyncio
async def test_authorization_request_needs_working_directory_and_rejection_never_runs(world):  # noqa: F811
    mission = await world.create_mission()
    pid = mission["project_id"]
    world.mission_ids.append(pid)
    url = f"/api/v1/missions/{pid}/approval-requests"
    body = {"action": "a", "justification": "j", "instructions": "i"}
    try:
        async with world.client() as client:
            refused = await client.post(url, json=body)
            assert refused.status_code == 422 and _code(refused) == "WORKING_DIRECTORY_REQUIRED"
        mission = await world.create_mission(working_directory_path=f"/srv/forgehub-test/rej-{world.tag}")
        pid2 = mission["project_id"]
        world.mission_ids.append(pid2)
        async with world.client() as client:
            created = await client.post(f"/api/v1/missions/{pid2}/approval-requests", json=body)
            assert created.status_code == 201, created.text
            demand_id = created.json()["demand_id"]
            no_reason = await client.post(f"/api/v1/demands/{demand_id}/decision", json={"action": "reject"})
            assert no_reason.status_code == 422
            rejected = await client.post(f"/api/v1/demands/{demand_id}/decision",
                                         json={"action": "reject", "reason": "Fora do orçamento"})
            assert rejected.status_code == 200, rejected.text
        async with AsyncSessionLocal() as db:
            demand = await db.get(AgentDemand, uuid.UUID(demand_id))
            assert demand.approval_status == "rejected" and demand.scheduled_at is None
            with pytest.raises(WorkflowBlocked):
                assert_execution_allowed(demand)
    finally:
        await _drop_mission_demands(pid)
        if "pid2" in locals():
            await _drop_mission_demands(pid2)


# ---------------------------------------------------------------------------
# Feature A: one approval inbox
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_pending_decisions_lists_plans_and_phases_until_decided(world):  # noqa: F811
    plan = await Plan().build(world)
    submitted = await plan.submit()
    assert submitted.status_code in (200, 201), submitted.text
    request_id = submitted.json()["approval_request_id"]

    mission = await world.create_mission(working_directory_path=f"/srv/forgehub-test/pd-{world.tag}")
    pid = mission["project_id"]
    world.mission_ids.append(pid)
    async with world.client() as client:
        phase = (await client.post(f"/api/v1/missions/{pid}/phases",
                                   json={"name": "Estrutura", "objective": "Navegação"})).json()["phases"][0]
    await _set_phase(phase["phase_id"], phase_status="awaiting_approval", homologation_verdict="approved",
                     homologation_summary="Testei a navegação", homologation_evidence="git:abc\nfile:x.md",
                     homologated_at=datetime.now(timezone.utc))
    orch_h = await world.agent_token(uuid.UUID(mission["orchestrator_agent_id"]), ["mission.orchestrate"],
                                     uuid.UUID(pid))
    try:
        async with world.client(orch_h) as client:
            assert (await client.get("/api/v1/missions/pending-decisions")).status_code == 403

        async with world.client() as client:
            listed = await client.get("/api/v1/missions/pending-decisions")
            assert listed.status_code == 200, listed.text
            rows = listed.json()
            plan_row = next(r for r in rows if r.get("approval_request_id") == request_id)
            assert plan_row["kind"] == "plan_approval" and plan_row["mission_project_id"] == plan.project_id
            assert plan_row["task_count"] == 1 and plan_row["link"] == f"/missions/{plan.project_id}"
            phase_row = next(r for r in rows if r.get("phase_id") == phase["phase_id"])
            assert phase_row["kind"] == "phase_approval" and phase_row["summary"] == "Testei a navegação"
            assert phase_row["homologation_evidence"] == ["git:abc", "file:x.md"]
            assert phase_row["title"] == "Fase 1 · Estrutura"

            decided = await plan.decide(request_id, decision="rejected")
            assert decided.status_code == 200, decided.text
            approved = await client.post(f"/api/v1/missions/{pid}/phases/{phase['phase_id']}:approve",
                                         json={"reason": "ok"})
            assert approved.status_code == 200, approved.text
            after = (await client.get("/api/v1/missions/pending-decisions")).json()
        assert not any(r.get("approval_request_id") == request_id for r in after)
        assert not any(r.get("phase_id") == phase["phase_id"] for r in after)
    finally:
        await _drop_mission_demands(pid)


# ---------------------------------------------------------------------------
# Feature B: Operação 24x7 by an agent
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def ops_world(world):  # noqa: F811
    orchestrator = await world.agent("ops-orch")
    target = await world.agent("ops-target")
    retired = await world.agent("ops-retired")
    async with AsyncSessionLocal() as db:
        (await db.get(Agent, retired)).status = "retired"
        db.add(AgentCharter(agent_id=target, mission="test", daily_run_budget=10))
        await db.commit()
        slug = (await db.get(Agent, orchestrator)).name
    world.ops = {
        "orchestrator": orchestrator, "target": target, "retired": retired, "actor": f"agent:{slug}",
        "headers": await world.agent_token(orchestrator, ["operations.routines.manage"]),
        "plain": await world.agent_token(await world.agent("ops-plain"), None),
    }
    yield world
    async with AsyncSessionLocal() as db:
        ids = [orchestrator, target, retired]
        routine_ids = list((await db.execute(select(AgentRoutine.id).where(AgentRoutine.agent_id.in_(ids)))).scalars())
        if routine_ids:
            demand_ids = list((await db.execute(select(AgentRoutineRun.demand_id).where(
                AgentRoutineRun.routine_id.in_(routine_ids)))).scalars())
            await db.execute(text("DELETE FROM company.audit_events WHERE entity_id = ANY(:ids)"),
                             {"ids": routine_ids})
            await db.execute(text("DELETE FROM company.agent_routines WHERE id = ANY(:ids)"), {"ids": routine_ids})
            demand_ids = [d for d in demand_ids if d]
            if demand_ids:
                await db.execute(text("DELETE FROM company.agent_demands WHERE id = ANY(:ids)"), {"ids": demand_ids})
        await db.execute(text("DELETE FROM company.agent_charters WHERE agent_id = ANY(:ids)"), {"ids": ids})
        await db.commit()


def _routine(target, **extra) -> dict:
    return {"agent_id": str(target), "title": "Verificar backups", "instructions": "Confira o último backup.",
            "schedule": "0 8 * * *", "timezone": "America/Sao_Paulo", **extra}


@pytest.mark.asyncio
async def test_agent_routines_crud_authorship_and_audit(ops_world):
    w, ops = ops_world, ops_world.ops
    base = "/api/v1/operations/agent/routines"
    async with w.client(ops["plain"]) as client:
        assert (await client.get(base)).status_code == 403
        assert (await client.post(base, json=_routine(ops["target"]))).status_code == 403
    async with w.client() as client:  # A person uses the admin routes.
        assert (await client.post(base, json=_routine(ops["target"]))).status_code == 403
        by_admin = await client.post("/api/v1/operations/routines", json=_routine(ops["target"], title="Admin"))
        assert by_admin.status_code == 201 and by_admin.json()["created_by"].startswith("test-admin-")
    admin_routine = by_admin.json()["id"]

    async with w.client(ops["headers"]) as client:
        created = await client.post(base, json=_routine(ops["target"]))
        assert created.status_code == 201, created.text
        routine = created.json()
        assert routine["created_by"] == ops["actor"] and routine["updated_by"] == ops["actor"]
        assert routine["next_occurrences"]
        listed = await client.get(base, params={"agent_id": str(ops["target"])})
        assert {r["id"] for r in listed.json()} == {routine["id"], admin_routine}

        bad = await client.post(base, json=_routine(ops["target"], schedule="*/5 * * * *"))
        assert bad.status_code == 422
        inactive = await client.post(base, json=_routine(ops["retired"]))
        assert inactive.status_code == 422 and _code(inactive) == "ROUTINE_TARGET_INACTIVE"

        updated = await client.patch(f"{base}/{routine['id']}", json={"schedule": "30 9 * * 1-5",
                                                                       "title": "Backups (dias úteis)"})
        assert updated.status_code == 200, updated.text
        assert updated.json()["schedule"] == "30 9 * * 1-5" and updated.json()["updated_by"] == ops["actor"]
        not_owned = await client.patch(f"{base}/{admin_routine}", json={"enabled": False})
        assert not_owned.status_code == 403 and _code(not_owned) == "ROUTINE_NOT_OWNED"
        not_owned = await client.delete(f"{base}/{admin_routine}")
        assert not_owned.status_code == 403 and _code(not_owned) == "ROUTINE_NOT_OWNED"

        run = await client.post(f"{base}/{routine['id']}:run-now")
        assert run.status_code == 201, run.text
        runs = await client.get("/api/v1/operations/agent/runs", params={"routine_id": routine["id"]})
        assert [r["id"] for r in runs.json()] == [run.json()["id"]]
        async with AsyncSessionLocal() as db:  # Out of any real queue.
            demand = await db.get(AgentDemand, uuid.UUID(run.json()["demand_id"]))
            demand.scheduled_at = datetime.now(timezone.utc) + timedelta(days=365)
            await db.commit()

        deleted = await client.delete(f"{base}/{routine['id']}")
        assert deleted.status_code == 204
    async with AsyncSessionLocal() as db:
        events = (await db.execute(select(AuditEvent).where(
            AuditEvent.entity_type == "agent_routine",
            AuditEvent.entity_id == uuid.UUID(routine["id"])).order_by(AuditEvent.created_at))).scalars().all()
        assert [e.event_type for e in events] == ["routine_created", "routine_updated", "routine_run_now",
                                                  "routine_deleted"]
        assert {e.actor for e in events} == {ops["actor"]}
        assert events[1].payload["changes"]["schedule"] == ["0 8 * * *", "30 9 * * 1-5"]
        assert await db.get(AgentRoutine, uuid.UUID(routine["id"])) is None
        assert await db.get(AgentRoutine, uuid.UUID(admin_routine)) is not None


@pytest.mark.asyncio
async def test_agent_routine_bounded_by_charter(ops_world):
    w, ops = ops_world, ops_world.ops
    base = "/api/v1/operations/agent/routines"
    async with w.client(ops["headers"]) as client:
        # 8 runs a day fits a budget of 10...
        eight = await client.post(base, json=_routine(ops["target"], schedule="0 8-15 * * *"))
        assert eight.status_code == 201, eight.text
        # ...3 more on the same day does not.
        three = await client.post(base, json=_routine(ops["target"], schedule="0 18-20 * * *"))
        assert three.status_code == 422 and _code(three) == "ROUTINE_EXCEEDS_CHARTER"
        assert three.json()["detail"]["busiest_day_runs"] == 11
        # Disabled, it is allowed; enabling it later is refused.
        paused = await client.post(base, json=_routine(ops["target"], schedule="0 18-20 * * *", enabled=False))
        assert paused.status_code == 201, paused.text
        enable = await client.patch(f"{base}/{paused.json()['id']}", json={"enabled": True})
        assert enable.status_code == 422 and _code(enable) == "ROUTINE_EXCEEDS_CHARTER"
        # Rescheduling the first routine counts it once, not twice.
        smaller = await client.patch(f"{base}/{eight.json()['id']}", json={"schedule": "0 8-14 * * *"})
        assert smaller.status_code == 200, smaller.text
        assert (await client.patch(f"{base}/{paused.json()['id']}", json={"enabled": True})).status_code == 200


@pytest.mark.asyncio
async def test_routine_mcp_tools_and_delegation_grant(ops_world, mcp_as):  # noqa: F811
    w, ops = ops_world, ops_world.ops
    mcp_as(ops["headers"]["Authorization"][7:])
    created = await factory_server.create_routine(str(ops["target"]), "Relatório", "Resuma o dia.", "0 18 * * *")
    assert created["created_by"] == ops["actor"]
    updated = await factory_server.update_routine(created["id"], enabled=False)
    assert updated["enabled"] is False
    assert any(r["id"] == created["id"] for r in await factory_server.list_routines(str(ops["target"])))
    assert await factory_server.list_routine_runs(created["id"]) == []
    assert (await factory_server.delete_routine(created["id"]))["deleted"] is True

    mcp_as(ops["plain"]["Authorization"][7:])
    with pytest.raises(factory_server.FactoryError, match=r"\(403\)"):
        await factory_server.list_routines()

    # An admin can grant the action through the governed delegation route.
    async with w.client() as client:
        grant = await client.post("/api/v1/governed/authority-delegations", json={
            "grantee_agent_id": str(ops["target"]), "allowed_actions": ["operations.routines.manage"],
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()})
        assert grant.status_code == 201, grant.text
        async with AsyncSessionLocal() as db:
            await db.execute(text("DELETE FROM company.notifications WHERE event_key = :k"),
                             {"k": f"delegation:granted:{grant.json()['id']}"})
            await db.execute(text("DELETE FROM company.audit_events WHERE entity_id = :i"),
                             {"i": uuid.UUID(grant.json()["id"])})
            await db.commit()


def test_tools_registered():
    tools = factory_server.mcp._tool_manager._tools
    assert {"request_marcelo_approval", "list_routines", "create_routine", "update_routine", "delete_routine",
            "run_routine_now", "list_routine_runs"} <= tools.keys()
