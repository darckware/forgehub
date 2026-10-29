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

from app.core.agent_profile_files import external_identity_preamble
from app.core.config import settings
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
    agent can't be dispatched at all (no runtime_type/profile_slug); raises
    httpx.HTTPError if the host-bridge call itself fails.

    Claude Code, Codex and agy always run on their own native login and
    default model, never ForgeRouter (2026-10-24): `forgerouter/auto` sent
    Aramis's runs to free models that stopped mid-task with exit 0. So no
    ForgeRouter credential is decrypted or sent; the bridge ignores
    `model_ref`/`routing_group`/`api_key` for these runtimes."""
    if not agent.runtime_type:
        raise AgentRunDispatchError(f"Agent '{agent.name}' has no runtime_type for CLI dispatch")
    if agent.runtime_type == "hermes" and not agent.profile_slug:
        raise AgentRunDispatchError(f"Agent '{agent.name}' has no profile_slug for hermes dispatch")
    # External runtimes only see the task text; their identity rides along.
    preamble = external_identity_preamble(agent)
    if preamble:
        prompt = f"{preamble}\n\n{prompt}"

    body = {
        "run_id": run_id,
        "runtime_type": agent.runtime_type,
        "project_path": project_path,
        "prompt": prompt,
        "model_ref": model_ref,
        "routing_group": routing_group,
        "api_key": "",
        "mode": mode,
        "max_seconds": max_seconds,
        "max_budget_usd": max_budget_usd,
        "hermes_profile": agent.profile_slug if agent.runtime_type == "hermes" else None,
        "autonomous": bool(agent.autonomous_runs),
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{settings.CHAT_BRIDGE_URL}/v1/agent-runs",
            json=body,
            headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
        )
        if response.status_code in (400, 401, 403, 404, 422):
            raise AgentRunDispatchError(
                "Agent runner rejected the request; check working directory, runtime "
                "configuration and access permissions before retrying"
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
