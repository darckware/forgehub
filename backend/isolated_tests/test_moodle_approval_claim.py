import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.routes import moodle_approval
from app.api.schemas.moodle_approval import ClaimIn, StatusIn
from app.core.demand_workflow import approval_fingerprint
from app.core.deps import ActorPrincipal


@pytest.mark.asyncio
async def test_claim_is_single_use_and_bound_to_authenticated_executor(monkeypatch):
    executor, source, request, message = (uuid.uuid4() for _ in range(4))
    demand = SimpleNamespace(id=message, status="new", consolidated_into_id=None, requires_approval=True,
        approval_status="approved", subject="Moodle", body="message", origin_type="task", origin_id=None,
        target_agent_id=executor, from_agent_id=source, working_path="/tmp", project_id=None,
        command_text=None, requires_response=False, channel=None, channel_ref=None,
        agent_run_id="run", dispatch_status=None, dispatch_error=None, dispatch_attempts=0, retry_limit=3)
    digest = approval_fingerprint(demand)
    demand.approved_content_hash = digest
    link = SimpleNamespace(executor_id=executor, source_agent_id=source, request_id=request, state="approved",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=1), params_hash="a" * 64, message_hash=digest)
    result = SimpleNamespace(one_or_none=lambda: (link, demand))
    db = SimpleNamespace(execute=AsyncMock(return_value=result), commit=AsyncMock(), add=MagicMock())
    proposal = {"wsfunction": "core_user_delete_users", "params": {"userids": [1]},
        "environment": "staging", "host": "https://example.test", "params_hash": "a" * 64}
    monkeypatch.setattr(moodle_approval, "_config", lambda: None)
    monkeypatch.setattr(moodle_approval, "_source", lambda agent_id, request_id: proposal if agent_id == source else None)
    payload = ClaimIn(request_id=request, message_id=message, params_hash="a" * 64)
    outsider = ActorPrincipal("agent", uuid.uuid4(), "outsider")
    with pytest.raises(HTTPException) as exc:
        await moodle_approval.claim(payload, outsider, db)
    assert exc.value.status_code == 403
    assert link.state == "approved"
    principal = ActorPrincipal("agent", executor, "executor")
    assert await moodle_approval.claim(payload, principal, db) == {k: proposal[k] for k in ("wsfunction", "params", "environment", "host")}
    assert link.state == "claimed"
    with pytest.raises(HTTPException) as exc:
        await moodle_approval.claim(payload, principal, db)
    assert exc.value.status_code == 409


def _status_db(link):
    return SimpleNamespace(scalar=AsyncMock(return_value=link))


@pytest.mark.asyncio
async def test_status_reports_without_changing_anything(monkeypatch):
    executor, source, request, message = (uuid.uuid4() for _ in range(4))
    link = SimpleNamespace(executor_id=executor, source_agent_id=source, request_id=request, state="approved", outcome=None, params_hash="a" * 64,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=1))
    monkeypatch.setattr(moodle_approval, "_config", lambda: None)
    payload = StatusIn(request_id=request, message_id=message)
    principal = ActorPrincipal("agent", executor, "executor")
    assert await moodle_approval.claim_status(payload, principal, _status_db(link)) == {
        "state": "approved", "outcome": None, "params_hash": "a" * 64, "expired": False}
    assert link.state == "approved"
    link.state, link.outcome = "finished", "completed"
    assert (await moodle_approval.claim_status(payload, principal, _status_db(link)))["outcome"] == "completed"


@pytest.mark.asyncio
async def test_status_of_a_pending_proposal_answers_its_creator_and_nobody_else(monkeypatch):
    source, request, message = (uuid.uuid4() for _ in range(3))
    link = SimpleNamespace(executor_id=None, source_agent_id=source, request_id=request, state="pending", outcome=None, params_hash="a" * 64,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    monkeypatch.setattr(moodle_approval, "_config", lambda: None)
    payload = StatusIn(request_id=request, message_id=message)
    answer = await moodle_approval.claim_status(payload, ActorPrincipal("agent", source, "creator"), _status_db(link))
    assert answer["state"] == "pending" and answer["expired"] is True
    with pytest.raises(HTTPException) as exc:
        await moodle_approval.claim_status(payload, ActorPrincipal("agent", uuid.uuid4(), "outsider"), _status_db(link))
    assert exc.value.status_code == 403
