"""Human-facing timestamps render in the operator's timezone, not UTC.

Storage stays UTC everywhere -- timezone-aware columns, `Z`-suffixed in the
API, converted by the browser. What these protect is the text ForgeHub
writes for a person to read: the canonical header on a dispatch result used
to print 18:56 when the operator's clock said 15:56 (2026-08-13, Marcelo:
"registrado com o fuso errado"). A timestamp that silently reads three hours
into the future is worse than none -- it can't be matched against anything
else on the machine.
"""
from datetime import datetime, timezone

from app.core.localtime import format_local, to_local


def test_a_stored_utc_instant_renders_as_local_wall_clock():
    utc = datetime(2026, 8, 13, 18, 56, 27, tzinfo=timezone.utc)
    local = to_local(utc)
    assert local.hour == 15, "America/Sao_Paulo is UTC-3"
    assert local.day == 13
    assert "15:56:27" in format_local(utc)


def test_a_naive_value_is_read_as_utc_not_as_local():
    """Every column here stores UTC. Treating a naive value as local would
    shift it the wrong way and produce a time that never happened."""
    naive = datetime(2026, 8, 13, 18, 56, 27)
    assert to_local(naive).hour == 15


def test_midnight_crossing_moves_the_date_too():
    """02:00 UTC is still the previous evening locally -- a converter that
    only shifted the clock would report the wrong day."""
    utc = datetime(2026, 8, 14, 2, 30, 0, tzinfo=timezone.utc)
    local = to_local(utc)
    assert (local.day, local.hour) == (13, 23)


def test_no_timestamp_stays_empty():
    """Absence is meaningful -- it never ran -- and must not be dressed up
    as a date."""
    assert to_local(None) is None
    assert format_local(None) == ""
