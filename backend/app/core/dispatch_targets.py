"""Target serialization for Messages runs (Plano Integrado M0.6b,
docs/architecture/MCP_MISSION_TOOLS_SPEC.md §4.3, decision D-M0-2).

A task declares what its run holds exclusively in `task_execution_targets`.
`reserve_dispatch` refuses a run (`TARGET_BUSY`, the item stays queued) while
another in-flight, reserved or uncertain run holds an equal target:
- `publish:production:*` for every task in Messages (the 28/10 incident was
  outside any mission);
- `worktree` and `branch` only for mission tasks, which also hold their
  `working_path` as an implicit worktree target.
Must run under reserve_dispatch's advisory lock.
"""
from __future__ import annotations

import os

from sqlalchemy import and_, or_, select

from app.core.demand_workflow import WorkflowBlocked
from app.db.models.demand import AgentDemand
from app.db.models.task import ProjectTask, TaskExecutionTarget


def normalize_target_key(kind: str, key: str) -> str:
    key = (key or "").strip()
    if kind == "worktree":
        return os.path.realpath(key)
    if kind == "branch":
        repo, _, branch = key.partition("#")
        return f"{os.path.realpath(repo.strip())}#{branch.strip()}"
    if kind == "publish":
        return key.lower()
    raise ValueError(f"Unknown execution target kind: {kind!r}")


def is_production_publish(kind: str, key: str) -> bool:
    return kind == "publish" and key.startswith("production:")


async def demand_targets(db, demand: AgentDemand) -> set[str]:
    """`<kind>:<key>` targets the run of `demand` holds."""
    from app.core.task_baseline_guard import task_missions

    if demand.origin_type != "task" or demand.origin_id is None:
        return set()
    task = await db.get(ProjectTask, demand.origin_id)
    if task is None:
        return set()
    mission_task = bool(await task_missions(db, task))
    rows = (await db.execute(
        select(TaskExecutionTarget.kind, TaskExecutionTarget.target_key)
        .where(TaskExecutionTarget.task_id == task.id)
    )).all()
    targets = set()
    for kind, key in rows:
        key = normalize_target_key(kind, key)
        if mission_task or is_production_publish(kind, key):
            targets.add(f"{kind}:{key}")
    if mission_task and (demand.working_path or "").strip():
        targets.add(f"worktree:{normalize_target_key('worktree', demand.working_path)}")
    return targets


def _holding_clause():
    # In flight, reserved (run id before the bridge call) or uncertain
    # (requires_reconciliation): each one may still be touching the target.
    return or_(
        AgentDemand.dispatch_status.in_(("dispatched", "running")),
        and_(AgentDemand.dispatch_status.is_(None), AgentDemand.agent_run_id.is_not(None)),
        and_(
            AgentDemand.dispatch_status == "failed", AgentDemand.agent_run_id.is_not(None),
            or_(AgentDemand.dispatch_error.is_(None), AgentDemand.dispatch_error.ilike("%uncertain%")),
        ),
    )


async def assert_targets_free(db, demand: AgentDemand) -> None:
    wanted = await demand_targets(db, demand)
    if not wanted:
        return
    holders = (await db.execute(
        select(AgentDemand)
        .where(AgentDemand.id != demand.id, AgentDemand.origin_type == "task", _holding_clause())
        .order_by(AgentDemand.created_at)
    )).scalars().all()
    for holder in holders:
        shared = wanted & await demand_targets(db, holder)
        if shared:
            raise WorkflowBlocked(f"TARGET_BUSY: {sorted(shared)[0]} held by #{holder.number}")
