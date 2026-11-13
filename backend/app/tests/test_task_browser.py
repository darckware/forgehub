"""Task-bound browser API against isolated Postgres; bridge effects are simulated."""
import uuid

import httpx
import pytest
from sqlalchemy import delete, select

from app.api.routes import task_browser as browser
from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.models.agent import AgentServiceCredential
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent, AuthorityDelegation
from app.db.models.task import TaskExecution
from app.tests.test_mission_base import World, _task


@pytest.mark.asyncio
async def test_browser_uses_canonical_run_and_revalidates_authority(admin_headers, monkeypatch):
    monkeypatch.setattr(settings, 'TASK_BROWSER_ENABLED', True)
    world = World(admin_headers)
    await world.setup()
    demand_id = None
    execution_id = None
    try:
        project = await world.common_project()
        agent = await world.agent('browser')
        headers = await world.agent_token(agent, ['task.browser.execute'], project_id=uuid.UUID(project['id']))
        task = await _task(uuid.UUID(project['id']), 'Isolated browser contract', status='in_progress')
        run_id = str(uuid.uuid4())
        async with AsyncSessionLocal() as db:
            execution = TaskExecution(task_id=task.id, status='running', executor_type='agent')
            db.add(execution)
            await db.flush()
            execution_id = execution.id
            demand = AgentDemand(from_agent='test-suite', subject='Browser contract', body='Synthetic only',
                                 target_agent_id=agent, status='read', origin_type='task', origin_id=task.id,
                                 task_execution_id=execution.id, agent_run_id=run_id, dispatch_status='running')
            db.add(demand)
            credential = await db.scalar(select(AgentServiceCredential).where(AgentServiceCredential.agent_id == agent))
            credential.label = f'dispatch:{run_id}'
            await db.commit()
            demand_id, number = demand.id, demand.number
        calls = []
        def bridge(request):
            calls.append(request)
            return httpx.Response(200, json={'status': 'completed', 'isolated': True})
        original = httpx.AsyncClient
        monkeypatch.setattr(browser.httpx, 'AsyncClient', lambda **kw: original(**kw, transport=httpx.MockTransport(bridge)))
        body = {'message_number': number, 'idempotency_key': 'open', 'action': 'open'}
        async with world.client(headers) as client:
            result = await client.post('/api/v1/workspace-browser/task-context', json=body)
            assert result.status_code == 200, result.text
            assert result.json()['execution_id'] == str(execution_id)
            assert len(calls) == 1
            # The agent cannot use operator cookies or login even with valid agt_.
            shared = await client.get('/api/v1/workspace-browser/state')
            assert shared.status_code == 403, shared.text
            # Site mutations require the existing delegation's medium risk ceiling.
            mutation = await client.post('/api/v1/workspace-browser/task-context', json={
                **body, 'action': 'fill', 'idempotency_key': 'fill', 'selector': '#synthetic', 'text': 'value'})
            assert mutation.status_code == 403, mutation.text
            assert len(calls) == 1
            async with AsyncSessionLocal() as db:
                grant = await db.scalar(select(AuthorityDelegation).where(AuthorityDelegation.grantee_id == agent))
                grant.status = 'revoked'
                await db.commit()
            denied = await client.post('/api/v1/workspace-browser/task-context', json={**body, 'action': 'read', 'idempotency_key': 'read'})
            assert denied.status_code == 403, denied.text
            assert len(calls) == 1
        async with AsyncSessionLocal() as db:
            audits = list((await db.scalars(select(AuditEvent).where(AuditEvent.entity_type == 'task_browser'))).all())
            ours = [e for e in audits if e.payload.get('execution_id') == str(execution_id)]
            assert {e.event_type for e in ours} == {'pending', 'completed'}
    finally:
        async with AsyncSessionLocal() as db:
            if demand_id:
                await db.execute(delete(AgentDemand).where(AgentDemand.id == demand_id))
            if execution_id:
                for event in list((await db.scalars(select(AuditEvent).where(AuditEvent.entity_type == 'task_browser'))).all()):
                    if event.payload.get('execution_id') == str(execution_id):
                        await db.delete(event)
            await db.commit()
        await world.cleanup()


LEGACY_ROUTES = [
    ('POST', '/start'), ('GET', '/state'), ('POST', '/navigate'), ('POST', '/reload'), ('POST', '/back'),
    ('POST', '/resize'), ('POST', '/pointer'), ('POST', '/text'), ('POST', '/scroll'), ('POST', '/login-forgehub'),
    ('GET', '/standalone-apps'), ('POST', '/standalone-apps'), ('PUT', '/standalone-apps/{id}'),
    ('DELETE', '/standalone-apps/{id}'), ('GET', '/routines'), ('POST', '/routines'), ('PUT', '/routines/{id}'),
    ('DELETE', '/routines/{id}'), ('POST', '/routines/{id}:run'), ('PUT', '/routines/{id}/background-test'),
    ('POST', '/routines/{id}:run-background'), ('POST', '/background-test'), ('GET', '/test-runs'),
    ('GET', '/test-runs/{id}'), ('GET', '/macros'), ('POST', '/macros'), ('PUT', '/macros/{id}'),
    ('DELETE', '/macros/{id}'),
]


@pytest.mark.asyncio
async def test_legacy_shared_browser_routes_refuse_agent_credentials(admin_headers):
    """The shared (operator-authenticated) browser is never reachable with agt_."""
    world = World(admin_headers)
    await world.setup()
    try:
        agent = await world.agent('legacy-browser')
        headers = await world.agent_token(agent, None)
        async with world.client(headers) as client:
            for method, path in LEGACY_ROUTES:
                url = '/api/v1/workspace-browser' + path.replace('{id}', str(uuid.uuid4()))
                response = await client.request(method, url, json={} if method in ('POST', 'PUT') else None)
                assert response.status_code == 403, (method, path, response.text)
    finally:
        await world.cleanup()


@pytest.mark.asyncio
async def test_task_browser_is_503_when_switched_off(admin_headers, monkeypatch):
    monkeypatch.setattr(settings, 'TASK_BROWSER_ENABLED', False)
    calls = []
    original = httpx.AsyncClient
    monkeypatch.setattr(browser.httpx, 'AsyncClient', lambda **kw: original(
        **kw, transport=httpx.MockTransport(lambda request: calls.append(request) or httpx.Response(200, json={}))))
    world = World(admin_headers)
    await world.setup()
    try:
        agent = await world.agent('browser-off')
        agent_headers = await world.agent_token(agent, ['task.browser.execute'])
        async with world.client(agent_headers) as client:
            off = await client.post('/api/v1/workspace-browser/task-context', json={
                'message_number': 1, 'idempotency_key': 'open', 'action': 'open'})
            assert off.status_code == 503, off.text
            assert off.json()['detail']['code'] == 'TASK_BROWSER_DISABLED'
        async with world.client(admin_headers) as client:
            control = await client.post('/api/v1/workspace-browser/task-context/control', json={
                'audit_id': str(uuid.uuid4()), 'action': 'read', 'reason': 'off'})
            assert control.status_code == 503, control.text
        assert calls == []
    finally:
        await world.cleanup()


@pytest.mark.asyncio
async def test_dispatch_delegation_alone_does_not_open_the_browser(admin_headers, monkeypatch):
    monkeypatch.setattr(settings, 'TASK_BROWSER_ENABLED', True)
    world = World(admin_headers)
    await world.setup()
    demand_id = None
    try:
        project = await world.common_project()
        agent = await world.agent('browser-dispatch-only')
        headers = await world.agent_token(agent, ['planning.execution.dispatch'], project_id=uuid.UUID(project['id']))
        task = await _task(uuid.UUID(project['id']), 'Dispatch-only browser', status='in_progress')
        run_id = str(uuid.uuid4())
        async with AsyncSessionLocal() as db:
            execution = TaskExecution(task_id=task.id, status='running', executor_type='agent')
            db.add(execution)
            await db.flush()
            demand = AgentDemand(from_agent='test-suite', subject='Browser contract', body='Synthetic only',
                                 target_agent_id=agent, status='read', origin_type='task', origin_id=task.id,
                                 task_execution_id=execution.id, agent_run_id=run_id, dispatch_status='running')
            db.add(demand)
            credential = await db.scalar(select(AgentServiceCredential).where(AgentServiceCredential.agent_id == agent))
            credential.label = f'dispatch:{run_id}'
            await db.commit()
            demand_id, number = demand.id, demand.number
        async with world.client(headers) as client:
            refused = await client.post('/api/v1/workspace-browser/task-context', json={
                'message_number': number, 'idempotency_key': 'open', 'action': 'open'})
            assert refused.status_code == 403, refused.text
            assert 'task.browser.execute' in refused.text
    finally:
        async with AsyncSessionLocal() as db:
            if demand_id:
                await db.execute(delete(AgentDemand).where(AgentDemand.id == demand_id))
                await db.commit()
        await world.cleanup()
