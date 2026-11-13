"""Shared client for the host-bridge's governed CLI runner (`/v1/agent-runs`).

Two call sites already talk to this endpoint by hand-rolling the same httpx
POST/GET (`api/routes/execution.py`'s `dispatch_package`/`refresh_runtime`/
`cancel_runtime`, `api/routes/orchestration.py`'s
`dispatch_execution_review`) -- this module factors that out so a third
caller (`api/routes/demand.py`'s Inbox dispatch) doesn't duplicate it again.
Payload shape matches those existing callers exactly; migrating them to use
this module instead is a separate, optional follow-up.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

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
    restricted_toolsets: str | None = None,
    runtime_intent: dict | None = None,
    work_package_hash: str | None = None,
    runtime_type: str | None = None,
    api_key: str = "",
) -> dict:
    """POST /v1/agent-runs for `agent`. Raises AgentRunDispatchError if the
    agent can't be dispatched at all (no runtime_type/profile_slug); raises
    httpx.HTTPError if the host-bridge call itself fails.

    Claude Code, Codex and agy always run on their own native login and
    default model, never ForgeRouter (2026-10-24): `forgerouter/auto` sent
    Aramis's runs to free models that stopped mid-task with exit 0. So no
    ForgeRouter credential is decrypted or sent; the bridge ignores
    `model_ref`/`routing_group`/`api_key` for these runtimes. `api_key` is
    only for a Hermes run of a governed work package (execution.py), which
    has always carried the agent's ForgeRouter key.

    `runtime_intent` is honoured only with RUNTIME_CONTRACT_ENABLED; off, the
    run goes to the plain /v1/agent-runs exactly as before the contract."""
    if not settings.RUNTIME_CONTRACT_ENABLED:
        runtime_intent = None
    runtime = runtime_type or agent.runtime_type
    if not runtime:
        raise AgentRunDispatchError(f"Agent '{agent.name}' has no runtime_type for CLI dispatch")
    if runtime == "hermes" and not agent.profile_slug:
        raise AgentRunDispatchError(f"Agent '{agent.name}' has no profile_slug for hermes dispatch")
    # External runtimes only see the task text; their identity rides along.
    identity = agent if runtime == agent.runtime_type else SimpleNamespace(
        runtime_type=runtime, name=agent.name, home_path=agent.home_path, profile_slug=agent.profile_slug)
    preamble = external_identity_preamble(identity)
    if preamble:
        prompt = f"{preamble}\n\n{prompt}"

    body = {
        "run_id": run_id,
        "runtime_type": runtime,
        "agent_slug": agent.profile_slug,
        "project_path": project_path,
        "prompt": prompt,
        "model_ref": model_ref,
        "routing_group": routing_group,
        "api_key": api_key,
        "mode": mode,
        "max_seconds": max_seconds,
        "max_budget_usd": max_budget_usd,
        "hermes_profile": agent.profile_slug if runtime == "hermes" else None,
        "autonomous": bool(agent.autonomous_runs),
    }
    if work_package_hash is not None:
        body['work_package_hash'] = work_package_hash
    if runtime_intent is not None:
        from app.api.schemas.runtime_intent import RuntimeIntent
        try:
            body["runtime_intent"] = RuntimeIntent.model_validate(runtime_intent).model_dump()
        except ValueError as exc:  # pydantic ValidationError included
            # e.g. a stored package asking for `delegate` after the switch was
            # turned off: a refusal to run, never a 500.
            raise AgentRunDispatchError(f"Runtime intent no longer valid: {exc}") from exc
    # Its own route: a bridge that doesn't know it answers 404 instead of running unrestricted.
    path = "/v1/agent-runs/contextual" if runtime_intent is not None else "/v1/agent-runs"
    if restricted_toolsets:
        if runtime != "hermes":
            raise AgentRunDispatchError(f"Agent '{agent.name}' cannot run with restricted tools")
        body["restricted_toolsets"] = restricted_toolsets
        path = "/v1/agent-runs/restricted"
    # After the refusals above, so a refused run leaves no credential behind.
    # A restricted run never gets one: it reads text from outside (instructors' group).
    # Hermes only when on the direct access list: a profile's stdio MCPs can all see the path.
    gets_credential = runtime in ("claude", "codex", "agy") or (
        runtime == "hermes" and agent.direct_access_allowed)
    if runtime_intent and runtime_intent.get('strategy') == 'delegate':
        gets_credential = False
    if agent.id is not None and not restricted_toolsets and gets_credential:
        from app.db.base import AsyncSessionLocal
        from app.db.models.agent import AgentServiceCredential
        token = "agt_" + secrets.token_urlsafe(32)
        async with AsyncSessionLocal() as credential_db:
            credential_db.add(AgentServiceCredential(agent_id=agent.id, label=f"dispatch:{run_id}",
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=min(max_seconds, 7200) + 60)))
            await credential_db.commit()
        body["agent_service_token"] = token
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{settings.CHAT_BRIDGE_URL}{path}",
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
