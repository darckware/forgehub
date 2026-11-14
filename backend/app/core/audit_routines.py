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

Batches run one at a time (``_BATCH_LOCK``), so a Sunday that is also the
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


def _batch_lock() -> asyncio.Lock:
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
    """Claim one scheduled audit run and run its tier's batch to the end.
    Returns None when another pass already claimed it."""
    from app.api.routes.audit import run_audit_batch

    if not await _claim(db, run_id):
        return None
    run = await db.get(AgentRoutineRun, run_id)
    routine = await db.get(AgentRoutine, run.routine_id)
    frequency, batch_id = routine.audit_frequency, run.audit_batch_id
    async with _batch_lock():
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
    restarted mid-run): record it as failed instead of leaving it open."""
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
        if now - max(run.occurrence_at, run.updated_at) > timedelta(minutes=deadline):
            run.status, run.finished_at, run.evidence_received = "failed", now, False
            run.detail = "Lote do Auditor interrompido antes de terminar (backend reiniciado?)"
            failed += 1
    if failed:
        await db.commit()
    return failed


async def _run_in_own_session(run_id: uuid.UUID) -> None:
    from app.db.base import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            await execute_audit_run(db, run_id)
    except Exception:
        logger.exception("Audit routine run %s crashed", run_id)


def start_audit_run(run_id: uuid.UUID) -> asyncio.Task:
    """Run the batch in the background (a batch can take minutes; the
    routine loop and the run-now request must not wait for it)."""
    task = asyncio.create_task(_run_in_own_session(run_id))
    _BACKGROUND.add(task)
    task.add_done_callback(_BACKGROUND.discard)
    return task


async def drain_audit_runs() -> None:
    """Await the background batches (tests, shutdown)."""
    while _BACKGROUND:
        await asyncio.gather(*list(_BACKGROUND), return_exceptions=True)


async def run_audit_routine_pass(db: AsyncSession, *, background: bool = True) -> int:
    """Start every scheduled audit run and close interrupted ones. Returns
    how many runs were started."""
    await fail_interrupted_audit_runs(db)
    run_ids = list(
        (
            await db.execute(
                select(AgentRoutineRun.id)
                .join(AgentRoutine, AgentRoutine.id == AgentRoutineRun.routine_id)
                .where(AgentRoutine.kind == "audit", AgentRoutineRun.status == "scheduled")
                .order_by(AgentRoutineRun.occurrence_at)
            )
        ).scalars()
    )
    for run_id in run_ids:
        if background:
            start_audit_run(run_id)
        else:
            await execute_audit_run(db, run_id)
    return len(run_ids)


async def _main() -> None:
    from app.db.base import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        print(await ensure_audit_routines(db))


if __name__ == "__main__":
    asyncio.run(_main())
