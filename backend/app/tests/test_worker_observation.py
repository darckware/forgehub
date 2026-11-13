"""Progress comes from completed work, never an unrelated liveness timer."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, select

from app.core.worker_observation import initialize_worker_observations, observe_worker_pass
from app.db.base import AsyncSessionLocal
from app.db.models.worker_observation import WorkerObservation


@pytest.fixture(autouse=True)
async def clean_observations():
    async with AsyncSessionLocal() as db:
        await db.execute(delete(WorkerObservation))
        await db.commit()
    yield
    async with AsyncSessionLocal() as db:
        await db.execute(delete(WorkerObservation))
        await db.commit()


async def row(name='feedback-poll'):
    async with AsyncSessionLocal() as db:
        return (await db.scalars(select(WorkerObservation).where(WorkerObservation.worker_name == name))).one()


@pytest.mark.asyncio
async def test_starting_a_pass_does_not_forge_success():
    async with observe_worker_pass('feedback-poll'):
        current = await row()
        assert current.last_status == 'running'
        assert current.last_success_at is None
    current = await row()
    assert current.last_status == 'ok'
    assert current.last_success_at <= datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_failure_is_visible_without_storing_exception_message():
    with pytest.raises(RuntimeError):
        async with observe_worker_pass('feedback-poll'):
            raise RuntimeError('fixture exception text must not be persisted')
    current = await row()
    assert current.last_status == 'error'
    assert current.error_type == 'RuntimeError'
    assert current.last_success_at is None


@pytest.mark.asyncio
async def test_unavailable_machine_source_is_not_successful_observation():
    async with observe_worker_pass('machine-status-poll') as observation:
        observation.unavailable = True
    current = await row('machine-status-poll')
    assert current.last_status == 'error'
    assert current.error_type == 'SourceUnavailable'


@pytest.mark.asyncio
async def test_old_completion_cannot_replace_new_pass():
    async with observe_worker_pass('feedback-poll'):
        async with observe_worker_pass('feedback-poll'):
            pass
        current = await row()
        finished_at = current.last_finished_at
    assert (await row()).last_finished_at == finished_at


@pytest.mark.asyncio
async def test_disabled_feature_is_explicit_and_not_reported_as_working():
    await initialize_worker_observations(background_enabled=True, mission_enabled=False)
    current = await row('mission-cycle-poll')
    assert current.enabled is False
    assert current.last_status == 'disabled'
    assert current.last_success_at is None


@pytest.mark.asyncio
async def test_observer_failure_cannot_interrupt_operational_work(monkeypatch):
    import app.core.worker_observation as observer

    def unavailable():
        raise RuntimeError('fixture sensitive details must not be logged')

    monkeypatch.setattr(observer, 'AsyncSessionLocal', unavailable)
    worked = False
    async with observe_worker_pass('feedback-poll'):
        worked = True
    assert worked
