"""ExecutionWave and immutable Work Package integration coverage."""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.backlog import PlanningItem
from app.db.models.execution import ExecutionWave, ExecutionWaveTask, ExecutionWorkPackage
from app.db.models.orchestration import AgentRuntimeProfile, ProjectAgentMembership
from app.db.models.product import Product, ProductVersion
from app.db.models.project import PlanBaseline, Project, ProjectPlan
from app.db.models.task import ProjectTask, TaskAssignment
from app.core.security import create_access_token, hash_password
from app.db.models.user import User
from app.main import app


@pytest_asyncio.fixture
async def runtime_context():
    async with AsyncSessionLocal() as db:
        product = Product(name=f"Runner product {uuid.uuid4()}")
        agent = Agent(name=f"runner-agent-{uuid.uuid4()}", agent_type="executor")
        admin = User(username=f"runner-admin-{uuid.uuid4()}", hashed_password=hash_password("test"), is_admin=True)
        db.add_all([product, agent, admin]); await db.flush()
        version = ProductVersion(product_id=product.id, version="1.0.0"); db.add(version); await db.flush()
        project = Project(name=f"Runner project {uuid.uuid4()}", product_version_id=version.id, working_directory_path="/tmp"); db.add(project); await db.flush()
        plan = ProjectPlan(project_id=project.id, name="Authorized plan", status="baselined"); db.add(plan); await db.flush()
        baseline = PlanBaseline(project_plan_id=plan.id, name="Runner baseline"); db.add(baseline)
        item = PlanningItem(project_id=project.id, title="Runner item", item_type="feature"); db.add(item); await db.flush()
        task = ProjectTask(planning_item_id=item.id, title="Execute safely", description="Implement the bounded change", status="planned"); db.add(task)
        membership = ProjectAgentMembership(project_id=project.id, agent_id=agent.id, role="developer", status="active", allowed_runtimes=["codex"]); db.add(membership)
        profile = AgentRuntimeProfile(agent_id=agent.id, name="Codex runner", runtime_type="codex", purpose="implementation", model_ref="forgerouter/auto"); db.add(profile); await db.flush()
        assignment = TaskAssignment(task_id=task.id, agent_id=agent.id, membership_id=membership.id, status="active"); db.add(assignment); await db.commit()
        ids = {"product": product.id, "version": version.id, "project": project.id, "plan": plan.id, "baseline": baseline.id, "item": item.id, "task": task.id, "agent": agent.id, "admin": admin.id, "admin_username": admin.username, "membership": membership.id, "profile": profile.id, "assignment": assignment.id}
    yield ids
    async with AsyncSessionLocal() as db:
        wave_ids = list((await db.execute(ExecutionWave.__table__.select().with_only_columns(ExecutionWave.id).where(ExecutionWave.project_id == ids["project"]))).scalars())
        if wave_ids:
            await db.execute(delete(ExecutionWorkPackage).where(ExecutionWorkPackage.execution_wave_id.in_(wave_ids)))
            await db.execute(delete(ExecutionWaveTask).where(ExecutionWaveTask.execution_wave_id.in_(wave_ids)))
            await db.execute(delete(ExecutionWave).where(ExecutionWave.id.in_(wave_ids)))
        await db.execute(delete(TaskAssignment).where(TaskAssignment.id == ids["assignment"]))
        await db.execute(delete(ProjectTask).where(ProjectTask.id == ids["task"]))
        await db.execute(delete(AgentRuntimeProfile).where(AgentRuntimeProfile.id == ids["profile"]))
        await db.execute(delete(ProjectAgentMembership).where(ProjectAgentMembership.id == ids["membership"]))
        await db.execute(delete(PlanningItem).where(PlanningItem.id == ids["item"]))
        await db.execute(delete(PlanBaseline).where(PlanBaseline.id == ids["baseline"]))
        await db.execute(delete(ProjectPlan).where(ProjectPlan.id == ids["plan"]))
        await db.execute(delete(Project).where(Project.id == ids["project"]))
        await db.execute(delete(ProductVersion).where(ProductVersion.id == ids["version"]))
        await db.execute(delete(Product).where(Product.id == ids["product"]))
        await db.execute(delete(Agent).where(Agent.id == ids["agent"]))
        await db.execute(delete(User).where(User.id == ids["admin"])); await db.commit()


@pytest.mark.asyncio
async def test_wave_release_and_immutable_package(runtime_context):
    ctx = runtime_context
    headers = {"Authorization": f"Bearer {create_access_token(ctx['admin_username'])}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as client:
        created = await client.post(f"/api/v1/projects/{ctx['project']}/execution-waves", json={"baseline_id": str(ctx["baseline"]), "name": "Safe wave", "task_ids": [str(ctx["task"])], "wip_limit": 1, "idempotency_key": f"wave-{uuid.uuid4()}"})
        assert created.status_code == 201, created.text
        wave = created.json(); assert wave["status"] == "draft"
        preflight = await client.post(f"/api/v1/execution-waves/{wave['id']}:preflight", json={})
        assert preflight.status_code == 200, preflight.text
        assert preflight.json()["eligible"] is True
        approved = await client.post(f"/api/v1/execution-waves/{wave['id']}:approve", json={})
        assert approved.status_code == 200, approved.text
        activated = await client.post(f"/api/v1/execution-waves/{wave['id']}:activate", json={})
        assert activated.status_code == 200, activated.text
        package = await client.post(f"/api/v1/execution-waves/{wave['id']}/tasks/{ctx['task']}/work-packages", json={"assignment_id": str(ctx["assignment"]), "runtime_profile_id": str(ctx["profile"]), "allowed_paths": ["backend/app"], "acceptance_criteria": ["Command is governed"], "definition_of_done": ["Tests pass"], "idempotency_key": f"package-{uuid.uuid4()}"})
        assert package.status_code == 201, package.text
        body = package.json(); assert body["status"] == "validated"; assert len(body["payload_hash"]) == 64
        issued = await client.post(f"/api/v1/work-packages/{body['id']}:issue", json={})
        assert issued.status_code == 200, issued.text
        assert issued.json()["status"] == "issued"
