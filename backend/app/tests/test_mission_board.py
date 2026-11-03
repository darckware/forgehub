"""M0.7: mission executions board, mission list, timeline and environment
releases (MISSION_EXECUTIONS_SCREEN_SPEC.md §3.2, §4, §5, §6, §8, §10, §11).

Runs only against the isolated test database. The board is read-only: these
tests prove its states and conflicts from fixture rows, and that what it lists
as allowed/blocked is what the guarded routes then answer (no action on the
screen has a path around the guards). Only the host-bridge start and the git
ancestry probe are replaced.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.core import command_receipts, mission_board
from app.core.config import settings
from app.core.evidence_bridge import EvidenceUnverifiable
from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.demand import AgentDemand
from app.db.models.environment import EnvironmentRelease
from app.db.models.governance import AuditEvent
from app.db.models.orchestration import TaskExecutionReview
from app.db.models.project import Project
from app.db.models.task import ProjectTask, TaskAssignment, TaskDependency, TaskExecution, TaskExecutionTarget
from app.db.models.user import User
from app.tests.test_mission_base import World, _member, _task
from app.tests import test_task_baseline_guard as m06b
from app.tests.test_task_baseline_guard import _cleanup, _code, _mission, _update

SHA = "0123456789abcdef0123456789abcdef01234567"
PROD = "fedcba9876543210fedcba9876543210fedcba98"
PLAN = "planning.execution.manage"
ORCH = "mission.orchestrate"


@pytest.fixture
def runner(monkeypatch):
    runner = m06b.Runner()

    async def slots(db):
        return 10

    monkeypatch.setattr(m06b.demand_routes, "dispatch_agent_run", runner)
    monkeypatch.setattr(m06b.demand_routes, "_send_notice", m06b.AsyncMock())
    monkeypatch.setattr(m06b.demand_routes, "_dispatch_slots", slots)
    return runner


@pytest_asyncio.fixture
async def world(admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "MISSION_TOOLS_ENABLED", True)
    command_receipts.agent_write_limiter.reset()
    w = World(admin_headers)
    w.targets: list[str] = []
    await w.setup()
    yield w
    async with AsyncSessionLocal() as db:
        if w.agent_ids:
            await db.execute(text("DELETE FROM company.agent_command_receipts WHERE principal_id = ANY(:ids)"),
                             {"ids": list(w.agent_ids)})
        await db.execute(text("DELETE FROM company.agent_command_receipts WHERE idempotency_key LIKE :k"),
                         {"k": f"m07-{w.tag}-%"})
        if w.targets:
            await db.execute(text("DELETE FROM company.environment_releases WHERE target = ANY(:t)"),
                             {"t": w.targets})
        await db.commit()
    await _cleanup(w)
    command_receipts.agent_write_limiter.reset()


def _key(world) -> str:
    return f"m07-{world.tag}-{uuid.uuid4().hex}"


async def _get(world, path, headers=None):
    async with world.client(headers) as client:
        return await client.get(path)


async def _post(world, path, body, headers=None):
    async with world.client(headers) as client:
        return await client.post(path, json=body)


async def _board(world, mission, headers=None) -> dict:
    response = await _get(world, f"/api/v1/missions/{mission.project_id}/executions", headers)
    assert response.status_code == 200, response.text
    return response.json()


def _row(board, task) -> dict:
    return next(r for r in board["tasks"] if r["task_id"] == str(task.id))


def _blocked(row, action) -> str | None:
    return next((b["reason"] for b in row["blocked_actions"] if b["action"] == action), None)


async def _add(*rows):
    async with AsyncSessionLocal() as db:
        db.add_all(rows)
        await db.commit()


async def _execution(task, status, evidence=None, attempt=1) -> TaskExecution:
    async with AsyncSessionLocal() as db:
        assignment_id = await db.scalar(select(TaskAssignment.id).where(
            TaskAssignment.task_id == task.id, TaskAssignment.status == "active"))
        execution = TaskExecution(task_id=task.id, attempt_number=attempt, status=status, assignment_id=assignment_id,
                                  evidence_ref=evidence, started_at=datetime.now(timezone.utc))
        db.add(execution)
        await db.flush()
        if evidence:
            db.add(AuditEvent(entity_type="task_execution", entity_id=execution.id, event_type="execution_reported",
                              actor="test", payload={"status": "reported", "evidence": [evidence, "file:a.py"]}))
        await db.commit()
        return execution


def _demand(task, agent_id, path, **fields) -> AgentDemand:
    return AgentDemand(from_agent="m07", subject=f"m07 {task.title}", body="x", origin_type="task",
                       origin_id=task.id, target_agent_id=agent_id, working_path=path, **fields)


async def _path(project_id) -> str:
    async with AsyncSessionLocal() as db:
        return (await db.get(Project, project_id)).working_directory_path


# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_board_state_precedence(world, runner):
    mission = await _mission(world)
    path = await _path(mission.project_id)
    reviewer = await world.agent("rev")
    reviewer_membership = await _member(mission.project_id, reviewer, can_review=True)
    t = {name: await mission.task(name) for name in (
        "ready", "blocked", "running", "uncertain", "queued", "scheduled", "awaiting", "reported",
        "changes", "proven", "historical", "cancelled")}
    unassigned = await _task(mission.project_id, "unassigned")
    await _add(TaskDependency(task_id=t["blocked"].id, depends_on_task_id=t["ready"].id))
    await mission.baseline([*[x.id for x in t.values()], unassigned.id])
    now = datetime.now(timezone.utc)
    await _add(
        _demand(t["running"], mission.executor, path, dispatch_status="running", agent_run_id=str(uuid.uuid4()),
                dispatched_at=now - timedelta(minutes=21), dispatch_deadline_at=now + timedelta(minutes=24)),
        # Uncertain beats running, whichever is newer.
        _demand(t["uncertain"], mission.executor, path, dispatch_status="running", agent_run_id=str(uuid.uuid4())),
        _demand(t["uncertain"], mission.executor, path, dispatch_status="failed", agent_run_id=str(uuid.uuid4()),
                dispatch_error="Dispatch outcome is uncertain"),
        _demand(t["queued"], mission.executor, path, scheduled_at=now - timedelta(minutes=1)),
        _demand(t["scheduled"], mission.executor, path, scheduled_at=now + timedelta(days=2)),
    )
    await _execution(t["awaiting"], "verified", f"git:{SHA}")
    await _execution(t["reported"], "reported", f"git:{SHA}")
    changes = await _execution(t["changes"], "verified", f"git:{SHA}")
    proven = await _execution(t["proven"], "verified", f"git:{SHA}")
    await _add(
        TaskExecutionReview(execution_id=changes.id, reviewer_membership_id=reviewer_membership,
                            status="changes_requested", feedback="fix it", decided_at=now),
        TaskExecutionReview(execution_id=proven.id, reviewer_membership_id=reviewer_membership,
                            status="approved", decided_at=now),
    )
    await _update(ProjectTask, t["proven"].id, status="done")
    await _update(ProjectTask, t["historical"].id, status="done")
    await _update(ProjectTask, t["cancelled"].id, status="cancelled")

    board = await _board(world, mission)
    states = {name: _row(board, task)["execution_state"] for name, task in t.items()}
    assert states == {
        "ready": "ready", "blocked": "blocked", "running": "running", "uncertain": "uncertain",
        "queued": "queued", "scheduled": "scheduled", "awaiting": "awaiting_review", "reported": "reported",
        "changes": "changes_requested", "proven": "done_proven", "historical": "done_historical",
        "cancelled": "cancelled",
    }, states
    assert _row(board, unassigned)["execution_state"] == "not_ready"
    assert "unassigned" in _row(board, unassigned)["missing"]
    running = _row(board, t["running"])["execution"]
    assert 1200 <= running["elapsed_seconds"] < 1400 and running["deadline_at"]
    # Topological order: a task after what it depends on.
    order = [r["task_id"] for r in board["tasks"]]
    assert order.index(str(t["ready"].id)) < order.index(str(t["blocked"].id))
    assert _row(board, t["blocked"])["depends_on"][0]["number"] == t["ready"].number
    # Evidence of a verified execution, with who checked and who reviewed.
    evidence = _row(board, t["proven"])["evidence"]
    assert evidence[0]["ref"] == f"git:{SHA}" and evidence[0]["verified"] is True
    assert evidence[0]["reviewed_by"]["status"] == "approved" and evidence[1]["verified"] is None
    assert board["mission"]["baseline"]["id"] and board["mission"]["state"] == "active"


@pytest.mark.asyncio
async def test_reviewer_equals_executor_flag(world, runner):
    mission = await _mission(world)
    task = await mission.task("self-review")
    await mission.baseline([task.id])
    # The executor's own membership can review: the only "reviewer" is itself.
    async with AsyncSessionLocal() as db:
        from app.db.models.orchestration import ProjectAgentMembership
        membership = await db.get(ProjectAgentMembership, mission.membership)
        membership.can_review = True
        await db.commit()
    execution = await _execution(task, "verified", f"git:{SHA}")
    await _add(TaskExecutionReview(execution_id=execution.id, reviewer_membership_id=mission.membership,
                                   status="changes_requested", feedback="x",
                                   decided_at=datetime.now(timezone.utc)))
    row = _row(await _board(world, mission), task)
    assert row["reviewer_is_executor"] is True
    assert _blocked(row, "request_review") == "REVIEWER_IS_EXECUTOR"
    assert any(c["kind"] == "reviewer_is_executor" and c["severity"] == "blocking"
               for c in (await _board(world, mission))["conflicts"])
    # The route refuses the same way.
    response = await _post(world, f"/api/v1/missions/{mission.project_id}/tasks/{task.id}:request-review",
                           {"execution_id": str(execution.id), "reviewer_agent_id": str(mission.executor),
                            "idempotency_key": _key(world)})
    assert _code(response) == "REVIEWER_IS_EXECUTOR", response.text
    # A decided review is never offered as decidable.
    assert row["review"]["decided"] is True and "approve_review" not in row["allowed_actions"]


@pytest.mark.asyncio
async def test_conflict_same_worktree_and_branch_and_publish(world, runner):
    mission = await _mission(world)
    other = await _mission(world)
    path = await _path(mission.project_id)
    a = await mission.task("a")
    b = await mission.task("b")
    c = await mission.task("c")
    d = await other.task("d")
    common = await world.common_project()
    plain = await _task(uuid.UUID(common["id"]), "plain")
    target = f"m07-{world.tag}"
    branch = f"/srv/forgehub-test/m07-repo-{world.tag}#feat"
    await _add(
        TaskExecutionTarget(task_id=c.id, kind="branch", target_key=branch),
        TaskExecutionTarget(task_id=d.id, kind="branch", target_key=branch),
        TaskExecutionTarget(task_id=c.id, kind="publish", target_key=f"production:{target}"),
        TaskExecutionTarget(task_id=plain.id, kind="publish", target_key=f"production:{target}"),
    )
    run = dict(dispatch_status="running", agent_run_id=str(uuid.uuid4()))
    await _add(
        _demand(a, mission.executor, path, **run),
        _demand(b, mission.executor, path, scheduled_at=datetime.now(timezone.utc)),
        _demand(c, mission.executor, f"/srv/forgehub-test/m07-c-{world.tag}", **{**run, "agent_run_id": "c"}),
        _demand(d, other.executor, await _path(other.project_id), **{**run, "agent_run_id": "d"}),
        _demand(plain, other.executor, "/srv/forgehub-test/m07-plain", **{**run, "agent_run_id": "p"}),
    )
    board = await _board(world, mission)
    kinds = {(cf["kind"], tuple(sorted(cf["task_ids"]))) for cf in board["conflicts"]}
    assert ("same_worktree", tuple(sorted([str(a.id), str(b.id)]))) in kinds, kinds
    assert ("same_branch", tuple(sorted([str(c.id), str(d.id)]))) in kinds, kinds
    assert ("same_publish_target", tuple(sorted([str(c.id), str(plain.id)]))) in kinds, kinds
    publish = next(cf for cf in board["conflicts"] if cf["kind"] == "same_publish_target")
    assert publish["outside_mission"] == [plain.number] and publish["severity"] == "blocking"
    assert publish["id"] in _row(board, c)["conflicts"]


@pytest.mark.asyncio
async def test_publish_missing_production_commit(world, runner, monkeypatch):
    mission = await _mission(world)
    task = await mission.task("publish")
    target = f"m07p-{world.tag}"
    world.targets.append(target)
    await _add(TaskExecutionTarget(task_id=task.id, kind="publish", target_key=f"production:{target}"))
    await _execution(task, "reported", f"git:{SHA}")

    board = await _board(world, mission)
    assert [c["kind"] for c in board["conflicts"]] == ["production_unknown"]

    response = await _post(world, "/api/v1/environments/releases", {
        "environment": "production", "target": target, "commit_sha": PROD})
    assert response.status_code == 201, response.text

    async def missing(repo, commit, ref):
        assert (commit, ref) == (PROD, SHA)
        return False, "not an ancestor"

    monkeypatch.setattr(mission_board, "commit_is_integrated", missing)
    conflicts = (await _board(world, mission))["conflicts"]
    assert [(c["kind"], c["severity"]) for c in conflicts] == [("publish_missing_production", "blocking")]

    async def unavailable(repo, commit, ref):
        raise EvidenceUnverifiable("host-bridge unreachable")

    monkeypatch.setattr(mission_board, "commit_is_integrated", unavailable)
    conflicts = (await _board(world, mission))["conflicts"]
    # Unknown is a warning of its own, never "no conflict".
    assert [(c["kind"], c["severity"]) for c in conflicts] == [("publish_ancestry_unknown", "warning")]


@pytest.mark.asyncio
async def test_environments_never_inferred(world, runner):
    mission = await _mission(world)
    task = await mission.task("env")
    target = f"m07e-{world.tag}"
    world.targets.append(target)
    await _add(TaskExecutionTarget(task_id=task.id, kind="publish", target_key=f"test:{target}"))
    strip = (await _board(world, mission))["environments"]
    assert {(e["environment"], e["source"]) for e in strip} == {("test", "no_record"), ("production", "no_record")}

    imported = await _post(world, "/api/v1/environments/releases", {
        "environment": "production", "target": target, "commit_sha": PROD, "source": "imported"})
    assert imported.status_code == 201, imported.text
    released = await _post(world, "/api/v1/environments/releases", {
        "environment": "test", "target": target, "commit_sha": SHA, "branch": "develop",
        "task_id": str(task.id)})
    assert released.status_code == 201 and released.json()["task_number"] == task.number
    strip = {e["environment"]: e for e in (await _board(world, mission))["environments"]}
    assert strip["production"]["source"] == "imported" and strip["test"]["commit_sha"] == SHA
    assert strip["test"]["task_number"] == task.number

    # One writer, guarded: a non-admin person and an agent without the
    # delegation are refused; the same instant twice is 409.
    agent = await world.agent("publisher")
    no_grant = await world.agent_token(agent, None)
    body = {"environment": "test", "target": target, "commit_sha": SHA}
    assert _code(await _post(world, "/api/v1/environments/releases", body, no_grant)) == "DELEGATION_REQUIRED"
    granted = await world.agent_token(agent, ["environment.release.record"])
    response = await _post(world, "/api/v1/environments/releases", body, granted)
    assert response.status_code == 201 and response.json()["released_by"].startswith("mission-test-publisher")
    async with AsyncSessionLocal() as db:
        events = list((await db.execute(select(AuditEvent).where(
            AuditEvent.event_type == "environment_release_recorded",
            AuditEvent.entity_id == uuid.UUID(response.json()["id"])))).scalars())
        assert events and events[0].payload["principal_id"] == str(agent)
        at = (await db.get(EnvironmentRelease, uuid.UUID(response.json()["id"]))).released_at
    dup = await _post(world, "/api/v1/environments/releases", {**body, "released_at": at.isoformat()})
    assert dup.status_code == 409 and _code(dup) == "RELEASE_ALREADY_RECORDED"


@pytest.mark.asyncio
async def test_allowed_actions_match_guards(world, runner):
    mission = await _mission(world)
    reviewer = await world.agent("rev")
    await _member(mission.project_id, reviewer, can_review=True)
    ready = await mission.task("ready")
    waiting = await mission.task("waiting")
    verified = await mission.task("verified")
    outside = await mission.task("outside-baseline")
    await _add(TaskDependency(task_id=waiting.id, depends_on_task_id=ready.id))
    await mission.baseline([ready.id, waiting.id, verified.id])
    execution = await _execution(verified, "verified", f"git:{SHA}")

    board = await _board(world, mission)
    rows = {name: _row(board, task) for name, task in
            (("ready", ready), ("waiting", waiting), ("verified", verified), ("outside", outside))}
    assert "dispatch" in rows["ready"]["allowed_actions"]
    assert _blocked(rows["waiting"], "dispatch") == "DEPENDENCIES_NOT_DONE"
    assert _blocked(rows["outside"], "dispatch") == "TASK_NOT_IN_BASELINE"
    assert _blocked(rows["ready"], "request_review") == "EXECUTION_NOT_VERIFIED"
    assert "request_review" in rows["verified"]["allowed_actions"]
    assert [c["name"] for c in rows["verified"]["reviewer_candidates"] if c["eligible"]]

    # Every blocked one fails on its route with the same reason ...
    response = await _post(world, f"/api/v1/tasks/{waiting.id}/dispatch", {})
    assert response.status_code == 409 and response.json()["detail"]["blocking"], response.text
    response = await _post(world, f"/api/v1/tasks/{outside.id}/dispatch", {})
    assert _code(response) == "TASK_NOT_IN_BASELINE", response.text
    response = await _post(world, f"/api/v1/missions/{mission.project_id}/tasks/{ready.id}:request-review", {
        "execution_id": str(execution.id), "reviewer_agent_id": str(reviewer), "idempotency_key": _key(world)})
    assert _code(response) == "EXECUTION_NOT_FOUND", response.text  # the ready task has no such execution
    # ... and every allowed one succeeds.
    response = await _post(world, f"/api/v1/tasks/{ready.id}/dispatch", {})
    assert response.status_code == 200, response.text
    response = await _post(world, f"/api/v1/missions/{mission.project_id}/tasks/{verified.id}:request-review", {
        "execution_id": str(execution.id), "reviewer_agent_id": str(reviewer), "idempotency_key": _key(world)})
    assert response.status_code == 201, response.text

    board = await _board(world, mission)
    ready_row = _row(board, ready)
    assert ready_row["execution_state"] == "running"
    assert _blocked(ready_row, "dispatch") == "TASK_RUN_IN_FLIGHT"
    assert _code(await _post(world, f"/api/v1/tasks/{ready.id}/dispatch", {})) == "TASK_RUN_IN_FLIGHT"
    assert _blocked(ready_row, "assign") == "TASK_RUN_IN_FLIGHT"
    assert _blocked(_row(board, verified), "request_review") == "REVIEW_ALREADY_OPEN"

    # The board's "return" is allowed for the verified task; the route agrees.
    assert "return" in _row(board, verified)["allowed_actions"]
    response = await _post(world, f"/api/v1/missions/{mission.project_id}/tasks/{verified.id}:return", {
        "execution_id": str(execution.id), "reason": "missing test", "idempotency_key": _key(world)})
    assert response.status_code == 200, response.text
    assert _row(await _board(world, mission), verified)["execution_state"] == "changes_requested"

    # Mission switch off: every mission command is blocked on the board too.
    settings.MISSION_TOOLS_ENABLED = False
    try:
        row = _row(await _board(world, mission), verified)
        assert _blocked(row, "assign") == "MISSION_TOOLS_DISABLED"
    finally:
        settings.MISSION_TOOLS_ENABLED = True


@pytest.mark.asyncio
async def test_non_member_agent_404_and_read_permissions(world, runner):
    mission = await _mission(world)
    task = await mission.task("t")
    stranger = await world.agent_token(await world.agent("stranger"), [PLAN, ORCH])
    for path in ("executions", "timeline"):
        response = await _get(world, f"/api/v1/missions/{mission.project_id}/{path}", stranger)
        assert response.status_code == 404 and _code(response) == "MISSION_NOT_FOUND", response.text
    listed = await _get(world, "/api/v1/missions", stranger)
    assert listed.status_code == 200
    assert str(mission.project_id) not in {m["project_id"] for m in listed.json()["items"]}

    # A member agent sees it, and only as itself: no admin action.
    member = await world.agent_token(mission.executor, None)
    board = await _board(world, mission, member)
    row = _row(board, task)
    assert _blocked(row, "dispatch") == "DELEGATION_REQUIRED" and board["viewer"]["principal_type"] == "agent"

    # A person without admin or the product module: 403; no action ever.
    username = f"m07-user-{world.tag}"
    async with AsyncSessionLocal() as db:
        user = User(username=username, hashed_password="x", is_admin=False)
        db.add(user)
        await db.commit()
        world.user_ids.append(user.id)
    person = {"Authorization": f"Bearer {create_access_token(username)}"}
    response = await _get(world, f"/api/v1/missions/{mission.project_id}/executions", person)
    assert response.status_code == 403, response.text
    response = await _post(world, "/api/v1/environments/releases",
                           {"environment": "test", "target": "m07-x", "commit_sha": SHA}, person)
    assert response.status_code == 403 and _code(response) == "ADMIN_ONLY"


@pytest.mark.asyncio
async def test_mission_list_filters_and_timeline(world, runner):
    first = await _mission(world)
    second = await _mission(world)
    await _update(m06b.ProjectMission, second.project_id, priority=10)
    task = await first.task("timeline")
    await first.baseline([task.id])
    assert (await _post(world, f"/api/v1/tasks/{task.id}/dispatch", {})).status_code == 200

    listed = await _get(world, f"/api/v1/missions?state=active&q={world.tag}")
    assert listed.status_code == 200, listed.text
    response = await _get(world, "/api/v1/missions?state=active")
    ours = [m for m in response.json()["items"] if m["project_id"] in (str(first.project_id), str(second.project_id))]
    assert [m["project_id"] for m in ours] == [str(second.project_id), str(first.project_id)]  # priority 10 first
    summary = next(m for m in ours if m["project_id"] == str(first.project_id))
    assert summary["running"] == 1 and summary["progress"] == {"done_proven": 0, "total": 1}
    drafts = await _get(world, "/api/v1/missions?state=draft")
    assert str(first.project_id) not in {m["project_id"] for m in drafts.json()["items"]}

    timeline = await _get(world, f"/api/v1/missions/{first.project_id}/timeline")
    assert timeline.status_code == 200, timeline.text
    events = timeline.json()["items"]
    assert any(e["event_type"] == "task.dispatched" and e["task_number"] == task.number for e in events)
    assert all("idempotency_key" not in e["payload"] for e in events)
