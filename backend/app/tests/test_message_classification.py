"""Read-only classification uses current authority, execution state and proof."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete

from app.core.demand_workflow import approval_fingerprint
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.mission_cycle import AgentAvailability
from app.db.models.operations import AgentQuestion
from app.tests.fixtures.demand_cleanup import cleanup_agent_demands


@pytest.fixture
async def classification_db():
    async with AsyncSessionLocal() as db:
        agent = Agent(name='Classification fixture', agent_type='executor', runtime_type='codex',
                      profile_slug='classification-' + uuid.uuid4().hex[:12])
        db.add(agent)
        await db.commit()
        agent_id = agent.id
        try:
            yield db, agent_id
        finally:
            await db.rollback()
            await db.execute(delete(AgentQuestion).where(AgentQuestion.agent_id == agent_id))
            await cleanup_agent_demands(db, [agent_id])
            await db.execute(delete(AgentAvailability).where(AgentAvailability.agent_id == agent_id))
            await db.execute(delete(Agent).where(Agent.id == agent_id))
            await db.commit()


async def work(db, agent, **overrides):
    values = dict(from_agent='classification', from_agent_id=agent, target_agent_id=agent,
        subject='Classification ' + uuid.uuid4().hex, body='A bounded operation', origin_type='task',
        working_path='/root/project/fixture')
    values.update(overrides)
    row = AgentDemand(**values)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def classify(db, *rows):
    from app.core.message_classification import classify_messages
    return await classify_messages(db, list(rows))


def quota(agent, **overrides):
    values = dict(agent_id=agent, unavailable_until=datetime.now(timezone.utc) + timedelta(hours=1),
                  reason='Usage limit', recorded_by='forgehub:usage-limit')
    values.update(overrides)
    return AgentAvailability(**values)


async def test_pending_authorization_precedes_quota_rejected_not_a_new_decision(classification_db):
    db, agent = classification_db
    pending = await work(db, agent, requires_approval=True, approval_status='pending')
    rejected = await work(db, agent, requires_approval=True, approval_status='rejected')
    db.add(quota(agent))
    await db.commit()
    result = await classify(db, pending, rejected)
    assert result[pending.id]['operator_decision'] == 'authorization'
    assert result[pending.id]['operator_destination'] == 'agent_tasks'
    assert result[pending.id]['execution_wait_reason'] is None
    assert 'authorization_pending' in result[pending.id]['message_labels']
    assert result[rejected.id]['operator_decision'] is None
    assert result[rejected.id]['execution_wait_reason'] is None


async def test_quota_unassigned_and_expired_quota(classification_db):
    db, agent = classification_db
    row = await work(db, agent)
    unassigned = await work(db, agent, target_agent_id=None)
    availability = quota(agent)
    db.add(availability)
    await db.commit()
    result = await classify(db, row, unassigned)
    assert result[row.id]['execution_wait_reason'] == 'quota'
    assert result[row.id]['execution_wait_until'] == availability.unavailable_until
    assert result[row.id]['message_labels'][:2] == ['awaiting_executor', 'quota_unavailable']
    assert result[unassigned.id]['execution_wait_reason'] == 'unassigned'
    availability.unavailable_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db.commit()
    current = (await classify(db, row))[row.id]
    assert current['execution_wait_reason'] is None
    assert 'quota_unavailable' not in current['message_labels']


async def test_active_busy_and_uncertain_are_distinct(classification_db):
    db, agent = classification_db
    active = await work(db, agent, dispatch_status='running', agent_run_id=str(uuid.uuid4()))
    waiting = await work(db, agent)
    uncertain = await work(db, agent, dispatch_status='failed', agent_run_id=str(uuid.uuid4()),
                           dispatch_error='Outcome uncertain')
    result = await classify(db, active, waiting, uncertain)
    assert result[active.id]['message_labels'] == ['running']
    assert result[active.id]['execution_wait_reason'] is None
    assert result[waiting.id]['execution_wait_reason'] == 'busy'
    assert result[uncertain.id]['message_labels'] == ['uncertain_execution']
    assert result[uncertain.id]['execution_wait_reason'] is None


async def test_exact_delivery_suppresses_quota_but_changed_scope_does_not(classification_db):
    db, agent = classification_db
    row = await work(db, agent)
    db.add_all([quota(agent), AuditEvent(entity_type='agent_demand', entity_id=row.id,
        event_type='message_delivery_verified', actor='operator', payload={
            'content_hash': approval_fingerprint(row), 'summary': 'Evidence checked', 'evidence_ref': 'git:1234567'})])
    await db.commit()
    current = (await classify(db, row))[row.id]
    assert current['message_labels'] == ['delivery_verified']
    assert current['execution_wait_reason'] is None
    row.body = 'A new scope needs another delivery'
    await db.commit()
    await db.refresh(row)
    assert (await classify(db, row))[row.id]['execution_wait_reason'] == 'quota'


async def test_question_destinations_use_actual_incubation_and_moodle_links(classification_db):
    from app.db.models.moodle_approval import MoodleApproval
    db, agent = classification_db
    incubation = await work(db, agent, origin_type='incubation', incubation_owner_id=agent,
                            incubation_state='decision_pending')
    moodle = await work(db, agent)
    for row in (incubation, moodle):
        db.add(AgentQuestion(agent_id=agent, origin_demand_id=row.id, question='Confirm destination?',
            blocking=True, status='pending', notify_after=datetime.now(timezone.utc)))
    db.add(MoodleApproval(message_id=moodle.id, request_id=uuid.uuid4(), source_agent_id=agent,
        params_hash='a'*64, state='approved', executor_id=agent, message_hash=approval_fingerprint(moodle),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
    await db.commit()
    result = await classify(db, incubation, moodle)
    assert result[incubation.id]['operator_decision'] == 'question'
    assert result[incubation.id]['operator_destination'] == 'incubations'
    assert result[moodle.id]['operator_decision'] == 'question'
    assert result[moodle.id]['operator_destination'] == 'moodle_approvals'
    assert result[incubation.id]['operator_question_id'] is not None
    assert result[moodle.id]['operator_question_id'] is not None
    assert 'decision_pending' in result[incubation.id]['message_labels']


async def test_future_schedule_and_inactive_executor(classification_db):
    db, agent = classification_db
    scheduled = await work(db, agent, scheduled_at=datetime.now(timezone.utc) + timedelta(days=2))
    unavailable = await work(db, agent)
    executor = await db.get(Agent, agent)
    executor.is_active = False
    await db.commit()
    result = await classify(db, scheduled, unavailable)
    assert result[scheduled.id]['message_labels'] == ['scheduled']
    assert result[scheduled.id]['execution_wait_reason'] is None
    assert result[unavailable.id]['execution_wait_reason'] == 'unavailable'


async def cache_analysis(db, row, category='service'):
    from app.core.message_triage_context import context_stamp, source_stamp
    from app.db.models.message_triage import MessageTriageResult
    context, versions = await context_stamp(db, row)
    cached = MessageTriageResult(message_id=row.id, source_updated_at=row.updated_at,
        source_fingerprint=source_stamp(row), context_fingerprint=context, context_versions=versions,
        operator_state='waiting', category=category, summary='A bounded advisory finding',
        reason='Known linked facts', recommendation='Check conditions', proposed_action='none',
        evidence_refs=[], analyzed_at=datetime.now(timezone.utc))
    db.add(cached)
    await db.commit()
    return cached


async def test_cached_service_advice_expires_when_linked_availability_changes(classification_db):
    db, agent = classification_db
    row = await work(db, agent)
    await cache_analysis(db, row)
    assert (await classify(db, row))[row.id]['message_labels'] == ['awaiting_service']
    db.add(quota(agent))
    await db.commit()
    current = (await classify(db, row))[row.id]
    assert current['execution_wait_reason'] == 'quota'
    assert 'awaiting_service' not in current['message_labels']


@pytest.mark.parametrize('category,expected', [('duplicate', 'possible_duplicate'), ('obsolete', 'possible_obsolete')])
async def test_advisory_related_work_never_claims_verified_completion(classification_db, category, expected):
    db, agent = classification_db
    row = await work(db, agent)
    await cache_analysis(db, row, category)
    current = (await classify(db, row))[row.id]
    assert current['message_labels'] == [expected]
    assert current['operator_decision'] is None
    row.body = 'Edited after observation'
    await db.commit()
    await db.refresh(row)
    assert (await classify(db, row))[row.id]['message_labels'] == ['analysis_pending']


async def test_stale_approval_fingerprint_and_answered_question(classification_db):
    db, agent = classification_db
    row = await work(db, agent, requires_approval=True, approval_status='approved')
    row.approved_content_hash = approval_fingerprint(row)
    await db.commit()
    db.add(quota(agent))
    await db.commit()
    assert (await classify(db, row))[row.id]['execution_wait_reason'] == 'quota'
    row.body = 'Authorization covered a different scope'
    await db.commit()
    await db.refresh(row)
    assert (await classify(db, row))[row.id]['operator_decision'] == 'authorization'
    row.requires_approval = False
    question = AgentQuestion(agent_id=agent, origin_demand_id=row.id, question='Which destination?',
        status='pending', blocking=True, notify_after=datetime.now(timezone.utc))
    db.add(question)
    await db.commit()
    assert (await classify(db, row))[row.id]['operator_decision'] == 'question'
    question.status = 'answered'
    question.answer = 'Destination confirmed'
    question.answered_at = datetime.now(timezone.utc)
    question.answered_by = 'classification-test'
    await db.commit()
    current = (await classify(db, row))[row.id]
    assert current['operator_decision'] is None and current['execution_wait_reason'] == 'quota'


async def test_manual_executor_hold_is_not_misreported_as_quota(classification_db):
    db, agent = classification_db
    row = await work(db, agent)
    db.add(quota(agent, recorded_by='operator', reason='Maintenance window'))
    await db.commit()
    current = (await classify(db, row))[row.id]
    assert current['execution_wait_reason'] == 'unavailable'
    assert 'quota_unavailable' not in current['message_labels']


async def test_batch_query_count_does_not_grow_per_message(classification_db):
    from sqlalchemy import event
    from app.db.base import engine
    db, agent = classification_db
    rows = [await work(db, agent) for _ in range(26)]
    counts = []
    def record(*args):
        counts.append(True)
    event.listen(engine.sync_engine, 'before_cursor_execute', record)
    try:
        await classify(db, rows[0])
        one = len(counts)
        counts.clear()
        result = await classify(db, *rows)
        assert len(result) == 26 and len(counts) == one
        assert one <= 10
    finally:
        event.remove(engine.sync_engine, 'before_cursor_execute', record)


async def test_get_list_and_detail_expose_additive_metadata(classification_db, admin_headers):
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    db, agent = classification_db
    row = await work(db, agent, target_agent_id=None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test', headers=admin_headers) as client:
        detail = await client.get(f'/api/v1/demands/{row.id}')
        assert detail.status_code == 200, detail.text
        payload = detail.json()
        assert payload['execution_wait_reason'] == 'unassigned'
        assert payload['message_labels'] == ['awaiting_executor', 'executor_unassigned']
        listed = await client.get('/api/v1/demands')
        assert listed.status_code == 200, listed.text
        item = next(item for item in listed.json() if item['id'] == str(row.id))
        assert item['message_labels'] == payload['message_labels']
        assert item['operator_destination'] is None


async def test_manual_archive_is_archived_even_when_failed_attempt_is_unverified(classification_db):
    db, agent = classification_db
    row = await work(db, agent, status='archived', dispatch_status='failed',
                     dispatch_error='quota exhausted', dispatch_attempts=1)
    current = (await classify(db, row))[row.id]
    assert current['message_labels'] == ['archived']
    assert current['operator_decision'] is None
    assert row.dispatch_status == 'failed'
    assert row.dispatch_error == 'quota exhausted'


async def test_unexecuted_reply_continuation_is_not_labeled_completed(classification_db):
    db, agent = classification_db
    origin = await work(db, agent, dispatch_status='completed')
    continuation = await work(db, agent, reply_to_id=origin.id, dispatch_status=None,
                              command_text='Continue authorized question answer')
    current = (await classify(db, continuation))[continuation.id]
    assert 'completed' not in current['message_labels']
    assert current['operator_decision'] is None


async def test_incubation_owner_decision_is_not_operator_decision(classification_db):
    db, agent = classification_db
    row = await work(db, agent, origin_type='incubation', incubation_owner_id=agent,
                     incubation_state='decision_pending')
    current = (await classify(db, row))[row.id]
    assert current['operator_decision'] is None
    assert current['operator_destination'] is None
    assert 'decision_pending' not in current['message_labels']
