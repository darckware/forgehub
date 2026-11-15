"""Who is calling a bridge-token route (MCP split plan, Fase 2a; docs/architecture/MCP_FASE2_AUTHORIZATION_SPEC.md).

The agent-facing routes used to trust the shared bridge token alone and take the agent from the
request (``from_agent``, ``agent``), so any holder of the token could act as any agent. From 2a
the ForgeHub MCP also sends the agent's own ``agt_`` credential. When it is present:

- the route checks it is an active credential of an active agent (401 otherwise), and
- the agent the request names must be that agent (403 ``AGENT_IMPERSONATION``).

Without it nothing changes yet (2a keeps every permission); the middleware logs those calls so
2d can stop accepting the bridge token alone once none remain.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

from fastapi import HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent import Agent, AgentServiceCredential

logger = logging.getLogger("forgehub.bridge_caller")

_STATE_KEY = "bridge_caller_agent"


def agent_credential(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    return token if token.startswith("agt_") else None


async def caller_agent(request: Request, db: AsyncSession) -> Agent | None:
    """The agent behind the request's ``agt_`` credential, or None when it carries none.
    A credential that is unknown, revoked, expired or of an inactive agent is refused (401):
    a caller that presents an identity must present a valid one."""
    if hasattr(request.state, _STATE_KEY):
        return getattr(request.state, _STATE_KEY)
    token = agent_credential(request)
    agent: Agent | None = None
    if token is not None:
        agent = (await db.execute(
            select(Agent)
            .join(AgentServiceCredential, AgentServiceCredential.agent_id == Agent.id)
            .where(
                AgentServiceCredential.token_hash == hashlib.sha256(token.encode()).hexdigest(),
                AgentServiceCredential.revoked_at.is_(None),
                or_(AgentServiceCredential.expires_at.is_(None),
                    AgentServiceCredential.expires_at > datetime.now(timezone.utc)),
                Agent.is_active.is_(True), Agent.status == "active",
            )
        )).scalar_one_or_none()
        if agent is None:
            raise HTTPException(status_code=401, detail={
                "code": "AGENT_CREDENTIAL_INVALID",
                "message": "The agent credential is unknown, revoked, expired or of an inactive agent.",
            })
    setattr(request.state, _STATE_KEY, agent)
    return agent


def _same_agent(agent: Agent, claimed: str | None) -> bool:
    value = (claimed or "").strip().lower()
    return bool(value) and value in {
        (agent.profile_slug or "").strip().lower(), (agent.name or "").strip().lower(), str(agent.id),
    }


async def assert_acts_as(request: Request, db: AsyncSession, claimed: str | None) -> Agent | None:
    """Refuse a request that names an agent other than the authenticated one. Returns the
    authenticated agent (None for a bridge-token-only call, still accepted in 2a)."""
    agent = await caller_agent(request, db)
    if agent is not None and not _same_agent(agent, claimed):
        logger.warning("agent %s tried to act as %r on %s %s", agent.profile_slug, claimed,
                       request.method, request.url.path)
        raise HTTPException(status_code=403, detail={
            "code": "AGENT_IMPERSONATION",
            "message": f"This credential belongs to {agent.profile_slug or agent.name}; "
                       "a request may only act as the agent that authenticated it.",
        })
    return agent


def log_bridge_only_call(request: Request) -> None:
    """Middleware hook: a bridge-token call that carries no agent credential (2d readiness)."""
    if agent_credential(request) is None:
        logger.info("bridge-token call without agent credential: %s %s", request.method, request.url.path)
