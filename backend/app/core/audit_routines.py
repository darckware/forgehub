"""Auditor tiers as Operação 24x7 routines (2026-11-13, Marcelo).

Each frequency of ``audit_checks.frequency`` is one ``AgentRoutine`` with
``kind="audit"`` owned by Athos. Unlike every other routine, its occurrence
is *not* a Messages task: running checks is deterministic host work that the
Auditor runner already does (``run_audit_batch``), so putting an LLM between
the schedule and the checks would only add cost and a way to fail. The
occurrence becomes an ``AgentRoutineRun`` whose ``audit_batch_id`` names the
batch before it starts; the batch is its evidence.

Lifecycle of an audit run:
  scheduled  (generator, or run-now)          -- audit_batch_id assigned
  running    (claimed by one pass, atomically) -- the batch is executing
  completed  the batch ran; evidence_received = every enabled check of the
             tier has a result in it (a failing check is still evidence --
             the Auditor opens its owner's incident task, as before)
  failed     the batch could not run, or it was interrupted (a running run
             older than its deadline: the backend restarted mid-batch)

Every failed or missed audit run raises a warning Notification; a monthly or
quarterly one gets one retry an hour later (``retry_of_run_id``), because
its evidence would otherwise stay stale for a whole period.

Batches run one at a time (``audit_batch_lock``, also taken by the manual
"run checklist"), so a Sunday that is also the
1st of a quarter runs daily, weekly, monthly and quarterly in sequence
rather than four batches against the bridge at once.

The four routines are created by ``ensure_audit_routines`` (CLI below), not
by a migration: they hang off the Athos agent row, which is data. They are
created **disabled**, so nothing runs until the activation plan
(docs/runbooks/auditor-frequencies.md) turns them on.
"""
import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent import Agent
from app.db.models.audit import AuditCheck
from app.db.models.operations import AgentRoutine, AgentRoutineRun

logger = logging.getLogger(__name__)

OWNER_SLUG = "athos"
TIMEZONE = "America/Sao_Paulo"
REQUESTED_BY = "routine"


@dataclass(frozen=True)
class AuditTier:
    frequency: str
    title: str
    schedule: str
    deadline_minutes: int


TIERS = (
    AuditTier("daily", "Auditoria diária", "0 19 * * *", 120),
    AuditTier("weekly", "Auditoria semanal", "0 19 * * 0", 120),
    AuditTier("monthly", "Auditoria mensal", "0 19 1 * *", 180),
    AuditTier("quarterly", "Auditoria trimestral", "0 19 1 1,4,7,10 *", 180),
)
TIER_BY_FREQUENCY = {tier.frequency: tier for tier in TIERS}

_INSTRUCTIONS = (
    "Executa, pelo runner do Auditor (sem LLM), todos os checks habilitados de frequência "
    "'{frequency}' como um único lote. Checks que falham abrem a Task de correção do dono, "
    "como antes. A frequência de cada check é editada na tela Auditor."
)
_EVIDENCE = "O lote do Auditor (audit_check_runs.batch_id) com um resultado para cada check habilitado da faixa."


def tier_routine_values(tier: AuditTier, agent_id: uuid.UUID) -> dict:
    return dict(
        agent_id=agent_id,
        title=tier.title,
        instructions=_INSTRUCTIONS.format(frequency=tier.frequency),
        schedule=tier.schedule,
        timezone=TIMEZONE,
        kind="audit",
        audit_frequency=tier.frequency,
        expected_evidence=_EVIDENCE,
        linked_audit_checks=[],
        enabled=False,
        deadline_minutes=tier.deadline_minutes,
        created_by="seed:auditor-frequencies",
        updated_by="seed:auditor-frequencies",
    )


async def ensure_audit_routines(db: AsyncSession, owner: Agent | None = None) -> dict:
    """Create each missing tier routine, disabled. Idempotent: a tier that
    already has a routine is left exactly as it is (the screen owns it)."""
    if owner is None:
        owner = (await db.execute(select(Agent).where(Agent.profile_slug == OWNER_SLUG))).scalar_one_or_none()
    if owner is None:
        return {"created": [], "existing": [], "error": f"agent '{OWNER_SLUG}' not found"}
    existing = set(
        (await db.execute(select(AgentRoutine.audit_frequency).where(AgentRoutine.kind == "audit"))).scalars()
    )
    created = []
    for tier in TIERS:
        if tier.frequency in existing:
            continue
        db.add(AgentRoutine(**tier_routine_values(tier, owner.id)))
        created.append(tier.frequency)
    await db.commit()
    return {"created": created, "existing": sorted(existing), "error": None}


# ---------------------------------------------------------------- execution


def new_audit_run(routine: AgentRoutine, occurrence_at: datetime) -> AgentRoutineRun:
    """The run an audit occurrence becomes: no Messages task, a named batch."""
    return AgentRoutineRun(
        routine_id=routine.id,
        occurrence_at=occurrence_at,
        status="scheduled",
        audit_batch_id=uuid.uuid4(),
        detail="Lote do Auditor aguardando execução",
    )


_BATCH_LOCKS: dict[int, asyncio.Lock] = {}
_BACKGROUND: set[asyncio.Task] = set()
# Runs that already have a background task waiting for the lock, so the
# 60-second pass doesn't queue a second task for the same run.
_STARTED: set[uuid.UUID] = set()
# Monthly and quarterly evidence is valid for 32/93 days: a lost occurrence
# would leave the tier stale for a whole period, so it gets one retry.
RETRIED_FREQUENCIES = ("monthly", "quarterly")
RETRY_DELAY = timedelta(hours=1)
# Failed/missed runs older than this are not swept again (notified once).
_SWEEP_WINDOW = timedelta(days=7)


def audit_batch_lock() -> asyncio.Lock:
    """One Auditor batch at a time in this process: routine tiers and the
    manual "run checklist" (audit.py) all take it."""
    loop = asyncio.get_running_loop()
    return _BATCH_LOCKS.setdefault(id(loop), asyncio.Lock())


async def _claim(db: AsyncSession, run_id: uuid.UUID) -> bool:
    claimed = await db.execute(
        update(AgentRoutineRun)
        .where(AgentRoutineRun.id == run_id, AgentRoutineRun.status == "scheduled")
        .values(status="running", detail="Lote do Auditor em execução")
    )
    await db.commit()
    return claimed.rowcount == 1


async def execute_audit_run(db: AsyncSession, run_id: uuid.UUID) -> AgentRoutineRun | None:
    """Wait for the batch lock, then claim one scheduled audit run and run its
    tier's batch to the end. The run turns "running" only once the lock is
    held, so a tier waiting behind another is never mistaken for an
    interrupted batch. Returns None when another pass already claimed it."""
    from app.api.routes.audit import run_audit_batch

    async with audit_batch_lock():
        if not await _claim(db, run_id):
            return None
        run = await db.get(AgentRoutineRun, run_id)
        await db.refresh(run)
        routine = await db.get(AgentRoutine, run.routine_id)
        frequency, batch_id = routine.audit_frequency, run.audit_batch_id
        started = datetime.now(timezone.utc)
        expected = (
            await db.execute(
                select(func.count(AuditCheck.id)).where(
                    AuditCheck.enabled.is_(True), AuditCheck.frequency == frequency
                )
            )
        ).scalar_one()
        try:
            results = await run_audit_batch(db, frequency, REQUESTED_BY, batch_id=batch_id)
            error = None
        except Exception as exc:  # the run records it; the loop must go on
            logger.exception("Audit routine run %s failed", run_id)
            await db.rollback()
            results, error = [], f"{type(exc).__name__}: {exc}"
    run = await db.get(AgentRoutineRun, run_id)
    await db.refresh(run)
    finished = datetime.now(timezone.utc)
    run.finished_at = finished
    run.duration_ms = round((finished - started).total_seconds() * 1000)
    run.cost_usd = Decimal("0")  # no LLM in this path: the cost is known to be zero
    if error is not None:
        run.status, run.detail, run.evidence_received = "failed", f"Lote não executado: {error}"[:2000], False
    else:
        names = {check.id: check.name for check in (await db.execute(select(AuditCheck))).scalars()}
        failing = sorted(names.get(r.check_id, str(r.check_id)) for r in results if r.status != "ok")
        ok = len(results) - len(failing)
        run.status = "completed"
        run.evidence_received = len(results) > 0 and len(results) >= expected
        run.no_action = expected == 0 or not failing
        run.detail = (
            f"Lote {batch_id}: {ok}/{len(results)} ok"
            + (f"; falharam: {', '.join(failing)}" if failing else "")
            + ("" if expected else "; nenhum check habilitado nesta faixa")
        )[:2000]
    await db.commit()
    return run


async def fail_interrupted_audit_runs(db: AsyncSession, now: datetime | None = None) -> int:
    """A running audit run past its deadline lost its batch (the backend
    restarted mid-run): record it as failed instead of leaving it open. The
    deadline counts from when the run was claimed (``updated_at``), which
    happens only after the batch lock was acquired."""
    now = now or datetime.now(timezone.utc)
    rows = (
        await db.execute(
            select(AgentRoutineRun, AgentRoutine.deadline_minutes)
            .join(AgentRoutine, AgentRoutine.id == AgentRoutineRun.routine_id)
            .where(AgentRoutine.kind == "audit", AgentRoutineRun.status == "running")
        )
    ).all()
    failed = 0
    for run, deadline in rows:
        if run.id in _STARTED:
            continue  # its batch is still running in this process
        if now - max(run.occurrence_at, run.updated_at) > timedelta(minutes=deadline):
            run.status, run.finished_at, run.evidence_received = "failed", now, False
            run.detail = "Lote do Auditor interrompido antes de terminar (backend reiniciado?)"
            failed += 1
    if failed:
        await db.commit()
    return failed


async def handle_lost_audit_runs(db: AsyncSession, now: datetime | None = None) -> dict:
    """Every failed or missed audit run raises one warning Notification
    (deduplicated by event_key). A monthly or quarterly one that is not
    itself a retry also gets one retry occurrence ``RETRY_DELAY`` later."""
    from app.db.models.notification import Notification

    now = now or datetime.now(timezone.utc)
    rows = (
        await db.execute(
            select(AgentRoutineRun, AgentRoutine)
            .join(AgentRoutine, AgentRoutine.id == AgentRoutineRun.routine_id)
            .where(
                AgentRoutine.kind == "audit",
                AgentRoutineRun.status.in_(("failed", "missed")),
                AgentRoutineRun.occurrence_at >= now - _SWEEP_WINDOW,
            )
        )
    ).all()
    retried = {
        retry_of
        for retry_of in (
            await db.execute(select(AgentRoutineRun.retry_of_run_id).where(AgentRoutineRun.retry_of_run_id.is_not(None)))
        ).scalars()
    }
    notified = retries = 0
    for run, routine in rows:
        event_key = f"audit-routine-run:{run.id}"
        if (await db.execute(select(Notification.id).where(Notification.event_key == event_key))).first() is None:
            will_retry = (
                routine.enabled and routine.audit_frequency in RETRIED_FREQUENCIES
                and run.retry_of_run_id is None and run.id not in retried
            )
            db.add(Notification(
                source="system", severity="warning",
                title=f"Auditoria {routine.audit_frequency} não concluída: {run.status}"[:255],
                message=(
                    f"{routine.title}, ocorrência {run.occurrence_at:%Y-%m-%d %H:%M} UTC: {run.detail or run.status}. "
                    + ("Uma nova tentativa foi agendada para daqui a 1 hora."
                       if will_retry else "Execute a faixa no Auditor ou em Operação 24x7 → Executar agora.")
                )[:4000],
                event_key=event_key, occurred_at=now,
            ))
            notified += 1
        if (routine.enabled and routine.audit_frequency in RETRIED_FREQUENCIES
                and run.retry_of_run_id is None and run.id not in retried):
            retry = new_audit_run(routine, now + RETRY_DELAY)
            retry.retry_of_run_id = run.id
            retry.detail = f"Nova tentativa da ocorrência de {run.occurrence_at:%Y-%m-%d %H:%M} UTC"
            db.add(retry)
            retried.add(run.id)
            retries += 1
    if notified or retries:
        await db.commit()
    return {"notified": notified, "retries": retries}


async def _run_in_own_session(run_id: uuid.UUID) -> None:
    from app.db.base import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            await execute_audit_run(db, run_id)
    except Exception:
        logger.exception("Audit routine run %s crashed", run_id)
    finally:
        _STARTED.discard(run_id)


def start_audit_run(run_id: uuid.UUID) -> asyncio.Task | None:
    """Run the batch in the background (a batch can take minutes; the
    routine loop and the run-now request must not wait for it). None when
    this run already has a task."""
    if run_id in _STARTED:
        return None
    _STARTED.add(run_id)
    task = asyncio.create_task(_run_in_own_session(run_id))
    _BACKGROUND.add(task)
    task.add_done_callback(_BACKGROUND.discard)
    return task


async def drain_audit_runs() -> None:
    """Await the background batches (tests, shutdown)."""
    while _BACKGROUND:
        await asyncio.gather(*list(_BACKGROUND), return_exceptions=True)


async def run_audit_routine_pass(db: AsyncSession, *, background: bool = True, now: datetime | None = None) -> int:
    """Close interrupted runs, notify and retry lost ones, then start every
    due scheduled audit run (a retry waits for its own time). Returns how
    many runs were started."""
    now = now or datetime.now(timezone.utc)
    await fail_interrupted_audit_runs(db, now)
    await handle_lost_audit_runs(db, now)
    run_ids = list(
        (
            await db.execute(
                select(AgentRoutineRun.id)
                .join(AgentRoutine, AgentRoutine.id == AgentRoutineRun.routine_id)
                .where(
                    AgentRoutine.kind == "audit",
                    AgentRoutineRun.status == "scheduled",
                    AgentRoutineRun.occurrence_at <= now,
                )
                .order_by(AgentRoutineRun.occurrence_at)
            )
        ).scalars()
    )
    started = 0
    for run_id in run_ids:
        if background:
            started += start_audit_run(run_id) is not None
        elif await execute_audit_run(db, run_id) is not None:
            started += 1
    return started


async def _main() -> None:
    from app.db.base import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        print(await ensure_audit_routines(db))


if __name__ == "__main__":
    asyncio.run(_main())
