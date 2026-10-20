"""End-to-end integration test validating the entire Software Factory pipeline from Conception to Version Closure."""
import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.backlog import PlanningItem
from app.db.models.product import Product, ProductVersion
from app.db.models.project import Project
from app.db.models.system_scope import (
    ProductConcept,
    ProjectScope,
    SystemBlueprint,
    SystemElement,
)
from app.db.models.task import ProjectTask, TaskAssignment, TaskExecution
from app.db.models.user import User
from app.core.security import create_access_token, hash_password
from app.main import app


@pytest_asyncio.fixture
async def factory_actor():
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        user = User(username=f"factory-agent-{suffix}", hashed_password=hash_password("secret"), is_admin=True)
        agent = Agent(name=f"Executor Agent {suffix}", profile_slug=f"exec-{suffix}", is_active=True)
        db.add_all([user, agent])
        await db.commit()
        await db.refresh(user)
        await db.refresh(agent)
        data = {
            "user_id": user.id,
            "agent_id": str(agent.id),
            "headers": {"Authorization": f"Bearer {create_access_token(user.username)}"},
            "agent_name": agent.name,
            "suffix": suffix,
        }
    yield data
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User).where(User.id == data["user_id"]))
        await db.execute(delete(Agent).where(Agent.id == uuid.UUID(data["agent_id"])))
        await db.commit()


@pytest_asyncio.fixture
async def api_client(factory_actor):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=factory_actor["headers"]
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_full_software_factory_pipeline_lifecycle(api_client, factory_actor):
    """Executes the complete Software Factory lifecycle:
    1. Phase 1: Conception (Idea creation + documentation markdown upload)
    2. Phase 2: Designer & System Map (Screens, HTML prototypes & ERD database derivation)
    3. Delivery Authorization: Create Project and Product Version
    4. Phase 3 & 4: Planning Item & Project Execution Tasks
    5. Phase 5: Governance Gate (Assign executor agent and release planning)
    6. Phase 6: Execution (Task in_progress -> verified -> done)
    7. Phase 7: Version Closure (Publish version & lock project permanently)
    """
    suffix = factory_actor["suffix"]
    created_product_ids = []
    created_project_ids = []

    try:
        # -------------------------------------------------------------
        # STEP 1: CONCEPTION & CONTEXT
        # -------------------------------------------------------------
        idea_payload = {
            "name": f"Factory E2E App {suffix}",
            "problem_statement": "Automate complete software lifecycle",
            "vision": "Autonomous factory pipeline",
            "scope_summary": "Full stack architecture with web and backend",
            "project_description": "Production grade service",
            "working_directory_path": "/root/project/e2e-app",
            "priority": "high",
        }
        resp = await api_client.post("/api/v1/conception/ideas", json=idea_payload)
        assert resp.status_code == 201, resp.text
        idea_data = resp.json()
        product_id = idea_data["product_id"]
        concept_id = idea_data["concept"]["id"]
        created_product_ids.append(product_id)

        # Attach PRD document
        doc_resp = await api_client.put(
            f"/api/v1/product-concepts/{concept_id}/documents/PRD.md",
            json={"content": "# PRD E2E\n\nRequirements specification.", "category": "prd"},
        )
        assert doc_resp.status_code == 200, doc_resp.text

        # -------------------------------------------------------------
        # STEP 2: AUTHORIZE PROJECT DELIVERY (CREATION)
        # -------------------------------------------------------------
        auth_payload = {
            "version": "1.0.0",
            "projects": [
                {
                    "project_name": f"Core Service {suffix}",
                    "solution_type": "web_app",
                    "project_type": "creation",
                    "working_directory_path": "/root/project/e2e-app",
                }
            ],
        }
        auth_resp = await api_client.post(
            f"/api/v1/product-concepts/{concept_id}:authorize-delivery-planning",
            json=auth_payload,
        )
        assert auth_resp.status_code == 200, auth_resp.text
        auth_data = auth_resp.json()
        project_id = auth_data["projects"][0]["project_id"]
        project_scope_id = auth_data["projects"][0]["project_scope_id"]
        version_id = auth_data["product_version_id"]
        created_project_ids.append(project_id)

        # -------------------------------------------------------------
        # STEP 3: SYSTEM MAP, SCREENS, HTML PROTOTYPE & DATABASE DERIVATION
        # -------------------------------------------------------------
        screen_resp = await api_client.post(
            f"/api/v1/project-scopes/{project_scope_id}/screens",
            json={
                "name": "Dashboard Screen",
                "description": "Main KPI dashboard",
                "spec": {
                    "route": "/dashboard",
                    "attributes": [{"name": "title", "type": "string"}, {"name": "amount", "type": "number"}],
                },
            },
        )
        assert screen_resp.status_code == 201, screen_resp.text
        screen_id = screen_resp.json()["element"]["id"]

        # Save HTML prototype / business rule
        proto_resp = await api_client.put(
            f"/api/v1/project-scopes/{project_scope_id}/screens/{screen_id}/business-rule",
            json={"content": "<div class='dashboard'><h1>Analytics</h1></div>"},
        )
        assert proto_resp.status_code == 200, proto_resp.text

        # Derive database tables from screens
        db_resp = await api_client.post(f"/api/v1/project-scopes/{project_scope_id}/derive-database")
        assert db_resp.status_code == 200, db_resp.text
        assert db_resp.json()["tables_created"] >= 1

        # -------------------------------------------------------------
        # STEP 4: PLANNING BACKLOG & EXECUTION TASKS
        # -------------------------------------------------------------
        plan_resp = await api_client.post(
            "/api/v1/planning-items",
            json={
                "project_id": project_id,
                "title": "Implement Analytics KPI Dashboard",
                "item_type": "feature",
                "description": "Build dashboard with responsive charts",
                "priority": "high",
            },
        )
        assert plan_resp.status_code == 201, plan_resp.text
        plan_id = plan_resp.json()["id"]

        task_resp = await api_client.post(
            "/api/v1/tasks",
            json={
                "planning_item_id": plan_id,
                "title": "Develop UI Components and Chart Integration",
                "description": "Wire dashboard components with backend endpoint",
                "priority": "high",
            },
        )
        assert task_resp.status_code == 201, task_resp.text
        task_id = task_resp.json()["id"]

        # -------------------------------------------------------------
        # STEP 5: GOVERNANCE GATE - RELEASE PLANNING TO EXECUTION
        # -------------------------------------------------------------
        # 5a. Assign Agent to Task
        assign_resp = await api_client.post(
            f"/api/v1/tasks/{task_id}/assignments",
            json={
                "task_id": task_id,
                "agent_id": factory_actor["agent_id"],
            },
        )
        assert assign_resp.status_code == 201, assign_resp.text

        # 5b. Advance Planning Item to in_progress
        gate_resp = await api_client.put(
            f"/api/v1/planning-items/{plan_id}",
            json={"status": "in_progress"},
        )
        assert gate_resp.status_code == 200, gate_resp.text
        assert gate_resp.json()["status"] == "in_progress"

        # -------------------------------------------------------------
        # STEP 6: EXECUTION & COMPLETION
        # -------------------------------------------------------------
        # 6a. Mark task in progress
        await api_client.patch(f"/api/v1/tasks/{task_id}", json={"status": "in_progress"})

        # 6b. Add verified task execution evidence
        exec_resp = await api_client.post(
            f"/api/v1/tasks/{task_id}/executions",
            json={
                "status": "verified",
                "outcome_summary": "All dashboard widgets verified and tests passing",
                "evidence_ref": "test://dashboard-validation-ok",
            },
        )
        assert exec_resp.status_code == 201, exec_resp.text

        # 6c. Mark task done and planning done
        task_done_resp = await api_client.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"})
        assert task_done_resp.status_code == 200, task_done_resp.text
        assert task_done_resp.json()["status"] == "done"

        plan_done_resp = await api_client.put(f"/api/v1/planning-items/{plan_id}", json={"status": "done"})
        assert plan_done_resp.status_code == 200, plan_done_resp.text
        assert plan_done_resp.json()["status"] == "done"

        # -------------------------------------------------------------
        # STEP 7: VERSION CLOSURE & PRODUCTION PUBLISHING
        # -------------------------------------------------------------
        # 7a. Update Release Notes
        await api_client.put(
            f"/api/v1/products/versions/{version_id}",
            json={"release_notes": "Official v1.0.0 release with full Analytics Dashboard."},
        )

        # 7b. Publish version & seal project
        pub_resp = await api_client.post(f"/api/v1/products/versions/{version_id}:publish")
        assert pub_resp.status_code == 200, pub_resp.text
        pub_data = pub_resp.json()
        assert pub_data["status"] == "published"
        assert pub_data["release_notes"] == "Official v1.0.0 release with full Analytics Dashboard."

    finally:
        # Cleanup
        async with AsyncSessionLocal() as db:
            for proj_id in created_project_ids:
                proj_uuid = uuid.UUID(proj_id)
                plan_ids = list((await db.execute(select(PlanningItem.id).where(PlanningItem.project_id == proj_uuid))).scalars())
                if plan_ids:
                    task_ids = list((await db.execute(select(ProjectTask.id).where(ProjectTask.planning_item_id.in_(plan_ids)))).scalars())
                    if task_ids:
                        await db.execute(delete(TaskAssignment).where(TaskAssignment.task_id.in_(task_ids)))
                        await db.execute(delete(TaskExecution).where(TaskExecution.task_id.in_(task_ids)))
                    await db.execute(delete(ProjectTask).where(ProjectTask.planning_item_id.in_(plan_ids)))
                await db.execute(delete(PlanningItem).where(PlanningItem.project_id == proj_uuid))
                await db.execute(delete(ProjectScope).where(ProjectScope.project_id == proj_uuid))
                await db.execute(delete(Project).where(Project.id == proj_uuid))

            for prod_id in created_product_ids:
                prod_uuid = uuid.UUID(prod_id)
                await db.execute(delete(ProductVersion).where(ProductVersion.product_id == prod_uuid))
                await db.execute(delete(ProductConcept).where(ProductConcept.product_id == prod_uuid))
                await db.execute(delete(SystemElement).where(SystemElement.product_id == prod_uuid))
                await db.execute(delete(SystemBlueprint).where(SystemBlueprint.product_id == prod_uuid))
                await db.execute(delete(Product).where(Product.id == prod_uuid))

            await db.commit()
