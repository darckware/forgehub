"""M0.8: the orchestrator decision cycle (MISSION_ORCHESTRATOR_CYCLE_SPEC.md §2-§9;
acceptance: 07 line M0.8).

Runs only against the isolated test database. Routes, guards, receipts and
queries are real; the host-bridge start and the Telegram notice are replaced
by M0.2c's `runner`, the evidence bridge is bound in process to temporary git
repositories (M0.6a's `bind_evidence_bridge`), and ask_marcelo's Telegram goes
to the T.3 integration stub. The cycle loop never runs under test: every pass
is called once, by hand.
"""
import subprocess
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select, text

from app.api.routes import demand as demand_routes
from app.core import mission_cycle
from app.core.config import settings
from app.core.demand_dispatch_guard import reserve_dispatch
from app.core.demand_workflow import WorkflowBlocked
from app.db.base import AsyncSessionLocal
from app.db.models.agent import AgentSkill
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.mission import MissionDecision, ProjectMission
from app.db.models.mission_cycle import AgentAvailability, MissionContextVersion, MissionSkillProposal
from app.db.models.notification import Notification
from app.db.models.operations import AgentQuestion, AgentRoutine, AgentRoutineRun
from app.db.models.orchestration import TaskExecutionReview
from app.db.models.project import Project
from app.db.models.task import ProjectTask, TaskExecution, TaskExecutionTarget, TaskRequiredSkill
from app.tests.test_mission_base import _force, _member, _row_version
from app.tests.test_mission_dispatch import _mission_row, runner, world  # noqa: F401 -- fixtures
from app.tests import test_task_baseline_guard as m06b
from app.tests.test_task_baseline_guard import DUE, _code, _mission, _queued_demand, _update

PLAN = "planning.execution.manage"
ORCH = "mission.orchestrate"
SP = ZoneInfo("America/Sao_Paulo")
STUB = "http://127.0.0.1:8003"
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.test",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.test"}


@pytest_asyncio.fixture
async def cw(world, runner, monkeypatch):  # noqa: F811 -- the imported fixtures
    """M0.2c's world + runner with the cycle switch on, plus the cleanup of
    what the cycle adds (routine messages, questions, alerts, receipts)."""
    monkeypatch.setattr(settings, "MISSION_CYCLE_ENABLED", True)
    world.runner = runner
    yield world
    async with AsyncSessionLocal() as db:
        ids = list(world.agent_ids)
        if ids:
            await db.execute(text("DELETE FROM company.mission_decisions WHERE question_id IN "
                                  "(SELECT id FROM company.agent_questions WHERE agent_id = ANY(:ids))"), {"ids": ids})
            await db.execute(text("DELETE FROM company.agent_questions WHERE agent_id = ANY(:ids)"), {"ids": ids})
            await db.execute(text("DELETE FROM company.agent_demands WHERE target_agent_id = ANY(:ids) "
                                  "OR from_agent_id = ANY(:ids)"), {"ids": ids})
        await db.execute(text("DELETE FROM company.agent_command_receipts WHERE idempotency_key LIKE :k"),
                         {"k": f"%m08-{world.tag}-%"})
        await db.execute(text("DELETE FROM company.notifications WHERE event_key LIKE 'mission-cycle:%' "
                              "AND message LIKE :t"), {"t": f"%{world.tag}%"})
        await db.commit()


def _key(world) -> str:  # noqa: F811 -- imported pytest fixtures are injected by name
    return f"m08-{world.tag}-{uuid.uuid4().hex}"


async def _orch_headers(world, mission, actions=(PLAN, ORCH)):  # noqa: F811 -- imported pytest fixtures are injected by name
    return await world.agent_token((await _mission_row(mission)).orchestrator_agent_id, list(actions))


async def _cycle(world, mission, headers=None):  # noqa: F811 -- imported pytest fixtures are injected by name
    async with world.client(headers) as client:
        response = await client.get(f"/api/v1/missions/{mission.project_id}/cycle")
    assert response.status_code == 200, response.text
    return response.json()


async def _decide(world, mission, headers, action, reason="cycle decision", task_id=None, proposal_id=None,  # noqa: F811 -- imported pytest fixtures are injected by name
                  cycle_id=None, key=None, **params):
    body = {"action": action, "reason": reason, "idempotency_key": key or _key(world),
            "params": {k: (str(v) if isinstance(v, (uuid.UUID, datetime)) else v) for k, v in params.items()}}
    if headers:
        versions = getattr(world, "decision_context_versions", {})
        if body["idempotency_key"] not in versions:
            async with AsyncSessionLocal() as db:
                context = await mission_cycle.latest_context_version(db, mission.project_id)
                versions[body["idempotency_key"]] = context.version if context else 0
        world.decision_context_versions = versions
        body["expected_context_version"] = versions[body["idempotency_key"]]
    if task_id:
        body["task_id"] = str(task_id)
    if proposal_id:
        body["proposal_id"] = proposal_id
    if cycle_id:
        body["cycle_id"] = str(cycle_id)
    async with world.client(headers) as client:
        return await client.post(f"/api/v1/missions/{mission.project_id}/decisions", json=body)


def _proposals(cycle, task_id=None, action=None):
    return [p for p in cycle["proposals"]
            if (task_id is None or p["task_id"] == str(task_id)) and (action is None or p["action"] == action)]


async def _decisions(project_id) -> list[MissionDecision]:
    async with AsyncSessionLocal() as db:
        return list((await db.execute(select(MissionDecision).where(MissionDecision.mission_project_id == project_id)
                                      .order_by(MissionDecision.created_at))).scalars())


async def _demand(demand_id) -> AgentDemand:
    async with AsyncSessionLocal() as db:
        return await db.get(AgentDemand, demand_id)


async def _finalize(demand_id, status, output):
    async with AsyncSessionLocal() as db:
        await demand_routes._finalize_dispatch(db, demand_id, {"status": status, "output": output})
        await db.commit()


async def _set_executions(task_id, **fields):
    async with AsyncSessionLocal() as db:
        for execution in (await db.execute(select(TaskExecution).where(TaskExecution.task_id == task_id))).scalars():
            for key, value in fields.items():
                setattr(execution, key, value)
        await db.commit()


async def _ready_task(mission, title, **fields):
    task = await mission.task(title, **fields)
    return task


async def _baselined(mission, *titles):
    tasks = [await mission.task(t) for t in titles]
    await mission.baseline([t.id for t in tasks])
    return tasks


async def _verified_execution(task, evidence, executor_assignment=True) -> uuid.UUID:
    from app.db.models.task import TaskAssignment

    async with AsyncSessionLocal() as db:
        assignment_id = (await db.execute(select(TaskAssignment.id).where(
            TaskAssignment.task_id == task.id, TaskAssignment.status == "active"))).scalars().first()
        execution = TaskExecution(task_id=task.id, attempt_number=1, status="verified", evidence_ref=evidence,
                                  assignment_id=assignment_id if executor_assignment else None,
                                  started_at=datetime.now(timezone.utc) - timedelta(hours=1))
        db.add(execution)
        await db.commit()
        return execution.id


# ---------------------------------------------------------------------------
# §2.1, §2.2: routine and triggers
# ---------------------------------------------------------------------------
async def _transition(world, mission, to, reason="test", headers=None):  # noqa: F811 -- imported pytest fixtures are injected by name
    async with world.client(headers) as client:
        return await client.post(f"/api/v1/missions/{mission.project_id}:transition", json={
            "to": to, "reason": reason, "expected_row_version": await _row_version(mission.project_id)})


async def _routine(project_id) -> AgentRoutine | None:
    async with AsyncSessionLocal() as db:
        return await mission_cycle.mission_routine(db, project_id)


@pytest.mark.asyncio
async def test_routine_created_on_activation_and_disabled_on_pause(cw, monkeypatch):
    mission = await _mission(cw)
    monkeypatch.setattr(settings, "MISSION_CYCLE_ENABLED", False)
    assert (await _transition(cw, mission, "paused")).status_code == 200
    assert (await _transition(cw, mission, "active")).status_code == 200
    assert await _routine(mission.project_id) is None  # switch off: no cycle anywhere
    monkeypatch.setattr(settings, "MISSION_CYCLE_ENABLED", True)

    assert (await _transition(cw, mission, "paused")).status_code == 200
    assert (await _transition(cw, mission, "active")).status_code == 200
    routine = await _routine(mission.project_id)
    assert routine is not None and routine.enabled and routine.kind == "coordination"
    assert routine.agent_id == (await _mission_row(mission)).orchestrator_agent_id
    assert routine.schedule == "*/30 * * * *" and routine.deadline_minutes == 20

    assert (await _transition(cw, mission, "paused")).status_code == 200
    paused = await _routine(mission.project_id)
    assert paused.id == routine.id and paused.enabled is False  # toggled, never deleted
    assert (await _transition(cw, mission, "active")).status_code == 200
    assert (await _routine(mission.project_id)).enabled is True
    assert (await _transition(cw, mission, "cancelled")).status_code == 200
    assert (await _routine(mission.project_id)).enabled is False
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(func.count(AgentRoutine.id)).where(
            AgentRoutine.mission_project_id == mission.project_id)) == 1


async def _active_with_routine(cw):
    mission = await _mission(cw)
    assert (await _transition(cw, mission, "paused")).status_code == 200
    assert (await _transition(cw, mission, "active")).status_code == 200
    return mission


@pytest.mark.asyncio
async def test_event_triggers_debounced(cw):
    mission = await _active_with_routine(cw)
    pid = mission.project_id
    async with AsyncSessionLocal() as db:
        assert await mission_cycle.request_mission_cycle(db, pid, "task done") == "started"
    async with AsyncSessionLocal() as db:
        outcomes = [await mission_cycle.request_mission_cycle(db, pid, f"burst {i}") for i in range(3)]
    assert outcomes == ["rerun_requested"] * 3
    async with AsyncSessionLocal() as db:
        runs = list((await db.execute(select(AgentRoutineRun).join(AgentRoutine).where(
            AgentRoutine.mission_project_id == pid))).scalars())
        assert len(runs) == 1 and (await db.get(ProjectMission, pid)).cycle_rerun_requested is True
        runs[0].status = "completed"
        await db.commit()
    async with AsyncSessionLocal() as db:
        summary = await mission_cycle.run_mission_cycle_pass(db, project_ids=[pid])
    assert summary["started"] == [str(pid)]
    async with AsyncSessionLocal() as db:
        assert (await db.get(ProjectMission, pid)).cycle_rerun_requested is False
        assert await db.scalar(select(func.count(AgentRoutineRun.id)).join(AgentRoutine).where(
            AgentRoutine.mission_project_id == pid)) == 2  # exactly one more
    async with AsyncSessionLocal() as db:
        again = await mission_cycle.run_mission_cycle_pass(db, project_ids=[pid])
    assert again["started"] == [] and again["rerun_requested"] == [str(pid)] or again["started"] == []

    # Events while paused are recorded and dropped.
    assert (await _transition(cw, mission, "paused")).status_code == 200
    async with AsyncSessionLocal() as db:
        assert await mission_cycle.request_mission_cycle(db, pid, "late event") == "dropped"
        assert await db.scalar(select(func.count(AuditEvent.id)).where(
            AuditEvent.entity_id == pid, AuditEvent.event_type == "mission_cycle_event_dropped")) == 1


@pytest.mark.asyncio
async def test_task_outcome_triggers_a_cycle(cw):
    mission = await _active_with_routine(cw)
    [task] = await _baselined(mission, "evented")
    headers = await _orch_headers(cw, mission)
    assert (await _decide(cw, mission, headers, "dispatch", task_id=task.id)).status_code == 201
    async with AsyncSessionLocal() as db:
        (await db.get(ProjectMission, mission.project_id)).cycle_event_cursor = datetime.now(timezone.utc)
        await db.commit()
    [demand] = await m06b_demands(task.id)
    await _finalize(demand.id, "completed", "done\nSTATUS: DONE")
    async with AsyncSessionLocal() as db:
        summary = await mission_cycle.run_mission_cycle_pass(db, project_ids=[mission.project_id])
    assert summary["started"] == [str(mission.project_id)]
    async with AsyncSessionLocal() as db:
        run = (await db.execute(select(AgentRoutineRun).join(AgentRoutine).where(
            AgentRoutine.mission_project_id == mission.project_id))).scalar_one()
        assert "dispatch_completed" in run.detail


async def m06b_demands(task_id) -> list[AgentDemand]:
    async with AsyncSessionLocal() as db:
        return list((await db.execute(select(AgentDemand).where(AgentDemand.origin_id == task_id)
                                      .order_by(AgentDemand.created_at))).scalars())


# ---------------------------------------------------------------------------
# §2.3, §3: proposals and decisions
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_proposals_deterministic(cw):
    mission = await _mission(cw)
    first, second = await _baselined(mission, "alpha", "beta")
    headers = await _orch_headers(cw, mission)
    a = await _cycle(cw, mission, headers)
    b = await _cycle(cw, mission, headers)
    assert a["proposals"] == b["proposals"] and a["board_hash"] == b["board_hash"]
    assert [(p["task_number"], p["action"]) for p in a["proposals"]] == [
        (first.number, "dispatch"), (second.number, "dispatch")]
    assert all(p["allowed"] and p["autonomy_required"] == "N0" for p in a["proposals"])


@pytest.mark.asyncio
async def test_dispatch_from_cycle_goes_through_guards(cw):
    mission = await _mission(cw)
    stale, busy_a, busy_b = await _baselined(mission, "stale", "busy-a", "busy-b")
    headers = await _orch_headers(cw, mission)

    await _update(ProjectTask, stale.id, description="changed after approval")
    refused = await _decide(cw, mission, headers, "dispatch", task_id=stale.id)
    assert refused.status_code == 409, refused.text
    stale_code = _code(refused)
    assert stale_code and refused.json()["detail"]["decision_id"]

    # Two tasks of one mission share its worktree: the second waits.
    assert (await _decide(cw, mission, headers, "dispatch", task_id=busy_a.id)).status_code == 201
    second = await _decide(cw, mission, headers, "dispatch", task_id=busy_b.id)
    assert second.status_code == 409 and _code(second) == "TARGET_BUSY", second.text

    await _force(mission.project_id, state="paused", paused_from_state="active")
    paused = await _decide(cw, mission, headers, "dispatch", task_id=busy_b.id)
    assert paused.status_code == 409, paused.text

    refused_rows = [d for d in await _decisions(mission.project_id) if d.status == "refused"]
    assert [d.refusal_code for d in refused_rows] == [stale_code, "TARGET_BUSY", _code(paused)]
    assert all(d.reason and d.actor_type == "agent" for d in refused_rows)
    assert len(cw.runner.runs) == 1  # only busy-a ever reached the runner


@pytest.mark.asyncio
async def test_two_production_publications_serialized_across_messages(cw):
    """D-M0-2: two simultaneous publications of production are refused, even
    from two different missions with different orchestrators and worktrees."""
    first, second = await _mission(cw), await _mission(cw)
    [task_a] = await _baselined(first, "publish-a")
    [task_b] = await _baselined(second, "publish-b")
    async with AsyncSessionLocal() as db:
        for task in (task_a, task_b):
            db.add(TaskExecutionTarget(task_id=task.id, kind="publish", target_key="production:forgehub-m08"))
        await db.commit()
    await first.baseline([task_a.id], name="with target")
    await second.baseline([task_b.id], name="with target")
    ok = await _decide(cw, first, await _orch_headers(cw, first), "dispatch", task_id=task_a.id)
    assert ok.status_code == 201, ok.text
    refused = await _decide(cw, second, await _orch_headers(cw, second), "dispatch", task_id=task_b.id)
    assert refused.status_code == 409 and _code(refused) == "TARGET_BUSY", refused.text
    assert "publish:production:forgehub-m08" in refused.json()["detail"]["message"]


@pytest.mark.asyncio
async def test_every_decision_recorded_with_reason(cw):
    mission = await _mission(cw)
    [task] = await _baselined(mission, "reasoned")
    headers = await _orch_headers(cw, mission)
    cycle = await _cycle(cw, mission, headers)
    [proposal] = _proposals(cycle, task.id)

    missing = await _decide(cw, mission, headers, "defer", reason="", task_id=task.id)
    assert missing.status_code == 422
    assert await _decisions(mission.project_id) == []

    deferred = await _decide(cw, mission, headers, "defer", reason="waiting for the other mission",
                             task_id=task.id, proposal_id=proposal["proposal_id"])
    assert deferred.status_code == 201, deferred.text
    assert deferred.json()["status"] == "deferred"
    assert deferred.json()["facts"]["reason_code"] == "ready"
    assert deferred.json()["facts"]["board_hash"] == cycle["board_hash"]
    applied = await _decide(cw, mission, headers, "dispatch", reason="ready and executor free",
                            task_id=task.id, proposal_id=proposal["proposal_id"])
    assert applied.status_code == 201 and applied.json()["status"] == "applied"
    assert applied.json()["demand_id"] and applied.json()["facts"]["context_version_id"]

    key = _key(cw)
    once = await _decide(cw, mission, headers, "defer", reason="once", task_id=task.id, key=key)
    replay = await _decide(cw, mission, headers, "defer", reason="once", task_id=task.id, key=key)
    assert replay.status_code == 200 and replay.json()["id"] == once.json()["id"]

    rows = await _decisions(mission.project_id)
    assert [r.status for r in rows] == ["deferred", "applied", "deferred"]
    async with AsyncSessionLocal() as db:
        audits = list((await db.execute(select(AuditEvent.event_type).where(
            AuditEvent.entity_id == mission.project_id,
            AuditEvent.event_type.like("mission_decision_%")))).scalars())
    assert sorted(audits) == ["mission_decision_defer", "mission_decision_defer", "mission_decision_dispatch"]
    stale = await _decide(cw, mission, headers, "dispatch", task_id=task.id, proposal_id="0000000000000000")
    assert _code(stale) == "PROPOSAL_NOT_CURRENT"


@pytest.mark.asyncio
async def test_orchestrator_cannot_accept_approve_cancel_or_raise_retry_budget(cw):
    mission = await _mission(cw)
    headers = await _orch_headers(cw, mission)
    for action in ("approve_plan", "approve_baseline", "accept", "cancel", "publish", "authorize_retry",
                   "raise_autonomy", "grant_delegation", "decide_item"):
        response = await _decide(cw, mission, headers, action)
        assert response.status_code == 422, (action, response.text)
    for to in ("cancelled", "completed"):
        response = await _transition(cw, mission, to, headers=headers)
        assert response.status_code in (403, 409), response.text
    async with AsyncSessionLocal() as db:
        demand = AgentDemand(from_agent="test", subject=f"m08 retry {cw.tag}", body="x", origin_type="task",
                             dispatch_status="failed", dispatch_attempts=3)
        db.add(demand)
        await db.commit()
    async with cw.client(headers) as client:
        response = await client.post(f"/api/v1/demands/{demand.id}/decision",
                                     json={"action": "authorize_retry", "reason": "more"})
    assert response.status_code in (401, 403), response.text
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM company.agent_demands WHERE id = :id"), {"id": demand.id})
        await db.commit()
    assert (await _mission_row(mission)).state == "active"


@pytest.mark.asyncio
async def test_pause_only_when_blocked(cw):
    mission = await _active_with_routine(cw)
    headers = await _orch_headers(cw, mission)
    refused = await _decide(cw, mission, headers, "pause", reason="it is slow")
    assert refused.status_code == 403 and _code(refused) == "ORCHESTRATOR_PAUSE_ONLY_WHEN_BLOCKED"
    applied = await _decide(cw, mission, headers, "pause", reason="blocked:deadline")
    assert applied.status_code == 201, applied.text
    assert (await _mission_row(mission)).state == "paused"
    assert (await _routine(mission.project_id)).enabled is False
    resume = await _transition(cw, mission, "active", headers=headers)
    assert resume.status_code in (403, 409), resume.text
    assert [d.status for d in await _decisions(mission.project_id)] == ["refused", "applied"]


@pytest.mark.asyncio
async def test_cycle_proposes_pause_when_every_task_is_blocked_or_late(cw):
    mission = await _mission(cw)
    [task] = await _baselined(mission, "late")
    await _force(mission.project_id, deadline_at=datetime.now(timezone.utc) - timedelta(hours=1))
    cycle = await _cycle(cw, mission, await _orch_headers(cw, mission))
    assert [p["reason_code"] for p in _proposals(cycle, action="pause")] == ["blocked:deadline"]
    assert _proposals(cycle, task.id, "dispatch")


@pytest.mark.asyncio
async def test_reassign_never_makes_reviewer_executor(cw):
    mission = await _mission(cw)
    [task] = await _baselined(mission, "reviewed")
    reviewer = await cw.agent("reviewer")
    membership = await _member(mission.project_id, reviewer, can_review=True)
    execution_id = await _verified_execution(task, f"db:project_task:{task.id}")
    async with AsyncSessionLocal() as db:
        db.add(TaskExecutionReview(execution_id=execution_id, reviewer_membership_id=membership, status="pending"))
        await db.commit()
    headers = await _orch_headers(cw, mission)
    refused = await _decide(cw, mission, headers, "reassign", task_id=task.id, agent_id=reviewer)
    assert refused.status_code == 409 and _code(refused) == "ASSIGNEE_IS_REVIEWER", refused.text
    assert [(d.action, d.status, d.refusal_code) for d in await _decisions(mission.project_id)] == [
        ("reassign", "refused", "ASSIGNEE_IS_REVIEWER")]


# ---------------------------------------------------------------------------
# §3.3: quota
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_schedule_on_quota_reset(cw):
    mission = await _mission(cw)
    [task] = await _baselined(mission, "quota")
    headers = await _orch_headers(cw, mission)
    assert (await _decide(cw, mission, headers, "dispatch", task_id=task.id)).status_code == 201
    [demand] = await m06b_demands(task.id)
    await _finalize(demand.id, "failed", "You've hit your 5-hour limit · resets 3:30am")

    now = datetime.now(timezone.utc).astimezone(SP)
    expected = now.replace(hour=3, minute=30, second=0, microsecond=0)
    if expected <= now:
        expected += timedelta(days=1)
    async with AsyncSessionLocal() as db:
        row = await db.get(AgentAvailability, mission.executor)
        assert row.unavailable_until == expected and row.source_demand_id == demand.id
        execution = (await db.execute(select(TaskExecution).where(TaskExecution.task_id == task.id))).scalar_one()
        assert execution.status == "failed"
        assert await db.scalar(select(func.count(TaskExecutionReview.id)).where(
            TaskExecutionReview.execution_id == execution.id)) == 0  # not a rejection
        # The orchestrator decides what follows, not Messages' automatic
        # failure check (Marcelo, 2026-11-03).
        from app.db.models.demand import AgentDemand
        assert await db.scalar(select(func.count(AgentDemand.id)).where(
            AgentDemand.failure_check_source_id == demand.id)) == 0

    cycle = await _cycle(cw, mission, headers)
    [proposal] = _proposals(cycle, task.id)
    assert proposal["action"] == "schedule" and proposal["reason_facts"]["infra"] == "usage_limit"
    scheduled_at = datetime.fromisoformat(proposal["params"]["scheduled_at"])
    assert scheduled_at == expected + timedelta(minutes=5)
    decided = await _decide(cw, mission, headers, "schedule", reason="quota resets at 03:30", task_id=task.id,
                            proposal_id=proposal["proposal_id"], scheduled_at=proposal["params"]["scheduled_at"])
    assert decided.status_code == 201, decided.text
    queued = await _demand(uuid.UUID(decided.json()["demand_id"]))
    assert queued.dispatch_status is None and queued.scheduled_at == scheduled_at

    # Even if due, reserve_dispatch keeps it queued until the reset.
    async with AsyncSessionLocal() as db:
        demand_row = await db.get(AgentDemand, queued.id)
        with pytest.raises(WorkflowBlocked) as blocked:
            await reserve_dispatch(db, demand_row, mission.executor, None)
        assert str(blocked.value.detail).startswith("AGENT_UNAVAILABLE")
        await db.rollback()


@pytest.mark.asyncio
async def test_unmatched_quota_text_writes_nothing(cw):
    mission = await _mission(cw)
    [task] = await _baselined(mission, "plain failure")
    headers = await _orch_headers(cw, mission)
    assert (await _decide(cw, mission, headers, "dispatch", task_id=task.id)).status_code == 201
    [demand] = await m06b_demands(task.id)
    await _finalize(demand.id, "completed", "3 tests fail in test_x.py\nSTATUS: PARTIAL")
    async with AsyncSessionLocal() as db:
        assert await db.get(AgentAvailability, mission.executor) is None
    [proposal] = _proposals(await _cycle(cw, mission, headers), task.id)
    assert (proposal["action"], proposal["reason_code"]) == ("reprocess", "known_failure")


# ---------------------------------------------------------------------------
# §3.4: continuation until the end
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_infra_failure_reprocessed_not_rejected(cw):
    mission = await _mission(cw)
    [task] = await _baselined(mission, "provider")
    other = await cw.agent("other-exec")
    await _member(mission.project_id, other)
    headers = await _orch_headers(cw, mission)
    assert (await _decide(cw, mission, headers, "dispatch", task_id=task.id)).status_code == 201
    [demand] = await m06b_demands(task.id)
    await _finalize(demand.id, "failed", "API Error: 529 {\"type\":\"overloaded_error\"}")

    [proposal] = _proposals(await _cycle(cw, mission, headers), task.id)
    assert (proposal["action"], proposal["reason_facts"]["infra"]) == ("reprocess", "provider_error")
    decided = await _decide(cw, mission, headers, "reprocess", reason="provider overloaded, once",
                            task_id=task.id, proposal_id=proposal["proposal_id"], demand_id=demand.id)
    assert decided.status_code == 201, decided.text
    back = await _demand(demand.id)
    assert back.dispatch_status is None and back.scheduled_at is not None
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(func.count(TaskExecutionReview.id)).join(TaskExecution).where(
            TaskExecution.task_id == task.id)) == 0
        assert (await db.get(ProjectTask, task.id)).status != "cancelled"

    # It fails on infrastructure again: the same role goes to another executor.
    await _update(AgentDemand, demand.id, dispatch_status="failed", dispatch_attempts=2,
                  dispatch_error="The agent run ended as 'failed'.",
                  dispatch_result="API Error: 529 overloaded_error")
    [proposal] = _proposals(await _cycle(cw, mission, headers), task.id)
    assert (proposal["action"], proposal["reason_code"]) == ("reassign", "infra_failure_repeated")
    assert proposal["params"]["agent_id"] == str(other)


@pytest.mark.asyncio
async def test_review_infra_failure_reassigned_to_independent_reviewer(cw):
    mission = await _mission(cw)
    [task] = await _baselined(mission, "review infra")
    first, second = await cw.agent("rev-a"), await cw.agent("rev-b")
    first_membership = await _member(mission.project_id, first, can_review=True)
    await _member(mission.project_id, second, can_review=True)
    execution_id = await _verified_execution(task, f"db:project_task:{task.id}")
    async with AsyncSessionLocal() as db:
        review_demand = AgentDemand(from_agent="test", subject="m08 review", body="x", origin_type="task",
                                    origin_id=task.id, target_agent_id=first, dispatch_status="failed",
                                    agent_run_id=str(uuid.uuid4()), dispatch_error="The agent run ended as 'failed'.",
                                    dispatch_result="Error: 400 INVALID_ARGUMENT", dispatch_attempts=1)
        db.add(review_demand)
        await db.flush()
        review = TaskExecutionReview(execution_id=execution_id, reviewer_membership_id=first_membership,
                                     status="pending", runtime_session_ref=str(review_demand.id))
        db.add(review)
        await db.commit()
    headers = await _orch_headers(cw, mission)
    [proposal] = _proposals(await _cycle(cw, mission, headers), task.id)
    assert (proposal["action"], proposal["reason_code"]) == ("request_review", "review_infra_failure")
    assert proposal["params"]["reviewer_agent_id"] == str(second)
    decided = await _decide(cw, mission, headers, "request_review", reason="reviewer run hit INVALID_ARGUMENT",
                            task_id=task.id, proposal_id=proposal["proposal_id"], **proposal["params"])
    assert decided.status_code == 201, decided.text
    async with AsyncSessionLocal() as db:
        old = await db.get(TaskExecutionReview, review.id)
        assert old.status == "failed" and old.feedback.startswith("infra_failure:provider_error")
        new = await db.get(TaskExecutionReview, uuid.UUID(decided.json()["review_id"]))
        assert new.status == "pending" and new.reviewer_membership_id != first_membership


@pytest.mark.asyncio
async def test_reverify_mismatch_returns_instead_of_review(cw):
    mission = await _mission(cw)
    good, bad = await _baselined(mission, "good", "bad")
    reviewer = await cw.agent("rev")
    await _member(mission.project_id, reviewer, can_review=True)
    await _verified_execution(good, f"db:project_task:{good.id}")
    bad_execution = await _verified_execution(bad, f"db:project_task:{uuid.uuid4()}")
    headers = await _orch_headers(cw, mission)

    cycle = await _cycle(cw, mission, headers)
    assert {p["task_id"]: p["action"] for p in cycle["proposals"]} == {str(good.id): "reverify",
                                                                       str(bad.id): "reverify"}
    for proposal in cycle["proposals"]:
        response = await _decide(cw, mission, headers, "reverify", reason="re-run declared evidence",
                                 task_id=proposal["task_id"], proposal_id=proposal["proposal_id"],
                                 **proposal["params"])
        assert response.status_code == 201, response.text
    cycle = await _cycle(cw, mission, headers)
    by_task = {p["task_id"]: p for p in cycle["proposals"]}
    assert by_task[str(good.id)]["action"] == "request_review"
    assert by_task[str(good.id)]["params"]["reviewer_agent_id"] == str(reviewer)
    assert (by_task[str(bad.id)]["action"], by_task[str(bad.id)]["reason_code"]) == ("return", "reverify_mismatch")
    returned = await _decide(cw, mission, headers, "return", reason="evidence does not exist",
                             task_id=bad.id, proposal_id=by_task[str(bad.id)]["proposal_id"],
                             execution_id=bad_execution)
    assert returned.status_code == 201, returned.text
    async with AsyncSessionLocal() as db:
        assert (await db.get(ProjectTask, bad.id)).status == "in_progress"
        assert await db.scalar(select(func.count(TaskExecutionReview.id)).where(
            TaskExecutionReview.execution_id == bad_execution)) == 0


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True,
                          env={**os.environ, **GIT_ENV}).stdout.strip()


async def _integration_world(cw, tmp_path, bind_evidence_bridge):
    root = tmp_path / "projects"
    repo = root / f"app-{cw.tag}"
    repo.mkdir(parents=True)
    bind_evidence_bridge(root)
    _git(repo, "init", "-q", "-b", "develop")
    (repo / "README.md").write_text("base")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "base")
    _git(repo, "checkout", "-q", "-B", "feature/m08")
    (repo / "feature.txt").write_text("x")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "feature")
    sha = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "develop")
    mission = await _mission(cw)
    async with AsyncSessionLocal() as db:
        (await db.get(Project, mission.project_id)).working_directory_path = str(repo)
        await db.commit()
    [task] = await _baselined(mission, "integrated")
    reviewer = await cw.agent("rev")
    membership = await _member(mission.project_id, reviewer, can_review=True)
    execution_id = await _verified_execution(task, f"git:{sha}")
    async with AsyncSessionLocal() as db:
        db.add(TaskExecutionReview(execution_id=execution_id, reviewer_membership_id=membership, status="approved",
                                   feedback="reviewed", decided_at=datetime.now(timezone.utc)))
        (await db.get(ProjectTask, task.id)).status = "in_review"
        await db.commit()
    return mission, task, execution_id, repo


@pytest.mark.asyncio
async def test_approved_task_not_done_until_integrated(cw, tmp_path, bind_evidence_bridge):
    mission, task, execution_id, repo = await _integration_world(cw, tmp_path, bind_evidence_bridge)
    headers = await _orch_headers(cw, mission)
    [proposal] = _proposals(await _cycle(cw, mission, headers), task.id)
    assert (proposal["action"], proposal["reason_code"]) == ("integrate", "review_approved")
    first = await _decide(cw, mission, headers, "integrate", reason="review approved", task_id=task.id,
                          proposal_id=proposal["proposal_id"], execution_id=execution_id)
    assert first.status_code == 201, first.text
    assert first.json()["facts"]["integrated"] is False
    integration = await _demand(uuid.UUID(first.json()["demand_id"]))
    assert integration.target_agent_id == mission.executor  # the executor, never the reviewer
    assert integration.channel_ref == f"integrate:{task.id}" and "develop" in integration.body
    async with AsyncSessionLocal() as db:
        assert (await db.get(ProjectTask, task.id)).status == "in_review"

    _git(repo, "merge", "-q", "--no-ff", "-m", "integrate", "feature/m08")
    await _update(AgentDemand, integration.id, dispatch_status="completed")
    second = await _decide(cw, mission, headers, "integrate", reason="merged into develop", task_id=task.id,
                           execution_id=execution_id)
    assert second.status_code == 201, second.text
    assert second.json()["facts"]["integrated"] is True
    async with AsyncSessionLocal() as db:
        assert (await db.get(ProjectTask, task.id)).status == "done"
        event = (await db.execute(select(AuditEvent).where(
            AuditEvent.entity_id == task.id, AuditEvent.event_type == "task_completed"))).scalar_one()
        assert event.payload["proof"]["integrated_ref"] == "develop" and event.actor != "system"


@pytest.mark.asyncio
async def test_integration_conflict_returns_to_executor(cw, tmp_path, bind_evidence_bridge):
    mission, task, execution_id, _repo = await _integration_world(cw, tmp_path, bind_evidence_bridge)
    headers = await _orch_headers(cw, mission)
    first = await _decide(cw, mission, headers, "integrate", reason="review approved", task_id=task.id,
                          execution_id=execution_id)
    assert first.status_code == 201, first.text
    await _update(AgentDemand, uuid.UUID(first.json()["demand_id"]), dispatch_status="failed",
                  dispatch_error="The agent reported STATUS: BLOCKED",
                  dispatch_result="CONFLICT (content): Merge conflict in app/core/x.py\n"
                                  "CONFLICT (content): Merge conflict in app/api/y.py\nSTATUS: BLOCKED")
    [proposal] = _proposals(await _cycle(cw, mission, headers), task.id)
    assert (proposal["action"], proposal["reason_code"]) == ("return", "integration_conflict")
    assert proposal["reason_facts"]["conflicting_files"] == ["app/api/y.py", "app/core/x.py"]
    returned = await _decide(cw, mission, headers, "return", reason="merge conflict in 2 files",
                             task_id=task.id, proposal_id=proposal["proposal_id"], execution_id=execution_id)
    assert returned.status_code == 201, returned.text
    async with AsyncSessionLocal() as db:
        assert (await db.get(ProjectTask, task.id)).status == "in_progress"


@pytest.mark.asyncio
async def test_idle_active_mission_without_reason_alerts(cw):
    mission = await _mission(cw)
    await _baselined(mission, "idle")
    await _force(mission.project_id, state_changed_at=datetime.now(timezone.utc) - timedelta(hours=2))
    async with AsyncSessionLocal() as db:
        alerts = await mission_cycle.run_mission_cycle_watchdog(db, project_ids=[mission.project_id])
    assert {a["code"] for a in alerts} == {"MISSION_CYCLE_GAP", "MISSION_IDLE_WITHOUT_REASON"}
    async with AsyncSessionLocal() as db:
        keys = list((await db.execute(select(Notification.event_key).where(
            Notification.event_key.like(f"mission-cycle:%:{mission.project_id}:%")))).scalars())
        await db.execute(text("UPDATE company.notifications SET message = message || :t WHERE event_key = ANY(:k)"),
                         {"t": f" {cw.tag}", "k": keys})
        await db.commit()
    assert len(keys) == 2
    async with AsyncSessionLocal() as db:  # same window: no duplicate alert
        await mission_cycle.run_mission_cycle_watchdog(db, project_ids=[mission.project_id])
        assert await db.scalar(select(func.count(Notification.id)).where(Notification.event_key.in_(keys))) == 2

    headers = await _orch_headers(cw, mission)
    assert (await _decide(cw, mission, headers, "defer", reason="waiting for Marcelo's call")).status_code == 201
    async with AsyncSessionLocal() as db:
        findings = await mission_cycle.watchdog_findings(db, await db.get(ProjectMission, mission.project_id),
                                                         datetime.now(timezone.utc))
    assert {f["code"] for f in findings} == {"MISSION_CYCLE_GAP"}


# ---------------------------------------------------------------------------
# §3.7: doubts through ask_marcelo
# ---------------------------------------------------------------------------
async def _ask(cw, mission, headers, dependent, reversible, answer_by=None, **extra):
    return await _decide(
        cw, mission, headers, "ask_marcelo", reason="spec ambiguous on the export format",
        question="CSV ou XLSX na exportação?", context="A especificação cita os dois formatos.",
        options=["CSV", "XLSX"], recommendation="CSV: menor e já usado no Darckware",
        default_action="seguir com CSV", default_reversible=reversible,
        answer_by=answer_by or datetime.now(timezone.utc) + timedelta(hours=4),
        dependent_task_ids=[str(t.id) for t in dependent], **extra)


@pytest.mark.asyncio
async def test_doubt_asks_marcelo_with_options_and_default(cw):
    mission = await _active_with_routine(cw)
    [task] = await _baselined(mission, "export")
    async with AsyncSessionLocal() as db:
        assert await mission_cycle.request_mission_cycle(db, mission.project_id, "test") == "started"
        run = (await db.execute(select(AgentRoutineRun).join(AgentRoutine).where(
            AgentRoutine.mission_project_id == mission.project_id))).scalar_one()
    headers = await _orch_headers(cw, mission)
    asked = await _ask(cw, mission, headers, [task], True, cycle_id=run.id)
    assert asked.status_code == 201, asked.text
    facts = asked.json()["facts"]
    assert facts["options"] == ["CSV", "XLSX"] and facts["default_reversible"] is True
    async with AsyncSessionLocal() as db:
        question = await db.get(AgentQuestion, uuid.UUID(asked.json()["question_id"]))
        assert question.blocking and question.origin_demand_id == run.demand_id
        assert "Opções:" in question.context and "seguir com CSV" in question.context
        assert question.recommendation.startswith("CSV")
        # Deliver through the T.3 stub (no Telegram is reached).
        question.relay_agent_id = (await _mission_row(mission)).orchestrator_agent_id
        question.telegram_chat = "100000001"
        question.notify_after = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db.commit()
    since = datetime.now(timezone.utc).isoformat()
    from app.core.agent_questions import run_question_delivery_pass

    async with AsyncSessionLocal() as db:
        assert await run_question_delivery_pass(db, ids=[question.id]) == 1
    async with AsyncSessionLocal() as db:
        assert (await db.get(AgentQuestion, question.id)).telegram_sent_at is not None
    async with httpx.AsyncClient(timeout=10) as client:
        calls = (await client.get(f"{STUB}/_stub/calls", params={"integration": "host-bridge",
                                                                  "since": since})).json()["calls"]
    sends = [c for c in calls if c["path"] == "/v1/messages/send"]
    assert sends and sends[-1]["outcome"] == "stubbed" and sends[-1]["auth"] == "test"


@pytest.mark.asyncio
async def test_open_question_blocks_only_dependent_tasks(cw):
    mission = await _mission(cw)
    held, free = await _baselined(mission, "held", "free")
    headers = await _orch_headers(cw, mission)
    asked = await _ask(cw, mission, headers, [held], True)
    assert asked.status_code == 201, asked.text
    by_task = {p["task_id"]: p for p in (await _cycle(cw, mission, headers))["proposals"] if p["task_id"]}
    assert by_task[str(held.id)]["action"] == "defer"
    assert by_task[str(held.id)]["reason_code"] == f"awaiting_marcelo:{asked.json()['question_id']}"
    assert by_task[str(free.id)]["action"] == "dispatch"
    async with AsyncSessionLocal() as db:  # answered: it moves again
        question = await db.get(AgentQuestion, uuid.UUID(asked.json()["question_id"]))
        question.status, question.answer = "answered", "CSV"
        question.answered_at = datetime.now(timezone.utc)
        await db.commit()
    by_task = {p["task_id"]: p for p in (await _cycle(cw, mission, headers))["proposals"] if p["task_id"]}
    assert by_task[str(held.id)]["action"] == "dispatch"


@pytest.mark.asyncio
async def test_irreversible_default_never_applied_without_answer(cw):
    mission = await _mission(cw)
    [task] = await _baselined(mission, "irreversible")
    headers = await _orch_headers(cw, mission)
    asked = await _ask(cw, mission, headers, [task], False)
    reversible = await _ask(cw, mission, headers, [], True)
    assert asked.status_code == 201 and reversible.status_code == 201
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    async with AsyncSessionLocal() as db:
        for decision_id in (asked.json()["id"], reversible.json()["id"]):
            row = await db.get(MissionDecision, uuid.UUID(decision_id))
            row.facts = {**row.facts, "answer_by": past}
        await db.commit()
    cycle = await _cycle(cw, mission, headers)
    general = [p for p in cycle["proposals"] if p["task_id"] is None]
    by_question = {p["reason_facts"]["question_id"]: p for p in general if "question_id" in p["reason_facts"]}
    assert by_question[asked.json()["question_id"]]["action"] == "ask_marcelo"  # re-ask once
    assert by_question[reversible.json()["question_id"]]["action"] == "apply_default"
    reask = by_question[asked.json()["question_id"]]
    again = await _ask(cw, mission, headers, [task], False, reask_of=reask["params"]["reask_of"])
    assert again.status_code == 201, again.text
    async with AsyncSessionLocal() as db:
        row = await db.get(MissionDecision, uuid.UUID(again.json()["id"]))
        row.facts = {**row.facts, "answer_by": past}
        await db.commit()
    cycle = await _cycle(cw, mission, headers)
    irreversible_ids = {asked.json()["question_id"], again.json()["question_id"]}
    for proposal in cycle["proposals"]:
        if proposal["reason_facts"].get("question_id") in irreversible_ids:
            # Spec §3.7: the mission keeps waiting; a task that depends on the
            # open question is deferred (`awaiting_marcelo:<id>`). Neither applies it.
            expected = "defer" if proposal.get("task_id") else "wait"
            assert proposal["action"] == expected, proposal
    assert not [p for p in cycle["proposals"] if p["action"] == "apply_default"
                and p["reason_facts"]["question_id"] in irreversible_ids]


# ---------------------------------------------------------------------------
# §5: undo and locks
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_undo_paths(cw):
    mission = await _mission(cw)
    later, now_task = await _baselined(mission, "later", "now")
    headers = await _orch_headers(cw, mission)
    scheduled = await _decide(cw, mission, headers, "schedule", task_id=later.id,
                              scheduled_at=datetime.now(timezone.utc) + timedelta(hours=3))
    assert scheduled.status_code == 201, scheduled.text
    started = await _decide(cw, mission, headers, "dispatch", task_id=now_task.id)
    assert started.status_code == 201, started.text

    async with cw.client(headers) as client:  # the orchestrator never undoes
        forbidden = await client.post(f"/api/v1/missions/{mission.project_id}/decisions/{scheduled.json()['id']}:undo",
                                      json={"reason": "no"})
    assert forbidden.status_code == 403
    async with cw.client() as client:
        undone = await client.post(f"/api/v1/missions/{mission.project_id}/decisions/{scheduled.json()['id']}:undo",
                                   json={"reason": "wrong order"})
        assert undone.status_code == 201, undone.text
        too_late = await client.post(f"/api/v1/missions/{mission.project_id}/decisions/{started.json()['id']}:undo",
                                     json={"reason": "stop it"})
    assert too_late.status_code == 409 and _code(too_late) == "UNDO_NOT_POSSIBLE"
    assert (await _demand(uuid.UUID(scheduled.json()["demand_id"]))).status == "archived"
    rows = {str(d.id): d for d in await _decisions(mission.project_id)}
    assert rows[scheduled.json()["id"]].status == "undone"
    assert rows[scheduled.json()["id"]].undone_by_decision_id == uuid.UUID(undone.json()["id"])
    assert rows[undone.json()["id"]].action == "undo" and rows[started.json()["id"]].status == "applied"


@pytest.mark.asyncio
async def test_cycle_lock_blocks_tools_but_not_marcelo(cw):
    mission = await _mission(cw)
    first, second, third = await _baselined(mission, "one", "two", "three")
    headers = await _orch_headers(cw, mission)
    async with cw.client() as admin:
        locked = await admin.post(f"/api/v1/missions/{mission.project_id}/cycle:lock",
                                  json={"reason": "I want to look first"})
        assert locked.status_code == 201, locked.text
    cycle = await _cycle(cw, mission, headers)
    assert cycle["locked"] and not any(p["allowed"] for p in cycle["proposals"])
    assert _code(await _decide(cw, mission, headers, "dispatch", task_id=first.id)) == "CYCLE_LOCKED"
    async with cw.client(headers) as client:  # the direct tool too
        direct = await client.post(f"/api/v1/tasks/{first.id}/dispatch", json={"idempotency_key": _key(cw)})
    assert direct.status_code == 409 and _code(direct) == "CYCLE_LOCKED", direct.text
    assert (await _decide(cw, mission, cw.admin, "dispatch", reason="Marcelo dispatches",
                          task_id=first.id)).status_code == 201
    async with cw.client() as admin:
        assert (await admin.post(f"/api/v1/missions/{mission.project_id}/cycle:unlock",
                                 json={"reason": "go"})).status_code == 200
        assert (await admin.post(f"/api/v1/missions/{mission.project_id}/tasks/{second.id}:lock-cycle",
                                 json={"reason": "this one waits"})).status_code == 201
    assert _code(await _decide(cw, mission, headers, "reassign", task_id=second.id,
                               agent_id=mission.executor)) == "TASK_CYCLE_LOCKED"
    await m06b._finish_runs(first.id)
    assert (await _decide(cw, mission, headers, "dispatch", task_id=third.id)).status_code == 201
    actions = [(d.action, d.actor_type) for d in await _decisions(mission.project_id)]
    assert ("lock", "user") in actions and ("unlock", "user") in actions


# ---------------------------------------------------------------------------
# §6: several missions
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_priority_ordering_in_scheduled_pass(cw, monkeypatch):
    shared = await cw.agent("shared-exec")
    urgent, relaxed = await _mission(cw), await _mission(cw)
    tasks = {}
    for mission, priority in ((urgent, 10), (relaxed, 50)):
        await _force(mission.project_id, priority=priority)
        membership = await _member(mission.project_id, shared)
        mission.executor, mission.membership = shared, membership
        [tasks[priority]] = await _baselined(mission, f"p{priority}")
    relaxed_demand = await _queued_demand(tasks[50], shared, await m06b._project_path(relaxed.project_id),
                                          scheduled_at=DUE - timedelta(days=1))  # older
    urgent_demand = await _queued_demand(tasks[10], shared, await m06b._project_path(urgent.project_id))
    async with AsyncSessionLocal() as db:
        common = AgentDemand(from_agent="test", subject=f"m08 common {cw.tag}", body="x", origin_type="task")
        assert await mission_cycle.effective_priorities(db, [common]) == {}  # non-mission work: default 100
    await m06b._scheduled_pass(monkeypatch)
    assert (await _demand(urgent_demand)).agent_run_id is not None
    assert (await _demand(relaxed_demand)).agent_run_id is None  # the contested agent went to priority 10


@pytest.mark.asyncio
async def test_mission_dependency_cycle_and_gate(cw):
    first, second = await _mission(cw), await _mission(cw)
    async with cw.client() as admin:
        for mission in (first, second):
            await _force(mission.project_id, state="ready")
        ok = await admin.post(f"/api/v1/missions/{second.project_id}/dependencies",
                              json={"depends_on_mission_project_id": str(first.project_id), "reason": "API first"})
        assert ok.status_code == 201, ok.text
        loop = await admin.post(f"/api/v1/missions/{first.project_id}/dependencies",
                                json={"depends_on_mission_project_id": str(second.project_id), "reason": "loop"})
        assert loop.status_code == 409 and _code(loop) == "MISSION_DEPENDENCY_CYCLE"
    response = await _transition(cw, second, "active")
    assert response.status_code == 409
    assert "MISSION_DEPENDENCY_OPEN" in {u["code"] for u in response.json()["detail"]["unmet"]}
    await _force(first.project_id, state="completed")
    response = await _transition(cw, second, "active")
    codes = {u["code"] for u in response.json()["detail"].get("unmet", [])} if response.status_code == 409 else set()
    assert "MISSION_DEPENDENCY_OPEN" not in codes


# ---------------------------------------------------------------------------
# §3.6: context pack and skills
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dispatch_records_context_version(cw):
    mission = await _mission(cw)
    [task] = await _baselined(mission, "context")
    headers = await _orch_headers(cw, mission)
    assert (await _decide(cw, mission, headers, "dispatch", task_id=task.id)).status_code == 201
    [demand] = await m06b_demands(task.id)
    assert demand.mission_context_version_id is not None
    async with AsyncSessionLocal() as db:
        version = await db.get(MissionContextVersion, demand.mission_context_version_id)
        assert version.project_id == mission.project_id and version.sources["current_baseline_id"]
        event = (await db.execute(select(AuditEvent).where(
            AuditEvent.entity_id == task.id, AuditEvent.event_type == "task.dispatched"))).scalar_one()
        [entry] = [m for m in event.payload["context_manifest"] if m["source"] == "mission_context_version"]
        assert entry["id"] == str(version.id) and entry["hash"] == version.content_hash
        versions = list((await db.execute(select(MissionContextVersion.version).where(
            MissionContextVersion.project_id == mission.project_id)
            .order_by(MissionContextVersion.version))).scalars())
    assert versions == list(range(1, len(versions) + 1)) and len(versions) >= 2  # the decision made a new one


@pytest.mark.asyncio
async def test_stale_context_delivery_returned(cw):
    mission = await _mission(cw)
    [task] = await _baselined(mission, "stale context")
    reviewer = await cw.agent("rev")
    await _member(mission.project_id, reviewer, can_review=True)
    headers = await _orch_headers(cw, mission)
    assert (await _decide(cw, mission, headers, "dispatch", task_id=task.id)).status_code == 201
    [demand] = await m06b_demands(task.id)
    await _update(AgentDemand, demand.id, dispatch_status="completed")
    await _set_executions(task.id, status="verified", evidence_ref=f"db:project_task:{task.id}")
    await mission.baseline([task.id], name="replaced")  # the baseline changed after the dispatch
    [reverify] = _proposals(await _cycle(cw, mission, headers), task.id)
    assert reverify["action"] == "reverify"
    assert (await _decide(cw, mission, headers, "reverify", task_id=task.id,
                          **reverify["params"])).status_code == 201
    [proposal] = _proposals(await _cycle(cw, mission, headers), task.id)
    assert (proposal["action"], proposal["reason_code"]) == ("return", "stale_context")
    assert proposal["reason_facts"]["carried_version"] < proposal["reason_facts"]["current_version"]


@pytest.mark.asyncio
async def test_propose_skill_never_grants(cw):
    mission = await _mission(cw)
    [task] = await _baselined(mission, "skilled")
    skill = await cw.skill()
    async with AsyncSessionLocal() as db:
        db.add(TaskRequiredSkill(task_id=task.id, skill_id=skill))
        await db.commit()
    await mission.baseline([task.id], name="with skill")
    headers = await _orch_headers(cw, mission)
    proposals = _proposals(await _cycle(cw, mission, headers), task.id)
    assert [(p["action"], p["reason_code"]) for p in proposals] == [("propose_skill", "skill_gap"),
                                                                    ("defer", "skill_gap")]
    async with cw.client(headers) as client:
        response = await client.post(f"/api/v1/missions/{mission.project_id}/skill-proposals", json={
            "kind": "grant_to_agent", "task_id": str(task.id), "skill_id": str(skill),
            "agent_id": str(mission.executor), "reason": "executor lacks the skill", "idempotency_key": _key(cw)})
    assert response.status_code == 201, response.text
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(func.count(AgentSkill.id)).where(AgentSkill.skill_id == skill)) == 0
        proposal = await db.get(MissionSkillProposal, uuid.UUID(response.json()["id"]))
        assert proposal.status == "proposed"
        if proposal.demand_id:
            assert (await db.get(AgentDemand, proposal.demand_id)).origin_type == "incubation"
    [row] = await _decisions(mission.project_id)
    assert (row.action, row.status) == ("defer", "deferred") and row.reason.startswith("skill_gap")


# ---------------------------------------------------------------------------
# §3.5: planning
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cycle_conducts_planning_but_never_approves_baseline(cw):
    mission = await _mission(cw)
    await _force(mission.project_id, state="planning", planning_stage="draft_plan")
    cycle = await _cycle(cw, mission, await _orch_headers(cw, mission))
    actions = {p["action"] for p in cycle["proposals"]}
    assert actions <= {"wait", "advance_planning", "ask_marcelo"}
    assert cycle["board"] == []
    headers = await _orch_headers(cw, mission)
    assert (await _decide(cw, mission, headers, "approve_baseline")).status_code == 422
