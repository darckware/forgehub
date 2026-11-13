"""Record actual worker progress; an alive timer cannot mask a stuck pass.

Only worker name, timestamps, policy and exception class are stored. Observer
failure must not stop operational work; the independent check then sees stale
or missing evidence. No background timer writes synthetic successful passes.
"""
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import uuid

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert

from app.db.base import AsyncSessionLocal
from app.db.models.worker_observation import WorkerObservation

logger = logging.getLogger(__name__)
WORKER_INTERVALS = {
    'scheduled-dispatch-poll': 30,
    'feedback-poll': 120,
    'routine-poll': 60,
    'mission-cycle-poll': 60,
    'machine-status-poll': 900,
}


async def _start(name: str, enabled: bool, *, starting: bool = False) -> uuid.UUID:
    if name not in WORKER_INTERVALS:
        raise ValueError('Unknown observed worker')
    run_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    values = dict(worker_name=name, enabled=enabled, interval_seconds=WORKER_INTERVALS[name],
                  active_run_id=run_id if enabled else None,
                  last_status=('starting' if starting else 'running') if enabled else 'disabled',
                  last_started_at=now, error_type=None, updated_at=now)
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(insert(WorkerObservation).values(id=uuid.uuid4(), **values)
                             .on_conflict_do_update(index_elements=['worker_name'], set_=values,
                                                    where=WorkerObservation.last_started_at <= now))
            await db.commit()
    except Exception as exc:
        logger.warning('Worker observation unavailable (%s)', type(exc).__name__)
    return run_id


async def initialize_worker_observations(*, background_enabled: bool, mission_enabled: bool) -> None:
    # Dev/test API processes may share a database with the worker owner. They
    # must not turn its observations into permanently healthy disabled rows.
    # Only a process that actually owns workers can publish worker policy.
    if not background_enabled:
        return
    for name in WORKER_INTERVALS:
        await _start(name, background_enabled and (name != 'mission-cycle-poll' or mission_enabled), starting=True)


@dataclass
class PassObservation:
    unavailable: bool = False


async def _finish(name: str, run_id: uuid.UUID, error_type: str | None) -> None:
    now = datetime.now(timezone.utc)
    values = dict(last_finished_at=now, last_status='error' if error_type else 'ok',
                  error_type=error_type, active_run_id=None, updated_at=now)
    if error_type is None:
        values['last_success_at'] = now
    try:
        async with AsyncSessionLocal() as db:
            # A late result from an older process cannot overwrite newer evidence.
            await db.execute(update(WorkerObservation).where(
                WorkerObservation.worker_name == name, WorkerObservation.active_run_id == run_id,
            ).values(**values))
            await db.commit()
    except Exception as exc:
        logger.warning('Worker observation unavailable (%s)', type(exc).__name__)


@asynccontextmanager
async def observe_worker_pass(name: str, *, enabled: bool = True):
    run_id = await _start(name, enabled)
    observation = PassObservation()
    try:
        yield observation
    except BaseException as exc:
        if enabled:
            await _finish(name, run_id, type(exc).__name__)
        raise
    else:
        if enabled:
            await _finish(name, run_id, 'SourceUnavailable' if observation.unavailable else None)
