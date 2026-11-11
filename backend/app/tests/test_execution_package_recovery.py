"""External acceptance is durable even when a Work Package loses its reply."""
import json
import asyncio
import uuid

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api.routes import execution as routes
from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.execution import ExecutionLease, ExecutionResult, ExecutionRunner
from app.db.models.project import ProjectForgeRouterConfig
from app.db.models.task import TaskExecution
from app.main import app
from app.tests.test_execution_runtime import runtime_context  # noqa: F401

HTTPX_CLIENT = httpx.AsyncClient

@pytest_asyncio.fixture
async def package(runtime_context,monkeypatch):  # noqa: F811
    ctx=runtime_context
    async with AsyncSessionLocal() as db:
        agent=await db.get(Agent,ctx['agent']); agent.runtime_type='codex'; agent.profile_slug='runner-test'
        config=ProjectForgeRouterConfig(project_id=ctx['project'],codex_enabled=True)
        runner=ExecutionRunner(runner_key=f"recovery-test-{uuid.uuid4()}",status='online',capabilities={'adapters':{'codex':{'available':True}}})
        db.add_all([config,runner]); await db.commit(); runner_id=runner.id
    async def get_runner(db):
        return await db.get(ExecutionRunner,runner_id)
    monkeypatch.setattr(routes,'_runner',get_runner)
    headers={'Authorization':f"Bearer {create_access_token(ctx['admin_username'])}"}
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test',headers=headers) as client:
        wave=(await client.post(f"/api/v1/projects/{ctx['project']}/execution-waves",json={'baseline_id':str(ctx['baseline']),'name':'Recovery wave','task_ids':[str(ctx['task'])],'idempotency_key':f'wave-{uuid.uuid4()}'})).json()
        for action in ('preflight','approve','activate'):
            response=await client.post(f"/api/v1/execution-waves/{wave['id']}:{action}",json={}); assert response.status_code==200,response.text
        response=await client.post(f"/api/v1/execution-waves/{wave['id']}/tasks/{ctx['task']}/work-packages",json={'assignment_id':str(ctx['assignment']),'runtime_profile_id':str(ctx['profile']),'allowed_paths':['backend/app'],'acceptance_criteria':['Verified'],'definition_of_done':['Checks pass'],'runtime_intent':{},'idempotency_key':f'package-{uuid.uuid4()}'})
        assert response.status_code==201,response.text
        item=response.json()
        response=await client.post(f"/api/v1/work-packages/{item['id']}:issue",json={}); assert response.status_code==200,response.text
        try:
            yield client,item
        finally:
            async with AsyncSessionLocal() as db:
                await db.execute(delete(ExecutionLease).where(ExecutionLease.runner_id==runner_id))
                await db.execute(delete(TaskExecution).where(TaskExecution.task_id==ctx['task']))
                await db.flush()
                await db.delete(await db.get(ExecutionRunner,runner_id)); await db.delete(await db.get(ProjectForgeRouterConfig,config.id)); await db.commit()


@pytest.mark.asyncio
async def test_lost_package_start_ack_retains_run_and_lease(package,monkeypatch):
    client,item=package
    calls=[]
    def bridge(req):
        calls.append(req)
        raise httpx.ReadTimeout('lost acknowledgement',request=req)
    original=httpx.AsyncClient
    monkeypatch.setattr(routes.httpx,'AsyncClient',lambda **kw:original(**kw,transport=httpx.MockTransport(bridge)))
    response=await client.post(f"/api/v1/work-packages/{item['id']}:dispatch",json={})
    assert response.status_code==502,response.text
    async with AsyncSessionLocal() as db:
        attempt=await db.scalar(select(TaskExecution).where(TaskExecution.work_package_id==uuid.UUID(item['id'])))
        lease=await db.scalar(select(ExecutionLease).where(ExecutionLease.task_execution_id==attempt.id))
        assert attempt.status=='reconciling'
        assert attempt.runtime_session_ref==str(attempt.id)
        assert attempt.finished_at is None and lease.released_at is None
    assert len(calls)==1


@pytest.mark.asyncio
async def test_cancel_ack_running_does_not_release_active_package(package,monkeypatch):
    client,item=package
    run_id=None
    def bridge(req):
        nonlocal run_id
        if req.url.path.endswith('/contextual'):
            run_id=json.loads(req.content)['run_id']
        return httpx.Response(202,json={'status':'running','run_id':run_id,'pid':123})
    original=httpx.AsyncClient
    monkeypatch.setattr(routes.httpx,'AsyncClient',lambda **kw:original(**kw,transport=httpx.MockTransport(bridge)))
    response=await client.post(f"/api/v1/work-packages/{item['id']}:dispatch",json={})
    assert response.status_code==202,response.text
    execution_id=response.json()['execution_id']
    response=await client.post(f'/api/v1/executions/{execution_id}:cancel-runtime',json={})
    assert response.status_code==200,response.text
    assert response.json()['status']=='running'
    async with AsyncSessionLocal() as db:
        attempt=await db.get(TaskExecution,uuid.UUID(execution_id))
        lease=await db.scalar(select(ExecutionLease).where(ExecutionLease.task_execution_id==attempt.id))
        assert attempt.finished_at is None and lease.released_at is None


def mock_runner(monkeypatch, handler):
    monkeypatch.setattr(routes.httpx,'AsyncClient',lambda **kw:HTTPX_CLIENT(**kw,transport=httpx.MockTransport(handler)))


async def start_package(package, monkeypatch):
    client,item=package
    def bridge(req):
        body=json.loads(req.content)
        return httpx.Response(202,json={'status':'running','run_id':body['run_id'],'pid':123})
    mock_runner(monkeypatch,bridge)
    response=await client.post(f"/api/v1/work-packages/{item['id']}:dispatch",json={})
    assert response.status_code==202,response.text
    return client,uuid.UUID(response.json()['execution_id'])


async def assert_active(execution_id, status):
    async with AsyncSessionLocal() as db:
        attempt=await db.get(TaskExecution,execution_id)
        lease=await db.scalar(select(ExecutionLease).where(ExecutionLease.task_execution_id==execution_id))
        assert attempt.status==status
        assert attempt.runtime_session_ref==str(execution_id)
        assert attempt.finished_at is None and lease.released_at is None
        assert await db.scalar(select(ExecutionResult.id).where(ExecutionResult.task_execution_id==execution_id)) is None


@pytest.mark.asyncio
async def test_wrong_start_identity_keeps_original_reservation_for_reconciliation(package,monkeypatch):
    client,item=package
    mock_runner(monkeypatch,lambda req:httpx.Response(202,json={'status':'running','run_id':str(uuid.uuid4())}))
    response=await client.post(f"/api/v1/work-packages/{item['id']}:dispatch",json={})
    assert response.status_code==502,response.text
    async with AsyncSessionLocal() as db:
        attempt=await db.scalar(select(TaskExecution).where(TaskExecution.work_package_id==uuid.UUID(item['id'])))
        attempt_id=attempt.id
    await assert_active(attempt_id,'reconciling')


@pytest.mark.asyncio
@pytest.mark.parametrize('status',[400,409,500])
async def test_only_definitive_start_refusal_releases_package_lease(package,monkeypatch,status):
    client,item=package
    mock_runner(monkeypatch,lambda req:httpx.Response(status,json={'detail':'runner declined'}))
    response=await client.post(f"/api/v1/work-packages/{item['id']}:dispatch",json={})
    assert response.status_code==502,response.text
    async with AsyncSessionLocal() as db:
        attempt=await db.scalar(select(TaskExecution).where(TaskExecution.work_package_id==uuid.UUID(item['id'])))
        lease=await db.scalar(select(ExecutionLease).where(ExecutionLease.task_execution_id==attempt.id))
        assert attempt.status==('failed' if status==400 else 'reconciling')
        assert (attempt.finished_at is not None)==(status==400)
        assert (lease.released_at is not None)==(status==400)


@pytest.mark.asyncio
@pytest.mark.parametrize('status,expected',[('starting','running'),('running','running'),('stale','reconciling'),('unknown','reconciling')])
async def test_nonterminal_runtime_observation_never_creates_terminal_result(package,monkeypatch,status,expected):
    client,execution_id=await start_package(package,monkeypatch)
    mock_runner(monkeypatch,lambda req:httpx.Response(200,json={'status':status,'run_id':str(execution_id)}))
    response=await client.post(f'/api/v1/executions/{execution_id}:refresh-runtime',json={})
    assert response.status_code==200,response.text
    assert response.json()['status']==expected
    await assert_active(execution_id,expected)


@pytest.mark.asyncio
async def test_refresh_wrong_identity_cannot_release_original_run(package,monkeypatch):
    client,execution_id=await start_package(package,monkeypatch)
    mock_runner(monkeypatch,lambda req:httpx.Response(200,json={'status':'completed','run_id':str(uuid.uuid4()),'exit_code':0}))
    response=await client.post(f'/api/v1/executions/{execution_id}:refresh-runtime',json={})
    assert response.status_code==502,response.text
    await assert_active(execution_id,'reconciling')


@pytest.mark.asyncio
async def test_lost_cancel_ack_keeps_lease_and_reconciliation_barrier(package,monkeypatch):
    client,execution_id=await start_package(package,monkeypatch)
    def bridge(req):
        raise httpx.ReadTimeout('cancel acknowledgement lost',request=req)
    mock_runner(monkeypatch,bridge)
    response=await client.post(f'/api/v1/executions/{execution_id}:cancel-runtime',json={})
    assert response.status_code==502,response.text
    await assert_active(execution_id,'reconciling')


def completed_run(execution_id, result_status='completed'):
    return {'run_id':str(execution_id),'status':'completed','exit_code':0,
            'output':json.dumps({'status':result_status,'summary':'Advisory CLI result','changed_files':[],
                'artifacts':[],'verification':[],'residual_risks':[],'follow_up_items':[]})}


@pytest.mark.asyncio
@pytest.mark.parametrize('result_status',['completed','failed'])
async def test_terminal_cli_contract_status_is_preserved_without_accepting_task(package,monkeypatch,result_status):
    from app.db.models.task import ProjectTask
    client,execution_id=await start_package(package,monkeypatch)
    mock_runner(monkeypatch,lambda req:httpx.Response(200,json=completed_run(execution_id,result_status)))
    response=await client.post(f'/api/v1/executions/{execution_id}:refresh-runtime',json={})
    assert response.status_code==200,response.text
    assert response.json()['status']==result_status
    async with AsyncSessionLocal() as db:
        attempt=await db.get(TaskExecution,execution_id)
        task=await db.get(ProjectTask,attempt.task_id)
        assert task.status=='in_progress'
        lease=await db.scalar(select(ExecutionLease).where(ExecutionLease.task_execution_id==execution_id))
        assert lease.released_at is not None


@pytest.mark.asyncio
async def test_cancel_cannot_overwrite_completed_result_and_refresh_cannot_reopen_it(package,monkeypatch):
    client,execution_id=await start_package(package,monkeypatch)
    mock_runner(monkeypatch,lambda req:httpx.Response(200,json=completed_run(execution_id)))
    response=await client.post(f'/api/v1/executions/{execution_id}:refresh-runtime',json={})
    assert response.status_code==200,response.text
    def unavailable(req):
        raise httpx.ConnectError('runner unavailable after completion',request=req)
    mock_runner(monkeypatch,unavailable)
    for action in ('cancel-runtime','refresh-runtime'):
        response=await client.post(f'/api/v1/executions/{execution_id}:{action}',json={})
        assert response.status_code==200,response.text
        assert response.json()['status']=='completed'
        assert response.json()['result']['summary']=='Advisory CLI result'


@pytest.mark.asyncio
async def test_slow_running_refresh_cannot_reopen_concurrently_completed_attempt(package,monkeypatch):
    client,execution_id=await start_package(package,monkeypatch)
    first_started=asyncio.Event()
    release_first=asyncio.Event()
    calls=0
    async def bridge(req):
        nonlocal calls
        calls+=1
        if calls==1:
            first_started.set()
            await release_first.wait()
            return httpx.Response(200,json={'run_id':str(execution_id),'status':'running','pid':123})
        return httpx.Response(200,json=completed_run(execution_id))
    mock_runner(monkeypatch,bridge)
    slow=asyncio.create_task(client.post(f'/api/v1/executions/{execution_id}:refresh-runtime',json={}))
    await asyncio.wait_for(first_started.wait(),timeout=5)
    fast=await client.post(f'/api/v1/executions/{execution_id}:refresh-runtime',json={})
    assert fast.status_code==200 and fast.json()['status']=='completed'
    release_first.set()
    delayed=await slow
    assert delayed.status_code==200 and delayed.json()['status']=='completed'
    async with AsyncSessionLocal() as db:
        attempt=await db.get(TaskExecution,execution_id)
        result=await db.scalar(select(ExecutionResult).where(ExecutionResult.task_execution_id==execution_id))
        lease=await db.scalar(select(ExecutionLease).where(ExecutionLease.task_execution_id==execution_id))
        assert attempt.status=='completed' and result is not None and lease.released_at is not None


@pytest.mark.asyncio
async def test_healthy_running_refresh_advances_the_execution_lease_heartbeat(package,monkeypatch):
    from datetime import datetime, timedelta, timezone
    client,execution_id=await start_package(package,monkeypatch)
    old=datetime.now(timezone.utc)-timedelta(minutes=10)
    async with AsyncSessionLocal() as db:
        lease=await db.scalar(select(ExecutionLease).where(ExecutionLease.task_execution_id==execution_id))
        lease.heartbeat_at=old
        await db.commit()
    mock_runner(monkeypatch,lambda req:httpx.Response(200,json={
        'run_id':str(execution_id),'status':'running','pid':123}))
    response=await client.post(f'/api/v1/executions/{execution_id}:refresh-runtime',json={})
    assert response.status_code==200 and response.json()['status']=='running'
    async with AsyncSessionLocal() as db:
        lease=await db.scalar(select(ExecutionLease).where(ExecutionLease.task_execution_id==execution_id))
        assert lease.heartbeat_at > old


@pytest.mark.asyncio
async def test_delayed_start_ack_cannot_reopen_attempt_finalized_by_refresh(package,monkeypatch):
    client,item=package
    started=asyncio.Event()
    release=asyncio.Event()
    run_id=None
    async def bridge(req):
        nonlocal run_id
        if req.url.path.endswith('/contextual'):
            run_id=json.loads(req.content)['run_id']
            started.set()
            await release.wait()
            return httpx.Response(202,json={'status':'running','run_id':run_id,'pid':123})
        return httpx.Response(200,json=completed_run(uuid.UUID(run_id)))
    mock_runner(monkeypatch,bridge)
    dispatch=asyncio.create_task(client.post(f"/api/v1/work-packages/{item['id']}:dispatch",json={}))
    await asyncio.wait_for(started.wait(),timeout=5)
    refreshed=await client.post(f'/api/v1/executions/{run_id}:refresh-runtime',json={})
    assert refreshed.status_code==200 and refreshed.json()['status']=='completed'
    release.set()
    acknowledgement=await dispatch
    assert acknowledgement.status_code==202,acknowledgement.text
    assert acknowledgement.json()['status']=='completed'
    async with AsyncSessionLocal() as db:
        attempt=await db.get(TaskExecution,uuid.UUID(run_id))
        result=await db.scalar(select(ExecutionResult).where(ExecutionResult.task_execution_id==attempt.id))
        lease=await db.scalar(select(ExecutionLease).where(ExecutionLease.task_execution_id==attempt.id))
        assert attempt.status=='completed' and result is not None and lease.released_at is not None
