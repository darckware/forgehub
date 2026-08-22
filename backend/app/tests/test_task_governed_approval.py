"""Layered task-execution governance, Fase 3 (plan: resilient-twirling-
blossom): the review-in-layers cycle -- an agent's verified execution opens
an ApprovalRequest, a *different* agent (deny_self_approval) decides
approved/changes_requested/rejected, and changes_requested redispatches
automatically with the reviewer's comments attached. See core/
governed_approval.py's request_task_approval/decide_task_approval
docstrings for the full design.

The mechanism is deliberately inert (silent no-op) unless a Policy/
PolicyVersion/PolicyBinding for target_type="project_task" is active --
this test file seeds one directly via ORM to exercise it, mirroring the
real seed shape from alembic/versions/e9b5c2d4f710_add_governed_planning_
approval.py (the concept-approval equivalent) without requiring that
migration data to actually be applied in every environment.
"""
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from app.api.routes.demand import _finalize_dispatch
from app.core.task_evidence import run_evidence_verification_pass
from app.db.base import AsyncSessionLocal, engine
from app.db.models.agent import Agent
from app.db.models.backlog import PlanningItem
from app.db.models.demand import AgentDemand
from app.db.models.governance import ApprovalRequest, Policy, PolicyBinding, PolicyVersion
from app.db.models.product import Product, ProductVersion
from app.db.models.project import Project
from app.db.models.task import ProjectTask, TaskAssignment, TaskExecution
from app.main import app

RULES = {"deny_self_approval": True, "expires_hours": 72}


@pytest_asyncio.fixture
async def client(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as ac:
        yield ac


@pytest_asyncio.fixture
async def world(tmp_path):
    suffix = uuid.uuid4().hex[:8]
    rules_json = json.dumps(RULES, sort_keys=True)
    async with AsyncSessionLocal() as session:
        product = Product(name=f"Governed Task Product {suffix}")
        session.add(product)
        await session.flush()
        version = ProductVersion(product_id=product.id, version="0.1.0")
        session.add(version)
        await session.flush()
        project = Project(
            name=f"Governed Task Project {suffix}",
            product_version_id=version.id,
            working_directory_path=str(tmp_path),
        )
        session.add(project)
        await session.flush()
        item = PlanningItem(title="Governed test planning item", item_type="feature", project_id=project.id)
        session.add(item)
        await session.flush()
        task = ProjectTask(title="Governed test task", planning_item_id=item.id, task_type="bug")
        session.add(task)
        executor = Agent(name=f"Executor {suffix}", agent_type="executor", runtime_type="claude")
        reviewer = Agent(name=f"Reviewer {suffix}", agent_type="executor", runtime_type="claude")
        session.add_all([executor, reviewer])
        await session.flush()
        assignment = TaskAssignment(task_id=task.id, agent_id=executor.id, status="active")
        session.add(assignment)

        policy = Policy(
            name=f"Task completion approval {suffix}",
            policy_type="approval_required",
            rules=RULES,
            is_active=True,
            entity_type="project_task",
        )
        session.add(policy)
        await session.flush()
        policy_version = PolicyVersion(
            policy_id=policy.id, version=1, rules_snapshot=RULES,
            evaluator_type="structured", content_hash=hashlib.sha256(rules_json.encode()).hexdigest(),
            status="active",
        )
        session.add(policy_version)
        await session.flush()
        # Project-scoped, not global -- matches how this is actually
        # activated in production (see PLANNING_DELIVERY_ARCHITECTURE.md
        # §6.6): a binding's target_id is interpreted as "scope to this
        # Project" for target_type="project_task".
        binding = PolicyBinding(
            policy_version_id=policy_version.id, target_type="project_task",
            target_id=project.id, priority=100, is_active=True,
        )
        session.add(binding)

        await session.commit()
        ids = {
            "product_id": product.id,
            "version_id": version.id,
            "project_id": project.id,
            "item_id": item.id,
            "task_id": task.id,
            "executor_id": executor.id,
            "reviewer_id": reviewer.id,
            "policy_id": policy.id,
        }

    yield ids

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "DELETE FROM company.approval_decisions WHERE approval_request_id IN "
                "(SELECT id FROM company.approval_requests WHERE target_id = :id)"
            ),
            {"id": ids["task_id"]},
        )
        await conn.execute(
            text("DELETE FROM company.approval_requests WHERE target_id = :id"), {"id": ids["task_id"]}
        )
        await conn.execute(
            text(
                "DELETE FROM company.policy_evaluations WHERE target_id = :id"
            ),
            {"id": ids["task_id"]},
        )
        await conn.execute(
            text("DELETE FROM company.policy_bindings WHERE policy_version_id IN "
                 "(SELECT id FROM company.policy_versions WHERE policy_id = :id)"),
            {"id": ids["policy_id"]},
        )
        await conn.execute(
            text("DELETE FROM company.policy_versions WHERE policy_id = :id"), {"id": ids["policy_id"]}
        )
        await conn.execute(text("DELETE FROM company.policies WHERE id = :id"), {"id": ids["policy_id"]})
        await conn.execute(
            text("DELETE FROM company.agent_demands WHERE origin_id = :id"), {"id": ids["task_id"]}
        )
        await conn.execute(
            text("DELETE FROM company.task_executions WHERE task_id = :id"), {"id": ids["task_id"]}
        )
        await conn.execute(
            text("DELETE FROM company.task_assignments WHERE task_id = :id"), {"id": ids["task_id"]}
        )
        await conn.execute(
            text("DELETE FROM company.project_tasks WHERE id = :id"), {"id": ids["task_id"]}
        )
        await conn.execute(
            text("DELETE FROM company.agents WHERE id = ANY(:ids)"),
            {"ids": [ids["executor_id"], ids["reviewer_id"]]},
        )
        await conn.execute(
            text("DELETE FROM company.planning_items WHERE id = :id"), {"id": ids["item_id"]}
        )
        await conn.execute(text("DELETE FROM company.projects WHERE id = :id"), {"id": ids["project_id"]})
        await conn.execute(
            text("DELETE FROM company.product_versions WHERE id = :id"), {"id": ids["version_id"]}
        )
        await conn.execute(text("DELETE FROM company.products WHERE id = :id"), {"id": ids["product_id"]})


def _mock_dispatch(monkeypatch):
    """Trivial dispatch_agent_run mock for tests that don't care about
    call counts -- just need dispatch to "succeed" without a real
    host-bridge."""
    from app.api.routes import demand as demand_routes

    async def fake_dispatch(*args, **kwargs):
        return {"run_id": "fake-run-id"}

    monkeypatch.setattr(demand_routes, "dispatch_agent_run", fake_dispatch)


async def _dispatch_and_verify(client, world, tmp_path, monkeypatch, *, filename="evidence.txt"):
    """Drives a task through dispatch -> finalize (reported) -> real
    evidence file -> automatic verification, ending with a pending
    ApprovalRequest (since `world`'s fixture already activated the
    project_task policy binding). Returns (task_id, approval_request_id).

    Does NOT touch `dispatch_agent_run` itself -- the caller mocks it
    beforehand (some tests need to track/count calls across this helper
    and a later redispatch, so a second setattr here would silently
    clobber theirs)."""
    dispatched = await client.post(f"/api/v1/tasks/{world['task_id']}/dispatch", json={})
    assert dispatched.status_code == 200, dispatched.text
    demand_id = uuid.UUID(dispatched.json()["demand_id"])

    async with AsyncSessionLocal() as session:
        await _finalize_dispatch(
            session, demand_id,
            {"status": "completed", "output": f"Done.\nEVIDENCE: file:{filename}"},
        )
        await session.commit()

    (tmp_path / filename).write_text("real work product")

    async with AsyncSessionLocal() as session:
        await run_evidence_verification_pass(session)

    async with AsyncSessionLocal() as session:
        request = (
            await session.execute(
                select(ApprovalRequest).where(
                    ApprovalRequest.target_type == "project_task",
                    ApprovalRequest.target_id == world["task_id"],
                    ApprovalRequest.status == "pending",
                )
            )
        ).scalar_one_or_none()
    assert request is not None, "expected a pending ApprovalRequest after verification"
    return request.id


async def _issue_agent_token(client, agent_id: uuid.UUID) -> str:
    resp = await client.post(
        "/api/v1/governed/agent-credentials", json={"agent_id": str(agent_id), "label": "test credential"}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["token"]


async def _grant_decide_authority(client, agent_id: uuid.UUID) -> None:
    """`decide_task_approval` calls authorize_action("governance.approval.
    decide", ...) same as decide_concept_approval already does -- an agent
    principal needs an active AuthorityDelegation for that action key
    before deny_self_approval (or anything else) is even reached. Admin
    `client` (the module fixture, JWT) grants it, same pattern as
    test_governed_authority.py."""
    resp = await client.post(
        "/api/v1/governed/authority-delegations",
        json={
            "grantee_agent_id": str(agent_id),
            "allowed_actions": ["governance.approval.decide"],
            "scope_type": "organization",
            "max_risk": "medium",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "reason": "test",
        },
    )
    assert resp.status_code == 201, resp.text


async def test_no_binding_means_no_approval_request(client, world, tmp_path, monkeypatch):
    """Confirms the mechanism is inert without an active binding -- deletes
    the one `world` seeded, then drives dispatch/evidence and checks no
    ApprovalRequest is created (Fase 1/2 behavior keeps working alone)."""
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("UPDATE company.policy_bindings SET is_active = false WHERE policy_version_id IN "
                 "(SELECT id FROM company.policy_versions WHERE policy_id = :id)"),
            {"id": world["policy_id"]},
        )
        await session.commit()

    from app.api.routes import demand as demand_routes

    async def fake_dispatch(*args, **kwargs):
        return {"run_id": "fake-run-id"}

    monkeypatch.setattr(demand_routes, "dispatch_agent_run", fake_dispatch)

    dispatched = await client.post(f"/api/v1/tasks/{world['task_id']}/dispatch", json={})
    demand_id = uuid.UUID(dispatched.json()["demand_id"])
    async with AsyncSessionLocal() as session:
        await _finalize_dispatch(
            session, demand_id, {"status": "completed", "output": "Done.\nEVIDENCE: file:inert.txt"}
        )
        await session.commit()
    (tmp_path / "inert.txt").write_text("work")

    async with AsyncSessionLocal() as session:
        await run_evidence_verification_pass(session)
        pending = (
            await session.execute(
                select(ApprovalRequest).where(
                    ApprovalRequest.target_type == "project_task", ApprovalRequest.target_id == world["task_id"]
                )
            )
        ).scalar_one_or_none()
    assert pending is None

    # And the task can still go straight to done (Fase 1's own gate is all
    # that applies) since nothing is pending.
    done = await client.patch(f"/api/v1/tasks/{world['task_id']}", json={"status": "done"})
    assert done.status_code == 200, done.text


async def test_task_cannot_be_marked_done_while_approval_pending(client, world, tmp_path, monkeypatch):
    _mock_dispatch(monkeypatch)
    await _dispatch_and_verify(client, world, tmp_path, monkeypatch)

    blocked = await client.patch(f"/api/v1/tasks/{world['task_id']}", json={"status": "done"})
    assert blocked.status_code == 409, blocked.text
    assert "governed approval" in blocked.json()["detail"]


async def test_executor_cannot_decide_its_own_execution(client, world, tmp_path, monkeypatch):
    _mock_dispatch(monkeypatch)
    request_id = await _dispatch_and_verify(client, world, tmp_path, monkeypatch)
    token = await _issue_agent_token(client, world["executor_id"])
    # Grant the executor decide-authority too, so the 403 below is proven to
    # come from deny_self_approval specifically -- not just "no delegation
    # at all" (a different, less interesting 403).
    await _grant_decide_authority(client, world["executor_id"])

    resp = await client.post(
        f"/api/v1/governed/approval-requests/{request_id}:decide",
        json={"decision": "approved"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text
    assert "separation_of_duties_violation" in resp.text


async def test_reviewer_approves_and_task_becomes_done(client, world, tmp_path, monkeypatch):
    _mock_dispatch(monkeypatch)
    request_id = await _dispatch_and_verify(client, world, tmp_path, monkeypatch)
    token = await _issue_agent_token(client, world["reviewer_id"])
    await _grant_decide_authority(client, world["reviewer_id"])

    resp = await client.post(
        f"/api/v1/governed/approval-requests/{request_id}:decide",
        json={"decision": "approved", "comments": "looks good"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text

    async with AsyncSessionLocal() as session:
        task = await session.get(ProjectTask, world["task_id"])
        assert task.status == "done"
        assert task.completed_at is not None


async def test_reviewer_requests_changes_and_task_redispatches(client, world, tmp_path, monkeypatch):
    from app.api.routes import demand as demand_routes

    dispatch_calls = []

    async def fake_dispatch(*args, **kwargs):
        dispatch_calls.append(kwargs)
        return {"run_id": f"fake-run-{len(dispatch_calls)}"}

    monkeypatch.setattr(demand_routes, "dispatch_agent_run", fake_dispatch)

    request_id = await _dispatch_and_verify(client, world, tmp_path, monkeypatch)
    assert len(dispatch_calls) == 1  # the original dispatch

    token = await _issue_agent_token(client, world["reviewer_id"])
    await _grant_decide_authority(client, world["reviewer_id"])
    resp = await client.post(
        f"/api/v1/governed/approval-requests/{request_id}:decide",
        json={"decision": "changes_requested", "comments": "faltou tratar o caso X"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text

    # A second dispatch happened automatically (the redispatch).
    assert len(dispatch_calls) == 2

    async with AsyncSessionLocal() as session:
        task = await session.get(ProjectTask, world["task_id"])
        assert task.status == "in_progress"

        executions = list(
            (await session.execute(
                select(TaskExecution).where(TaskExecution.task_id == world["task_id"])
                .order_by(TaskExecution.attempt_number)
            )).scalars()
        )
        assert len(executions) == 2
        assert executions[0].status == "verified"
        assert executions[1].status == "running"

        new_demand = (
            await session.execute(
                select(AgentDemand).where(AgentDemand.task_execution_id == executions[1].id)
            )
        ).scalar_one()
        # command_text is its own column (fed into the CLI prompt via
        # build_thread_prompt), not merged into `body` -- see
        # _execute_dispatch's own docstring.
        assert new_demand.command_text is not None
        assert "faltou tratar o caso X" in new_demand.command_text


async def test_reviewer_rejects_and_task_becomes_blocked(client, world, tmp_path, monkeypatch):
    _mock_dispatch(monkeypatch)
    request_id = await _dispatch_and_verify(client, world, tmp_path, monkeypatch)
    token = await _issue_agent_token(client, world["reviewer_id"])
    await _grant_decide_authority(client, world["reviewer_id"])

    resp = await client.post(
        f"/api/v1/governed/approval-requests/{request_id}:decide",
        json={"decision": "rejected", "comments": "abordagem errada"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text

    async with AsyncSessionLocal() as session:
        task = await session.get(ProjectTask, world["task_id"])
        assert task.status == "blocked"


async def test_binding_scoped_to_one_project_does_not_affect_another(client, world, tmp_path, monkeypatch):
    """`world`'s PolicyBinding is scoped to `world["project_id"]` only.
    A second, unrelated project with its own task -- no binding of its own
    -- must complete straight to done, exactly as Fase 1/2 alone would
    (production-realistic version of test_no_binding_means_no_approval_
    request, proving isolation rather than just absence)."""
    suffix = uuid.uuid4().hex[:8]
    other_tmp = tmp_path / "other-project"
    other_tmp.mkdir()
    async with AsyncSessionLocal() as session:
        product = Product(name=f"Other Product {suffix}")
        session.add(product)
        await session.flush()
        version = ProductVersion(product_id=product.id, version="0.1.0")
        session.add(version)
        await session.flush()
        other_project = Project(
            name=f"Other Project {suffix}", product_version_id=version.id,
            working_directory_path=str(other_tmp),
        )
        session.add(other_project)
        await session.flush()
        item = PlanningItem(title="Other planning item", item_type="feature", project_id=other_project.id)
        session.add(item)
        await session.flush()
        other_task = ProjectTask(title="Other project's task", planning_item_id=item.id, task_type="bug")
        session.add(other_task)
        await session.flush()
        assignment = TaskAssignment(task_id=other_task.id, agent_id=world["executor_id"], status="active")
        session.add(assignment)
        await session.commit()
        other_task_id = other_task.id
        other_project_id = other_project.id

    try:
        _mock_dispatch(monkeypatch)
        dispatched = await client.post(f"/api/v1/tasks/{other_task_id}/dispatch", json={})
        assert dispatched.status_code == 200, dispatched.text
        demand_id = uuid.UUID(dispatched.json()["demand_id"])
        async with AsyncSessionLocal() as session:
            await _finalize_dispatch(
                session, demand_id, {"status": "completed", "output": "Done.\nEVIDENCE: file:other.txt"}
            )
            await session.commit()
        (other_tmp / "other.txt").write_text("real work, different project")

        async with AsyncSessionLocal() as session:
            await run_evidence_verification_pass(session)
            pending = (
                await session.execute(
                    select(ApprovalRequest).where(
                        ApprovalRequest.target_type == "project_task", ApprovalRequest.target_id == other_task_id
                    )
                )
            ).scalar_one_or_none()
        assert pending is None, "a binding scoped to world's project must not leak into another project"

        done = await client.patch(f"/api/v1/tasks/{other_task_id}", json={"status": "done"})
        assert done.status_code == 200, done.text
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("DELETE FROM company.agent_demands WHERE origin_id = :id"), {"id": other_task_id}
            )
            await session.execute(
                text("DELETE FROM company.task_executions WHERE task_id = :id"), {"id": other_task_id}
            )
            await session.execute(
                text("DELETE FROM company.task_assignments WHERE task_id = :id"), {"id": other_task_id}
            )
            await session.execute(text("DELETE FROM company.project_tasks WHERE id = :id"), {"id": other_task_id})
            await session.execute(
                text("DELETE FROM company.planning_items WHERE project_id = :id"), {"id": other_project_id}
            )
            await session.execute(text("DELETE FROM company.projects WHERE id = :id"), {"id": other_project_id})
            await session.execute(
                text("DELETE FROM company.product_versions WHERE product_id = :id"), {"id": product.id}
            )
            await session.execute(text("DELETE FROM company.products WHERE id = :id"), {"id": product.id})
            await session.commit()
