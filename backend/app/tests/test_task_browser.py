"""Task-bound browser API against isolated Postgres; bridge effects are simulated."""
import uuid

import httpx
import pytest
from sqlalchemy import delete, select

from app.api.routes import task_browser as browser
from app.db.base import AsyncSessionLocal
from app.db.models.agent import AgentServiceCredential
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent, AuthorityDelegation
from app.db.models.task import TaskExecution
from app.tests.test_mission_base import World, _task


@pytest.mark.asyncio
async def test_browser_uses_canonical_run_and_revalidates_authority(admin_headers, monkeypatch):
    world = World(admin_headers)
    await world.setup()
    demand_id = None
    execution_id = None
    try:
        project = await world.common_project()
        agent = await world.agent('browser')
        headers = await world.agent_token(agent, ['planning.execution.dispatch'], project_id=uuid.UUID(project['id']))
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
