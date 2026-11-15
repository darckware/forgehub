"""Which delegation an agent needs on the sensitive ForgeHub MCP routes (MCP split plan, Fase 2b;
docs/architecture/MCP_FASE2_AUTHORIZATION_SPEC.md, decisions D2 and B; business rule MCP-023).

The middleware asks ``required_action`` for every request. When the request carries an agent's own
``agt_`` credential and the route maps to an action here, the agent must hold an active
``AuthorityDelegation`` for it (``authorize_action``), or it gets 403. People (JWT) are not
affected, and a bridge-token-only call is still let through until Fase 2d.

Only an admin grants these actions (governed_approval.grant_delegation).
"""
from __future__ import annotations

import re

OPS_READ = "ops.read"
OPS_AUDIT_RUN = "ops.audit.run"
OPS_BACKUP_RUN = "ops.backup.run"
OPS_DEPLOY_RESTART = "ops.deploy.restart"
OPS_DATABASE_QUERY = "ops.database.query"
REGISTRY_READ = "registry.read"
REGISTRY_MANAGE = "registry.manage"
REGISTRY_CREDENTIAL_REQUEST = "registry.credential.request"

AGENT_MCP_ACTIONS = (
    OPS_READ, OPS_AUDIT_RUN, OPS_BACKUP_RUN, OPS_DEPLOY_RESTART, OPS_DATABASE_QUERY,
    REGISTRY_READ, REGISTRY_MANAGE, REGISTRY_CREDENTIAL_REQUEST,
)

_SEG = r"[^/]+"
# (methods, full-path pattern, action). First match wins; order matters only where patterns overlap.
_RULES: tuple[tuple[frozenset[str], re.Pattern[str], str], ...] = tuple(
    (frozenset(methods), re.compile(pattern), action) for methods, pattern, action in (
        # Operations
        (("GET",), r"/api/v1/system-stats", OPS_READ),
        (("POST",), r"/api/v1/system-control/backups/run", OPS_BACKUP_RUN),
        (("GET",), r"/api/v1/system-control/.*", OPS_READ),
        (("GET",), r"/api/v1/backups(/.*)?", OPS_READ),
        (("POST",), rf"/api/v1/deploy/containers/{_SEG}/restart", OPS_DEPLOY_RESTART),
        (("GET",), r"/api/v1/deploy/.*", OPS_READ),
        (("POST",), r"/api/v1/audit/run", OPS_AUDIT_RUN),
        (("POST",), rf"/api/v1/audit/checks/{_SEG}/(run|remediate)", OPS_AUDIT_RUN),
        (("GET",), r"/api/v1/audit/.*", OPS_READ),
        (("GET",), r"/api/v1/servers", OPS_READ),
        (("POST",), r"/api/v1/database/query", OPS_DATABASE_QUERY),
        # Registry. The skills catalog (GET /agents/skills, /agents/{id}/skills) stays open: the
        # core server's list_agent_skills reads it.
        (("POST",), rf"/api/v1/agents/{_SEG}/credentials", REGISTRY_CREDENTIAL_REQUEST),
        (("DELETE",), rf"/api/v1/agents/{_SEG}/credentials/{_SEG}", REGISTRY_MANAGE),
        (("GET",), rf"/api/v1/agents/{_SEG}/credentials", REGISTRY_READ),
        (("GET",), rf"/api/v1/agents/{_SEG}/profile-files(/.*)?", REGISTRY_READ),
        (("PUT",), rf"/api/v1/agents/{_SEG}/profile-files/{_SEG}", REGISTRY_MANAGE),
        (("POST",), rf"/api/v1/agents/{_SEG}/skills", REGISTRY_MANAGE),
        (("DELETE",), rf"/api/v1/agents/{_SEG}/skills/{_SEG}", REGISTRY_MANAGE),
        (("POST",), r"/api/v1/agents/sync/hermes-foundation", REGISTRY_MANAGE),
        (("GET",), r"/api/v1/tools(/.*)?", REGISTRY_READ),
        (("POST", "PATCH", "PUT", "DELETE"), r"/api/v1/tools(/.*)?", REGISTRY_MANAGE),
    )
)


def required_action(method: str, path: str) -> str | None:
    """The delegation an agent caller needs for this route, or None when the route is not gated."""
    path = path.rstrip("/") or path
    for methods, pattern, action in _RULES:
        if method in methods and pattern.fullmatch(path):
            return action
    return None
