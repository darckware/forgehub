# ruff: noqa: F811
"""Service execution evidence must belong to the exact canonical attempt."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete

from app.core.task_evidence import verify_evidence
from app.db.base import AsyncSessionLocal
from app.db.models.host_execution import HostExecution, HostExecutionResult
from app.db.models.task import TaskExecution
from app.tests.test_task_evidence import project_and_task, _create_execution, _create_dispatched_demand  # noqa: F401


@pytest.mark.parametrize("case,expected", [("success", True), ("failed", False),
    ("wrong_attempt", False), ("empty", False), ("running", None)])
async def test_host_evidence_verifies_own_attempt_and_all_machine_results(project_and_task, case, expected):
    execution_id = await _create_execution(project_and_task["task_id"])
    demand_id = await _create_dispatched_demand(project_and_task["task_id"], project_and_task["agent_id"], execution_id)
    async with AsyncSessionLocal() as db:
        host = HostExecution(shell="sh", command="true", timeout_seconds=30,
            status="running" if case == "running" else "completed", requested_by="test",
            agent_id=project_and_task["agent_id"], trigger="agent", agent_demand_id=demand_id,
            started_at=datetime.now(timezone.utc))
        db.add(host)
        await db.flush()
        host_id = host.id
        if case != "empty":
            db.add(HostExecutionResult(execution_id=host.id, server_name="isolated-test",
                status="failed" if case == "failed" else "succeeded", exit_code=1 if case == "failed" else 0))
        await db.commit()
        execution = await db.get(TaskExecution, execution_id)
        if case == "wrong_attempt":
            # Same task, different attempt: a previous run must not prove this one.
            execution = TaskExecution(task_id=execution.task_id, status="reported", attempt_number=2)
            db.add(execution)
            await db.flush()
        execution.evidence_ref = f"host:{host_id}"
        try:
            result, reason = await verify_evidence(db, execution)
            assert result is expected, reason
        finally:
            await db.rollback()
            await db.execute(delete(HostExecution).where(HostExecution.id == host_id))
            await db.commit()


async def test_host_report_accepts_only_its_canonical_attempt(project_and_task):
    from fastapi import HTTPException
    from app.api.routes.task import _assert_evidence_in_scope
    from app.db.models.task import ProjectTask
    execution_id = await _create_execution(project_and_task["task_id"])
    demand_id = await _create_dispatched_demand(project_and_task["task_id"], project_and_task["agent_id"], execution_id)
    async with AsyncSessionLocal() as db:
        host = HostExecution(shell="sh", command="true", timeout_seconds=30, status="completed",
            requested_by="test", agent_id=project_and_task["agent_id"], trigger="agent", agent_demand_id=demand_id,
            started_at=datetime.now(timezone.utc))
        db.add(host)
        await db.flush()
        task = await db.get(ProjectTask, project_and_task["task_id"])
        evidence = [f"host:{host.id}"]
        await _assert_evidence_in_scope(db, task, evidence, execution_id)
        import uuid
        with pytest.raises(HTTPException) as exc:
            await _assert_evidence_in_scope(db, task, evidence, uuid.uuid4())
        assert exc.value.status_code == 422
        await db.rollback()
