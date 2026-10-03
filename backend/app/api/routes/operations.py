"""Operations domain routes: 24x7 agent operation.

Charters (what each agent is for), routines (recurring work it owes), runs
(one per occurrence) and the shared policy. Two background passes, wired in
main.py, keep it moving:

- run_routine_generation_pass turns every due occurrence into an ordinary
  Messages Task addressed to the routine's agent -- Messages remains the only
  executor, so a routine run gets the same deadline, per-agent concurrency
  cap, failure notification and Agent Activity visibility as any task.
- run_routine_sync_pass copies each linked task's outcome back onto its run.

Spec: docs/superpowers/specs/2026-10-02-agent-operations-24x7-design.md.
Cost budgets are stored on the charter but only the run budget is enforced
here; cost enforcement arrives with the self-improvement phase, which is
where per-run cost from ForgeRouter is collected.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.demand import create_demand_and_notify
from app.api.schemas.demand import DemandSubmitIn
from app.api.schemas.operations import (
    AgentOperationsSummary,
    CharterIn,
    CharterOut,
    OperationsOverview,
    PolicyIn,
    PolicyOut,
    RoutineCreate,
    RoutineOut,
    RoutineRunOut,
    RoutineUpdate,
)
from app.core.deps import get_current_admin
from app.core.routine_schedule import (
    local_day_bounds,
    next_occurrences,
    occurrences_between,
    validate_schedule,
)
from app.db.base import get_db
from app.db.models.agent import Agent
from app.db.models.audit import AuditCheck
from app.db.models.demand import AgentDemand
from app.db.models.operations import (
    ROUTINE_RUN_TERMINAL_STATUSES,
    AgentCharter,
    AgentRoutine,
    AgentRoutineRun,
    OperationsPolicy,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/operations", tags=["operations"])

COORDINATOR_SLUG = "athos"
# Runs that never executed don't consume the agent's daily budget.
_NON_BUDGET_STATUSES = ("missed", "skipped_budget")
# At most this many past-due occurrences are recorded as "missed" per pass
# (an hourly routine after a day of downtime), so a long outage can't write
# an unbounded batch in one transaction.
_MAX_MISSED_RECORDED = 50


# ---------------------------------------------------------------- helpers


async def _agent_or_404(db: AsyncSession, agent_id: uuid.UUID) -> Agent:
    agent = await db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent


async def _owned_checks(db: AsyncSession, profile_slug: str | None) -> list[str]:
    if not profile_slug:
        return []
    rows = await db.execute(
        select(AuditCheck.name)
        .where(AuditCheck.agent_profile == profile_slug, AuditCheck.enabled.is_(True))
        .order_by(AuditCheck.name)
    )
    return list(rows.scalars())


async def _charter_out(db: AsyncSession, charter: AgentCharter, agent: Agent) -> CharterOut:
    out = CharterOut.model_validate(charter)
    out.agent_name = agent.name
    out.owned_audit_checks = await _owned_checks(db, agent.profile_slug)
    return out


def _routine_out(routine: AgentRoutine, agent_name: str | None) -> RoutineOut:
    out = RoutineOut.model_validate(routine)
    out.agent_name = agent_name
    if routine.enabled:
        out.next_occurrences = next_occurrences(
            routine.schedule, routine.timezone, datetime.now(timezone.utc), 5
        )
    return out


async def _current_policy(db: AsyncSession) -> OperationsPolicy | None:
    return (
        await db.execute(select(OperationsPolicy).order_by(OperationsPolicy.version.desc()).limit(1))
    ).scalar_one_or_none()


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- (não definido)"


def compose_routine_message(
    routine: AgentRoutine,
    agent: Agent,
    occurrence_at: datetime,
    charter: AgentCharter | None,
    policy: OperationsPolicy | None,
) -> str:
    """The task body an agent receives for one occurrence: what to do, the
    evidence that counts as done, its own charter and the shared policy --
    so every run carries the full context, never just a title."""
    local = occurrence_at.astimezone(ZoneInfo(routine.timezone))
    parts = [
        f"# Rotina: {routine.title}",
        f"Agente: {agent.name} · Ocorrência: {local:%Y-%m-%d %H:%M} ({routine.timezone}) · "
        f"Prazo: {routine.deadline_minutes} min · Tipo: {routine.kind}",
        "",
        "## O que fazer",
        routine.instructions.strip(),
        "",
        "## Evidência esperada",
        (routine.expected_evidence or "Relate o que foi verificado, o que foi feito e o resultado.").strip(),
    ]
    if routine.linked_audit_checks:
        parts += ["", "## Checks de auditoria vinculados", _bullets(routine.linked_audit_checks)]
    if charter is not None:
        parts += [
            "",
            "## Sua carta de funções",
            f"Missão: {charter.mission.strip()}",
            "Responsabilidades:",
            _bullets(charter.responsibilities),
            "Nunca faz:",
            _bullets(charter.never_does),
        ]
    if policy is not None:
        parts += ["", f"## Instruções comuns (política v{policy.version})", policy.content.strip()]
    return "\n".join(parts)


# ---------------------------------------------------------------- passes


async def _runs_counted_today(db: AsyncSession, agent_id: uuid.UUID, tz: str, now: datetime) -> int:
    start, end = local_day_bounds(now, tz)
    return (
        await db.execute(
            select(func.count(AgentRoutineRun.id))
            .join(AgentRoutine, AgentRoutine.id == AgentRoutineRun.routine_id)
            .where(
                AgentRoutine.agent_id == agent_id,
                AgentRoutineRun.occurrence_at >= start,
                AgentRoutineRun.occurrence_at < end,
                AgentRoutineRun.status.notin_(_NON_BUDGET_STATUSES),
            )
        )
    ).scalar_one()


async def _materialize_occurrence(
    db: AsyncSession,
    routine: AgentRoutine,
    occurrence_at: datetime,
    now: datetime,
    coordinator: Agent | None,
) -> AgentRoutineRun:
    """Create the run for the newest due occurrence: a Messages task, unless
    its window already closed (missed) or the agent's budget is spent."""
    run = AgentRoutineRun(routine_id=routine.id, occurrence_at=occurrence_at)
    if now - occurrence_at > timedelta(minutes=routine.deadline_minutes):
        run.status, run.detail, run.finished_at = "missed", "occurrence window closed before generation", now
        return run

    agent = await db.get(Agent, routine.agent_id)
    charter = (
        await db.execute(select(AgentCharter).where(AgentCharter.agent_id == routine.agent_id))
    ).scalar_one_or_none()
    if charter is not None and await _runs_counted_today(db, routine.agent_id, routine.timezone, now) >= charter.daily_run_budget:
        run.status = "skipped_budget"
        run.detail = f"daily run budget of {charter.daily_run_budget} reached"
        run.finished_at = now
        return run

    sender = coordinator or agent
    demand = await create_demand_and_notify(
        db,
        DemandSubmitIn(
            from_agent=sender.profile_slug or sender.name,
            from_agent_id=sender.id,
            target_agent_id=agent.id,
            subject=f"[Rotina] {routine.title}"[:255],
            body=compose_routine_message(routine, agent, occurrence_at, charter, await _current_policy(db)),
            origin_type="task",
            scheduled_at=occurrence_at,
        ),
        commit=False,
        notify=False,
    )
    run.demand_id = demand.id
    run.status = "scheduled"
    return run


async def run_routine_generation_pass(db: AsyncSession, now: datetime | None = None) -> int:
    """Materialize every due occurrence of every enabled routine. Returns the
    number of tasks created. Each routine commits on its own, so one bad
    routine never blocks the rest; the UNIQUE (routine_id, occurrence_at)
    makes a concurrent or repeated pass harmless."""
    now = now or datetime.now(timezone.utc)
    coordinator = (
        await db.execute(select(Agent).where(Agent.profile_slug == COORDINATOR_SLUG))
    ).scalar_one_or_none()
    routine_ids = list(
        (await db.execute(select(AgentRoutine.id).where(AgentRoutine.enabled.is_(True)))).scalars()
    )
    created = 0
    for routine_id in routine_ids:
        routine = await db.get(AgentRoutine, routine_id)
        if routine is None or not routine.enabled:
            continue
        cursor = routine.last_occurrence_at or routine.created_at
        due = occurrences_between(routine.schedule, routine.timezone, cursor, now, limit=_MAX_MISSED_RECORDED + 1)
        if not due:
            continue
        try:
            for past in due[:-1]:
                db.add(AgentRoutineRun(
                    routine_id=routine.id, occurrence_at=past, status="missed",
                    detail="generator was not running at this occurrence", finished_at=now,
                ))
            run = await _materialize_occurrence(db, routine, due[-1], now, coordinator)
            db.add(run)
            routine.last_occurrence_at = due[-1]
            await db.commit()
            created += run.status == "scheduled"
        except IntegrityError:
            # Another pass already materialized it: just advance the cursor.
            await db.rollback()
            routine = await db.get(AgentRoutine, routine_id)
            routine.last_occurrence_at = due[-1]
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Routine %s generation failed", routine_id)
    if created:
        from app.core.dispatch_signal import wake_scheduled_dispatch

        wake_scheduled_dispatch()
    return created


_DISPATCH_TO_RUN = {"dispatched": "running", "running": "running", "completed": "completed", "failed": "failed"}


async def run_routine_sync_pass(db: AsyncSession) -> int:
    """Copy each open run's Messages outcome onto the run. Returns how many
    runs changed."""
    rows = (
        await db.execute(
            select(AgentRoutineRun, AgentDemand)
            .outerjoin(AgentDemand, AgentDemand.id == AgentRoutineRun.demand_id)
            .where(AgentRoutineRun.status.in_(("scheduled", "running")))
        )
    ).all()
    now = datetime.now(timezone.utc)
    changed = 0
    for run, demand in rows:
        if demand is None:
            new_status, detail = "failed", "the routine's message was deleted"
        else:
            new_status = _DISPATCH_TO_RUN.get(demand.dispatch_status or "", "scheduled")
            detail = demand.dispatch_error if new_status == "failed" else run.detail
        if new_status != run.status:
            run.status, run.detail = new_status, detail
            if new_status in ROUTINE_RUN_TERMINAL_STATUSES:
                run.finished_at = now
            changed += 1
    if changed:
        await db.commit()
    return changed


# ---------------------------------------------------------------- charters


@router.get("/charters", response_model=list[CharterOut])
async def list_charters(db: AsyncSession = Depends(get_db)) -> list[CharterOut]:
    rows = (await db.execute(select(AgentCharter, Agent).join(Agent, Agent.id == AgentCharter.agent_id).order_by(Agent.name))).all()
    return [await _charter_out(db, charter, agent) for charter, agent in rows]


@router.get("/charters/{agent_id}", response_model=CharterOut)
async def get_charter(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> CharterOut:
    agent = await _agent_or_404(db, agent_id)
    charter = (await db.execute(select(AgentCharter).where(AgentCharter.agent_id == agent_id))).scalar_one_or_none()
    if charter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Charter not found")
    return await _charter_out(db, charter, agent)


@router.put("/charters/{agent_id}", response_model=CharterOut)
async def upsert_charter(
    agent_id: uuid.UUID,
    payload: CharterIn,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> CharterOut:
    agent = await _agent_or_404(db, agent_id)
    charter = (await db.execute(select(AgentCharter).where(AgentCharter.agent_id == agent_id))).scalar_one_or_none()
    values = payload.model_dump(mode="json")
    values["daily_cost_budget"] = payload.daily_cost_budget
    if charter is None:
        charter = AgentCharter(agent_id=agent_id, **values)
        db.add(charter)
    else:
        for field, value in values.items():
            setattr(charter, field, value)
    await db.commit()
    await db.refresh(charter)
    return await _charter_out(db, charter, agent)


# ---------------------------------------------------------------- routines


@router.get("/routines", response_model=list[RoutineOut])
async def list_routines(
    agent_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db)
) -> list[RoutineOut]:
    query = select(AgentRoutine, Agent.name).join(Agent, Agent.id == AgentRoutine.agent_id)
    if agent_id is not None:
        query = query.where(AgentRoutine.agent_id == agent_id)
    rows = (await db.execute(query.order_by(Agent.name, AgentRoutine.title))).all()
    return [_routine_out(routine, name) for routine, name in rows]


@router.post("/routines", response_model=RoutineOut, status_code=status.HTTP_201_CREATED)
async def create_routine(
    payload: RoutineCreate, db: AsyncSession = Depends(get_db), _admin=Depends(get_current_admin)
) -> RoutineOut:
    agent = await _agent_or_404(db, payload.agent_id)
    routine = AgentRoutine(**payload.model_dump())
    db.add(routine)
    await db.commit()
    await db.refresh(routine)
    return _routine_out(routine, agent.name)


async def _routine_or_404(db: AsyncSession, routine_id: uuid.UUID) -> AgentRoutine:
    routine = await db.get(AgentRoutine, routine_id)
    if routine is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Routine not found")
    return routine


@router.patch("/routines/{routine_id}", response_model=RoutineOut)
async def update_routine(
    routine_id: uuid.UUID,
    payload: RoutineUpdate,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> RoutineOut:
    routine = await _routine_or_404(db, routine_id)
    changes = payload.model_dump(exclude_unset=True)
    schedule = changes.get("schedule", routine.schedule)
    tz = changes.get("timezone", routine.timezone)
    try:
        validate_schedule(schedule, tz)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from None
    was_enabled = routine.enabled
    for field, value in changes.items():
        setattr(routine, field, value)
    if routine.enabled and (not was_enabled or "schedule" in changes or "timezone" in changes):
        # Re-arm from now: re-enabling or rescheduling must not replay (or
        # record as missed) every occurrence of the old schedule.
        routine.last_occurrence_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(routine)
    agent = await db.get(Agent, routine.agent_id)
    return _routine_out(routine, agent.name if agent else None)


@router.delete("/routines/{routine_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_routine(
    routine_id: uuid.UUID, db: AsyncSession = Depends(get_db), _admin=Depends(get_current_admin)
) -> None:
    routine = await _routine_or_404(db, routine_id)
    await db.delete(routine)
    await db.commit()


@router.post("/routines/{routine_id}:run-now", response_model=RoutineRunOut, status_code=status.HTTP_201_CREATED)
async def run_routine_now(
    routine_id: uuid.UUID, db: AsyncSession = Depends(get_db), _admin=Depends(get_current_admin)
) -> RoutineRunOut:
    """Extra occurrence now, outside the schedule (does not move the cursor)."""
    routine = await _routine_or_404(db, routine_id)
    now = datetime.now(timezone.utc)
    coordinator = (await db.execute(select(Agent).where(Agent.profile_slug == COORDINATOR_SLUG))).scalar_one_or_none()
    run = await _materialize_occurrence(db, routine, now, now, coordinator)
    db.add(run)
    await db.commit()
    await db.refresh(run)
    if run.status == "scheduled":
        from app.core.dispatch_signal import wake_scheduled_dispatch

        wake_scheduled_dispatch()
    agent = await db.get(Agent, routine.agent_id)
    return RoutineRunOut.model_validate(run).model_copy(
        update={"routine_title": routine.title, "agent_id": routine.agent_id, "agent_name": agent.name if agent else None}
    )


# ---------------------------------------------------------------- runs


@router.get("/runs", response_model=list[RoutineRunOut])
async def list_runs(
    agent_id: uuid.UUID | None = None,
    routine_id: uuid.UUID | None = None,
    run_status: str | None = Query(default=None, alias="status"),
    since: datetime | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> list[RoutineRunOut]:
    query = (
        select(AgentRoutineRun, AgentRoutine, Agent.name, AgentDemand.number)
        .join(AgentRoutine, AgentRoutine.id == AgentRoutineRun.routine_id)
        .join(Agent, Agent.id == AgentRoutine.agent_id)
        .outerjoin(AgentDemand, AgentDemand.id == AgentRoutineRun.demand_id)
    )
    if agent_id is not None:
        query = query.where(AgentRoutine.agent_id == agent_id)
    if routine_id is not None:
        query = query.where(AgentRoutineRun.routine_id == routine_id)
    if run_status is not None:
        query = query.where(AgentRoutineRun.status == run_status)
    if since is not None:
        query = query.where(AgentRoutineRun.occurrence_at >= since)
    rows = (await db.execute(query.order_by(AgentRoutineRun.occurrence_at.desc()).limit(limit))).all()
    now = datetime.now(timezone.utc)
    return [
        RoutineRunOut.model_validate(run).model_copy(update={
            "routine_title": routine.title,
            "agent_id": routine.agent_id,
            "agent_name": agent_name,
            "demand_number": number,
            "overdue": run.status == "scheduled"
            and now - run.occurrence_at > timedelta(minutes=routine.deadline_minutes),
        })
        for run, routine, agent_name, number in rows
    ]


# ---------------------------------------------------------------- policy


@router.get("/policy", response_model=PolicyOut | None)
async def get_policy(db: AsyncSession = Depends(get_db)) -> PolicyOut | None:
    policy = await _current_policy(db)
    return PolicyOut.model_validate(policy) if policy else None


@router.get("/policy/versions", response_model=list[PolicyOut])
async def list_policy_versions(db: AsyncSession = Depends(get_db)) -> list[PolicyOut]:
    rows = await db.execute(select(OperationsPolicy).order_by(OperationsPolicy.version.desc()))
    return [PolicyOut.model_validate(p) for p in rows.scalars()]


@router.post("/policy", response_model=PolicyOut, status_code=status.HTTP_201_CREATED)
async def publish_policy(
    payload: PolicyIn, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)
) -> PolicyOut:
    """Append a new version (never edits in place, so any earlier text can be
    restored by publishing it again)."""
    current = await _current_policy(db)
    policy = OperationsPolicy(
        version=(current.version + 1) if current else 1,
        content=payload.content,
        change_reason=payload.change_reason,
        author=getattr(admin, "username", None) or "admin",
    )
    db.add(policy)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Policy changed concurrently, retry") from None
    await db.refresh(policy)
    return PolicyOut.model_validate(policy)


# ---------------------------------------------------------------- overview


@router.get("/overview", response_model=OperationsOverview)
async def operations_overview(db: AsyncSession = Depends(get_db)) -> OperationsOverview:
    """One row per active agent: charter present, routines, today's runs by
    status and budget consumption -- the screen's "Agentes" tab."""
    now = datetime.now(timezone.utc)
    start, end = local_day_bounds(now, "America/Sao_Paulo")
    agents = list((await db.execute(select(Agent).where(Agent.is_active.is_(True)).order_by(Agent.name))).scalars())
    charters = {c.agent_id: c for c in (await db.execute(select(AgentCharter))).scalars()}
    routine_counts: dict[uuid.UUID, tuple[int, int]] = {}
    for agent_id, enabled, count in (
        await db.execute(select(AgentRoutine.agent_id, AgentRoutine.enabled, func.count()).group_by(AgentRoutine.agent_id, AgentRoutine.enabled))
    ).all():
        total, on = routine_counts.get(agent_id, (0, 0))
        routine_counts[agent_id] = (total + count, on + (count if enabled else 0))
    today: dict[uuid.UUID, dict[str, int]] = {}
    for agent_id, run_status, count in (
        await db.execute(
            select(AgentRoutine.agent_id, AgentRoutineRun.status, func.count())
            .join(AgentRoutine, AgentRoutine.id == AgentRoutineRun.routine_id)
            .where(AgentRoutineRun.occurrence_at >= start, AgentRoutineRun.occurrence_at < end)
            .group_by(AgentRoutine.agent_id, AgentRoutineRun.status)
        )
    ).all():
        today.setdefault(agent_id, {})[run_status] = count
    policy = await _current_policy(db)
    summaries = []
    for agent in agents:
        total, on = routine_counts.get(agent.id, (0, 0))
        counts = today.get(agent.id, {})
        charter = charters.get(agent.id)
        summaries.append(AgentOperationsSummary(
            agent_id=agent.id,
            agent_name=agent.name,
            profile_slug=agent.profile_slug,
            runtime_type=agent.runtime_type,
            has_charter=charter is not None,
            routines_enabled=on,
            routines_total=total,
            today=counts,
            daily_run_budget=charter.daily_run_budget if charter else None,
            runs_counted_today=sum(v for k, v in counts.items() if k not in _NON_BUDGET_STATUSES),
        ))
    return OperationsOverview(agents=summaries, policy_version=policy.version if policy else None)
