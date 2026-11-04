"""A browser session for an agent, opened with its own `agt_` credential.

Agents need the screens, to test them and to write manuals, without a person's
login. The credential comes from ForgeVault; what the session may see is the
`svc-agente` user's profile, so access is controlled in Users and Profiles.

Most routes here only check that a token is valid, so a read-only profile alone
would not stop writes. `agent_session_refusal` is the real boundary: read
methods only, on an allowlist of project areas, anything else refused. Before
adding an area, check that none of its GETs writes or returns private content.
"""
from __future__ import annotations

import ipaddress
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.db.models.agent import Agent, AgentServiceCredential
from app.db.models.governance import AuditEvent
from app.db.models.user import User

AGENT_SESSION_PURPOSE = "agent_session"
AGENT_SESSION_MINUTES = 30
SERVICE_USERNAME = "svc-agente"

# Access audit, one entity type so the admin screen reads it with one query.
AUDIT_ENTITY = "agent_screen_access"
EVENT_OPENED = "session_opened"
EVENT_REFUSED = "session_refused"
EVENT_AREA_READ = "area_read"
EVENT_REQUEST_DENIED = "request_denied"
UNKNOWN_AGENT_ID = uuid.UUID(int=0)
_seen: dict[tuple[str, str], float] = {}

_READ_METHODS = {"GET", "HEAD"}
# Project work only. Messages, channels, Foundation, docs, audit, tools and agent
# activity stay closed: they carry conversations, memories, files or GETs that
# write (security review, message 41917). A new area starts closed.
_ALLOWED_AREAS = frozenset({
    "bug-reports", "environments", "factory", "feature-requests", "missions", "pipelines",
    "planning-items", "products", "projects", "responsibility-areas", "service-lines", "tasks",
    "triage-decisions", "version-scope-items",
})
_CLOSED_SEGMENTS = frozenset({
    "attachments", "content", "download", "file", "files", "memory", "messages", "stream",
})
_AGENT_ROSTER = re.compile(r"^agents(/[0-9a-f-]{36})?$")
_SECRET_LOOKING = re.compile(r"agt_[A-Za-z0-9_-]+|[A-Za-z0-9_-]{40,}")
_SEEN_LIMIT = 5000


def is_agent_session(payload: dict[str, Any] | None) -> bool:
    return bool(payload) and payload.get("purpose") == AGENT_SESSION_PURPOSE


def create_agent_session_token(agent: Agent, credential_id: uuid.UUID) -> str:
    return create_access_token(
        subject=SERVICE_USERNAME,
        expires_delta=timedelta(minutes=AGENT_SESSION_MINUTES),
        extra_claims={"purpose": AGENT_SESSION_PURPOSE, "agent": agent.profile_slug or agent.name,
                      "agent_id": str(agent.id), "credential_id": str(credential_id),
                      "session_id": uuid.uuid4().hex},
    )


def _clean(value: str, limit: int) -> str:
    """Client-controlled text: a key pasted there must not reach the audit."""
    return _SECRET_LOOKING.sub("[oculto]", value)[:limit]


def _client_ip(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def request_origin(request: Any) -> dict[str, str | None]:
    forwarded = _client_ip(request.headers.get("x-forwarded-for", "").split(",")[0])
    return {
        "ip_address": forwarded or (request.client.host if request.client else None),
        "user_agent": _clean(request.headers.get("user-agent") or "", 200) or None,
    }


def audit_path(path: str) -> str:
    return _clean(path, 200)


def audit_access(db: AsyncSession, event: str, agent_id: uuid.UUID | None, actor: str, **details: Any) -> None:
    db.add(AuditEvent(entity_type=AUDIT_ENTITY, entity_id=agent_id or UNKNOWN_AGENT_ID,
                      event_type=event, actor=actor[:100], payload=details))


def first_time(session_id: str, key: str) -> bool:
    """True once per session and key, so a flood becomes one audit row."""
    now = time.monotonic()
    if len(_seen) > _SEEN_LIMIT:
        for seen_key, seen_at in list(_seen.items()):
            if now - seen_at > AGENT_SESSION_MINUTES * 60:
                del _seen[seen_key]
        if len(_seen) > _SEEN_LIMIT:
            _seen.clear()
    if (session_id, key) in _seen:
        return False
    _seen[(session_id, key)] = now
    return True


def area_of(path: str) -> str:
    return path.removeprefix("/api/v1/").split("/")[0]


def agent_session_refusal(method: str, path: str) -> str | None:
    """Why an agent session may not make this call, or None when it may."""
    if method not in _READ_METHODS:
        return "An agent session is read-only"
    target = path.removeprefix("/api/v1/").rstrip("/")
    if target == "auth/me" or _AGENT_ROSTER.match(target):
        return None
    parts = target.split("/")
    if parts[0] not in _ALLOWED_AREAS or _CLOSED_SEGMENTS.intersection(parts):
        return "This area is not open to agent sessions"
    return None


async def agent_session_is_live(db: AsyncSession, payload: dict[str, Any]) -> bool:
    """Revoking the credential, turning the agent off or disabling `svc-agente` ends it at once."""
    try:
        credential_id = uuid.UUID(str(payload.get("credential_id")))
    except ValueError:
        return False
    credential = await db.get(AgentServiceCredential, credential_id)
    if credential is None or credential.revoked_at is not None:
        return False
    if credential.expires_at and credential.expires_at <= datetime.now(timezone.utc):
        return False
    agent = await db.get(Agent, credential.agent_id)
    if agent is None or not agent.is_active or agent.status != "active" or not agent.screen_access_enabled:
        return False
    user = (await db.execute(select(User).where(User.username == SERVICE_USERNAME))).scalar_one_or_none()
    return user is not None and user.is_active
