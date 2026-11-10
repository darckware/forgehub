# ruff: noqa: F811
"""24x7 supervision must preserve independent work beside legitimate waits."""
from datetime import datetime, timezone

import pytest

from app.core import mission_cycle
from app.db.base import AsyncSessionLocal
from app.db.models.mission import ProjectMission
from app.tests.test_mission_cycle import cw, _baselined, _orch_headers, _ask  # noqa: F401
from app.tests.test_mission_dispatch import runner, world  # noqa: F401
from app.tests.test_task_baseline_guard import _mission


@pytest.mark.asyncio
async def test_question_for_one_task_does_not_hide_independent_idle_work(cw):
    mission = await _mission(cw)
    held, free = await _baselined(mission, "waiting for a decision", "independent work")
    headers = await _orch_headers(cw, mission)
    response = await _ask(cw, mission, headers, [held], True)
    assert response.status_code == 201, response.text
    async with AsyncSessionLocal() as db:
        findings = await mission_cycle.watchdog_findings(db, await db.get(ProjectMission, mission.project_id),
                                                         datetime.now(timezone.utc))
    idle = next((f for f in findings if f["code"] == "MISSION_IDLE_WITHOUT_REASON"), None)
    assert idle is not None
    assert idle["open_tasks"] == 1
    assert idle["task_ids"] == [str(free.id)]


@pytest.mark.asyncio
async def test_active_task_does_not_hide_independent_idle_work(cw):
    from app.db.models.demand import AgentDemand
    mission = await _mission(cw)
    running, free = await _baselined(mission, "running", "independent idle")
    async with AsyncSessionLocal() as db:
        db.add(AgentDemand(subject="running", body="authorized task", from_agent="test",
                           origin_type="task", origin_id=running.id,
                           target_agent_id=mission.executor, dispatch_status="running"))
        await db.commit()
    async with AsyncSessionLocal() as db:
        findings = await mission_cycle.watchdog_findings(db, await db.get(ProjectMission, mission.project_id),
                                                         datetime.now(timezone.utc))
    idle = next((f for f in findings if f["code"] == "MISSION_IDLE_WITHOUT_REASON"), None)
    assert idle is not None
    assert idle["task_ids"] == [str(free.id)]


@pytest.mark.asyncio
async def test_planning_cycle_gap_is_supervised_and_recovered_once(cw):
    from datetime import timedelta
    from sqlalchemy import func, select
    from app.db.models.operations import AgentRoutine, AgentRoutineRun
    from app.tests.test_mission_cycle import _active_with_routine
    from app.tests.test_mission_base import _force
    mission = await _active_with_routine(cw)
    now = datetime.now(timezone.utc)
    await _force(mission.project_id, state="planning", planning_stage="draft_plan",
                 state_changed_at=now - timedelta(hours=2))
    count = select(func.count(AgentRoutineRun.id)).join(AgentRoutine).where(
        AgentRoutine.mission_project_id == mission.project_id)
    async with AsyncSessionLocal() as db:
        before = await db.scalar(count)
        first = await mission_cycle.run_mission_cycle_watchdog(db, now, [mission.project_id])
        second = await mission_cycle.run_mission_cycle_watchdog(db, now, [mission.project_id])
        assert any(f["code"] == "MISSION_CYCLE_GAP" and f.get("recovery") == "started" for f in first)
        assert await db.scalar(count) == before + 1
        assert not any(f.get("recovery") == "started" for f in second)
