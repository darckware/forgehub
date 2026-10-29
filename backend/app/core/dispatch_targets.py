"""Target serialization for Messages runs (Plano Integrado M0.6b,
docs/architecture/MCP_MISSION_TOOLS_SPEC.md §4.3, decision D-M0-2).

A task declares what its run holds exclusively in `task_execution_targets`.
`reserve_dispatch` refuses a run (`TARGET_BUSY`, the item stays queued) while
another in-flight, reserved or uncertain run holds an equal target:
- `publish:production:*` for every task in Messages (the 28/10 incident was
  outside any mission);
- `worktree` and `branch` only for mission tasks, which also hold their
  `working_path` as an implicit worktree target.
Work packages (`POST /work-packages/{id}:dispatch`) take the same lock and the
same check before creating their TaskExecution, and an active governed
execution holds its task's targets (its worktree being the project checkout)
just as an in-flight message does.
Must run under DISPATCH_ADMISSION_LOCK.
"""
from __future__ import annotations

import os

from sqlalchemy import and_, or_, select

from app.core.demand_workflow import WorkflowBlocked
from app.db.models.demand import AgentDemand
from app.db.models.execution import ExecutionWave, ExecutionWorkPackage
from app.db.models.project import Project
from app.db.models.task import ProjectTask, TaskExecution, TaskExecutionTarget

DISPATCH_ADMISSION_LOCK = 0x464844495350
# A governed (work-package) execution in one of these states holds its targets;
# routes/execution.py imports this tuple.
ACTIVE_EXECUTION_STATES = ("pending", "running", "recovering", "reconciling")


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


async def task_targets(db, task: ProjectTask, working_path: str | None) -> set[str]:
    """`<kind>:<key>` targets a run of `task` started in `working_path` holds."""
    from app.core.task_baseline_guard import task_missions

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
    if mission_task and (working_path or "").strip():
        targets.add(f"worktree:{normalize_target_key('worktree', working_path)}")
    return targets


async def demand_targets(db, demand: AgentDemand) -> set[str]:
    """`<kind>:<key>` targets the run of `demand` holds."""
    if demand.origin_type != "task" or demand.origin_id is None:
        return set()
    task = await db.get(ProjectTask, demand.origin_id)
    if task is None:
        return set()
    return await task_targets(db, task, demand.working_path)


def _holding_clause():
    # In flight, reserved (run id before the bridge call) or uncertain
    # (requires_reconciliation): each one may still be touching the target.
    return or_(
        AgentDemand.dispatch_status.in_(("dispatched", "running")),
        and_(AgentDemand.dispatch_status.is_(None), AgentDemand.agent_run_id.is_not(None)),
        and_(
            AgentDemand.dispatch_status == "failed", AgentDemand.agent_run_id.is_not(None),
            or_(
                AgentDemand.dispatch_error.is_(None), AgentDemand.dispatch_error == "",
                AgentDemand.dispatch_error.ilike("%uncertain%"),
            ),
        ),
    )


async def _first_holder(db, wanted: set[str], demand_id=None) -> str | None:
    if not wanted:
        return None
    holders = (await db.execute(
        select(AgentDemand)
        # demand_id None (a work package) makes this `id IS NOT NULL`: every holder.
        .where(AgentDemand.id != demand_id, AgentDemand.origin_type == "task", _holding_clause())
        .order_by(AgentDemand.created_at)
    )).scalars().all()
    for holder in holders:
        shared = wanted & await demand_targets(db, holder)
        if shared:
            return f"{sorted(shared)[0]} held by #{holder.number}"
    executions = (await db.execute(
        select(TaskExecution, Project.working_directory_path)
        .join(ExecutionWorkPackage, ExecutionWorkPackage.id == TaskExecution.work_package_id)
        .join(ExecutionWave, ExecutionWave.id == ExecutionWorkPackage.execution_wave_id)
        .join(Project, Project.id == ExecutionWave.project_id)
        .where(TaskExecution.status.in_(ACTIVE_EXECUTION_STATES))
        .order_by(TaskExecution.created_at)
    )).all()
    for execution, working_path in executions:
        task = await db.get(ProjectTask, execution.task_id)
        shared = wanted & await task_targets(db, task, working_path) if task is not None else set()
        if shared:
            return f"{sorted(shared)[0]} held by execution {execution.id}"
    return None


async def assert_targets_free(db, demand: AgentDemand) -> None:
    busy = await _first_holder(db, await demand_targets(db, demand), demand_id=demand.id)
    if busy:
        raise WorkflowBlocked(f"TARGET_BUSY: {busy}")


async def assert_task_targets_free(db, task: ProjectTask, working_path: str | None) -> None:
    """The work-package counterpart of assert_targets_free."""
    busy = await _first_holder(db, await task_targets(db, task, working_path))
    if busy:
        raise WorkflowBlocked(f"TARGET_BUSY: {busy}")
