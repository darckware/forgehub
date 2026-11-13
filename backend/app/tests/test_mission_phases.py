"""Mission phases (docs/architecture/MISSION_PHASES_PLAN.md, 2026-11-12).

Runs only against the isolated test database; every route, guard and query is
real. Each test builds its own product, mission and agents and removes them.
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.core import command_receipts
from app.core.config import settings
from app.core.mission import transition_preconditions
from app.core.mission_phases import mark_phase_started, phase_plan_items
from app.core.mission_plan import plan_checks
from app.core.task_baseline_guard import TaskBaselineBlocked, assert_task_baseline_current
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.backlog import PlanningItem
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.mission import MissionProjectLink, ProjectMission
from app.db.models.notification import Notification
from app.db.models.orchestration import ProjectAgentMembership, TaskExecutionReview
from app.db.models.project import Project
from app.db.models.task import ProjectTask, TaskDependency
from app.mcp import factory_server
from app.tests.test_mission_base import (  # noqa: F401  (_clean_stale_mission_fixtures is an autouse fixture)
    World,
    _assign,
    _clean_stale_mission_fixtures,
    _force,
    _member,
    _task,
)
from app.tests.test_mission_cycle import _verified_execution
from app.tests.test_mission_mcp import mcp_as  # noqa: F401
from app.tests.test_task_baseline_guard import Mission


@pytest_asyncio.fixture
async def world(admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "MISSION_TOOLS_ENABLED", True)
    command_receipts.agent_write_limiter.reset()
    w = World(admin_headers)
    await w.setup()
    yield w
    projects = ("SELECT p.id FROM company.projects p JOIN company.product_versions v "
                f"ON v.id = p.product_version_id WHERE v.product_id = '{w.product_id}'")
    tasks = ("SELECT id FROM company.project_tasks WHERE planning_item_id IN "
             f"(SELECT id FROM company.planning_items WHERE project_id IN ({projects}))")
    async with AsyncSessionLocal() as db:
        for statement in (
            f"DELETE FROM company.notifications n USING company.mission_project_links l "
            f"WHERE n.event_key LIKE 'mission-phase:' || l.id::text || ':%' "
            f"AND l.mission_project_id IN ({projects})",
            f"UPDATE company.mission_project_links SET homologation_demand_id = NULL "
            f"WHERE mission_project_id IN ({projects})",
            f"DELETE FROM company.agent_demands WHERE project_id IN ({projects})",
            f"DELETE FROM company.agent_demands WHERE origin_id IN ({tasks})",
            f"UPDATE company.project_missions SET current_baseline_id = NULL WHERE project_id IN ({projects})",
            f"DELETE FROM company.plan_baseline_items WHERE task_id IN ({tasks})",
            f"DELETE FROM company.project_plans WHERE project_id IN ({projects})",
        ):
            await db.execute(text(statement))
        if w.agent_ids:
            await db.execute(text("DELETE FROM company.agent_command_receipts WHERE principal_id = ANY(:ids)"),
                             {"ids": list(w.agent_ids)})
        await db.execute(text("DELETE FROM company.agent_command_receipts WHERE idempotency_key LIKE :k"),
                         {"k": f"phases-{w.tag}-%"})
        await db.commit()
    await w.cleanup()
    command_receipts.agent_write_limiter.reset()


def _key(world: World) -> str:
    return f"phases-{world.tag}-{uuid.uuid4().hex}"


def _code(response) -> str | None:
    detail = response.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


async def _mission(world: World) -> dict:
    return await world.create_mission(
        working_directory_path=f"/srv/forgehub-test/phases-{world.tag}-{uuid.uuid4().hex[:6]}")


async def _call(world: World, method: str, path: str, body=None, headers=None, **params):
    async with world.client(headers) as client:
        return await client.request(method, path, json=body, params=params or None)


async def _create_phase(world: World, project_id, name="Estrutura", objective="Navegação e design system, sem regras",
                        headers=None, **extra):
    return await _call(world, "POST", f"/api/v1/missions/{project_id}/phases",
                       {"name": name, "objective": objective, **extra}, headers)


async def _phase_row(phase_id) -> MissionProjectLink:
    async with AsyncSessionLocal() as db:
        return await db.get(MissionProjectLink, uuid.UUID(str(phase_id)))


async def _set_phase(phase_id, **fields) -> None:
    async with AsyncSessionLocal() as db:
        phase = await db.get(MissionProjectLink, uuid.UUID(str(phase_id)))
        for key, value in fields.items():
            setattr(phase, key, value)
        await db.commit()


async def _set_task(task_id, **fields) -> None:
    async with AsyncSessionLocal() as db:
        task = await db.get(ProjectTask, task_id)
        for key, value in fields.items():
            setattr(task, key, value)
        await db.commit()


async def _item_with_tasks(project_id, titles: list[str]) -> tuple[uuid.UUID, list[ProjectTask]]:
    async with AsyncSessionLocal() as db:
        item = PlanningItem(title=f"item {titles[0]}", item_type="feature", project_id=uuid.UUID(str(project_id)))
        db.add(item)
        await db.flush()
        tasks = [ProjectTask(planning_item_id=item.id, title=t) for t in titles]
        db.add_all(tasks)
        await db.commit()
        for task in tasks:
            await db.refresh(task)
        return item.id, tasks


async def _agent(world: World, label: str, runtime: str) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        agent = Agent(name=f"mission-test-{label}-{world.tag}-{uuid.uuid4().hex[:4]}", runtime_type=runtime)
        db.add(agent)
        await db.commit()
        world.agent_ids.append(agent.id)
        return agent.id


async def _edges(task_ids) -> set[tuple[uuid.UUID, uuid.UUID]]:
    async with AsyncSessionLocal() as db:
        return {(d.task_id, d.depends_on_task_id) for d in (await db.execute(
            select(TaskDependency).where(TaskDependency.task_id.in_(list(task_ids))))).scalars()}


# ---------------------------------------------------------------------------
# Create / update / reorder / delete and freezing
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_reorder_delete_and_freeze(world):
    mission = await _mission(world)
    pid = mission["project_id"]
    orchestrator = uuid.UUID(mission["orchestrator_agent_id"])

    first = await _create_phase(world, pid)
    assert first.status_code == 201, first.text
    second = await _create_phase(world, pid, name="Telas", objective="Somente as telas, sem código")
    assert second.status_code == 201, second.text
    phases = second.json()["phases"]
    assert [(p["position"], p["name"], p["phase_status"]) for p in phases] == [
        (1, "Estrutura", "planned"), (2, "Telas", "planned")]
    assert second.json()["editable"] is True
    p1, p2 = phases[0]["phase_id"], phases[1]["phase_id"]
    async with AsyncSessionLocal() as db:
        executor = await db.get(Project, uuid.UUID(phases[1]["executor_project_id"]))
        mission_project = await db.get(Project, uuid.UUID(pid))
        assert executor.name == f"{mission_project.name} · Fase 2 · Telas"
        assert executor.working_directory_path == mission_project.working_directory_path
        assert executor.product_version_id == mission_project.product_version_id
        coordinator = (await db.execute(select(ProjectAgentMembership).where(
            ProjectAgentMembership.project_id == executor.id))).scalar_one()
        assert (coordinator.agent_id, coordinator.role) == (orchestrator, "coordinator")
        assert await db.scalar(select(AuditEvent.id).where(
            AuditEvent.entity_id == uuid.UUID(pid), AuditEvent.event_type == "mission_phase_created").limit(1))

    # Rename and reorder; the project names follow.
    renamed = await _call(world, "PATCH", f"/api/v1/missions/{pid}/phases/{p2}", {"name": "Telas sem código"})
    assert renamed.status_code == 200 and renamed.json()["phases"][1]["name"] == "Telas sem código"
    bad = await _call(world, "POST", f"/api/v1/missions/{pid}/phases:reorder", {"phase_ids": [p2]})
    assert bad.status_code == 422 and _code(bad) == "PHASE_SET_MISMATCH"
    reordered = await _call(world, "POST", f"/api/v1/missions/{pid}/phases:reorder", {"phase_ids": [p2, p1]})
    assert reordered.status_code == 200, reordered.text
    assert [p["phase_id"] for p in reordered.json()["phases"]] == [p2, p1]
    async with AsyncSessionLocal() as db:
        assert (await db.get(Project, uuid.UUID(phases[1]["executor_project_id"]))).name.endswith(
            "· Fase 1 · Telas sem código")

    # A phase with a planning item is not removed; an empty one is, and the rest renumber.
    await _item_with_tasks(phases[0]["executor_project_id"], ["t"])
    not_empty = await _call(world, "DELETE", f"/api/v1/missions/{pid}/phases/{p1}")
    assert not_empty.status_code == 409 and _code(not_empty) == "PHASE_NOT_EMPTY"
    removed = await _call(world, "DELETE", f"/api/v1/missions/{pid}/phases/{p2}")
    assert removed.status_code == 200, removed.text
    assert [(p["phase_id"], p["position"]) for p in removed.json()["phases"]] == [(p1, 1)]
    async with AsyncSessionLocal() as db:
        assert await db.get(Project, uuid.UUID(phases[1]["executor_project_id"])) is None

    # The orchestrator edits with its delegation and a key; another agent cannot.
    orch_h = await world.agent_token(orchestrator, ["mission.orchestrate"], uuid.UUID(pid))
    no_key = await _create_phase(world, pid, name="Regras", headers=orch_h)
    assert no_key.status_code == 422 and _code(no_key) == "IDEMPOTENCY_KEY_REQUIRED"
    key = _key(world)
    by_agent = await _create_phase(world, pid, name="Regras", headers=orch_h, idempotency_key=key)
    assert by_agent.status_code == 201, by_agent.text
    replay = await _create_phase(world, pid, name="Regras", headers=orch_h, idempotency_key=key)
    assert replay.status_code == 200 and replay.headers.get("idempotent-replay") == "true"
    assert len(replay.json()["phases"]) == 2
    stranger = await world.agent_token(await world.agent("x"), ["mission.orchestrate"], uuid.UUID(pid))
    refused = await _create_phase(world, pid, name="X", headers=stranger, idempotency_key=_key(world))
    assert refused.status_code == 403

    # Frozen outside draft/planning, or once a baseline exists.
    await _force(pid, state="active")
    for response in (
        await _create_phase(world, pid, name="late"),
        await _call(world, "PATCH", f"/api/v1/missions/{pid}/phases/{p1}", {"objective": "x"}),
        await _call(world, "DELETE", f"/api/v1/missions/{pid}/phases/{p1}"),
    ):
        assert response.status_code == 409 and _code(response) == "MISSION_PHASES_FROZEN", response.text
    listed = await _call(world, "GET", f"/api/v1/missions/{pid}/phases")
    assert listed.status_code == 200 and listed.json()["editable"] is False


# ---------------------------------------------------------------------------
# tasks:sequence
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sequence_builds_chain_and_keeps_outside_dependencies(world):
    mission = await _mission(world)
    pid = mission["project_id"]
    phase = (await _create_phase(world, pid)).json()["phases"][0]
    item_id, (t1, t2, t3) = await _item_with_tasks(phase["executor_project_id"], ["a", "b", "c"])
    outside = await _task(phase["executor_project_id"], "outside")
    async with AsyncSessionLocal() as db:
        db.add(TaskDependency(task_id=t1.id, depends_on_task_id=outside.id))
        db.add(TaskDependency(task_id=t1.id, depends_on_task_id=t2.id))  # an old edge inside the item
        await db.commit()

    url = f"/api/v1/missions/{pid}/plannings/{item_id}/tasks:sequence"
    mismatch = await _call(world, "POST", url, {"task_ids": [str(t1.id), str(t2.id)]})
    assert mismatch.status_code == 422 and _code(mismatch) == "TASK_SET_MISMATCH"
    done = await _call(world, "POST", url, {"task_ids": [str(t3.id), str(t2.id), str(t1.id)]})
    assert done.status_code == 200, done.text
    assert await _edges([t1.id, t2.id, t3.id]) == {(t2.id, t3.id), (t1.id, t2.id), (t1.id, outside.id)}
    async with AsyncSessionLocal() as db:
        positions = {t.id: t.position for t in (await db.execute(
            select(ProjectTask).where(ProjectTask.id.in_([t1.id, t2.id, t3.id])))).scalars()}
    assert positions == {t3.id: 1, t2.id: 2, t1.id: 3}
    view = done.json()["phases"][0]["planning_items"]
    item = next(i for i in view if i["planning_item_id"] == str(item_id))
    assert item["sequenced"] is True and [t["title"] for t in item["tasks"]] == ["c", "b", "a"]
    assert item["tasks"][2]["depends_on"] == sorted([t2.number, outside.number])

    # A planning item of another mission is not found; a frozen task refuses.
    other = await _mission(world)
    other_item, _ = await _item_with_tasks(other["project_id"], ["z"])
    assert _code(await _call(world, "POST", f"/api/v1/missions/{pid}/plannings/{other_item}/tasks:sequence",
                             {"task_ids": [str(uuid.uuid4())]})) == "PLANNING_ITEM_NOT_FOUND"
    await _force(pid, state="active")
    m = Mission(world, {"project_id": pid}, None, None)
    await m.baseline([t1.id, t2.id, t3.id])
    frozen = await _call(world, "POST", url, {"task_ids": [str(t1.id), str(t2.id), str(t3.id)]})
    assert frozen.status_code == 409 and _code(frozen) == "TASK_IN_BASELINE"


# ---------------------------------------------------------------------------
# Plan checks
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_plan_checks_for_phases(world):
    mission = await _mission(world)
    pid = mission["project_id"]

    async def check():
        async with AsyncSessionLocal() as db:
            m = await db.get(ProjectMission, uuid.UUID(pid))
            unmet, warnings = await phase_plan_items(db, m)
            return {u["code"] for u in unmet}, {w["code"] for w in warnings}

    assert await check() == ({"PHASES_MISSING"}, set())
    phase = (await _create_phase(world, pid, objective=None)).json()["phases"][0]
    assert await check() == ({"PHASE_OBJECTIVE_MISSING", "PHASE_WITHOUT_TASKS"}, set())
    item_id, (a, b) = await _item_with_tasks(phase["executor_project_id"], ["a", "b"])
    single, _ = await _item_with_tasks(phase["executor_project_id"], ["alone"])  # one task is sequenced
    assert await check() == ({"PHASE_OBJECTIVE_MISSING", "TASKS_NOT_SEQUENCED"}, set())
    await _call(world, "PATCH", f"/api/v1/missions/{pid}/phases/{phase['phase_id']}", {"objective": "Entrega X"})
    # Positions without the chain are not a sequence.
    await _set_task(a.id, position=1)
    await _set_task(b.id, position=2)
    assert await check() == ({"TASKS_NOT_SEQUENCED"}, set())
    await _call(world, "POST", f"/api/v1/missions/{pid}/plannings/{item_id}/tasks:sequence",
                {"task_ids": [str(a.id), str(b.id)]})
    # A cancelled task does not count.
    await _set_task(b.id, status="cancelled")
    assert await check() == (set(), set())
    # A mission-level task is allowed, only warned about.
    await _task(pid, "mission-level")
    assert await check() == (set(), {"TASK_OUTSIDE_PHASE"})

    async with AsyncSessionLocal() as db:
        m = await db.get(ProjectMission, uuid.UUID(pid))
        checks = {c["key"]: c for c in await plan_checks(db, m, [a.id], None)}
    assert checks["phases"]["status"] == "passed"
    assert checks["tasks_in_phases"]["status"] == "warning" and checks["tasks_in_phases"]["passed"] is True
    # The draft_plan exit reads the phase's tasks too (their environment).
    await _force(pid, state="planning", planning_stage="draft_plan")
    async with world.client() as client:
        response = await client.post(f"/api/v1/missions/{pid}/planning:advance", json={
            "to": "auto_check", "reason": "go", "idempotency_key": uuid.uuid4().hex})
    unmet = response.json()["detail"]["unmet"]
    assert any(u["code"] == "TASK_ENVIRONMENT_MISSING" and u.get("task_id") == str(a.id) for u in unmet), unmet
    assert not any(u["code"].startswith("PHASE") or u["code"] == "TASKS_NOT_SEQUENCED" for u in unmet)


# ---------------------------------------------------------------------------
# Dispatch gate
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dispatch_gate_locks_later_phases_and_closes_homologating_ones(world):
    mission = await _mission(world)
    pid = mission["project_id"]
    first = (await _create_phase(world, pid)).json()["phases"][0]
    second = (await _create_phase(world, pid, name="Telas")).json()["phases"][1]
    t1 = await _task(first["executor_project_id"], "phase 1 work")
    t2 = await _task(second["executor_project_id"], "phase 2 work")
    await _force(pid, state="active")
    await Mission(world, {"project_id": pid}, None, None).baseline([t1.id, t2.id])

    async def code(task):
        async with AsyncSessionLocal() as db:
            try:
                await assert_task_baseline_current(db, await db.get(ProjectTask, task.id))
            except TaskBaselineBlocked as exc:
                return exc.code, exc.detail
        return None, None

    assert (await code(t1))[0] is None
    locked, detail = await code(t2)
    assert locked == "PHASE_LOCKED" and [p["position"] for p in detail["blocking_phases"]] == [1]

    # The first admitted dispatch starts the phase.
    async with AsyncSessionLocal() as db:
        await mark_phase_started(db, await db.get(ProjectTask, t1.id))
        await db.commit()
    assert (await _phase_row(first["phase_id"])).phase_status == "in_progress"

    for status in ("homologating", "awaiting_approval"):
        await _set_phase(first["phase_id"], phase_status=status)
        assert (await code(t1))[0] == "PHASE_CLOSED", status
        assert (await code(t2))[0] == "PHASE_LOCKED", status
    await _set_phase(first["phase_id"], phase_status="returned")
    assert (await code(t1))[0] is None
    await _set_phase(first["phase_id"], phase_status="approved")
    assert (await code(t1))[0] == "PHASE_CLOSED"
    assert (await code(t2))[0] is None

    # active -> verifying needs every phase approved.
    async with AsyncSessionLocal() as db:
        m = await db.get(ProjectMission, uuid.UUID(pid))
        unmet = {u["code"]: u for u in await transition_preconditions(db, m, "verifying")}
    assert [p["position"] for p in unmet["PHASES_NOT_APPROVED"]["phases"]] == [2]
    await _set_phase(second["phase_id"], phase_status="approved")
    async with AsyncSessionLocal() as db:
        m = await db.get(ProjectMission, uuid.UUID(pid))
        assert "PHASES_NOT_APPROVED" not in {u["code"] for u in await transition_preconditions(db, m, "verifying")}


# ---------------------------------------------------------------------------
# Homologation and Marcelo's decision
# ---------------------------------------------------------------------------
async def _homologation_world(world: World):
    mission = await _mission(world)
    pid = mission["project_id"]
    orchestrator = uuid.UUID(mission["orchestrator_agent_id"])
    phase = (await _create_phase(world, pid)).json()["phases"][0]
    executor_project = phase["executor_project_id"]
    executor = await world.agent("exec")
    task = await _task(executor_project, "phase work")
    await _assign(task.id, executor, await _member(executor_project, executor))
    reviewer = await world.agent("rev")
    reviewer_membership = await _member(executor_project, reviewer, role="reviewer", can_review=True)
    execution = await _verified_execution(task, "file:README.md")
    async with AsyncSessionLocal() as db:
        db.add(TaskExecutionReview(execution_id=execution, reviewer_membership_id=reviewer_membership,
                                   status="approved", feedback="ok"))
        await db.commit()
    await _force(pid, state="active")
    return pid, orchestrator, phase, task, executor, reviewer


@pytest.mark.asyncio
async def test_homologation_request_refusals(world):
    pid, orchestrator, phase, task, executor, reviewer = await _homologation_world(world)
    url = f"/api/v1/missions/{pid}/phases/{phase['phase_id']}:request-homologation"
    homologator = await world.agent("hom")
    await _member(pid, homologator, role="homologation")

    open_tasks = await _call(world, "POST", url, {"homologator_agent_id": str(homologator)})
    assert open_tasks.status_code == 409 and _code(open_tasks) == "PHASE_TASKS_OPEN"
    assert [t["number"] for t in open_tasks.json()["detail"]["tasks"]] == [task.number]
    await _set_task(task.id, status="done")

    hermes = await _agent(world, "hermes-hom", "hermes")
    await _member(pid, hermes, role="homologation")
    not_external = await _call(world, "POST", url, {"homologator_agent_id": str(hermes)})
    assert not_external.status_code == 422 and _code(not_external) == "HOMOLOGATOR_NOT_EXTERNAL"
    outsider = await world.agent("no-member")
    assert _code(await _call(world, "POST", url, {"homologator_agent_id": str(outsider)})) == "HOMOLOGATOR_NOT_MEMBER"
    for insider in (executor, reviewer):
        await _member(pid, insider, role="homologation")
        response = await _call(world, "POST", url, {"homologator_agent_id": str(insider)})
        assert response.status_code == 409 and _code(response) == "HOMOLOGATOR_NOT_INDEPENDENT", response.text

    # An agent other than the orchestrator cannot request it.
    stranger = await world.agent_token(homologator, ["mission.orchestrate"], uuid.UUID(pid))
    assert (await _call(world, "POST", url, {"homologator_agent_id": str(homologator),
                                             "idempotency_key": _key(world)}, stranger)).status_code == 403

    sent = await _call(world, "POST", url, {"homologator_agent_id": str(homologator)})
    assert sent.status_code == 200, sent.text
    row = sent.json()["phases"][0]
    assert row["phase_status"] == "homologating" and row["homologator"]["agent_id"] == str(homologator)
    async with AsyncSessionLocal() as db:
        demand = await db.get(AgentDemand, uuid.UUID(sent.json()["demand_id"]))
        mission_project = await db.get(Project, uuid.UUID(pid))
    assert (demand.target_agent_id, demand.from_agent_id, demand.fixed_agent) == (homologator, orchestrator, True)
    assert demand.origin_type == "task" and demand.origin_id is None and demand.task_execution_id is None
    assert demand.working_path == mission_project.working_directory_path
    assert "report_phase_homologation" in demand.body and f"Task #{task.number}" in demand.body
    assert "file:README.md" in demand.body
    # Not twice.
    again = await _call(world, "POST", url, {"homologator_agent_id": str(homologator)})
    assert again.status_code == 409 and _code(again) == "PHASE_STATE_CHANGED"


@pytest.mark.asyncio
async def test_report_and_marcelo_decision(world):
    pid, orchestrator, phase, task, _executor, _reviewer = await _homologation_world(world)
    await _set_task(task.id, status="done")
    phase_id = phase["phase_id"]
    homologator = await world.agent("hom")
    await _member(pid, homologator, role="homologation")
    hom_h = await world.agent_token(homologator, None)
    other_h = await world.agent_token(await world.agent("other"), None)
    orch_h = await world.agent_token(orchestrator, ["mission.orchestrate"], uuid.UUID(pid))
    base = f"/api/v1/missions/{pid}/phases/{phase_id}"

    async def request():
        response = await _call(world, "POST", f"{base}:request-homologation", {"homologator_agent_id": str(homologator)})
        assert response.status_code == 200, response.text

    async def report(verdict, evidence=("git:abc123",), headers=hom_h):
        return await _call(world, "POST", f"{base}:report-homologation", {
            "verdict": verdict, "summary": "Testei a navegação", "evidence": list(evidence),
            "idempotency_key": _key(world)}, headers)

    await request()
    assert (await report("approved", headers=other_h)).status_code == 403
    assert (await report("approved", headers=world.admin)).status_code == 403
    no_evidence = await report("approved", evidence=())
    assert no_evidence.status_code == 422 and _code(no_evidence) == "EVIDENCE_REQUIRED"
    approved = await report("approved")
    assert approved.status_code == 200, approved.text
    row = approved.json()["phases"][0]
    assert (row["phase_status"], row["homologation_verdict"], row["homologation_evidence"]) == (
        "awaiting_approval", "approved", "git:abc123")
    async with AsyncSessionLocal() as db:
        notice = (await db.execute(select(Notification).where(
            Notification.event_key.like(f"mission-phase:{phase_id}:homologated:%")))).scalar_one()
    assert "aguardando sua aprovação" in notice.title and f"/missions/{pid}" in notice.message
    assert _code(await report("approved")) == "PHASE_STATE_CHANGED"

    # Only Marcelo decides; returning needs a reason and messages the orchestrator.
    by_agent = await _call(world, "POST", f"{base}:approve", {"idempotency_key": _key(world)}, orch_h)
    assert by_agent.status_code == 403 and _code(by_agent) == "PHASE_DECISION_HUMAN_ONLY"
    assert (await _call(world, "POST", f"{base}:return", {"reason": ""})).status_code == 422
    returned = await _call(world, "POST", f"{base}:return", {"reason": "Faltou o menu lateral"})
    assert returned.status_code == 200 and returned.json()["phases"][0]["phase_status"] == "returned"
    async with AsyncSessionLocal() as db:
        demand = await db.get(AgentDemand, uuid.UUID(returned.json()["demand_id"]))
    assert demand.target_agent_id == orchestrator and "Faltou o menu lateral" in demand.body

    # Homologator rejects: back to the orchestrator with its findings.
    await request()
    rejected = await report("rejected", evidence=())
    assert rejected.status_code == 200 and rejected.json()["phases"][0]["phase_status"] == "returned"
    async with AsyncSessionLocal() as db:
        demand = await db.get(AgentDemand, uuid.UUID(rejected.json()["demand_id"]))
    assert (demand.from_agent_id, demand.target_agent_id) == (homologator, orchestrator)
    assert "Testei a navegação" in demand.body

    # Approve: the last phase tells the orchestrator the mission can go to verifying.
    await request()
    await report("approved")
    stale = await _call(world, "POST", f"{base}:approve", {"expected_phase_status": "homologating"})
    assert stale.status_code == 409 and _code(stale) == "PHASE_STATE_CHANGED"
    decided = await _call(world, "POST", f"{base}:approve", {"reason": "ok"})
    assert decided.status_code == 200, decided.text
    row = decided.json()["phases"][0]
    assert row["phase_status"] == "approved" and row["decided_by"]
    async with AsyncSessionLocal() as db:
        demand = await db.get(AgentDemand, uuid.UUID(decided.json()["demand_id"]))
        events = set((await db.execute(select(AuditEvent.event_type).where(
            AuditEvent.entity_id == uuid.UUID(pid)))).scalars())
    assert "verifying" in demand.body
    assert {"mission_phase_homologation_requested", "mission_phase_homologation_reported",
            "mission_phase_returned", "mission_phase_approved"} <= events


# ---------------------------------------------------------------------------
# Role, board and MCP
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_homologation_role_only_for_external_runtimes(world):
    mission = await _mission(world)
    pid = mission["project_id"]
    hermes = await _agent(world, "hermes", "hermes")
    codex = await _agent(world, "codex", "codex")
    url = f"/api/v1/missions/{pid}/members:apply"
    refused = await _call(world, "POST", url, {"idempotency_key": _key(world), "operations": [
        {"op": "add", "agent_id": str(hermes), "role": "homologation"}]})
    assert refused.status_code == 422 and _code(refused) == "MEMBER_RULE_VIOLATION"
    assert {v["code"] for v in refused.json()["detail"]["violations"]} == {"HOMOLOGATION_REQUIRES_EXTERNAL_RUNTIME"}
    accepted = await _call(world, "POST", url, {"idempotency_key": _key(world), "operations": [
        {"op": "add", "agent_id": str(codex), "role": "homologation"}]})
    assert accepted.status_code == 200, accepted.text


@pytest.mark.asyncio
async def test_board_and_mcp_tools(world, mcp_as):  # noqa: F811
    mission = await _mission(world)
    pid = mission["project_id"]
    orchestrator = uuid.UUID(mission["orchestrator_agent_id"])
    token = (await world.agent_token(orchestrator, ["mission.orchestrate"], uuid.UUID(pid)))["Authorization"][7:]
    mcp_as(token)
    created = await factory_server.create_mission_phase(pid, "Estrutura", "Navegação, sem regras", _key(world))
    assert created["replayed"] is False and created["phases"][0]["position"] == 1
    await factory_server.create_mission_phase(pid, "Telas", "Somente telas", _key(world))
    updated = await factory_server.update_mission_phase(pid, "2", _key(world), objective="Telas sem código")
    assert updated["phases"][1]["objective"] == "Telas sem código"
    reordered = await factory_server.reorder_mission_phases(pid, ["2", "1"], _key(world))
    assert [p["name"] for p in reordered["phases"]] == ["Telas", "Estrutura"]
    listed = await factory_server.list_mission_phases(pid)
    executor_project = listed["phases"][0]["executor_project_id"]
    item_id, (a, b) = await _item_with_tasks(executor_project, ["a", "b"])
    sequenced = await factory_server.sequence_planning_tasks(pid, str(item_id), [str(b.number), str(a.id)],
                                                             _key(world))
    item = sequenced["phases"][0]["planning_items"][0]
    assert [t["title"] for t in item["tasks"]] == ["b", "a"] and item["sequenced"] is True

    async with world.client() as client:
        board = (await client.get(f"/api/v1/missions/{pid}/executions")).json()
    assert [p["name"] for p in board["phases"]] == ["Telas", "Estrutura"]
    assert board["phases"][0]["planning_items"][0]["tasks"][1]["depends_on"] == [b.number]


# ---------------------------------------------------------------------------
# Review fixes: legacy links, re-sending a homologation, sub-agents, names, report guards
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_legacy_executor_link_is_not_a_phase_and_hash_is_unchanged(world):
    """A mission with only a plain executor link (as every link was before
    phases) hashes exactly as before: no `phases` key, the baseline items
    match the pre-phases formula, and dispatch is not refused."""
    from app.core.governed_approval import canonical_hash
    from app.core.plan_baseline import mission_content_part, task_content_part
    from app.db.models.project import PlanBaselineItem
    from app.tests.test_mission_base import _brief

    executor = await world.common_project()
    mission = await world.create_mission(
        brief_artifact_id=str(await _brief(world)), executor_project_ids=[executor["id"]],
        working_directory_path=f"/srv/forgehub-test/phases-{world.tag}-legacy")
    pid = mission["project_id"]
    async with AsyncSessionLocal() as db:
        link = (await db.execute(select(MissionProjectLink).where(
            MissionProjectLink.mission_project_id == uuid.UUID(pid)))).scalar_one()
    assert (link.is_phase, link.position, link.name) == (False, None, None)
    legacy_task = await _task(executor["id"], "legacy work")
    own_task = await _task(pid, "mission work")
    await _force(pid, state="active")
    baseline_id = await Mission(world, {"project_id": pid}, None, None).baseline([legacy_task.id, own_task.id])

    async with AsyncSessionLocal() as db:
        m = await db.get(ProjectMission, uuid.UUID(pid))
        part = await mission_content_part(db, m)
        assert set(part) == {"brief_artifact_id", "brief_artifact_version_id", "criteria"}
        stored = {i.task_id: i.content_hash for i in (await db.execute(select(PlanBaselineItem).where(
            PlanBaselineItem.baseline_id == baseline_id))).scalars()}
        for task in (legacy_task, own_task):
            fresh = await db.get(ProjectTask, task.id)
            # The formula before phases existed: task part + {brief, criteria}.
            before = canonical_hash({"task": await task_content_part(db, fresh), "mission": {
                "brief_artifact_id": m.brief_artifact_id,
                "brief_artifact_version_id": part["brief_artifact_version_id"], "criteria": part["criteria"]}})
            assert stored[task.id] == before
            await assert_task_baseline_current(db, fresh)  # no PHASE_* and no TASK_CONTENT_CHANGED
        assert "PHASES_NOT_APPROVED" not in {u["code"] for u in await transition_preconditions(db, m, "verifying")}
    listed = await _call(world, "GET", f"/api/v1/missions/{pid}/phases")
    assert listed.json()["phases"] == []
    # A plain link is not reachable through the phase routes.
    missing = await _call(world, "POST", f"/api/v1/missions/{pid}/phases/{link.id}:request-homologation",
                          {"homologator_agent_id": str(uuid.uuid4())})
    assert missing.status_code == 404 and _code(missing) == "PHASE_NOT_FOUND"


@pytest.mark.asyncio
async def test_replace_homologation_and_sub_agent_independence(world):
    from app.db.models.agent import SubAgent

    pid, _orchestrator, phase, task, _executor, _reviewer = await _homologation_world(world)
    await _set_task(task.id, status="done")
    url = f"/api/v1/missions/{pid}/phases/{phase['phase_id']}:request-homologation"

    # A sub-agent reviewed a task of the phase: its parent is not independent.
    parent = await world.agent("parent")
    async with AsyncSessionLocal() as db:
        sub = SubAgent(agent_id=parent, name=f"mission-test-sub-{world.tag}")
        db.add(sub)
        await db.flush()
        membership = ProjectAgentMembership(project_id=uuid.UUID(phase["executor_project_id"]), sub_agent_id=sub.id,
                                            role="reviewer", status="active", can_review=True)
        db.add(membership)
        await db.flush()
        execution = (await db.execute(text("SELECT id FROM company.task_executions WHERE task_id = :t"),
                                      {"t": str(task.id)})).scalar_one()
        db.add(TaskExecutionReview(execution_id=execution, reviewer_membership_id=membership.id,
                                   status="approved", feedback="ok"))
        await db.commit()
    await _member(pid, parent, role="homologation")
    refused = await _call(world, "POST", url, {"homologator_agent_id": str(parent)})
    assert refused.status_code == 409 and _code(refused) == "HOMOLOGATOR_NOT_INDEPENDENT", refused.text
    assert refused.json()["detail"]["as_reviewer"] is True

    first_h, second_h = await world.agent("hom-1"), await world.agent("hom-2")
    await _member(pid, first_h, role="homologation")
    await _member(pid, second_h, role="homologation")
    first = await _call(world, "POST", url, {"homologator_agent_id": str(first_h)})
    assert first.status_code == 200, first.text
    # Without replace a homologating phase is not re-sent.
    assert _code(await _call(world, "POST", url, {"homologator_agent_id": str(second_h)})) == "PHASE_STATE_CHANGED"
    second = await _call(world, "POST", url, {"homologator_agent_id": str(second_h), "replace": True})
    assert second.status_code == 200, second.text
    assert second.json()["phases"][0]["homologator"]["agent_id"] == str(second_h)
    async with AsyncSessionLocal() as db:
        old = await db.get(AgentDemand, uuid.UUID(first.json()["demand_id"]))
        assert old.status == "archived" and old.scheduled_at is None
        audit = (await db.execute(select(AuditEvent).where(
            AuditEvent.entity_id == uuid.UUID(pid), AuditEvent.event_type == "mission_phase_homologation_requested")
            .order_by(AuditEvent.created_at.desc()).limit(1))).scalar_one()
        assert audit.payload["replaced"]["previous_homologator_agent_id"] == str(first_h)
        assert audit.payload["replaced"]["previous_demand_archived"] is True
        # The new run is in flight: replacing it now is refused.
        current = await db.get(AgentDemand, uuid.UUID(second.json()["demand_id"]))
        current.dispatch_status = "running"
        current.agent_run_id = str(uuid.uuid4())
        await db.commit()
    in_flight = await _call(world, "POST", url, {"homologator_agent_id": str(first_h), "replace": True})
    assert in_flight.status_code == 409 and _code(in_flight) == "HOMOLOGATION_RUN_IN_FLIGHT"
    async with AsyncSessionLocal() as db:
        current = await db.get(AgentDemand, uuid.UUID(second.json()["demand_id"]))
        current.dispatch_status = "completed"
        await db.commit()


@pytest.mark.asyncio
async def test_rename_refuses_a_taken_project_name(world):
    mission = await _mission(world)
    pid = mission["project_id"]
    first = (await _create_phase(world, pid, name="Estrutura")).json()["phases"][0]
    second = (await _create_phase(world, pid, name="Telas")).json()["phases"][1]
    async with AsyncSessionLocal() as db:
        mission_project = await db.get(Project, uuid.UUID(pid))
        db.add(Project(name=f"{mission_project.name} · Fase 1 · Regras", owner="test",
                       product_version_id=mission_project.product_version_id))
        await db.commit()
    clash = await _call(world, "PATCH", f"/api/v1/missions/{pid}/phases/{first['phase_id']}", {"name": "Regras"})
    assert clash.status_code == 409 and _code(clash) == "PROJECT_NAME_EXISTS_IN_VERSION", clash.text
    assert (await _phase_row(first["phase_id"])).name == "Estrutura"
    # Swapping two phases renames both projects without tripping on each other.
    swapped = await _call(world, "POST", f"/api/v1/missions/{pid}/phases:reorder",
                          {"phase_ids": [second["phase_id"], first["phase_id"]]})
    assert swapped.status_code == 200, swapped.text
    # Renumbering into a taken name is refused too.
    async with AsyncSessionLocal() as db:
        db.add(Project(name=f"{mission_project.name} · Fase 1 · Estrutura", owner="test",
                       product_version_id=mission_project.product_version_id))
        await db.commit()
    back = await _call(world, "POST", f"/api/v1/missions/{pid}/phases:reorder",
                       {"phase_ids": [first["phase_id"], second["phase_id"]]})
    assert back.status_code == 409 and _code(back) == "PROJECT_NAME_EXISTS_IN_VERSION"


@pytest.mark.asyncio
async def test_report_refused_for_terminal_mission_or_lost_membership(world):
    pid, _orchestrator, phase, task, _executor, _reviewer = await _homologation_world(world)
    await _set_task(task.id, status="done")
    homologator = await world.agent("hom")
    membership = await _member(pid, homologator, role="homologation")
    hom_h = await world.agent_token(homologator, None)
    base = f"/api/v1/missions/{pid}/phases/{phase['phase_id']}"
    sent = await _call(world, "POST", f"{base}:request-homologation", {"homologator_agent_id": str(homologator)})
    assert sent.status_code == 200, sent.text

    async def report():
        return await _call(world, "POST", f"{base}:report-homologation", {
            "verdict": "approved", "summary": "ok", "evidence": ["git:abc"], "idempotency_key": _key(world)}, hom_h)

    async with AsyncSessionLocal() as db:
        (await db.get(ProjectAgentMembership, membership)).status = "released"
        await db.commit()
    lost = await report()
    assert lost.status_code == 409 and _code(lost) == "HOMOLOGATOR_NOT_MEMBER"
    async with AsyncSessionLocal() as db:
        (await db.get(ProjectAgentMembership, membership)).status = "active"
        await db.commit()
    await _force(pid, state="cancelled")
    terminal = await report()
    assert terminal.status_code == 409 and _code(terminal) == "MISSION_TERMINAL"
