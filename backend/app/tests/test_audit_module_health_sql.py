"""Run actual read-only aggregate SQL on the isolated test PostgreSQL."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest
from sqlalchemy import text
from app.db.base import AsyncSessionLocal

SOURCE = Path(__file__).resolve().parents[3] / 'ops/athos/module_health.py'
SPEC = importlib.util.spec_from_file_location('module_health_sql_tests', SOURCE)
m = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = m
SPEC.loader.exec_module(m)


async def execute(name, ctes=None):
    query = m.CHECKS[name].query
    if ctes:
        query = query.replace('company.', 'fixture_')
        if query.lstrip().startswith('WITH '):
            query = 'WITH ' + ctes + ', ' + query.lstrip()[5:]
        else:
            query = 'WITH ' + ctes + ' ' + query
    async with AsyncSessionLocal() as db:
        result = (await db.execute(text(query))).scalar_one()
    return json.loads(result) if isinstance(result,str) else result


@pytest.mark.asyncio
@pytest.mark.parametrize('name',list(m.CHECKS))
async def test_module_sql_executes_against_current_schema(name):
    result = await execute(name)
    m.CHECKS[name].evaluate(result)


@pytest.mark.asyncio
@pytest.mark.parametrize('activity,healthy', [('now()',True), ("now()+interval '2 hours'",False)])
async def test_session_actual_sql_only_flags_activity_after_expiry(activity,healthy):
    counts = await execute('sessions',f'''fixture_user_sessions AS (SELECT
        '00000000-0000-0000-0000-000000000001'::uuid user_id,NULL::uuid agent_id,
        now()-interval '1 day' created_at,now()+interval '1 hour' expires_at,{activity} last_activity_at)''')
    assert m.CHECKS['sessions'].evaluate(counts)[0] is healthy


@pytest.mark.asyncio
async def test_expired_active_session_without_post_expiry_activity_is_valid():
    counts = await execute('sessions', '''fixture_user_sessions AS (SELECT true is_active,
        '00000000-0000-0000-0000-000000000001'::uuid user_id,NULL::uuid agent_id,
        now()-interval '2 days' created_at,now()-interval '1 day' expires_at,
        now()-interval '25 hours' last_activity_at)''')
    assert m.CHECKS['sessions'].evaluate(counts)[0]


@pytest.mark.asyncio
@pytest.mark.parametrize('status,success,enabled,healthy', [
    ('ok','now()',True,True),('running',"now()-interval '2 hours'",True,False),
    ('error','now()',True,False),('disabled','NULL::timestamptz',False,True),
    ('ok',"now()+interval '1 hour'",True,False),
])
async def test_workers_actual_sql_requires_recent_real_progress(status,success,enabled,healthy):
    counts = await execute('workers', f'''fixture_operational_worker_observations AS (
        SELECT name worker_name,seconds interval_seconds,{str(enabled).lower()} enabled,
        '{status}'::text last_status,{success} last_success_at,now() last_started_at
        FROM (VALUES ('scheduled-dispatch-poll',30),('feedback-poll',120),('routine-poll',60),
        ('mission-cycle-poll',60),('machine-status-poll',900)) e(name,seconds))''')
    assert m.CHECKS['workers'].evaluate(counts)[0] is healthy


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled,status,mission,evidence,no_action,healthy,kind',[
    (True,'scheduled',False,False,False,False,'report'),
    (True,'running',False,False,False,False,'report'),
    (False,'scheduled',False,False,False,True,'report'),
    (True,'completed',False,False,False,False,'report'),
    (True,'completed',False,True,False,True,'report'),
    (True,'completed',False,False,True,True,'report'),
    (True,'completed',True,False,False,True,'report'),
    # An audit routine's batch has no Messages task by design (2026-11-13);
    # only its deadline (an interrupted batch) still counts.
    (True,'running',False,False,False,False,'audit'),
])
async def test_routine_actual_sql_honors_disabled_and_coordination_exceptions(enabled,status,mission,evidence,no_action,healthy,kind):
    counts=await execute('routines',f'''fixture_agent_routines AS (SELECT 1 id,
    {str(enabled).lower()} enabled,60 deadline_minutes,'report'::text expected_evidence,'{kind}'::text kind,
    {'1' if mission else 'NULL::int'} mission_project_id),
    fixture_agent_routine_runs AS (SELECT 1 id,NULL::int retry_of_run_id,1 routine_id,'{status}'::text status,
    now()-interval '2 hours' occurrence_at,NULL::uuid demand_id,
    {str(evidence).lower()} evidence_received,{str(no_action).lower()} no_action)''')
    assert m.CHECKS['routines'].evaluate(counts)[0] is healthy


@pytest.mark.asyncio
async def test_running_audit_batch_within_its_deadline_is_not_missing_a_demand():
    counts=await execute('routines','''fixture_agent_routines AS (SELECT 1 id,true enabled,
    180 deadline_minutes,'lote'::text expected_evidence,'audit'::text kind,NULL::int mission_project_id),
    fixture_agent_routine_runs AS (SELECT 1 id,NULL::int retry_of_run_id,1 routine_id,'running'::text status,now() occurrence_at,
    NULL::uuid demand_id,NULL::boolean evidence_received,NULL::boolean no_action)''')
    assert counts['missing_demand'] == 0 and m.CHECKS['routines'].evaluate(counts)[0] is True


@pytest.mark.asyncio
@pytest.mark.parametrize('origin,status,healthy', [
    ('planning','in_progress',True),('change','in_progress',True),
    ('neither','in_progress',False),('neither','done',True),('mismatch','in_progress',False),
])
async def test_factory_actual_sql_accepts_change_requests_and_history(origin,status,healthy):
    counts=await execute('factory',f'''fixture_project_tasks AS (SELECT 1 id,
    {'1' if origin in ('planning','mismatch') else 'NULL::int'} planning_item_id,
    {'1' if origin in ('change','mismatch') else 'NULL::int'} change_request_id,
    NULL::int parent_task_id,'{status}'::text status),
    fixture_planning_items AS (SELECT 1 id,1 project_id),
    fixture_change_requests AS (SELECT 1 id,{'2' if origin=='mismatch' else '1'} project_id)''')
    assert m.CHECKS['factory'].evaluate(counts)[0] is healthy


@pytest.mark.asyncio
@pytest.mark.parametrize('baseline,member,projection,cycles,routine,healthy', [
    (True,True,'active',True,True,True), (False,True,'active',True,True,False),
    (True,False,'active',True,True,False), (True,True,'planned',True,True,False),
    (True,True,'active',True,False,False), (True,True,'active',False,False,True),
])
async def test_mission_actual_sql_baseline_membership_projection_and_feature_policy(baseline,member,projection,cycles,routine,healthy):
    counts=await execute('mission',f'''fixture_project_missions AS (SELECT 1 project_id,'active'::text state,
        1 current_baseline_id,1 orchestrator_agent_id),
    fixture_projects AS (SELECT 1 id,'{projection}'::text status,'mission'::text project_type),
    fixture_plan_baselines AS (SELECT {'1' if baseline else '2'} id,1 project_plan_id,NULL::timestamptz superseded_at),
    fixture_project_plans AS (SELECT 1 id,1 project_id),
    fixture_project_agent_memberships AS (SELECT 1 project_id,1 agent_id,'coordinator'::text role,
        '{'active' if member else 'released'}'::text status,NULL::date valid_from,NULL::date valid_to),
    fixture_agents AS (SELECT 1 id,true is_active),
    fixture_operational_worker_observations AS (SELECT 'mission-cycle-poll'::text worker_name,{str(cycles).lower()} enabled),
    fixture_agent_routines AS (SELECT 1 mission_project_id,{str(routine).lower()} enabled,
        'coordination'::text kind,1 agent_id)''')
    assert m.CHECKS['mission'].evaluate(counts)[0] is healthy


@pytest.mark.asyncio
@pytest.mark.parametrize('observed,client,stale,linked,healthy',[
    (True,False,False,True,True),(False,False,False,True,False),
    (False,True,False,True,False),(True,False,True,True,False),
    (True,False,False,False,False),
])
async def test_remote_actual_sql_observation_heartbeat_and_task_link(observed,client,stale,linked,healthy):
    counts=await execute('remote',f'''fixture_servers AS (SELECT 1 id,true access_enabled,
        {'1' if client else 'NULL::int'} darckware_client_id),
    fixture_machine_status_observations AS (SELECT 1 server_id,
        {'now()' if observed else "now()-interval '1 hour'"} last_checked_at),
    fixture_operational_worker_observations AS (SELECT 'machine-status-poll'::text worker_name,
        true enabled,'ok'::text last_status),
    fixture_host_executions AS (SELECT 1 id,'running'::text status,now() started_at,
        {'now()' if not stale else "now()-interval '10 minutes'"} heartbeat_at,60 timeout_seconds,
        NULL::timestamptz retry_until,'agent'::text trigger,1 agent_id,
        {'1' if linked else 'NULL::int'} agent_demand_id),
    fixture_host_execution_results AS (SELECT 1 execution_id,'pending'::text status, NULL::timestamptz started_at),
    fixture_agent_demands AS (SELECT 1 id,'task'::text origin_type)''')
    assert m.CHECKS['remote'].evaluate(counts)[0] is healthy
