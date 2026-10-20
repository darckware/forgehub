"""Cron arithmetic for agent routines -- pure, no database.

Occurrences are computed in the routine's own timezone (a 08:00 briefing is
08:00 in Sao Paulo regardless of the container's clock) and returned as
timezone-aware UTC datetimes, which is what the database stores.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter

# A routine more frequent than this would turn the agent into a polling loop
# and burn its budget; the self-improvement loop can only tune within bounds.
MIN_INTERVAL_SECONDS = 15 * 60


def validate_schedule(schedule: str, tz: str) -> None:
    """Raise ValueError with a readable reason for an unusable schedule."""
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"unknown timezone: {tz}") from None
    if len(schedule.split()) != 5 or not croniter.is_valid(schedule):
        raise ValueError(f"invalid 5-field cron expression: {schedule!r}")
    probe = croniter(schedule, datetime(2026, 1, 5, tzinfo=zone))
    first, second, third = probe.get_next(datetime), probe.get_next(datetime), probe.get_next(datetime)
    if min((second - first).total_seconds(), (third - second).total_seconds()) < MIN_INTERVAL_SECONDS:
        raise ValueError("routines may not run more often than every 15 minutes")


def occurrences_between(
    schedule: str, tz: str, after: datetime, until: datetime, limit: int = 200
) -> list[datetime]:
    """Occurrences in (after, until], oldest first, at most `limit` (the most
    recent ones are kept when the window holds more)."""
    zone = ZoneInfo(tz)
    it = croniter(schedule, after.astimezone(zone))
    found: list[datetime] = []
    while True:
        nxt = it.get_next(datetime)
        if nxt > until.astimezone(zone):
            break
        found.append(nxt.astimezone(timezone.utc))
        if len(found) > limit:
            found.pop(0)
    return found


def next_occurrences(schedule: str, tz: str, start: datetime, count: int = 5) -> list[datetime]:
    zone = ZoneInfo(tz)
    it = croniter(schedule, start.astimezone(zone))
    return [it.get_next(datetime).astimezone(timezone.utc) for _ in range(count)]


def local_day_bounds(moment: datetime, tz: str) -> tuple[datetime, datetime]:
    """[start, end) of the calendar day containing `moment` in `tz`, in UTC --
    the window a daily budget is counted over."""
    zone = ZoneInfo(tz)
    local = moment.astimezone(zone)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    end = croniter("0 0 * * *", start).get_next(datetime)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)
