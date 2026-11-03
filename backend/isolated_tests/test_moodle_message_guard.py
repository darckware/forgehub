from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.core.demand_workflow import decide_demand, ensure_workflow_allowed


@pytest.mark.asyncio
async def test_generic_decision_cannot_release_a_linked_moodle_message():
    db = SimpleNamespace(scalar=AsyncMock(return_value="linked"))
    message = SimpleNamespace(id="b7fa75cf-056e-46c0-8de4-954131b7d6ba", consolidated_into_id=None,
        dispatch_status=None, agent_run_id=None, updated_at=None, status="new", dispatch_error=None,
        target_agent_id=None, from_agent_id=None, working_path=None)
    decision = SimpleNamespace(action="approve", expected_updated_at=None)
    with pytest.raises(HTTPException) as exc:
        await decide_demand(db, message, decision, actor="admin")
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_unapproved_linked_message_cannot_reach_dispatch():
    db = SimpleNamespace(scalar=AsyncMock(return_value=SimpleNamespace(state="pending")))
    message = SimpleNamespace(id="b7fa75cf-056e-46c0-8de4-954131b7d6ba", status="new",
        consolidated_into_id=None, requires_approval=False)
    with pytest.raises(HTTPException) as exc:
        await ensure_workflow_allowed(db, message)
    assert exc.value.status_code == 409
