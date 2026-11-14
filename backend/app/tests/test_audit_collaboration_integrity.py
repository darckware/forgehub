"""Actual Auditor SQL over fictitious CTEs; guarded/locked by tests/conftest.

No domain rows are inserted. Each query runs in a read-only transaction.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy import select

from app.core.secret_masking import mask_secrets
from app.db.base import AsyncSessionLocal
from app.db.models.governance import AuditEvent
from app.db.models.host_execution import HostExecution
from app.tests import test_remote_collaboration as remote_tests

# Reuse the isolated route fixtures and their cleanup without changing the
# remote executor's tests. The bridge remains the fixture's simulated bridge.
ctx = remote_tests.ctx

ROOT = Path(__file__).resolve().parents[3]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


m = load('auditor_integrity_health', ROOT / 'ops/athos/module_health.py')
v = load('auditor_integrity_verifier', ROOT / 'ops/athos/checklist_verifier.py')
CHECK = m.COLLABORATION_CHECK
NOW = '2026-11-14T12:00:00+00:00'

SCHEMAS = {
    'remote_collaboration_commands': 'id uuid, session_id uuid, command text, shell text, command_sha256 text, allow_elevation boolean, status text, used_at timestamptz, execution_id uuid, created_at timestamptz',
    'remote_collaboration_sessions': 'id uuid, agent_id uuid, agent_demand_id uuid, agent_run_id text, server_id uuid, owner_user_id uuid, allow_elevation boolean, created_at timestamptz, expires_at timestamptz, ended_at timestamptz',
    'host_executions': 'id uuid, agent_id uuid, agent_demand_id uuid, trigger text, shell text, command text, started_at timestamptz, finished_at timestamptz, status text',
    'host_execution_results': 'execution_id uuid, server_id uuid, started_at timestamptz, finished_at timestamptz, status text',
    'agent_demands': 'id uuid, number integer, agent_run_id text, target_agent_id uuid, status text',
    'audit_events': 'entity_type text, entity_id uuid, event_type text, payload jsonb, created_at timestamptz',
    'agent_routines': 'id uuid, kind text, audit_frequency text, schedule text, timezone text, enabled boolean, enabled_at timestamptz',
    'agent_routine_runs': 'routine_id uuid, status text, audit_batch_id uuid, created_at timestamptz, finished_at timestamptz, occurrence_at timestamptz, evidence_received boolean, no_action boolean',
    'audit_checks': 'id uuid, enabled boolean, frequency text',
    'audit_check_runs': 'check_id uuid, batch_id uuid, requested_by text, status text, created_at timestamptz',
}


def uid(number):
    return str(uuid.UUID(int=number))


def at(time):
    return f'2026-11-14T{time}+00:00'


async def execute(query, fixture):
    ctes = ', '.join(
        f"fx_{table} AS (SELECT * FROM jsonb_to_recordset(cast(:fixture AS jsonb)->'{table}') AS r({SCHEMAS[table]}))"
        for table in fixture)
    query = query.replace('company.', 'fx_').replace('now()', f"'{NOW}'::timestamptz")
    query = 'WITH ' + ctes + (', ' + query.lstrip()[5:] if query.lstrip().startswith('WITH ') else ' ' + query)
    async with AsyncSessionLocal() as db:
        await db.execute(text('SET TRANSACTION READ ONLY'))
        # Use the same raw SQL as the verifier with one bound fixture payload.
        connection = await db.connection()
        result = (await connection.exec_driver_sql(query.replace(':fixture', '$1'), (json.dumps(fixture),))).scalar_one()
    return json.loads(result) if isinstance(result, str) else result


@pytest.fixture
def history():
    command = 'printf hello'
    digest = hashlib.sha256(command.encode()).hexdigest()
    session = dict(id=uid(1), agent_id=uid(2), agent_demand_id=uid(3), agent_run_id='historical-run',
                   server_id=uid(4), owner_user_id=uid(5), allow_elevation=False,
                   created_at=at('10:00:00'), expires_at=at('11:00:00'), ended_at=at('10:04:00'))
    entry = dict(id=uid(6), session_id=uid(1), command=command, shell='sh', command_sha256=digest,
                 allow_elevation=False, status='used', used_at=at('10:02:01'), execution_id=uid(7), created_at=at('10:01:00'))
    execution = dict(id=uid(7), agent_id=uid(2), agent_demand_id=uid(3), trigger='agent', shell='sh',
                     command=command, started_at=at('10:02:00'), finished_at=at('10:03:00'), status='completed')
    events = []
    for entity, entity_id in [('remote_collaboration_session', uid(1)), ('server', uid(4))]:
        for event, timestamp, payload in [
            ('opened', at('10:00:00'), dict(agent_id=uid(2), message_number=42, agent_run_id='historical-run', allow_elevation=False)),
            ('command_authorized', at('10:01:00'), dict(command_id=uid(6), command_sha256=digest, shell='sh', allow_elevation=False)),
            ('command_run', at('10:02:00'), dict(command_id=uid(6), command_sha256=digest, execution_command_sha256=digest, execution_id=uid(7), server_id=uid(4), message_number=42, agent_run_id='historical-run', owner_user_id=uid(5))),
        ]:
            events.append(dict(entity_type=entity, entity_id=entity_id, event_type='remote_collaboration_' + event,
                               created_at=timestamp, payload=dict(session_id=uid(1), **payload)))
    events.append(dict(entity_type='host_execution', entity_id=uid(7), event_type='started', created_at=at('10:02:00'),
                       payload=dict(command=command, shell='sh', agent_id=uid(2), agent_demand_id=uid(3))))
    return dict(remote_collaboration_commands=[entry], remote_collaboration_sessions=[session],
                host_executions=[execution], host_execution_results=[dict(execution_id=uid(7), server_id=uid(4),
                status='succeeded', started_at=at('10:02:02'), finished_at=at('10:03:00'))],
                agent_demands=[dict(id=uid(3), number=42, agent_run_id='replaced-run', target_agent_id=uid(99), status='archived')],
                audit_events=events)


@pytest.mark.asyncio
async def test_valid_historical_execution_survives_replaced_current_run(history):
    counts = await execute(CHECK.query, history)
    assert counts['collaboration_used'] == 1
    assert CHECK.evaluate(counts)[0]


@pytest.mark.asyncio
@pytest.mark.parametrize('table,field,value', [
    ('remote_collaboration_commands', 'status', 'authorized'),
    ('remote_collaboration_commands', 'execution_id', None),
    ('remote_collaboration_commands', 'command_sha256', '0' * 64),
    ('remote_collaboration_commands', 'allow_elevation', True),
    ('remote_collaboration_commands', 'used_at', at('13:00:00')),
    ('remote_collaboration_commands', 'used_at', at('09:00:00')),
    ('remote_collaboration_sessions', 'expires_at', at('10:02:00')),
    ('remote_collaboration_sessions', 'ended_at', at('10:01:00')),
    ('remote_collaboration_sessions', 'agent_run_id', 'wrong-run'),
    ('host_executions', 'agent_id', uid(90)),
    ('host_executions', 'agent_demand_id', uid(90)),
    ('host_executions', 'shell', 'powershell'),
    ('host_executions', 'command', 'different command ********'),
    ('host_execution_results', 'server_id', uid(90)),
    ('host_execution_results', 'status', 'pending'),
    ('host_execution_results', 'finished_at', at('13:00:00')),
])
async def test_each_corrupt_binding_fails_actual_sql(history, table, field, value):
    history[table][0][field] = value
    assert not CHECK.evaluate(await execute(CHECK.query, history))[0]


@pytest.mark.asyncio
@pytest.mark.parametrize('missing', range(7))
async def test_every_required_session_server_and_execution_event_is_mandatory(history, missing):
    del history['audit_events'][missing]
    assert not CHECK.evaluate(await execute(CHECK.query, history))[0]


@pytest.mark.asyncio
async def test_wrong_starred_command_fails_even_with_matching_started_witness(history):
    history['host_executions'][0]['command'] = 'different command ********'
    history['audit_events'][-1]['payload']['command'] = 'different command ********'
    assert not CHECK.evaluate(await execute(CHECK.query, history))[0]


@pytest.mark.asyncio
@pytest.mark.parametrize('command', [
    "echo password='fictional password'", 'echo Bearer fictional_token_123456',
    "ConvertTo-SecureString -String 'fictional password'", 'net user example fictional',
    'echo tskey-fictional12345', 'echo -----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----',
    'echo password=fictional token=fictional',
    "echo password='fictional'bar",
    'echo -----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY----- trailing text',
    'echo -----BEGIN PRIVATE KEY-----\nfirst\n-----END PRIVATE KEY----- middle '
    '-----BEGIN PRIVATE KEY-----\nsecond\n-----END PRIVATE KEY----- trailing text',
])
async def test_trusted_masking_matches_real_execution(history, command):
    digest = hashlib.sha256(command.encode()).hexdigest()
    history['remote_collaboration_commands'][0].update(command=command, command_sha256=digest)
    history['host_executions'][0]['command'] = mask_secrets(command)
    history['audit_events'][-1]['payload']['command'] = mask_secrets(command)
    for event in history['audit_events']:
        if 'command_sha256' in event['payload']:
            event['payload']['command_sha256'] = digest
        if 'execution_command_sha256' in event['payload']:
            event['payload']['execution_command_sha256'] = hashlib.sha256(mask_secrets(command).encode()).hexdigest()
    assert CHECK.evaluate(await execute(CHECK.query, history))[0]


@pytest.mark.asyncio
async def test_elevation_must_match_the_authorization_witness(history):
    history['remote_collaboration_commands'][0]['allow_elevation'] = True
    history['remote_collaboration_sessions'][0]['allow_elevation'] = True
    assert not CHECK.evaluate(await execute(CHECK.query, history))[0]


@pytest.mark.asyncio
@pytest.mark.parametrize('index', [2, 5])
@pytest.mark.parametrize('digest', [None, '0' * 64])
async def test_missing_or_wrong_execution_digest_fails_on_either_audit_target(history, index, digest):
    payload = history['audit_events'][index]['payload']
    if digest is None:
        del payload['execution_command_sha256']
    else:
        payload['execution_command_sha256'] = digest
    assert not CHECK.evaluate(await execute(CHECK.query, history))[0]


@pytest.mark.asyncio
@pytest.mark.parametrize('command', ["echo password=********bar", 'echo ******** trailing text', 'echo ******** middle ******** trailing text'])
async def test_changed_stored_command_fails_with_unchanged_digest_even_when_started_matches(history, command):
    history['host_executions'][0]['command'] = command
    history['audit_events'][-1]['payload']['command'] = command
    assert not CHECK.evaluate(await execute(CHECK.query, history))[0]


@pytest.mark.asyncio
async def test_route_records_raw_and_trusted_masked_digests_on_actual_launch(ctx):
    command = 'echo password=$FICTIONAL'
    session = await remote_tests.open_session(ctx)
    entry = await remote_tests.authorize(ctx, session, command=command)
    response = await remote_tests.run(ctx, session, entry)
    assert response.status_code == 201, response.text
    execution_id = response.json()['id']
    await remote_tests.finished(execution_id)
    async with AsyncSessionLocal() as db:
        execution = await db.get(HostExecution, uuid.UUID(execution_id))
        events = (await db.scalars(select(AuditEvent).where(
            AuditEvent.event_type == 'remote_collaboration_command_run',
            AuditEvent.entity_id.in_([uuid.UUID(session['id']), ctx.lab.id])))).all()
    assert execution.command == mask_secrets(command) and execution.command != command
    assert {event.entity_type for event in events} == {'remote_collaboration_session', 'server'}
    raw_digest = hashlib.sha256(command.encode()).hexdigest()
    stored_digest = hashlib.sha256(execution.command.encode()).hexdigest()
    assert raw_digest != stored_digest
    for event in events:
        assert event.payload['command_sha256'] == raw_digest
        assert event.payload['execution_command_sha256'] == stored_digest
        assert event.payload['execution_id'] == execution_id
        assert 'command' not in event.payload


@pytest.fixture
def tiers():
    fixture = dict(agent_routines=[], agent_routine_runs=[], audit_checks=[], audit_check_runs=[])
    for index, (frequency, schedule) in enumerate(v.AUDIT_ROUTINE_SCHEDULES.items(), 10):
        fixture['agent_routines'].append(dict(id=uid(index), kind='audit', audit_frequency=frequency,
            schedule=schedule, timezone='America/Sao_Paulo', enabled=True, enabled_at='2025-01-01T00:00:00+00:00'))
        fixture['agent_routine_runs'].append(dict(routine_id=uid(index), status='completed', audit_batch_id=uid(index+10),
            created_at=at('10:00:00'), finished_at=at('10:01:00'), occurrence_at=at('10:00:00'), evidence_received=True, no_action=False))
        fixture['audit_checks'].append(dict(id=uid(index+20), enabled=True, frequency=frequency))
        fixture['audit_check_runs'].append(dict(check_id=uid(index+20), batch_id=uid(index+10),
            requested_by='routine', status='fail', created_at=at('10:00:30')))
    return fixture


@pytest.mark.asyncio
async def test_complete_audit_counts_failing_controls_as_evidence(tiers):
    rows = await execute(v.AUDIT_ROUTINE_INVENTORY_QUERY, tiers)
    assert not v.audit_routine_problems(rows, v._moment(NOW))


@pytest.mark.asyncio
@pytest.mark.parametrize('anomaly', ['no_evidence', 'missing_result', 'foreign_batch', 'future_finish', 'no_batch', 'new_check', 'empty_without_no_action'])
async def test_completed_run_without_full_or_proven_empty_evidence_fails(tiers, anomaly):
    if anomaly == 'no_evidence':
        tiers['agent_routine_runs'][0]['evidence_received'] = False
    elif anomaly == 'missing_result':
        del tiers['audit_check_runs'][0]
    elif anomaly == 'foreign_batch':
        tiers['audit_check_runs'][0]['batch_id'] = uid(99)
    elif anomaly == 'future_finish':
        tiers['agent_routine_runs'][0]['finished_at'] = at('13:00:00')
    elif anomaly == 'no_batch':
        tiers['agent_routine_runs'][0]['audit_batch_id'] = None
    elif anomaly == 'new_check':
        tiers['audit_checks'].append(dict(id=uid(99), enabled=True, frequency='daily'))
    else:
        tiers['audit_checks'][0]['enabled'] = False
        tiers['agent_routine_runs'][0]['evidence_received'] = False
        del tiers['audit_check_runs'][0]
    rows = await execute(v.AUDIT_ROUTINE_INVENTORY_QUERY, tiers)
    assert v.audit_routine_problems(rows, v._moment(NOW)) == ['daily: no completed run in 2 days']


@pytest.mark.asyncio
async def test_empty_quarterly_is_valid_only_with_no_action_and_no_results(tiers):
    tiers['audit_checks'][-1]['enabled'] = False
    tiers['agent_routine_runs'][-1].update(evidence_received=False, no_action=True)
    del tiers['audit_check_runs'][-1]
    assert not v.audit_routine_problems(await execute(v.AUDIT_ROUTINE_INVENTORY_QUERY, tiers), v._moment(NOW))
    tiers['audit_check_runs'].append(copy.deepcopy(tiers['audit_check_runs'][0]) | {'batch_id': uid(23)})
    assert v.audit_routine_problems(await execute(v.AUDIT_ROUTINE_INVENTORY_QUERY, tiers), v._moment(NOW))


@pytest.mark.asyncio
@pytest.mark.parametrize('query', [CHECK.query, m.COLLABORATION_SCHEMA_QUERY, v.AUDIT_ROUTINE_INVENTORY_QUERY])
async def test_queries_parse_against_migrated_schema_without_reading_domain_rows(query):
    async with AsyncSessionLocal() as db:
        await db.execute(text('SET TRANSACTION READ ONLY'))
        connection = await db.connection()
        # EXPLAIN without ANALYZE validates real column names as well as syntax.
        assert (await connection.exec_driver_sql('EXPLAIN ' + query)).all()
