import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core import task_recovery as mod


def test_recovery_only_current_task_dispatch_or_human_admin(monkeypatch):
    task_id, agent_id = uuid4(), uuid4()
    principal = SimpleNamespace(principal_type='agent', principal_id=agent_id, credential_label='dispatch:new')
    demand = SimpleNamespace(origin_type='task', origin_id=task_id, target_agent_id=agent_id,
                             task_execution_id=uuid4(), agent_run_id='new', dispatch_status='running', status='read')
    execution = SimpleNamespace(task_id=task_id, status='running')
    db = SimpleNamespace(scalar=AsyncMock(return_value=demand), get=AsyncMock(return_value=execution))
    monkeypatch.setattr(mod, 'resolve_executor_agent_id', AsyncMock(return_value=agent_id))
    assert asyncio.run(mod.require_recovery_reader(db, principal, task_id, 42)) == demand
    principal.credential_label = 'dispatch:old'
    with pytest.raises(HTTPException):
        asyncio.run(mod.require_recovery_reader(db, principal, task_id, 42))
    principal.principal_type, principal.is_admin = 'user', True
    assert asyncio.run(mod.require_recovery_reader(db, principal, task_id, None)) is None
