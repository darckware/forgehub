"""Routine occurrences for the Agent Activity timeline and alerts (Plano Integrado A.2, 2026-11-03).

A routine (``agent_routines``) never runs anything itself: each due occurrence becomes a
Messages Task and an ``agent_routine_runs`` row (``api/routes/operations.py``'s generator).
This module only *reads* both, plus the routine's own cron, to answer "what did this
agent's routines do, and what is next?" on the timeline that already exists:

- past occurrences come from ``agent_routine_runs`` (done / failed / missed / skipped /
  running), refined by the linked Messages dispatch when the sync pass is behind;
- an occurrence the schedule says was owed but that has **no run at all** is computed: it
  is ``missed`` once its deadline passed (the generator was down, or capped), ``pending``
  while still inside it;
- the next 24 h come from the cron, evaluated in the routine's own timezone
  (``core/routine_schedule.py``), marked ``scheduled``.

One entry per (routine, instant): a recorded run always wins over the computed one.
Disabled routines keep their recorded history but owe nothing (no computed miss, no
future). Nothing here writes: rolling the UI/API back removes no history, since the
history is the runs table this module only reads.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.agent_activity import ActivityIncidentOut, ActivityRecordLinkOut, TimelineRoutineOccurrenceOut
from app.core.routine_schedule import occurrences_between
from app.db.models.demand import AgentDemand
from app.db.models.operations import AgentRoutine, AgentRoutineRun

UPCOMING_WINDOW = timedelta(hours=24)
# An hourly routine over a 24 h window plus the next 24 h is 48; the 15-minute floor
# (routine_schedule.MIN_INTERVAL_SECONDS) makes 96 per day the most any routine can owe.
_MAX_PER_ROUTINE = 200

_RUN_OUTCOME = {
    "completed": "done",
    "failed": "failed",
    "missed": "missed",
    "skipped_budget": "skipped",
    "running": "running",
}
_DISPATCH_OUTCOME = {"dispatched": "running", "running": "running", "completed": "done", "failed": "failed"}


def _utc(moment: datetime) -> datetime:
    return moment.astimezone(timezone.utc) if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _run_outcome(run: Any, demand: Any, deadline_at: datetime, now: datetime) -> tuple[str, str | None]:
    outcome = _RUN_OUTCOME.get(run.status)
    if outcome is not None and run.status != "running":
        return outcome, run.detail
    # Open runs: their Messages task exists. The sync pass copies the dispatch
    # outcome every few minutes, so read the dispatch itself before calling it a miss.
    dispatched = _DISPATCH_OUTCOME.get(getattr(demand, "dispatch_status", None) or "")
    if dispatched is not None:
        return dispatched, (getattr(demand, "dispatch_error", None) or run.detail) if dispatched == "failed" else run.detail
    if outcome == "running":
        return outcome, run.detail
    if now > deadline_at:
        return "missed", run.detail or "not started before its deadline"
    return "pending", run.detail


def classify_occurrences(
    routines: Iterable[Any],
    runs: Iterable[tuple[Any, Any]],
    *,
    start: datetime,
    end: datetime,
    now: datetime,
    horizon: datetime,
) -> list[TimelineRoutineOccurrenceOut]:
    """Pure: occurrences in ``[start, end]`` (past/due) and ``(now, horizon]`` (scheduled).

    ``runs``: (AgentRoutineRun, its AgentDemand or None) pairs. Sorted by instant.
    """
    routines = list(routines)
    by_id = {routine.id: routine for routine in routines}
    found: dict[tuple[uuid.UUID, datetime], TimelineRoutineOccurrenceOut] = {}

    def entry(routine: Any, at: datetime, outcome: str, **extra: Any) -> TimelineRoutineOccurrenceOut:
        return TimelineRoutineOccurrenceOut(
            key=f"routine:{routine.id}:{at.isoformat()}",
            routine_id=routine.id,
            agent_id=routine.agent_id,
            title=routine.title,
            routine_kind=routine.kind,
            timezone=routine.timezone,
            occurrence_at=at,
            deadline_at=at + timedelta(minutes=routine.deadline_minutes),
            outcome=outcome,
            **extra,
        )

    for run, demand in runs:
        routine = by_id.get(run.routine_id)
        if routine is None:
            continue
        at = _utc(run.occurrence_at)
        if not (start <= at <= end or now < at <= horizon) or (routine.id, at) in found:
            continue
        outcome, detail = _run_outcome(run, demand, at + timedelta(minutes=routine.deadline_minutes), now)
        found[(routine.id, at)] = entry(
            routine, at, outcome,
            recorded=True, run_id=run.id, detail=detail, finished_at=run.finished_at,
            duration_ms=run.duration_ms,
            message_number=getattr(demand, "number", None),
            canonical_path=f"/demands?message={run.demand_id}" if run.demand_id else "/operations",
        )

    for routine in routines:
        if not routine.enabled:
            continue  # a disabled routine owes nothing; its recorded runs stay above
        created = _utc(routine.created_at) if routine.created_at else start
        past_from = max(start, created)
        past_until = min(end, now)
        if past_from <= past_until:
            for at in occurrences_between(
                routine.schedule, routine.timezone, past_from - timedelta(microseconds=1), past_until,
                limit=_MAX_PER_ROUTINE,
            ):
                if (routine.id, at) in found:
                    continue
                deadline = at + timedelta(minutes=routine.deadline_minutes)
                missed = now > deadline
                found[(routine.id, at)] = entry(
                    routine, at, "missed" if missed else "pending",
                    detail="no run was recorded for this occurrence" if missed else None,
                    canonical_path="/operations",
                )
        if horizon > now:
            for at in occurrences_between(routine.schedule, routine.timezone, now, horizon, limit=_MAX_PER_ROUTINE):
                if (routine.id, at) not in found:
                    found[(routine.id, at)] = entry(routine, at, "scheduled", canonical_path="/operations")

    return sorted(found.values(), key=lambda item: (item.occurrence_at, str(item.routine_id)))


async def collect_routine_occurrences(
    db: AsyncSession,
    agent_ids: Iterable[uuid.UUID],
    *,
    start: datetime,
    end: datetime,
    now: datetime,
    horizon: datetime | None = None,
) -> list[TimelineRoutineOccurrenceOut]:
    """Read the routines of ``agent_ids`` and their runs, then classify (see module doc)."""
    ids = list(agent_ids)
    if not ids:
        return []
    horizon = horizon if horizon is not None else now + UPCOMING_WINDOW
    routines = list(
        (await db.execute(select(AgentRoutine).where(AgentRoutine.agent_id.in_(ids)))).scalars()
    )
    if not routines:
        return []
    upper = max(end, horizon)
    runs = (
        await db.execute(
            select(AgentRoutineRun, AgentDemand)
            .outerjoin(AgentDemand, AgentDemand.id == AgentRoutineRun.demand_id)
            .where(
                AgentRoutineRun.routine_id.in_([routine.id for routine in routines]),
                AgentRoutineRun.occurrence_at >= start,
                AgentRoutineRun.occurrence_at <= upper,
            )
        )
    ).all()
    return classify_occurrences(
        routines, [(run, demand) for run, demand in runs], start=start, end=end, now=now, horizon=horizon
    )


def routine_missed_incidents(
    occurrences: Iterable[TimelineRoutineOccurrenceOut], agents_by_id: dict[uuid.UUID, Any], *, now: datetime
) -> list[ActivityIncidentOut]:
    """One incident per routine and exception kind, keyed by its newest exception.

    A routine that misses every hour while the generator is down is one alert that grows,
    not one per hour; a new miss after a good run is a new key. It is about the routine
    only: an agent's Telegram channel (installed or not) plays no part in it.
    """
    missed: dict[tuple[uuid.UUID, str], list[TimelineRoutineOccurrenceOut]] = {}
    for item in occurrences:
        # A budget cap is an intentional scheduling decision, not an execution
        # failure. It becomes an unfulfilled occurrence only after its deadline.
        if item.outcome in {"missed", "failed"} or (item.outcome == "skipped" and now > item.deadline_at):
            missed.setdefault((item.routine_id, item.outcome), []).append(item)
    incidents = []
    for (routine_id, outcome), items in missed.items():
        items.sort(key=lambda item: item.occurrence_at)
        latest = items[-1]
        agent = agents_by_id.get(latest.agent_id)
        name = agent.name if agent is not None else "?"
        count = len(items)
        kind = {"missed": "routine_missed", "failed": "routine_failed", "skipped": "routine_skipped_budget"}[outcome]
        description = {"missed": "missed", "failed": "failed", "skipped": "was skipped for budget"}[outcome]
        explanation = {
            "missed": "its deadline passed without a run",
            "failed": "its execution failed",
            "skipped": "its budget prevented execution before its deadline",
        }[outcome]
        incidents.append(ActivityIncidentOut(
            key=f"{kind}:{routine_id}:{latest.occurrence_at.isoformat()}",
            kind=kind,
            severity="error" if count >= 3 or outcome == "failed" else "warning",
            title=(
                f"{name}: routine {latest.title} {description}"
                if count == 1 else f"{name}: routine {latest.title} {description} {count} times"
            ),
            occurred_at=latest.occurrence_at,
            source_type="agent_routine",
            source_id=routine_id,
            affected_agent_id=latest.agent_id,
            error_code=kind,
            summary=(
                f"Due at {latest.occurrence_at.isoformat()} ({latest.timezone}); {explanation}. "
                f"{latest.detail or ''} Later successful occurrences do not establish "
                "service acceptance or remediation of this occurrence."
            ).strip(),
            recommended_action="open_agent",
            last_observed_at=now,
            runtime_type=getattr(agent, "runtime_type", None),
            current_owner_agent_id=latest.agent_id,
            canonical_path=latest.canonical_path,
            related_records=[ActivityRecordLinkOut(
                source_type="agent_routine_run", source_id=item.run_id,
                canonical_path=item.canonical_path or "/operations",
                label=f"{item.title}: {item.occurrence_at.isoformat()}",
            ) for item in items if item.run_id is not None],
        ))
    return incidents
