"""RBAC action and revocable agent-delegation integration coverage."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.security import create_access_token, hash_password
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent, AgentServiceCredential
from app.db.models.backlog import PlanningItem
from app.db.models.execution import ExecutionWave, ExecutionWaveTask
from app.db.models.governance import AuditEvent, AuthorityDelegation
from app.db.models.notification import Notification
from app.db.models.orchestration import ProjectAgentMembership
from app.db.models.product import Product, ProductVersion
from app.db.models.project import PlanBaseline, Project, ProjectPlan
from app.db.models.profile import Profile, ProfileActionPermission
from app.db.models.task import ProjectTask, TaskAssignment
from app.db.models.user import User
from app.main import app


@pytest_asyncio.fixture
async def authority_context():
    suffix = uuid.uuid4().hex
    async with AsyncSessionLocal() as db:
        profile = Profile(name=f"limited-{suffix}")
        admin = User(username=f"authority-admin-{suffix}", hashed_password=hash_password("test"), is_admin=True)
        db.add_all([profile, admin]); await db.flush()
        limited = User(username=f"authority-limited-{suffix}", hashed_password=hash_password("test"), profile_id=profile.id)
        agent = Agent(name=f"athos-test-{suffix}", agent_type="coordinator")
        db.add_all([limited, agent]); await db.commit()
        for row in (profile, admin, limited, agent): await db.refresh(row)
        data = {
            "profile": profile.id, "admin": admin.id, "limited": limited.id, "agent": agent.id,
            "admin_headers": {"Authorization": f"Bearer {create_access_token(admin.username)}"},
            "limited_headers": {"Authorization": f"Bearer {create_access_token(limited.username)}"},
        }
    yield data
    async with AsyncSessionLocal() as db:
        delegation_id = data.get("delegation")
        credential_id = data.get("credential")
        if delegation_id:
            await db.execute(delete(Notification).where(Notification.event_key.in_([
                f"delegation:granted:{delegation_id}", f"delegation:revoked:{delegation_id}",
            ])))
            await db.execute(delete(AuditEvent).where(AuditEvent.entity_type == "authority_delegation", AuditEvent.entity_id == delegation_id))
        if credential_id:
            await db.execute(delete(AuditEvent).where(AuditEvent.entity_type == "agent_service_credential", AuditEvent.entity_id == credential_id))
        await db.execute(delete(AgentServiceCredential).where(AgentServiceCredential.agent_id == data["agent"]))
        await db.execute(delete(AuthorityDelegation).where(AuthorityDelegation.grantee_id == data["agent"]))
        if data.get("project"):
            await db.execute(delete(Project).where(Project.id == data["project"]))
        if data.get("version"):
            await db.execute(delete(ProductVersion).where(ProductVersion.id == data["version"]))
        if data.get("product"):
            await db.execute(delete(Product).where(Product.id == data["product"]))
        await db.execute(delete(ProfileActionPermission).where(ProfileActionPermission.profile_id == data["profile"]))
        await db.execute(delete(User).where(User.id.in_([data["admin"], data["limited"]])))
        await db.execute(delete(Profile).where(Profile.id == data["profile"]))
        await db.execute(delete(Agent).where(Agent.id == data["agent"]))
        await db.commit()


@pytest.mark.asyncio
async def test_sensitive_action_is_deny_by_default(authority_context):
    transport = ASGITransport(app=app)
    payload = {"name": f"Denied {uuid.uuid4()}", "problem_statement": "Must not be created without action permission."}
    async with AsyncClient(transport=transport, base_url="http://test", headers=authority_context["limited_headers"]) as client:
        denied = await client.post("/api/v1/conception/ideas", json=payload)
        assert denied.status_code == 403
        me = await client.get("/api/v1/auth/me")
        assert me.status_code == 200
        assert me.json()["actions"]["planning.concept.edit"] is False


@pytest.mark.asyncio
async def test_agent_credential_and_delegation_are_revocable(authority_context):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=authority_context["admin_headers"]) as admin:
        credential = await admin.post("/api/v1/governed/agent-credentials", json={
            "agent_id": str(authority_context["agent"]), "label": "test governed credential"
        })
        assert credential.status_code == 201, credential.text
        token = credential.json()["token"]
        credential_id = credential.json()["credential_id"]
        delegation = await admin.post("/api/v1/governed/authority-delegations", json={
            "grantee_agent_id": str(authority_context["agent"]),
            "allowed_actions": ["governance.approval.view", "governance.approval.decide"],
            "scope_type": "organization", "max_risk": "medium",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "reason": "integration test",
        })
        assert delegation.status_code == 201, delegation.text
        delegation_id = delegation.json()["id"]
        authority_context["credential"] = uuid.UUID(credential_id)
        authority_context["delegation"] = uuid.UUID(delegation_id)

        async with AsyncClient(transport=transport, base_url="http://test", headers={"Authorization": f"Bearer {token}"}) as agent:
            allowed = await agent.get("/api/v1/governed/approval-requests")
            assert allowed.status_code == 200, allowed.text

            revoked = await admin.post(f"/api/v1/governed/authority-delegations/{delegation_id}:revoke")
            assert revoked.status_code == 200
            denied = await agent.get("/api/v1/governed/approval-requests")
            assert denied.status_code == 403

            credential_revoked = await admin.post(f"/api/v1/governed/agent-credentials/{credential_id}:revoke")
            assert credential_revoked.status_code == 204
            unauthenticated = await agent.get("/api/v1/governed/approval-requests")
            assert unauthenticated.status_code == 401


@pytest.mark.asyncio
async def test_agent_progress_read_is_project_scoped_and_revocable(authority_context):
    async with AsyncSessionLocal() as db:
        product = Product(name=f"progress-authority-{uuid.uuid4()}")
        db.add(product); await db.flush()
        version = ProductVersion(product_id=product.id, version="0.1.0")
        db.add(version); await db.flush()
        project = Project(name=f"progress-project-{uuid.uuid4()}", product_version_id=version.id)
        db.add(project); await db.commit()
        authority_context.update(product=product.id, version=version.id, project=project.id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=authority_context["admin_headers"]) as admin:
        credential = await admin.post("/api/v1/governed/agent-credentials", json={
            "agent_id": str(authority_context["agent"]), "label": "progress credential",
        })
        token = credential.json()["token"]
        authority_context["credential"] = uuid.UUID(credential.json()["credential_id"])
        delegation = await admin.post("/api/v1/governed/authority-delegations", json={
            "grantee_agent_id": str(authority_context["agent"]),
            "allowed_actions": ["planning.progress.view"],
            "scope_type": "project", "project_id": str(authority_context["project"]),
            "max_risk": "low",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "reason": "project progress monitoring",
        })
        assert delegation.status_code == 201, delegation.text
        delegation_id = delegation.json()["id"]
        authority_context["delegation"] = uuid.UUID(delegation_id)

        async with AsyncClient(
            transport=transport, base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as agent:
            allowed = await agent.get(f"/api/v1/projects/{authority_context['project']}/progress")
            assert allowed.status_code == 200, allowed.text
            assert allowed.json()["first_safe_action"] == "Create or activate a project pipeline"
            await admin.post(f"/api/v1/governed/authority-delegations/{delegation_id}:revoke")
            denied = await agent.get(f"/api/v1/projects/{authority_context['project']}/progress")
            assert denied.status_code == 403


@pytest.mark.asyncio
async def test_delegation_budget_limit_bounds_execution_wave_release(authority_context):
    async with AsyncSessionLocal() as db:
        product = Product(name=f"budget-authority-{uuid.uuid4()}")
        db.add(product); await db.flush()
        version = ProductVersion(product_id=product.id, version="0.1.0")
        db.add(version); await db.flush()
        project = Project(name=f"budget-project-{uuid.uuid4()}", product_version_id=version.id)
        db.add(project); await db.flush()
        plan = ProjectPlan(project_id=project.id, name="Budget plan", status="baselined")
        db.add(plan); await db.flush()
        baseline = PlanBaseline(project_plan_id=plan.id, name="Budget baseline")
        db.add(baseline); await db.flush()
        item = PlanningItem(project_id=project.id, title="Budget item", item_type="feature")
        db.add(item); await db.flush()
        task = ProjectTask(planning_item_id=item.id, title="Bounded task", description="Bounded by delegation budget", status="planned")
        db.add(task); await db.flush()
        membership = ProjectAgentMembership(project_id=project.id, agent_id=authority_context["agent"], role="developer", status="active", allowed_runtimes=["codex"])
        db.add(membership); await db.flush()
        assignment = TaskAssignment(task_id=task.id, agent_id=authority_context["agent"], membership_id=membership.id, status="active")
        db.add(assignment); await db.commit()
        authority_context.update(product=product.id, version=version.id, project=project.id)
        plan_id, baseline_id, item_id, task_id, assignment_id, membership_id = plan.id, baseline.id, item.id, task.id, assignment.id, membership.id

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test", headers=authority_context["admin_headers"]) as admin:
            credential = await admin.post("/api/v1/governed/agent-credentials", json={
                "agent_id": str(authority_context["agent"]), "label": "budget credential",
            })
            assert credential.status_code == 201, credential.text
            token = credential.json()["token"]
            authority_context["credential"] = uuid.UUID(credential.json()["credential_id"])
            delegation = await admin.post("/api/v1/governed/authority-delegations", json={
                "grantee_agent_id": str(authority_context["agent"]),
                "allowed_actions": ["planning.execution.release"],
                "scope_type": "project", "project_id": str(authority_context["project"]),
                "max_risk": "low", "budget_limit": 100,
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                "reason": "bounded wave release",
            })
            assert delegation.status_code == 201, delegation.text
            authority_context["delegation"] = uuid.UUID(delegation.json()["id"])

            over_budget = await admin.post(f"/api/v1/projects/{authority_context['project']}/execution-waves", json={
                "baseline_id": str(baseline_id), "name": "Over-budget wave", "task_ids": [str(task_id)],
                "wip_limit": 1, "budget_limit": 500, "idempotency_key": f"wave-over-{uuid.uuid4()}",
            })
            assert over_budget.status_code == 201, over_budget.text
            over_wave_id = over_budget.json()["id"]
            preflight_over = await admin.post(f"/api/v1/execution-waves/{over_wave_id}:preflight", json={})
            assert preflight_over.status_code == 200, preflight_over.text

            async with AsyncClient(transport=transport, base_url="http://test", headers={"Authorization": f"Bearer {token}"}) as agent:
                denied = await agent.post(f"/api/v1/execution-waves/{over_wave_id}:approve", json={})
                assert denied.status_code == 403, denied.text

            under_budget = await admin.post(f"/api/v1/projects/{authority_context['project']}/execution-waves", json={
                "baseline_id": str(baseline_id), "name": "In-budget wave", "task_ids": [str(task_id)],
                "wip_limit": 1, "budget_limit": 50, "idempotency_key": f"wave-under-{uuid.uuid4()}",
            })
            assert under_budget.status_code == 201, under_budget.text
            under_wave_id = under_budget.json()["id"]
            preflight_under = await admin.post(f"/api/v1/execution-waves/{under_wave_id}:preflight", json={})
            assert preflight_under.status_code == 200, preflight_under.text

            async with AsyncClient(transport=transport, base_url="http://test", headers={"Authorization": f"Bearer {token}"}) as agent:
                allowed = await agent.post(f"/api/v1/execution-waves/{under_wave_id}:approve", json={})
                assert allowed.status_code == 200, allowed.text
                assert allowed.json()["status"] == "approved"

        async with AsyncSessionLocal() as db:
            approved_wave = await db.get(ExecutionWave, uuid.UUID(under_wave_id))
            assert approved_wave.delegation_id == authority_context["delegation"]
    finally:
        async with AsyncSessionLocal() as db:
            wave_ids = list((await db.execute(
                ExecutionWave.__table__.select().with_only_columns(ExecutionWave.id).where(ExecutionWave.project_id == project.id)
            )).scalars())
            if wave_ids:
                await db.execute(delete(ExecutionWaveTask).where(ExecutionWaveTask.execution_wave_id.in_(wave_ids)))
                await db.execute(delete(ExecutionWave).where(ExecutionWave.id.in_(wave_ids)))
            await db.execute(delete(TaskAssignment).where(TaskAssignment.id == assignment_id))
            await db.execute(delete(ProjectAgentMembership).where(ProjectAgentMembership.id == membership_id))
            await db.execute(delete(ProjectTask).where(ProjectTask.id == task_id))
            await db.execute(delete(PlanningItem).where(PlanningItem.id == item_id))
            await db.execute(delete(PlanBaseline).where(PlanBaseline.id == baseline_id))
            await db.execute(delete(ProjectPlan).where(ProjectPlan.id == plan_id))
            await db.commit()
