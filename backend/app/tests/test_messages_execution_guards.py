from unittest.mock import AsyncMock
import uuid

import pytest
import httpx
from fastapi import HTTPException

from app.api.routes import demand as routes
from app.core.agent_runs import AgentRunDispatchError
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand


@pytest.mark.parametrize("runtime", ["claude", "codex", "agy", "hermes"])
@pytest.mark.parametrize("path", [None, "", "   ", "relative/project"])
async def test_dispatch_requires_explicit_absolute_directory(runtime, path, monkeypatch):
    agent = Agent(
        id=uuid.uuid4(),
        name="Guard test",
        runtime_type=runtime,
        profile_slug="guard-test" if runtime == "hermes" else None,
    )
    monkeypatch.setattr(routes, "_get_agent_or_404", AsyncMock(return_value=agent))
    dispatch = AsyncMock(return_value={"run_id": "must-not-start"})
    monkeypatch.setattr(routes, "dispatch_agent_run", dispatch)
    monkeypatch.setattr(routes, "_send_notice", AsyncMock())
    item = AgentDemand(origin_type="task", body="test", subject="test", working_path=path)
    with pytest.raises(AgentRunDispatchError, match="directory"):
        await routes._execute_dispatch(AsyncMock(), item, agent.id, None)
    dispatch.assert_not_awaited()


def test_incubation_with_sender_cannot_execute_before_promotion():
    item = AgentDemand(origin_type="incubation", from_agent_id=uuid.uuid4())
    with pytest.raises(HTTPException):
        routes._assert_dispatchable(item)


@pytest.mark.parametrize("runtime", ["claude", "codex", "agy", "hermes"])
async def test_dispatch_preserves_requested_directory(runtime, monkeypatch):
    agent = Agent(
        id=uuid.uuid4(),
        name="Guard test",
        runtime_type=runtime,
        profile_slug="guard-test" if runtime == "hermes" else None,
    )
    monkeypatch.setattr(routes, "_get_agent_or_404", AsyncMock(return_value=agent))
    dispatch = AsyncMock(return_value={"run_id": "isolated-run"})
    monkeypatch.setattr(routes, "dispatch_agent_run", dispatch)
    monkeypatch.setattr(routes, "_send_notice", AsyncMock())
    item = AgentDemand(origin_type="task", body="test", subject="test",
                       working_path="/root/project/duplica")
    await routes._execute_dispatch(AsyncMock(), item, agent.id, None)
    assert dispatch.await_args.args[3] == "/root/project/duplica"
    assert item.dispatch_status == "dispatched"


async def test_bridge_directory_rejection_is_permanent_and_sanitized(monkeypatch):
    from app.core import agent_runs
    agent = Agent(name="Guard", runtime_type="codex")
    response = httpx.Response(400, json={"detail": "sensitive upstream detail"},
                              request=httpx.Request("POST", "http://bridge/v1/agent-runs"))
    client = AsyncMock()
    client.post.return_value = response
    client.__aenter__.return_value = client
    monkeypatch.setattr(agent_runs.httpx, "AsyncClient", lambda **_: client)
    with pytest.raises(AgentRunDispatchError) as error:
        await agent_runs.dispatch_agent_run("test", agent, "test", "/missing")
    assert "sensitive" not in str(error.value)
