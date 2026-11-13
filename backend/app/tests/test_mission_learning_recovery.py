"""Evidence-backed skill proposal and recovery from fresh canonical sessions."""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, func, select

from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.models.command_receipt import AgentCommandReceipt
from app.db.models.agent import AgentSkill
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.mission import MissionDecision
from app.db.models.mission_cycle import MissionSkillProposal
from app.db.models.orchestration import TaskExecutionReview
from app.db.models.task import ProjectTask, TaskAssignment, TaskExecution
from app.tests.test_mission_base import _member
from app.tests.test_mission_cycle import cw, _baselined, _key, _mission, _orch_headers, _verified_execution  # noqa: F401
from app.tests.test_mission_dispatch import runner, world  # noqa: F401


@pytest.mark.asyncio
async def test_learning_rejects_observation_then_preserves_reviewed_proposal_without_grant(cw, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, 'MISSION_LEARNING_ENABLED', True)
    mission = await _mission(cw)
    [task] = await _baselined(mission, 'learning-source')
    headers = await _orch_headers(cw, mission)
    skill = await cw.skill()
    execution_id = await _verified_execution(task, f'db:project_task:{task.id}')
    key = _key(cw)
    body = {'kind': 'grant_to_agent', 'skill_id': str(skill), 'agent_id': str(mission.executor),
            'reason': 'Propose an independently reviewed lesson', 'idempotency_key': key,
            'learning': {'source_execution_ids': [str(execution_id)],
                         'reproduction': 'Repeat the canonical database evidence check',
                         'lesson': 'Check the stored artifact before reporting the result',
                         'proposed_skill_version': '1.2.0', 'runtime_types': ['claude']}}
    proposal_id = None
    try:
        async with cw.client(headers) as client:
            observation = await client.post(f'/api/v1/missions/{mission.project_id}/skill-proposals', json=body)
            assert observation.status_code == 422, observation.text
            assert observation.json()['detail']['code'] == 'LEARNING_TASK_NOT_ACCEPTED'
            reviewer = await cw.agent('learning-reviewer')
            membership = await _member(mission.project_id, reviewer, can_review=True)
            async with AsyncSessionLocal() as db:
                db.add(TaskExecutionReview(execution_id=execution_id, reviewer_membership_id=membership,
                                          status='approved', decided_at=datetime.now(timezone.utc)))
                (await db.get(ProjectTask, task.id)).status = 'done'
                await db.commit()
            accepted = await client.post(f'/api/v1/missions/{mission.project_id}/skill-proposals', json=body)
            assert accepted.status_code == 201, accepted.text
            proposal_id = uuid.UUID(accepted.json()['id'])
            assert accepted.json()['learning']['status'] == 'evidence_verified_owner_review_pending'
            assert accepted.json()['status'] == 'proposed'
            replay = await client.post(f'/api/v1/missions/{mission.project_id}/skill-proposals', json=body)
            assert replay.status_code == 200 and replay.json()['id'] == str(proposal_id)
            changed = await client.post(f'/api/v1/missions/{mission.project_id}/skill-proposals', json={**body, 'reason': 'Different reason'})
            assert changed.status_code == 409, changed.text
        # New session represents recovery without local model/conversation state.
        async with AsyncSessionLocal() as db:
            proposal = await db.get(MissionSkillProposal, proposal_id)
            assert proposal.status == 'proposed'
            audit = await db.scalar(select(AuditEvent).where(AuditEvent.entity_type == 'mission_skill_proposal', AuditEvent.entity_id == proposal_id))
            assert audit.payload['proofs'][0]['execution_id'] == str(execution_id)
            assert audit.payload['publication'] == 'not_published'
            assert await db.scalar(select(func.count(AgentSkill.id)).where(AgentSkill.skill_id == skill)) == 0
    finally:
        if proposal_id:
            async with AsyncSessionLocal() as db:
                await db.execute(delete(AuditEvent).where(AuditEvent.entity_type == 'mission_skill_proposal', AuditEvent.entity_id == proposal_id))
                await db.commit()


@pytest.mark.asyncio
async def test_learning_field_refused_when_switched_off(cw, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, 'MISSION_LEARNING_ENABLED', False)
    mission = await _mission(cw)
    headers = await _orch_headers(cw, mission)
    body = {'kind': 'create_skill', 'reason': 'Learning while switched off', 'idempotency_key': _key(cw),
            'learning': {'source_execution_ids': [str(uuid.uuid4())],
                         'reproduction': 'Repeat the canonical database evidence check',
                         'lesson': 'Check the stored artifact before reporting the result',
                         'proposed_skill_version': '1.2.0', 'runtime_types': ['claude']}}
    async with cw.client(headers) as client:
        refused = await client.post(f'/api/v1/missions/{mission.project_id}/skill-proposals', json=body)
    assert refused.status_code == 422, refused.text
    assert refused.json()['detail']['code'] == 'MISSION_LEARNING_DISABLED'
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(func.count(MissionSkillProposal.id)).where(
            MissionSkillProposal.mission_project_id == mission.project_id)) == 0


@pytest.mark.asyncio
async def test_legacy_skill_proposal_without_request_hash_replays(cw):  # noqa: F811
    """A decision recorded before request hashes (and before receipts) replays
    by its key as it always did; it is never a 409."""
    mission = await _mission(cw)
    headers = await _orch_headers(cw, mission)
    key = _key(cw)
    body = {'kind': 'create_skill', 'reason': 'Legacy proposal', 'idempotency_key': key}
    async with cw.client(headers) as client:
        created = await client.post(f'/api/v1/missions/{mission.project_id}/skill-proposals', json=body)
        assert created.status_code == 201, created.text
        # Make it look like a pre-357e985 record: no receipt, no request_hash.
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AgentCommandReceipt).where(AgentCommandReceipt.idempotency_key == key))
            decision = await db.scalar(select(MissionDecision).where(MissionDecision.idempotency_key == f'skill:{key}'))
            decision.facts = {k: v for k, v in decision.facts.items() if k != 'request_hash'}
            await db.commit()
        replay = await client.post(f'/api/v1/missions/{mission.project_id}/skill-proposals',
                                   json={**body, 'reason': 'Legacy proposal, resent'})
        assert replay.status_code == 200, replay.text
        assert replay.headers.get('Idempotent-Replay') == 'true'
        assert replay.json()['id'] == created.json()['id']


@pytest.mark.asyncio
async def test_recovery_after_fresh_session_keeps_later_requirement_and_decision(cw):  # noqa: F811
    mission = await _mission(cw)
    [task] = await _baselined(mission, 'recovery-source')
    headers = None  # A human administrator can recover a run whose dispatch credential was revoked.
    run = str(uuid.uuid4())
    async with AsyncSessionLocal() as db:
        assignment = await db.scalar(select(TaskAssignment).where(TaskAssignment.task_id == task.id))
        execution = TaskExecution(task_id=task.id, assignment_id=assignment.id, status='running')
        db.add(execution)
        await db.flush()
        demand = AgentDemand(from_agent='test-suite', subject='Recovery', body='Synthetic only',
                             target_agent_id=mission.executor, status='read', origin_type='task', origin_id=task.id,
                             task_execution_id=execution.id, agent_run_id=run, dispatch_status='failed',
                             dispatch_error='Runner acknowledgement uncertain; reconcile this run')
        db.add(demand)
        (await db.get(ProjectTask, task.id)).plan_brief = 'Later requirement: preserve the exact task identity after restart.'
        db.add(MissionDecision(mission_project_id=mission.project_id, task_id=task.id, action='defer',
                               reason='Later decision: review the original artifact first', facts={}, autonomy_level='N0',
                               actor_type='user', actor_id=uuid.uuid4(), actor_name='test', authority_source='admin',
                               status='deferred', idempotency_key=_key(cw)))
        await db.commit()
        number = demand.number
    async with cw.client(headers) as client:
        pack = await client.get(f'/api/v1/missions/{mission.project_id}/tasks/{task.id}/context', params={'message_number': number})
        assert pack.status_code == 200, pack.text
        assert 'Later requirement' in pack.json()['context']
        assert any('Later decision' in d['reason'] for d in pack.json()['decisions'])
        assert pack.json()['current_baseline_id'] is not None
        assert pack.json()['attempts'][0]['id'] == str(execution.id)
        assert pack.json()['next_step'] == 'reconcile_original_run'
        # Administrator access stays bound to this explicit canonical task.
        other_number = await client.get(f'/api/v1/missions/{mission.project_id}/tasks/{task.id}/context', params={'message_number': number + 100000})
        assert other_number.status_code == 200 and other_number.json()['task_id'] == str(task.id)


@pytest.mark.asyncio
async def test_admin_recovery_pack_flags_reconciling_work_package_without_demand(cw):  # noqa: F811
    mission = await _mission(cw)
    [task] = await _baselined(mission, 'work-package-recovery')
    run_id = str(uuid.uuid4())
    async with AsyncSessionLocal() as db:
        execution = TaskExecution(task_id=task.id, status='reconciling', runtime_session_ref=run_id)
        db.add(execution)
        await db.commit()
        execution_id = execution.id
    async with cw.client() as client:
        pack = await client.get(f'/api/v1/missions/{mission.project_id}/tasks/{task.id}/context')
    assert pack.status_code == 200, pack.text
    assert pack.json()['next_step'] == 'reconcile_original_run'
    assert pack.json()['attempts'][0]['id'] == str(execution_id)


@pytest.mark.asyncio
async def test_recovery_pack_follows_mission_tools_switch(cw, monkeypatch):  # noqa: F811
    mission = await _mission(cw)
    [task] = await _baselined(mission, 'recovery-switch')
    monkeypatch.setattr(settings, 'MISSION_TOOLS_ENABLED', False)
    async with cw.client() as client:
        off = await client.get(f'/api/v1/missions/{mission.project_id}/tasks/{task.id}/context')
    assert off.status_code == 503, off.text
    assert off.json()['detail']['code'] == 'MISSION_TOOLS_DISABLED'
