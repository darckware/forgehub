"""Recurring exceptions remain attached to their original service occurrence."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import uuid

import pytest

from app.core.agent_activity_routines import classify_occurrences, routine_missed_incidents


@pytest.mark.parametrize("status,kind", [
    ("failed", "routine_failed"),
    ("skipped_budget", "routine_skipped_budget"),
    ("missed", "routine_missed"),
])
def test_later_success_keeps_original_occurrence_exception(status, kind):
    now = datetime(2026, 11, 11, 15, tzinfo=timezone.utc)
    agent = SimpleNamespace(id=uuid.uuid4(), name="Service owner", runtime_type="claude")
    routine = SimpleNamespace(id=uuid.uuid4(), agent_id=agent.id, title="Service check",
        kind="check", timezone="UTC", deadline_minutes=30, enabled=False)
    failed_at = now - timedelta(hours=2)
    failed_id = uuid.uuid4()
    failed_message_id = uuid.uuid4()
    def run(at, state, **extra):
        return SimpleNamespace(id=extra.get("id", uuid.uuid4()), routine_id=routine.id,
            occurrence_at=at, status=state, detail="original service obligation",
            finished_at=at, duration_ms=10, demand_id=extra.get("demand_id"))
    original = run(failed_at, status, id=failed_id, demand_id=failed_message_id)
    later = run(now - timedelta(hours=1), "completed")
    items = classify_occurrences([routine], [(original, None), (later, None)],
        start=now - timedelta(hours=3), end=now, now=now, horizon=now)
    incidents = routine_missed_incidents(items, {agent.id: agent}, now=now)
    assert len(incidents) == 1
    incident = incidents[0]
    assert incident.kind == kind
    assert incident.occurred_at == failed_at
    assert incident.source_id == routine.id
    assert "original service obligation" in incident.summary
    assert incident.canonical_path == f"/demands?message={failed_message_id}"
    assert [(link.source_type, link.source_id, link.canonical_path) for link in incident.related_records] == [
        ("agent_routine_run", failed_id, f"/demands?message={failed_message_id}"),
    ]
    assert "service acceptance" in incident.summary.lower()


def test_budget_skip_is_actionable_only_when_original_deadline_has_passed():
    now = datetime(2026, 11, 11, 15, tzinfo=timezone.utc)
    routine = SimpleNamespace(id=uuid.uuid4(), agent_id=uuid.uuid4(), title="Service check",
        kind="check", timezone="UTC", deadline_minutes=30, enabled=False)
    run = SimpleNamespace(id=uuid.uuid4(), routine_id=routine.id, occurrence_at=now,
        status="skipped_budget", detail="daily run budget reached", finished_at=now,
        duration_ms=None, demand_id=None)
    items = classify_occurrences([routine], [(run, None)], start=now, end=now,
        now=now, horizon=now)
    assert routine_missed_incidents(items, {}, now=now) == []
    incidents = routine_missed_incidents(items, {}, now=now + timedelta(minutes=31))
    assert len(incidents) == 1
    assert incidents[0].kind == "routine_skipped_budget"


@pytest.mark.parametrize("dispatch_status,expected", [("failed", "failed"), ("completed", "done")])
def test_running_occurrence_uses_terminal_message_outcome_before_sync(dispatch_status, expected):
    now = datetime(2026, 11, 11, 15, tzinfo=timezone.utc)
    routine = SimpleNamespace(id=uuid.uuid4(), agent_id=uuid.uuid4(), title="Service check",
        kind="check", timezone="UTC", deadline_minutes=30, enabled=False)
    run = SimpleNamespace(id=uuid.uuid4(), routine_id=routine.id, occurrence_at=now,
        status="running", detail=None, finished_at=None, duration_ms=None, demand_id=uuid.uuid4())
    demand = SimpleNamespace(dispatch_status=dispatch_status, dispatch_error="service failed", number=42)
    items = classify_occurrences([routine], [(run, demand)], start=now, end=now,
        now=now, horizon=now)
    assert items[0].outcome == expected
    if expected == "failed":
        assert items[0].detail == "service failed"
