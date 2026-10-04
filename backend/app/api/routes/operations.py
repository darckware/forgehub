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
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.demand import create_demand_and_notify
from app.api.schemas.demand import DemandSubmitIn
from app.api.schemas.operations import (
    AgentChangeProposalIn,
    AgentOperationsSummary,
    QuestionAnswerIn,
    QuestionAskIn,
    QuestionOut,
    QuestionRelayAnswerIn,
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
from app.core import agent_questions
from app.core.operations_evolution import execution_signals
from app.core.config import settings
from app.core.deps import get_current_admin
from app.core.routine_schedule import (
    local_day_bounds,
    next_occurrences,
    occurrences_between,
    validate_schedule,
)
from app.db.base import get_db
from app.db.models.agent import Agent
from app.db.models.audit import AuditCheck, AuditCheckRun
from app.db.models.demand import AgentDemand
from app.db.models.notification import Notification
from app.db.models.operations import (
    ROUTINE_RUN_TERMINAL_STATUSES,
    AgentCharter,
    AgentQuestion,
    AgentRoutine,
    AgentRoutineRun,
    OperationsChange,
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
                if demand is not None and new_status in ("completed", "failed"):
                    signals = execution_signals(demand)
                    run.duration_ms = signals.duration_ms
                    run.cost_usd = signals.cost_usd
                    run.evidence_received = signals.evidence_received
                    run.no_action = signals.no_action
            changed += 1
    if changed:
        await db.commit()
    return changed


async def _routine_metric(
    db: AsyncSession, routine_id: uuid.UUID, metric_name: str,
    start: datetime, end: datetime,
) -> Decimal | None:
    runs = list((await db.execute(
        select(AgentRoutineRun).where(
            AgentRoutineRun.routine_id == routine_id,
            AgentRoutineRun.occurrence_at >= start,
            AgentRoutineRun.occurrence_at < end,
        )
    )).scalars())
    if metric_name == "failed_runs":
        return Decimal(sum(run.status == "failed" for run in runs))
    if metric_name == "evidence_rate":
        completed = [run for run in runs if run.status == "completed"]
        return (Decimal(sum(run.evidence_received is True for run in completed)) / Decimal(len(completed))) if completed else None
    return None


async def run_evolution_pass(
    db: AsyncSession, now: datetime | None = None,
    routine_ids: list[uuid.UUID] | None = None,
    change_ids: list[uuid.UUID] | None = None,
) -> int:
    """Evaluate due changes, then apply deduplicated A0/A1 proposals."""
    from app.core.operations_evolution import suggest_routine_change

    now = now or datetime.now(timezone.utc)
    approval_query = select(OperationsChange).where(
        OperationsChange.status == "awaiting_approval",
        OperationsChange.question_id.is_not(None),
    )
    if change_ids is not None:
        approval_query = approval_query.where(OperationsChange.id.in_(change_ids))
    approvals = list((await db.execute(approval_query.with_for_update())).scalars())
    decided = 0
    for change in approvals:
        question = await db.get(AgentQuestion, change.question_id)
        if question is None or question.status != "answered" or not question.answer:
            continue
        answer = question.answer.strip().casefold()
        approved = answer in ("sim", "aprovado", "aprovada", "yes", "approved") or answer.startswith(("sim,", "sim.", "aprovado,"))
        rejected = answer in ("não", "nao", "no", "rejeitado", "rejeitada") or answer.startswith(("não,", "nao,", "no,"))
        if not approved and not rejected:
            continue
        if rejected:
            change.status = "rejected"
            change.evaluated_at = now
            change.learning = f"Marcelo não aprovou: {question.answer.strip()[:500]}"
            decided += 1
            continue
        if change.target_type == "charter":
            agent_id = uuid.UUID(change.previous_state["agent_id"])
            charter = (await db.execute(
                select(AgentCharter).where(AgentCharter.agent_id == agent_id).with_for_update()
            )).scalar_one_or_none()
            if charter is None or any(
                str(getattr(charter, field)) != str(value)
                for field, value in change.previous_state.items() if field != "agent_id"
            ):
                change.status = "rejected"
                change.learning = "A carta mudou após a proposta; gere uma nova proposta sobre a versão atual."
                change.evaluated_at = now
                decided += 1
                continue
            for field, value in change.new_state.items():
                setattr(charter, field, Decimal(str(value)) if field == "daily_cost_budget" else value)
        elif change.target_type == "policy":
            current = await _current_policy(db)
            if (current.version if current else 0) != change.previous_state.get("version"):
                change.status = "rejected"
                change.learning = "A política mudou após a proposta; gere uma nova proposta sobre a versão atual."
                change.evaluated_at = now
                decided += 1
                continue
            db.add(OperationsPolicy(
                version=(current.version + 1) if current else 1,
                content=change.new_state["content"],
                author="operations-a2",
                change_reason=f"Aprovada na pergunta #{question.number}: {change.summary}",
            ))
        else:
            continue
        change.status = "evaluating"
        change.applied_at = now
        change.evaluation_ends_at = now + timedelta(days=7)
        decided += 1

    due_query = select(OperationsChange).where(
        OperationsChange.status == "evaluating",
        OperationsChange.evaluation_ends_at <= now,
    )
    if routine_ids is not None:
        due_query = due_query.where(OperationsChange.routine_id.in_(routine_ids))
    due = list((await db.execute(due_query.with_for_update())).scalars())
    evaluated = 0
    for change in due:
        if change.target_type != "routine":
            change.evaluated_at = now
            change.status = "kept"
            change.learning = "Janela de avaliação encerrada; mudança A2 mantida para revisão humana."
            evaluated += 1
            continue
        after = await _routine_metric(
            db, change.routine_id, change.metric_name,
            change.applied_at, change.evaluation_ends_at,
        )
        change.after_value = after
        change.evaluated_at = now
        routine = await db.get(AgentRoutine, change.routine_id) if change.routine_id else None
        worse = (
            after is not None and change.before_value is not None and
            ((change.metric_name == "failed_runs" and after > change.before_value) or
             (change.metric_name == "evidence_rate" and after < change.before_value))
        )
        state_matches = routine is not None and all(
            getattr(routine, field) == value for field, value in change.new_state.items()
        )
        if worse and change.autonomy_level in ("A0", "A1") and state_matches:
            for field, value in change.previous_state.items():
                setattr(routine, field, value)
            if change.previous_state.get("enabled") is True:
                routine.last_occurrence_at = now
            change.status = "reverted"
            change.learning = f"Métrica {change.metric_name} piorou de {change.before_value} para {after}; mudança desfeita automaticamente."
        else:
            change.status = "kept"
            if not state_matches:
                change.learning = "Estado alterado por outra intervenção; reversão automática ignorada."
            elif after is None:
                change.learning = "Sem amostra na janela de avaliação; mudança mantida para revisão humana."
            else:
                change.learning = f"Métrica {change.metric_name}: {change.before_value} → {after}; mudança mantida."
        evaluated += 1

    query = select(AgentRoutine.id).where(AgentRoutine.enabled.is_(True))
    if routine_ids is not None:
        query = query.where(AgentRoutine.id.in_(routine_ids))
    ids = list((await db.execute(query)).scalars())
    applied = 0
    for routine_id in ids:
        routine = (await db.execute(
            select(AgentRoutine).where(AgentRoutine.id == routine_id).with_for_update()
        )).scalar_one_or_none()
        if routine is None or not routine.enabled:
            continue
        recent = list((await db.execute(
            select(AgentRoutineRun)
            .where(
                AgentRoutineRun.routine_id == routine_id,
                AgentRoutineRun.occurrence_at >= now - timedelta(days=7),
            )
            .order_by(AgentRoutineRun.occurrence_at.desc()).limit(3)
        )).scalars())
        proposal = suggest_routine_change(routine, recent)
        if proposal is None:
            continue
        active = (await db.execute(
            select(OperationsChange.id).where(
                OperationsChange.routine_id == routine_id,
                OperationsChange.metric_name == proposal.metric_name,
                OperationsChange.status.in_(("proposed", "awaiting_approval", "evaluating")),
            ).limit(1)
        )).scalar_one_or_none()
        if active is not None:
            continue
        before = await _routine_metric(db, routine_id, proposal.metric_name, now - timedelta(days=7), now)
        change = OperationsChange(
            routine_id=routine_id, target_type="routine", summary=proposal.summary,
            rationale=proposal.rationale, autonomy_level=proposal.autonomy_level,
            status="evaluating", metric_name=proposal.metric_name, before_value=before,
            previous_state=proposal.previous_state, new_state=proposal.new_state,
            applied_at=now, evaluation_ends_at=now + timedelta(days=7),
        )
        for field, value in proposal.new_state.items():
            setattr(routine, field, value)
        db.add(change)
        await db.flush()
        db.add(Notification(
            source="system", severity="warning" if proposal.autonomy_level == "A0" else "info",
            title=f"Operations {proposal.autonomy_level}: {routine.title}"[:255],
            message=f"{proposal.summary}. {proposal.rationale} Avaliação até {change.evaluation_ends_at.date()}.",
            event_key=f"operations-change:{change.id}", occurred_at=now,
        ))
        applied += 1
    if applied or evaluated or decided:
        await db.commit()
    return applied + evaluated + decided


def _change_out(change: OperationsChange) -> dict:
    return {
        "id": str(change.id), "target_type": change.target_type,
        "target_id": str(change.routine_id) if change.routine_id else change.previous_state.get("agent_id"),
        "summary": change.summary, "rationale": change.rationale,
        "autonomy_level": change.autonomy_level, "status": change.status,
        "metric_name": change.metric_name,
        "before_value": float(change.before_value) if change.before_value is not None else None,
        "after_value": float(change.after_value) if change.after_value is not None else None,
        "evaluation_ends_at": change.evaluation_ends_at.isoformat() if change.evaluation_ends_at else None,
        "created_at": change.created_at.isoformat(),
    }


@router.get("/evolution")
async def get_evolution(db: AsyncSession = Depends(get_db)) -> dict:
    """Seven days of outcomes and the reversible change ledger."""
    local_tz = ZoneInfo("America/Sao_Paulo")
    today = datetime.now(local_tz).date()
    start = datetime.combine(today - timedelta(days=6), datetime.min.time(), tzinfo=local_tz).astimezone(timezone.utc)
    changes = list((await db.execute(
        select(OperationsChange).order_by(OperationsChange.created_at.desc()).limit(100)
    )).scalars())
    runs = (await db.execute(
        select(AgentRoutineRun.occurrence_at, AgentRoutineRun.status, AgentRoutineRun.cost_usd)
        .where(AgentRoutineRun.occurrence_at >= start)
    )).all()
    audit_runs = (await db.execute(
        select(AuditCheckRun.created_at, AuditCheckRun.status)
        .where(AuditCheckRun.created_at >= start)
    )).all()
    trend = {
        (today - timedelta(days=offset)).isoformat(): {
            "date": (today - timedelta(days=offset)).isoformat(),
            "routines_completed": 0, "routines_failed": 0,
            "audit_ok": 0, "audit_failed": 0,
            "cost_usd": None, "improvements_delivered": 0,
        }
        for offset in range(6, -1, -1)
    }
    for occurred_at, state, cost in runs:
        day = trend.get(occurred_at.astimezone(local_tz).date().isoformat())
        if day is None:
            continue
        if state == "completed":
            day["routines_completed"] += 1
        elif state in ("failed", "missed", "skipped_budget"):
            day["routines_failed"] += 1
        if cost is not None:
            day["cost_usd"] = (day["cost_usd"] or 0) + float(cost)
    for occurred_at, state in audit_runs:
        day = trend.get(occurred_at.astimezone(local_tz).date().isoformat())
        if day is not None:
            day["audit_ok" if state == "ok" else "audit_failed"] += 1
    for change in changes:
        if change.status == "kept" and change.evaluated_at:
            day = trend.get(change.evaluated_at.astimezone(local_tz).date().isoformat())
            if day is not None:
                day["improvements_delivered"] += 1
    return {"changes": [_change_out(change) for change in changes], "trend": list(trend.values())}


@router.post("/agent-changes", status_code=status.HTTP_201_CREATED)
async def propose_agent_change(
    payload: AgentChangeProposalIn,
    x_bridge_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """An agent proposes an A2 change; only Marcelo's answer may apply it."""
    _require_bridge(x_bridge_token)
    proposer = await _agent_by_slug_or_404(db, payload.agent)
    if payload.target_type == "charter":
        if payload.target_id is None:
            raise HTTPException(422, "target_id is required for a charter change")
        charter = (await db.execute(
            select(AgentCharter).where(AgentCharter.agent_id == payload.target_id)
        )).scalar_one_or_none()
        if charter is None:
            raise HTTPException(404, "Charter not found")
        allowed = {"mission", "responsibilities", "monitored_domains", "coordinates_with",
                   "never_does", "daily_run_budget", "daily_cost_budget", "escalation"}
        if not payload.new_state or set(payload.new_state) - allowed:
            raise HTTPException(422, "Unsupported charter fields")
        baseline = {field: getattr(charter, field) for field in allowed}
        validated = CharterIn.model_validate({**baseline, **payload.new_state}).model_dump(mode="json")
        new_state = {field: validated[field] for field in payload.new_state}
        previous_state = {"agent_id": str(payload.target_id), **{
            field: str(baseline[field]) if isinstance(baseline[field], Decimal) else baseline[field]
            for field in payload.new_state
        }}
    else:
        if payload.target_id is not None or set(payload.new_state) != {"content"}:
            raise HTTPException(422, "Policy change requires only content and no target_id")
        policy = await _current_policy(db)
        content = payload.new_state.get("content")
        if not isinstance(content, str) or not content.strip():
            raise HTTPException(422, "Policy content is required")
        new_state = {"content": content.strip()}
        previous_state = {"version": policy.version if policy else 0, "content": policy.content if policy else ""}
    if all(previous_state.get(field) == value for field, value in new_state.items()):
        raise HTTPException(409, "Proposal does not change the current state")
    duplicate = (await db.execute(select(OperationsChange).where(
        OperationsChange.target_type == payload.target_type,
        OperationsChange.status == "awaiting_approval",
        OperationsChange.new_state == new_state,
        OperationsChange.previous_state == previous_state,
    ).limit(1))).scalar_one_or_none()
    if duplicate is not None:
        raise HTTPException(409, "Equivalent change already awaits approval")

    relay, chat = await agent_questions.resolve_relay(db, proposer)
    now = datetime.now(timezone.utc)
    question = AgentQuestion(
        agent_id=proposer.id, relay_agent_id=relay.id if relay else None,
        telegram_chat=chat,
        question=f"Aprova a mudança A2? {payload.summary.strip()}",
        context=f"Motivo: {payload.rationale.strip()}\nNovo estado: {new_state}",
        recommendation="Responda SIM para aprovar ou NÃO para rejeitar.",
        blocking=True, urgent=False,
        notify_after=agent_questions.notify_after_for(now, False),
    )
    db.add(question)
    await db.flush()
    change = OperationsChange(
        target_type=payload.target_type, routine_id=None, question_id=question.id,
        summary=payload.summary.strip(), rationale=payload.rationale.strip(),
        autonomy_level="A2", status="awaiting_approval",
        metric_name=payload.metric_name, previous_state=previous_state,
        new_state=new_state,
    )
    db.add(change)
    db.add(Notification(
        source="system", severity="warning", title=f"Pergunta #{question.number} de {proposer.name}",
        message=question.question[:500], event_key=f"agent-question:{question.id}", occurred_at=now,
    ))
    await db.commit()
    await db.refresh(change)
    return _change_out(change)


@router.post("/changes/{change_id}:undo")
async def undo_change(
    change_id: uuid.UUID, db: AsyncSession = Depends(get_db), _admin=Depends(get_current_admin)
) -> dict:
    change = (await db.execute(
        select(OperationsChange).where(OperationsChange.id == change_id).with_for_update()
    )).scalar_one_or_none()
    if change is None:
        raise HTTPException(status_code=404, detail="Operations change not found")
    if change.status not in ("evaluating", "kept"):
        raise HTTPException(status_code=409, detail="Only applied changes can be undone")
    if change.target_type == "routine":
        routine = await db.get(AgentRoutine, change.routine_id) if change.routine_id else None
        if routine is None:
            raise HTTPException(status_code=409, detail="Changed routine no longer exists")
        if any(getattr(routine, field) != value for field, value in change.new_state.items()):
            raise HTTPException(status_code=409, detail="Routine changed since this proposal was applied")
        for field, value in change.previous_state.items():
            setattr(routine, field, value)
        if change.previous_state.get("enabled") is True:
            routine.last_occurrence_at = datetime.now(timezone.utc)
    elif change.target_type == "charter":
        charter = (await db.execute(select(AgentCharter).where(
            AgentCharter.agent_id == uuid.UUID(change.previous_state["agent_id"])
        ).with_for_update())).scalar_one_or_none()
        if charter is None or any(
            str(getattr(charter, field)) != str(value) for field, value in change.new_state.items()
        ):
            raise HTTPException(status_code=409, detail="Charter changed since this proposal was applied")
        for field, value in change.previous_state.items():
            if field != "agent_id":
                setattr(charter, field, Decimal(str(value)) if field == "daily_cost_budget" else value)
    elif change.target_type == "policy":
        current = await _current_policy(db)
        if current is None or current.version != change.previous_state["version"] + 1 or current.content != change.new_state["content"]:
            raise HTTPException(status_code=409, detail="Policy changed since this proposal was applied")
        db.add(OperationsPolicy(
            version=current.version + 1,
            content=change.previous_state["content"],
            author="operations-a2-undo",
            change_reason=f"Reversão da mudança {change.id}",
        ))
    else:
        raise HTTPException(status_code=409, detail="Unsupported change target")
    change.status = "reverted"
    change.evaluated_at = datetime.now(timezone.utc)
    change.learning = "Desfeita manualmente pelo administrador."
    await db.commit()
    await db.refresh(change)
    return _change_out(change)


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


# ---------------------------------------------------------------- questions
#
# Two surfaces. /agent-questions is the agents' side (bridge token, the
# forgehub Messages MCP's ask_marcelo / list_my_questions /
# record_marcelo_answer) and is carved out of RequireAuthMiddleware in
# main.py. /questions is Marcelo's side (JWT): the Dúvidas tab lists and
# answers. Answering from either side goes through
# agent_questions.record_answer, so the agent gets the same Task either way.


def _require_bridge(token: str | None) -> None:
    if not settings.CHAT_BRIDGE_TOKEN or token != settings.CHAT_BRIDGE_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bridge token")


async def _agent_by_slug_or_404(db: AsyncSession, slug: str) -> Agent:
    agent = (await db.execute(select(Agent).where(Agent.profile_slug == slug.strip()))).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No agent with profile_slug {slug!r}")
    return agent


async def _question_out(db: AsyncSession, question: AgentQuestion) -> QuestionOut:
    out = QuestionOut.model_validate(question)
    asker = await db.get(Agent, question.agent_id)
    relay = await db.get(Agent, question.relay_agent_id) if question.relay_agent_id else None
    out.agent_name = asker.name if asker else None
    out.relay_agent_name = relay.name if relay else None
    return out


def _assert_pending(question: AgentQuestion) -> None:
    if question.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Question #{question.number} is already {question.status}",
        )


@router.post("/agent-questions", response_model=QuestionOut, status_code=status.HTTP_201_CREATED)
async def ask_question(
    payload: QuestionAskIn,
    x_bridge_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> QuestionOut:
    """An agent asks Marcelo something (MCP ask_marcelo). Recorded and shown
    in ForgeHub at once; the Telegram message goes out with the next delivery
    pass (every minute), or at 07:00 when asked in the quiet window."""
    _require_bridge(x_bridge_token)
    asker = await _agent_by_slug_or_404(db, payload.agent)
    origin_demand_id = None
    if payload.origin_message_number is not None:
        origin_demand_id = (
            await db.execute(select(AgentDemand.id).where(AgentDemand.number == payload.origin_message_number))
        ).scalar_one_or_none()
        if origin_demand_id is None:
            raise HTTPException(status_code=404, detail=f"No message #{payload.origin_message_number}")
    relay, chat = await agent_questions.resolve_relay(db, asker)
    now = datetime.now(timezone.utc)
    question = AgentQuestion(
        agent_id=asker.id,
        relay_agent_id=relay.id if relay else None,
        telegram_chat=chat,
        question=payload.question.strip(),
        context=(payload.context or "").strip() or None,
        recommendation=(payload.recommendation or "").strip() or None,
        blocking=payload.blocking,
        urgent=payload.urgent,
        origin_demand_id=origin_demand_id,
        notify_after=agent_questions.notify_after_for(now, payload.urgent),
    )
    db.add(question)
    await db.flush()
    db.add(
        Notification(
            source="system",
            severity="warning" if payload.urgent or payload.blocking else "info",
            title=f"Pergunta #{question.number} de {asker.name}",
            message=question.question[:500],
            event_key=f"agent-question:{question.id}",
            occurred_at=now,
        )
    )
    await db.commit()
    await db.refresh(question)
    return await _question_out(db, question)


@router.get("/agent-questions", response_model=list[QuestionOut])
async def list_agent_questions(
    agent: str,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=200),
    x_bridge_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[QuestionOut]:
    """What an agent asked (or relays). Covers both: the asker checking for
    an answer, and the relay agent finding the #number Marcelo replied to."""
    _require_bridge(x_bridge_token)
    who = await _agent_by_slug_or_404(db, agent)
    query = select(AgentQuestion).where(
        (AgentQuestion.agent_id == who.id) | (AgentQuestion.relay_agent_id == who.id)
    )
    if status_filter:
        query = query.where(AgentQuestion.status == status_filter)
    rows = await db.execute(query.order_by(AgentQuestion.number.desc()).limit(limit))
    return [await _question_out(db, q) for q in rows.scalars()]


@router.post("/agent-questions/{number}/relay-answer", response_model=QuestionOut)
async def relay_answer(
    number: int,
    payload: QuestionRelayAnswerIn,
    x_bridge_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> QuestionOut:
    """Marcelo answered in Telegram: the agent whose bot carried the question
    records it. Only that agent -- the reply exists only in its conversation,
    and any other agent "answering" would be speaking for Marcelo."""
    _require_bridge(x_bridge_token)
    relay = await _agent_by_slug_or_404(db, payload.agent)
    question = (await db.execute(select(AgentQuestion).where(AgentQuestion.number == number))).scalar_one_or_none()
    if question is None:
        raise HTTPException(status_code=404, detail=f"No question #{number}")
    if question.relay_agent_id != relay.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Question #{number} was not sent through {payload.agent!r}'s Telegram",
        )
    _assert_pending(question)
    await agent_questions.record_answer(
        db, question, payload.answer, via="telegram", by=f"marcelo (via {relay.profile_slug})"
    )
    return await _question_out(db, question)


@router.get("/questions", response_model=list[QuestionOut])
async def list_questions(
    status_filter: str | None = Query(default=None, alias="status"),
    agent_id: uuid.UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[QuestionOut]:
    query = select(AgentQuestion)
    if status_filter:
        query = query.where(AgentQuestion.status == status_filter)
    if agent_id:
        query = query.where(AgentQuestion.agent_id == agent_id)
    rows = await db.execute(query.order_by(AgentQuestion.number.desc()).limit(limit))
    return [await _question_out(db, q) for q in rows.scalars()]


async def _question_or_404(db: AsyncSession, question_id: uuid.UUID) -> AgentQuestion:
    question = await db.get(AgentQuestion, question_id)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    return question


@router.post("/questions/{question_id}:answer", response_model=QuestionOut)
async def answer_question(
    question_id: uuid.UUID,
    payload: QuestionAnswerIn,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
) -> QuestionOut:
    question = await _question_or_404(db, question_id)
    _assert_pending(question)
    await agent_questions.record_answer(
        db, question, payload.answer, via="screen", by=getattr(admin, "username", None) or "marcelo"
    )
    return await _question_out(db, question)


@router.post("/questions/{question_id}:cancel", response_model=QuestionOut)
async def cancel_question(
    question_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> QuestionOut:
    """Withdraw a question that no longer needs an answer. Kept, never deleted."""
    question = await _question_or_404(db, question_id)
    _assert_pending(question)
    question.status = "cancelled"
    await db.commit()
    await db.refresh(question)
    return await _question_out(db, question)
