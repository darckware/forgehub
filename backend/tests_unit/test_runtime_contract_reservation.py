"""reserve_dispatch's runtime-contract check: permanent refusals, never a silent queue."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core import demand_dispatch_guard as guard
from app.core import runtime_intent
from app.core.agent_runs import AgentRunDispatchError


def _db(*rows):
    return SimpleNamespace(get=AsyncMock(side_effect=list(rows)))


def test_missing_target_agent_is_a_dispatch_error_not_an_attribute_error():
    current = SimpleNamespace(task_execution_id=uuid4())
    db = _db(SimpleNamespace(task_id=uuid4()), None)
    with pytest.raises(AgentRunDispatchError, match='Target agent not found'):
        asyncio.run(guard._ensure_runtime_contract_satisfiable(db, current, uuid4()))


def test_unsatisfiable_contract_is_a_dispatch_error(monkeypatch):
    current = SimpleNamespace(task_execution_id=uuid4())
    db = _db(SimpleNamespace(task_id=uuid4()), SimpleNamespace(runtime_type='codex'))
    monkeypatch.setattr(runtime_intent, 'resolve_runtime_intent',
                        AsyncMock(side_effect=ValueError('Mandatory runtime skill x is not approved and granted')))
    with pytest.raises(AgentRunDispatchError, match='Runtime contract cannot be satisfied'):
        asyncio.run(guard._ensure_runtime_contract_satisfiable(db, current, uuid4()))


def test_hermes_executor_is_not_checked(monkeypatch):
    current = SimpleNamespace(task_execution_id=uuid4())
    db = _db(SimpleNamespace(task_id=uuid4()), SimpleNamespace(runtime_type='hermes'))
    resolve = AsyncMock()
    monkeypatch.setattr(runtime_intent, 'resolve_runtime_intent', resolve)
    asyncio.run(guard._ensure_runtime_contract_satisfiable(db, current, uuid4()))
    resolve.assert_not_awaited()
