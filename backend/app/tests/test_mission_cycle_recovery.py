# ruff: noqa: F811
# Pytest injects fixtures imported from the existing domain test modules.
"""Mission event consumption must persist its resulting intent atomically."""
import pytest
from sqlalchemy import func, select

from app.core import mission_cycle
from app.db.base import AsyncSessionLocal
from app.db.models.mission import ProjectMission
from app.db.models.operations import AgentRoutine, AgentRoutineRun
from app.tests.test_mission_cycle import cw, _active_with_routine  # noqa: F401
from app.tests.test_mission_dispatch import runner, world  # noqa: F401


@pytest.mark.asyncio
async def test_failed_cycle_request_does_not_consume_event_cursor(cw, monkeypatch):
    mission = await _active_with_routine(cw)
    pid = mission.project_id
    async with AsyncSessionLocal() as db:
        original_cursor = (await db.get(ProjectMission, pid)).cycle_event_cursor

    async def events(*_args): return ["task outcome"]
    async def crash(*_args, **_kwargs):
        raise RuntimeError("crash before durable cycle intent")
    async def watchdog(*_args): return []
    monkeypatch.setattr(mission_cycle, "detect_events", events)
    monkeypatch.setattr(mission_cycle, "request_mission_cycle", crash)
    monkeypatch.setattr(mission_cycle, "run_mission_cycle_watchdog", watchdog)

    async with AsyncSessionLocal() as db:
        await mission_cycle.run_mission_cycle_pass(db, project_ids=[pid])
    async with AsyncSessionLocal() as db:
        assert (await db.get(ProjectMission, pid)).cycle_event_cursor == original_cursor


@pytest.mark.asyncio
async def test_uncommitted_cycle_intent_rolls_back_without_waking_dispatch(cw, monkeypatch):
    mission = await _active_with_routine(cw)
    pid = mission.project_id
    wakes = []
    monkeypatch.setattr("app.core.dispatch_signal.wake_scheduled_dispatch", lambda: wakes.append(True))
    count_runs = select(func.count(AgentRoutineRun.id)).join(AgentRoutine).where(
        AgentRoutine.mission_project_id == pid)
    async with AsyncSessionLocal() as db:
        original_count = await db.scalar(count_runs)
        assert await mission_cycle.request_mission_cycle(db, pid, "test", commit=False) == "started"
        await db.rollback()
    assert wakes == []
    async with AsyncSessionLocal() as db:
        assert await db.scalar(count_runs) == original_count
        assert await mission_cycle.request_mission_cycle(db, pid, "test") == "started"
        assert await db.scalar(count_runs) == original_count + 1
    assert wakes == [True]


@pytest.mark.asyncio
async def test_decision_key_rejects_changed_reason_and_parameters(cw):
    import uuid
    mission = await _active_with_routine(cw)
    body = {"action": "defer", "reason": "Wait for dependency", "params": {},
            "idempotency_key": f"m08-{cw.tag}-{uuid.uuid4().hex}"}
    path = f"/api/v1/missions/{mission.project_id}/decisions"
    async with cw.client() as client:
        original = await client.post(path, json=body)
        assert original.status_code == 201, original.text
        replay = await client.post(path, json=body)
        assert replay.status_code == 200
        assert replay.json()["id"] == original.json()["id"]
        changed = await client.post(path, json={**body, "reason": "Different decision"})
        assert changed.status_code == 409, changed.text
        changed = await client.post(path, json={**body, "params": {"command_text": "different scope"}})
        assert changed.status_code == 409, changed.text


@pytest.mark.asyncio
async def test_decision_replay_precedes_context_freshness_check(cw):
    import uuid
    from app.core.mission_cycle import latest_context_version
    mission = await _active_with_routine(cw)
    async with AsyncSessionLocal() as db:
        latest = await latest_context_version(db, mission.project_id)
        expected = latest.version if latest else 0
    body = {"action": "defer", "reason": "Wait", "expected_context_version": expected,
            "idempotency_key": f"m08-{cw.tag}-{uuid.uuid4().hex}"}
    path = f"/api/v1/missions/{mission.project_id}/decisions"
    async with cw.client() as client:
        first = await client.post(path, json=body)
        assert first.status_code == 201, first.text
        replay = await client.post(path, json=body)
        assert replay.status_code == 200, replay.text
        stale = await client.post(path, json={**body, "idempotency_key": f"m08-{cw.tag}-{uuid.uuid4().hex}"})
        assert stale.status_code == 409, stale.text
        assert stale.json()["detail"]["code"] == "CONTEXT_VERSION_STALE"


@pytest.mark.asyncio
async def test_assignment_and_outer_decision_roll_back_together(cw, monkeypatch):
    import uuid
    from app.api.routes import mission_cycle as routes
    from app.db.models.task import TaskAssignment
    from app.tests.test_mission_base import _member
    from app.tests.test_mission_cycle import _baselined
    mission = await _active_with_routine(cw)
    [task] = await _baselined(mission, "atomic assignment")
    candidate = await cw.agent("replacement")
    await _member(mission.project_id, candidate)

    async def crash(*_args, **_kwargs):
        raise RuntimeError("crash before decision completion")
    monkeypatch.setattr(routes, "write_context_version", crash)
    body = {"action": "reassign", "reason": "Replace unavailable executor", "task_id": str(task.id),
            "params": {"agent_id": str(candidate)}, "idempotency_key": f"m08-{cw.tag}-{uuid.uuid4().hex}"}
    async with cw.client() as client:
        with pytest.raises(RuntimeError, match="crash before decision completion"):
            await client.post(f"/api/v1/missions/{mission.project_id}/decisions", json=body)
    async with AsyncSessionLocal() as db:
        assigned = await db.scalar(select(TaskAssignment.id).where(
            TaskAssignment.task_id == task.id, TaskAssignment.agent_id == candidate))
        assert assigned is None


@pytest.mark.asyncio
async def test_dispatch_replay_completes_outer_audit_without_starting_another_run(cw, monkeypatch):
    import asyncio
    import uuid
    from app.api.routes import mission_cycle as routes
    from app.tests.test_mission_cycle import _baselined
    mission = await _active_with_routine(cw)
    [task] = await _baselined(mission, "recover accepted dispatch")
    original_writer = routes.write_context_version
    async def crash(*_args, **_kwargs):
        raise RuntimeError("crash after accepted dispatch")
    monkeypatch.setattr(routes, "write_context_version", crash)
    body = {"action": "dispatch", "reason": "Execute", "task_id": str(task.id),
            "idempotency_key": f"m08-{cw.tag}-{uuid.uuid4().hex}"}
    path = f"/api/v1/missions/{mission.project_id}/decisions"
    async with cw.client() as client:
        with pytest.raises(RuntimeError, match="crash after accepted dispatch"):
            await client.post(path, json=body)
        assert len(cw.runner.runs) == 1
        from app.db.models.mission import MissionDecision
        async with AsyncSessionLocal() as db:
            interrupted = await db.scalar(select(MissionDecision).where(
                MissionDecision.mission_project_id == mission.project_id,
                MissionDecision.idempotency_key == body["idempotency_key"]))
            assert interrupted.status == "pending"
        monkeypatch.setattr(routes, "write_context_version", original_writer)
        replay, concurrent_replay = await asyncio.gather(client.post(path, json=body), client.post(path, json=body))
        assert replay.status_code == 200, replay.text
        assert concurrent_replay.status_code == 200, concurrent_replay.text
        assert replay.json()["id"] == concurrent_replay.json()["id"]
        assert replay.json()["demand_id"] is not None
        assert replay.json()["facts"]["context_version"] >= 1
        assert len(cw.runner.runs) == 1
    from app.db.models.governance import AuditEvent
    async with AsyncSessionLocal() as db:
        audits = await db.scalar(select(func.count(AuditEvent.id)).where(
            AuditEvent.entity_id == mission.project_id,
            AuditEvent.event_type == "mission_decision_dispatch"))
        assert audits == 1


@pytest.mark.asyncio
async def test_new_agent_decision_requires_explicit_context_version(cw):
    import uuid
    from app.tests.test_mission_cycle import _orch_headers
    mission = await _active_with_routine(cw)
    headers = await _orch_headers(cw, mission)
    body = {"action": "defer", "reason": "Wait", "idempotency_key": f"m08-{cw.tag}-{uuid.uuid4().hex}"}
    async with cw.client(headers) as client:
        response = await client.post(f"/api/v1/missions/{mission.project_id}/decisions", json=body)
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "CONTEXT_VERSION_REQUIRED"


@pytest.mark.asyncio
async def test_ambiguous_host_acceptance_preserves_pending_decision_and_run(cw, monkeypatch):
    import uuid
    import httpx
    from app.api.routes import demand as demand_routes
    from app.db.models.mission import MissionDecision
    from app.tests.test_mission_cycle import _baselined
    mission = await _active_with_routine(cw)
    [task] = await _baselined(mission, "ambiguous acceptance")
    original_dispatch = demand_routes.dispatch_agent_run
    async def accept_then_timeout(*args, **kwargs):
        await original_dispatch(*args, **kwargs)
        raise httpx.ReadTimeout("response lost after acceptance")
    monkeypatch.setattr(demand_routes, "dispatch_agent_run", accept_then_timeout)
    body = {"action": "dispatch", "reason": "Execute", "task_id": str(task.id),
            "idempotency_key": f"m08-{cw.tag}-{uuid.uuid4().hex}"}
    path = f"/api/v1/missions/{mission.project_id}/decisions"
    async with cw.client() as client:
        first = await client.post(path, json=body)
        assert first.status_code == 502, first.text
        async with AsyncSessionLocal() as db:
            decision = await db.scalar(select(MissionDecision).where(
                MissionDecision.mission_project_id == mission.project_id,
                MissionDecision.idempotency_key == body["idempotency_key"]))
            assert decision.status == "pending"
        replay = await client.post(path, json=body)
        assert replay.status_code == 200, replay.text
        assert replay.json()["demand_id"] is not None
        assert len(cw.runner.runs) == 1


@pytest.mark.asyncio
async def test_pause_and_outer_decision_roll_back_together(cw, monkeypatch):
    import uuid
    from app.api.routes import mission_cycle as routes
    mission = await _active_with_routine(cw)
    async def crash(*_args, **_kwargs):
        raise RuntimeError("crash before pause decision completion")
    monkeypatch.setattr(routes, "write_context_version", crash)
    body = {"action": "pause", "reason": "blocked: executor unavailable",
            "idempotency_key": f"m08-{cw.tag}-{uuid.uuid4().hex}"}
    async with cw.client() as client:
        with pytest.raises(RuntimeError, match="crash before pause decision completion"):
            await client.post(f"/api/v1/missions/{mission.project_id}/decisions", json=body)
    async with AsyncSessionLocal() as db:
        assert (await db.get(ProjectMission, mission.project_id)).state == "active"


@pytest.mark.asyncio
async def test_integration_queue_and_outer_decision_roll_back_together(cw, tmp_path, bind_evidence_bridge, monkeypatch):
    import uuid
    from app.api.routes import mission_cycle as routes
    from app.db.models.demand import AgentDemand
    from app.tests.test_mission_cycle import _integration_world
    mission, task, execution_id, _repo = await _integration_world(cw, tmp_path, bind_evidence_bridge)
    wakes = []
    monkeypatch.setattr("app.core.dispatch_signal.wake_scheduled_dispatch", lambda: wakes.append(True))
    async def crash(*_args, **_kwargs):
        raise RuntimeError("crash before integration decision completion")
    monkeypatch.setattr(routes, "write_context_version", crash)
    body = {"action": "integrate", "reason": "Integrate approved change", "task_id": str(task.id),
            "params": {"execution_id": str(execution_id)},
            "idempotency_key": f"m08-{cw.tag}-{uuid.uuid4().hex}"}
    async with cw.client() as client:
        with pytest.raises(RuntimeError, match="crash before integration decision completion"):
            await client.post(f"/api/v1/missions/{mission.project_id}/decisions", json=body)
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(AgentDemand.id).where(AgentDemand.channel_ref == f"integrate:{task.id}")) is None
    assert wakes == []
