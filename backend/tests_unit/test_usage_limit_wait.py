"""A run that ended on a usage limit: who waits for the reset, and how.

No database: run with ``pytest --noconftest``. `_finalize_dispatch` and the
scheduled pass run for real against a small fake session, so the parser,
`record_usage_limit`, the decision and the row's final state are all real. The
SQL due filter and `reserve_dispatch` are covered in
``app/tests/test_agent_failover.py``.
"""
import os

os.environ.setdefault("ENVIRONMENT", "test")

import uuid  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

import pytest  # noqa: E402

from app.api.routes import demand as demand_routes  # noqa: E402
from app.core import demand_failure_check  # noqa: E402
from app.core.agent_availability import HOST_TIMEZONE, RESCHEDULE_MARGIN, describe_reset  # noqa: E402
from app.core.agent_failover import can_switch, can_wait_for_reset  # noqa: E402
from app.db.models.agent import Agent  # noqa: E402
from app.db.models.mission_cycle import AgentAvailability  # noqa: E402
from app.db.models.notification import Notification  # noqa: E402

GENERIC = "The agent run ended as 'failed'."
ZONE = ZoneInfo(HOST_TIMEZONE)


class _Rows:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def scalar_one_or_none(self):
        return self.rows[0] if self.rows else None

    def scalars(self):
        return SimpleNamespace(all=lambda: self.rows, first=lambda: self.rows[0] if self.rows else None)


class FakeSession:
    """Answers the first SELECT with `rows`, and nothing after it."""

    def __init__(self, rows, agent):
        self.rows, self.agent, self.added, self.commits = list(rows), agent, [], 0

    async def execute(self, _statement):
        rows, self.rows = self.rows, []
        return _Rows(rows)

    async def get(self, model, _id):
        return self.agent if model is Agent else None

    async def scalar(self, _statement):
        return None

    async def scalars(self, _statement):
        # No dispatch credential is stored by this in-memory test session.
        return SimpleNamespace(all=lambda: [])

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        return None

    def add(self, row):
        self.added.append(row)

    def of(self, kind):
        return [row for row in self.added if isinstance(row, kind)]


def _row(agent, **fields):
    base = dict(
        id=uuid.uuid4(), number=42000, subject="Revisão", status="new", origin_type="task", origin_id=None,
        target_agent_id=agent.id, from_agent_id=None, from_agent="teste", body="corpo", command_text=None,
        agent_run_id="run-1", dispatch_status="running", dispatch_error=None, dispatch_attempts=1, retry_limit=None,
        dispatch_deadline_at=datetime.now(timezone.utc), scheduled_at=None, consolidated_into_id=None,
        fixed_agent=False, requires_approval=False, task_execution_id=None, mission_context_version_id=None,
        failure_check_source_id=None, requires_response=False, task_execution_at=None, dispatch_result=None,
    )
    return SimpleNamespace(**{**base, **fields})


def _limited_run(hours=2):
    """A failed run whose limit resets `hours` ahead, as the bridge reports it."""
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    reset = now + timedelta(hours=hours)
    clock = reset.astimezone(ZONE).strftime("%I:%M %p")
    return {"run_id": "run-1", "status": "failed", "output": f"You've hit your usage limit. try again at {clock}.",
            "finished_at": now.astimezone(ZONE).replace(tzinfo=None).isoformat()}, reset


@pytest.fixture
def agent():
    return SimpleNamespace(id=uuid.uuid4(), name="Aramis", runtime_type="codex")


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    """Keeps the failed path's side effects out, and records the checks it opens."""
    opened = []

    async def no_check(_db, demand_id):
        opened.append(demand_id)

    async def no_feedback(_db, _demand):
        return False

    monkeypatch.setattr(demand_failure_check, "ensure_failure_check", no_check)
    monkeypatch.setattr(demand_routes, "deliver_feedback", no_feedback)
    monkeypatch.setattr("app.core.feedback.deliver_feedback", no_feedback)
    monkeypatch.setattr("app.core.dispatch_signal.wake_scheduled_dispatch", lambda: None)
    monkeypatch.setattr("app.core.demand_workflow.record_transition", lambda *a, **k: None)
    return opened


async def _finish(agent, row, run):
    db = FakeSession([row], agent)
    await demand_routes._finalize_dispatch(db, row.id, run)
    return db


@pytest.mark.parametrize("field,waits", [
    ({"fixed_agent": True}, True),
    ({"failure_check_source_id": uuid.uuid4()}, True),
    ({"requires_approval": True}, False),
    ({"task_execution_id": uuid.uuid4()}, False),
    ({"mission_context_version_id": uuid.uuid4()}, False),
    ({"fixed_agent": True, "requires_approval": True}, False),
    ({"fixed_agent": True, "task_execution_id": uuid.uuid4()}, False),
])
def test_who_waits_for_the_reset(field, waits):
    base = dict(fixed_agent=False, requires_approval=False, task_execution_id=None,
                mission_context_version_id=None, failure_check_source_id=None)
    assert can_wait_for_reset(SimpleNamespace(**{**base, **field})) is waits
    assert can_switch(SimpleNamespace(**{**base, **field})) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("field", [{"fixed_agent": True}, {"failure_check_source_id": uuid.uuid4()}])
async def test_kept_work_goes_back_to_the_queue_until_the_reset(agent, quiet, field):
    run, reset = _limited_run()
    row = _row(agent, **field)
    db = await _finish(agent, row, run)

    assert row.dispatch_status is None and row.agent_run_id is None and row.dispatch_deadline_at is None
    assert row.target_agent_id == agent.id
    assert row.scheduled_at == reset + RESCHEDULE_MARGIN
    assert row.dispatch_attempts == 1
    assert describe_reset(reset) in row.dispatch_error
    assert "uncertain" not in row.dispatch_error.lower()
    [marked] = db.of(AgentAvailability)
    assert marked.unavailable_until == reset
    [notice] = db.of(Notification)
    assert notice.severity == "warning" and describe_reset(reset) in notice.message
    assert quiet == [] and db.commits == 1


@pytest.mark.asyncio
async def test_a_plain_message_stays_due_now_for_the_failover(agent):
    run, reset = _limited_run()
    row = _row(agent)
    before = datetime.now(timezone.utc)
    db = await _finish(agent, row, run)

    assert row.dispatch_status is None and row.dispatch_error is None
    assert before <= row.scheduled_at < reset
    assert db.of(Notification) == []


@pytest.mark.asyncio
async def test_a_reconciled_limit_is_held_by_the_date_alone(agent):
    """A reconciliation writes no unavailability, so only the schedule stops an
    early run."""
    run, reset = _limited_run()
    row = _row(agent, fixed_agent=True)
    db = FakeSession([row], agent)
    await demand_routes._finalize_dispatch(db, row.id, run, reconciling=True)
    assert db.of(AgentAvailability) == []
    assert row.dispatch_status is None and row.scheduled_at == reset + RESCHEDULE_MARGIN


@pytest.mark.asyncio
async def test_a_reset_already_past_is_due_at_once(agent):
    run, reset = _limited_run(hours=-1)
    run["finished_at"] = (reset - timedelta(hours=1)).astimezone(ZONE).replace(tzinfo=None).isoformat()
    row = _row(agent, fixed_agent=True)
    before = datetime.now(timezone.utc)
    await _finish(agent, row, run)
    assert row.dispatch_status is None and row.scheduled_at >= before


@pytest.mark.asyncio
async def test_no_attempts_left_fails_and_names_the_limit(agent, quiet):
    run, reset = _limited_run()
    row = _row(agent, fixed_agent=True, dispatch_attempts=3)
    await _finish(agent, row, run)
    assert row.dispatch_status == "failed"
    assert row.dispatch_error == f"{GENERIC} Usage limit reached; it resets at {describe_reset(reset)}."
    assert quiet == [row.id]


@pytest.mark.asyncio
@pytest.mark.parametrize("field", [{"requires_approval": True}, {"mission_context_version_id": uuid.uuid4()}])
async def test_work_that_cannot_wait_fails_and_names_the_limit(agent, field):
    run, reset = _limited_run()
    row = _row(agent, fixed_agent=True, **field)
    db = await _finish(agent, row, run)
    assert row.dispatch_status == "failed"
    assert describe_reset(reset) in row.dispatch_error
    [notice] = db.of(Notification)
    assert notice.severity == "error" and describe_reset(reset) in notice.message


@pytest.mark.asyncio
async def test_a_run_without_a_limit_stays_a_plain_failure(agent):
    row = _row(agent, fixed_agent=True)
    await _finish(agent, row, {"run_id": "run-1", "status": "failed", "output": "exit 1: segmentation fault"})
    assert row.dispatch_status == "failed" and row.dispatch_error == GENERIC


@pytest.mark.asyncio
async def test_a_limit_with_no_reset_says_so(agent):
    row = _row(agent, fixed_agent=True)
    await _finish(agent, row, {"run_id": "run-1", "status": "failed", "output": "Individual quota reached."})
    assert row.dispatch_status == "failed"
    assert row.dispatch_error == f"{GENERIC} The run reported a usage limit, with no reset time recognised."


@pytest.mark.asyncio
async def test_the_pass_skips_a_waiting_agent_and_runs_it_after_the_reset(agent, monkeypatch):
    other = SimpleNamespace(id=uuid.uuid4(), name="Dartan", runtime_type="agy")
    row = _row(agent, fixed_agent=True, dispatch_status=None, agent_run_id=None,
               scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    started, until = [], {agent.id: datetime.now(timezone.utc) + timedelta(hours=1)}

    async def slots(_db):
        return 5

    async def nobody(_db):
        return set()

    async def unavailable(_db):
        return until

    async def priorities(_db, _due):
        return {}

    async def allowed(*_args):
        return None

    async def substitute(*_args):
        raise AssertionError("a fixed_agent message never looks for another agent")

    async def execute(_db, demand, target, _command):
        started.append(target)
        demand.dispatch_status = "dispatched"
        demand.dispatch_attempts += 1

    for name, value in (("_dispatch_slots", slots), ("_agents_already_running", nobody),
                        ("ensure_workflow_allowed", allowed), ("ensure_task_dispatch_admissible", allowed),
                        ("_ensure_demand_dependencies_satisfied", allowed), ("_execute_dispatch", execute)):
        monkeypatch.setattr(demand_routes, name, value)
    monkeypatch.setattr("app.core.agent_availability.unavailable_agents", unavailable)
    monkeypatch.setattr("app.core.mission_cycle.effective_priorities", priorities)
    monkeypatch.setattr("app.core.agent_failover.substitute_for", substitute)

    class Pass(FakeSession):
        async def get(self, model, _id):
            return row

    for _ in range(3):
        await demand_routes.run_scheduled_dispatch_pass(Pass([row], other))
    assert started == [] and row.dispatch_attempts == 1 and row.target_agent_id == agent.id

    until.clear()
    await demand_routes.run_scheduled_dispatch_pass(Pass([row], other))
    assert started == [agent.id] and row.dispatch_attempts == 2
