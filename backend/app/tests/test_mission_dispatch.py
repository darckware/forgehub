"""M0.2c: assign_task, dispatch_task, report_task_execution, request_task_review
and return_task_for_correction (MCP_MISSION_TOOLS_SPEC.md §5.5-§5.7, §5.11,
§5.12, §9.4; acceptance: 07 line M0.2c).

Runs only against the isolated test database. Routes, guards, receipts and
queries are real; only the host-bridge start and the Telegram notice are
replaced (test_task_baseline_guard's `runner`), and dispatch capacity is
pinned so leftovers in the shared database can't fill it.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text

from app.core import command_receipts
from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.orchestration import TaskExecutionReview
from app.db.models.task import ProjectTask, TaskAssignment, TaskDependency, TaskExecution
from app.mcp import factory_server
from app.tests.test_mission_base import World, _member, _task
from app.tests import test_task_baseline_guard as m06b
from app.tests.test_task_baseline_guard import _cleanup, _code, _executions, _finish_runs, _mission, _update

SHA = "0123456789abcdef0123456789abcdef01234567"
PLAN = "planning.execution.manage"


@pytest.fixture
def runner(monkeypatch):
    """test_task_baseline_guard's runner: records every accepted run (and its
    prompt) instead of starting it; capacity pinned."""
    runner = m06b.Runner()
    runner.prompts = []

    async def run(run_id, agent, prompt, project_path):
        runner.prompts.append(prompt)
        return await m06b.Runner.__call__(runner, run_id, agent, prompt, project_path)

    async def slots(db):
        return 10

    monkeypatch.setattr(m06b.demand_routes, "dispatch_agent_run", run)
    monkeypatch.setattr(m06b.demand_routes, "_send_notice", m06b.AsyncMock())
    monkeypatch.setattr(m06b.demand_routes, "_dispatch_slots", slots)
    return runner


@pytest_asyncio.fixture
async def world(admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "MISSION_TOOLS_ENABLED", True)
    command_receipts.agent_write_limiter.reset()
    w = World(admin_headers)
    await w.setup()
    yield w
    async with AsyncSessionLocal() as db:
        if w.agent_ids:
            await db.execute(text("DELETE FROM company.agent_command_receipts WHERE principal_id = ANY(:ids)"),
                             {"ids": list(w.agent_ids)})
        await db.execute(text("DELETE FROM company.agent_command_receipts WHERE idempotency_key LIKE :k"),
                         {"k": f"m02c-{w.tag}-%"})
        await db.commit()
    await _cleanup(w)
    command_receipts.agent_write_limiter.reset()


def _key(world: World) -> str:
    return f"m02c-{world.tag}-{uuid.uuid4().hex}"


async def _post(world: World, path: str, body: dict, headers=None):
    async with world.client(headers) as client:
        return await client.post(path, json=body)


async def _dispatch(world: World, task_id, headers=None, **body):
    return await _post(world, f"/api/v1/tasks/{task_id}/dispatch", body, headers)


async def _assign(world: World, mission, task_id, agent_id, headers=None, key=None):
    return await _post(world, f"/api/v1/missions/{mission.project_id}/tasks/{task_id}:assign",
                       {"agent_id": str(agent_id), "reason": "best fit", "idempotency_key": key or _key(world)},
                       headers)


async def _report(world: World, task_id, execution_id, headers, evidence=None, status="reported", key=None):
    return await _post(world, f"/api/v1/tasks/{task_id}/executions/{execution_id}:report", {
        "status": status, "summary": "did it", "evidence": evidence or [f"git:{SHA}"],
        "idempotency_key": key or _key(world)}, headers)


async def _latest_execution(task_id) -> TaskExecution:
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(TaskExecution).where(TaskExecution.task_id == task_id)
                                 .order_by(TaskExecution.attempt_number.desc()).limit(1))).scalar_one()


async def _demands(task_id) -> list[AgentDemand]:
    async with AsyncSessionLocal() as db:
        return list((await db.execute(select(AgentDemand).where(AgentDemand.origin_id == task_id)
                                      .order_by(AgentDemand.created_at))).scalars())


async def _audits(task_id, event_type) -> list[AuditEvent]:
    async with AsyncSessionLocal() as db:
        return list((await db.execute(select(AuditEvent).where(
            AuditEvent.entity_id == task_id, AuditEvent.event_type == event_type))).scalars())


# ---------------------------------------------------------------------------
# assign_task (§5.5)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_assign_refused_when_reviewer_or_in_flight(world, runner):
    mission = await _mission(world)
    task = await _task(mission.project_id, "to assign")
    outsider = await world.agent("outsider")
    planner = await world.agent("planner")
    await _member(mission.project_id, planner, role="planner")
    orch = await world.agent_token(uuid.UUID(str((await _mission_row(mission)).orchestrator_agent_id)), [PLAN])

    # Not a member of the mission (as caller) -> 404, no existence leak.
    stranger = await world.agent_token(outsider, [PLAN, "mission.orchestrate"])
    assert _code(await _assign(world, mission, task.id, mission.executor, stranger)) == "MISSION_NOT_FOUND"
    # Member without the delegation -> 403.
    member = await world.agent("member")
    await _member(mission.project_id, member)
    no_grant = await world.agent_token(member, None)
    response = await _assign(world, mission, task.id, mission.executor, no_grant)
    assert response.status_code == 403 and _code(response) == "DELEGATION_REQUIRED", response.text
    # Target not a member / a non-executor role -> 422.
    assert _code(await _assign(world, mission, task.id, outsider, orch)) == "ASSIGNEE_NOT_ELIGIBLE"
    response = await _assign(world, mission, task.id, planner, orch)
    assert response.status_code == 422 and response.json()["detail"]["reason"] == "non_executor_role"

    key = _key(world)
    first = await _assign(world, mission, task.id, mission.executor, orch, key=key)
    assert first.status_code == 201, first.text
    assert first.json()["changed"] is True and first.json()["task_status"] == "assigned"
    replay = await _assign(world, mission, task.id, mission.executor, orch, key=key)
    assert replay.status_code == 200 and replay.headers.get("Idempotent-Replay") == "true"
    assert replay.json()["assignment_id"] == first.json()["assignment_id"]

    # Replacing an active assignment also needs mission.orchestrate.
    other = await world.agent("other")
    await _member(mission.project_id, other)
    response = await _assign(world, mission, task.id, other, orch)
    assert response.status_code == 403 and _code(response) == "DELEGATION_REQUIRED", response.text
    orch_full = await world.agent_token((await _mission_row(mission)).orchestrator_agent_id,
                                        [PLAN, "mission.orchestrate"])
    swapped = await _assign(world, mission, task.id, other, orch_full)
    assert swapped.status_code == 201, swapped.text
    assert swapped.json()["previous_assignment_id"] == first.json()["assignment_id"]
    async with AsyncSessionLocal() as db:
        released = await db.get(TaskAssignment, uuid.UUID(first.json()["assignment_id"]))
        assert released.status == "released" and released.unassigned_at is not None
    assert [e.payload["reason"] for e in await _audits(task.id, "task_reassigned")] == ["best fit"]

    # The reviewer of an open review never becomes the executor.
    reviewer = await world.agent("reviewer")
    reviewer_membership = await _member(mission.project_id, reviewer, can_review=True)
    async with AsyncSessionLocal() as db:
        execution = TaskExecution(task_id=task.id, attempt_number=1, status="verified")
        db.add(execution)
        await db.flush()
        db.add(TaskExecutionReview(execution_id=execution.id, reviewer_membership_id=reviewer_membership,
                                   status="pending"))
        await db.commit()
    assert _code(await _assign(world, mission, task.id, reviewer, orch_full)) == "ASSIGNEE_IS_REVIEWER"

    # A run in flight refuses any reassignment.
    async with AsyncSessionLocal() as db:
        db.add(AgentDemand(from_agent="test", subject="m02c running", body="x", origin_type="task",
                           origin_id=task.id, target_agent_id=other, dispatch_status="running",
                           agent_run_id=str(uuid.uuid4()), working_path="/srv/forgehub-test/m02c"))
        await db.commit()
    assert _code(await _assign(world, mission, task.id, mission.executor, orch_full)) == "TASK_RUN_IN_FLIGHT"


async def _mission_row(mission):
    from app.db.models.mission import ProjectMission

    async with AsyncSessionLocal() as db:
        return await db.get(ProjectMission, mission.project_id)


# ---------------------------------------------------------------------------
# dispatch_task (§5.6)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dispatch_guards_order_and_retry(world, runner):
    mission = await _mission(world)
    orchestrator = (await _mission_row(mission)).orchestrator_agent_id
    agt = await world.agent_token(orchestrator, [PLAN])
    before = await mission.task("before")
    task = await mission.task("guarded")
    async with AsyncSessionLocal() as db:
        db.add(TaskDependency(task_id=task.id, depends_on_task_id=before.id))
        await db.commit()

    # An agent needs a key and the delegation.
    assert _code(await _dispatch(world, task.id, agt)) == "IDEMPOTENCY_KEY_REQUIRED"
    no_grant = await world.agent_token(await world.agent("nogrant"), None)
    response = await _dispatch(world, task.id, no_grant, idempotency_key=_key(world))
    assert response.status_code == 403 and _code(response) == "DELEGATION_REQUIRED"

    # Baseline first: with no baseline the open dependency is not even reached.
    response = await _dispatch(world, task.id, agt, idempotency_key=_key(world))
    assert response.status_code == 409 and _code(response) == "TASK_NOT_IN_BASELINE", response.text
    await mission.baseline([before.id, task.id])
    # Then the dependency.
    response = await _dispatch(world, task.id, agt, idempotency_key=_key(world))
    assert response.status_code == 409 and response.json()["detail"]["blocking"][0]["task_id"] == str(before.id)
    await _update(ProjectTask, before.id, status="done")
    # Then the assignment: a mission task never runs on another target.
    response = await _dispatch(world, task.id, agt, idempotency_key=_key(world),
                               target_agent_id=str(await world.agent("elsewhere")))
    assert _code(response) == "TARGET_NOT_ASSIGNEE", response.text
    assert await _executions(task.id) == 0 and runner.runs == []

    key = _key(world)
    first = await _dispatch(world, task.id, agt, idempotency_key=key)
    assert first.status_code == 200, first.text
    assert first.json()["dispatch_status"] == "dispatched" and first.json()["task_status"] == "in_progress"
    # Retry with the same key: the same demand, no second run.
    replay = await _dispatch(world, task.id, agt, idempotency_key=key)
    assert replay.status_code == 200 and replay.headers.get("Idempotent-Replay") == "true", replay.text
    assert replay.json()["demand_id"] == first.json()["demand_id"]
    # A new key while the run is active: refused, still one run.
    again = await _dispatch(world, task.id, agt, idempotency_key=_key(world))
    assert again.status_code == 409 and _code(again) == "TASK_RUN_IN_FLIGHT", again.text
    assert len(runner.runs) == 1 and await _executions(task.id) == 1

    audit = (await _audits(task.id, "task.dispatched"))[0]
    assert audit.actor != "forgehub" and audit.payload["principal_id"] == str(orchestrator)
    assert audit.payload["idempotency_key"] == key and audit.payload["context_manifest"]


@pytest.mark.asyncio
async def test_dispatch_unassigned_and_scheduled(world, runner):
    mission = await _mission(world)
    agt = await world.agent_token((await _mission_row(mission)).orchestrator_agent_id, [PLAN])
    unassigned = await _task(mission.project_id, "nobody")
    task = await mission.task("later")
    await mission.baseline([unassigned.id, task.id])
    # No responsibility-area fallback for a mission task.
    assert _code(await _dispatch(world, unassigned.id, agt, idempotency_key=_key(world))) == "TASK_NOT_ASSIGNED"

    when = datetime.now(timezone.utc) + timedelta(days=30)
    queued = await _dispatch(world, task.id, agt, idempotency_key=_key(world), scheduled_at=when.isoformat())
    assert queued.status_code == 200, queued.text
    assert queued.json()["dispatch_status"] is None and queued.json()["scheduled_at"] is not None
    assert runner.runs == [] and (await _latest_execution(task.id)).status == "pending"
    # A queued mission run is in flight too.
    assert _code(await _dispatch(world, task.id, agt, idempotency_key=_key(world))) == "TASK_RUN_IN_FLIGHT"


# ---------------------------------------------------------------------------
# report_task_execution (§5.7)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_report_cannot_set_verified(world, runner):
    mission = await _mission(world)
    task = await mission.task("report")
    await mission.baseline([task.id])
    assert (await _dispatch(world, task.id)).status_code == 200
    execution = await _latest_execution(task.id)
    # The executor without the delegation (delegations belong to the agent).
    no_grant = await world.agent_token(mission.executor, None)
    assert _code(await _report(world, task.id, execution.id, no_grant)) == "DELEGATION_REQUIRED"
    executor = await world.agent_token(mission.executor, ["mission.execution.report"])

    # DONE is never acceptance: verified/completed are not report statuses.
    for forbidden in ("verified", "completed"):
        response = await _report(world, task.id, execution.id, executor, status=forbidden)
        assert response.status_code == 422, response.text
    # The generic PATCH, which can set verified, is not an agent's.
    async with world.client(executor) as client:
        patched = await client.patch(f"/api/v1/tasks/{task.id}/executions/{execution.id}",
                                     json={"status": "verified", "evidence_ref": f"git:{SHA}"})
    assert patched.status_code in (401, 403), patched.text
    # Not the executor / no delegation / a person -> 403.
    stranger = await world.agent_token(await world.agent("stranger"), ["mission.execution.report"])
    assert _code(await _report(world, task.id, execution.id, stranger)) == "NOT_EXECUTOR"
    assert _code(await _report(world, task.id, execution.id, world.admin)) == "AGENT_ONLY"
    # Evidence outside the task's scope -> 422.
    other = await world.common_project()
    for ref in ("file:../outside.txt", "file:/etc/passwd", f"db:project:{other['id']}", "git:main"):
        response = await _report(world, task.id, execution.id, executor, evidence=[ref])
        assert response.status_code == 422 and _code(response) == "EVIDENCE_OUT_OF_SCOPE", (ref, response.text)
    assert _code(await _report(world, task.id, execution.id, executor, evidence=["url:x"])) == "EVIDENCE_INVALID"

    key = _key(world)
    response = await _report(world, task.id, execution.id, executor, key=key,
                             evidence=[f"git:{SHA}", "file:src/app.py", f"db:project:{mission.project_id}"])
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "reported" and response.json()["verification"] == "queued"
    replay = await _report(world, task.id, execution.id, executor, key=key,
                           evidence=[f"git:{SHA}", "file:src/app.py", f"db:project:{mission.project_id}"])
    assert replay.headers.get("Idempotent-Replay") == "true"
    async with AsyncSessionLocal() as db:
        stored = await db.get(TaskExecution, execution.id)
        assert (stored.status, stored.evidence_ref) == ("reported", f"git:{SHA}")
        assert (await db.get(ProjectTask, task.id)).status == "in_progress"
    audit = (await _audits(execution.id, "execution_reported"))[0]
    assert audit.actor != "system" and len(audit.payload["evidence"]) == 3

    # The run's end keeps the executor's report (no overwrite by the reply).
    from app.api.routes import demand as demand_routes
    demand = (await _demands(task.id))[0]
    async with AsyncSessionLocal() as db:
        await demand_routes._finalize_dispatch(db, demand.id, {"status": "completed", "result": "EVIDENCE: git:"
                                                               "ffffffffffffffffffffffffffffffffffffffff\nSTATUS: DONE"})
        await db.commit()
    assert (await _latest_execution(task.id)).status == "reported"


# ---------------------------------------------------------------------------
# request_task_review / return_task_for_correction (§5.11, §5.12)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_review_request_and_return(world, runner):
    mission = await _mission(world)
    orchestrator = (await _mission_row(mission)).orchestrator_agent_id
    orch = await world.agent_token(orchestrator, [PLAN, "mission.orchestrate"])
    task = await mission.task("reviewed")
    await mission.baseline([task.id])
    assert (await _dispatch(world, task.id, orch, idempotency_key=_key(world))).status_code == 200
    await _finish_runs(task.id)
    execution = await _latest_execution(task.id)
    reviewer = await world.agent("reviewer")
    await _member(mission.project_id, reviewer, role="reviewer", can_review=True)
    path = f"/api/v1/missions/{mission.project_id}/tasks/{task.id}"

    def ask(agent_id):
        return {"execution_id": str(execution.id), "reviewer_agent_id": str(agent_id),
                "idempotency_key": _key(world)}

    assert _code(await _post(world, f"{path}:request-review", ask(reviewer), orch)) == "EXECUTION_NOT_VERIFIED"
    await _update(TaskExecution, execution.id, status="verified", evidence_ref=f"git:{SHA}")
    # The executor never reviews its own execution.
    await _update_membership(mission.membership, can_review=True)
    response = await _post(world, f"{path}:request-review", ask(mission.executor), orch)
    assert response.status_code == 409 and _code(response) == "REVIEWER_IS_EXECUTOR", response.text
    no_review = await world.agent("noreview")
    await _member(mission.project_id, no_review)
    assert _code(await _post(world, f"{path}:request-review", ask(no_review), orch)) == "REVIEWER_NOT_ELIGIBLE"

    requested = await _post(world, f"{path}:request-review", ask(reviewer), orch)
    assert requested.status_code == 201, requested.text
    review_id = requested.json()["review_id"]
    review_demand = next(d for d in await _demands(task.id) if d.id == uuid.UUID(requested.json()["demand_id"]))
    assert (review_demand.target_agent_id, review_demand.task_execution_id) == (reviewer, None)
    assert review_demand.scheduled_at is not None and review_demand.origin_type == "task"

    # The reviewer decides with its own agt_; another agent can't.
    reviewer_token = await world.agent_token(reviewer, None)
    async with world.client(await world.agent_token(no_review, None)) as client:
        assert (await client.patch(f"/api/v1/orchestration/reviews/{review_id}",
                                   json={"status": "running"})).status_code == 403
    async with world.client(reviewer_token) as client:
        response = await client.patch(f"/api/v1/orchestration/reviews/{review_id}", json={"status": "running"})
    assert response.status_code == 200, response.text

    # Return: never by the executor; the open review gets the reason.
    executor_token = await world.agent_token(mission.executor, ["mission.orchestrate"])
    body = {"execution_id": str(execution.id), "reason": "the migration has no downgrade",
            "idempotency_key": _key(world)}
    assert _code(await _post(world, f"{path}:return", body, executor_token)) == "EXECUTOR_CANNOT_RETURN"
    returned = await _post(world, f"{path}:return", {**body, "idempotency_key": _key(world)}, orch)
    assert returned.status_code == 200, returned.text
    assert returned.json()["task_status"] == "in_progress" and returned.json()["review_status"] == "changes_requested"
    async with AsyncSessionLocal() as db:
        assert (await db.get(AgentDemand, review_demand.id)).status == "archived"
        review = await db.get(TaskExecutionReview, uuid.UUID(review_id))
        assert review.feedback == "the migration has no downgrade"
    # Nothing was redispatched; the next dispatch carries the reason.
    assert len(runner.runs) == 1
    again = await _dispatch(world, task.id, orch, idempotency_key=_key(world))
    assert again.status_code == 200, again.text
    async with AsyncSessionLocal() as db:
        demand = await db.get(AgentDemand, uuid.UUID(again.json()["demand_id"]))
    assert "the migration has no downgrade" in demand.body


async def _update_membership(membership_id, **fields):
    from app.db.models.orchestration import ProjectAgentMembership

    await _update(ProjectAgentMembership, membership_id, **fields)


# ---------------------------------------------------------------------------
# Switch and MCP surface
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_tools_disabled_flag(world, runner, monkeypatch):
    mission = await _mission(world)
    task = await mission.task("off")
    await mission.baseline([task.id])
    agt = await world.agent_token((await _mission_row(mission)).orchestrator_agent_id, [PLAN])
    monkeypatch.setattr(settings, "MISSION_TOOLS_ENABLED", False)
    assert _code(await _dispatch(world, task.id, agt, idempotency_key=_key(world))) == "MISSION_TOOLS_DISABLED"
    assert _code(await _assign(world, mission, task.id, mission.executor, agt)) == "MISSION_TOOLS_DISABLED"
    assert await _executions(task.id) == 0
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(func.count(AgentDemand.id)).where(AgentDemand.origin_id == task.id)) == 0


def test_m0_2c_tools_registered():
    tools = factory_server.mcp._tool_manager._tools
    assert {"assign_task", "dispatch_task", "report_task_execution", "request_task_review",
            "return_task_for_correction"} <= tools.keys()
