"""Runtime alerts for the Agent Activity severity inbox (phase 5, 2026-09-28).

Until phase 5 every incident came from a durable ForgeHub record (a failed execution, a
failed dispatch, a pending approval). The failures that hurt most never produce one: a turn
that hangs, a Telegram adapter that goes ``fatal`` inside a healthy gateway (16 hours unseen
on 2026-09-27), a cron that keeps erroring, a provider returning 503s, an agent suddenly
burning many times its usual tokens. Each signal below is read from where it is actually
true, and each source is optional: when one is unreachable its alerts are simply absent
(the page's source-freshness banner already reports ForgeRouter/bridge outages) -- never a
false "all clear" and never an error that takes the inbox down.

Rules (kept deliberately few and explicit, like the cockpit's traffic lights):

- ``turn_stuck``: the agent's newest runtime turn has no end after ``STUCK_TURN_MINUTES``
  (warning); at ``TURN_STALE_MINUTES`` the live state already reads it as abandoned (error).
- ``adapter_fatal``: an agent with Telegram configured whose gateway adapter is ``fatal``
  (critical) or otherwise not ``connected`` (error). Bridge unreachable = no verdict.
- ``cron_failing``: an enabled cron job whose last run errored, or that is overdue.
- ``provider_error``: ``PROVIDER_ERROR_THRESHOLD`` or more non-success ForgeRouter calls for
  the agent in the last ``PROVIDER_ERROR_WINDOW_MINUTES``.
- ``usage_anomaly``: today's tokens (or cost) far above the agent's own 7-day daily average.
  Most calls cost $0 on this host (free/subscription models), which is why tokens count too.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Iterable, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.agent_activity import ActivityIncidentOut
from app.core import agent_telegram
from app.core.agent_live_state import TURN_STALE_MINUTES, is_on_demand_runtime
from app.core.forgerouter_sync import ForgeRouterHealth, read_forgerouter_health
from app.db.models.agent import Agent
from app.db.models.agent_activity_event import AgentActivityEvent

STUCK_TURN_MINUTES = 10
PROVIDER_ERROR_WINDOW_MINUTES = 15
PROVIDER_ERROR_THRESHOLD = 3
TOKEN_ANOMALY_FACTOR = 3.0
TOKEN_ANOMALY_FLOOR = 200_000
COST_ANOMALY_FACTOR = 3.0
COST_ANOMALY_FLOOR = 1.0  # USD
SOURCE_CACHE_SECONDS = 60
SOURCE_TIMEOUT_SECONDS = 5

T = TypeVar("T")
_cache: dict[str, tuple[float, Any]] = {}


async def _cached(key: str, loader: Callable[[], Awaitable[T]]) -> T | None:
    """The page polls every few seconds; these sources change on the scale of minutes and
    each costs a bridge call, a filesystem walk or another database. A failure is cached
    too (as None), so a dead source isn't retried on every poll."""
    fetched_at, value = _cache.get(key, (0.0, None))
    if key in _cache and time.monotonic() - fetched_at < SOURCE_CACHE_SECONDS:
        return value
    try:
        value = await asyncio.wait_for(loader(), timeout=SOURCE_TIMEOUT_SECONDS)
    except Exception:
        value = None
    _cache[key] = (time.monotonic(), value)
    return value


def _agent_key(agent_id: uuid.UUID, suffix: str) -> uuid.UUID:
    return uuid.uuid5(agent_id, suffix)


def stuck_turn_incidents(
    newest_turns: Iterable[tuple[Agent, Any, bool]], *, now: datetime
) -> list[ActivityIncidentOut]:
    """``newest_turns``: (agent, its newest turn_started event, whether that turn ended)."""
    incidents = []
    for agent, turn, ended in newest_turns:
        age = now - turn.occurred_at
        if ended or age < timedelta(minutes=STUCK_TURN_MINUTES):
            continue
        abandoned = age >= timedelta(minutes=TURN_STALE_MINUTES)
        minutes = int(age.total_seconds() // 60)
        incidents.append(ActivityIncidentOut(
            key=f"turn_stuck:{agent.id}:{turn.turn_id or turn.session_id or turn.occurred_at.isoformat()}",
            kind="turn_stuck",
            severity="error" if abandoned else "warning",
            title=f"{agent.name}: turn with no end for {minutes} min",
            occurred_at=turn.occurred_at,
            source_type="agent_activity_event",
            source_id=turn.id,
            affected_agent_id=agent.id,
            error_code="turn_abandoned" if abandoned else "turn_stuck",
            summary=(
                f"Started on {turn.platform or 'unknown channel'}"
                + (f" with {turn.model}" if turn.model else "")
                + "; the runtime never reported its end."
            ),
            recommended_action="open_agent",
            last_observed_at=now,
            runtime_type=agent.runtime_type,
            current_owner_agent_id=agent.id,
            canonical_path=f"/agents/{agent.id}",
        ))
    return incidents


def adapter_incidents(
    agents: Iterable[Agent], states: dict[str, str] | None, *, now: datetime
) -> list[ActivityIncidentOut]:
    """``states`` None = the bridge could not be read: no verdict either way."""
    if states is None:
        return []
    incidents = []
    for agent in agents:
        if agent.runtime_type != "hermes" or not agent.profile_slug:
            continue
        installed, _ = agent_telegram.read_profile_telegram_config(
            agent.effective_home_path, agent.runtime_type, agent.profile_slug
        )
        if not installed:
            continue
        state = states.get(agent.profile_slug)
        if state == "connected":
            continue
        fatal = state == "fatal"
        incidents.append(ActivityIncidentOut(
            key=f"adapter_fatal:{agent.id}:{state or 'missing'}",
            kind="adapter_fatal",
            severity="critical" if fatal else "error",
            title=f"{agent.name}: Telegram channel {'fatal' if fatal else 'down'}",
            occurred_at=now,
            source_type="telegram_adapter",
            source_id=_agent_key(agent.id, "telegram"),
            affected_agent_id=agent.id,
            error_code=f"telegram_{state or 'not_running'}",
            summary=(
                "Messages sent to this agent on Telegram go nowhere. Never start a second "
                "gateway to fix it (Foundation 52_policies/hermes-gateway-operations.md)."
            ),
            recommended_action="open_agent",
            last_observed_at=now,
            runtime_type=agent.runtime_type,
            current_owner_agent_id=agent.id,
            canonical_path=f"/agents/{agent.id}",
        ))
    return incidents


def cron_incidents(
    agents: Iterable[Agent], jobs: Iterable[Any] | None, *, now: datetime
) -> list[ActivityIncidentOut]:
    """``jobs``: foundation's CronJobOut rows (profile, id, name, health, last_error...)."""
    if jobs is None:
        return []
    by_slug = {(agent.profile_slug or "").lower(): agent for agent in agents if agent.profile_slug}
    incidents = []
    for job in jobs:
        if job.health not in ("error", "overdue"):
            continue
        agent = by_slug.get((job.profile or "").lower())
        occurred = _parse_time(job.last_run_at) or _parse_time(job.next_run_at) or now
        incidents.append(ActivityIncidentOut(
            key=f"cron_failing:{job.profile}:{job.id}",
            kind="cron_failing",
            severity="error" if job.health == "error" else "warning",
            title=f"Cron {job.name or job.id} ({job.profile}) {'failing' if job.health == 'error' else 'overdue'}",
            occurred_at=occurred,
            source_type="cron_job",
            source_id=uuid.uuid5(uuid.NAMESPACE_URL, f"cron:{job.profile}:{job.id}"),
            affected_agent_id=agent.id if agent else None,
            error_code=f"cron_{job.health}",
            summary=(job.last_error or job.last_status or None) if job.health == "error"
            else f"Next run was due at {job.next_run_at}; the scheduler is not running it.",
            recommended_action="open_crons",
            last_observed_at=now,
            current_owner_agent_id=agent.id if agent else None,
            canonical_path="/crons",
        ))
    return incidents


def forgerouter_incidents(
    agents: Iterable[Agent], health: Iterable[ForgeRouterHealth] | None, *, now: datetime
) -> list[ActivityIncidentOut]:
    if health is None:
        return []
    by_name = {agent.name.casefold(): agent for agent in agents}
    incidents = []
    for row in health:
        agent = by_name.get((row.agent_name or "").casefold())
        if agent is None:
            continue  # a ForgeRouter service or an unattributed call: not an agent's incident
        if row.errors_recent >= PROVIDER_ERROR_THRESHOLD:
            incidents.append(ActivityIncidentOut(
                key=f"provider_error:{agent.id}",
                kind="provider_error",
                severity="error" if row.errors_recent >= 3 * PROVIDER_ERROR_THRESHOLD else "warning",
                title=f"{agent.name}: {row.errors_recent} LLM errors in {PROVIDER_ERROR_WINDOW_MINUTES} min",
                occurred_at=row.last_error_at or now,
                source_type="forgerouter_route_events",
                source_id=_agent_key(agent.id, "forgerouter-errors"),
                affected_agent_id=agent.id,
                error_code=row.last_error_type,
                summary="ForgeRouter calls for this agent are failing at the provider.",
                recommended_action="open_agent",
                last_observed_at=now,
                provider="forgerouter",
                current_owner_agent_id=agent.id,
                canonical_path=f"/agents/{agent.id}",
            ))
        cost_high = row.cost_today >= COST_ANOMALY_FLOOR and row.cost_today > max(
            COST_ANOMALY_FACTOR * row.cost_prev_avg, row.cost_prev_avg + COST_ANOMALY_FLOOR
        )
        tokens_high = row.tokens_today >= TOKEN_ANOMALY_FLOOR and row.tokens_today > max(
            TOKEN_ANOMALY_FACTOR * row.tokens_prev_avg, row.tokens_prev_avg + TOKEN_ANOMALY_FLOOR
        )
        if cost_high or tokens_high:
            ratio = (
                row.cost_today / row.cost_prev_avg if cost_high and row.cost_prev_avg
                else row.tokens_today / row.tokens_prev_avg if row.tokens_prev_avg else None
            )
            incidents.append(ActivityIncidentOut(
                key=f"usage_anomaly:{agent.id}:{now.date().isoformat()}",
                kind="usage_anomaly",
                severity="error" if cost_high else "warning",
                title=(
                    f"{agent.name}: usage {ratio:.0f}× its daily average" if ratio
                    else f"{agent.name}: usage with no recent baseline"
                ),
                occurred_at=now,
                source_type="forgerouter_route_events",
                source_id=_agent_key(agent.id, f"usage-{now.date().isoformat()}"),
                affected_agent_id=agent.id,
                error_code="cost_anomaly" if cost_high else "token_anomaly",
                summary=(
                    f"Today: {row.tokens_today:,} tokens, US$ {row.cost_today:.2f}. "
                    f"7-day daily average: {row.tokens_prev_avg:,.0f} tokens, US$ {row.cost_prev_avg:.2f}."
                ),
                recommended_action="open_agent",
                last_observed_at=now,
                provider="forgerouter",
                current_owner_agent_id=agent.id,
                canonical_path=f"/agents/{agent.id}",
            ))
    return incidents


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


async def _newest_turns(db: AsyncSession, agents: list[Agent], *, now: datetime):
    ids = [agent.id for agent in agents if not is_on_demand_runtime(agent.runtime_type)]
    if not ids:
        return []
    since = now - timedelta(hours=24)
    newest = (
        select(AgentActivityEvent.agent_id, func.max(AgentActivityEvent.occurred_at).label("at"))
        .where(
            AgentActivityEvent.agent_id.in_(ids),
            AgentActivityEvent.kind == "turn_started",
            AgentActivityEvent.occurred_at >= since,
        )
        .group_by(AgentActivityEvent.agent_id)
        .subquery()
    )
    starts = (
        await db.execute(
            select(AgentActivityEvent).join(
                newest,
                (AgentActivityEvent.agent_id == newest.c.agent_id)
                & (AgentActivityEvent.occurred_at == newest.c.at)
                & (AgentActivityEvent.kind == "turn_started"),
            )
        )
    ).scalars().all()
    by_id = {agent.id: agent for agent in agents}
    result = []
    for start in starts:
        ends = select(AgentActivityEvent.id).where(
            AgentActivityEvent.agent_id == start.agent_id,
            AgentActivityEvent.kind == "turn_ended",
            AgentActivityEvent.occurred_at >= start.occurred_at,
        )
        if start.turn_id:
            ends = ends.where(AgentActivityEvent.turn_id == start.turn_id)
        elif start.session_id:
            ends = ends.where(AgentActivityEvent.session_id == start.session_id)
        ended = (await db.execute(ends.limit(1))).first() is not None
        result.append((by_id[start.agent_id], start, ended))
    return result


async def _cron_jobs():
    from app.api.routes.foundation import _list_cron_jobs  # the cron store's own reader

    return await asyncio.to_thread(_list_cron_jobs)


async def _telegram_states():
    states, error = await agent_telegram.read_telegram_platform_states()
    return None if error else states


async def build_runtime_incidents(
    db: AsyncSession, agents: Iterable[Agent], *, now: datetime | None = None
) -> list[ActivityIncidentOut]:
    now = now or datetime.now(timezone.utc)
    agents = [agent for agent in agents if agent.is_active]
    health, states, jobs = await asyncio.gather(
        _cached("forgerouter_health", lambda: read_forgerouter_health(PROVIDER_ERROR_WINDOW_MINUTES)),
        _cached("telegram_states", _telegram_states),
        _cached("cron_jobs", _cron_jobs),
    )
    return [
        *stuck_turn_incidents(await _newest_turns(db, agents, now=now), now=now),
        *adapter_incidents(agents, states, now=now),
        *cron_incidents(agents, jobs, now=now),
        *forgerouter_incidents(agents, health, now=now),
    ]
