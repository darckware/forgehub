"""The orchestrator decision cycle of a mission (Plano Integrado M0.8).

Contract: docs/architecture/MISSION_ORCHESTRATOR_CYCLE_SPEC.md. The cycle is
the orchestrator *choosing* among actions that already exist as guarded
routes; this module adds no executor and no bypass:

- ``sync_mission_routine``: one ``coordination`` AgentRoutine per mission in a
  cycle state, toggled with the mission, never deleted (§2.1). Created only
  while ``MISSION_CYCLE_ENABLED`` is on (the M0.8 switch; off = no cycle).
- ``request_mission_cycle``: run one cycle now, debounced to one open cycle
  per mission (``cycle_rerun_requested``) (§2.2).
- ``run_mission_cycle_pass``: what the Operação 24x7 loop calls -- event
  detection since the mission's cursor (task/execution/review/dispatch
  outcomes, the 80 % deadline, an executor's availability returning, an
  answered question), the pending rerun and the watchdog (§2.2, §3.4 item 4).
  Events are detected by reading the database, not by hooks in each writer,
  so a guarded transaction never carries cycle work.
- ``build_cycle``: the board and the deterministic proposals (§2.3, §3):
  same database state, same proposals in the same order.
- ``write_context_version``: the mission's versioned context pack (§3.6).
- locks (§5) and the inter-mission priority of a queued demand (§6.1).

Decisions themselves are executed and recorded by ``api/routes/mission_cycle.py``.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_availability import RESCHEDULE_MARGIN, classify_infra_failure, unavailable_agents
from app.core.config import settings
from app.db.models.agent import Agent
from app.db.models.demand import DISPATCH_MAX_ATTEMPTS, AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.notification import Notification
from app.db.models.mission import MissionDecision, ProjectMission
from app.db.models.mission_cycle import MissionContextVersion, MissionCycleLock
from app.db.models.operations import AgentQuestion, AgentRoutine, AgentRoutineRun
from app.db.models.orchestration import ProjectAgentMembership, TaskExecutionReview
from app.db.models.task import ProjectTask, TaskAssignment, TaskExecution

logger = logging.getLogger(__name__)

# The mission states a cycle runs in: planning conducts P1-P8 (§3.5), the
# others execute (§3.4). Paused/completed/cancelled disable the routine.
CYCLE_STATES = ("planning", "active", "verifying")
WATCHED_STATES = CYCLE_STATES
CYCLE_SCHEDULE = "*/30 * * * *"
CYCLE_DEADLINE_MINUTES = 20
MISSION_CYCLE_MAX_GAP = timedelta(minutes=30)
REASSIGN_UNAVAILABLE_AFTER = timedelta(hours=2)
DEFAULT_PRIORITY = 100

# §3, column N0: what the orchestrator may decide alone in Onda 1. Anything
# else (approve a plan/CR, accept/cancel, publish to production, raise the
# retry budget or autonomy, grant a delegation) is never a cycle action.
N0_ACTIONS = ("dispatch", "schedule", "reassign", "request_review", "return", "reprocess",
              "integrate", "reverify", "ask_marcelo", "pause", "defer")
# Proposal-only kinds: information for the orchestrator, no tool of their own.
INFO_ACTIONS = ("wait", "check_progress", "apply_default", "advance_planning", "propose_skill")
_ACTION_ORDER = {a: i for i, a in enumerate(
    ("return", "integrate", "reverify", "request_review", "reprocess", "reassign", "schedule", "dispatch",
     "check_progress", "ask_marcelo", "apply_default", "advance_planning", "propose_skill", "defer", "wait",
     "pause"))}
TERMINAL_TASK = ("done", "deployed", "cancelled")
TERMINAL_DISPATCH = ("completed", "failed")
INTEGRATION_REF_PREFIX = "integrate:"
_CONTEXT_MISSING = re.compile(r"^\s*CONTEXT_MISSING:\s*(.{1,300})$", re.MULTILINE)
_CONFLICT_FILE = re.compile(r"^\s*(?:CONFLICT \([^)]*\): (?:Merge conflict in )?|both modified:\s+)(\S+)",
                            re.MULTILINE)

ROUTINE_INSTRUCTIONS = (
    "Conduza um ciclo de decisão desta missão. Chame get_mission_cycle(project_id) e decida somente pelas "
    "ferramentas de missão (mission_decide e as ferramentas de tarefa), sempre com cycle_id, motivo e "
    "idempotency_key e expected_context_version da versão lida (0 se não houver versão). Preserve esses "
    "valores ao repetir a mesma solicitação. As propostas são fatos calculados pelo backend; os guards revalidam tudo. Você "
    "nunca aprova plano ou baseline, nunca decide item sinalizado, nunca aceita, cancela ou publica em "
    "produção. Pergunte ao Marcelo (ask_marcelo) só quando houver dúvida de verdade. Termine com a linha "
    "STATUS."
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def cycle_error(status_code: int, code: str, message: str, **context: Any) -> HTTPException:
    return HTTPException(status_code, detail={"code": code, "message": message, **context})


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Locks (§5)
# ---------------------------------------------------------------------------
def _open_lock_clause(now: datetime):
    return and_(MissionCycleLock.released_at.is_(None),
                or_(MissionCycleLock.locked_until.is_(None), MissionCycleLock.locked_until > now))


async def open_locks(db: AsyncSession, project_id: uuid.UUID, now: datetime | None = None) -> list[MissionCycleLock]:
    return list((await db.execute(select(MissionCycleLock).where(
        MissionCycleLock.mission_project_id == project_id, _open_lock_clause(now or utcnow()),
    ).order_by(MissionCycleLock.created_at))).scalars())


async def assert_cycle_unlocked(
    db: AsyncSession, mission: ProjectMission, principal, task_id: uuid.UUID | None = None,
) -> None:
    """§5: every mission tool from the orchestrator answers 409 while Marcelo
    holds a lock on the cycle (or on that task); his own actions still work."""
    if principal is None or principal.principal_type != "agent" or principal.principal_id != mission.orchestrator_agent_id:
        return
    for lock in await open_locks(db, mission.project_id):
        if lock.task_id is None:
            raise cycle_error(409, "CYCLE_LOCKED", "Marcelo locked this mission's cycle", lock_id=str(lock.id),
                              reason=lock.reason)
        if task_id is not None and lock.task_id == task_id:
            raise cycle_error(409, "TASK_CYCLE_LOCKED", "Marcelo locked this task for the cycle",
                              lock_id=str(lock.id), task_id=str(task_id), reason=lock.reason)


# ---------------------------------------------------------------------------
# Priority between missions (§6.1)
# ---------------------------------------------------------------------------
async def effective_priorities(db: AsyncSession, demands: list[AgentDemand]) -> dict[uuid.UUID, int]:
    """A queued demand of a mission task gets the highest priority (lowest
    number) of the non-terminal missions it serves; everything else is
    absent (the caller's default, 100)."""
    from app.core.task_baseline_guard import task_missions
    from app.db.models.mission import MISSION_TERMINAL_STATES

    by_task: dict[uuid.UUID, int | None] = {}
    out: dict[uuid.UUID, int] = {}
    for demand in demands:
        if demand.origin_type != "task" or demand.origin_id is None:
            continue
        if demand.origin_id not in by_task:
            task = await db.get(ProjectTask, demand.origin_id)
            missions = [m for m in await task_missions(db, task) if m.state not in MISSION_TERMINAL_STATES] if task else []
            by_task[demand.origin_id] = min((m.priority for m in missions), default=None)
        priority = by_task[demand.origin_id]
        if priority is not None:
            out[demand.id] = priority
    return out


# ---------------------------------------------------------------------------
# Routine (§2.1) and triggers (§2.2)
# ---------------------------------------------------------------------------
async def mission_routine(db: AsyncSession, project_id: uuid.UUID) -> AgentRoutine | None:
    return (await db.execute(select(AgentRoutine).where(AgentRoutine.mission_project_id == project_id)
                             .order_by(AgentRoutine.created_at).limit(1))).scalar_one_or_none()


async def sync_mission_routine(db: AsyncSession, project, mission: ProjectMission,
                               now: datetime | None = None) -> AgentRoutine | None:
    """Create (switch on) or toggle the mission's coordination routine for its
    new state. Never deletes: the runs keep the history. Caller commits."""
    now = now or utcnow()
    routine = await mission_routine(db, mission.project_id)
    wanted = mission.state in CYCLE_STATES and settings.MISSION_CYCLE_ENABLED
    if routine is None:
        if not wanted:
            return None
        routine = AgentRoutine(
            agent_id=mission.orchestrator_agent_id, mission_project_id=mission.project_id,
            title=f"Ciclo da missão {project.name}"[:200], instructions=ROUTINE_INSTRUCTIONS,
            schedule=CYCLE_SCHEDULE, kind="coordination", deadline_minutes=CYCLE_DEADLINE_MINUTES,
            expected_evidence="As decisões registradas na linha do tempo da missão (mission_decisions).",
            enabled=True, last_occurrence_at=now,
        )
        db.add(routine)
        await db.flush()
        return routine
    if routine.enabled != wanted:
        routine.enabled = wanted
        if wanted:
            # Re-enabled: start from now, never back-fill the paused window.
            routine.last_occurrence_at = now
    return routine


async def open_cycle_run(db: AsyncSession, routine: AgentRoutine) -> AgentRoutineRun | None:
    return (await db.execute(select(AgentRoutineRun).where(
        AgentRoutineRun.routine_id == routine.id, AgentRoutineRun.status.in_(("scheduled", "running")),
    ).order_by(AgentRoutineRun.occurrence_at.desc()).limit(1))).scalar_one_or_none()


async def _cycle_locked(db: AsyncSession, project_id: uuid.UUID, now: datetime) -> bool:
    return any(lock.task_id is None for lock in await open_locks(db, project_id, now))


async def request_mission_cycle(
    db: AsyncSession, project_id: uuid.UUID, reason: str, source_ref: str | None = None,
    now: datetime | None = None, *, commit: bool = True,
) -> str:
    """Run one cycle now (the run-now path). Returns `started`,
    `rerun_requested` (a cycle is open: exactly one more after it) or
    `dropped` (mission not in a cycle state, cycle locked, or no routine --
    recorded, never queued). With commit=False the caller owns commit and wake."""
    from app.api.routes.operations import COORDINATOR_SLUG, _materialize_occurrence
    from app.core.dispatch_signal import wake_scheduled_dispatch

    now = now or utcnow()
    mission = await db.scalar(select(ProjectMission).where(ProjectMission.project_id == project_id)
                              .with_for_update().execution_options(populate_existing=True))
    routine = await mission_routine(db, project_id) if mission is not None else None
    if mission is None or mission.state not in CYCLE_STATES or routine is None or not routine.enabled \
            or await _cycle_locked(db, project_id, now):
        if mission is not None:
            db.add(AuditEvent(entity_type="mission", entity_id=project_id, event_type="mission_cycle_event_dropped",
                              actor="forgehub", payload={"reason": reason, "source_ref": source_ref,
                                                          "state": mission.state}))
            if commit:
                await db.commit()
        return "dropped"
    if await open_cycle_run(db, routine) is not None:
        mission.cycle_rerun_requested = True
        if commit:
            await db.commit()
        return "rerun_requested"
    coordinator = (await db.execute(select(Agent).where(Agent.profile_slug == COORDINATOR_SLUG))).scalar_one_or_none()
    run = await _materialize_occurrence(db, routine, now, now, coordinator)
    run.detail = f"cycle requested: {reason}"[:1000]
    db.add(run)
    mission.cycle_rerun_requested = False
    if commit:
        await db.commit()
        wake_scheduled_dispatch()
    return "started"


async def _mission_task_ids(db: AsyncSession, project_id: uuid.UUID) -> list[uuid.UUID]:
    from app.core.mission_plan import mission_scope_tasks

    return list((await mission_scope_tasks(db, project_id)).keys())


async def detect_events(db: AsyncSession, mission: ProjectMission, since: datetime, now: datetime,
                        routine: AgentRoutine | None) -> list[str]:
    """Events since the cursor that should trigger a cycle (§2.2 table)."""
    task_ids = await _mission_task_ids(db, mission.project_id)
    events: list[str] = []
    if task_ids:
        demand_query = select(AgentDemand.number, AgentDemand.dispatch_status).where(
            AgentDemand.origin_type == "task", AgentDemand.origin_id.in_(task_ids),
            AgentDemand.dispatch_status.in_(TERMINAL_DISPATCH), AgentDemand.updated_at > since,
            AgentDemand.updated_at <= now)
        events += [f"dispatch_{state}:#{number}" for number, state in (await db.execute(demand_query)).all()]
        events += [f"execution_{state}:{eid}" for eid, state in (await db.execute(select(
            TaskExecution.id, TaskExecution.status).where(
            TaskExecution.task_id.in_(task_ids), TaskExecution.status.in_(("reported", "verified", "failed")),
            TaskExecution.updated_at > since, TaskExecution.updated_at <= now))).all()]
        events += [f"review_{state}:{rid}" for rid, state in (await db.execute(select(
            TaskExecutionReview.id, TaskExecutionReview.status)
            .join(TaskExecution, TaskExecution.id == TaskExecutionReview.execution_id).where(
            TaskExecution.task_id.in_(task_ids),
            TaskExecutionReview.status.in_(("approved", "changes_requested", "rejected", "failed")),
            TaskExecutionReview.updated_at > since, TaskExecutionReview.updated_at <= now))).all()]
        events += [f"task_{state}:#{number}" for number, state in (await db.execute(select(
            ProjectTask.number, ProjectTask.status).where(
            ProjectTask.id.in_(task_ids), ProjectTask.status.in_(("done", "deployed", "blocked", "cancelled")),
            ProjectTask.updated_at > since, ProjectTask.updated_at <= now))).all()]
        # A run passing 80 % of its deadline (§3.2).
        running = (await db.execute(select(AgentDemand).where(
            AgentDemand.origin_type == "task", AgentDemand.origin_id.in_(task_ids),
            AgentDemand.dispatch_status.in_(("dispatched", "running")),
            AgentDemand.dispatched_at.is_not(None), AgentDemand.dispatch_deadline_at.is_not(None)))).scalars()
        for demand in running:
            mark = demand.dispatched_at + (demand.dispatch_deadline_at - demand.dispatched_at) * 0.8
            if since < mark <= now:
                events.append(f"deadline_80:#{demand.number}")
        # An executor's availability returning (§3.3).
        assignees = set((await db.execute(select(TaskAssignment.agent_id).where(
            TaskAssignment.task_id.in_(task_ids), TaskAssignment.status == "active"))).scalars())
        if assignees:
            from app.db.models.mission_cycle import AgentAvailability

            events += [f"agent_available:{aid}" for aid in (await db.execute(select(AgentAvailability.agent_id).where(
                AgentAvailability.agent_id.in_(assignees), AgentAvailability.unavailable_until > since,
                AgentAvailability.unavailable_until <= now))).scalars()]
    # Marcelo answered a question the mission asked.
    events += [f"question_answered:{qid}" for qid in (await db.execute(select(AgentQuestion.id)
        .join(MissionDecision, MissionDecision.question_id == AgentQuestion.id).where(
        MissionDecision.mission_project_id == mission.project_id, AgentQuestion.status == "answered",
        AgentQuestion.answered_at > since, AgentQuestion.answered_at <= now))).scalars()]
    return sorted(set(events))


async def run_mission_cycle_pass(db: AsyncSession, now: datetime | None = None,
                                 project_ids: list[uuid.UUID] | None = None) -> dict[str, Any]:
    """One pass of the Operação 24x7 mission loop: the pending rerun, the
    events since each mission's cursor, then the watchdog. `project_ids`
    restricts it (tests share the database)."""
    now = now or utcnow()
    query = select(ProjectMission.project_id).where(ProjectMission.state.in_(CYCLE_STATES))
    if project_ids is not None:
        query = query.where(ProjectMission.project_id.in_(project_ids))
    summary: dict[str, Any] = {"started": [], "rerun_requested": [], "dropped": [], "alerts": []}
    for project_id in list((await db.execute(query.order_by(ProjectMission.project_id))).scalars()):
        try:
            mission = await db.get(ProjectMission, project_id)
            routine = await mission_routine(db, project_id)
            if routine is None or not routine.enabled:
                continue
            reason: str | None = None
            if mission.cycle_rerun_requested and await open_cycle_run(db, routine) is None:
                reason = "rerun requested by an event during the previous cycle"
            since = mission.cycle_event_cursor or mission.state_changed_at
            events = await detect_events(db, mission, since, now, routine)
            mission.cycle_event_cursor = now
            if events:
                reason = "events: " + ", ".join(events[:20])
            if reason:
                outcome = await request_mission_cycle(db, project_id, reason, source_ref="cycle-pass", now=now,
                                                      commit=False)
                await db.commit()
                if outcome == "started":
                    from app.core.dispatch_signal import wake_scheduled_dispatch
                    wake_scheduled_dispatch()
                summary[outcome].append(str(project_id))
            else:
                await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Mission cycle pass failed for %s", project_id)
    summary["alerts"] = await run_mission_cycle_watchdog(db, now, project_ids)
    return summary


# ---------------------------------------------------------------------------
# Watchdog (§3.4 item 4)
# ---------------------------------------------------------------------------
async def _in_flight_or_scheduled(db: AsyncSession, task_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    if not task_ids:
        return set()
    return set((await db.scalars(select(AgentDemand.origin_id).where(
        AgentDemand.origin_type == "task", AgentDemand.origin_id.in_(task_ids), AgentDemand.status != "archived",
        or_(AgentDemand.dispatch_status.in_(("dispatched", "running")),
            and_(AgentDemand.dispatch_status.is_(None), AgentDemand.scheduled_at.is_not(None))),
    ))).all())


async def watchdog_findings(db: AsyncSession, mission: ProjectMission, now: datetime) -> list[dict[str, Any]]:
    """`MISSION_CYCLE_GAP` (no cycle within MISSION_CYCLE_MAX_GAP) and
    `MISSION_IDLE_WITHOUT_REASON` (open work, nothing in flight or scheduled,
    and no defer/ask/pause recorded since the gap window)."""
    if mission.state not in WATCHED_STATES:
        return []
    findings: list[dict[str, Any]] = []
    routine = await mission_routine(db, mission.project_id)
    last_cycle = await db.scalar(select(func.max(AgentRoutineRun.occurrence_at)).where(
        AgentRoutineRun.routine_id == routine.id)) if routine is not None else None
    reference = max(filter(None, (last_cycle, mission.state_changed_at)))
    if routine is None or not routine.enabled or now - reference > MISSION_CYCLE_MAX_GAP:
        findings.append({"code": "MISSION_CYCLE_GAP", "last_cycle_at": last_cycle.isoformat() if last_cycle else None,
                         "max_gap_minutes": int(MISSION_CYCLE_MAX_GAP.total_seconds() // 60),
                         "routine_enabled": bool(routine and routine.enabled)})
    from app.core.mission_plan import mission_scope_tasks

    tasks = await mission_scope_tasks(db, mission.project_id)
    open_ids = [t.id for t in tasks.values() if t.status not in TERMINAL_TASK]
    if open_ids:
        asked = list((await db.scalars(select(MissionDecision).join(
            AgentQuestion, MissionDecision.question_id == AgentQuestion.id).where(
            MissionDecision.mission_project_id == mission.project_id,
            MissionDecision.action == "ask_marcelo", MissionDecision.status == "applied",
            AgentQuestion.status == "pending"))).all())
        held_by_question, _ = await _open_questions(db, asked)
        unattended = [task_id for task_id in open_ids if task_id not in held_by_question]
        busy = await _in_flight_or_scheduled(db, unattended)
        unattended = [task_id for task_id in unattended if task_id not in busy]
        if unattended:
            decisions = list((await db.scalars(select(MissionDecision).where(
                MissionDecision.mission_project_id == mission.project_id,
                MissionDecision.action.in_(("defer", "pause")),
                MissionDecision.status.in_(("applied", "deferred")),
                MissionDecision.created_at > now - MISSION_CYCLE_MAX_GAP,
            ))).all())
            # An explicit mission-wide defer remains a legitimate reason.
            global_hold = any(d.task_id is None for d in decisions)
            held_by_decision = {d.task_id for d in decisions if d.task_id is not None}
            unexplained = [task_id for task_id in unattended if task_id not in held_by_decision]
            if unexplained and not global_hold:
                findings.append({"code": "MISSION_IDLE_WITHOUT_REASON", "open_tasks": len(unexplained),
                                 "task_ids": sorted(str(task_id) for task_id in unexplained)})
    return findings


async def run_mission_cycle_watchdog(db: AsyncSession, now: datetime | None = None,
                                     project_ids: list[uuid.UUID] | None = None) -> list[dict[str, Any]]:
    """Raise one Operação 24x7 alert (deduplicated Notification) per finding
    and gap window. Returns the findings."""
    now = now or utcnow()
    query = select(ProjectMission).where(ProjectMission.state.in_(WATCHED_STATES))
    if project_ids is not None:
        query = query.where(ProjectMission.project_id.in_(project_ids))
    bucket = int(now.timestamp() // MISSION_CYCLE_MAX_GAP.total_seconds())
    alerts: list[dict[str, Any]] = []
    for mission in list((await db.execute(query.order_by(ProjectMission.project_id).with_for_update(skip_locked=True))).scalars()):
        for finding in await watchdog_findings(db, mission, now):
            key = f"mission-cycle:{finding['code']}:{mission.project_id}:{bucket}"
            if await db.scalar(select(Notification.id).where(Notification.event_key == key).limit(1)) is None:
                title = ("Missão sem ciclo recente" if finding["code"] == "MISSION_CYCLE_GAP"
                         else "Missão ativa parada sem motivo registrado")
                db.add(Notification(source="system", severity="warning", title=title,
                                    message=f"{finding['code']} — missão {mission.project_id}",
                                    event_key=key, occurred_at=now))
            if finding["code"] == "MISSION_CYCLE_GAP":
                routine = await mission_routine(db, mission.project_id)
                if routine and routine.enabled and await open_cycle_run(db, routine) is None:
                    finding["recovery"] = await request_mission_cycle(db, mission.project_id,
                        "24x7 detected a missing mission cycle", source_ref="watchdog", now=now, commit=False)
            alerts.append({"project_id": str(mission.project_id), **finding})
    await db.commit()
    if any(f.get("recovery") == "started" for f in alerts):
        from app.core.dispatch_signal import wake_scheduled_dispatch
        wake_scheduled_dispatch()
    return alerts


# ---------------------------------------------------------------------------
# Context pack (§3.6, MCP spec §6.1)
# ---------------------------------------------------------------------------
async def _context_sources(db: AsyncSession, mission: ProjectMission) -> dict[str, Any]:
    from app.core.mission_plan import mission_scope_tasks

    tasks = await mission_scope_tasks(db, mission.project_id)
    task_ids = list(tasks)
    decisions = list((await db.execute(select(MissionDecision.id).where(
        MissionDecision.mission_project_id == mission.project_id,
        MissionDecision.action != "advance_planning").order_by(MissionDecision.created_at, MissionDecision.id)
        .limit(500))).scalars())
    answered = list((await db.execute(select(AgentQuestion.id)
        .join(MissionDecision, MissionDecision.question_id == AgentQuestion.id).where(
        MissionDecision.mission_project_id == mission.project_id, AgentQuestion.status == "answered")
        .order_by(AgentQuestion.number))).scalars())
    missing: list[dict[str, str]] = []
    if task_ids:
        for demand_id, result in (await db.execute(select(AgentDemand.id, AgentDemand.dispatch_result).where(
                AgentDemand.origin_type == "task", AgentDemand.origin_id.in_(task_ids),
                AgentDemand.dispatch_result.is_not(None)).order_by(AgentDemand.created_at))).all():
            missing += [{"demand_id": str(demand_id), "item": line.strip()} for line in _CONTEXT_MISSING.findall(result)]
    return {
        "brief_artifact_id": str(mission.brief_artifact_id) if mission.brief_artifact_id else None,
        "current_baseline_id": str(mission.current_baseline_id) if mission.current_baseline_id else None,
        "decision_ids": [str(d) for d in decisions],
        "task_states": {str(t.id): t.status for t in sorted(tasks.values(), key=lambda t: t.number or 0)},
        "integrated_task_ids": sorted(str(t.id) for t in tasks.values() if t.status in ("done", "deployed")),
        "answered_question_ids": [str(q) for q in answered],
        "context_missing": missing,
    }


async def latest_context_version(db: AsyncSession, project_id: uuid.UUID) -> MissionContextVersion | None:
    return (await db.execute(select(MissionContextVersion).where(MissionContextVersion.project_id == project_id)
                             .order_by(MissionContextVersion.version.desc()).limit(1))).scalar_one_or_none()


async def write_context_version(
    db: AsyncSession, mission: ProjectMission, reason: str, *, actor_type: str = "system",
    actor_id: uuid.UUID | None = None,
) -> MissionContextVersion:
    """A new pack version when its content changed, else the current one.
    Serialized per mission (transaction advisory lock). Caller commits."""
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"mission-context:{mission.project_id}"))))
    sources = await _context_sources(db, mission)
    content_hash = _sha(sources)
    latest = await latest_context_version(db, mission.project_id)
    if latest is not None and latest.content_hash == content_hash:
        return latest
    version = MissionContextVersion(
        project_id=mission.project_id, version=(latest.version + 1) if latest else 1, content_hash=content_hash,
        sources=sources, created_by_type=actor_type, created_by_id=actor_id, reason=reason[:2000] or "update",
    )
    db.add(version)
    await db.flush()
    return version


def _material(sources: dict[str, Any]) -> tuple[Any, Any]:
    """What makes a delivery on an older pack invalid: the brief or baseline changed."""
    return sources.get("brief_artifact_id"), sources.get("current_baseline_id")


# ---------------------------------------------------------------------------
# Board and proposals (§2.3, §3)
# ---------------------------------------------------------------------------
def _proposal(action: str, reason_code: str, task: ProjectTask | None = None, **facts: Any) -> dict[str, Any]:
    params = facts.pop("params", {}) or {}
    body = {"action": action, "task_id": str(task.id) if task else None, "reason_code": reason_code,
            "params": params}
    return {
        "proposal_id": _sha(body)[:16], "action": action, "task_id": body["task_id"],
        "task_number": task.number if task else None, "reason_code": reason_code, "params": params,
        "reason_facts": facts,
        "autonomy_required": "N0" if action in N0_ACTIONS else ("info" if action in INFO_ACTIONS else "marcelo"),
    }


async def _decisions(db: AsyncSession, project_id: uuid.UUID) -> list[MissionDecision]:
    return list((await db.execute(select(MissionDecision).where(MissionDecision.mission_project_id == project_id)
                                  .order_by(MissionDecision.created_at, MissionDecision.id))).scalars())


def _is_integration(demand: AgentDemand) -> bool:
    return (demand.channel_ref or "").startswith(INTEGRATION_REF_PREFIX)


async def _eligible_executors(db: AsyncSession, project_ids: list[uuid.UUID], exclude: set[uuid.UUID]) -> list[uuid.UUID]:
    from app.core.mission_plan import NON_EXECUTOR_ROLES

    rows = (await db.execute(select(ProjectAgentMembership.agent_id).join(Agent, Agent.id == ProjectAgentMembership.agent_id)
        .where(ProjectAgentMembership.project_id.in_(project_ids), ProjectAgentMembership.status == "active",
               ProjectAgentMembership.role.not_in(NON_EXECUTOR_ROLES), Agent.is_active.is_(True))
        .order_by(ProjectAgentMembership.created_at, ProjectAgentMembership.agent_id))).scalars()
    return [a for a in dict.fromkeys(rows) if a not in exclude]


async def _eligible_reviewers(db: AsyncSession, project_ids: list[uuid.UUID], exclude: set[uuid.UUID]) -> list[uuid.UUID]:
    rows = (await db.execute(select(ProjectAgentMembership.agent_id).where(
        ProjectAgentMembership.project_id.in_(project_ids), ProjectAgentMembership.status == "active",
        ProjectAgentMembership.can_review.is_(True)).order_by(ProjectAgentMembership.created_at,
                                                             ProjectAgentMembership.agent_id))).scalars()
    return [a for a in dict.fromkeys(rows) if a not in exclude]


async def _task_proposals(
    db: AsyncSession, mission: ProjectMission, task: ProjectTask, ctx: dict[str, Any], now: datetime,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from app.core.task_dependencies import blocking_task_dependencies
    from app.core.demand_workflow import requires_reconciliation
    from app.core.mission import project_id_for_task_source
    from app.core.task_baseline_guard import assert_task_baseline_current
    from app.core.task_completion_guard import resolve_executor_agent_id

    task_project_id = await project_id_for_task_source(db, task.planning_item_id, task.change_request_id)
    scope_projects = list(dict.fromkeys((task_project_id, mission.project_id)))
    assignment = (await db.execute(select(TaskAssignment).where(
        TaskAssignment.task_id == task.id, TaskAssignment.status == "active", TaskAssignment.agent_id.is_not(None))
        .order_by(TaskAssignment.created_at.desc()).limit(1))).scalar_one_or_none()
    assignee = assignment.agent_id if assignment else None
    executions = list((await db.execute(select(TaskExecution).where(TaskExecution.task_id == task.id)
                                        .order_by(TaskExecution.attempt_number))).scalars())
    execution = executions[-1] if executions else None
    demands = list((await db.execute(select(AgentDemand).where(
        AgentDemand.origin_type == "task", AgentDemand.origin_id == task.id, AgentDemand.status != "archived")
        .order_by(AgentDemand.created_at, AgentDemand.id))).scalars())
    reviews = list((await db.execute(select(TaskExecutionReview).where(
        TaskExecutionReview.execution_id == execution.id).order_by(TaskExecutionReview.created_at))).scalars()) \
        if execution else []
    review = reviews[-1] if reviews else None
    review_demand_ids = {r.runtime_session_ref for r in reviews if r.runtime_session_ref}
    exec_demand = next((d for d in reversed(demands) if execution and d.task_execution_id == execution.id), None)
    integration = next((d for d in reversed(demands) if _is_integration(d)), None)
    review_demand = next((d for d in reversed(demands) if str(d.id) in review_demand_ids), None)
    until = ctx["unavailable"].get(assignee) if assignee else None
    lock = ctx["task_locks"].get(task.id)

    board = {
        "task_id": str(task.id), "number": task.number, "title": task.title, "status": task.status,
        "assignee_agent_id": str(assignee) if assignee else None,
        "assignee_unavailable_until": until.isoformat() if until else None,
        "locked": bool(lock),
        "execution": {"id": str(execution.id), "status": execution.status, "attempt": execution.attempt_number,
                      "evidence_ref": execution.evidence_ref} if execution else None,
        "review": {"id": str(review.id), "status": review.status} if review else None,
        "demands": [{"id": str(d.id), "number": d.number, "dispatch_status": d.dispatch_status,
                     "scheduled_at": d.scheduled_at.isoformat() if d.scheduled_at else None,
                     "kind": "integration" if _is_integration(d) else ("review" if str(d.id) in review_demand_ids
                                                                      else "execution"),
                     "context_version_id": str(d.mission_context_version_id) if d.mission_context_version_id else None}
                    for d in demands[-5:]],
    }
    if task.status in TERMINAL_TASK:
        return board, []
    if lock is not None:
        return board, [_proposal("wait", "task_locked", task, lock_id=str(lock.id))]
    question = ctx["questions_by_task"].get(task.id)
    if question is not None:
        return board, [_proposal("defer", f"awaiting_marcelo:{question}", task, question_id=str(question))]

    in_flight = next((d for d in demands if d.dispatch_status in ("dispatched", "running")
                      or (d.dispatch_status is None and d.agent_run_id)), None)
    uncertain = next((d for d in demands if requires_reconciliation(d)), None)
    if uncertain is not None:
        return board, [_proposal("wait", "uncertain_outcome", task, demand_number=uncertain.number)]
    if in_flight is not None:
        if in_flight.dispatched_at and in_flight.dispatch_deadline_at:
            mark = in_flight.dispatched_at + (in_flight.dispatch_deadline_at - in_flight.dispatched_at) * 0.8
            if now >= mark:
                return board, [_proposal("check_progress", "deadline_80", task, demand_number=in_flight.number,
                                         deadline_at=in_flight.dispatch_deadline_at.isoformat())]
        return board, [_proposal("wait", "run_in_flight", task, demand_number=in_flight.number)]
    queued = next((d for d in demands if d.dispatch_status is None and d.scheduled_at is not None
                   and d.agent_run_id is None), None)
    if queued is not None:
        return board, [_proposal("wait", "scheduled", task, demand_number=queued.number,
                                 scheduled_at=queued.scheduled_at.isoformat())]

    executor = await resolve_executor_agent_id(db, execution) if execution else None

    # A failed review run on infrastructure: the same role, another independent reviewer (§3.4 item 3).
    if review is not None and review.status in ("pending", "running") and review_demand is not None \
            and review_demand.dispatch_status == "failed":
        kind = classify_infra_failure(review_demand.dispatch_result, review_demand.dispatch_error)
        failed_reviewer = review_demand.target_agent_id
        if kind:
            candidates = await _eligible_reviewers(db, scope_projects, {failed_reviewer, executor, assignee} - {None})
            if candidates:
                return board, [_proposal("request_review", "review_infra_failure", task, infra=kind,
                                         failed_reviewer_agent_id=str(failed_reviewer),
                                         params={"execution_id": str(execution.id),
                                                 "reviewer_agent_id": str(candidates[0]),
                                                 "replace_review_id": str(review.id)})]
            return board, [_proposal("ask_marcelo", "no_independent_reviewer", task, infra=kind)]
        return board, [_proposal("ask_marcelo", "review_run_failed", task, demand_number=review_demand.number)]

    # The executor's last run failed (§3.4 item 3: infrastructure is not rejection).
    if exec_demand is not None and exec_demand.dispatch_status == "failed" \
            and execution is not None and execution.status == "failed":
        kind = classify_infra_failure(exec_demand.dispatch_result, exec_demand.dispatch_error)
        limit = exec_demand.retry_limit or DISPATCH_MAX_ATTEMPTS
        reprocessed = sum(1 for d in ctx["decisions"] if d.action == "reprocess" and d.demand_id == exec_demand.id
                          and d.status == "applied")
        failed_runs = sum(1 for e in executions if e.status == "failed")
        if kind:
            if until is not None:
                return board, [_proposal("schedule", "executor_unavailable", task, infra=kind,
                                         unavailable_until=until.isoformat(),
                                         params={"scheduled_at": (until + RESCHEDULE_MARGIN).isoformat()})]
            if reprocessed < 1 and (exec_demand.dispatch_attempts or 0) < limit:
                return board, [_proposal("reprocess", "infra_failure", task, infra=kind,
                                         params={"demand_id": str(exec_demand.id)})]
            candidates = await _eligible_executors(db, scope_projects, {assignee} - {None})
            if candidates:
                return board, [_proposal("reassign", "infra_failure_repeated", task, infra=kind,
                                         params={"agent_id": str(candidates[0])})]
            return board, [_proposal("ask_marcelo", "infra_failure_no_alternative", task, infra=kind)]
        if failed_runs >= 2:
            candidates = await _eligible_executors(db, scope_projects, {assignee} - {None})
            if candidates:
                return board, [_proposal("reassign", "failed_twice", task, failed_runs=failed_runs,
                                         params={"agent_id": str(candidates[0])})]
        if (exec_demand.dispatch_attempts or 0) < limit:
            return board, [_proposal("reprocess", "known_failure", task,
                                     params={"demand_id": str(exec_demand.id)})]
        return board, [_proposal("ask_marcelo", "retry_budget_exhausted", task, attempts=exec_demand.dispatch_attempts,
                                 retry_limit=limit)]

    if execution is not None and execution.status == "reported":
        return board, [_proposal("wait", "awaiting_evidence_check", task, execution_id=str(execution.id))]

    if execution is not None and execution.status == "verified":
        if review is None:
            reverify = next((d for d in reversed(ctx["decisions"]) if d.action == "reverify"
                             and d.status == "applied" and (d.facts or {}).get("execution_id") == str(execution.id)),
                            None)
            if reverify is None:
                return board, [_proposal("reverify", "verified_not_reverified", task,
                                         params={"execution_id": str(execution.id)})]
            if (reverify.facts or {}).get("match") is False:
                return board, [_proposal("return", "reverify_mismatch", task, detail=reverify.facts.get("detail"),
                                         params={"execution_id": str(execution.id)})]
            stale = await _stale_context(db, exec_demand, ctx)
            if stale:
                return board, [_proposal("return", "stale_context", task, **stale,
                                         params={"execution_id": str(execution.id)})]
            if (reverify.facts or {}).get("match") is None:
                return board, [_proposal("ask_marcelo", "reverify_inconclusive", task,
                                         detail=(reverify.facts or {}).get("detail"))]
            candidates = await _eligible_reviewers(db, scope_projects, {executor, assignee} - {None})
            if not candidates:
                return board, [_proposal("ask_marcelo", "no_independent_reviewer", task)]
            return board, [_proposal("request_review", "verified_and_reverified", task,
                                     params={"execution_id": str(execution.id), "reviewer_agent_id": str(candidates[0])})]
        if review.status in ("pending", "running"):
            return board, [_proposal("wait", "review_open", task, review_id=str(review.id))]
        if review.status == "approved":
            if integration is not None and integration.dispatch_status == "failed":
                files = sorted(set(_CONFLICT_FILE.findall(integration.dispatch_result or "")))
                if files or "conflict" in (integration.dispatch_result or "").lower():
                    return board, [_proposal("return", "integration_conflict", task, conflicting_files=files,
                                             demand_number=integration.number,
                                             params={"execution_id": str(execution.id)})]
            return board, [_proposal("integrate", "review_approved", task,
                                     params={"execution_id": str(execution.id)})]

    if review is not None and review.status in ("changes_requested", "rejected") and task.status != "in_progress":
        # return_task_for_correction already put it back to in_progress; a
        # review decided elsewhere is returned first.
        return board, [_proposal("return", f"review_{review.status}", task,
                                 params={"execution_id": str(execution.id)})]

    # Ready to run (first attempt, or a correction after a return).
    if assignee is None:
        candidates = await _eligible_executors(db, scope_projects, set())
        if candidates:
            return board, [_proposal("reassign", "unassigned", task, params={"agent_id": str(candidates[0])})]
        return board, [_proposal("ask_marcelo", "no_eligible_executor", task)]
    blocking = await blocking_task_dependencies(db, task.id)
    if blocking:
        return board, [_proposal("wait", "dependencies_open", task,
                                 blocking=[b.get("task_number") for b in blocking])]
    try:
        await assert_task_baseline_current(db, task)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        return board, [_proposal("wait", "baseline_guard", task, guard=detail.get("code") or str(detail)[:200])]
    gaps = ctx["skill_gaps"].get(task.id)
    if gaps:
        return board, [_proposal("defer", "skill_gap", task, missing=gaps),
                       _proposal("propose_skill", "skill_gap", task, missing=gaps)]
    if until is not None:
        candidates = await _eligible_executors(db, scope_projects, {assignee})
        if until - now > REASSIGN_UNAVAILABLE_AFTER and candidates:
            return board, [_proposal("reassign", "executor_unavailable_long", task, unavailable_until=until.isoformat(),
                                     params={"agent_id": str(candidates[0])})]
        return board, [_proposal("schedule", "executor_unavailable", task, unavailable_until=until.isoformat(),
                                 params={"scheduled_at": (until + RESCHEDULE_MARGIN).isoformat()})]
    if assignee in ctx["busy_agents"]:
        return board, [_proposal("wait", "executor_busy", task)]
    busy_target = await _busy_target(db, task, ctx)
    if busy_target:
        return board, [_proposal("wait", "target_busy", task, target=busy_target)]
    return board, [_proposal("dispatch", "ready", task)]


async def _busy_target(db: AsyncSession, task: ProjectTask, ctx: dict[str, Any]) -> str | None:
    from app.core.dispatch_targets import _first_holder, task_targets

    return await _first_holder(db, await task_targets(db, task, ctx["working_paths"].get(task.id)))


async def _stale_context(db: AsyncSession, demand: AgentDemand | None, ctx: dict[str, Any]) -> dict[str, Any] | None:
    """A delivery made on a pack version whose brief/baseline was superseded."""
    latest: MissionContextVersion | None = ctx["context"]
    if demand is None or demand.mission_context_version_id is None or latest is None \
            or demand.mission_context_version_id == latest.id:
        return None
    carried = await db.get(MissionContextVersion, demand.mission_context_version_id)
    if carried is None or _material(carried.sources) == _material(latest.sources):
        return None
    return {"carried_version": carried.version, "current_version": latest.version}


async def _skill_gaps(db: AsyncSession, mission: ProjectMission, tasks: list[ProjectTask]) -> dict[uuid.UUID, list[str]]:
    """Required skills the active assignee does not hold (§3.6)."""
    from app.core.task_skills import required_skill_map
    from app.db.models.agent import AgentSkill

    required = await required_skill_map(db, [t.id for t in tasks])
    gaps: dict[uuid.UUID, list[str]] = {}
    for task in tasks:
        wanted = set(required.get(task.id) or ())
        if not wanted:
            continue
        assignee = await db.scalar(select(TaskAssignment.agent_id).where(
            TaskAssignment.task_id == task.id, TaskAssignment.status == "active")
            .order_by(TaskAssignment.created_at.desc()).limit(1))
        if assignee is None:
            continue
        held = set((await db.execute(select(AgentSkill.skill_id).where(
            AgentSkill.agent_id == assignee, AgentSkill.skill_id.in_(wanted)))).scalars())
        if wanted - held:
            gaps[task.id] = sorted(str(s) for s in wanted - held)
    return gaps


async def _open_questions(db: AsyncSession, decisions: list[MissionDecision]) -> tuple[dict, list]:
    """Pending questions the mission asked: which tasks each one holds, and
    the questions past their answer_by (§3.7)."""
    by_task: dict[uuid.UUID, uuid.UUID] = {}
    overdue: list[tuple[MissionDecision, AgentQuestion]] = []
    asked = [d for d in decisions if d.action == "ask_marcelo" and d.question_id and d.status == "applied"]
    for decision in asked:
        question = await db.get(AgentQuestion, decision.question_id)
        if question is None or question.status != "pending":
            continue
        for task_id in (decision.facts or {}).get("dependent_task_ids") or []:
            by_task.setdefault(uuid.UUID(task_id), question.id)
        overdue.append((decision, question))
    return by_task, overdue


def _question_proposals(overdue: list, decisions: list[MissionDecision], now: datetime) -> list[dict[str, Any]]:
    """At answer_by without an answer: the recommendation only when it is
    reversible (and within N0); otherwise one re-ask, then keep waiting."""
    out: list[dict[str, Any]] = []
    for decision, question in overdue:
        facts = decision.facts or {}
        answer_by = facts.get("answer_by")
        if not answer_by or datetime.fromisoformat(answer_by) > now:
            continue
        if facts.get("reask_of"):
            out.append(_proposal("wait", "awaiting_marcelo_after_reask", None, question_id=str(question.id)))
            continue
        if facts.get("default_reversible") is True:
            out.append(_proposal("apply_default", "answer_by_passed", None, question_id=str(question.id),
                                 default_action=facts.get("default_action")))
            continue
        reasked = any(d.action == "ask_marcelo" and (d.facts or {}).get("reask_of") == str(question.id)
                      for d in decisions)
        if reasked:
            out.append(_proposal("wait", "awaiting_marcelo_irreversible", None, question_id=str(question.id)))
        else:
            out.append(_proposal("ask_marcelo", "reask_irreversible_default", None, question_id=str(question.id),
                                 params={"reask_of": str(question.id)}))
    return out


async def _planning_proposals(db: AsyncSession, mission: ProjectMission) -> list[dict[str, Any]]:
    """§3.5: the cycle conducts P1-P8 only through planning:advance, raises
    flagged items to Marcelo, never decides an item, never approves a baseline."""
    from app.core.mission import next_planning_stages, planning_exit_conditions
    from app.core.mission_records import current_plan, flagged_items, plan_items

    out: list[dict[str, Any]] = []
    unmet, not_evaluated = await planning_exit_conditions(db, mission)
    plan = await current_plan(db, mission.project_id)
    if plan is not None:
        flagged = flagged_items(await plan_items(db, plan.id))
        if flagged:
            out.append(_proposal("ask_marcelo", "flagged_review_items", None,
                                 items=[f.get("item_id") for f in flagged][:20]))
    if unmet:
        out.append(_proposal("wait", "planning_exit_unmet", None, stage=mission.planning_stage,
                             unmet=sorted({u["code"] for u in unmet})))
    else:
        nxt = next_planning_stages(mission)
        if nxt:
            out.append(_proposal("advance_planning", "planning_exit_met", None, stage=mission.planning_stage,
                                 params={"to": nxt[0]},
                                 not_evaluated=sorted({n["code"] for n in not_evaluated})))
    return out


async def build_cycle(db: AsyncSession, mission: ProjectMission, now: datetime | None = None) -> dict[str, Any]:
    """The board and the deterministic proposals of one mission."""
    from app.api.routes.demand import _agents_already_running
    from app.core.mission import project_id_for_task_source
    from app.core.mission_plan import mission_scope_tasks
    from app.db.models.project import Project

    now = now or utcnow()
    locks = await open_locks(db, mission.project_id, now)
    cycle_lock = next((lock for lock in locks if lock.task_id is None), None)
    decisions = await _decisions(db, mission.project_id)
    tasks = sorted((await mission_scope_tasks(db, mission.project_id)).values(), key=lambda t: (t.number or 0, str(t.id)))
    questions_by_task, overdue = await _open_questions(db, decisions)
    working_paths: dict[uuid.UUID, str | None] = {}
    for task in tasks:
        project = await db.get(Project, await project_id_for_task_source(db, task.planning_item_id, task.change_request_id))
        working_paths[task.id] = project.working_directory_path if project else None
    ctx = {
        "decisions": decisions, "task_locks": {lock.task_id: lock for lock in locks if lock.task_id},
        "unavailable": await unavailable_agents(db, now), "busy_agents": await _agents_already_running(db),
        "questions_by_task": questions_by_task, "working_paths": working_paths,
        "skill_gaps": await _skill_gaps(db, mission, [t for t in tasks if t.status not in TERMINAL_TASK]),
        "context": await latest_context_version(db, mission.project_id),
    }
    board: list[dict[str, Any]] = []
    proposals: list[dict[str, Any]] = []
    if mission.state == "planning":
        proposals += await _planning_proposals(db, mission)
    elif mission.state in WATCHED_STATES:
        for task in tasks:
            row, task_proposals = await _task_proposals(db, mission, task, ctx, now)
            board.append(row)
            proposals += task_proposals
        proposals += _question_proposals(overdue, decisions, now)
        open_tasks = [t for t in tasks if t.status not in TERMINAL_TASK]
        actionable = [p for p in proposals if p["action"] in N0_ACTIONS and p["action"] != "defer"]
        moving = [p for p in proposals if p["reason_code"] in ("run_in_flight", "scheduled", "deadline_80",
                                                                "awaiting_evidence_check", "review_open",
                                                                "executor_busy", "target_busy",
                                                                "dependencies_open")]
        if mission.deadline_at is not None and now > mission.deadline_at and open_tasks:
            proposals.append(_proposal("pause", "blocked:deadline", None, deadline_at=mission.deadline_at.isoformat(),
                                       params={"reason": "blocked:deadline"}))
        elif open_tasks and not actionable and not moving:
            proposals.append(_proposal("pause", "blocked:all_tasks_blocked", None,
                                       open_tasks=[t.number for t in open_tasks],
                                       params={"reason": "blocked:all_tasks_blocked"}))
    proposals.sort(key=lambda p: (p["task_number"] if p["task_number"] is not None else 1 << 30,
                                  _ACTION_ORDER.get(p["action"], 99), p["proposal_id"]))
    for proposal in proposals:
        task_locked = proposal["task_id"] and uuid.UUID(proposal["task_id"]) in ctx["task_locks"]
        proposal["allowed"] = (proposal["action"] in N0_ACTIONS and cycle_lock is None and not task_locked
                               and mission.autonomy_level == "N0")
    board_hash = _sha(board)
    for proposal in proposals:
        proposal["reason_facts"]["board_hash"] = board_hash
    context = ctx["context"]
    return {
        "mission_state": mission.state, "autonomy_level": mission.autonomy_level, "board": board,
        "board_hash": board_hash, "proposals": proposals,
        "locked": {"lock_id": str(cycle_lock.id), "reason": cycle_lock.reason} if cycle_lock else None,
        "context_version": {"id": str(context.id), "version": context.version, "hash": context.content_hash}
        if context else None,
        "watchdog": await watchdog_findings(db, mission, now),
    }
