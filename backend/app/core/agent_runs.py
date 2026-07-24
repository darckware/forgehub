"""Shared client for the host-bridge's governed CLI runner (`/v1/agent-runs`).

Two call sites already talk to this endpoint by hand-rolling the same httpx
POST/GET (`api/routes/execution.py`'s `dispatch_package`/`refresh_runtime`/
`cancel_runtime`, `api/routes/orchestration.py`'s
`dispatch_execution_review`) -- this module factors that out so a third
caller (`api/routes/demand.py`'s Inbox dispatch) doesn't duplicate it again.
Payload shape matches those existing callers exactly; migrating them to use
this module instead is a separate, optional follow-up.
"""
import httpx

from app.core.config import settings
from app.core.secrets import decrypt_secret
from app.db.models.agent import Agent


class AgentRunDispatchError(Exception):
    """Raised for conditions the route layer should turn into an HTTP error
    (missing credential/runtime_type) -- never for transport failures, which
    propagate as httpx.HTTPError so callers can distinguish "can't even try"
    from "tried and the bridge/runner failed"."""


async def dispatch_agent_run(
    run_id: str,
    agent: Agent,
    prompt: str,
    project_path: str,
    *,
    mode: str = "execute",
    model_ref: str = "forgerouter/auto",
    routing_group: str = "auto",
    max_seconds: int = 1800,
    max_budget_usd: float | None = None,
) -> dict:
    """POST /v1/agent-runs for `agent`. Raises AgentRunDispatchError if the
    agent can't be dispatched at all (no credential/runtime_type); raises
    httpx.HTTPError if the host-bridge call itself fails."""
    if not agent.runtime_type:
        raise AgentRunDispatchError(f"Agent '{agent.name}' has no runtime_type for CLI dispatch")
    if not agent.forgerouter_api_key_encrypted:
        raise AgentRunDispatchError(f"Agent '{agent.name}' has no ForgeRouter credential")
    api_key = decrypt_secret(agent.forgerouter_api_key_encrypted)

    body = {
        "run_id": run_id,
        "runtime_type": agent.runtime_type,
        "project_path": project_path,
        "prompt": prompt,
        "model_ref": model_ref,
        "routing_group": routing_group,
        "api_key": api_key,
        "mode": mode,
        "max_seconds": max_seconds,
        "max_budget_usd": max_budget_usd,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{settings.CHAT_BRIDGE_URL}/v1/agent-runs",
            json=body,
            headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
        )
        response.raise_for_status()
        return response.json()


async def poll_agent_run(run_id: str) -> dict:
    """GET /v1/agent-runs/{run_id} -- current status/output of a dispatched run."""
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{settings.CHAT_BRIDGE_URL}/v1/agent-runs/{run_id}",
            headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
        )
        response.raise_for_status()
        return response.json()
