"""Realizado on an agenda event: a one-off becomes done, a recurring one moves on."""
from datetime import datetime

from app.api.routes.personal import _complete_event
from app.db.models.personal import PersonalEvent


def _event(**kw) -> PersonalEvent:
    return PersonalEvent(title="nutricionista", starts_at=datetime(2026, 10, 16, 11, 30), status="scheduled",
                         recurrence="", reminders_sent=["x"], **kw)


def test_one_off_event_is_done():
    event = _event()
    _complete_event(event)
    assert event.status == "done"
    assert event.starts_at == datetime(2026, 10, 16, 11, 30)


def test_recurring_event_moves_to_next_occurrence_with_its_duration():
    event = _event(ends_at=datetime(2026, 10, 16, 12, 30))
    event.recurrence = "weekly"
    _complete_event(event)
    assert event.status == "scheduled"
    assert event.starts_at == datetime(2026, 10, 23, 11, 30)
    assert event.ends_at == datetime(2026, 10, 23, 12, 30)
    assert event.reminders_sent == []
