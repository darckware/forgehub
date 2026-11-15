"""The two ForgeHub MCP actions that go through Marcelo's approval when they are outside the calling
agent's function (MCP split plan, Fase 2b; business rule MCP-023).

Marcelo, 2026-11-15: "eu não posso bloquear nenhum agente de usar forgehub" and "os agentes estão
aqui para trabalhar em todo o sistema de acordo com suas funções". So nothing is refused:

- every agent uses every ForgeHub tool;
- restarting a container and querying a database directly run at once for the functions that do
  that work, and an explicit admin delegation adds an agent outside them;
- for any other agent the call becomes a request in Pessoal > Tarefas dos agentes > Aprovação.
  Once approved, ForgeHub runs it itself and writes the result on that message
  (``core/agent_action_requests.py``); the agent reads it there.

An agent's function is its registered ``Agent.department``, so changing the function changes what
runs without approval, and a new agent gets what its function gives.
"""
from __future__ import annotations

import re

OPS_DEPLOY_RESTART = "ops.deploy.restart"
OPS_DATABASE_QUERY = "ops.database.query"

AGENT_MCP_ACTIONS = (OPS_DEPLOY_RESTART, OPS_DATABASE_QUERY)

# Functions (Agent.department) whose work includes the action: no approval needed.
FUNCTION_ACTIONS: dict[str, frozenset[str]] = {
    OPS_DEPLOY_RESTART: frozenset({"Executive Orchestration", "Platform & Operations"}),
    OPS_DATABASE_QUERY: frozenset({
        "Executive Orchestration", "Platform & Operations", "Security & Assurance", "Knowledge & Context",
    }),
}

_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("POST", re.compile(r"/api/v1/deploy/containers/(?P<container>[^/]+)/restart"), OPS_DEPLOY_RESTART),
    ("POST", re.compile(r"/api/v1/database/query"), OPS_DATABASE_QUERY),
)


def required_action(method: str, path: str) -> tuple[str, dict[str, str]] | None:
    """The action a route performs and its path parameters, or None when the route is free for all."""
    path = path.rstrip("/") or path
    for rule_method, pattern, action in _RULES:
        match = pattern.fullmatch(path) if method == rule_method else None
        if match:
            return action, match.groupdict()
    return None


def within_function(department: str | None, action: str) -> bool:
    return (department or "").strip() in FUNCTION_ACTIONS.get(action, frozenset())
