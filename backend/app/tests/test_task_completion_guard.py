"""M0.6a: global, prospective completion guard (MCP_MISSION_TOOLS_SPEC.md §4.1,
§9.2 and "Integration before `done` for mission tasks").

File and git evidence is checked by the real host-bridge evidence router
(host-bridge/evidence_probe.py) against real temporary git repositories: the
backend's bridge client is bound to that router in-process, so nothing but the
transport is replaced. Every other piece -- routes, guard, database -- is real.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, or_, select

from app.core import evidence_bridge
from app.core.deps import ActorPrincipal
from app.core.security import create_access_token, hash_password
from app.core.task_evidence import verify_evidence
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent, AgentServiceCredential
from app.db.models.backlog import PlanningItem
from app.db.models.demand import AgentDemand
from app.db.models.notification import Notification
from app.db.models.governance import (
    ApprovalDecisionRecord,
    ApprovalRequest,
    AuditEvent,
    Policy,
    PolicyBinding,
    PolicyEvaluation,
    PolicyVersion,
)
from app.db.models.orchestration import (
    AgentRuntimeProfile,
    ProjectAgentMembership,
    ProjectLoopPolicy,
    TaskExecutionReview,
)
from app.db.models.product import Product, ProductVersion
from app.db.models.project import Project
from app.db.models.task import ProjectTask, TaskAssignment, TaskDependency, TaskExecution
from app.db.models.user import User
from app.main import app

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.test",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.test"}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True,
                          env={**os.environ, **GIT_ENV}).stdout.strip()


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "develop")
    (repo / "README.md").write_text("base")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "base")


def _commit(repo: Path, name: str, branch: str | None = None) -> str:
    if branch:
        _git(repo, "checkout", "-q", "-B", branch)
    (repo / name).write_text(uuid.uuid4().hex)
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", name)
    sha = _git(repo, "rev-parse", "HEAD")
    if branch:
        _git(repo, "checkout", "-q", "develop")
    return sha


@pytest.fixture
def projects_root(tmp_path, bind_evidence_bridge):
    """The backend's bridge client bound to the real evidence router, which
    only accepts roots under `projects_root`."""
    root = tmp_path / "projects"
    root.mkdir()
    bind_evidence_bridge(root)
    return root


@pytest_asyncio.fixture
async def world(projects_root):
    suffix = uuid.uuid4().hex[:8]
    repo = projects_root / f"app-{suffix}"
    _init_repo(repo)
    other_repo = projects_root / f"other-{suffix}"
    _init_repo(other_repo)
    ids: dict = {"suffix": suffix, "repo": repo, "other_repo": other_repo, "tasks": [], "users": []}
    async with AsyncSessionLocal() as db:
        product = Product(name=f"Guard Product {suffix}")
        db.add(product)
        await db.flush()
        version = ProductVersion(product_id=product.id, version="0.1.0")
        db.add(version)
        await db.flush()
        project = Project(name=f"Guard Project {suffix}", product_version_id=version.id,
                          working_directory_path=str(repo))
        other = Project(name=f"Guard Other {suffix}", product_version_id=version.id,
                        working_directory_path=str(other_repo))
        mission = Project(name=f"Guard Mission {suffix}", product_version_id=version.id,
                          working_directory_path=str(repo), project_type="mission")
        db.add_all([project, other, mission])
        await db.flush()
        item = PlanningItem(title="Guard item", item_type="feature", project_id=project.id)
        mission_item = PlanningItem(title="Guard mission item", item_type="feature", project_id=mission.id)
        db.add_all([item, mission_item])
        executor = Agent(name=f"guard-exec-{suffix}", agent_type="executor", runtime_type="codex")
        reviewer = Agent(name=f"guard-rev-{suffix}", agent_type="executor", runtime_type="claude")
        outsider = Agent(name=f"guard-out-{suffix}", agent_type="executor", runtime_type="agy")
        db.add_all([executor, reviewer, outsider])
        await db.flush()
        memberships = {}
        for key, proj, agent, can_review in (
            ("exec", project, executor, True), ("rev", project, reviewer, True),
            ("noreview", project, outsider, False), ("other_rev", other, reviewer, True),
            ("m_exec", mission, executor, True), ("m_rev", mission, reviewer, True),
        ):
            membership = ProjectAgentMembership(project_id=proj.id, agent_id=agent.id,
                                                role="developer", can_review=can_review)
            db.add(membership)
            await db.flush()
            memberships[key] = membership.id
        admin = User(username=f"guard-admin-{suffix}", hashed_password=hash_password(uuid.uuid4().hex),
                     is_admin=True)
        operator = User(username=f"guard-op-{suffix}", hashed_password=hash_password(uuid.uuid4().hex),
                        is_admin=False)
        db.add_all([admin, operator])
        tokens = {}
        for key, agent in (("exec", executor), ("rev", reviewer)):
            token = f"agt_{secrets.token_urlsafe(24)}"
            db.add(AgentServiceCredential(agent_id=agent.id, label="guard test",
                                          token_hash=hashlib.sha256(token.encode()).hexdigest()))
            tokens[key] = token
        await db.commit()
        ids.update(
            product=product.id, version=version.id, project=project.id, other=other.id, mission=mission.id,
            item=item.id, mission_item=mission_item.id, executor=executor.id, reviewer=reviewer.id,
            outsider=outsider.id, memberships=memberships, admin=admin.username, operator=operator.username,
            admin_id=admin.id, tokens=tokens, reviewer_name=reviewer.name,
        )
        ids["users"] = [admin.id, operator.id]

    yield ids

    async with AsyncSessionLocal() as db:
        task_ids = list((await db.execute(select(ProjectTask.id).where(
            ProjectTask.planning_item_id.in_([ids["item"], ids["mission_item"]])
        ))).scalars())
        execution_ids = list((await db.execute(
            select(TaskExecution.id).where(TaskExecution.task_id.in_(task_ids))
        )).scalars()) if task_ids else []
        review_ids = list((await db.execute(
            select(TaskExecutionReview.id).where(TaskExecutionReview.execution_id.in_(execution_ids))
        )).scalars()) if execution_ids else []
        request_ids = list((await db.execute(
            select(ApprovalRequest.id).where(ApprovalRequest.target_id.in_(task_ids))
        )).scalars()) if task_ids else []
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_(task_ids + review_ids + request_ids)))
        if request_ids:
            await db.execute(delete(ApprovalDecisionRecord).where(
                ApprovalDecisionRecord.approval_request_id.in_(request_ids)))
            await db.execute(delete(ApprovalRequest).where(ApprovalRequest.id.in_(request_ids)))
        if task_ids:
            await db.execute(delete(PolicyEvaluation).where(PolicyEvaluation.target_id.in_(task_ids)))
        if request_ids:
            await db.execute(delete(Notification).where(
                Notification.event_key.in_([f"approval:requested:{rid}" for rid in request_ids])))
        if ids.get("policy"):
            await db.execute(delete(PolicyBinding).where(PolicyBinding.policy_version_id == ids["policy_version"]))
            await db.execute(delete(PolicyVersion).where(PolicyVersion.id == ids["policy_version"]))
            await db.execute(delete(Policy).where(Policy.id == ids["policy"]))
        if review_ids:
            await db.execute(delete(TaskExecutionReview).where(TaskExecutionReview.id.in_(review_ids)))
        if execution_ids:
            await db.execute(delete(AgentDemand).where(AgentDemand.task_execution_id.in_(execution_ids)))
            await db.execute(delete(TaskExecution).where(TaskExecution.id.in_(execution_ids)))
        if task_ids:
            await db.execute(delete(TaskDependency).where(or_(
                TaskDependency.task_id.in_(task_ids), TaskDependency.depends_on_task_id.in_(task_ids))))
            await db.execute(delete(TaskAssignment).where(TaskAssignment.task_id.in_(task_ids)))
            await db.execute(delete(ProjectTask).where(ProjectTask.id.in_(task_ids)))
        await db.execute(delete(ProjectLoopPolicy).where(ProjectLoopPolicy.project_id == ids["project"]))
        await db.execute(delete(AgentRuntimeProfile).where(AgentRuntimeProfile.agent_id == ids["reviewer"]))
        await db.execute(delete(ProjectAgentMembership).where(
            ProjectAgentMembership.project_id.in_([ids["project"], ids["other"], ids["mission"]])))
        await db.execute(delete(AgentServiceCredential).where(
            AgentServiceCredential.agent_id.in_([ids["executor"], ids["reviewer"]])))
        await db.execute(delete(PlanningItem).where(PlanningItem.id.in_([ids["item"], ids["mission_item"]])))
        await db.execute(delete(Project).where(Project.id.in_([ids["project"], ids["other"], ids["mission"]])))
        await db.execute(delete(ProductVersion).where(ProductVersion.id == ids["version"]))
        await db.execute(delete(Product).where(Product.id == ids["product"]))
        await db.execute(delete(Agent).where(Agent.id.in_([ids["executor"], ids["reviewer"], ids["outsider"]])))
        await db.execute(delete(User).where(User.id.in_(ids["users"])))
        await db.commit()


def _client(token: str) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                       headers={"Authorization": f"Bearer {token}"})


@pytest_asyncio.fixture
async def admin(world):
    async with _client(create_access_token(world["admin"])) as client:
        yield client


async def _task(world, *, status: str = "in_progress", mission: bool = False, assigned: bool = True) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        task = ProjectTask(title="Guarded task", status=status,
                           planning_item_id=world["mission_item" if mission else "item"])
        db.add(task)
        await db.flush()
        if assigned:
            db.add(TaskAssignment(
                task_id=task.id, agent_id=world["executor"],
                membership_id=world["memberships"]["m_exec" if mission else "exec"],
            ))
        await db.commit()
        return task.id


async def _execution(
    world, task_id, *, evidence: str | None, status: str = "verified", via_assignment: bool = True,
    started_at: datetime | None = None,
) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        assignment_id = None
        if via_assignment:
            assignment_id = (await db.execute(
                select(TaskAssignment.id).where(TaskAssignment.task_id == task_id))).scalar_one_or_none()
        attempt = (await db.execute(
            select(TaskExecution.attempt_number).where(TaskExecution.task_id == task_id)
            .order_by(TaskExecution.attempt_number.desc()).limit(1))).scalar_one_or_none() or 0
        execution = TaskExecution(
            task_id=task_id, assignment_id=assignment_id, attempt_number=attempt + 1, status=status,
            evidence_ref=evidence, started_at=started_at or datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db.add(execution)
        await db.flush()
        if not via_assignment:
            # A Messages dispatch: no assignment, the executor is the demand's target.
            db.add(AgentDemand(
                from_agent="guard-test", subject="dispatch", body="run", origin_type="task", origin_id=task_id,
                from_agent_id=world["reviewer"], target_agent_id=world["executor"],
                task_execution_id=execution.id,
            ))
        await db.commit()
        return execution.id


async def _review(world, execution_id, membership_key: str, status: str = "approved") -> uuid.UUID:
    """A review row written directly (bypassing the review route's own
    checks) to prove the guard re-checks independence by itself."""
    async with AsyncSessionLocal() as db:
        review = TaskExecutionReview(
            execution_id=execution_id, reviewer_membership_id=world["memberships"][membership_key],
            status=status, feedback="looked at it", decided_at=datetime.now(timezone.utc),
        )
        db.add(review)
        await db.commit()
        return review.id


async def _proven(world, *, mission: bool = False, integrated: bool = True) -> tuple[uuid.UUID, uuid.UUID, str]:
    """A task with a verified execution, real git evidence and an independent
    approved review. Returns (task_id, execution_id, sha)."""
    task_id = await _task(world, mission=mission)
    sha = _commit(world["repo"], f"work-{uuid.uuid4().hex[:6]}.txt", branch=None if integrated else "feature")
    execution_id = await _execution(world, task_id, evidence=f"git:{sha}")
    await _review(world, execution_id, "m_rev" if mission else "rev")
    return task_id, execution_id, sha


async def _status(task_id) -> str:
    async with AsyncSessionLocal() as db:
        return (await db.get(ProjectTask, task_id)).status


def _code(response) -> str:
    assert response.status_code == 409, response.text
    return response.json()["detail"]["code"]


@pytest.mark.asyncio
async def test_done_without_execution_refused(world, admin):
    task_id = await _task(world)
    response = await admin.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"})
    assert _code(response) == "COMPLETION_NO_EXECUTION"
    assert response.json()["detail"]["message"]
    assert await _status(task_id) == "in_progress"


@pytest.mark.asyncio
async def test_done_with_reported_not_verified_refused(world, admin):
    task_id = await _task(world)
    sha = _commit(world["repo"], "reported.txt")
    for state in ("reported", "completed"):
        execution_id = await _execution(world, task_id, evidence=f"git:{sha}", status=state)
        await _review(world, execution_id, "rev")
        response = await admin.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"})
        assert _code(response) == "COMPLETION_EXECUTION_NOT_VERIFIED", state
    assert await _status(task_id) == "in_progress"


@pytest.mark.asyncio
async def test_invented_evidence_refused(world, admin):
    (world["repo"] / "old.txt").write_text("written before the execution started")
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    cases = [
        ("file:missing.txt", None, "COMPLETION_EVIDENCE_INVALID"),
        ("file:old.txt", future, "COMPLETION_EVIDENCE_INVALID"),  # mtime before the start
        ("git:" + "deadbeef" * 5, None, "COMPLETION_EVIDENCE_INVALID"),  # unknown sha
        (f"db:project_task:{uuid.uuid4()}", None, "COMPLETION_EVIDENCE_INVALID"),  # absent row
        ("db:users:" + str(uuid.uuid4()), None, "COMPLETION_EVIDENCE_INVALID"),  # not allowlisted
        ("forgehub://execution-results/x", None, "COMPLETION_EVIDENCE_INVALID"),  # untyped
        ("host_execution:123", None, "COMPLETION_EVIDENCE_INVALID"),  # refused until I.5
    ]
    for evidence, started_at, expected in cases:
        task_id = await _task(world)
        execution_id = await _execution(world, task_id, evidence=evidence, started_at=started_at)
        await _review(world, execution_id, "rev")
        response = await admin.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"})
        assert _code(response) == expected, evidence
        assert await _status(task_id) == "in_progress"


@pytest.mark.asyncio
async def test_unreachable_bridge_is_not_verified(world, admin, monkeypatch):
    task_id = await _task(world)
    execution_id = await _execution(world, task_id, evidence=f"git:{_commit(world['repo'], 'x.txt')}")
    await _review(world, execution_id, "rev")

    def down():
        def refuse(request):
            raise httpx.ConnectError("bridge down", request=request)
        return httpx.AsyncClient(transport=httpx.MockTransport(refuse))

    monkeypatch.setattr(evidence_bridge, "_client", down)
    response = await admin.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"})
    assert _code(response) == "COMPLETION_EVIDENCE_UNVERIFIED"
    assert await _status(task_id) == "in_progress"


@pytest.mark.asyncio
async def test_evidence_from_other_project_refused(world, admin, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("x")
    (world["repo"] / "leak.txt").symlink_to(outside / "secret.txt")
    other_sha = _commit(world["other_repo"], "other.txt")
    other_file = world["other_repo"] / "only-there.txt"
    other_file.write_text("x")
    cases = [
        (f"git:{other_sha}", "COMPLETION_EVIDENCE_INVALID"),  # commit of the other project's repo
        ("file:../" + world["other_repo"].name + "/only-there.txt", "COMPLETION_EVIDENCE_INVALID"),
        (f"file:{other_file}", "COMPLETION_EVIDENCE_INVALID"),  # absolute path
        ("file:leak.txt", "COMPLETION_EVIDENCE_UNVERIFIED"),  # symlink out: the bridge refuses (403)
    ]
    for evidence, expected in cases:
        task_id = await _task(world)
        execution_id = await _execution(world, task_id, evidence=evidence)
        await _review(world, execution_id, "rev")
        response = await admin.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"})
        assert _code(response) == expected, evidence
        assert "x" not in response.json()["detail"].get("content", "")


@pytest.mark.asyncio
async def test_reviewer_equals_executor_refused(world, admin):
    for via_assignment in (True, False):
        task_id = await _task(world, assigned=via_assignment)
        sha = _commit(world["repo"], f"self-{via_assignment}.txt")
        execution_id = await _execution(world, task_id, evidence=f"git:{sha}", via_assignment=via_assignment)
        await _review(world, execution_id, "exec")  # the executor's own membership
        response = await admin.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"})
        assert _code(response) == "COMPLETION_REVIEWER_IS_EXECUTOR", via_assignment
        # The review route refuses it too, even with no assignment_id to compare.
        created = await admin.post(f"/api/v1/orchestration/executions/{execution_id}/reviews", json={
            "reviewer_membership_id": str(world["memberships"]["exec"]), "status": "pending",
        })
        assert created.status_code == 409, created.text


@pytest.mark.asyncio
async def test_reviewer_without_can_review_refused(world, admin):
    task_id = await _task(world)
    execution_id = await _execution(world, task_id, evidence=f"git:{_commit(world['repo'], 'nr.txt')}")
    await _review(world, execution_id, "noreview")
    response = await admin.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"})
    assert _code(response) == "COMPLETION_NO_INDEPENDENT_REVIEW"
    assert "can_review" in " ".join(response.json()["detail"]["reasons"])

    # A suspended membership, and one of another project, don't count either.
    async with AsyncSessionLocal() as db:
        (await db.get(ProjectAgentMembership, world["memberships"]["rev"])).status = "suspended"
        await db.commit()
    task_id = await _task(world)
    execution_id = await _execution(world, task_id, evidence=f"git:{_commit(world['repo'], 'sus.txt')}")
    await _review(world, execution_id, "rev")
    await _review(world, execution_id, "other_rev")
    response = await admin.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"})
    assert _code(response) == "COMPLETION_NO_INDEPENDENT_REVIEW"
    reasons = " ".join(response.json()["detail"]["reasons"])
    assert "suspended" in reasons and "another project" in reasons
    async with AsyncSessionLocal() as db:
        (await db.get(ProjectAgentMembership, world["memberships"]["rev"])).status = "active"
        await db.commit()


@pytest.mark.asyncio
async def test_dependencies_and_subtasks_open_refused(world, admin):
    task_id, _, _ = await _proven(world)
    blocker = await _task(world)
    async with AsyncSessionLocal() as db:
        db.add(TaskDependency(task_id=task_id, depends_on_task_id=blocker))
        await db.commit()
    assert _code(await admin.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"})) == "COMPLETION_DEPENDENCIES_OPEN"
    async with AsyncSessionLocal() as db:
        await db.execute(delete(TaskDependency).where(TaskDependency.task_id == task_id))
        db.add(ProjectTask(title="sub", status="in_progress", planning_item_id=world["item"], parent_task_id=task_id))
        await db.commit()
    assert _code(await admin.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"})) == "COMPLETION_SUBTASKS_OPEN"


@pytest.mark.asyncio
async def test_all_writers_call_guard(world, admin, monkeypatch):
    # 1. PATCH /tasks (JWT).
    task_id = await _task(world)
    assert _code(await admin.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"})) == "COMPLETION_NO_EXECUTION"

    # 2. MCP update_task_status: the real tool, its HTTP call answered by the app.
    from app.mcp import factory_server

    real_client = httpx.AsyncClient
    monkeypatch.setenv("FORGEHUB_AGENT_TOKEN", world["tokens"]["exec"])
    monkeypatch.setattr(factory_server, "BASE_URL", "http://test")
    monkeypatch.setattr(factory_server.httpx, "AsyncClient",
                        lambda **kw: real_client(transport=ASGITransport(app=app), **kw))
    async with AsyncSessionLocal() as db:
        from app.db.models.governance import AuthorityDelegation
        delegation = AuthorityDelegation(
            grantor_user_id=world["admin_id"], grantee_type="agent",
            grantee_id=world["executor"], project_id=world["project"],
            allowed_actions=["planning.execution.manage"], max_risk="low", status="active",
            valid_from=datetime.now(timezone.utc) - timedelta(minutes=1),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add(delegation)
        await db.commit()
        delegation_id = delegation.id
    try:
        with pytest.raises(factory_server.FactoryError) as refused:
            await factory_server.update_task_status(str(task_id), "done")
        assert "409" in str(refused.value) and "COMPLETION_NO_EXECUTION" in str(refused.value)
    finally:
        monkeypatch.setattr(factory_server.httpx, "AsyncClient", real_client)
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AuthorityDelegation).where(AuthorityDelegation.id == delegation_id))
            await db.commit()
    assert await _status(task_id) == "in_progress"

    # 3. PATCH /orchestration/reviews approve, without valid evidence: 409, nothing recorded.
    task_id = await _task(world)
    execution_id = await _execution(world, task_id, evidence="file:never-written.txt", status="completed")
    review_id = await _review(world, execution_id, "rev", status="pending")
    response = await admin.patch(f"/api/v1/orchestration/reviews/{review_id}",
                                 json={"status": "approved", "feedback": "ok"})
    assert _code(response) == "COMPLETION_EVIDENCE_INVALID"
    async with AsyncSessionLocal() as db:
        assert (await db.get(TaskExecutionReview, review_id)).status == "pending"
        assert (await db.get(TaskExecution, execution_id)).status == "completed"
    assert await _status(task_id) == "in_progress"

    # 4. Review refresh (reviewer CLI approves): the review is kept, the task is not done.
    task_id = await _task(world)
    async with AsyncSessionLocal() as db:
        profile = AgentRuntimeProfile(agent_id=world["reviewer"], name="guard review", runtime_type="claude")
        db.add(profile)
        await db.flush()
        policy = ProjectLoopPolicy(
            project_id=world["project"], name="guard loop", phase="implementation",
            producer_membership_id=world["memberships"]["exec"], reviewer_membership_id=world["memberships"]["rev"],
            producer_runtime_profile_id=profile.id, reviewer_runtime_profile_id=profile.id,
            min_review_score=50, requires_human_approval=False,
        )
        db.add(policy)
        await db.flush()
        execution = TaskExecution(task_id=task_id, attempt_number=1, status="completed",
                                  evidence_ref="forgehub://agent-runs/x", loop_policy_id=policy.id,
                                  started_at=datetime.now(timezone.utc) - timedelta(hours=1))
        db.add(execution)
        await db.flush()
        review = TaskExecutionReview(execution_id=execution.id, reviewer_membership_id=world["memberships"]["rev"],
                                     status="running", runtime_session_ref="guard-run")
        db.add(review)
        await db.commit()
        refresh_review_id = review.id

    from app.api.routes import orchestration

    def fake_bridge(**kw):
        def answer(request):
            return httpx.Response(200, json={"status": "completed",
                                             "output": "FORGEHUB_SCORE: 90\nFORGEHUB_DECISION: approved"})
        return real_client(transport=httpx.MockTransport(answer))

    monkeypatch.setattr(orchestration.httpx, "AsyncClient", fake_bridge)
    try:
        response = await admin.post(f"/api/v1/orchestration/reviews/{refresh_review_id}/refresh")
    finally:
        monkeypatch.setattr(orchestration.httpx, "AsyncClient", real_client)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "approved"
    assert await _status(task_id) == "in_progress"
    async with AsyncSessionLocal() as db:
        refused_event = (await db.execute(select(AuditEvent).where(
            AuditEvent.entity_id == task_id, AuditEvent.event_type == "task_completion_refused"))).scalar_one()
        assert refused_event.payload["code"] == "COMPLETION_EVIDENCE_INVALID"
        assert refused_event.actor == world["admin"]

    # 5. Governed task approval: approving the request is not proof by itself.
    from app.core.governed_approval import decide_task_approval, request_task_approval

    task_id = await _task(world, assigned=False)
    sha = _commit(world["repo"], "governed.txt")
    execution_id = await _execution(world, task_id, evidence=f"git:{sha}", via_assignment=False)
    rules = {"deny_self_approval": True, "expires_hours": 72}
    async with AsyncSessionLocal() as db:
        policy = Policy(name=f"Guard task approval {world['suffix']}", policy_type="approval_required",
                        rules=rules, is_active=True, entity_type="project_task")
        db.add(policy)
        await db.flush()
        version = PolicyVersion(policy_id=policy.id, version=1, rules_snapshot=rules, evaluator_type="structured",
                                content_hash=hashlib.sha256(json.dumps(rules, sort_keys=True).encode()).hexdigest(),
                                status="active")
        db.add(version)
        await db.flush()
        db.add(PolicyBinding(policy_version_id=version.id, target_type="project_task", target_id=world["project"],
                             priority=100, is_active=True))
        await db.commit()
        world["policy"], world["policy_version"] = policy.id, version.id
    async with AsyncSessionLocal() as db:
        request = await request_task_approval(db, await db.get(ProjectTask, task_id),
                                              await db.get(TaskExecution, execution_id))
        await db.commit()
        request_id = request.id
    principal = ActorPrincipal("user", world["admin_id"], world["admin"], is_admin=True)
    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            await decide_task_approval(db, principal, await db.get(ApprovalRequest, request_id),
                                       "approved", "fine", None)
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "COMPLETION_NO_INDEPENDENT_REVIEW"
        await db.rollback()
    assert await _status(task_id) == "in_progress"


@pytest.mark.asyncio
async def test_deployed_requires_done_and_release(world, admin):
    task_id, _, _ = await _proven(world)
    assert _code(await admin.patch(f"/api/v1/tasks/{task_id}", json={"status": "deployed"})) == "DEPLOYED_REQUIRES_DONE"
    done = await admin.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"})
    assert done.status_code == 200, done.text
    deployed = await admin.patch(f"/api/v1/tasks/{task_id}", json={"status": "deployed"})
    assert deployed.status_code == 200, deployed.text
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(AuditEvent.id).where(
            AuditEvent.entity_id == task_id, AuditEvent.event_type == "task_deployed"))).scalar_one()

    # A mission task: done once integrated, never deployed without a release row.
    mission_task, _, _ = await _proven(world, mission=True)
    assert (await admin.patch(f"/api/v1/tasks/{mission_task}", json={"status": "done"})).status_code == 200
    assert _code(await admin.patch(f"/api/v1/tasks/{mission_task}", json={"status": "deployed"})) == "DEPLOYED_WITHOUT_RELEASE"
    assert await _status(mission_task) == "done"


@pytest.mark.asyncio
async def test_historical_done_untouched(world, admin):
    task_id = await _task(world, status="done")  # completed before the guard: no execution at all
    response = await admin.patch(f"/api/v1/tasks/{task_id}", json={"status": "done", "title": "Renamed"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "done" and response.json()["title"] == "Renamed"
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(TaskExecution.id).where(TaskExecution.task_id == task_id))).first() is None
        assert (await db.execute(select(AuditEvent.id).where(AuditEvent.entity_id == task_id))).first() is None
    # A new transition from it is still guarded.
    assert _code(await admin.patch(f"/api/v1/tasks/{task_id}", json={"status": "deployed"})) == "COMPLETION_NO_EXECUTION"
    assert await _status(task_id) == "done"


@pytest.mark.asyncio
async def test_historical_import_through_guard(world, admin):
    """Importing past work = a reported execution with real evidence, an
    independent review recorded by an admin, then the guard. Without proof
    it stays reported."""
    task_id = await _task(world, status="blocked")
    (world["repo"] / "delivered.md").write_text("real deliverable")
    execution_id = await _execution(world, task_id, evidence="file:delivered.md", status="reported")
    async with AsyncSessionLocal() as db:
        execution = await db.get(TaskExecution, execution_id)
        ok, reason = await verify_evidence(db, execution)
        assert ok is True, reason
        execution.status = "verified"
        await db.commit()
    review = await admin.post(f"/api/v1/orchestration/executions/{execution_id}/reviews", json={
        "reviewer_membership_id": str(world["memberships"]["rev"]), "status": "approved",
        "feedback": "Checked the delivered file.",
    })
    assert review.status_code == 201, review.text
    async with AsyncSessionLocal() as db:
        recorded = (await db.execute(select(AuditEvent).where(
            AuditEvent.entity_id == uuid.UUID(review.json()["id"])))).scalar_one()
        assert recorded.payload["recorded_by"] == world["admin"] and recorded.payload["manual_verification"]
    response = await admin.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"})
    assert response.status_code == 200, response.text

    # Without proof: the evidence doesn't exist, so it can never become verified.
    unproven = await _task(world, status="blocked")
    execution_id = await _execution(world, unproven, evidence="file:invented.md", status="reported")
    async with AsyncSessionLocal() as db:
        ok, _ = await verify_evidence(db, await db.get(TaskExecution, execution_id))
    assert ok is False
    assert _code(await admin.patch(f"/api/v1/tasks/{unproven}", json={"status": "done"})) == "COMPLETION_EXECUTION_NOT_VERIFIED"
    async with AsyncSessionLocal() as db:
        assert (await db.get(TaskExecution, execution_id)).status == "reported"
    assert await _status(unproven) == "blocked"


@pytest.mark.asyncio
async def test_audit_actor_is_principal(world, admin):
    from app.core.dispatch_signal import reset_scheduled_dispatch_signal, wait_for_scheduled_dispatch

    task_id, execution_id, sha = await _proven(world)
    reset_scheduled_dispatch_signal()
    assert (await admin.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"})).status_code == 200
    assert await wait_for_scheduled_dispatch(0.05)  # dependents may be released now
    async with AsyncSessionLocal() as db:
        event = (await db.execute(select(AuditEvent).where(
            AuditEvent.entity_id == task_id, AuditEvent.event_type == "task_completed"))).scalar_one()
    assert event.actor == world["admin"] and event.actor not in ("system", "forgehub")
    assert event.payload["principal_type"] == "user"
    assert event.payload["proof"]["execution_id"] == str(execution_id)
    assert event.payload["proof"]["evidence_ref"] == f"git:{sha}"
    assert event.payload["proof"]["reviewer_agent_id"] == str(world["reviewer"])
    assert event.payload["proof"]["review_id"]

    # An agent credential (agt_) is recorded as that agent.
    task_id, _, _ = await _proven(world)
    async with AsyncSessionLocal() as db:
        from app.db.models.governance import AuthorityDelegation
        delegation = AuthorityDelegation(
            grantor_user_id=world["admin_id"], grantee_type="agent", grantee_id=world["reviewer"],
            project_id=world["project"], allowed_actions=["planning.execution.manage"], max_risk="low",
            status="active", valid_from=datetime.now(timezone.utc) - timedelta(minutes=1),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add(delegation)
        await db.commit()
        delegation_id = delegation.id
    try:
        async with _client(world["tokens"]["rev"]) as agent:
            response = await agent.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"})
        assert response.status_code == 200, response.text
        async with AsyncSessionLocal() as db:
            event = (await db.execute(select(AuditEvent).where(
                AuditEvent.entity_id == task_id, AuditEvent.event_type == "task_completed"))).scalar_one()
        assert event.actor == world["reviewer_name"] and event.payload["principal_type"] == "agent"
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AuthorityDelegation).where(AuthorityDelegation.id == delegation_id))
            await db.commit()


@pytest.mark.asyncio
async def test_review_created_approved_without_feedback_refused(world, admin):
    task_id = await _task(world)
    execution_id = await _execution(world, task_id, evidence=f"git:{_commit(world['repo'], 'fb.txt')}")
    response = await admin.post(f"/api/v1/orchestration/executions/{execution_id}/reviews", json={
        "reviewer_membership_id": str(world["memberships"]["rev"]), "status": "approved",
    })
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_review_caller_must_be_the_reviewer(world):
    """An agent reviews only through its own membership; a human must be an
    admin (recording the agent's review). The middleware doesn't admit agt_
    on the review routes yet (M0.2a adds it), so the agent rule is proven on
    the route's own check."""
    from app.core.task_completion_guard import assert_principal_may_review

    task_id = await _task(world)
    execution_id = await _execution(world, task_id, evidence=f"git:{_commit(world['repo'], 'who.txt')}")
    body = {"reviewer_membership_id": str(world["memberships"]["rev"]), "status": "pending"}
    path = f"/api/v1/orchestration/executions/{execution_id}/reviews"
    async with _client(create_access_token(world["operator"])) as operator:  # human, not admin
        assert (await operator.post(path, json=body)).status_code == 403
    async with AsyncSessionLocal() as db:
        membership = await db.get(ProjectAgentMembership, world["memberships"]["rev"])
        executor = ActorPrincipal("agent", world["executor"], "executor")
        with pytest.raises(HTTPException) as exc:
            await assert_principal_may_review(db, executor, membership)
        assert exc.value.status_code == 403
        reviewer = ActorPrincipal("agent", world["reviewer"], world["reviewer_name"])
        assert await assert_principal_may_review(db, reviewer, membership) is None


@pytest.mark.asyncio
async def test_review_approval_does_not_mark_mission_task_done_before_integration(world, admin):
    task_id = await _task(world, mission=True)
    sha = _commit(world["repo"], "mission-feature.txt", branch="feature/m0-6a")
    execution_id = await _execution(world, task_id, evidence=f"git:{sha}", status="completed")
    review_id = await _review(world, execution_id, "m_rev", status="pending")

    approved = await admin.patch(f"/api/v1/orchestration/reviews/{review_id}",
                                 json={"status": "approved", "feedback": "Code and tests reviewed."})
    assert approved.status_code == 200, approved.text
    async with AsyncSessionLocal() as db:
        assert (await db.get(TaskExecution, execution_id)).status == "verified"
    assert await _status(task_id) == "in_review"

    refused = await admin.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"})
    assert _code(refused) == "COMPLETION_NOT_INTEGRATED"
    assert refused.json()["detail"]["mainline"] == "develop"

    _git(world["repo"], "merge", "-q", "--no-ff", "-m", "integrate", "feature/m0-6a")
    done = await admin.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"})
    assert done.status_code == 200, done.text
    async with AsyncSessionLocal() as db:
        event = (await db.execute(select(AuditEvent).where(
            AuditEvent.entity_id == task_id, AuditEvent.event_type == "task_completed"))).scalar_one()
    assert event.payload["proof"]["integrated_ref"] == "develop"
