"""Version closure rechecks delivery proof, including change-request work."""
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.backlog import PlanningItem
from app.db.models.orchestration import ProjectAgentMembership, TaskExecutionReview
from app.db.models.product import ProductVersion
from app.db.models.project import ChangeRequest, Project
from app.db.models.service_line import ServiceLine
from app.db.models.task import ProjectTask, TaskAssignment, TaskExecution
from app.main import app


@pytest_asyncio.fixture(params=["software", "service"])
async def delivery(request, auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=auth_headers) as client:
        response = await client.post("/api/v1/products", json={
            "name": f"Qualified closure {uuid.uuid4()}", "kind": request.param,
        })
        assert response.status_code == 201, response.text
        product_id = uuid.UUID(response.json()["id"])
        version_id = uuid.UUID(response.json()["versions"][0]["id"])
        async with AsyncSessionLocal() as db:
            line = await db.scalar(select(ServiceLine).where(ServiceLine.slug == (
                "software" if request.param == "software" else "suporte")))
            project = Project(name="Approved delivery", product_version_id=version_id,
                service_line_id=line.id, status="active")
            executor = Agent(name=f"Closure executor {uuid.uuid4()}")
            reviewer = Agent(name=f"Closure reviewer {uuid.uuid4()}")
            db.add_all([project, executor, reviewer])
            await db.flush()
            item = PlanningItem(project_id=project.id, title="Approved delivery obligation", item_type="feature")
            membership = ProjectAgentMembership(project_id=project.id, agent_id=reviewer.id,
                role="reviewer", can_review=True)
            db.add_all([item, membership])
            await db.flush()
            task = ProjectTask(planning_item_id=item.id, title="Delivery accepted by independent review", status="done")
            db.add(task)
            await db.flush()
            assignment = TaskAssignment(task_id=task.id, agent_id=executor.id)
            db.add(assignment)
            await db.flush()
            execution = TaskExecution(task_id=task.id, assignment_id=assignment.id, status="verified",
                evidence_ref=f"db:planning_item:{item.id}", attempt_number=1)
            db.add(execution)
            await db.flush()
            db.add(TaskExecutionReview(execution_id=execution.id, reviewer_membership_id=membership.id,
                status="approved", feedback="Approved obligation checked", decided_at=datetime.now(timezone.utc)))
            await db.commit()
            data = dict(client=client, product_id=product_id, version_id=version_id, project_id=project.id,
                task_id=task.id, execution_id=execution.id, membership_id=membership.id,
                agent_ids=[executor.id, reviewer.id], item_id=item.id)
        try:
            yield data
        finally:
            response = await client.delete(f"/api/v1/products/{product_id}")
            assert response.status_code == 204, response.text
            async with AsyncSessionLocal() as db:
                await db.execute(delete(Agent).where(Agent.id.in_(data["agent_ids"])))
                await db.commit()


async def test_open_change_request_task_blocks_exact_version_closure(delivery):
    async with AsyncSessionLocal() as db:
        change = ChangeRequest(project_id=delivery["project_id"], title="Approved corrective scope", status="approved")
        db.add(change)
        await db.flush()
        task = ProjectTask(change_request_id=change.id, title="Unfinished corrective obligation")
        db.add(task)
        await db.commit()
        task_id = task.id
    response = await delivery["client"].post(f'/api/v1/products/versions/{delivery["version_id"]}:publish')
    assert response.status_code == 409, response.text
    assert [row["task_id"] for row in response.json()["detail"]["blocking"]] == [str(task_id)]
    assert (await delivery["client"].get(f'/api/v1/products/versions/{delivery["version_id"]}')).json()["status"] == "planned"


@pytest.mark.parametrize("invalid", ["missing_execution", "stale_evidence", "revoked_reviewer"])
async def test_done_label_cannot_replace_current_delivery_proof(delivery, invalid):
    async with AsyncSessionLocal() as db:
        if invalid == "missing_execution":
            await db.execute(delete(TaskExecutionReview).where(TaskExecutionReview.execution_id == delivery["execution_id"]))
            await db.execute(delete(TaskExecution).where(TaskExecution.id == delivery["execution_id"]))
        elif invalid == "stale_evidence":
            execution = await db.get(TaskExecution, delivery["execution_id"])
            execution.evidence_ref = f"db:planning_item:{uuid.uuid4()}"
        else:
            membership = await db.get(ProjectAgentMembership, delivery["membership_id"])
            membership.can_review = False
        await db.commit()
    response = await delivery["client"].post(f'/api/v1/products/versions/{delivery["version_id"]}:publish')
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["task_id"] == str(delivery["task_id"])
    async with AsyncSessionLocal() as db:
        assert (await db.get(Project, delivery["project_id"])).status == "active"


async def test_verified_reviewed_delivery_closes_only_its_exact_version(delivery):
    async with AsyncSessionLocal() as db:
        other = ProductVersion(product_id=delivery["product_id"], version="next-cycle")
        db.add(other)
        await db.flush()
        project = Project(name="Next obligation", product_version_id=other.id)
        db.add(project)
        await db.flush()
        change = ChangeRequest(project_id=project.id, title="Unfinished next-cycle scope", status="approved")
        db.add(change)
        await db.flush()
        db.add(ProjectTask(change_request_id=change.id, title="Future obligation"))
        await db.commit()
        other_id, other_project_id = other.id, project.id
    response = await delivery["client"].post(f'/api/v1/products/versions/{delivery["version_id"]}:publish')
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "published"
    async with AsyncSessionLocal() as db:
        assert (await db.get(Project, delivery["project_id"])).status == "completed"
        assert (await db.get(ProductVersion, other_id)).status == "planned"
        assert (await db.get(Project, other_project_id)).status == "planned"


async def test_generic_version_update_cannot_bypass_closure(delivery):
    async with AsyncSessionLocal() as db:
        (await db.get(ProjectTask, delivery["task_id"])).status = "in_progress"
        await db.commit()
    response = await delivery["client"].put(f'/api/v1/products/versions/{delivery["version_id"]}',
        json={"status": "published"})
    assert response.status_code == 409, response.text


async def test_new_version_cannot_start_published_without_delivery_proof(delivery):
    response = await delivery["client"].post(f'/api/v1/products/{delivery["product_id"]}/versions',
        json={"version": "unverified", "status": "published"})
    assert response.status_code == 409, response.text


async def test_new_product_cannot_start_published_without_delivery_proof(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=auth_headers) as client:
        response = await client.post("/api/v1/products", json={"name": f"Bypassed closure {uuid.uuid4()}",
            "initial_version": {"version": "unverified", "status": "published"}})
        try:
            assert response.status_code == 409, response.text
        finally:
            if response.status_code == 201:
                await client.delete(f'/api/v1/products/{response.json()["id"]}')
