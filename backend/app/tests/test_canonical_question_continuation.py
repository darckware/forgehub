# ruff: noqa: F811
"""Answers resume canonical work without losing its execution/evidence contract."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.core import agent_questions
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.task import ProjectTask, TaskDependency, TaskExecution
from app.tests.test_mission_cycle import cw, _verified_execution  # noqa: F401
from app.tests.test_mission_dispatch import runner, world  # noqa: F401
from app.tests.test_task_baseline_guard import _mission, _queued_demand


@pytest.mark.asyncio
async def test_answer_preserves_task_and_creates_its_own_pending_attempt(cw):
    mission = await _mission(cw)
    task = await mission.task("canonical answer continuation")
    await mission.baseline([task.id])
    previous_id = await _verified_execution(task, f"db:project_task:{task.id}")
    source_id = await _queued_demand(task, mission.executor, "/root/project/canonical",
        task_execution_id=previous_id, dispatch_status="failed", dispatch_error="STATUS: BLOCKED")
    async with AsyncSessionLocal() as db:
        previous = await db.get(TaskExecution, previous_id)
        previous.status = "failed"
        asker = await db.get(Agent, mission.executor)
        question = await agent_questions.create_question(db, asker, question="Qual formato?",
            blocking=True, origin_demand_id=source_id)
        await db.commit()
        answer = await agent_questions.record_answer(db, question, "CSV", via="screen", by="test",
            dispatch_at=datetime.now(timezone.utc) + timedelta(days=1))
        assert answer.reply_to_id == source_id
        assert answer.origin_id == task.id and answer.project_id == mission.project_id
        assert answer.working_path == "/root/project/canonical"
        assert answer.task_execution_id is not None and answer.task_execution_id != previous_id
        continuation = await db.get(TaskExecution, answer.task_execution_id)
        assert continuation.task_id == task.id and continuation.status == "pending"
        assert continuation.runtime_session_ref == str(answer.id)
        await db.refresh(previous)
        assert previous.status == "failed" and previous.evidence_ref == f"db:project_task:{task.id}"
        replay = await agent_questions.record_answer(db, question, "CSV", via="screen", by="test")
        assert replay.id == answer.id
        assert await db.scalar(select(func.count(TaskExecution.id)).where(TaskExecution.task_id == task.id)) == 2

        from app.api.routes.demand import _ensure_demand_dependencies_satisfied
        from app.core.demand_dispatch_guard import ensure_task_dispatch_admissible
        from app.core.task_dependencies import TaskDependenciesBlocked
        from app.core.task_baseline_guard import TaskBaselineBlocked
        await ensure_task_dispatch_admissible(db, answer)
        blocker = await mission.task("new prerequisite")
        dependency = TaskDependency(task_id=task.id, depends_on_task_id=blocker.id)
        db.add(dependency)
        await db.commit()
        with pytest.raises(TaskDependenciesBlocked):
            await _ensure_demand_dependencies_satisfied(db, answer)
        await db.delete(dependency)
        current_task = await db.get(ProjectTask, task.id, populate_existing=True)
        current_task.description = "Changed approved scope"
        await db.commit()
        with pytest.raises(TaskBaselineBlocked):
            await ensure_task_dispatch_admissible(db, answer)


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["done", "deployed", "cancelled"])
async def test_late_answer_does_not_create_an_attempt_for_closed_work(cw, terminal):
    mission = await _mission(cw)
    task = await mission.task("closed before answer")
    previous_id = await _verified_execution(task, f"db:project_task:{task.id}")
    source_id = await _queued_demand(task, mission.executor, "/root/project/canonical",
                                    task_execution_id=previous_id, dispatch_status="completed")
    async with AsyncSessionLocal() as db:
        asker = await db.get(Agent, mission.executor)
        question = await agent_questions.create_question(db, asker, question="Qual formato?",
            blocking=True, origin_demand_id=source_id)
        current = await db.get(ProjectTask, task.id)
        current.status = terminal
        await db.commit()
        answer = await agent_questions.record_answer(db, question, "CSV", via="screen", by="test")
        assert question.status == "answered" and question.answer == "CSV"
        assert answer.origin_id == task.id and answer.reply_to_id == source_id
        assert answer.status == "archived" and answer.scheduled_at is None
        assert answer.task_execution_id is None and answer.agent_run_id is None
        assert answer.dispatch_status is None
        assert await db.scalar(select(func.count(TaskExecution.id)).where(TaskExecution.task_id == task.id)) == 1
        await db.refresh(current)
        assert current.status == terminal


@pytest.mark.asyncio
async def test_continuation_run_receives_current_task_context_and_reports_its_own_evidence(cw):
    from app.api.routes import demand as routes
    from app.db.models.demand import AgentDemand
    mission = await _mission(cw)
    task = await mission.task("resume scoped delivery", description="REQUIRED_SCOPE_MARKER: export approved records only")
    await mission.baseline([task.id])
    previous_id = await _verified_execution(task, f"db:project_task:{task.id}")
    source_id = await _queued_demand(task, mission.executor, "/root/project/canonical",
        task_execution_id=previous_id, dispatch_status="failed", dispatch_error="STATUS: BLOCKED")
    async with AsyncSessionLocal() as db:
        previous = await db.get(TaskExecution, previous_id)
        previous.status = "failed"
        asker = await db.get(Agent, mission.executor)
        question = await agent_questions.create_question(db, asker, question="Qual formato?",
            blocking=True, origin_demand_id=source_id)
        await db.commit()
        answer = await agent_questions.record_answer(db, question, "CSV", via="screen", by="test",
            dispatch_at=datetime.now(timezone.utc) + timedelta(days=1))
        await routes._execute_dispatch(db, answer, mission.executor, None)
        await db.commit()
        assert len(cw.runner.runs) == 1
        assert "REQUIRED_SCOPE_MARKER" in cw.runner.prompts[0]
        assert "CSV" in cw.runner.prompts[0]
        assert str(task.number) in cw.runner.prompts[0]
        await routes._finalize_dispatch(db, answer.id, {"status": "completed",
            "output": f"STATUS: DONE\nEVIDENCE: db:project_task:{task.id}"})
        await db.commit()
        current = await db.get(TaskExecution, answer.task_execution_id, populate_existing=True)
        assert current.status == "reported" and current.evidence_ref == f"db:project_task:{task.id}"
        assert current.id != previous_id
        await db.refresh(previous)
        assert previous.status == "failed"
        original = await db.get(AgentDemand, source_id)
        assert original.task_execution_id == previous_id


@pytest.mark.asyncio
async def test_answer_to_review_preserves_review_operation_without_executor_attempt(cw):
    from app.tests.test_mission_base import _member
    from app.db.models.orchestration import TaskExecutionReview
    mission = await _mission(cw)
    task = await mission.task("review continuation")
    await mission.baseline([task.id])
    execution_id = await _verified_execution(task, f"db:project_task:{task.id}")
    reviewer = await cw.agent("reviewer")
    member_id = await _member(mission.project_id, reviewer, role="reviewer", can_review=True)
    source_id = await _queued_demand(task, reviewer, "/root/project/canonical", dispatch_status="completed")
    async with AsyncSessionLocal() as db:
        review = TaskExecutionReview(execution_id=execution_id, reviewer_membership_id=member_id,
            status="running", runtime_session_ref=str(source_id))
        db.add(review)
        question = await agent_questions.create_question(db, await db.get(Agent, reviewer),
            question="Which checks?", blocking=True, origin_demand_id=source_id)
        await db.commit()
        answer = await agent_questions.record_answer(db, question, "Check the fixtures", via="screen", by="test")
        assert answer.task_execution_id is None, "A review answer is not a new delivery attempt"
        assert review.runtime_session_ref == str(answer.id)
        assert await db.scalar(select(func.count(TaskExecution.id)).where(TaskExecution.task_id == task.id)) == 1
        from app.core.question_continuations import prepare_answer_context
        await prepare_answer_context(db, answer)
        assert "Check the fixtures" in answer.body


@pytest.mark.asyncio
async def test_answer_execution_link_uses_target_execution_and_retains_context(cw):
    mission = await _mission(cw)
    context_task = await mission.task("completed contextual predecessor")
    actual_task = await mission.task("actual ongoing delivery")
    await mission.baseline([context_task.id, actual_task.id])
    previous_id = await _verified_execution(actual_task, f"db:project_task:{actual_task.id}")
    source_id = await _queued_demand(context_task, mission.executor, "/root/project/canonical",
        task_execution_id=previous_id, dispatch_status="failed", dispatch_error="STATUS: BLOCKED")
    async with AsyncSessionLocal() as db:
        (await db.get(ProjectTask, context_task.id)).status = "done"
        (await db.get(TaskExecution, previous_id)).status = "failed"
        question = await agent_questions.create_question(db, await db.get(Agent, mission.executor),
            question="Which output?", blocking=True, origin_demand_id=source_id)
        await db.commit()
        answer = await agent_questions.record_answer(db, question, "CSV", via="screen", by="test")
        assert answer.origin_id == actual_task.id and answer.status != "archived"
        assert answer.reply_to_id == source_id
        assert (await db.get(TaskExecution, answer.task_execution_id)).task_id == actual_task.id
        from app.core.question_continuations import prepare_answer_context
        await prepare_answer_context(db, answer)
