"""Execute release-check SQL against synthetic CTEs in the isolated PostgreSQL.

These fixtures contain no operational records or secret values. They verify
the actual SQL's time windows/eligibility as well as its final Python verdict.
"""
import importlib.util
import json
from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone
import uuid

import pytest
from sqlalchemy import delete, select, text

from app.db.base import AsyncSessionLocal

SOURCE = Path(__file__).resolve().parents[3] / 'ops/athos/checklist_verifier.py'
SPEC = importlib.util.spec_from_file_location('sql_fixture_verifier', SOURCE)
v = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = v
SPEC.loader.exec_module(v)


async def evaluate_query(monkeypatch, fn, seed, ctes):
    queries = []
    monkeypatch.setattr(v, 'psql', lambda query, *args: queries.append(query) or json.dumps(seed))
    fn()
    assert len(queries) == 1
    query = queries[0].replace('company.', 'audit_fixture_')
    query = 'WITH ' + ctes + ',' + query.lstrip()[5:] if query.lstrip().startswith('WITH ') else 'WITH ' + ctes + ' ' + query
    async with AsyncSessionLocal() as db:
        data = (await db.execute(text(query))).scalar_one()
    if isinstance(data, str):
        data = json.loads(data)
    monkeypatch.setattr(v, 'psql', lambda *args: json.dumps(data))
    return fn()


@pytest.mark.asyncio
@pytest.mark.parametrize('changes,healthy', [
    ({'dispatch_status': "'running'", 'dispatch_deadline_at': "now()-interval '1 minute'"}, False),
    ({'dispatch_status': "'running'"}, False),
    ({'dispatch_status': "'completed'", 'updated_at': "now()-interval '20 minutes'"}, False),
    ({'dispatch_status': "'completed'", 'status': "'archived'", 'updated_at': "now()-interval '20 minutes'"}, True),
    ({'dispatch_status': "'completed'", 'channel': "'agent'", 'updated_at': "now()-interval '20 minutes'"}, True),
    ({'dispatch_status': "'failed'", 'channel': "'agent'", 'from_agent_id': "'00000000-0000-0000-0000-000000000002'::uuid", 'updated_at': "now()-interval '20 minutes'"}, False),
    ({'scheduled_at': "now()-interval '20 minutes'"}, False),
    ({'scheduled_at': "now()-interval '20 minutes'", 'executor_wait_checked_at': 'now()'}, True),
    ({'scheduled_at': "now()+interval '1 hour'"}, True),
])
async def test_messages_actual_sql_keeps_old_obligations_and_legitimate_waits(monkeypatch, changes, healthy):
    row = {
        'created_at': "now()-interval '10 days'", 'dispatch_status': 'NULL::text',
        'dispatch_deadline_at': 'NULL::timestamptz', 'origin_type': "'task'", 'status': "'new'",
        'consolidated_into_id': 'NULL::uuid', 'agent_run_id': 'NULL::text',
        'target_agent_id': "'00000000-0000-0000-0000-000000000001'::uuid",
        'scheduled_at': 'NULL::timestamptz', 'executor_wait_checked_at': 'NULL::timestamptz',
        'feedback_sent_at': 'NULL::timestamptz', 'updated_at': 'now()',
        'channel': "'web'", 'from_agent_id': 'NULL::uuid',
    } | changes
    cte = 'audit_fixture_agent_demands AS (SELECT ' + ','.join(f'{value} AS {key}' for key,value in row.items()) + ')'
    seed = dict(total=0,failed=0,overdue=0,missing_deadlines=0,queued_due=0,unchecked_due=0,feedback_overdue=0)
    result = await evaluate_query(monkeypatch,v.check_messages_health,seed,cte)
    assert result.ok is healthy, result.notes


@pytest.mark.asyncio
@pytest.mark.parametrize('event_delay,event_agent,healthy', [
    ('2 minutes', '00000000-0000-0000-0000-000000000001', True),
    ('10 minutes', '00000000-0000-0000-0000-000000000001', False),
    ('2 minutes', '00000000-0000-0000-0000-000000000002', False),
])
async def test_activity_actual_sql_requires_delivery_for_the_correct_agent_and_window(monkeypatch,event_delay,event_agent,healthy):
    ctes = f"""
        audit_fixture_agents AS (SELECT '00000000-0000-0000-0000-000000000001'::uuid id,
            true is_active, 'active'::text status, 'hermes'::text runtime_type),
        audit_fixture_agent_demands AS (SELECT '00000000-0000-0000-0000-000000000001'::uuid target_agent_id,
            now()-interval '20 minutes' dispatched_at, 'completed'::text dispatch_status),
        audit_fixture_agent_activity_events AS (SELECT '{event_agent}'::uuid agent_id,
            'hermes'::text runtime, 'turn_started'::text kind,
            now()-interval '20 minutes'+interval '{event_delay}' created_at)
    """
    seed = dict(active_profiles=1,recently_executed=1,missing_delivery=0)
    result = await evaluate_query(monkeypatch,v.check_outbound_hooks,seed,ctes)
    assert result.ok is healthy, result.notes


@pytest.mark.asyncio
async def test_examined_queue_stamp_preserves_content_timestamp():
    from app.api.routes.demand import mark_dispatch_queue_examined
    from app.db.models.agent import Agent
    from app.db.models.demand import AgentDemand
    agent = Agent(name=f'audit-fixture-{uuid.uuid4().hex}',agent_type='executor')
    moment = datetime.now(timezone.utc)
    original = moment-timedelta(hours=1)
    async with AsyncSessionLocal() as db:
        db.add(agent)
        await db.flush()
        demand = AgentDemand(from_agent='test-auditor',subject='Queue observation fixture',body='Synthetic fixture',
                             target_agent_id=agent.id,origin_type='task',scheduled_at=original,updated_at=original)
        db.add(demand)
        await db.commit()
    try:
        async with AsyncSessionLocal() as db:
            await mark_dispatch_queue_examined(db,[demand.id],moment)
        async with AsyncSessionLocal() as db:
            observed = await db.scalar(select(AgentDemand).where(AgentDemand.id==demand.id))
            assert observed.executor_wait_checked_at == moment
            assert observed.updated_at == original
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AgentDemand).where(AgentDemand.id==demand.id))
            await db.execute(delete(Agent).where(Agent.id==agent.id))
            await db.commit()
