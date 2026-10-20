"""Layered task-execution governance, Fase 1 (plan: resilient-twirling-
blossom) -- the chain that closes the incident this module exists to
prevent: dispatch creates a real TaskExecution, _finalize_dispatch never
writes "completed"/"verified" directly (only "reported"), and
run_evidence_verification_pass is the only thing that promotes "reported"
to "verified" (or demotes it to "failed") by checking evidence_ref against
reality. See core/task_evidence.py's module docstring for the full story.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.routes.demand import _finalize_dispatch
from app.core.task_evidence import run_evidence_verification_pass
from app.db.base import AsyncSessionLocal, engine
from app.db.models.agent import Agent
from app.db.models.backlog import PlanningItem
from app.db.models.demand import AgentDemand
from app.db.models.product import Product, ProductVersion
from app.db.models.project import Project
from app.db.models.task import ProjectTask, TaskExecution
from app.main import app


@pytest_asyncio.fixture
async def client(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as ac:
        yield ac


@pytest_asyncio.fixture
async def project_and_task(tmp_path):
    """A real Product -> ProductVersion -> Project (with a real filesystem
    working_directory_path, for file: evidence checks) -> PlanningItem ->
    ProjectTask chain, plus a registered Agent to act as dispatch target."""
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        product = Product(name=f"Evidence Test Product {suffix}")
        session.add(product)
        await session.flush()
        version = ProductVersion(product_id=product.id, version="0.1.0")
        session.add(version)
        await session.flush()
        project = Project(
            name=f"Evidence Test Project {suffix}",
            product_version_id=version.id,
            working_directory_path=str(tmp_path),
        )
        session.add(project)
        await session.flush()
        item = PlanningItem(
            title="Evidence test planning item", item_type="feature", project_id=project.id
        )
        session.add(item)
        await session.flush()
        task = ProjectTask(title="Evidence test task", planning_item_id=item.id)
        session.add(task)
        agent = Agent(name=f"Evidence Test Agent {suffix}", agent_type="executor", runtime_type="claude")
        session.add(agent)
        await session.commit()
        ids = {
            "product_id": product.id,
            "version_id": version.id,
            "project_id": project.id,
            "item_id": item.id,
            "task_id": task.id,
            "agent_id": agent.id,
        }

    yield ids

    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM company.agent_demands WHERE origin_id = :id"), {"id": ids["task_id"]}
        )
        await conn.execute(
            text("DELETE FROM company.task_executions WHERE task_id = :id"), {"id": ids["task_id"]}
        )
        await conn.execute(
            text("DELETE FROM company.project_tasks WHERE id = :id"), {"id": ids["task_id"]}
        )
        await conn.execute(text("DELETE FROM company.agents WHERE id = :id"), {"id": ids["agent_id"]})
        await conn.execute(
            text("DELETE FROM company.planning_items WHERE id = :id"), {"id": ids["item_id"]}
        )
        await conn.execute(text("DELETE FROM company.projects WHERE id = :id"), {"id": ids["project_id"]})
        await conn.execute(
            text("DELETE FROM company.product_versions WHERE id = :id"), {"id": ids["version_id"]}
        )
        await conn.execute(text("DELETE FROM company.products WHERE id = :id"), {"id": ids["product_id"]})


async def _create_execution(task_id: uuid.UUID, *, started_at: datetime | None = None) -> uuid.UUID:
    async with AsyncSessionLocal() as session:
        execution = TaskExecution(
            task_id=task_id,
            executor_type="agent",
            status="running",
            started_at=started_at or datetime.now(timezone.utc),
        )
        session.add(execution)
        await session.commit()
        await session.refresh(execution)
        return execution.id


async def _create_dispatched_demand(
    task_id: uuid.UUID, agent_id: uuid.UUID, execution_id: uuid.UUID
) -> uuid.UUID:
    async with AsyncSessionLocal() as session:
        demand = AgentDemand(
            from_agent="forgehub",
            target_agent_id=agent_id,
            subject="dispatch",
            body="do the thing",
            origin_type="task",
            origin_id=task_id,
            task_execution_id=execution_id,
            dispatch_status="dispatched",
        )
        session.add(demand)
        await session.commit()
        await session.refresh(demand)
        return demand.id


# ---------------------------------------------------------------------------
# _finalize_dispatch closes the linked TaskExecution instead of leaving it
# ---------------------------------------------------------------------------


async def test_finalize_dispatch_marks_execution_reported_on_success(project_and_task):
    execution_id = await _create_execution(project_and_task["task_id"])
    demand_id = await _create_dispatched_demand(
        project_and_task["task_id"], project_and_task["agent_id"], execution_id
    )

    async with AsyncSessionLocal() as session:
        await _finalize_dispatch(session, demand_id, {"status": "completed", "output": "did the thing"})
        await session.commit()

    async with AsyncSessionLocal() as session:
        execution = await session.get(TaskExecution, execution_id)
        assert execution.status == "reported"
        assert execution.outcome_summary == "did the thing"
        assert execution.finished_at is not None


async def test_finalize_dispatch_marks_execution_failed_on_run_failure(project_and_task):
    execution_id = await _create_execution(project_and_task["task_id"])
    demand_id = await _create_dispatched_demand(
        project_and_task["task_id"], project_and_task["agent_id"], execution_id
    )

    async with AsyncSessionLocal() as session:
        await _finalize_dispatch(session, demand_id, {"status": "failed", "error": "boom"})
        await session.commit()

    async with AsyncSessionLocal() as session:
        execution = await session.get(TaskExecution, execution_id)
        assert execution.status == "failed"


async def test_finalize_dispatch_extracts_structured_evidence_line(project_and_task):
    execution_id = await _create_execution(project_and_task["task_id"])
    demand_id = await _create_dispatched_demand(
        project_and_task["task_id"], project_and_task["agent_id"], execution_id
    )

    async with AsyncSessionLocal() as session:
        await _finalize_dispatch(
            session,
            demand_id,
            {"status": "completed", "output": "Created the file.\nEVIDENCE: file:notes.txt\nDone."},
        )
        await session.commit()

    async with AsyncSessionLocal() as session:
        execution = await session.get(TaskExecution, execution_id)
        assert execution.evidence_ref == "file:notes.txt"


# ---------------------------------------------------------------------------
# run_evidence_verification_pass -- the actual check against reality
# ---------------------------------------------------------------------------


async def test_file_evidence_verified_when_fresh(project_and_task, tmp_path):
    started_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    execution_id = await _create_execution(project_and_task["task_id"], started_at=started_at)
    (tmp_path / "output.txt").write_text("real work")

    async with AsyncSessionLocal() as session:
        execution = await session.get(TaskExecution, execution_id)
        execution.status = "reported"
        execution.evidence_ref = "file:output.txt"
        await session.commit()

        await run_evidence_verification_pass(session)

    async with AsyncSessionLocal() as session:
        execution = await session.get(TaskExecution, execution_id)
        assert execution.status == "verified"


async def test_file_evidence_fails_when_it_predates_execution_start(project_and_task, tmp_path):
    """The exact repro of the incident that motivated this whole chain: an
    agent cited a file as evidence of work it claimed to have just done, but
    the file's mtime was from before the dispatch even started."""
    stale_file = tmp_path / "stale.txt"
    stale_file.write_text("old content")
    # Force the mtime into the past, ahead of when we'll claim the execution started.
    old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()
    import os
    os.utime(stale_file, (old_time, old_time))

    started_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    execution_id = await _create_execution(project_and_task["task_id"], started_at=started_at)

    async with AsyncSessionLocal() as session:
        execution = await session.get(TaskExecution, execution_id)
        execution.status = "reported"
        execution.evidence_ref = "file:stale.txt"
        await session.commit()

        await run_evidence_verification_pass(session)

    async with AsyncSessionLocal() as session:
        execution = await session.get(TaskExecution, execution_id)
        assert execution.status == "failed"


async def test_file_evidence_fails_when_file_does_not_exist(project_and_task):
    execution_id = await _create_execution(project_and_task["task_id"])

    async with AsyncSessionLocal() as session:
        execution = await session.get(TaskExecution, execution_id)
        execution.status = "reported"
        execution.evidence_ref = "file:never_created.txt"
        await session.commit()

        await run_evidence_verification_pass(session)

    async with AsyncSessionLocal() as session:
        execution = await session.get(TaskExecution, execution_id)
        assert execution.status == "failed"


async def test_db_evidence_verified_when_entity_exists(project_and_task):
    execution_id = await _create_execution(project_and_task["task_id"])

    async with AsyncSessionLocal() as session:
        execution = await session.get(TaskExecution, execution_id)
        execution.status = "reported"
        execution.evidence_ref = f"db:project_task:{project_and_task['task_id']}"
        await session.commit()

        await run_evidence_verification_pass(session)

    async with AsyncSessionLocal() as session:
        execution = await session.get(TaskExecution, execution_id)
        assert execution.status == "verified"


async def test_db_evidence_fails_when_entity_does_not_exist(project_and_task):
    """The OSINTKey incident's other half: narrating a registered
    Product/Project that was never actually created."""
    execution_id = await _create_execution(project_and_task["task_id"])

    async with AsyncSessionLocal() as session:
        execution = await session.get(TaskExecution, execution_id)
        execution.status = "reported"
        execution.evidence_ref = f"db:product:{uuid.uuid4()}"
        await session.commit()

        await run_evidence_verification_pass(session)

    async with AsyncSessionLocal() as session:
        execution = await session.get(TaskExecution, execution_id)
        assert execution.status == "failed"


async def test_missing_evidence_ref_stays_reported_for_manual_review(project_and_task):
    execution_id = await _create_execution(project_and_task["task_id"])

    async with AsyncSessionLocal() as session:
        execution = await session.get(TaskExecution, execution_id)
        execution.status = "reported"
        execution.evidence_ref = None
        await session.commit()

        await run_evidence_verification_pass(session)

    async with AsyncSessionLocal() as session:
        execution = await session.get(TaskExecution, execution_id)
        assert execution.status == "reported"


# ---------------------------------------------------------------------------
# _ensure_evidence_verified -- the gate on marking a task "done"
# ---------------------------------------------------------------------------


async def test_task_with_unverified_execution_cannot_be_marked_done(client, project_and_task):
    await _create_execution(project_and_task["task_id"])

    resp = await client.patch(
        f"/api/v1/tasks/{project_and_task['task_id']}", json={"status": "done"}
    )
    assert resp.status_code == 409, resp.text
    assert "not verified/completed" in resp.json()["detail"]


async def test_task_with_verified_execution_can_be_marked_done(client, project_and_task):
    execution_id = await _create_execution(project_and_task["task_id"])
    async with AsyncSessionLocal() as session:
        execution = await session.get(TaskExecution, execution_id)
        execution.status = "verified"
        execution.evidence_ref = "file:whatever.txt"
        await session.commit()

    resp = await client.patch(
        f"/api/v1/tasks/{project_and_task['task_id']}", json={"status": "done"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "done"
