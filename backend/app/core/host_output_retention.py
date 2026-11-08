"""Bounded, idempotent removal of terminal machine output; audit rows remain."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.models.host_execution import HostExecution, HostExecutionResult

logger = logging.getLogger(__name__)
BATCH_SIZE = 500
POLL_SECONDS = 3600


async def run_host_output_retention(
    db: AsyncSession, *, now: datetime | None = None,
    retention_days: int | None = None, batch_size: int = BATCH_SIZE,
) -> int:
    """Commit one batch. Both parent and result must have finished before cutoff.

    Lock parent and result together so concurrent runners cannot reopen/write a
    selected execution during erasure. SKIP LOCKED lets multiple workers coexist.
    A null output plus output_expired=True differs from a run with no output.
    """
    days = retention_days if retention_days is not None else settings.HOST_OUTPUT_RETENTION_DAYS
    if days < 1 or not 1 <= batch_size <= 10_000:
        raise ValueError("Retention days and batch size must be positive (batch size <= 10000)")
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    ids = list((await db.scalars(
        select(HostExecutionResult.id)
        .join(HostExecution, HostExecution.id == HostExecutionResult.execution_id)
        .where(
            HostExecutionResult.output_expired.is_(False),
            HostExecutionResult.status.in_(("succeeded", "failed", "skipped")),
            HostExecutionResult.finished_at < cutoff,
            HostExecution.status.in_(("completed", "cancelled")),
            HostExecution.finished_at < cutoff,
        )
        .order_by(HostExecutionResult.finished_at, HostExecutionResult.id)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )).all())
    if ids:
        await db.execute(update(HostExecutionResult).where(HostExecutionResult.id.in_(ids)).values(
            stdout=None, stderr=None, output_expired=True,
            updated_at=HostExecutionResult.updated_at,
        ), execution_options={"synchronize_session": False})
    await db.commit()
    return len(ids)


async def host_output_retention_loop() -> None:
    """Own background worker; disabled in tests/when other workers are disabled."""
    if not settings.background_workers_enabled:
        return
    while True:
        count = 0
        try:
            async with AsyncSessionLocal() as db:
                count = await run_host_output_retention(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Host output retention sweep failed")
        await asyncio.sleep(0 if count == BATCH_SIZE else POLL_SECONDS)
