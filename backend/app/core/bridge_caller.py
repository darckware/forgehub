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
import time
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent import Agent, AgentServiceCredential

logger = logging.getLogger("forgehub.bridge_caller")

_STATE_KEY = "bridge_caller_agent"


def agent_credential(request: Request | None) -> str | None:
    if request is None:  # a route function called directly (tests, internal callers)
        return None
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    return token if token.startswith("agt_") else None


async def caller_agent(request: Request | None, db: AsyncSession) -> Agent | None:
    """The agent behind the request's ``agt_`` credential, or None when it carries none.
    A credential that is unknown, revoked, expired or of an inactive agent is refused (401):
    a caller that presents an identity must present a valid one."""
    if request is None:
        return None
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
    """Exactly the slug the routes resolve by (``Agent.profile_slug ==``): a name or a different
    case could match one agent here and resolve another in the route (review F4)."""
    return bool(agent.profile_slug) and (claimed or "").strip() == agent.profile_slug


def _refuse(request: Request, agent: Agent, claimed: object) -> HTTPException:
    logger.warning("agent %s tried to act as %r on %s %s", agent.profile_slug, claimed,
                   request.method, request.url.path)
    return HTTPException(status_code=403, detail={
        "code": "AGENT_IMPERSONATION",
        "message": f"This credential belongs to {agent.profile_slug or agent.name}; "
                   "a request may only act as the agent that authenticated it.",
    })


async def assert_acts_as(request: Request | None, db: AsyncSession, claimed: str | None,
                         claimed_id: uuid.UUID | None = None) -> Agent | None:
    """Refuse a request that names an agent other than the authenticated one, by slug and,
    when the request also carries one, by id (review F1: ``from_agent_id`` wins over the slug
    in /demands/submit). Returns the authenticated agent; None for a bridge-token-only call,
    still accepted in 2a and logged."""
    agent = await caller_agent(request, db)
    if agent is None:
        if request is not None:
            log_bridge_only_call(request)
        return None
    if not _same_agent(agent, claimed):
        raise _refuse(request, agent, claimed)
    if claimed_id is not None and claimed_id != agent.id:
        raise _refuse(request, agent, str(claimed_id))
    return agent


# One line per (method, path) per hour: enough to know what still calls without a credential
# (2d readiness) without a line for every inbox poll (review F6).
_LOG_EVERY_SECONDS = 3600
_last_logged: dict[tuple[str, str], float] = {}


def log_bridge_only_call(request: Request) -> None:
    """A bridge-token call that carries no agent credential."""
    if agent_credential(request) is not None:
        return
    key = (request.method, request.url.path)
    now = time.monotonic()
    if now - _last_logged.get(key, -_LOG_EVERY_SECONDS) < _LOG_EVERY_SECONDS:
        return
    if len(_last_logged) > 5000:
        _last_logged.clear()
    _last_logged[key] = now
    logger.info("bridge-token call without agent credential: %s %s", request.method, request.url.path)
