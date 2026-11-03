"""M0.2b: submit_project_plan, the governed baseline approval and add_task_dependency
(docs/architecture/MCP_MISSION_TOOLS_SPEC.md §5.3, §5.4, §7, §9.4).

A plan submission only proposes; Marcelo (admin JWT) decides on the governed
route, which recomputes the plan hash and, on approval, creates the next
baseline in one transaction without dispatching anything. Runs only against
the isolated test database; every test removes what it created. The
migration test round-trips this revision only.
"""
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy import func, select, text

from app.core import command_receipts
from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.models.demand import AgentDemand
from app.db.models.governance import ApprovalDecisionRecord, ApprovalRequest, AuditEvent
from app.db.models.mission import MissionPlanSubmission, ProjectMission
from app.db.models.project import ChangeRequest, PlanBaseline, PlanBaselineItem, ProjectPlan
from app.db.models.task import ProjectTask, TaskDependency
from app.main import app
from app.mcp import factory_server
from app.mcp.factory_server import FactoryError
from app.tests.test_mission_base import (  # noqa: F401  (_clean_stale_mission_fixtures is an autouse fixture)
    World,
    _assign,
    _brief,
    _clean_stale_mission_fixtures,
    _criterion,
    _force,
    _member,
    _row_version,
    _task,
    _transition,
)

REVISION = "e8c4b2d9a7f1"
DOWN_REVISION = "c5a8e2f71d04"
BACKEND_DIR = Path(__file__).resolve().parents[2]


async def _remove_plan_approvals(project_ids: list[str], task_ids: list[uuid.UUID]) -> None:
    """Governed requests, their evaluations and audit, then the plans (and so
    the baselines, which hold their tasks RESTRICT)."""
    if not project_ids:
        return
    projects = ",".join(f"'{p}'::uuid" for p in project_ids)
    plans = f"SELECT id FROM company.project_plans WHERE project_id IN ({projects})"
    requests = f"SELECT id FROM company.approval_requests WHERE target_type = 'project_plan' AND target_id IN ({plans})"
    async with AsyncSessionLocal() as db:
        for statement in (
            f"DELETE FROM company.notifications WHERE event_key LIKE ANY (SELECT 'approval:%' || id || '%' FROM ({requests}) r)",
            f"DELETE FROM company.audit_events WHERE entity_id IN ({requests})",
            f"CREATE TEMP TABLE _evals ON COMMIT DROP AS SELECT policy_evaluation_id AS id FROM company.approval_requests "
            f"WHERE id IN ({requests})",
            f"DELETE FROM company.approval_requests WHERE id IN ({requests})",
            "DELETE FROM company.policy_evaluations WHERE id IN (SELECT id FROM _evals)",
            f"UPDATE company.project_missions SET current_baseline_id = NULL WHERE project_id IN ({projects})",
            f"DELETE FROM company.project_plans WHERE project_id IN ({projects})",
        ):
            await db.execute(text(statement))
        if task_ids:
            await db.execute(text("DELETE FROM company.audit_events WHERE entity_id = ANY(:ids)"),
                             {"ids": list(task_ids)})
        await db.commit()


@pytest_asyncio.fixture
async def world(admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "MISSION_TOOLS_ENABLED", True)
    command_receipts.agent_write_limiter.reset()
    w = World(admin_headers)
    w.mission_ids = []
    w.task_ids = []
    await w.setup()
    yield w
    await _remove_plan_approvals(w.mission_ids, w.task_ids)
    async with AsyncSessionLocal() as db:
        if w.agent_ids:
            await db.execute(text("DELETE FROM company.agent_command_receipts WHERE principal_id = ANY(:ids)"),
                             {"ids": list(w.agent_ids)})
        await db.execute(text("DELETE FROM company.agent_command_receipts WHERE target_type = 'approval_request' "
                              "AND target_id NOT IN (SELECT id FROM company.approval_requests)"))
        await db.commit()
    await w.cleanup()
    command_receipts.agent_write_limiter.reset()


@pytest.fixture
def mcp_as(monkeypatch):
    """Route the MCP's HTTP client to the in-process app, as a given agt_
    (same as test_mission_mcp's fixture)."""
    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs.pop("timeout", None)
        return real_client(transport=ASGITransport(app=app), timeout=30.0)

    monkeypatch.setattr(factory_server, "BASE_URL", "http://test")
    monkeypatch.setattr(factory_server.httpx, "AsyncClient", factory)

    def use(token: str) -> None:
        monkeypatch.setenv("FORGEHUB_AGENT_TOKEN", token)
    return use


def _token(headers: dict[str, str]) -> str:
    return headers["Authorization"][len("Bearer "):]


def _key() -> str:
    return f"mission-test-{uuid.uuid4()}"


def _code(response) -> str:
    return response.json()["detail"]["code"]


class Plan:
    """A mission at planning/baseline (P1-P7 done, M0.0b) with one task that
    passes every automatic check: executor through a member, an independent
    reviewer, a criterion, environment and prerequisites, brief, deadline and
    budget. The orchestrator submits with mission.plan.submit."""

    async def build(self, world: World) -> "Plan":
        self.world = world
        mission = await world.create_mission(brief_artifact_id=str(await _brief(world)))
        self.project_id = mission["project_id"]
        world.mission_ids.append(self.project_id)
        self.pid = uuid.UUID(self.project_id)
        self.orchestrator = uuid.UUID(mission["orchestrator_agent_id"])
        async with world.client() as client:
            patched = await client.patch(f"/api/v1/missions/{self.project_id}", json={
                "expected_row_version": await _row_version(self.project_id), "risk_level": "medium",
                "required_review_layers": ["backend"],
                "deadline_at": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
                "budget_limit": "50"})
        assert patched.status_code == 200, patched.text
        await _force(self.project_id, state="planning", planning_stage="draft_plan")
        self.executor = await world.agent("exec")
        self.executor_membership = await _member(self.project_id, self.executor)
        self.reviewer = await world.agent("rev")
        await _member(self.project_id, self.reviewer, role="reviewer", can_review=True)
        self.task = await self.add_task("first")
        await _criterion(self.project_id, self.reviewer, task_ids=[self.task.id])
        self.orch_h = await world.agent_token(
            self.orchestrator,
            ["mission.plan.submit", "mission.orchestrate", "planning.execution.manage", "governance.approval.decide"],
            self.pid,
        )
        async with world.client(self.orch_h) as client:
            registered = await client.post(self.url("/plans"), json={"name": "plan v1", "scope_summary": "scope"})
        assert registered.status_code == 201, registered.text
        self.plan_id = registered.json()["project_plan_id"]
        await _force(self.project_id, planning_stage="baseline")
        return self

    async def add_task(self, title: str, **fields) -> ProjectTask:
        task = await _task(self.project_id, title=title, target_environment="test", environment_prerequisites=[],
                           **fields)
        self.world.task_ids.append(task.id)
        await _assign(task.id, self.executor, self.executor_membership)
        return task

    def url(self, suffix: str) -> str:
        return f"/api/v1/missions/{self.project_id}{suffix}"

    async def submit(self, headers=None, **body):
        body = {"task_ids": [str(self.task.id)], "idempotency_key": _key(), **body}
        async with self.world.client(headers or self.orch_h) as client:
            return await client.post(self.url("/plans:submit"), json=body)

    async def decide(self, request_id, decision="approved", headers=None, key=None):
        async with self.world.client(headers) as client:
            return await client.post(f"/api/v1/governed/approval-requests/{request_id}:decide", json={
                "decision": decision, "comments": "ok", "idempotency_key": key or _key()})

    async def mission(self) -> ProjectMission:
        async with AsyncSessionLocal() as db:
            return await db.get(ProjectMission, self.pid)


async def _request(request_id) -> ApprovalRequest:
    async with AsyncSessionLocal() as db:
        return await db.get(ApprovalRequest, uuid.UUID(str(request_id)))


# ---------------------------------------------------------------------------
# submit_project_plan (§5.3)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_submit_plan_never_approves(world, mcp_as):
    plan = await Plan().build(world)
    mcp_as(_token(plan.orch_h))

    # Approver fields don't exist: any of them is a 422, before anything is written.
    for extra in ({"approved": True}, {"approver_token": "agt_x"}, {"approved_by": "Marcelo"}):
        assert (await plan.submit(**extra)).status_code == 422
    assert (await plan.submit(plan={"name": "plan v1", "approved": True})).status_code == 422
    with pytest.raises(FactoryError, match="422"):
        await factory_server.submit_project_plan(plan.project_id, [str(plan.task.id)], _key(),
                                                 plan={"name": "plan v1", "approver_name": "Marcelo"})

    key = _key()
    submitted = await factory_server.submit_project_plan(plan.project_id, [str(plan.task.id)], key)
    assert submitted["status"] == "pending_approval" and submitted["replayed"] is False
    assert submitted["plan_id"] == plan.plan_id
    checks = {c["key"]: c for c in submitted["checks"]}
    assert all(c["status"] == "passed" for c in checks.values() if c["status"] != "not_evaluated")
    for key_name in ("critical_path_vs_deadline", "document_owners", "risk_list", "budget_sum"):
        assert checks[key_name]["status"] == "not_evaluated" and checks[key_name]["passed"] is None

    # Pending, no baseline, nothing moved.
    request = await _request(submitted["approval_request_id"])
    assert (request.status, request.target_type, request.requested_by_type) == ("pending", "project_plan", "agent")
    mission = await plan.mission()
    assert mission.current_baseline_id is None and mission.state == "planning"
    async with AsyncSessionLocal() as db:
        assert (await db.get(ProjectPlan, uuid.UUID(plan.plan_id))).status == "draft"

    # Replay returns the receipt; the same key with another body is refused.
    again = await factory_server.submit_project_plan(plan.project_id, [str(plan.task.id)], key)
    assert again["replayed"] is True and again["approval_request_id"] == submitted["approval_request_id"]
    other = await plan.add_task("second")
    with pytest.raises(FactoryError, match="IDEMPOTENCY_KEY_REUSED"):
        await factory_server.submit_project_plan(plan.project_id, [str(other.id)], key)
    with pytest.raises(FactoryError, match="PLAN_ALREADY_PENDING"):
        await factory_server.submit_project_plan(plan.project_id, [str(plan.task.id)], _key())

    # An agent never decides a plan, even with governance.approval.decide; nor a non-admin user.
    by_agent = await plan.decide(submitted["approval_request_id"], headers=plan.orch_h)
    assert by_agent.status_code == 403 and _code(by_agent) == "PLAN_APPROVAL_HUMAN_ONLY"
    assert (await _request(submitted["approval_request_id"])).status == "pending"
    async with AsyncSessionLocal() as db:
        events = set((await db.execute(select(AuditEvent.event_type).where(
            AuditEvent.entity_type == "mission", AuditEvent.entity_id == plan.pid))).scalars())
    assert "plan_submitted" in events


@pytest.mark.asyncio
async def test_submit_refusals_and_failed_checks(world):
    plan = await Plan().build(world)
    await _force(plan.project_id, planning_stage="decisions")
    assert _code(await plan.submit()) == "PLANNING_PIPELINE_UNFINISHED"
    await _force(plan.project_id, planning_stage="baseline")
    # The reviewed version is submitted as it is.
    differs = await plan.submit(plan={"name": "renamed"})
    assert differs.status_code == 409 and _code(differs) == "PLAN_DIFFERS_FROM_REVIEWED_VERSION"
    assert (await plan.submit(plan={"name": "plan v1", "scope_summary": "scope"})).status_code == 201

    # A second mission whose task has no executor and no environment fails the checks, listing them.
    other = await Plan().build(world)
    async with AsyncSessionLocal() as db:
        await db.execute(text("UPDATE company.task_assignments SET status = 'released' WHERE task_id = :t"),
                         {"t": str(other.task.id)})
        await db.execute(text("UPDATE company.project_tasks SET environment_prerequisites = NULL WHERE id = :t"),
                         {"t": str(other.task.id)})
        await db.commit()
    stranger = await _task(plan.project_id, title="not mine")
    world.task_ids.append(stranger.id)
    failed = await other.submit(task_ids=[str(other.task.id), str(stranger.id)])
    assert failed.status_code == 409 and _code(failed) == "PLAN_CHECKS_FAILED"
    statuses = {c["key"]: c["status"] for c in failed.json()["detail"]["checks"]}
    assert statuses["executor_assigned"] == statuses["environment"] == statuses["tasks_in_scope"] == "failed"
    assert statuses["dependencies_acyclic"] == "passed"
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(MissionPlanSubmission).where(
            MissionPlanSubmission.mission_project_id == other.pid)) == 0

    # Outside planning/baseline or an approved change request: refused.
    await _force(other.project_id, state="draft", planning_stage=None)
    assert _code(await other.submit()) == "MISSION_NOT_DRAFT_OR_CR"
    # A member without mission.plan.submit cannot submit.
    no_delegation = await world.agent_token(other.reviewer, ["mission.plan.review"], other.pid)
    await _force(other.project_id, state="planning", planning_stage="baseline")
    assert _code(await other.submit(headers=no_delegation)) == "DELEGATION_REQUIRED"


@pytest.mark.asyncio
async def test_plan_hash_mismatch_on_decide(world):
    plan = await Plan().build(world)
    submitted = await plan.submit()
    assert submitted.status_code == 201, submitted.text
    request_id = submitted.json()["approval_request_id"]
    async with world.client() as client:
        edited = await client.patch(f"/api/v1/tasks/{plan.task.id}", json={"title": "edited after submission"})
    assert edited.status_code == 200
    refused = await plan.decide(request_id)
    assert refused.status_code == 409 and _code(refused) == "PLAN_CHANGED_SINCE_SUBMISSION"
    # The request is left stale (committed), so a new submission is possible.
    assert (await _request(request_id)).status == "stale"
    assert (await plan.mission()).current_baseline_id is None
    resubmitted = await plan.submit()
    assert resubmitted.status_code == 201, resubmitted.text
    approved = await plan.decide(resubmitted.json()["approval_request_id"])
    assert approved.status_code == 200, approved.text


@pytest.mark.asyncio
async def test_self_approval_refused(world):
    plan = await Plan().build(world)
    by_admin = await plan.submit(headers=world.admin)
    assert by_admin.status_code == 201, by_admin.text
    refused = await plan.decide(by_admin.json()["approval_request_id"])
    assert refused.status_code == 403 and _code(refused) == "SEPARATION_OF_DUTIES"


@pytest.mark.asyncio
async def test_rejected_plan_creates_no_baseline(world):
    plan = await Plan().build(world)
    submitted = (await plan.submit()).json()
    rejected = await plan.decide(submitted["approval_request_id"], decision="rejected")
    assert rejected.status_code == 200 and rejected.json()["decision"] == "rejected"
    assert (await plan.mission()).current_baseline_id is None
    async with AsyncSessionLocal() as db:
        assert (await db.get(ProjectPlan, uuid.UUID(plan.plan_id))).status == "draft"


# ---------------------------------------------------------------------------
# Approval -> baseline; change request -> next baseline (§7 items 3, 5, 6)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_approval_creates_baseline_and_cr_supersedes_it(world):
    plan = await Plan().build(world)
    submitted = (await plan.submit()).json()
    key = _key()
    approved = await plan.decide(submitted["approval_request_id"], key=key)
    assert approved.status_code == 200, approved.text
    record_id = approved.json()["id"]
    # Replaying the decision returns the same record; nothing is decided twice.
    replay = await plan.decide(submitted["approval_request_id"], key=key)
    assert replay.status_code == 200 and replay.json()["id"] == record_id

    mission = await plan.mission()
    async with AsyncSessionLocal() as db:
        first = await db.get(PlanBaseline, mission.current_baseline_id)
        items = set((await db.execute(select(PlanBaselineItem.task_id).where(
            PlanBaselineItem.baseline_id == first.id))).scalars())
        assert items == {plan.task.id}
        assert (await db.get(ProjectPlan, uuid.UUID(plan.plan_id))).status == "baselined"
        submission = await db.get(MissionPlanSubmission, uuid.UUID(submitted["approval_request_id"]))
        assert submission.baseline_id == first.id
        assert await db.scalar(select(func.count()).select_from(ApprovalDecisionRecord).where(
            ApprovalDecisionRecord.approval_request_id == uuid.UUID(submitted["approval_request_id"]))) == 1
        # Approval dispatches nothing and does not move the mission.
        assert await db.scalar(select(func.count()).select_from(AgentDemand).where(
            AgentDemand.origin_id == plan.task.id)) == 0
    assert mission.state == "planning" and mission.planning_stage == "baseline"
    ready = await _transition(world, plan.project_id, "ready")
    assert ready.status_code == 200, ready.text

    # After the baseline only a change request changes the plan.
    assert _code(await plan.submit()) == "CHANGE_REQUEST_REQUIRED"
    async with AsyncSessionLocal() as db:
        change_request = ChangeRequest(project_id=plan.pid, plan_baseline_id=first.id, title="add a task",
                                       status="pending")
        db.add(change_request)
        await db.commit()
        cr_id = change_request.id
    new_task = await plan.add_task("from the change request", change_request_id=cr_id)
    async with AsyncSessionLocal() as db:
        await db.execute(text("INSERT INTO company.mission_criterion_tasks (id, criterion_id, task_id, created_at, "
                              "updated_at) SELECT gen_random_uuid(), criterion_id, :n, now(), now() "
                              "FROM company.mission_criterion_tasks WHERE task_id = :t"),
                         {"n": str(new_task.id), "t": str(plan.task.id)})
        await db.commit()
    body = {"change_request_id": str(cr_id), "plan": {"name": "plan v2"},
            "task_ids": [str(plan.task.id), str(new_task.id)]}
    assert _code(await plan.submit(**body)) == "CHANGE_REQUEST_NOT_APPROVED"
    async with AsyncSessionLocal() as db:
        (await db.get(ChangeRequest, cr_id)).status = "approved"
        await db.commit()
    assert _code(await plan.submit(change_request_id=str(cr_id))) == "PLAN_REQUIRED"
    cr_plan = await plan.submit(**body)
    assert cr_plan.status_code == 201, cr_plan.text
    checks = {c["key"]: c["status"] for c in cr_plan.json()["checks"]}
    assert checks["change_request_review_pipeline"] == "not_evaluated"
    approved2 = await plan.decide(cr_plan.json()["approval_request_id"])
    assert approved2.status_code == 200, approved2.text

    mission = await plan.mission()
    async with AsyncSessionLocal() as db:
        second = await db.get(PlanBaseline, mission.current_baseline_id)
        assert second.id != first.id
        assert (await db.get(PlanBaseline, first.id)).superseded_at is not None
        assert set((await db.execute(select(PlanBaselineItem.task_id).where(
            PlanBaselineItem.baseline_id == second.id))).scalars()) == {plan.task.id, new_task.id}
        assert (await db.get(ChangeRequest, cr_id)).status == "applied"
        cr_plan_row = await db.get(ProjectPlan, uuid.UUID(cr_plan.json()["plan_id"]))
        assert (cr_plan_row.status, cr_plan_row.change_request_id) == ("baselined", cr_id)
        assert (await db.get(ProjectPlan, uuid.UUID(plan.plan_id))).status == "superseded"
        events = set((await db.execute(select(AuditEvent.event_type).where(
            AuditEvent.entity_type == "mission", AuditEvent.entity_id == plan.pid))).scalars())
    assert {"plan_submitted", "mission_plan_approved"} <= events
    assert mission.state == "ready"


# ---------------------------------------------------------------------------
# :withdraw (D-M0-4)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_withdraw(world, mcp_as):
    plan = await Plan().build(world)
    submitted = (await plan.submit()).json()
    request_id = submitted["approval_request_id"]
    stranger = await world.agent("stranger")
    await _member(plan.project_id, stranger, role="reviewer")
    stranger_h = await world.agent_token(stranger, ["mission.plan.submit"], plan.pid)
    withdraw = plan.url(f"/plans/{plan.plan_id}:withdraw")
    async with world.client(stranger_h) as client:
        refused = await client.post(withdraw, json={"reason": "not mine"})
    assert refused.status_code == 403 and _code(refused) == "NOT_PLAN_SUBMITTER"

    mcp_as(_token(plan.orch_h))
    done = await factory_server.withdraw_project_plan(plan.project_id, plan.plan_id, "the plan needs another pass")
    assert done["status"] == "withdrawn" and done["plan_status"] == "draft"
    again = await factory_server.withdraw_project_plan(plan.project_id, plan.plan_id, "again")
    assert again["status"] == "withdrawn" and again["withdrawn_reason"] == "the plan needs another pass"
    assert (await _request(request_id)).status == "withdrawn"
    decided = await plan.decide(request_id)
    assert decided.status_code == 409 and _code(decided) == "APPROVAL_NOT_PENDING"
    # Nothing was deleted and a new submission is possible.
    async with AsyncSessionLocal() as db:
        assert await db.get(MissionPlanSubmission, uuid.UUID(request_id)) is not None
        events = set((await db.execute(select(AuditEvent.event_type).where(
            AuditEvent.entity_type == "mission", AuditEvent.entity_id == plan.pid))).scalars())
    assert "plan_submission_withdrawn" in events
    assert (await plan.submit()).status_code == 201


# ---------------------------------------------------------------------------
# add_task_dependency (§5.4)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_add_dependency_rules_and_task_in_baseline(world, mcp_as):
    plan = await Plan().build(world)
    second = await plan.add_task("second")
    third = await plan.add_task("third")
    mcp_as(_token(plan.orch_h))

    key = _key()
    added = await factory_server.add_task_dependency(str(second.id), str(plan.task.id), key)
    assert added["replayed"] is False and added["baseline_impact"] == "none"
    replay = await factory_server.add_task_dependency(str(second.id), str(plan.task.id), key)
    assert replay["replayed"] is True and replay["id"] == added["id"]
    with pytest.raises(FactoryError, match="DEPENDENCY_ALREADY_EXISTS"):
        await factory_server.add_task_dependency(str(second.id), str(plan.task.id), _key())
    with pytest.raises(FactoryError, match="409"):  # cycle
        await factory_server.add_task_dependency(str(plan.task.id), str(second.id), _key())
    with pytest.raises(FactoryError, match="DEPENDENCY_TYPE_NOT_SUPPORTED"):
        await factory_server.add_task_dependency(str(third.id), str(second.id), _key(), "start_to_start")
    # A task of another project is invisible from a mission task (404, no leak).
    other = await Plan().build(world)
    with pytest.raises(FactoryError, match="TASK_NOT_FOUND"):
        await factory_server.add_task_dependency(str(third.id), str(other.task.id), _key())
    # An agent must send a key; without the delegation it is refused.
    async with world.client(plan.orch_h) as client:
        keyless = await client.post(f"/api/v1/tasks/{third.id}/dependencies", json={
            "task_id": str(third.id), "depends_on_task_id": str(second.id)})
    assert keyless.status_code == 422 and _code(keyless) == "IDEMPOTENCY_KEY_REQUIRED"
    mcp_as(_token(await world.agent_token(plan.reviewer, ["mission.plan.review"], plan.pid)))
    with pytest.raises(FactoryError, match="DELEGATION_REQUIRED"):
        await factory_server.add_task_dependency(str(third.id), str(second.id), _key())

    # Baseline the first two tasks: their dependencies are frozen (TASK_IN_BASELINE).
    submitted = (await plan.submit(task_ids=[str(plan.task.id), str(second.id)])).json()
    assert (await plan.decide(submitted["approval_request_id"])).status_code == 200
    mcp_as(_token(plan.orch_h))
    with pytest.raises(FactoryError, match="TASK_IN_BASELINE"):
        await factory_server.add_task_dependency(str(plan.task.id), str(third.id), _key())
    async with world.client() as client:
        removed = await client.delete(f"/api/v1/tasks/{second.id}/dependencies/{added['id']}")
    assert removed.status_code == 409 and _code(removed) == "TASK_IN_BASELINE"
    # A task left out of the baseline still takes one, flagged as needing a change request.
    flagged = await factory_server.add_task_dependency(str(third.id), str(second.id), _key())
    assert flagged["baseline_impact"] == "requires_change_request"
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(TaskDependency).where(
            TaskDependency.task_id == second.id)) == 1
        events = list((await db.execute(select(AuditEvent).where(
            AuditEvent.entity_id == second.id, AuditEvent.event_type == "task_dependency_added"))).scalars())
    assert len(events) == 1 and events[0].actor != "system"


@pytest.mark.asyncio
async def test_tools_disabled_flag(world, monkeypatch):
    plan = await Plan().build(world)
    second = await plan.add_task("second")
    monkeypatch.setattr(settings, "MISSION_TOOLS_ENABLED", False)
    submitted = await plan.submit()
    assert submitted.status_code == 503 and _code(submitted) == "MISSION_TOOLS_DISABLED"
    body = {"task_id": str(second.id), "depends_on_task_id": str(plan.task.id), "idempotency_key": _key()}
    async with world.client(plan.orch_h) as client:
        by_agent = await client.post(f"/api/v1/tasks/{second.id}/dependencies", json=body)
    assert by_agent.status_code == 503
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(MissionPlanSubmission).where(
            MissionPlanSubmission.mission_project_id == plan.pid)) == 0
        assert await db.scalar(select(func.count()).select_from(TaskDependency).where(
            TaskDependency.task_id == second.id)) == 0
    # A person's dependency edit is not behind the switch.
    async with world.client() as client:
        by_person = await client.post(f"/api/v1/tasks/{second.id}/dependencies", json=body)
    assert by_person.status_code == 201, by_person.text


# ---------------------------------------------------------------------------
# Migration (only this revision moves)
# ---------------------------------------------------------------------------
def _alembic(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=BACKEND_DIR, capture_output=True, text=True,
        env={**os.environ, "ENVIRONMENT": "test"}, timeout=180,
    )


@pytest.mark.asyncio
async def test_migration_roundtrip_only_this_revision(world):
    """Downgrade this revision only and back, with a duplicate dependency and
    a required_skill_ids entry written in between: the upgrade collapses the
    duplicate (audited) and folds the column into task_required_skills.
    Skipped unless the database is exactly at this revision."""
    current = _alembic("current").stdout.split()
    if [t for t in current if len(t) == 12 and t.isalnum()] != [REVISION]:
        pytest.skip(f"database at {current}, not only {REVISION}")
    plan = await Plan().build(world)
    second = await plan.add_task("second")
    skill = await world.skill()

    # A pending project_plan request makes the downgrade refuse.
    submitted = (await plan.submit()).json()
    refused = _alembic("downgrade", DOWN_REVISION)
    assert refused.returncode != 0 and "Refusing to downgrade" in refused.stderr
    assert REVISION in _alembic("current").stdout
    await _remove_plan_approvals([plan.project_id], [])
    assert await _request(submitted["approval_request_id"]) is None

    async with AsyncSessionLocal() as db:
        db.add(TaskDependency(task_id=second.id, depends_on_task_id=plan.task.id))
        await db.commit()
    down = _alembic("downgrade", DOWN_REVISION)
    assert down.returncode == 0, down.stderr
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "INSERT INTO company.task_dependencies (id, task_id, depends_on_task_id, dependency_type, "
                "created_at, updated_at) VALUES (gen_random_uuid(), :t, :d, 'finish_to_start', now(), now())"),
                {"t": str(second.id), "d": str(plan.task.id)})
            await db.execute(text("UPDATE company.project_tasks SET required_skill_ids = ARRAY[CAST(:s AS uuid), "
                                  "CAST(:g AS uuid)] WHERE id = :t"),
                             {"s": str(skill), "g": str(uuid.uuid4()), "t": str(second.id)})
            await db.commit()
    finally:
        up = _alembic("upgrade", REVISION)
        assert up.returncode == 0, up.stderr
    assert REVISION in _alembic("current").stdout
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(TaskDependency).where(
            TaskDependency.task_id == second.id)) == 1
        audited = set((await db.execute(select(AuditEvent.event_type).where(
            AuditEvent.entity_id == second.id))).scalars())
        rows = (await db.execute(text("SELECT skill_id, is_mandatory FROM company.task_required_skills "
                                      "WHERE task_id = :t"), {"t": str(second.id)})).all()
    assert {"task_dependency_duplicate_removed", "task_required_skill_unknown_dropped"} <= audited
    assert rows == [(skill, True)]
