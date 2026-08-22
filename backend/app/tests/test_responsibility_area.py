"""Layered task-execution governance, Fase 2 (plan: resilient-twirling-
blossom): ResponsibilityArea maps a task_type (optionally scoped to a
project) to a default owner agent, consulted by _dispatch_task_by_id
(task.py) only as a fallback when a task has no explicit target_agent_id
and no active TaskAssignment.
"""
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db.base import AsyncSessionLocal, engine
from app.db.models.agent import Agent
from app.db.models.backlog import PlanningItem
from app.db.models.product import Product, ProductVersion
from app.db.models.project import Project
from app.db.models.task import ProjectTask
from app.main import app


@pytest_asyncio.fixture
async def client(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as ac:
        yield ac


@pytest_asyncio.fixture
async def world():
    """Product -> ProductVersion -> Project -> PlanningItem -> ProjectTask,
    plus two distinct agents, to exercise global-default vs. project-scoped
    resolution."""
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        product = Product(name=f"Responsibility Test Product {suffix}")
        session.add(product)
        await session.flush()
        version = ProductVersion(product_id=product.id, version="0.1.0")
        session.add(version)
        await session.flush()
        project = Project(name=f"Responsibility Test Project {suffix}", product_version_id=version.id)
        session.add(project)
        await session.flush()
        item = PlanningItem(
            title="Responsibility test planning item", item_type="feature", project_id=project.id
        )
        session.add(item)
        await session.flush()
        task = ProjectTask(title="Responsibility test task", planning_item_id=item.id, task_type="bug")
        session.add(task)
        global_agent = Agent(
            name=f"Global Owner {suffix}", agent_type="executor", runtime_type="claude"
        )
        scoped_agent = Agent(
            name=f"Scoped Owner {suffix}", agent_type="executor", runtime_type="claude"
        )
        session.add_all([global_agent, scoped_agent])
        await session.commit()
        ids = {
            "product_id": product.id,
            "version_id": version.id,
            "project_id": project.id,
            "item_id": item.id,
            "task_id": task.id,
            "global_agent_id": global_agent.id,
            "scoped_agent_id": scoped_agent.id,
        }

    yield ids

    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM company.agent_demands WHERE origin_id = :id"), {"id": ids["task_id"]}
        )
        await conn.execute(
            text("DELETE FROM company.responsibility_areas WHERE project_id = :id OR project_id IS NULL"),
            {"id": ids["project_id"]},
        )
        await conn.execute(
            text("DELETE FROM company.task_executions WHERE task_id = :id"), {"id": ids["task_id"]}
        )
        await conn.execute(
            text("DELETE FROM company.project_tasks WHERE id = :id"), {"id": ids["task_id"]}
        )
        await conn.execute(
            text("DELETE FROM company.agents WHERE id = ANY(:ids)"),
            {"ids": [ids["global_agent_id"], ids["scoped_agent_id"]]},
        )
        await conn.execute(
            text("DELETE FROM company.planning_items WHERE id = :id"), {"id": ids["item_id"]}
        )
        await conn.execute(text("DELETE FROM company.projects WHERE id = :id"), {"id": ids["project_id"]})
        await conn.execute(
            text("DELETE FROM company.product_versions WHERE id = :id"), {"id": ids["version_id"]}
        )
        await conn.execute(text("DELETE FROM company.products WHERE id = :id"), {"id": ids["product_id"]})


async def test_create_and_list_global_default(client, world):
    resp = await client.post(
        "/api/v1/responsibility-areas",
        json={"task_type": "bug", "owner_agent_id": str(world["global_agent_id"])},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["project_id"] is None

    listed = await client.get("/api/v1/responsibility-areas")
    assert listed.status_code == 200
    assert any(a["task_type"] == "bug" and a["project_id"] is None for a in listed.json())


async def test_duplicate_global_default_rejected(client, world):
    payload = {"task_type": "bug", "owner_agent_id": str(world["global_agent_id"])}
    first = await client.post("/api/v1/responsibility-areas", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/v1/responsibility-areas", json=payload)
    assert second.status_code == 409, second.text


async def test_invalid_task_type_rejected(client, world):
    resp = await client.post(
        "/api/v1/responsibility-areas",
        json={"task_type": "not_a_real_type", "owner_agent_id": str(world["global_agent_id"])},
    )
    assert resp.status_code == 422


async def test_unknown_owner_agent_rejected(client, world):
    resp = await client.post(
        "/api/v1/responsibility-areas",
        json={"task_type": "bug", "owner_agent_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 400


async def test_update_and_delete(client, world):
    created = await client.post(
        "/api/v1/responsibility-areas",
        json={"task_type": "bug", "owner_agent_id": str(world["global_agent_id"])},
    )
    area_id = created.json()["id"]

    updated = await client.patch(
        f"/api/v1/responsibility-areas/{area_id}",
        json={"owner_agent_id": str(world["scoped_agent_id"])},
    )
    assert updated.status_code == 200
    assert updated.json()["owner_agent_id"] == str(world["scoped_agent_id"])

    deleted = await client.delete(f"/api/v1/responsibility-areas/{area_id}")
    assert deleted.status_code == 204

    listed = await client.get("/api/v1/responsibility-areas")
    assert all(a["id"] != area_id for a in listed.json())


async def test_dispatch_falls_back_to_global_responsibility_area(client, world, monkeypatch):
    from app.api.routes import demand as demand_routes

    async def fake_dispatch(*args, **kwargs):
        return {"run_id": "fake-run-id"}

    monkeypatch.setattr(demand_routes, "dispatch_agent_run", fake_dispatch)

    created = await client.post(
        "/api/v1/responsibility-areas",
        json={"task_type": "bug", "owner_agent_id": str(world["global_agent_id"])},
    )
    assert created.status_code == 201

    dispatched = await client.post(f"/api/v1/tasks/{world['task_id']}/dispatch", json={})
    assert dispatched.status_code == 200, dispatched.text
    assert dispatched.json()["target_agent_id"] == str(world["global_agent_id"])


async def test_dispatch_prefers_project_scoped_over_global(client, world, monkeypatch):
    from app.api.routes import demand as demand_routes

    async def fake_dispatch(*args, **kwargs):
        return {"run_id": "fake-run-id"}

    monkeypatch.setattr(demand_routes, "dispatch_agent_run", fake_dispatch)

    await client.post(
        "/api/v1/responsibility-areas",
        json={"task_type": "bug", "owner_agent_id": str(world["global_agent_id"])},
    )
    await client.post(
        "/api/v1/responsibility-areas",
        json={
            "task_type": "bug",
            "project_id": str(world["project_id"]),
            "owner_agent_id": str(world["scoped_agent_id"]),
        },
    )

    dispatched = await client.post(f"/api/v1/tasks/{world['task_id']}/dispatch", json={})
    assert dispatched.status_code == 200, dispatched.text
    assert dispatched.json()["target_agent_id"] == str(world["scoped_agent_id"])


async def test_dispatch_without_assignment_or_area_still_fails_400(client, world):
    resp = await client.post(f"/api/v1/tasks/{world['task_id']}/dispatch", json={})
    assert resp.status_code == 400
    assert "responsibility area" in resp.json()["detail"]
