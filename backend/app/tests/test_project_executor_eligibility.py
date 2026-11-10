# ruff: noqa: F811
"""Canonical project capabilities remain binding at dispatch admission."""
import uuid

import pytest

from app.core.agent_failover import executor_eligibility
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Skill
from app.db.models.demand import AgentDemand
from app.db.models.orchestration import ProjectAgentMembership
from app.db.models.task import TaskRequiredSkill
from app.tests.test_mission_cycle import cw  # noqa: F401
from app.tests.test_mission_dispatch import runner, world  # noqa: F401
from app.tests.test_mission_base import _member
from app.tests.test_task_baseline_guard import _mission, _queued_demand


@pytest.mark.asyncio
@pytest.mark.parametrize("case, code", [
    ("member", "EXECUTOR_PROJECT_MEMBERSHIP_REQUIRED"),
    ("runtime", "EXECUTOR_RUNTIME_NOT_ALLOWED"),
    ("skill", "EXECUTOR_SKILL_REQUIRED"),
])
async def test_project_contract_is_checked_for_current_executor(cw, case, code):
    mission = await _mission(cw)
    task = await mission.task("eligibility-" + uuid.uuid4().hex)
    candidate = await cw.agent("candidate")
    member_id = await _member(mission.project_id, candidate) if case != "member" else None
    demand_id = await _queued_demand(task, candidate, "/root/project/test")
    skill_id = None
    try:
        async with AsyncSessionLocal() as db:
            if case == "runtime":
                membership = await db.get(ProjectAgentMembership, member_id)
                membership.allowed_runtimes = ["hermes"]
            if case == "skill":
                skill = Skill(name="eligibility-" + uuid.uuid4().hex, version="1", origin="internal",
                    risk_level="low", permissions="repository", is_approved=True)
                db.add(skill)
                await db.flush()
                skill_id = skill.id
                db.add(TaskRequiredSkill(task_id=task.id, skill_id=skill.id, is_mandatory=True))
            await db.commit()
            demand = await db.get(AgentDemand, demand_id)
            reasons = await executor_eligibility(db, demand, candidate)
            assert code in {r["code"] for r in reasons}
    finally:
        if skill_id:
            from sqlalchemy import delete
            async with AsyncSessionLocal() as db:
                await db.execute(delete(TaskRequiredSkill).where(TaskRequiredSkill.skill_id == skill_id))
                await db.execute(delete(Skill).where(Skill.id == skill_id))
                await db.commit()


@pytest.mark.asyncio
async def test_reservation_rechecks_runtime_permission_after_selection(cw):
    from app.core.demand_dispatch_guard import reserve_dispatch
    from app.core.demand_workflow import WorkflowBlocked
    mission = await _mission(cw)
    task = await mission.task("changed runtime permission")
    await mission.baseline([task.id])
    demand_id = await _queued_demand(task, mission.executor, "/root/project/test")
    async with AsyncSessionLocal() as db:
        demand = await db.get(AgentDemand, demand_id)
        assert await executor_eligibility(db, demand, mission.executor) == []
        async with AsyncSessionLocal() as changed:
            membership = await changed.get(ProjectAgentMembership, mission.membership)
            membership.allowed_runtimes = ["hermes"]
            await changed.commit()
        with pytest.raises(WorkflowBlocked, match="EXECUTOR_RUNTIME_NOT_ALLOWED"):
            await reserve_dispatch(db, demand, mission.executor, None)


@pytest.mark.asyncio
async def test_author_cannot_become_independent_reviewer_at_admission(cw):
    from app.db.models.orchestration import TaskExecutionReview
    from app.tests.test_mission_cycle import _verified_execution
    mission = await _mission(cw)
    task = await mission.task("independent review")
    execution_id = await _verified_execution(task, f"db:project_task:{task.id}")
    demand_id = await _queued_demand(task, mission.executor, "/root/project/test")
    async with AsyncSessionLocal() as db:
        membership = await db.get(ProjectAgentMembership, mission.membership)
        membership.can_review = True
        db.add(TaskExecutionReview(execution_id=execution_id, reviewer_membership_id=membership.id,
            status="pending", runtime_session_ref=str(demand_id)))
        await db.commit()
        demand = await db.get(AgentDemand, demand_id)
        reasons = await executor_eligibility(db, demand, mission.executor)
        assert "EXECUTOR_CANNOT_REVIEW_OWN_WORK" in {r["code"] for r in reasons}
