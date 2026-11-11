"""No database or browser effects: task/run boundary checks."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routes import task_browser as mod


def test_browser_revalidates_task_run_executor_and_current_grant(monkeypatch):
    aid, eid, tid = uuid4(), uuid4(), uuid4()
    demand = SimpleNamespace(task_execution_id=eid, origin_type='task', origin_id=tid,
                             target_agent_id=aid, agent_run_id='run', dispatch_status='running', status='read')
    execution = SimpleNamespace(id=eid, task_id=tid, status='running', assignment_id=None)
    db = SimpleNamespace(scalar=AsyncMock(return_value=demand), get=AsyncMock(return_value=execution))
    principal = SimpleNamespace(principal_type='agent', principal_id=aid, credential_label='dispatch:run')
    monkeypatch.setattr(mod, 'require_agent_access_active', AsyncMock())
    monkeypatch.setattr(mod, 'resolve_executor_agent_id', AsyncMock(return_value=aid))
    monkeypatch.setattr(mod, '_get_task_or_404', AsyncMock(return_value=SimpleNamespace(status="in_progress")))
    monkeypatch.setattr(mod, '_resolve_task_project_id', AsyncMock(return_value=uuid4()))
    authority = AsyncMock(return_value=('delegation', None))
    monkeypatch.setattr(mod, 'authorize_action', authority)
    got = asyncio.run(mod.browser_authority(db, principal, 42))
    assert got[0] == demand
    assert authority.await_args.args[2] == 'planning.execution.dispatch'
    principal.credential_label = 'dispatch:previous-run'
    with pytest.raises(HTTPException):
        asyncio.run(mod.browser_authority(db, principal, 42))
    principal.credential_label = 'dispatch:run'
    execution.status = 'completed'
    with pytest.raises(HTTPException):
        asyncio.run(mod.browser_authority(db, principal, 42))


@pytest.mark.parametrize('reason', ['paused', 'expired_grant', 'reassigned'])
def test_revoked_authority_never_reaches_browser(monkeypatch, reason):
    aid, eid, tid = uuid4(), uuid4(), uuid4()
    demand = SimpleNamespace(task_execution_id=eid, origin_type='task', origin_id=tid,
                             target_agent_id=aid, agent_run_id='run', dispatch_status='running', status='read')
    execution = SimpleNamespace(id=eid, task_id=tid, status='running', assignment_id=None)
    db = SimpleNamespace(scalar=AsyncMock(return_value=demand), get=AsyncMock(return_value=execution))
    principal = SimpleNamespace(principal_type='agent', principal_id=aid, credential_label='dispatch:run')
    monkeypatch.setattr(mod, 'require_agent_access_active', AsyncMock(side_effect=HTTPException(403) if reason == 'paused' else None))
    monkeypatch.setattr(mod, 'resolve_executor_agent_id', AsyncMock(return_value=uuid4() if reason == 'reassigned' else aid))
    monkeypatch.setattr(mod, '_get_task_or_404', AsyncMock(return_value=SimpleNamespace(status="in_progress")))
    monkeypatch.setattr(mod, '_resolve_task_project_id', AsyncMock(return_value=uuid4()))
    monkeypatch.setattr(mod, 'authorize_action', AsyncMock(side_effect=HTTPException(403) if reason == 'expired_grant' else None))
    with pytest.raises(HTTPException):
        asyncio.run(mod.browser_authority(db, principal, 42))


def test_pending_audit_is_durable_before_browser_effect(monkeypatch):
    import httpx
    aid, eid, tid = uuid4(), uuid4(), uuid4()
    execution = SimpleNamespace(id=eid, task_id=tid)
    demand = SimpleNamespace(agent_run_id='run')
    principal = SimpleNamespace(principal_id=aid, display_name='Synthetic')
    monkeypatch.setattr(mod, 'browser_authority', AsyncMock(return_value=(demand, execution, 'delegation', None)))
    events = []
    db = SimpleNamespace(add=events.append, commit=AsyncMock())
    calls = []
    def effect(request):
        assert db.commit.await_count == 1
        assert events[0].event_type == 'pending'
        calls.append(request)
        raise httpx.ReadTimeout('secret must not surface', request=request)
    original = httpx.AsyncClient
    monkeypatch.setattr(mod.httpx, 'AsyncClient', lambda **kw: original(**kw, transport=httpx.MockTransport(effect)))
    result = asyncio.run(mod.task_browser_command(mod.TaskBrowserCommand(
        message_number=42, idempotency_key='same', action='navigate', url='https://test.invalid/'), principal, db))
    assert result['status'] == 'uncertain'
    assert 'secret' not in str(result)
    assert result['execution_id'] == str(eid)
    assert events[-1].event_type == 'uncertain'
    assert len(calls) == 1
    assert 'url' not in events[0].payload


def test_shared_authenticated_context_denies_agent():
    from app.api.routes.workspace_browser import _shared_context_boundary
    principal = SimpleNamespace(principal_type='agent')
    request = SimpleNamespace(url=SimpleNamespace(path='/api/v1/workspace-browser/login-forgehub'))
    with pytest.raises(HTTPException):
        asyncio.run(_shared_context_boundary(request, principal))
    request.url.path = '/api/v1/workspace-browser/task-context'
    asyncio.run(_shared_context_boundary(request, principal))


def test_operator_control_requires_human_admin():
    principal = SimpleNamespace(principal_type='agent', is_admin=True)
    payload = mod.TaskBrowserControl(audit_id=uuid4(), action='take', reason='Inspect uncertainty')
    with pytest.raises(HTTPException) as error:
        asyncio.run(mod.task_browser_control(payload, principal, None))
    assert error.value.status_code == 403
