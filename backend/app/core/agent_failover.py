"""When an external agent runs out of quota, its work moves to another one.

Marcelo, 2026-11-04: a limit must be identified and the agent replaced, so a
queue never waits on, or keeps failing against, an agent with no quota.

Only plain Messages work moves. A mission task keeps the executor its baseline
froze, a message marked `fixed_agent` (a review, whose reviewer must not be the
executor) keeps its agent, an approved text keeps its approval, and a failure
check belongs to its owner. Queued, those wait for the reset instead.

Moving and waiting are two questions, because a run that already started and
ended on a limit has more to answer for than a queued message: see
`can_wait_for_reset`.
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


def can_wait_for_reset(demand: AgentDemand) -> bool:
    """Whether a run that ended on a usage limit may go back to the queue.

    A `fixed_agent` message and a failure check run again by themselves after
    the reset, on the same agent. A failure check has to: it can't open a check
    of itself, so failing it ended the diagnosis in silence (#42186).

    The others stay failed, with the limit in `dispatch_error`:
    - `requires_approval`: the run may have had effects, and an approval covers
      one execution. The failure check it opens verifies them first, and a
      Moodle approval can expire during the wait.
    - `task_execution_id`: the execution would stay `running` with no run, and
      its failure is what the task flow and the mission cycle act on.
    - `mission_context_version_id`: the mission cycle reschedules it.
    """
    return not (demand.requires_approval or demand.task_execution_id or demand.mission_context_version_id)


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
    free = []
    for candidate in agents:
        if (candidate.id != demand.target_agent_id and candidate.id not in unavailable
                and candidate.id not in busy
                and not await executor_eligibility(db, demand, candidate.id)):
            free.append(candidate)
    return min(free, key=lambda a: FAILOVER_ORDER.index(a.runtime_type), default=None)


async def executor_eligibility(db: AsyncSession, demand: AgentDemand, candidate_id: uuid.UUID) -> list[dict]:
    """Explain deterministic contract blockers without granting assignment authority."""
    reasons = []
    candidate = await db.get(Agent, candidate_id, populate_existing=True)
    if candidate is None or not candidate.is_active or candidate.status != "active":
        return [{"code": "EXECUTOR_INACTIVE"}]
    if not candidate.runtime_type:
        reasons.append({"code": "EXECUTOR_RUNTIME_MISSING"})
    if candidate_id != demand.target_agent_id:
        if not can_switch(demand):
            reasons.append({"code": "EXECUTOR_BOUND"})
        from app.core.message_triage_context import domain_for
        source_ids = {i for i in (demand.from_agent_id, demand.target_agent_id, demand.incubation_owner_id) if i}
        sources = {a.id: a for a in (await db.scalars(select(Agent).where(Agent.id.in_(source_ids))
            .execution_options(populate_existing=True))).all()}
        if (domain_for(demand, sources) != "athos"
                or demand.channel in {"personal", "whatsapp", "whatsapp_group"}):
            reasons.append({"code": "PRIVATE_CONTEXT_BOUND"})
        previous = sources.get(demand.target_agent_id)
        if previous is None or not previous.default_role or not candidate.default_role:
            reasons.append({"code": "EXECUTOR_CONTRACT_UNKNOWN"})
        elif candidate.default_role != previous.default_role:
            reasons.append({"code": "EXECUTOR_ROLE_MISMATCH", "required_role": previous.default_role,
                            "candidate_role": candidate.default_role})
    from datetime import date
    from app.core.mission import project_id_for_task_source
    from app.core.mission_plan import NON_EXECUTOR_ROLES
    from app.db.models.agent import AgentSkill
    from app.db.models.orchestration import ProjectAgentMembership, TaskExecutionReview
    from app.db.models.task import ProjectTask, TaskAssignment, TaskExecution, TaskRequiredSkill

    task_id = demand.origin_id if demand.origin_type == "task" else None
    if demand.task_execution_id is not None:
        carried_execution = await db.get(TaskExecution, demand.task_execution_id, populate_existing=True)
        if carried_execution is not None:
            task_id = carried_execution.task_id
    task = await db.get(ProjectTask, task_id, populate_existing=True) if task_id else None
    project_id = await project_id_for_task_source(db, task.planning_item_id, task.change_request_id) if task else demand.project_id
    review = await db.scalar(select(TaskExecutionReview).where(
        TaskExecutionReview.runtime_session_ref == str(demand.id)).execution_options(populate_existing=True))
    # Existing standalone tasks can keep their assigned executor without a
    # project. Missing project facts cannot authorize a substitute, however.
    if task is not None and project_id is None and candidate_id != demand.target_agent_id:
        reasons.append({"code": "EXECUTOR_PROJECT_CONTEXT_MISSING"})
    # Mission membership governs mission tasks, not every common project.
    # Preserve an unchanged common-project assignment; substitution and review
    # still require the explicit project contract rather than inferred rights.
    from app.core.task_baseline_guard import task_missions
    governed = bool(await task_missions(db, task)) if task is not None else False
    if project_id is not None and (governed or review is not None or candidate_id != demand.target_agent_id):
        member = await db.scalar(select(ProjectAgentMembership).where(
            ProjectAgentMembership.project_id == project_id, ProjectAgentMembership.agent_id == candidate_id,
            ProjectAgentMembership.status == "active").execution_options(populate_existing=True))
        today = date.today()
        if (member is None or (member.valid_from and member.valid_from > today)
                or (member.valid_to and member.valid_to < today)):
            reasons.append({"code": "EXECUTOR_PROJECT_MEMBERSHIP_REQUIRED"})
        else:
            if review is not None:
                if not member.can_review:
                    reasons.append({"code": "EXECUTOR_REVIEW_PERMISSION_REQUIRED"})
            elif member.role in NON_EXECUTOR_ROLES:
                reasons.append({"code": "EXECUTOR_PROJECT_ROLE_MISMATCH"})
            if member.allowed_runtimes is not None and candidate.runtime_type not in member.allowed_runtimes:
                reasons.append({"code": "EXECUTOR_RUNTIME_NOT_ALLOWED"})
    if review is not None:
        from app.core.task_completion_guard import resolve_executor_agent_id
        execution = await db.get(TaskExecution, review.execution_id)
        if execution is not None and await resolve_executor_agent_id(db, execution) == candidate_id:
            reasons.append({"code": "EXECUTOR_CANNOT_REVIEW_OWN_WORK"})
    if task is not None:
        if task.status in {"done", "deployed", "cancelled"}:
            reasons.append({"code": "EXECUTOR_TASK_TERMINAL"})
        required = list((await db.scalars(select(TaskRequiredSkill).where(
            TaskRequiredSkill.task_id == task.id, TaskRequiredSkill.is_mandatory.is_(True))
            .execution_options(populate_existing=True))).all())
        wanted = {r.skill_id for r in required}
        held = set((await db.scalars(select(AgentSkill.skill_id).where(
            AgentSkill.agent_id == candidate_id, AgentSkill.skill_id.in_(wanted)))).all()) if wanted else set()
        for skill_id in sorted(wanted - held, key=str):
            reasons.append({"code": "EXECUTOR_SKILL_REQUIRED", "skill_id": str(skill_id)})
        for required_skill in required:
            if required_skill.minimum_proficiency:
                reasons.append({"code": "EXECUTOR_SKILL_PROFICIENCY_UNVERIFIED", "skill_id": str(required_skill.skill_id)})
        if review is None:
            assignment = await db.scalar(select(TaskAssignment).where(TaskAssignment.task_id == task.id,
                TaskAssignment.status == "active").order_by(TaskAssignment.created_at.desc()).limit(1))
            if assignment is not None and assignment.agent_id and assignment.agent_id != candidate_id:
                reasons.append({"code": "EXECUTOR_ASSIGNMENT_CHANGED"})
    return reasons


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
