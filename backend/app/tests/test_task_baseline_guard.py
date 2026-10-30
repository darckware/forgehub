"""M0.6b: immutable baseline and dispatch guard (MCP_MISSION_TOOLS_SPEC.md
§4.2, §4.3, §7 item 4 and §9.3; decisions D-M0-2 and D-M0-3).

Runs only against the isolated test database. Every route, guard and query is
real; only the host-bridge start (`dispatch_agent_run`) and the Telegram
notice are replaced, and the dispatch capacity is pinned so leftovers in the
shared test database can't fill it. The scheduled pass runs with a frozen
clock (2001) and the test's items due in 2000, so it never picks up anyone
else's message.
"""
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import func, select, text

from app.api.routes import demand as demand_routes
from app.api.routes import execution as execution_routes
from app.core.deps import ActorPrincipal, authorize_action
from app.core.plan_baseline import BaselineCreationError, create_mission_baseline
from app.db.base import AsyncSessionLocal
from app.db.models.artifact import ArtifactVersion, ArtifactVersionStatus
from app.db.models.channel import ChatChannel, ChatChannelMember, ChatChannelMessage
from app.db.models.demand import AgentDemand
from app.db.models.execution import ExecutionLease, ExecutionWave, ExecutionWorkPackage
from app.db.models.governance import Approval, AuthorityDelegation
from app.db.models.mission import MissionAcceptanceCriterion, MissionProjectLink, ProjectMission
from app.db.models.orchestration import AgentRuntimeProfile
from app.db.models.notification import Notification
from app.db.models.project import ChangeRequest, PlanBaseline, Project, ProjectPlan
from app.db.models.task import ProjectTask, TaskAssignment, TaskExecution, TaskExecutionTarget
from app.db.models.user import User
from app.tests.test_mission_base import World, _assign, _brief, _criterion, _force, _member, _task

BACKEND_DIR = Path(__file__).resolve().parents[2]
REVISION = "b9e4d2a7c615"
DUE = datetime(2000, 12, 31, tzinfo=timezone.utc)


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2001, 1, 1, tzinfo=timezone.utc)
        return value if tz is not None else value.replace(tzinfo=None)


class Runner:
    """Stands in for the host-bridge start; records every run it accepted."""

    def __init__(self):
        self.runs: list[str] = []

    async def __call__(self, run_id, agent, prompt, project_path):
        self.runs.append(run_id)
        return {"run_id": run_id}


@pytest.fixture
def runner(monkeypatch):
    runner = Runner()
    monkeypatch.setattr(demand_routes, "dispatch_agent_run", runner)
    monkeypatch.setattr(demand_routes, "_send_notice", AsyncMock())

    async def slots(db):
        return 10

    monkeypatch.setattr(demand_routes, "_dispatch_slots", slots)
    return runner


class Mission:
    """An active mission whose tasks are frozen in a current baseline."""

    def __init__(self, world: World, data: dict, executor: uuid.UUID, membership: uuid.UUID):
        self.world = world
        self.project_id = uuid.UUID(data["project_id"])
        self.executor = executor
        self.membership = membership

    async def task(self, title: str, executor: uuid.UUID | None = None, **fields) -> ProjectTask:
        task = await _task(self.project_id, title, **fields)
        agent = executor or self.executor
        membership = self.membership if agent == self.executor else await _member(self.project_id, agent)
        await _assign(task.id, agent, membership)
        return task

    async def baseline(self, task_ids, name="baseline") -> uuid.UUID:
        async with AsyncSessionLocal() as db:
            mission = await db.get(ProjectMission, self.project_id)
            plan = ProjectPlan(project_id=self.project_id, name=f"plan {name}", status="approved")
            db.add(plan)
            await db.flush()
            baseline = await create_mission_baseline(db, mission, plan, list(task_ids), name=name, actor="test")
            await db.commit()
            return baseline.id


async def _mission(world: World, state="active") -> Mission:
    executor = await world.agent("exec")
    data = await world.create_mission(
        brief_artifact_id=str(await _brief(world)),
        working_directory_path=f"/srv/forgehub-test/m06b-{world.tag}-{uuid.uuid4().hex[:6]}",
    )
    membership = await _member(data["project_id"], executor)
    await _force(data["project_id"], state=state)
    return Mission(world, data, executor, membership)


async def _cleanup(world: World) -> None:
    if world.product_id is None:
        await world.cleanup()
        return
    projects = ("SELECT p.id FROM company.projects p JOIN company.product_versions v "
                f"ON v.id = p.product_version_id WHERE v.product_id = '{world.product_id}'")
    tasks = ("SELECT id FROM company.project_tasks WHERE planning_item_id IN "
             f"(SELECT id FROM company.planning_items WHERE project_id IN ({projects}))")
    async with AsyncSessionLocal() as db:
        for statement in (
            f"DELETE FROM company.chat_channels WHERE project_id IN ({projects})",
            # A channel dispatch on a common project files an ad hoc demand
            # (no origin_id); left in `dispatched` it held the shared test
            # database's capacity for every later dispatch test.
            f"DELETE FROM company.agent_demands WHERE project_id IN ({projects})",
            f"DELETE FROM company.execution_leases WHERE work_package_id IN "
            f"(SELECT id FROM company.execution_work_packages WHERE task_id IN ({tasks}))",
            f"DELETE FROM company.task_executions WHERE task_id IN ({tasks})",
            f"DELETE FROM company.execution_work_packages WHERE task_id IN ({tasks})",
            f"DELETE FROM company.execution_waves WHERE project_id IN ({projects})",
            f"DELETE FROM company.agent_runtime_profiles WHERE name LIKE 'm06b-{world.tag}-%'",
            f"DELETE FROM company.agent_demands WHERE origin_id IN ({tasks})",
            f"DELETE FROM company.approvals WHERE entity_id IN ({tasks})",
            f"UPDATE company.project_missions SET current_baseline_id = NULL WHERE project_id IN ({projects})",
            f"DELETE FROM company.plan_baseline_items WHERE task_id IN ({tasks})",
            f"UPDATE company.project_tasks SET change_request_id = NULL WHERE id IN ({tasks})",
            f"DELETE FROM company.change_requests WHERE project_id IN ({projects})",
            f"DELETE FROM company.project_plans WHERE project_id IN ({projects})",
        ):
            await db.execute(text(statement))
        await db.commit()
    await world.cleanup()


@pytest_asyncio.fixture
async def world(admin_headers):
    w = World(admin_headers)
    await w.setup()
    yield w
    await _cleanup(w)


async def _dispatch(world: World, task_id):
    async with world.client() as client:
        return await client.post(f"/api/v1/tasks/{task_id}/dispatch", json={})


def _code(response) -> str | None:
    detail = response.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


async def _executions(task_id) -> int:
    async with AsyncSessionLocal() as db:
        return await db.scalar(select(func.count(TaskExecution.id)).where(TaskExecution.task_id == task_id))


async def _finish_runs(task_id) -> None:
    """Mark the task's runs completed so they no longer hold their targets."""
    async with AsyncSessionLocal() as db:
        for demand in (await db.execute(select(AgentDemand).where(AgentDemand.origin_id == task_id))).scalars():
            if demand.dispatch_status in ("dispatched", "running"):
                demand.dispatch_status = "completed"
        await db.commit()


async def _queued_demand(task: ProjectTask, agent_id, working_path, **fields) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        demand = AgentDemand(
            from_agent="marcelo", subject=f"m06b {task.title}", body="run it", origin_type="task",
            origin_id=task.id, target_agent_id=agent_id, working_path=working_path, scheduled_at=DUE, **fields,
        )
        db.add(demand)
        await db.commit()
        return demand.id


async def _project_path(project_id) -> str:
    async with AsyncSessionLocal() as db:
        return (await db.get(Project, project_id)).working_directory_path


async def _scheduled_pass(monkeypatch) -> None:
    monkeypatch.setattr(demand_routes, "datetime", FrozenDateTime)
    try:
        async with AsyncSessionLocal() as db:
            await demand_routes.run_scheduled_dispatch_pass(db)
    finally:
        monkeypatch.setattr(demand_routes, "datetime", datetime)


async def _demand(demand_id) -> AgentDemand:
    async with AsyncSessionLocal() as db:
        return await db.get(AgentDemand, demand_id)


async def _update(model, row_id, **fields) -> None:
    async with AsyncSessionLocal() as db:
        row = await db.get(model, row_id)
        for key, value in fields.items():
            setattr(row, key, value)
        await db.commit()


# ---------------------------------------------------------------------------
# Baseline content
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_edit_after_approval_blocks_dispatch(world, runner):
    mission = await _mission(world)
    task = await mission.task("edit me", description="what", plan_brief="how")
    verifier = await world.agent("verifier")
    criterion = await _criterion(mission.project_id, verifier, task_ids=[task.id])
    await mission.baseline([task.id])

    for field, changed in (("title", "edited"), ("description", "other"), ("plan_brief", "other way")):
        original = getattr(task, field)
        await _update(ProjectTask, task.id, **{field: changed})
        response = await _dispatch(world, task.id)
        assert response.status_code == 409 and _code(response) == "TASK_CONTENT_CHANGED", (field, response.text)
        await _update(ProjectTask, task.id, **{field: original})

    await _update(MissionAcceptanceCriterion, criterion, statement="A different promise")
    response = await _dispatch(world, task.id)
    assert _code(response) == "TASK_CONTENT_CHANGED", response.text
    await _update(MissionAcceptanceCriterion, criterion, statement="The thing works")

    # Reassignment is not content (D-M0-3): the task is still authorized.
    other = await world.agent("exec2")
    async with AsyncSessionLocal() as db:
        await db.execute(text(f"UPDATE company.task_assignments SET status = 'cancelled' WHERE task_id = '{task.id}'"))
        await db.commit()
    await _assign(task.id, other, await _member(mission.project_id, other))
    response = await _dispatch(world, task.id)
    assert response.status_code == 200, response.text
    assert response.json()["target_agent_id"] == str(other)
    await _finish_runs(task.id)

    # A new version of the brief changes what every task was approved against.
    async with AsyncSessionLocal() as db:
        brief_id = (await db.get(ProjectMission, mission.project_id)).brief_artifact_id
        db.add(ArtifactVersion(artifact_id=brief_id, version_number=2, status=ArtifactVersionStatus.FINAL,
                               location_uri="docs/missions/test/BRIEF-v2.md"))
        await db.commit()
    before = await _executions(task.id)
    response = await _dispatch(world, task.id)
    assert _code(response) == "TASK_CONTENT_CHANGED", response.text
    assert await _executions(task.id) == before, "a refused dispatch must not create a TaskExecution"
    assert len(runner.runs) == 1


@pytest.mark.asyncio
async def test_added_task_without_cr_blocked(world, runner):
    mission = await _mission(world)
    frozen = await mission.task("frozen")
    await mission.baseline([frozen.id])
    added = await mission.task("added later")
    response = await _dispatch(world, added.id)
    assert response.status_code == 409 and _code(response) == "TASK_NOT_IN_BASELINE", response.text
    assert await _executions(added.id) == 0
    assert runner.runs == []


@pytest.mark.asyncio
async def test_baseline_of_other_project_blocked(world, runner):
    mission = await _mission(world)
    task = await mission.task("mine")
    await mission.baseline([task.id])
    other = await _mission(world)
    foreign = await other.baseline([(await other.task("theirs")).id])
    await _force(mission.project_id, current_baseline_id=foreign)
    response = await _dispatch(world, task.id)
    assert _code(response) == "BASELINE_FOREIGN_PROJECT", response.text
    assert runner.runs == []


@pytest.mark.asyncio
async def test_cr_pending_blocks_and_new_baseline_unblocks(world, runner):
    mission = await _mission(world)
    first = await mission.task("first")
    old_baseline = await mission.baseline([first.id], name="v1")

    async with AsyncSessionLocal() as db:
        cr = ChangeRequest(project_id=mission.project_id, plan_baseline_id=old_baseline, title="add second",
                           adds_features=True)
        db.add(cr)
        await db.commit()
        cr_id = cr.id
    second = await mission.task("second", change_request_id=cr_id)
    response = await _dispatch(world, second.id)
    assert _code(response) == "CHANGE_REQUEST_PENDING", response.text

    await _update(ChangeRequest, cr_id, status="approved")
    assert _code(await _dispatch(world, second.id)) == "CHANGE_REQUEST_PENDING"

    # Applying the CR alone authorizes nothing: the task needs a new baseline.
    await _update(ChangeRequest, cr_id, status="applied")
    assert _code(await _dispatch(world, second.id)) == "TASK_NOT_IN_BASELINE"

    new_baseline = await mission.baseline([first.id, second.id], name="v2")
    response = await _dispatch(world, second.id)
    assert response.status_code == 200, response.text
    await _finish_runs(second.id)

    async with AsyncSessionLocal() as db:
        old = await db.get(PlanBaseline, old_baseline)
        assert old.superseded_at is not None
        assert (await db.get(ProjectPlan, old.project_plan_id)).status == "superseded"
        assert (await db.get(ProjectMission, mission.project_id)).current_baseline_id == new_baseline
        assert (await db.get(PlanBaseline, new_baseline)).content_hash
    # The old authorization is not reusable even if cited again.
    await _force(mission.project_id, current_baseline_id=old_baseline)
    assert _code(await _dispatch(world, first.id)) == "BASELINE_SUPERSEDED"


@pytest.mark.asyncio
async def test_baseline_creation_refuses_invalid_input(world):
    mission = await _mission(world)
    other = await _mission(world)
    outsider = await other.task("outsider")
    with pytest.raises(BaselineCreationError, match="outside the mission scope"):
        await mission.baseline([outsider.id])
    with pytest.raises(BaselineCreationError, match="at least one task"):
        await mission.baseline([])
    async with AsyncSessionLocal() as db:
        draft = ProjectPlan(project_id=mission.project_id, name="draft plan", status="draft")
        db.add(draft)
        await db.flush()
        with pytest.raises(BaselineCreationError, match="approved"):
            await create_mission_baseline(db, await db.get(ProjectMission, mission.project_id), draft,
                                          [(await mission.task("t")).id], name="x", actor="test")


# ---------------------------------------------------------------------------
# Every dispatch path
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_all_dispatch_paths_guarded(world, runner, monkeypatch):
    mission = await _mission(world)
    task = await mission.task("changed after approval")
    await mission.baseline([task.id])
    await _update(ProjectTask, task.id, title="changed")
    path = await _project_path(mission.project_id)

    # POST /tasks/{id}/dispatch
    response = await _dispatch(world, task.id)
    assert _code(response) == "TASK_CONTENT_CHANGED", response.text
    assert await _executions(task.id) == 0

    # POST /demands/{id}/dispatch
    demand_id = await _queued_demand(task, mission.executor, path)
    async with world.client() as client:
        response = await client.post(f"/api/v1/demands/{demand_id}/dispatch",
                                     json={"target_agent_id": str(mission.executor)})
    assert response.status_code == 409 and _code(response) == "TASK_CONTENT_CHANGED", response.text

    # Scheduled pass: stays queued, no attempt consumed, nothing reserved.
    await _scheduled_pass(monkeypatch)
    queued = await _demand(demand_id)
    assert (queued.dispatch_status, queued.agent_run_id, queued.dispatch_attempts or 0) == (None, None, 0)

    # Reprocess: puts a failed item back in the queue, the next start is refused.
    await _update(AgentDemand, demand_id, dispatch_status="failed", dispatch_attempts=1,
                  dispatch_error="runner said no")
    async with world.client() as client:
        response = await client.post(f"/api/v1/demands/{demand_id}:reprocess")
    assert response.status_code == 200, response.text
    await _update(AgentDemand, demand_id, scheduled_at=DUE)
    await _scheduled_pass(monkeypatch)
    queued = await _demand(demand_id)
    assert (queued.dispatch_status, queued.agent_run_id, queued.dispatch_attempts) == (None, None, 1)

    # Legacy Approval(project_task) auto-dispatch: approval stands, dispatch
    # degrades to a notification and leaves no execution behind.
    async with AsyncSessionLocal() as db:
        approval = Approval(entity_type="project_task", entity_id=task.id, approval_type="task_release",
                            status="pending", requested_by="test")
        db.add(approval)
        await db.commit()
        approval_id = approval.id
    async with world.client() as client:
        response = await client.post(f"/api/v1/governance/approvals/{approval_id}/approve",
                                     json={"decided_by": "test"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "approved"
    async with AsyncSessionLocal() as db:
        notice = await db.scalar(select(Notification).where(
            Notification.event_key == f"approval-dispatch-failed:{approval_id}"))
        assert notice is not None and "TASK_CONTENT_CHANGED" in notice.title
        await db.delete(notice)
        await db.commit()
    assert await _executions(task.id) == 0
    assert runner.runs == []


@pytest.mark.asyncio
async def test_paused_mission_not_dispatched(world, runner, monkeypatch):
    mission = await _mission(world)
    task = await mission.task("paused work")
    await mission.baseline([task.id])
    await _force(mission.project_id, state="paused", paused_from_state="active")

    response = await _dispatch(world, task.id)
    assert _code(response) == "MISSION_NOT_ACTIVE", response.text
    demand_id = await _queued_demand(task, mission.executor, await _project_path(mission.project_id))
    await _scheduled_pass(monkeypatch)
    assert (await _demand(demand_id)).dispatch_status is None

    await _force(mission.project_id, state="active", paused_from_state=None)
    await _scheduled_pass(monkeypatch)
    resumed = await _demand(demand_id)
    assert resumed.dispatch_status == "dispatched" and resumed.dispatch_attempts == 1
    assert runner.runs == [resumed.agent_run_id]


# ---------------------------------------------------------------------------
# Runs: replay, uncertainty, revocation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_retry_does_not_duplicate_run(world, runner):
    mission = await _mission(world)
    task = await mission.task("once")
    await mission.baseline([task.id])
    first = await _dispatch(world, task.id)
    assert first.status_code == 200, first.text
    receipt = first.json()

    # Another start while the run is active is refused under the lock.
    again = await _dispatch(world, task.id)
    assert again.status_code == 409, again.text

    # While the outcome is uncertain, a replay returns the existing demand.
    await _update(AgentDemand, uuid.UUID(receipt["demand_id"]), dispatch_status="failed",
                  dispatch_error=demand_routes.RECONCILIATION_REQUIRED_ERROR)
    replay = await _dispatch(world, task.id)
    assert replay.status_code == 200, replay.text
    assert (replay.json()["demand_id"], replay.json()["agent_run_id"]) == (receipt["demand_id"], receipt["agent_run_id"])
    assert runner.runs == [receipt["agent_run_id"]]


@pytest.mark.asyncio
async def test_uncertain_keeps_run_id(world, runner):
    mission = await _mission(world)
    task = await mission.task("uncertain")
    sibling = await mission.task("same worktree", executor=await world.agent("exec2"))
    await mission.baseline([task.id, sibling.id])
    receipt = (await _dispatch(world, task.id)).json()
    demand_id = uuid.UUID(receipt["demand_id"])
    await _update(AgentDemand, demand_id, dispatch_status="failed",
                  dispatch_error=demand_routes.RECONCILIATION_REQUIRED_ERROR)

    async with world.client() as client:
        assert (await client.post(f"/api/v1/demands/{demand_id}:reprocess")).status_code == 409
        # The uncertain run still holds the mission worktree.
        held = await _dispatch(world, sibling.id)
        assert held.status_code == 409 and str(held.json()["detail"]).startswith("TARGET_BUSY: worktree:"), held.text
        wrong = await client.post(f"/api/v1/demands/{demand_id}/decision", json={
            "action": "confirm_inactive", "reason": "checked", "evidence_ref": "ps", "confirmation": "nope"})
        assert wrong.status_code == 409
        assert (await _demand(demand_id)).agent_run_id == receipt["agent_run_id"]
        confirmed = await client.post(f"/api/v1/demands/{demand_id}/decision", json={
            "action": "confirm_inactive", "reason": "checked on the host", "evidence_ref": "ps aux",
            "confirmation": receipt["agent_run_id"]})
        assert confirmed.status_code == 200, confirmed.text
    assert (await _demand(demand_id)).agent_run_id == receipt["agent_run_id"]
    released = await _dispatch(world, sibling.id)
    assert released.status_code == 200, released.text


@pytest.mark.asyncio
async def test_revoked_delegation_refused(world, runner):
    """`authorize_action` re-reads delegations on every call; revoking does
    not cancel a run already reserved (M0)."""
    mission = await _mission(world)
    task = await mission.task("delegated")
    await mission.baseline([task.id])
    receipt = (await _dispatch(world, task.id)).json()
    async with AsyncSessionLocal() as db:
        grantor = User(username=f"mission-grantor-{uuid.uuid4().hex[:8]}", hashed_password="x", is_admin=True)
        db.add(grantor)
        await db.flush()
        world.user_ids.append(grantor.id)
        now = datetime.now(timezone.utc)
        delegation = AuthorityDelegation(
            grantor_user_id=grantor.id, grantee_type="agent", grantee_id=mission.executor, scope_type="project",
            project_id=mission.project_id, allowed_actions=["planning.execution.manage"], max_risk="low",
            valid_from=now - timedelta(minutes=1), expires_at=now + timedelta(hours=1),
        )
        db.add(delegation)
        await db.commit()
        principal = ActorPrincipal(principal_type="agent", principal_id=mission.executor, display_name="exec")
        await authorize_action(db, principal, "planning.execution.manage", project_id=mission.project_id)
        delegation.status = "revoked"
        await db.commit()
        with pytest.raises(HTTPException) as refused:
            await authorize_action(db, principal, "planning.execution.manage", project_id=mission.project_id)
        assert refused.value.status_code == 403
    running = await _demand(uuid.UUID(receipt["demand_id"]))
    assert running.dispatch_status == "dispatched" and running.agent_run_id == receipt["agent_run_id"]


# ---------------------------------------------------------------------------
# Target serialization (§4.3, D-M0-2)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_target_serialization(world, runner, monkeypatch):
    # Mission: the working_path is an implicit worktree target.
    mission = await _mission(world)
    a = await mission.task("a")
    b = await mission.task("b", executor=await world.agent("exec-b"))
    await mission.baseline([a.id, b.id])
    assert (await _dispatch(world, a.id)).status_code == 200
    queued = await _queued_demand(b, (await _assignee(b.id)), await _project_path(mission.project_id))
    await _scheduled_pass(monkeypatch)
    assert (await _demand(queued)).dispatch_status is None
    async with world.client() as client:
        response = await client.post(f"/api/v1/demands/{queued}/dispatch",
                                     json={"target_agent_id": str(await _assignee(b.id))})
    assert response.status_code == 409 and response.json()["detail"].startswith("TARGET_BUSY: worktree:"), response.text
    await _finish_runs(a.id)
    await _scheduled_pass(monkeypatch)
    assert (await _demand(queued)).dispatch_status == "dispatched"
    await _finish_runs(b.id)

    # Mission: an explicit branch target, different worktrees.
    c = await mission.task("c", executor=await world.agent("exec-c"))
    d = await mission.task("d", executor=await world.agent("exec-d"))
    for task in (c, d):
        await _target(task.id, "branch", "/srv/forgehub-test/repo#feat/x")
    await mission.baseline([a.id, b.id, c.id, d.id], name="v2")
    first = await _queued_demand(c, await _assignee(c.id), "/srv/forgehub-test/wt-c")
    second = await _queued_demand(d, await _assignee(d.id), "/srv/forgehub-test/wt-d")
    await _scheduled_pass(monkeypatch)
    assert (await _demand(first)).dispatch_status == "dispatched"
    assert (await _demand(second)).dispatch_status is None and (await _demand(second)).dispatch_attempts in (None, 0)

    # Common projects: production publishing is serialized for all Messages,
    # a shared worktree is not (D-M0-2).
    p1, p2 = await _common_task(world, "pub-1"), await _common_task(world, "pub-2")
    for task in (p1, p2):
        await _target(task.id, "publish", "production:forgehub-test")
        await _target(task.id, "worktree", "/srv/forgehub-test/shared")
    assert (await _dispatch(world, p1.id)).status_code == 200
    response = await _dispatch(world, p2.id)
    assert response.status_code == 409 and response.json()["detail"].startswith(
        "TARGET_BUSY: publish:production:forgehub-test"), response.text
    w1, w2 = await _common_task(world, "wt-1"), await _common_task(world, "wt-2")
    for task in (w1, w2):
        await _target(task.id, "worktree", "/srv/forgehub-test/shared")
        await _target(task.id, "publish", "staging:forgehub-test")
    assert (await _dispatch(world, w1.id)).status_code == 200
    assert (await _dispatch(world, w2.id)).status_code == 200


async def _assignee(task_id) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        return await db.scalar(select(TaskAssignment.agent_id).where(
            TaskAssignment.task_id == task_id, TaskAssignment.status == "active"))


async def _target(task_id, kind, key) -> None:
    async with AsyncSessionLocal() as db:
        db.add(TaskExecutionTarget(task_id=task_id, kind=kind, target_key=key))
        await db.commit()


async def _common_task(world: World, title: str) -> ProjectTask:
    project = await world.common_project()
    await _update(Project, uuid.UUID(project["id"]),
                  working_directory_path=f"/srv/forgehub-test/common-{uuid.uuid4().hex[:6]}")
    agent = await world.agent(title)
    task = await _task(project["id"], title)
    await _assign(task.id, agent, await _member(project["id"], agent))
    return task


# ---------------------------------------------------------------------------
# Common projects and the generic plan routes (§7 item 4)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_common_project_legacy_baseline_not_blocked(world, runner):
    task = await _common_task(world, "legacy")
    async with AsyncSessionLocal() as db:
        project_id = (await db.execute(text(
            f"SELECT project_id FROM company.planning_items WHERE id = '{task.planning_item_id}'"))).scalar_one()
    async with world.client() as client:
        plan = await client.post(f"/api/v1/projects/{project_id}/plans", json={"name": "legacy plan"})
        assert plan.status_code == 201, plan.text
        assert (await client.post(f"/api/v1/projects/plans/{plan.json()['id']}/approve")).status_code == 200
        baseline = await client.post(f"/api/v1/projects/{project_id}/baselines",
                                     json={"project_plan_id": plan.json()["id"], "name": "legacy"})
        assert baseline.status_code == 201, baseline.text
    response = await _dispatch(world, task.id)
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_mission_plan_shortcuts_refused(world):
    mission = await _mission(world, state="planning")
    async with world.client() as client:
        plan = await client.post(f"/api/v1/projects/{mission.project_id}/plans", json={"name": "mission plan"})
        assert plan.status_code == 201, plan.text
        approve = await client.post(f"/api/v1/projects/plans/{plan.json()['id']}/approve")
        assert approve.status_code == 409 and _code(approve) == "USE_GOVERNED_PLAN_APPROVAL"
        baseline = await client.post(f"/api/v1/projects/{mission.project_id}/baselines",
                                     json={"project_plan_id": plan.json()["id"], "name": "shortcut"})
        assert baseline.status_code == 409 and _code(baseline) == "USE_GOVERNED_PLAN_APPROVAL"
    frozen = await mission.task("frozen")
    baseline_id = await mission.baseline([frozen.id])
    async with AsyncSessionLocal() as db:
        plan_id = (await db.get(PlanBaseline, baseline_id)).project_plan_id
    async with world.client() as client:
        refused = await client.delete(f"/api/v1/projects/plans/{plan_id}")
    assert refused.status_code == 409 and _code(refused) == "BASELINE_IMMUTABLE"


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------
def _alembic(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=BACKEND_DIR, capture_output=True, text=True,
        env={**os.environ, "ENVIRONMENT": "test"}, timeout=180,
    )


async def _guarded_missions() -> int:
    async with AsyncSessionLocal() as db:
        return await db.scalar(text(
            "SELECT count(*) FROM company.project_missions WHERE state IN ('active', 'verifying')"))


@pytest.mark.asyncio
async def test_migration_roundtrip_refuses_with_active_mission(world):
    """Only this revision moves: downgrade to its parent and back."""
    assert REVISION in _alembic("current").stdout
    await _mission(world)
    refused = _alembic("downgrade", f"{REVISION}@-1")
    assert refused.returncode != 0 and "active or verifying" in refused.stderr, refused.stderr[-2000:]
    assert REVISION in _alembic("current").stdout

    await _cleanup(world)
    world.product_id = None
    if await _guarded_missions():
        pytest.skip("another active mission in the shared test database; refusal proven, roundtrip skipped")
    down = _alembic("downgrade", f"{REVISION}@-1")
    up = _alembic("upgrade", REVISION)
    assert down.returncode == 0, down.stderr[-2000:]
    assert up.returncode == 0, up.stderr[-2000:]
    assert REVISION in _alembic("current").stdout


# ---------------------------------------------------------------------------
# Review #41754: paths outside Messages, governing mission, holding clause
# ---------------------------------------------------------------------------
class BridgeRecorder:
    """Replaces httpx inside routes/execution.py: records any runner call."""

    HTTPError = httpx.HTTPError

    def __init__(self):
        self.calls: list[str] = []
        recorder = self

        class _Client:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def post(self, url, **kwargs):
                recorder.calls.append(url)
                raise httpx.ConnectError("no runner in this test")

        self.AsyncClient = _Client


async def _work_package(mission: Mission, task: ProjectTask, baseline_id: uuid.UUID) -> uuid.UUID:
    """An issued package in an active wave, ready for :dispatch."""
    async with AsyncSessionLocal() as db:
        assignment_id = await db.scalar(select(TaskAssignment.id).where(
            TaskAssignment.task_id == task.id, TaskAssignment.status == "active"))
        profile = AgentRuntimeProfile(agent_id=await _assignee(task.id), name=f"m06b-{mission.world.tag}-{task.title}",
                                      runtime_type="claude")
        wave = ExecutionWave(project_id=mission.project_id, baseline_id=baseline_id, name="m06b wave", status="active",
                             idempotency_key=f"m06b-{uuid.uuid4().hex}")
        db.add_all([profile, wave])
        await db.flush()
        package = ExecutionWorkPackage(
            task_id=task.id, assignment_id=assignment_id, runtime_profile_id=profile.id, execution_wave_id=wave.id,
            baseline_id=baseline_id, revision=1, payload={"constraints": {"max_seconds": 60}}, payload_hash="0" * 64,
            idempotency_key=f"m06b-{uuid.uuid4().hex}", status="issued",
        )
        db.add(package)
        await db.commit()
        return package.id


async def _package_dispatch(world: World, package_id):
    async with world.client() as client:
        return await client.post(f"/api/v1/work-packages/{package_id}:dispatch", json={})


async def _leases(package_id) -> int:
    async with AsyncSessionLocal() as db:
        return await db.scalar(select(func.count(ExecutionLease.id)).where(ExecutionLease.work_package_id == package_id))


@pytest.mark.asyncio
async def test_work_package_dispatch_guarded(world, runner, monkeypatch):
    bridge = BridgeRecorder()
    monkeypatch.setattr(execution_routes, "httpx", bridge)
    mission = await _mission(world)
    a = await mission.task("pkg-changed")
    b = await mission.task("pkg-busy", executor=await world.agent("exec-pkg"))
    baseline_id = await mission.baseline([a.id, b.id])

    # Baseline guard: content changed after approval -> 409, nothing created.
    await _update(ProjectTask, a.id, title="pkg-changed later")
    package_a = await _work_package(mission, a, baseline_id)
    response = await _package_dispatch(world, package_a)
    assert response.status_code == 409 and _code(response) == "TASK_CONTENT_CHANGED", response.text
    assert (await _executions(a.id), await _leases(package_a)) == (0, 0)

    # Target serialization: a Messages run of the same mission holds its worktree.
    sibling = await mission.task("holder", executor=await world.agent("exec-holder"))
    current = await mission.baseline([a.id, b.id, sibling.id], name="v2")
    assert (await _dispatch(world, sibling.id)).status_code == 200
    package_b = await _work_package(mission, b, current)
    response = await _package_dispatch(world, package_b)
    assert response.status_code == 409 and str(response.json()["detail"]).startswith("TARGET_BUSY: worktree:"), response.text
    assert (await _executions(b.id), await _leases(package_b)) == (0, 0)
    # Only the Messages holder ever started; the runner was never called.
    assert bridge.calls == [] and len(runner.runs) == 1


async def _channel_message(project_id, agent_id) -> tuple[uuid.UUID, uuid.UUID]:
    async with AsyncSessionLocal() as db:
        channel = ChatChannel(name=f"m06b-{uuid.uuid4().hex[:6]}", project_id=project_id,
                              working_directory_path="/srv/forgehub-test/m06b-channel")
        db.add(channel)
        await db.flush()
        db.add(ChatChannelMember(channel_id=channel.id, agent_id=agent_id, is_human=False))
        message = ChatChannelMessage(channel_id=channel.id, author_type="human", author_label="Marcelo",
                                     content="run this ad hoc")
        db.add(message)
        await db.commit()
        return channel.id, message.id


@pytest.mark.asyncio
async def test_channel_dispatch_in_mission_requires_task(world, runner):
    mission = await _mission(world)
    executor = await world.common_project()
    executor_id = uuid.UUID(executor["id"])
    async with AsyncSessionLocal() as db:
        db.add(MissionProjectLink(mission_project_id=mission.project_id, executor_project_id=executor_id,
                                  linked_by="test"))
        await db.commit()
    common = await world.common_project()
    for project_id, refused in ((mission.project_id, True), (executor_id, True), (uuid.UUID(common["id"]), False)):
        channel_id, message_id = await _channel_message(project_id, mission.executor)
        async with world.client() as client:
            response = await client.post(f"/api/v1/channels/{channel_id}/messages/{message_id}:dispatch-task",
                                         json={"agent_id": str(mission.executor)})
        if refused:
            assert response.status_code == 409 and _code(response) == "MISSION_DISPATCH_REQUIRES_TASK", response.text
            async with AsyncSessionLocal() as db:
                assert (await db.get(ChatChannelMessage, message_id)).triggered_demand_id is None
        else:
            assert response.status_code == 200, response.text
    # Only the common-project channel started a run.
    assert len(runner.runs) == 1


@pytest.mark.asyncio
async def test_closed_mission_does_not_mask_baseline_refusal(world, runner):
    """An executor project serving a completed mission and an active one: a
    task frozen in neither is refused by the active one (TASK_NOT_IN_BASELINE),
    not by the closed one (MISSION_NOT_ACTIVE)."""
    closed, active = await _mission(world), await _mission(world)
    await _force(closed.project_id, state="completed")
    executor = await world.common_project()
    executor_id = uuid.UUID(executor["id"])
    await _update(Project, executor_id, working_directory_path=f"/srv/forgehub-test/linked-{uuid.uuid4().hex[:6]}")
    async with AsyncSessionLocal() as db:
        for mission in (closed, active):  # the closed one is linked, and created, first
            db.add(MissionProjectLink(mission_project_id=mission.project_id, executor_project_id=executor_id,
                                      linked_by="test"))
        await db.commit()
    await active.baseline([(await active.task("frozen")).id])
    agent = await world.agent("exec-linked")
    task = await _task(executor_id, "outside both baselines")
    await _assign(task.id, agent, await _member(executor_id, agent))

    response = await _dispatch(world, task.id)
    assert response.status_code == 409 and _code(response) == "TASK_NOT_IN_BASELINE", response.text
    assert response.json()["detail"]["mission_project_id"] == str(active.project_id)

    # Every mission closed: the closed one still refuses.
    await _force(active.project_id, state="cancelled")
    response = await _dispatch(world, task.id)
    assert _code(response) == "MISSION_NOT_ACTIVE", response.text
    assert runner.runs == []


@pytest.mark.asyncio
async def test_empty_dispatch_error_still_holds_targets(world, runner):
    """A failed run with a run id and an empty error is uncertain (as in
    _in_flight_dispatch_filter): it keeps holding the mission worktree."""
    mission = await _mission(world)
    a = await mission.task("empty error")
    b = await mission.task("waits", executor=await world.agent("exec-empty"))
    await mission.baseline([a.id, b.id])
    receipt = (await _dispatch(world, a.id)).json()
    await _update(AgentDemand, uuid.UUID(receipt["demand_id"]), dispatch_status="failed", dispatch_error="")
    held = await _dispatch(world, b.id)
    assert held.status_code == 409 and str(held.json()["detail"]).startswith("TARGET_BUSY: worktree:"), held.text
    assert runner.runs == [receipt["agent_run_id"]]
