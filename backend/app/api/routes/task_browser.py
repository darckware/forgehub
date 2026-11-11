"""Narrow task-bound navigation in an isolated unauthenticated browser context."""
import hashlib
import uuid
from typing import Literal
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.task import _get_task_or_404, _resolve_task_project_id
from app.core.config import settings
from app.core.deps import ActorPrincipal, authorize_action, get_actor_principal
from app.core.remote_authority import require_agent_access_active, require_remote_task_credential
from app.core.task_completion_guard import resolve_executor_agent_id
from app.db.base import get_db
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.task import TaskAssignment, TaskExecution

router = APIRouter()


class TaskBrowserCommand(BaseModel):
    message_number: int = Field(gt=0)
    idempotency_key: str = Field(min_length=1, max_length=200)
    action: Literal['open', 'read', 'navigate', 'close', 'fill', 'click', 'submit']
    url: str | None = Field(default=None, max_length=2048)
    selector: str | None = Field(default=None, max_length=1000)
    text: str | None = Field(default=None, max_length=10000)

    @model_validator(mode='after')
    def valid_navigation(self):
        if self.action == 'navigate':
            url = urlsplit(self.url or '')
            if url.scheme not in {'https', 'http'} or not url.hostname or url.username or url.password:
                raise ValueError('Navigate requires an HTTP(S) URL without embedded credentials')
        elif self.url is not None:
            raise ValueError('Only navigation accepts a URL')
        if self.action in {'fill', 'click', 'submit'}:
            if not self.selector:
                raise ValueError('CSS selector required')
        elif self.selector is not None:
            raise ValueError('This operation does not accept a selector')
        if self.action == 'fill':
            if self.text is None:
                raise ValueError('Fill text required')
        elif self.text is not None:
            raise ValueError('Only fill accepts text')
        return self


async def browser_authority(db, principal, message_number, action='read'):
    if principal.principal_type != 'agent':
        raise HTTPException(403, 'Individual dispatched agent credential required')
    await require_agent_access_active(db, lock=True)
    demand = await db.scalar(select(AgentDemand).where(AgentDemand.number == message_number).with_for_update())
    if not demand or demand.target_agent_id != principal.principal_id:
        raise HTTPException(403, 'Task is not addressed to this agent')
    require_remote_task_credential(principal, demand)
    if demand.status == 'archived' or demand.origin_type != 'task' or not demand.task_execution_id:
        raise HTTPException(403, 'A current canonical task execution is required')
    execution = await db.get(TaskExecution, demand.task_execution_id, with_for_update=True)
    if (not execution or execution.task_id != demand.origin_id or execution.status != 'running'
            or await resolve_executor_agent_id(db, execution) != principal.principal_id):
        raise HTTPException(403, 'This agent is not the current running executor')
    if execution.assignment_id:
        assignment = await db.get(TaskAssignment, execution.assignment_id, with_for_update=True)
        if not assignment or assignment.status != 'active':
            raise HTTPException(403, 'Execution assignment is no longer active')
    task = await _get_task_or_404(db, execution.task_id)
    if task.status in {'done', 'deployed', 'cancelled', 'blocked'}:
        raise HTTPException(403, 'Task no longer permits browser execution')
    project_id = await _resolve_task_project_id(db, task)
    source, delegation = await authorize_action(db, principal, 'planning.execution.dispatch', project_id=project_id,
                                                action_risk='medium' if action in {'fill', 'click', 'submit'} else 'low')
    if delegation and delegation.revoked_at is not None:
        raise HTTPException(403, 'Browser execution delegation was revoked')
    return demand, execution, source, delegation


@router.post('/task-context')
async def task_browser_command(payload: TaskBrowserCommand,
                               principal: ActorPrincipal = Depends(get_actor_principal),
                               db: AsyncSession = Depends(get_db)):
    demand, execution, source, delegation = await browser_authority(db, principal, payload.message_number, payload.action)
    scope = f'{execution.id}:{demand.agent_run_id}:{principal.principal_id}'
    metadata = {'task_id': str(execution.task_id), 'execution_id': str(execution.id),
                'agent_run_id': demand.agent_run_id, 'principal_id': str(principal.principal_id),
                'authority_source': source, 'delegation_id': str(delegation.id) if delegation else None,
                'idempotency_key': payload.idempotency_key, 'operation': payload.action,
                'url_hash': hashlib.sha256((payload.url or '').encode()).hexdigest()}
    operation = uuid.uuid4()
    db.add(AuditEvent(entity_type='task_browser', entity_id=operation, event_type='pending',
                      actor=principal.display_name, payload=metadata))
    await db.commit()  # intent survives transport or process failure
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(f'{settings.CHAT_BRIDGE_URL}/v1/workspace-browser/task-context',
                                         headers={'X-Bridge-Token': settings.CHAT_BRIDGE_TOKEN},
                                         json={'scope': scope, 'idempotency_key': payload.idempotency_key,
                                               'action': payload.action, 'url': payload.url,
                                               'selector': payload.selector, 'text': payload.text})
        if response.status_code in {400, 401, 403, 409, 422}:
            result = {'status': 'refused', 'code': 'BROWSER_COMMAND_REFUSED'}
        else:
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict) or result.get('status') not in {'completed', 'uncertain'}:
                raise ValueError('Invalid browser acknowledgement')
    except (httpx.HTTPError, ValueError):
        result = {'status': 'uncertain', 'code': 'UPSTREAM_UNCERTAIN',
                  'message': 'Reconcile the original task/run and same idempotency key before repeating any operation.'}
    db.add(AuditEvent(entity_type='task_browser', entity_id=operation, event_type=result['status'],
                      actor=principal.display_name, payload=metadata))
    await db.commit()
    return {**result, 'task_id': str(execution.task_id), 'execution_id': str(execution.id),
            'agent_run_id': demand.agent_run_id, 'audit_id': str(operation)}


class TaskBrowserControl(BaseModel):
    audit_id: uuid.UUID
    action: Literal['take', 'read', 'confirm', 'release', 'close']
    operation_key: str | None = Field(default=None, max_length=200)
    observation_hash: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    reason: str = Field(min_length=1, max_length=1000)


@router.post('/task-context/control')
async def task_browser_control(payload: TaskBrowserControl,
                               principal: ActorPrincipal = Depends(get_actor_principal),
                               db: AsyncSession = Depends(get_db)):
    """An administrator observes/reconciles the exact isolated task context.

    Takeover never shares the operator's browser login or grants a new agent
    capability. Confirmation names the uncertain operation and a fresh human
    observation of this same context; site business acceptance stays human.
    """
    if principal.principal_type != 'user' or not principal.is_admin:
        raise HTTPException(403, 'Human administrator required for browser takeover or confirmation')
    event = await db.scalar(select(AuditEvent).where(
        AuditEvent.entity_type == 'task_browser', AuditEvent.entity_id == payload.audit_id,
        AuditEvent.event_type == 'pending'))
    if event is None:
        raise HTTPException(404, 'Recorded task browser operation not found')
    original = event.payload
    execution = await db.get(TaskExecution, uuid.UUID(original['execution_id']))
    if execution is None or str(execution.task_id) != original['task_id']:
        raise HTTPException(409, 'Recorded canonical task execution unavailable')
    scope = f"{original['execution_id']}:{original['agent_run_id']}:{original['principal_id']}"
    metadata = {**payload.model_dump(mode='json'), 'operator_id': str(principal.principal_id),
                'execution_id': original['execution_id'], 'agent_run_id': original['agent_run_id'],
                'task_id': original['task_id']}
    control_id = uuid.uuid4()
    db.add(AuditEvent(entity_type='task_browser_control', entity_id=control_id, event_type='pending',
                      actor=principal.display_name, payload=metadata))
    await db.commit()
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(f'{settings.CHAT_BRIDGE_URL}/v1/workspace-browser/task-context/control',
                                         headers={'X-Bridge-Token': settings.CHAT_BRIDGE_TOKEN},
                                         json={'scope': scope, 'operator': str(principal.principal_id),
                                               'action': payload.action, 'operation_key': payload.operation_key,
                                               'observation_hash': payload.observation_hash})
        if response.status_code in {400, 401, 403, 409, 422}:
            result = {'status': 'refused', 'code': 'BROWSER_CONTROL_REFUSED'}
        else:
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict) or result.get('status') != 'completed':
                raise ValueError('Invalid human control acknowledgement')
    except (httpx.HTTPError, ValueError):
        result = {'status': 'uncertain', 'code': 'UPSTREAM_UNCERTAIN',
                  'message': 'Human control acknowledgement was lost; observe the exact context before further action.'}
    db.add(AuditEvent(entity_type='task_browser_control', entity_id=control_id, event_type=result['status'],
                      actor=principal.display_name, payload=metadata))
    await db.commit()
    return {**result, 'control_audit_id': str(control_id)}
