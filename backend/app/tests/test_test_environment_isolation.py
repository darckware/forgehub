"""No integration traffic from a test process (Plano Integrado T.2).

Under ENVIRONMENT=test the background loops main.py owns (dispatch to the
host-bridge, Telegram feedback, Darckware polling, ForgeRouter key sync, the
Maia's context pass, ...) must not start, whatever BACKGROUND_WORKERS_ENABLED
says, and the DEV_USER admin bootstrap is skipped (the seed owns the test
users). Pure unit tests: the lifespan's database steps are replaced, so these
run with `--noconftest` as well as inside the suite.
"""
import pytest

from app import main
from app.core.config import Settings

TEST_DB = dict(
    POSTGRES_HOST="127.0.0.1", POSTGRES_PORT=5439, POSTGRES_DB="forgehub_test", POSTGRES_USER="forgehub_test"
)


def _settings(**values) -> Settings:
    return Settings(_env_file=None, **values)


def test_background_workers_are_off_in_test_even_when_enabled():
    assert _settings(ENVIRONMENT="test", **TEST_DB).background_workers_enabled is False
    assert _settings(ENVIRONMENT=" TEST ", BACKGROUND_WORKERS_ENABLED=True, **TEST_DB).background_workers_enabled is False


def test_background_workers_default_on_outside_test_and_can_be_turned_off():
    assert _settings(ENVIRONMENT="production").background_workers_enabled is True
    assert _settings(ENVIRONMENT="development").background_workers_enabled is True
    assert _settings(ENVIRONMENT="production", BACKGROUND_WORKERS_ENABLED=False).background_workers_enabled is False


async def _run_lifespan(monkeypatch, settings_obj) -> list[str]:
    calls: list[str] = []

    def recorder(name):
        async def _step():
            calls.append(name)
        return _step

    monkeypatch.setattr(main, "settings", settings_obj)
    for step in ("_bootstrap_admin", "_recover_host_executions", "_seed_system_scripts",
                 "_start_background_tasks", "_stop_background_tasks"):
        monkeypatch.setattr(main, step, recorder(step))
    async with main.app.router.lifespan_context(main.app):
        pass
    return calls


@pytest.mark.asyncio
async def test_lifespan_starts_no_loop_and_no_admin_bootstrap_in_test(monkeypatch):
    calls = await _run_lifespan(monkeypatch, _settings(ENVIRONMENT="test", BACKGROUND_WORKERS_ENABLED=True, **TEST_DB))
    assert "_start_background_tasks" not in calls
    assert "_bootstrap_admin" not in calls
    assert calls == ["_recover_host_executions", "_seed_system_scripts", "_stop_background_tasks"]


@pytest.mark.asyncio
async def test_lifespan_still_starts_loops_in_production(monkeypatch):
    calls = await _run_lifespan(monkeypatch, _settings(ENVIRONMENT="production"))
    assert calls == [
        "_bootstrap_admin", "_recover_host_executions", "_seed_system_scripts",
        "_start_background_tasks", "_stop_background_tasks",
    ]


@pytest.mark.asyncio
async def test_real_start_is_never_reached_in_test(monkeypatch):
    """The real _start_background_tasks, not a stub: no task is created."""
    created = []
    monkeypatch.setattr(main.asyncio, "create_task", lambda *a, **k: created.append(a) or pytest.fail("loop started"))
    monkeypatch.setattr(main, "settings", _settings(ENVIRONMENT="test", **TEST_DB))
    for step in ("_bootstrap_admin", "_recover_host_executions", "_seed_system_scripts"):
        async def _noop():
            return None
        monkeypatch.setattr(main, step, _noop)
    async with main.app.router.lifespan_context(main.app):
        assert main._background_tasks == []
    assert created == []
