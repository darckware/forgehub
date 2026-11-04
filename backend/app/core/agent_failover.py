"""When an external agent runs out of quota, its work moves to another one.

Marcelo, 2026-11-04: a limit must be identified and the agent replaced, so a
queue never waits on, or keeps failing against, an agent with no quota.

Only plain Messages work moves. A mission task keeps the executor its baseline
froze, a message marked `fixed_agent` (a review, whose reviewer must not be the
executor) keeps its agent, an approved text keeps its approval, and a failure
check belongs to its owner. Those wait for the reset instead.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent

# Codex and agy first: Claude Code is the costly one (Marcelo, 2026-11-03).
FAILOVER_ORDER = ("codex", "agy", "claude")


def can_switch(demand: AgentDemand) -> bool:
    return not (
        demand.fixed_agent
        or demand.requires_approval
        or demand.task_execution_id
        or demand.mission_context_version_id
        or demand.failure_check_source_id
    )


async def substitute_for(
    db: AsyncSession, demand: AgentDemand, unavailable: set[uuid.UUID], busy: set[uuid.UUID]
) -> Agent | None:
    """The next free external agent, only when the target is an external one too."""
    agents = (await db.execute(select(Agent).where(
        Agent.runtime_type.in_(FAILOVER_ORDER), Agent.is_active.is_(True),
        Agent.status == "active", Agent.autonomous_runs.is_(True),
    ))).scalars().all()
    if demand.target_agent_id not in {agent.id for agent in agents}:
        return None
    free = [a for a in agents if a.id != demand.target_agent_id and a.id not in unavailable and a.id not in busy]
    return min(free, key=lambda a: FAILOVER_ORDER.index(a.runtime_type), default=None)


def switch_agent(db: AsyncSession, demand: AgentDemand, substitute: Agent, until: datetime | None) -> None:
    previous = demand.target_agent_id
    demand.target_agent_id = substitute.id
    demand.body = (
        "## Troca de agente por limite de uso\n"
        "O agente anterior ficou sem cota. Antes de começar, verifique o que já foi feito em "
        "`working_path` e continue sem repetir nada.\n\n" + (demand.body or "")
    )
    db.add(AuditEvent(
        entity_type="agent_demand", entity_id=demand.id, event_type="agent_switched_usage_limit",
        actor="forgehub:usage-limit",
        payload={"from_agent_id": str(previous), "to_agent_id": str(substitute.id),
                 "until": until.isoformat() if until else None},
    ))
