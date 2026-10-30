"""Tests for the Task domain (project_tasks, task_dependencies,
task_required_skills, task_assignments, task_executions).

DB strategy: this suite runs against the real, shared `company_postgres`
database used by every domain agent's tests, so it must be careful never
to assume exclusive ownership of any table -- other domain agents may be
creating/using `company.agents`, `company.sub_agents`, `company.skills`,
and `company.planning_items` concurrently. Specifically:
- Table creation uses `checkfirst=True` (the default) and only ever
  *creates* tables, never drops them -- so this module is safe to import
  whether the real `agents`/`sub_agents`/`skills`/`planning_items` tables
  already exist (created by another domain agent) or not (in which case
  minimal stub tables with just an `id` column are created here,
  sufficient to satisfy this domain's string FKs; a later domain
  migration may legitimately add more columns to those same tables
  without conflict since we never redefine columns that already exist).
- Each test cleans up only the specific rows it created (by id), never a
  blanket `DELETE FROM <table>` / `DROP TABLE`, so concurrently-running
  tests from other domains are not affected.
"""
import uuid

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, text

from app.db.base import AsyncSessionLocal, Base, engine
from app.db.models.agent import Agent
from app.db.models.backlog import PlanningItem
from app.db.models.governance import AuditEvent
from app.db.models.product import Product, ProductVersion
from app.db.models.project import Project
from app.db.models.progress import ProgressCheckpoint
from app.db.models.task import (  # noqa: F401  (ensures tables register on Base.metadata)
    ProjectTask,
    TaskAssignment,
    TaskDependency,
    TaskExecution,
    TaskRequiredSkill,
)
from app.api.schemas.task import TaskExecutionCreate
from app.main import app
from app.api.routes import task as task_routes

# Make sure this domain's router is mounted even though the central wiring
# step (main.py) hasn't added it yet -- keeps this test self-contained.
app.include_router(task_routes.router)


@pytest_asyncio.fixture
async def dependency_pair(client, created_ids, planning_item_id):
    ids = []
    for title in ("Prerequisite", "Dependent"):
        response = await client.post("/api/v1/tasks", json=_task_payload(planning_item_id, title=title))
        assert response.status_code == 201, response.text
        ids.append(response.json()["id"])
    created_ids["project_tasks"].extend(ids)
    response = await client.post(
        f"/api/v1/tasks/{ids[1]}/dependencies",
        json={"task_id": ids[1], "depends_on_task_id": ids[0]},
    )
    assert response.status_code == 201, response.text
    created_ids["task_dependencies"].append(response.json()["id"])
    return ids


@pytest.mark.parametrize("entry", ["execution", "execution_update", "status", "messages", "execution_link", "scheduler"])
async def test_dependencies_gate_every_execution_entry(
    client, dependency_pair, test_suite_agent, monkeypatch, entry
):
    from datetime import datetime, timedelta, timezone
    from unittest.mock import AsyncMock

    from app.api.routes import demand as demand_routes
    from app.db.models.demand import AgentDemand

    predecessor_id, task_id = dependency_pair
    starts = []

    async def runner(run_id, agent, prompt, path):
        starts.append(run_id)
        return {"run_id": run_id}

    monkeypatch.setattr(demand_routes, "dispatch_agent_run", runner)
    monkeypatch.setattr(demand_routes, "_send_notice", AsyncMock())
    if entry == "execution":
        response = await client.post(f"/api/v1/tasks/{task_id}/executions", json={"executor_type": "agent"})
        assert response.status_code == 409, response.text
    elif entry == "execution_update":
        await _set_status(predecessor_id, "done")
        response = await client.post(f"/api/v1/tasks/{task_id}/executions", json={"executor_type": "agent"})
        assert response.status_code == 201, response.text
        execution_id = response.json()["id"]
        response = await client.patch(f"/api/v1/tasks/{predecessor_id}", json={"status": "planned"})
        assert response.status_code == 200, response.text
        response = await client.patch(
            f"/api/v1/tasks/{task_id}/executions/{execution_id}", json={"status": "running"}
        )
        assert response.status_code == 409, response.text
    elif entry == "status":
        response = await client.patch(f"/api/v1/tasks/{task_id}", json={"status": "in_progress"})
        assert response.status_code == 409, response.text
    else:
        due = datetime(2000, 1, 1, tzinfo=timezone.utc)

        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2001, 1, 1, tzinfo=timezone.utc)

        monkeypatch.setattr(demand_routes, "datetime", Clock)
        monkeypatch.setattr(demand_routes, "_dispatch_slots", AsyncMock(return_value=1))
        async with AsyncSessionLocal() as db:
            linked_execution_id = None
            if entry == "execution_link":
                execution = TaskExecution(
                    task_id=uuid.UUID(task_id), executor_type="agent", attempt_number=1, status="pending",
                )
                db.add(execution)
                await db.flush()
                linked_execution_id = execution.id
            item = AgentDemand(
                from_agent="test-suite", from_agent_id=test_suite_agent,
                target_agent_id=test_suite_agent, subject="Dependency guard", body="test",
                working_path="/tmp", origin_type="task",
                origin_id=uuid.UUID(predecessor_id if entry == "execution_link" else task_id),
                task_execution_id=linked_execution_id,
                scheduled_at=due,
            )
            db.add(item)
            independent = None
            if entry == "scheduler":
                independent = AgentDemand(
                    from_agent="test-suite", from_agent_id=test_suite_agent,
                    target_agent_id=test_suite_agent, subject="Independent work", body="test",
                    working_path="/tmp", origin_type="task", scheduled_at=due + timedelta(seconds=1),
                )
                db.add(independent)
            await db.commit()
            demand_id = item.id
            demand_ids = [item.id] + ([independent.id] if independent is not None else [])
        try:
            if entry in {"messages", "execution_link"}:
                response = await client.post(
                    f"/api/v1/demands/{demand_id}/dispatch",
                    json={"target_agent_id": str(test_suite_agent)},
                )
                assert response.status_code == 409, response.text
                assert response.json()["detail"]["blocking"][0]["task_id"] == predecessor_id
            else:
                async with AsyncSessionLocal() as db:
                    await demand_routes.run_scheduled_dispatch_pass(db)
            async with AsyncSessionLocal() as db:
                queued = await db.get(AgentDemand, demand_id)
                assert queued.dispatch_status is None
                assert queued.agent_run_id is None
                assert queued.dispatch_attempts == 0
                assert queued.dispatch_error is None
                if independent is not None:
                    ready = await db.get(AgentDemand, independent.id)
                    assert ready.dispatch_status == "dispatched"
                    # The external runner is a fake; simulate its terminal
                    # result before expecting a second run for this agent.
                    ready.dispatch_status = "completed"
                    await db.commit()
            assert len(starts) == (1 if entry == "scheduler" else 0)
            await _set_status(predecessor_id, "done")
            async with AsyncSessionLocal() as db:
                await demand_routes.run_scheduled_dispatch_pass(db)
            async with AsyncSessionLocal() as db:
                released = await db.get(AgentDemand, demand_id)
                assert released.dispatch_status == "dispatched"
                assert released.dispatch_attempts == 1
            assert len(starts) == (2 if entry == "scheduler" else 1)
        finally:
            async with AsyncSessionLocal() as db:
                await db.execute(delete(AgentDemand).where(AgentDemand.id.in_(demand_ids)))
                await db.commit()
    if entry in {"execution", "execution_update", "status"}:
        assert starts == []
    else:
        assert len(starts) == (2 if entry == "scheduler" else 1)


async def test_every_prerequisite_must_finish(client, dependency_pair, created_ids, planning_item_id):
    first_id, task_id = dependency_pair
    response = await client.post("/api/v1/tasks", json=_task_payload(planning_item_id, title="Second prerequisite"))
    assert response.status_code == 201, response.text
    second_id = response.json()["id"]
    created_ids["project_tasks"].append(second_id)
    response = await client.post(
        f"/api/v1/tasks/{task_id}/dependencies",
        json={"task_id": task_id, "depends_on_task_id": second_id},
    )
    assert response.status_code == 201, response.text
    created_ids["task_dependencies"].append(response.json()["id"])
    await _set_status(first_id, "done")
    response = await client.post(f"/api/v1/tasks/{task_id}/dispatch", json={})
    assert response.status_code == 409, response.text
    assert [item["task_id"] for item in response.json()["detail"]["blocking"]] == [second_id]
    await _set_status(second_id, "done")
    response = await client.post(f"/api/v1/tasks/{task_id}/dispatch", json={})
    assert response.status_code == 400, response.text
    assert "dependencies" not in response.json()["detail"]


@pytest.mark.parametrize("predecessor_status", ["in_progress", "blocked", "cancelled"])
async def test_unfinished_dependency_states_block_dispatch(client, dependency_pair, predecessor_status):
    predecessor_id, task_id = dependency_pair
    response = await client.patch(f"/api/v1/tasks/{predecessor_id}", json={"status": predecessor_status})
    assert response.status_code == 200, response.text
    response = await client.post(f"/api/v1/tasks/{task_id}/dispatch", json={})
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["blocking"][0]["status"] == predecessor_status


async def test_deployed_dependency_allows_completion(admin_client, dependency_pair):
    predecessor_id, task_id = dependency_pair
    await _set_status(predecessor_id, "deployed")
    response = await admin_client.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"})
    # The dependency gate passed; the next one (no execution yet) is what stops it.
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "COMPLETION_NO_EXECUTION"


async def test_indirect_dependency_cycle_rejected(client, dependency_pair, created_ids, planning_item_id):
    predecessor_id, task_id = dependency_pair
    response = await client.post("/api/v1/tasks", json=_task_payload(planning_item_id, title="Third"))
    assert response.status_code == 201, response.text
    third_id = response.json()["id"]
    created_ids["project_tasks"].append(third_id)
    response = await client.post(
        f"/api/v1/tasks/{third_id}/dependencies",
        json={"task_id": third_id, "depends_on_task_id": task_id},
    )
    assert response.status_code == 201, response.text
    created_ids["task_dependencies"].append(response.json()["id"])
    response = await client.post(
        f"/api/v1/tasks/{predecessor_id}/dependencies",
        json={"task_id": predecessor_id, "depends_on_task_id": third_id},
    )
    assert response.status_code == 409, response.text


# NOTE: this module previously declared local stub `Table()` objects for the
# other-domain FK targets (`planning_items`, `agents`, `sub_agents`,
# `skills`) to satisfy string-FK resolution before the unified Alembic
# migration existed. The real ORM models for those tables now exist (Backlog
# and Agent domains) and are migration-managed, so those stubs were removed
# -- a duplicate `Table(..., extend_existing=True)` registration for an
# already-mapped table corrupts SQLAlchemy's mapper configuration for any
# other test module that also touches that table in the same test session.
# This module's tests never persist a real agent_id/sub_agent_id (the one
# place they're used is a pre-DB Pydantic validation case), so no stub data
# is needed here at all.

_ALL_TEST_TABLES = [
    ProjectTask.__table__,
    TaskDependency.__table__,
    TaskRequiredSkill.__table__,
    TaskAssignment.__table__,
    TaskExecution.__table__,
]


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _setup_schema():
    # checkfirst=True (default): only creates tables that don't exist yet.
    # Never drops anything -- this DB is shared with other domain agents'
    # concurrent test runs.
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn, tables=_ALL_TEST_TABLES, checkfirst=True
            )
        )
    yield


@pytest_asyncio.fixture
async def client(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as ac:
        yield ac


@pytest_asyncio.fixture
async def admin_client(admin_headers):
    """Completing a task records the authenticated principal (M0.6a), so the
    PATCHes that reach the completion guard need a real user."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=admin_headers) as ac:
        yield ac


async def _set_status(task_id: str, status: str) -> None:
    """Setup only: puts a *predecessor* in a status directly, like a task
    finished before the completion guard existed (M0.6a). Completing a task
    through the API needs proof; that is test_task_completion_guard.py's job."""
    async with AsyncSessionLocal() as db:
        (await db.get(ProjectTask, uuid.UUID(str(task_id)))).status = status
        await db.commit()


@pytest_asyncio.fixture
async def created_ids():
    """Tracks ids of rows created during a test, per table, so the test
    can delete exactly those rows on teardown instead of truncating
    shared tables."""
    ids: dict[str, list[uuid.UUID]] = {
        "task_executions": [],
        "task_assignments": [],
        "task_required_skills": [],
        "task_dependencies": [],
        "project_tasks": [],
    }
    yield ids
    async with engine.begin() as conn:
        for table in (
            "task_executions",
            "task_assignments",
            "task_required_skills",
            "task_dependencies",
            "project_tasks",
        ):
            row_ids = ids.get(table) or []
            if row_ids:
                await conn.execute(
                    text(f"DELETE FROM company.{table} WHERE id = ANY(:ids)"),
                    {"ids": row_ids},
                )


@pytest_asyncio.fixture
async def planning_item_id():
    """A real PlanningItem (via a real Project -> ProductVersion -> Product
    chain), since ProjectTask.planning_item_id is now required on create
    (core traceability invariant) -- see create_task in
    app/api/routes/task.py."""
    async with AsyncSessionLocal() as session:
        product = Product(name=f"Task Test Product {uuid.uuid4()}")
        session.add(product)
        await session.flush()
        version = ProductVersion(product_id=product.id, version="0.1.0")
        session.add(version)
        await session.flush()
        project = Project(
            name=f"Task Test Project {uuid.uuid4()}", product_version_id=version.id
        )
        session.add(project)
        await session.flush()
        item = PlanningItem(
            title="Task domain test planning item",
            item_type="feature",
            project_id=project.id,
        )
        session.add(item)
        await session.commit()
        item_id, project_id, version_id, product_id = (
            item.id,
            project.id,
            version.id,
            product.id,
        )

    yield item_id

    async with engine.begin() as conn:
        # Defensively clear any project_tasks (and their children) still
        # pointing at this planning item -- fixture teardown order relative
        # to the test's own `created_ids` cleanup isn't guaranteed, so don't
        # rely on the test having already deleted its tasks.
        task_ids_result = await conn.execute(
            text("SELECT id FROM company.project_tasks WHERE planning_item_id = :id"),
            {"id": item_id},
        )
        task_ids = [row[0] for row in task_ids_result.all()]
        if task_ids:
            await conn.execute(
                text("DELETE FROM company.task_executions WHERE task_id = ANY(:ids)"),
                {"ids": task_ids},
            )
            await conn.execute(
                text("DELETE FROM company.task_assignments WHERE task_id = ANY(:ids)"),
                {"ids": task_ids},
            )
            await conn.execute(
                text(
                    "DELETE FROM company.task_dependencies "
                    "WHERE task_id = ANY(:ids) OR depends_on_task_id = ANY(:ids)"
                ),
                {"ids": task_ids},
            )
            await conn.execute(
                text("DELETE FROM company.task_required_skills WHERE task_id = ANY(:ids)"),
                {"ids": task_ids},
            )
            await conn.execute(
                text("DELETE FROM company.project_tasks WHERE id = ANY(:ids)"),
                {"ids": task_ids},
            )
        await conn.execute(
            text("DELETE FROM company.planning_items WHERE id = :id"), {"id": item_id}
        )
        await conn.execute(
            text("DELETE FROM company.projects WHERE id = :id"), {"id": project_id}
        )
        await conn.execute(
            text("DELETE FROM company.product_versions WHERE id = :id"),
            {"id": version_id},
        )
        await conn.execute(
            text("DELETE FROM company.products WHERE id = :id"), {"id": product_id}
        )


def _task_payload(planning_item_id, **overrides):
    payload = {
        "planning_item_id": str(planning_item_id),
        "title": "Implement task domain backend",
        "description": "Build CRUD + business rules",
        "task_type": "feature",
        "priority": "high",
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_create_get_list_task(client: AsyncClient, created_ids, planning_item_id):
    resp = await client.post("/api/v1/tasks", json=_task_payload(planning_item_id))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    created_ids["project_tasks"].append(body["id"])
    assert body["title"] == "Implement task domain backend"
    assert body["status"] == "planned"
    assert body["task_type"] == "feature"

    task_id = body["id"]

    get_resp = await client.get(f"/api/v1/tasks/{task_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == task_id

    list_resp = await client.get("/api/v1/tasks")
    assert list_resp.status_code == 200
    ids = [t["id"] for t in list_resp.json()]
    assert task_id in ids


@pytest.mark.asyncio
async def test_get_nonexistent_task_returns_404(client: AsyncClient):
    resp = await client.get(f"/api/v1/tasks/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_invalid_task_type_returns_422(client: AsyncClient, planning_item_id):
    resp = await client.post(
        "/api/v1/tasks", json=_task_payload(planning_item_id, task_type="not_a_real_type")
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_missing_source_returns_400(client: AsyncClient):
    # Neither planning_item_id nor change_request_id -- 400 from route layer.
    payload = {"title": "No source", "task_type": "feature", "priority": "high"}
    resp = await client.post("/api/v1/tasks", json=payload)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_nonexistent_planning_item_id_returns_400(client: AsyncClient):
    payload = {
        "planning_item_id": str(uuid.uuid4()),
        "title": "Bad planning item",
        "task_type": "feature",
        "priority": "high",
    }
    resp = await client.post("/api/v1/tasks", json=payload)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_execution_requires_evidence_when_completed(
    client: AsyncClient, created_ids, planning_item_id
):
    """Business rule 6.4.3: every execution must have evidence -- creating
    an execution with status=completed and no evidence_ref must be
    rejected (422), and the rule must also be re-checked on PATCH."""
    resp = await client.post("/api/v1/tasks", json=_task_payload(planning_item_id))
    assert resp.status_code == 201
    task_id = resp.json()["id"]
    created_ids["project_tasks"].append(task_id)

    bad_exec = await client.post(
        f"/api/v1/tasks/{task_id}/executions",
        json={"executor_type": "agent", "status": "completed"},
    )
    assert bad_exec.status_code == 422

    ok_exec = await client.post(
        f"/api/v1/tasks/{task_id}/executions",
        json={"executor_type": "agent", "status": "running"},
    )
    assert ok_exec.status_code == 201, ok_exec.text
    execution_id = ok_exec.json()["id"]
    assert ok_exec.json()["attempt_number"] == 1
    created_ids["task_executions"].append(execution_id)
    async with AsyncSessionLocal() as session:
        started_checkpoint = (await session.execute(select(ProgressCheckpoint).where(
            ProgressCheckpoint.task_execution_id == uuid.UUID(execution_id),
            ProgressCheckpoint.checkpoint_type == "started",
        ))).scalar_one()
        assert started_checkpoint.resume_from_step_key == "execution.started"

    # Task should have moved from planned -> in_progress as a side effect.
    task_after = await client.get(f"/api/v1/tasks/{task_id}")
    assert task_after.json()["status"] == "in_progress"

    bad_patch = await client.patch(
        f"/api/v1/tasks/{task_id}/executions/{execution_id}",
        json={"status": "completed"},
    )
    assert bad_patch.status_code == 400

    good_patch = await client.patch(
        f"/api/v1/tasks/{task_id}/executions/{execution_id}",
        json={"status": "completed", "evidence_ref": "https://example.com/pr/123"},
    )
    assert good_patch.status_code == 200
    assert good_patch.json()["status"] == "completed"
    async with AsyncSessionLocal() as session:
        lifecycle = list((await session.execute(select(ProgressCheckpoint).where(
            ProgressCheckpoint.task_execution_id == uuid.UUID(execution_id)
        ).order_by(ProgressCheckpoint.sequence))).scalars())
        assert [checkpoint.checkpoint_type for checkpoint in lifecycle] == ["started", "completed"]
        assert lifecycle[-1].evidence_refs == ["https://example.com/pr/123"]


def test_task_execution_normalizes_legacy_runtime_name():
    payload = TaskExecutionCreate(runtime_type="antigravity")

    assert payload.runtime_type == "agy"


@pytest.mark.asyncio
async def test_task_cannot_complete_with_unfinished_dependency(
    client: AsyncClient, admin_client: AsyncClient, created_ids, planning_item_id
):
    """Mirrors SPEC 6.2.9 (blocked stages prevent dependents from
    advancing), applied at task granularity: a task depending on a
    not-done task cannot be marked done."""
    dep_resp = await client.post(
        "/api/v1/tasks", json=_task_payload(planning_item_id, title="Dependency task")
    )
    assert dep_resp.status_code == 201
    dep_id = dep_resp.json()["id"]
    created_ids["project_tasks"].append(dep_id)

    main_resp = await client.post(
        "/api/v1/tasks", json=_task_payload(planning_item_id, title="Main task")
    )
    assert main_resp.status_code == 201
    main_id = main_resp.json()["id"]
    created_ids["project_tasks"].append(main_id)

    dependency = await client.post(
        f"/api/v1/tasks/{main_id}/dependencies",
        json={"task_id": main_id, "depends_on_task_id": dep_id},
    )
    assert dependency.status_code == 201, dependency.text
    created_ids["task_dependencies"].append(dependency.json()["id"])

    blocked = await admin_client.patch(f"/api/v1/tasks/{main_id}", json={"status": "done"})
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "COMPLETION_DEPENDENCIES_OPEN"

    await _set_status(dep_id, "done")

    unblocked = await admin_client.patch(f"/api/v1/tasks/{main_id}", json={"status": "done"})
    # Dependency gate passed; completing still needs proof (M0.6a).
    assert unblocked.status_code == 409
    assert unblocked.json()["detail"]["code"] == "COMPLETION_NO_EXECUTION"


@pytest.mark.asyncio
async def test_task_cannot_complete_with_unfinished_subtask(
    client: AsyncClient, admin_client: AsyncClient, created_ids, planning_item_id
):
    """Layered task-execution governance, Fase 4 (plan: resilient-twirling-
    blossom): the fan-out half -- a parent task cannot be marked done while
    any of its own subtasks (parent_task_id) hasn't reached done/deployed.
    Mirrors test_task_cannot_complete_with_unfinished_dependency above,
    walking the parent/child axis instead of the explicit TaskDependency
    one."""
    parent_resp = await client.post(
        "/api/v1/tasks", json=_task_payload(planning_item_id, title="Parent task")
    )
    assert parent_resp.status_code == 201
    parent_id = parent_resp.json()["id"]
    created_ids["project_tasks"].append(parent_id)

    sub_resp = await client.post(
        "/api/v1/tasks",
        json=_task_payload(planning_item_id, title="Subtask", parent_task_id=parent_id),
    )
    assert sub_resp.status_code == 201, sub_resp.text
    sub_id = sub_resp.json()["id"]
    created_ids["project_tasks"].append(sub_id)

    blocked = await admin_client.patch(f"/api/v1/tasks/{parent_id}", json={"status": "done"})
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["detail"]["code"] == "COMPLETION_SUBTASKS_OPEN"

    await _set_status(sub_id, "done")

    unblocked = await admin_client.patch(f"/api/v1/tasks/{parent_id}", json={"status": "done"})
    # Subtask gate passed; completing still needs proof (M0.6a).
    assert unblocked.status_code == 409
    assert unblocked.json()["detail"]["code"] == "COMPLETION_NO_EXECUTION"


@pytest.mark.asyncio
async def test_task_with_no_subtasks_is_unaffected(
    client: AsyncClient, admin_client: AsyncClient, created_ids, planning_item_id
):
    """A leaf task (no children at all) is never refused for subtasks --
    the subtask gate only engages when parent_task_id rows actually exist
    for it (completing still needs the M0.6a proof)."""
    resp = await client.post("/api/v1/tasks", json=_task_payload(planning_item_id, title="Leaf task"))
    assert resp.status_code == 201
    task_id = resp.json()["id"]
    created_ids["project_tasks"].append(task_id)

    done = await admin_client.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"})
    # The subtask gate doesn't engage; the next one (no execution) does.
    assert done.status_code == 409, done.text
    assert done.json()["detail"]["code"] == "COMPLETION_NO_EXECUTION"


@pytest.mark.asyncio
async def test_self_dependency_rejected(client: AsyncClient, created_ids, planning_item_id):
    resp = await client.post(
        "/api/v1/tasks", json=_task_payload(planning_item_id, title="Solo task")
    )
    assert resp.status_code == 201
    task_id = resp.json()["id"]
    created_ids["project_tasks"].append(task_id)

    self_dep = await client.post(
        f"/api/v1/tasks/{task_id}/dependencies",
        json={"task_id": task_id, "depends_on_task_id": task_id},
    )
    assert self_dep.status_code == 422


@pytest.mark.asyncio
async def test_assignment_requires_exactly_one_target(
    client: AsyncClient, created_ids, planning_item_id
):
    resp = await client.post(
        "/api/v1/tasks", json=_task_payload(planning_item_id, title="Assignable task")
    )
    assert resp.status_code == 201
    task_id = resp.json()["id"]
    created_ids["project_tasks"].append(task_id)

    neither = await client.post(
        f"/api/v1/tasks/{task_id}/assignments", json={"task_id": task_id}
    )
    assert neither.status_code == 422

    both = await client.post(
        f"/api/v1/tasks/{task_id}/assignments",
        json={
            "task_id": task_id,
            "agent_id": str(uuid.uuid4()),
            "sub_agent_id": str(uuid.uuid4()),
        },
    )
    assert both.status_code == 422


@pytest.mark.asyncio
async def test_dispatch_blocked_by_unfinished_dependency(
    client: AsyncClient, created_ids, planning_item_id
):
    """Pacote 3 (2026-08-01): dispatch_task now ports execution.py's
    dependency preflight -- a task cannot be dispatched via Messages while
    a predecessor hasn't reached done/deployed. Verified without touching
    the real dispatch/host-bridge path: the dependency check happens before
    target-agent resolution, so a blocked dispatch never gets that far, and
    an unblocked-but-unassigned dispatch fails on the *next* check (400, no
    active assignment) instead -- proving the dependency gate specifically
    let it through."""
    predecessor = await client.post(
        "/api/v1/tasks", json=_task_payload(planning_item_id, title="Predecessor task")
    )
    assert predecessor.status_code == 201
    predecessor_id = predecessor.json()["id"]
    created_ids["project_tasks"].append(predecessor_id)

    dependent = await client.post(
        "/api/v1/tasks", json=_task_payload(planning_item_id, title="Dependent task", plan_brief="Faça X depois de Y")
    )
    assert dependent.status_code == 201
    dependent_id = dependent.json()["id"]
    assert dependent.json()["plan_brief"] == "Faça X depois de Y"
    created_ids["project_tasks"].append(dependent_id)

    dependency = await client.post(
        f"/api/v1/tasks/{dependent_id}/dependencies",
        json={"task_id": dependent_id, "depends_on_task_id": predecessor_id},
    )
    assert dependency.status_code == 201, dependency.text
    created_ids["task_dependencies"].append(dependency.json()["id"])

    blocked = await client.post(f"/api/v1/tasks/{dependent_id}/dispatch", json={})
    assert blocked.status_code == 409, blocked.text
    detail = blocked.json()["detail"]
    assert "unfinished dependencies" in detail["message"]
    assert detail["blocking"][0]["task_id"] == predecessor_id

    await _set_status(predecessor_id, "done")

    unblocked = await client.post(f"/api/v1/tasks/{dependent_id}/dispatch", json={})
    # Dependency gate passed -- next gate (no active agent assignment) is
    # what actually stops it here, a different status/reason than before.
    assert unblocked.status_code == 400, unblocked.text
    assert "dependencies" not in unblocked.json()["detail"]


@pytest.mark.asyncio
async def test_successful_dispatch_commits_and_writes_audit_event(
    client: AsyncClient, created_ids, planning_item_id, monkeypatch
):
    """Pacote 4 (2026-08-01) regression test for a pre-existing bug: a
    successful dispatch used to construct AuditEvent(description=...), a
    kwarg the model doesn't have (it has actor/payload) -- this raised
    *after* the agent run had already been kicked off via dispatch_agent_run
    (no commit yet, "Caller commits"), so the whole transaction rolled back
    while the real side effect (starting the run) had already happened.
    Mocks dispatch_agent_run the same way test_demand_backlog_dispatch.py
    does, since there's no live host-bridge in this test environment."""
    from app.api.routes import demand as demand_routes

    dispatched_paths: list[str] = []

    async def fake_dispatch(_run_id, _agent, _prompt, project_path):
        dispatched_paths.append(project_path)
        return {"run_id": "fake-run-id"}

    monkeypatch.setattr(demand_routes, "dispatch_agent_run", fake_dispatch)

    async with AsyncSessionLocal() as db:
        agent = Agent(
            name=f"Dispatch Test Agent {uuid.uuid4().hex[:8]}",
            agent_type="executor",
            runtime_type="claude",
        )
        db.add(agent)
        planning_item = await db.get(PlanningItem, planning_item_id)
        project = await db.get(Project, planning_item.project_id)
        project.working_directory_path = "/root/project/task-dispatch-test"
        await db.commit()
        await db.refresh(agent)
        agent_id = agent.id

    resp = await client.post(
        "/api/v1/tasks", json=_task_payload(planning_item_id, title="Dispatchable task")
    )
    assert resp.status_code == 201
    task_id = resp.json()["id"]
    created_ids["project_tasks"].append(task_id)

    try:
        dispatched = await client.post(
            f"/api/v1/tasks/{task_id}/dispatch", json={"target_agent_id": str(agent_id)}
        )
        assert dispatched.status_code == 200, dispatched.text
        assert dispatched.json()["dispatch_status"] == "dispatched"
        assert dispatched.json()["task_status"] == "in_progress"
        assert dispatched_paths == ["/root/project/task-dispatch-test"]

        async with AsyncSessionLocal() as db:
            events = list((await db.execute(select(AuditEvent).where(
                AuditEvent.entity_type == "project_task", AuditEvent.entity_id == uuid.UUID(task_id),
                AuditEvent.event_type == "task.dispatched",
            ))).scalars())
            assert len(events) == 1
            # §0.5 (M0.2c): the authenticated principal, never "forgehub".
            assert events[0].actor != "forgehub" and events[0].payload["principal_type"] == "user"
            assert "dispatched to Dispatch Test Agent" in (events[0].payload or {}).get("description", "")
            await db.execute(text("DELETE FROM company.audit_events WHERE id = :id"), {"id": events[0].id})
            await db.commit()
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(text("DELETE FROM company.agent_demands WHERE origin_id = :id"), {"id": task_id})
            await db.execute(delete(Agent).where(Agent.id == agent_id))
            await db.commit()


async def test_ambiguous_task_dispatch_reuses_the_persisted_inbox_demand(
    client: AsyncClient, created_ids, planning_item_id, monkeypatch
):
    """A retry must follow the original potentially-running task execution."""
    from app.api.routes import demand as demand_routes
    from app.db.models.demand import AgentDemand

    async def accepted_but_timed_out(run_id, *_args):
        raise httpx.ReadTimeout(
            "bridge response timed out",
            request=httpx.Request("POST", "http://bridge/v1/agent-runs"),
        )

    monkeypatch.setattr(demand_routes, "dispatch_agent_run", accepted_but_timed_out)
    async with AsyncSessionLocal() as db:
        agent = Agent(
            name=f"Ambiguous Task Agent {uuid.uuid4().hex[:8]}",
            agent_type="executor", runtime_type="claude",
        )
        db.add(agent)
        planning_item = await db.get(PlanningItem, planning_item_id)
        project = await db.get(Project, planning_item.project_id)
        project.working_directory_path = "/root/project/task-dispatch-test"
        await db.commit()
        agent_id = agent.id

    created = await client.post(
        "/api/v1/tasks", json=_task_payload(planning_item_id, title="Ambiguous task dispatch")
    )
    assert created.status_code == 201, created.text
    task_id = uuid.UUID(created.json()["id"])
    created_ids["project_tasks"].append(task_id)
    try:
        first = await client.post(
            f"/api/v1/tasks/{task_id}/dispatch", json={"target_agent_id": str(agent_id)}
        )
        assert first.status_code == 502, first.text
        async with AsyncSessionLocal() as db:
            demand = (
                await db.execute(select(AgentDemand).where(AgentDemand.origin_id == task_id))
            ).scalar_one()
            original_demand_id = demand.id
            assert demand.task_execution_id is not None
            assert demand.agent_run_id is not None

        repeat = await client.post(
            f"/api/v1/tasks/{task_id}/dispatch", json={"target_agent_id": str(agent_id)}
        )
        assert repeat.status_code == 200, repeat.text
        assert uuid.UUID(repeat.json()["demand_id"]) == original_demand_id
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AgentDemand).where(AgentDemand.origin_id == task_id))
            await db.execute(delete(Agent).where(Agent.id == agent_id))
            await db.commit()


@pytest.mark.asyncio
async def test_dispatch_requires_a_configured_project_working_directory(
    client: AsyncClient, created_ids, planning_item_id
):
    """A Task route must surface missing execution context before any run starts."""
    async with AsyncSessionLocal() as db:
        agent = Agent(name=f"No path Agent {uuid.uuid4().hex[:8]}", agent_type="executor")
        db.add(agent)
        await db.commit()
        agent_id = agent.id

    response = await client.post(
        "/api/v1/tasks", json=_task_payload(planning_item_id, title="Task without project directory")
    )
    assert response.status_code == 201, response.text
    task_id = response.json()["id"]
    created_ids["project_tasks"].append(task_id)
    try:
        dispatched = await client.post(
            f"/api/v1/tasks/{task_id}/dispatch", json={"target_agent_id": str(agent_id)}
        )
        assert dispatched.status_code == 409, dispatched.text
        assert "absolute working directory" in dispatched.json()["detail"]
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(text("DELETE FROM company.agent_demands WHERE origin_id = :id"), {"id": task_id})
            await db.execute(delete(Agent).where(Agent.id == agent_id))
            await db.commit()
