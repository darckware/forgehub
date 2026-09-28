"""Live stream behind the Agent Activity screen (phase 2, 2026-09-28).

``GET /api/v1/agent-activity/stream`` (SSE) sends a *live snapshot* -- every agent's live
state, a per-agent 60-minute sparkline and the page-wide pulse -- when a client connects,
again within a fraction of a second after any runtime event lands (the ingest route calls
``broadcaster.publish``), and every ``STREAM_REFRESH_SECONDS`` regardless. The periodic send
covers what no webhook announces: a Workspace turn starting, a message queued for an
agent, "idle for N min" drifting, a stale turn crossing its 30-minute cutoff.

Whole snapshots rather than deltas on purpose: a dropped connection or a missed event
can never leave the client with a state the server doesn't have -- the next frame
simply replaces it. It stays small (a few hundred bytes per agent).

The broadcaster is in-process, which is right for the single uvicorn worker this backend
runs (``backend/Dockerfile``). A second worker would need a shared channel (Postgres
LISTEN/NOTIFY) -- the periodic refresh keeps even that case correct, only slower.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.agent_activity import (
    ActivityLiveStateOut,
    ActivityPulseOut,
    AgentLiveSnapshotItemOut,
    AgentLiveSnapshotOut,
)
from app.core.agent_activity import load_live_states
from app.core.agent_live_state import is_on_demand_runtime
from app.core.forgerouter_sync import ForgeRouterUsage, read_forgerouter_usage
from app.db.models.agent import Agent
from app.db.models.agent_activity_event import AgentActivityEvent

STREAM_REFRESH_SECONDS = 10
EVENT_DEBOUNCE_SECONDS = 0.3
SPARK_BUCKETS = 12  # 5-minute buckets over the last hour, per agent
PULSE_BUCKETS = 60  # 1-minute buckets over the last hour, page-wide
FORGEROUTER_CACHE_SECONDS = 30

IN_TURN_STATES = {"executing", "thinking"}
ACTIVE_STATES = IN_TURN_STATES | {"conversing"}


class ActivityBroadcaster:
    """Fan-out of "something happened" signals to every open stream."""

    def __init__(self) -> None:
        self._queues: set[asyncio.Queue[str]] = set()

    @contextmanager
    def subscribe(self) -> Iterator[asyncio.Queue[str]]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        self._queues.add(queue)
        try:
            yield queue
        finally:
            self._queues.discard(queue)

    def publish(self, signal: str = "event") -> None:
        for queue in list(self._queues):
            try:
                queue.put_nowait(signal)
            except asyncio.QueueFull:
                pass  # that client is already due a refresh; one pending signal is enough

    @property
    def subscriber_count(self) -> int:
        return len(self._queues)


broadcaster = ActivityBroadcaster()

_usage_cache: tuple[float, list[ForgeRouterUsage] | None] = (0.0, None)


async def _cached_forgerouter_usage() -> list[ForgeRouterUsage] | None:
    """ForgeRouter lives in another Postgres; never let it slow or break the stream."""
    global _usage_cache
    fetched_at, value = _usage_cache
    if value is not None and time.monotonic() - fetched_at < FORGEROUTER_CACHE_SECONDS:
        return value
    try:
        value = await asyncio.wait_for(read_forgerouter_usage(), timeout=3)
    except Exception:
        value = None
    _usage_cache = (time.monotonic(), value)
    return value


def _bucket_counts(times: list[datetime], *, now: datetime, buckets: int, width: timedelta) -> list[int]:
    counts = [0] * buckets
    start = now - width * buckets
    for moment in times:
        if moment < start or moment > now:
            continue
        index = min(buckets - 1, int((moment - start) / width))
        counts[index] += 1
    return counts


async def build_live_snapshot(db: AsyncSession, *, now: datetime | None = None) -> AgentLiveSnapshotOut:
    now = now or datetime.now(timezone.utc)
    agents = list(
        (await db.execute(select(Agent).where(Agent.is_active.is_(True)).order_by(Agent.name))).scalars()
    )
    live_states = await load_live_states(db, agents, now=now)

    hour_ago = now - timedelta(hours=1)
    rows = (
        await db.execute(
            select(AgentActivityEvent.agent_id, AgentActivityEvent.occurred_at).where(
                AgentActivityEvent.occurred_at >= hour_ago,
                AgentActivityEvent.kind.in_(("turn_started", "tool_started")),
            )
        )
    ).all()
    times_by_agent: dict[uuid.UUID | None, list[datetime]] = defaultdict(list)
    for agent_id, occurred_at in rows:
        times_by_agent[agent_id].append(occurred_at)
    all_turn_times = (
        await db.execute(
            select(AgentActivityEvent.occurred_at).where(
                AgentActivityEvent.occurred_at >= hour_ago, AgentActivityEvent.kind == "turn_started"
            )
        )
    ).scalars().all()
    reporting_agents = (
        await db.execute(select(func.count(func.distinct(AgentActivityEvent.agent_id))))
    ).scalar_one()

    usage = await _cached_forgerouter_usage()
    usage_by_name = {(u.agent_name or "").casefold(): u for u in usage or []}

    items: list[AgentLiveSnapshotItemOut] = []
    for agent in agents:
        live = live_states.get(agent.id)
        if is_on_demand_runtime(agent.runtime_type) and live is None:
            continue  # an external executor is only on the board while Messages runs it
        agent_usage = usage_by_name.get(agent.name.casefold())
        items.append(
            AgentLiveSnapshotItemOut(
                agent_id=agent.id,
                live=ActivityLiveStateOut(**vars(live)) if live is not None else None,
                spark=_bucket_counts(
                    times_by_agent.get(agent.id, []), now=now, buckets=SPARK_BUCKETS,
                    width=timedelta(minutes=5),
                ),
                tokens_last_hour=agent_usage.tokens_last_hour if agent_usage else 0,
                cost_today=agent_usage.cost_today if agent_usage else 0.0,
            )
        )

    states = [item.live for item in items if item.live is not None]
    pulse = ActivityPulseOut(
        agents_total=len(items),
        agents_reporting=int(reporting_agents or 0),
        agents_active=sum(1 for s in states if s.state in ACTIVE_STATES),
        agents_in_turn=sum(1 for s in states if s.state in IN_TURN_STATES),
        agents_degraded=sum(1 for s in states if s.state == "degraded"),
        turns_last_hour=sum(s.turns_last_hour for s in states),
        tools_last_hour=sum(s.tools_last_hour for s in states),
        failures_last_hour=sum(s.failures_last_hour for s in states),
        pending_total=sum(s.pending_count for s in states),
        llm_calls_last_hour=sum(u.calls_last_hour for u in usage) if usage is not None else None,
        tokens_last_hour=sum(u.tokens_last_hour for u in usage) if usage is not None else None,
        cost_today=round(sum(u.cost_today for u in usage), 4) if usage is not None else None,
        turns_per_minute=_bucket_counts(
            list(all_turn_times), now=now, buckets=PULSE_BUCKETS, width=timedelta(minutes=1)
        ),
    )
    return AgentLiveSnapshotOut(generated_at=now, agents=items, pulse=pulse)
