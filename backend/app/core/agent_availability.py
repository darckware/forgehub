"""Executor availability: usage-limit patterns and infrastructure failures (M0.8).

Contract: docs/architecture/MISSION_ORCHESTRATOR_CYCLE_SPEC.md §3.3 and §3.4
item 3.

- ``parse_usage_limit(runtime, text, now)`` turns a runtime's own usage-limit
  message into the time it resets, or ``None``. Only deterministic, versioned
  patterns: no match, no guess, nothing written. A reset given as a clock time
  is the next such time after ``now`` in the timezone the message names, else
  the host's (``HOST_TIMEZONE``).
- ``record_usage_limit`` stores it in ``agent_availability`` from a finished
  run (called by ``_finalize_dispatch``/``_fail_dispatch``).
- ``unavailable_agents``/``unavailable_until`` are what ``reserve_dispatch``
  and the scheduled pass read: the agent is busy until then
  (``AGENT_UNAVAILABLE``, the item stays queued).
- ``classify_infra_failure`` tells a runtime/infrastructure failure (quota,
  provider 4xx/5xx, permission auto-denied, timeout without output) from a
  real failure of the work: the cycle reprocesses/reschedules/reassigns the
  former and never counts it as a rejection or as the executor's failure.

Patterns (version ``PATTERNS_VERSION``), with the outputs they come from:
- Claude Code: ``You've hit your 5-hour limit · resets 2:30pm (America/Sao_Paulo)``
  (run #41798, 2026-10-30) and ``... · resets 3:30am`` (2026-10-28); the older
  ``Claude AI usage limit reached|<epoch seconds>``.
- Codex: ``You've hit your usage limit. ... try again in 2 hours 13 minutes.``
  and ``... try again at 3:39 PM.`` (Codex CLI's message format).
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent import Agent
from app.db.models.mission_cycle import AgentAvailability

PATTERNS_VERSION = "2026-10-30.1"
HOST_TIMEZONE = "America/Sao_Paulo"
# The cycle schedules an unavailable executor's work this long after the reset.
RESCHEDULE_MARGIN = timedelta(minutes=5)

_MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}

_CLAUDE_RESETS = re.compile(
    r"you['’]ve hit your [\w -]{0,40}?limit\s*[·•\-–|]\s*resets\s+"
    r"(?:(?P<month>[A-Za-z]{3})[a-z]*\.?\s+(?P<day>\d{1,2}),?\s+(?:at\s+)?)?"
    r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)"
    r"(?:\s*\((?P<tz>[^)\n]{1,60})\))?",
    re.IGNORECASE,
)
_CLAUDE_EPOCH = re.compile(r"Claude AI usage limit reached\|(?P<epoch>\d{10})\b")
_CODEX_IN = re.compile(
    r"you['’]ve hit your usage limit\b.{0,200}?try again in\s+"
    r"(?:(?P<days>\d+)\s+days?\s*)?(?:(?P<hours>\d+)\s+hours?\s*)?(?:(?P<minutes>\d+)\s+minutes?)?",
    re.IGNORECASE | re.DOTALL,
)
_CODEX_AT = re.compile(
    r"you['’]ve hit your usage limit\b.{0,200}?try again at\s+"
    r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)",
    re.IGNORECASE | re.DOTALL,
)

# §3.4 item 3: runtime/infrastructure failures, never the work's own failure.
_INFRA_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("usage_limit", re.compile(
        r"you['’]ve hit your [\w -]{0,40}?limit|usage limit reached|rate[ _-]?limit(?:ed| exceeded)|"
        r"quota (?:exceeded|exhausted)|RESOURCE_EXHAUSTED", re.IGNORECASE)),
    ("provider_error", re.compile(
        r"\bINVALID_ARGUMENT\b|\boverloaded_error\b|\bapi_error\b|\bAPI Error:\s*[45]\d\d\b|"
        r"\b(?:HTTP|status(?: code)?)[ :]*(?:429|5\d\d)\b|internal server error|service unavailable|"
        r"bad gateway|\bUNAVAILABLE\b", re.IGNORECASE)),
    ("permission_denied", re.compile(
        r"permission (?:was )?(?:auto-?)?denied|requires? (?:your )?(?:approval|permission) to|"
        r"not allowed to (?:run|use) this tool|tool use was denied", re.IGNORECASE)),
)


def _zone(name: str | None) -> ZoneInfo | None:
    """The named zone, the host's when none is named, None when the name is
    not a zone (then there is no match: a wrong zone is a wrong time)."""
    try:
        return ZoneInfo(name.strip()) if name else ZoneInfo(HOST_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def _hour24(hour: int, ampm: str) -> int | None:
    if not 1 <= hour <= 12:
        return None
    return (hour % 12) + (12 if ampm.lower() == "pm" else 0)


def _next_clock(now: datetime, tz: ZoneInfo, hour: int, minute: int,
                month: int | None = None, day: int | None = None) -> datetime | None:
    local_now = now.astimezone(tz)
    try:
        if month is not None and day is not None:
            candidate = local_now.replace(month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)
            if candidate <= local_now:
                candidate = candidate.replace(year=candidate.year + 1)
            return candidate.astimezone(timezone.utc)
        candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    except ValueError:
        return None
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)


def parse_usage_limit(runtime: str | None, text: str | None, now: datetime) -> datetime | None:
    """The reset time a runtime's usage-limit message announces, or None."""
    if not text:
        return None
    runtime = (runtime or "").lower()
    if runtime in ("claude", ""):
        match = _CLAUDE_RESETS.search(text)
        if match:
            hour = _hour24(int(match["hour"]), match["ampm"])
            minute = int(match["minute"] or 0)
            month = _MONTHS.get((match["month"] or "").lower()[:3]) if match["month"] else None
            if hour is None or minute > 59 or (match["month"] and month is None):
                return None
            day = int(match["day"]) if match["day"] else None
            zone = _zone(match["tz"])
            return _next_clock(now, zone, hour, minute, month, day) if zone is not None else None
        match = _CLAUDE_EPOCH.search(text)
        if match:
            value = datetime.fromtimestamp(int(match["epoch"]), tz=timezone.utc)
            return value if value > now else None
    if runtime in ("codex", ""):
        match = _CODEX_IN.search(text)
        if match and any(match[g] for g in ("days", "hours", "minutes")):
            return now + timedelta(days=int(match["days"] or 0), hours=int(match["hours"] or 0),
                                   minutes=int(match["minutes"] or 0))
        match = _CODEX_AT.search(text)
        if match:
            hour = _hour24(int(match["hour"]), match["ampm"])
            minute = int(match["minute"] or 0)
            if hour is None or minute > 59:
                return None
            return _next_clock(now, _zone(None), hour, minute)
    return None


def classify_infra_failure(text: str | None, dispatch_error: str | None = None) -> str | None:
    """`usage_limit` | `provider_error` | `permission_denied` |
    `timeout_no_output`, or None when the failure is the work's own."""
    body = "\n".join(part for part in (text, dispatch_error) if part)
    for kind, pattern in _INFRA_PATTERNS:
        if pattern.search(body):
            return kind
    error = (dispatch_error or "").lower()
    if ("timed_out" in error or "deadline" in error or "timed out" in error) and not (text or "").strip():
        return "timeout_no_output"
    return None


async def record_usage_limit(db: AsyncSession, demand, text: str | None, now: datetime | None = None) -> datetime | None:
    """From a finished run's output: when it matches a usage-limit pattern of
    the target agent's runtime, mark the agent unavailable until the reset.
    Never shortens a later known reset. Caller commits."""
    if demand.target_agent_id is None or not text:
        return None
    agent = await db.get(Agent, demand.target_agent_id)
    now = now or datetime.now(timezone.utc)
    until = parse_usage_limit(agent.runtime_type if agent else None, text, now)
    if until is None:
        return None
    row = await db.get(AgentAvailability, demand.target_agent_id)
    reason = f"usage limit reported by run #{demand.number} (patterns {PATTERNS_VERSION})"[:200]
    if row is None:
        db.add(AgentAvailability(agent_id=demand.target_agent_id, unavailable_until=until, reason=reason,
                                 source_demand_id=demand.id, recorded_by="forgehub:usage-limit"))
    elif row.unavailable_until < until:
        row.unavailable_until, row.reason = until, reason
        row.source_demand_id, row.recorded_by = demand.id, "forgehub:usage-limit"
    return until


async def unavailable_until(db: AsyncSession, agent_id: uuid.UUID | None, now: datetime | None = None) -> datetime | None:
    if agent_id is None:
        return None
    now = now or datetime.now(timezone.utc)
    row = await db.get(AgentAvailability, agent_id)
    return row.unavailable_until if row is not None and row.unavailable_until > now else None


async def unavailable_agents(db: AsyncSession, now: datetime | None = None) -> dict[uuid.UUID, datetime]:
    now = now or datetime.now(timezone.utc)
    rows = (await db.execute(select(AgentAvailability.agent_id, AgentAvailability.unavailable_until).where(
        AgentAvailability.unavailable_until > now))).all()
    return {agent_id: until for agent_id, until in rows}
