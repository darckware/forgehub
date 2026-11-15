"""An agent's restart or direct database query that falls outside its function becomes a request for
Marcelo's approval, and ForgeHub runs it once approved (business rule MCP-023; see
``core/agent_mcp_actions.py`` for which functions skip this).

The request is an ordinary Messages item, so it shows in Pessoal > Tarefas dos agentes > Aprovação
with no new screen: a task from the agent to itself, ``requires_approval`` pending, never scheduled
(no agent run), ``context_area = "agent_action:<action>"``. The exact parameters are in its body
between markers; the body is part of the approval fingerprint, so an edit voids an approval.

Approving it (``demand_workflow.decide_demand``) runs the action here, in the backend, and writes the
outcome on the same message (``dispatch_result``, ``dispatch_status`` completed or failed). The agent
reads it with ``list_agent_messages`` / ``get_agent_message``.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_mcp_actions import OPS_DATABASE_QUERY, OPS_DEPLOY_RESTART
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand

logger = logging.getLogger("forgehub.agent_action_requests")

CONTEXT_PREFIX = "agent_action:"
_BEGIN = "<<<parametros>>>"
_END = "<<<fim>>>"
_MAX_RESULT = 60_000

_LABELS = {
    OPS_DEPLOY_RESTART: "reiniciar o contêiner {container}",
    OPS_DATABASE_QUERY: "consultar o banco {instance}/{db}",
}


def is_agent_action(demand: AgentDemand) -> bool:
    return (demand.context_area or "").startswith(CONTEXT_PREFIX)


def _params_of(demand: AgentDemand) -> dict:
    body = demand.body or ""
    start, end = body.find(_BEGIN), body.find(_END)
    if start < 0 or end < start:
        raise ValueError("request parameters missing")
    return json.loads(body[start + len(_BEGIN):end])


async def request_approval(db: AsyncSession, agent: Agent, action: str, params: dict) -> AgentDemand:
    """The pending approval request for this agent, action and parameters; reused when an identical
    one is still waiting, so a retried tool call never files it twice."""
    context = f"{CONTEXT_PREFIX}{action}"
    payload = json.dumps(params, ensure_ascii=False, sort_keys=True)
    label = _LABELS[action].format(**{"container": "?", "instance": "?", "db": "?", **params})
    body = (
        f"{agent.name} pediu para {label}.\n\n"
        "Essa ação fica fora da função dele, então precisa da aprovação do Marcelo. Aprovada, o ForgeHub a "
        "executa e grava o resultado nesta mensagem.\n\n"
        f"{_BEGIN}{payload}{_END}"
    )
    existing = (await db.execute(select(AgentDemand).where(
        AgentDemand.from_agent_id == agent.id, AgentDemand.context_area == context,
        AgentDemand.approval_status == "pending", AgentDemand.status != "archived",
        AgentDemand.body == body,
    ))).scalars().first()
    if existing is not None:
        return existing
    from app.db.models.notification import Notification

    demand = AgentDemand(
        from_agent=agent.profile_slug or agent.name, from_agent_id=agent.id, target_agent_id=agent.id,
        subject=f"Aprovação: {agent.name} quer {label}"[:255], body=body, origin_type="task",
        requires_approval=True, approval_status="pending", context_area=context, channel="agent",
        working_path="/root", fixed_agent=True,
        scheduled_at=None,  # never dispatched to an agent: the backend runs it on approval
    )
    db.add(demand)
    await db.flush()
    await db.refresh(demand)  # the #number comes from the database
    db.add(Notification(
        source="system", severity="warning", title="Pedido de agente aguardando aprovação",
        message=f"#{demand.number}: {agent.name} quer {label}.",
        event_key=f"agent-action:{demand.id}", occurred_at=datetime.now(timezone.utc),
    ))
    await db.commit()
    await db.refresh(demand)
    return demand


async def execute_approved(db: AsyncSession, demand: AgentDemand) -> None:
    """Run an approved agent action and record the outcome on its message."""
    action = (demand.context_area or "")[len(CONTEXT_PREFIX):]
    now = datetime.now(timezone.utc)
    try:
        params = _params_of(demand)
        if action == OPS_DEPLOY_RESTART:
            from app.api.routes.deploy import restart_container

            result = await restart_container(params["container"])
        elif action == OPS_DATABASE_QUERY:
            from app.api.routes.database import QueryRequest, execute_query

            result = await execute_query(QueryRequest(**params))
            result = result.model_dump() if hasattr(result, "model_dump") else result
        else:
            raise ValueError(f"unknown agent action {action!r}")
        text = json.dumps(result, ensure_ascii=False, default=str)
        demand.dispatch_status = "completed"
        demand.dispatch_result = ("Aprovado e executado pelo ForgeHub.\n\n" + text)[:_MAX_RESULT]
        demand.dispatch_error = None
    except Exception as exc:  # the outcome is recorded either way; never left pending
        detail = getattr(exc, "detail", None) or str(exc)
        logger.warning("approved agent action %s on #%s failed: %s", action, demand.number, detail)
        demand.dispatch_status = "failed"
        demand.dispatch_error = f"Aprovado, mas a execução falhou: {detail}"[:2000]
    demand.task_execution_at = now
    demand.agent_processed_at = None  # back in the agent's inbox with the result
    await db.commit()
