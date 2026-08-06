"""Integration tests for project agents, ForgeRouter profiles, and loops."""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.backlog import PlanningItem
from app.db.models.orchestration import (
    AgentRuntimeProfile,
    ProjectAgentMembership,
    ProjectLoopPolicy,
    TaskExecutionReview,
)
from app.db.models.product import Product, ProductVersion
from app.db.models.project import Project
from app.db.models.task import ProjectTask, TaskAssignment, TaskExecution
from app.main import app
from app.core.secrets import encrypt_secret


@pytest_asyncio.fixture
async def client(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as ac:
        yield ac


@pytest_asyncio.fixture
async def orchestration_context():
    async with AsyncSessionLocal() as db:
        product = Product(name=f"Orchestration Product {uuid.uuid4()}")
        producer = Agent(name=f"producer-{uuid.uuid4()}", agent_type="executor", forgerouter_api_key_encrypted=encrypt_secret("producer-test-key"))
        reviewer = Agent(name=f"reviewer-{uuid.uuid4()}", agent_type="executor", forgerouter_api_key_encrypted=encrypt_secret("reviewer-test-key"))
        db.add_all([product, producer, reviewer])
        await db.flush()
        version = ProductVersion(product_id=product.id, version="0.1.0")
        db.add(version)
        await db.flush()
        project = Project(
            name=f"Orchestration Project {uuid.uuid4()}",
            product_version_id=version.id,
            working_directory_path="/tmp",
        )
        db.add(project)
        await db.flush()
        item = PlanningItem(
            title="Automated loop item", item_type="feature", project_id=project.id
        )
        db.add(item)
        await db.commit()
        ids = {
            "product": product.id,
            "version": version.id,
            "project": project.id,
            "item": item.id,
            "producer": producer.id,
            "reviewer": reviewer.id,
        }

    yield ids

    async with AsyncSessionLocal() as db:
        task_ids = list(
            (await db.execute(
                ProjectTask.__table__.select().with_only_columns(ProjectTask.id).where(
                    ProjectTask.planning_item_id == ids["item"]
                )
            )).scalars().all()
        )
        if task_ids:
            execution_ids = list(
                (await db.execute(
                    TaskExecution.__table__.select().with_only_columns(TaskExecution.id).where(
                        TaskExecution.task_id.in_(task_ids)
                    )
                )).scalars().all()
            )
            if execution_ids:
                await db.execute(delete(TaskExecutionReview).where(TaskExecutionReview.execution_id.in_(execution_ids)))
            await db.execute(delete(TaskExecution).where(TaskExecution.task_id.in_(task_ids)))
            await db.execute(delete(TaskAssignment).where(TaskAssignment.task_id.in_(task_ids)))
            await db.execute(delete(ProjectTask).where(ProjectTask.id.in_(task_ids)))
        await db.execute(delete(ProjectLoopPolicy).where(ProjectLoopPolicy.project_id == ids["project"]))
        await db.execute(
            delete(ProjectAgentMembership).where(ProjectAgentMembership.project_id == ids["project"])
        )
        await db.execute(
            delete(AgentRuntimeProfile).where(
                AgentRuntimeProfile.agent_id.in_([ids["producer"], ids["reviewer"]])
            )
        )
        await db.execute(delete(PlanningItem).where(PlanningItem.id == ids["item"]))
        await db.execute(delete(Project).where(Project.id == ids["project"]))
        await db.execute(delete(ProductVersion).where(ProductVersion.id == ids["version"]))
        await db.execute(delete(Product).where(Product.id == ids["product"]))
        await db.execute(delete(Agent).where(Agent.id.in_([ids["producer"], ids["reviewer"]])))
        await db.commit()


async def _create_profile(client, agent_id, name, purpose, intelligence):
    routing_group = "code" if purpose == "implementation" else "reasoning"
    response = await client.post(
        "/api/v1/orchestration/runtime-profiles",
        json={
            "agent_id": str(agent_id),
            "name": name,
            "runtime_type": "codex" if purpose == "implementation" else "claude",
            "model_ref": "forgerouter/auto",
            "routing_group": routing_group,
            "purpose": purpose,
            "intelligence_level": intelligence,
        },
    )
    assert response.status_code == 201, response.text
    profile = response.json()
    assert profile["routing_group"] == routing_group
    return profile


async def _create_membership(client, project_id, agent_id, role, can_review=False):
    response = await client.post(
        f"/api/v1/orchestration/projects/{project_id}/memberships",
        json={
            "agent_id": str(agent_id),
            "role": role,
            "allowed_runtimes": ["claude", "codex", "antigravity"],
            "can_review": can_review,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_project_team_runtime_profiles_and_bounded_loop(client, orchestration_context):
    ctx = orchestration_context
    producer_profile = await _create_profile(
        client, ctx["producer"], "Fast implementation", "implementation", 2
    )
    reviewer_profile = await _create_profile(client, ctx["reviewer"], "Deep review", "review", 5)
    producer = await _create_membership(client, ctx["project"], ctx["producer"], "developer")
    reviewer = await _create_membership(
        client, ctx["project"], ctx["reviewer"], "reviewer", can_review=True
    )

    policy_response = await client.post(
        f"/api/v1/orchestration/projects/{ctx['project']}/loop-policies",
        json={
            "name": "implementation quality loop",
            "phase": "implementation",
            "producer_membership_id": producer["id"],
            "reviewer_membership_id": reviewer["id"],
            "producer_runtime_profile_id": producer_profile["id"],
            "reviewer_runtime_profile_id": reviewer_profile["id"],
            "max_iterations": 3,
            "min_review_score": 85,
        },
    )
    assert policy_response.status_code == 201, policy_response.text
    assert policy_response.json()["max_iterations"] == 3

    invalid = await client.post(
        f"/api/v1/orchestration/projects/{ctx['project']}/loop-policies",
        json={
            "name": "self review",
            "phase": "implementation",
            "producer_membership_id": producer["id"],
            "reviewer_membership_id": producer["id"],
            "producer_runtime_profile_id": producer_profile["id"],
            "reviewer_runtime_profile_id": producer_profile["id"],
        },
    )
    assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_list_agent_memberships_is_the_inverse_of_project_team(client, orchestration_context):
    """See list_agent_memberships (2026-08-05, Software Factory visibility
    fix) -- the agent detail page's "Projetos ativos" section reads this."""
    ctx = orchestration_context
    membership = await _create_membership(client, ctx["project"], ctx["producer"], "developer")

    resp = await client.get(f"/api/v1/orchestration/agents/{ctx['producer']}/memberships")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert {r["id"] for r in rows} == {membership["id"]}
    assert rows[0]["project_id"] == str(ctx["project"])

    empty_resp = await client.get(f"/api/v1/orchestration/agents/{ctx['reviewer']}/memberships")
    assert empty_resp.status_code == 200
    assert empty_resp.json() == []


@pytest.mark.asyncio
async def test_assignment_execution_and_independent_review_are_traceable(
    client, orchestration_context
):
    ctx = orchestration_context
    producer_profile = await _create_profile(
        client, ctx["producer"], "Codex implementation", "implementation", 3
    )
    await _create_profile(client, ctx["reviewer"], "Claude review", "review", 5)
    producer = await _create_membership(client, ctx["project"], ctx["producer"], "developer")
    reviewer = await _create_membership(
        client, ctx["project"], ctx["reviewer"], "reviewer", can_review=True
    )

    task_response = await client.post(
        "/api/v1/tasks",
        json={
            "planning_item_id": str(ctx["item"]),
            "title": "Implement through governed CLI",
            "task_type": "feature",
        },
    )
    assert task_response.status_code == 201, task_response.text
    task = task_response.json()

    eligible = await client.get(
        f"/api/v1/orchestration/tasks/{task['id']}/eligible-memberships"
    )
    assert eligible.status_code == 200, eligible.text
    assert {row["membership"]["id"] for row in eligible.json() if row["eligible"]} == {
        producer["id"], reviewer["id"]
    }

    assignment_response = await client.post(
        f"/api/v1/tasks/{task['id']}/assignments",
        json={
            "task_id": task["id"],
            "agent_id": str(ctx["producer"]),
            "membership_id": producer["id"],
        },
    )
    assert assignment_response.status_code == 201, assignment_response.text
    assignment = assignment_response.json()

    execution_response = await client.post(
        f"/api/v1/tasks/{task['id']}/executions",
        json={
            "assignment_id": assignment["id"],
            "runtime_profile_id": producer_profile["id"],
            "runtime_type": "codex",
            "status": "completed",
            "evidence_ref": "test://execution-evidence",
        },
    )
    assert execution_response.status_code == 201, execution_response.text
    execution = execution_response.json()
    assert execution["runtime_type"] == "codex"
    assert execution["assignment_id"] == assignment["id"]

    self_review = await client.post(
        f"/api/v1/orchestration/executions/{execution['id']}/reviews",
        json={
            "reviewer_membership_id": producer["id"],
            "status": "approved",
            "feedback": "self review is forbidden",
        },
    )
    assert self_review.status_code == 409

    review_response = await client.post(
        f"/api/v1/orchestration/executions/{execution['id']}/reviews",
        json={
            "reviewer_membership_id": reviewer["id"],
            "status": "approved",
            "score": 92,
            "feedback": "Acceptance criteria and tests verified.",
            "evidence_ref": "test://review-evidence",
        },
    )
    assert review_response.status_code == 201, review_response.text
    assert review_response.json()["score"] == 92
