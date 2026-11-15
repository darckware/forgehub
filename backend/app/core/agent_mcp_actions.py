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


# ----------------------------------------------------------------- servers per agent (D4 screen)
CORE_SERVER = "forgehub"
OPTIONAL_SERVERS = (
    "forgehub_factory", "forgehub_missions", "forgehub_ops", "forgehub_registry", "forgehub_remote",
    "forgehub_personal",
)
PERSONAL_SERVER = "forgehub_personal"

# What the screen suggests when an agent's function is set or changed; Marcelo adjusts per agent.
FUNCTION_DEFAULTS: dict[str, dict] = {
    "Executive Orchestration": {"servers": ["forgehub_factory", "forgehub_missions", "forgehub_ops", "forgehub_registry"],
                                "restart_mode": "direct", "query_mode": "direct"},
    "Platform & Operations": {"servers": ["forgehub_ops", "forgehub_registry", "forgehub_remote"],
                              "restart_mode": "direct", "query_mode": "direct"},
    "Security & Assurance": {"servers": ["forgehub_factory", "forgehub_ops", "forgehub_registry", "forgehub_remote"],
                             "restart_mode": "approval", "query_mode": "direct"},
    "Governance & Compliance": {"servers": ["forgehub_factory", "forgehub_ops", "forgehub_registry"],
                                "restart_mode": "approval", "query_mode": "approval"},
    "Engineering": {"servers": ["forgehub_factory", "forgehub_missions", "forgehub_ops"],
                    "restart_mode": "approval", "query_mode": "approval"},
    "Product & Planning": {"servers": ["forgehub_factory", "forgehub_missions"],
                           "restart_mode": "approval", "query_mode": "approval"},
    "Documentation": {"servers": ["forgehub_factory", "forgehub_missions", "forgehub_ops"],
                      "restart_mode": "approval", "query_mode": "approval"},
    "Knowledge & Context": {"servers": ["forgehub_ops"], "restart_mode": "approval", "query_mode": "direct"},
    "Marketing": {"servers": ["forgehub_factory"], "restart_mode": "approval", "query_mode": "approval"},
    "Customer Service & Sales": {"servers": ["forgehub_factory"], "restart_mode": "approval", "query_mode": "approval"},
    "Personal Assistant": {"servers": ["forgehub_factory", "forgehub_personal"],
                           "restart_mode": "approval", "query_mode": "approval"},
}
_NO_FUNCTION = {"servers": [], "restart_mode": "approval", "query_mode": "approval"}


def function_defaults(department: str | None) -> dict:
    return FUNCTION_DEFAULTS.get((department or "").strip(), _NO_FUNCTION)


def mode_for(access, department: str | None, action: str) -> str:
    """``direct`` or ``approval`` for this agent: its saved row, else what its function gives."""
    field = "restart_mode" if action == OPS_DEPLOY_RESTART else "query_mode"
    if access is not None:
        return getattr(access, field)
    return "direct" if within_function(department, action) else "approval"
