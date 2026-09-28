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

from sqlalchemy import func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.agent_activity import (
    ActivityLinkOut,
    ActivityLiveStateOut,
    ActivityPulseOut,
    AgentLiveSnapshotItemOut,
    AgentLiveSnapshotOut,
)
from app.core.agent_activity import load_live_states
from app.core.agent_activity_timeline import dispatch_interval
from app.core.agent_live_state import LiveState, is_on_demand_runtime
from app.db.models.active_turn import ActiveTurn
from app.core.forgerouter_sync import ForgeRouterUsage, read_forgerouter_usage
from app.db.models.agent import Agent
from app.db.models.agent_activity_event import AgentActivityEvent
from app.db.models.demand import AgentDemand

STREAM_REFRESH_SECONDS = 10
EVENT_DEBOUNCE_SECONDS = 0.3
SPARK_BUCKETS = 12  # 5-minute buckets over the last hour, per agent
PULSE_BUCKETS = 60  # 1-minute buckets over the last hour, page-wide
FORGEROUTER_CACHE_SECONDS = 30

# How long an interaction stays drawn on the constellation after its last activity.
LINK_WINDOW = timedelta(minutes=5)

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


async def build_links(
    db: AsyncSession,
    *,
    now: datetime,
    agent_ids: set[uuid.UUID],
    live_states: dict[uuid.UUID, LiveState],
    historical: bool = False,
) -> list[ActivityLinkOut]:
    """Recent interactions per (source, agent, channel), newest activity wins.

    ``active`` means "happening right now": the agent's open turn is on that channel and
    counterpart, a Workspace turn is running, or a Messages dispatch is in flight.
    ``historical`` (replay): ``now`` is a past instant; "running" means running then.
    """
    since = now - LINK_WINDOW
    links: dict[str, ActivityLinkOut] = {}

    def upsert(link: ActivityLinkOut) -> None:
        current = links.get(link.key)
        if current is None:
            links[link.key] = link
            return
        current.count += 1
        current.active = current.active or link.active
        if link.last_at > current.last_at:
            current.last_at = link.last_at
            current.message_number = link.message_number or current.message_number

    turns = (
        await db.execute(
            select(AgentActivityEvent).where(
                AgentActivityEvent.kind == "turn_started",
                AgentActivityEvent.occurred_at >= since,
                (AgentActivityEvent.occurred_at <= now) if historical else true(),
                AgentActivityEvent.agent_id.in_(agent_ids),
            )
        )
    ).scalars()
    for event in turns:
        source = event.counterpart_kind or "system"
        live = live_states.get(event.agent_id)
        active = bool(
            live
            and live.state in IN_TURN_STATES
            and live.source == "runtime"
            and live.platform == event.platform
            and (live.counterpart_kind or "system") == source
        )
        upsert(ActivityLinkOut(
            key=f"conversation:{source}:{event.platform or '-'}:{event.agent_id}",
            kind="conversation", source_type=source, target_agent_id=event.agent_id,
            channel=event.platform, active=active, last_at=event.occurred_at,
        ))

    workspace_turns = (
        await db.execute(
            select(ActiveTurn).where(
                ActiveTurn.agent_id.in_(agent_ids),
                (ActiveTurn.created_at <= now) if historical else true(),
                (ActiveTurn.status == "running") | (ActiveTurn.updated_at >= since),
            )
        )
    ).scalars()
    for turn in workspace_turns:
        ended = None if turn.status == "running" else (turn.finished_at or turn.updated_at)
        if historical and ended is not None and ended < since:
            continue
        running = ended is None or (historical and ended > now)
        upsert(ActivityLinkOut(
            key=f"workspace:{turn.agent_id}", kind="workspace", source_type="owner",
            target_agent_id=turn.agent_id, channel="workspace", active=running,
            last_at=now if running and historical else (ended or turn.updated_at or turn.created_at),
        ))

    demands = (
        await db.execute(
            select(AgentDemand).where(
                AgentDemand.target_agent_id.in_(agent_ids),
                (AgentDemand.created_at <= now) if historical else true(),
                (AgentDemand.dispatch_status.in_(("dispatched", "running"))) | (AgentDemand.updated_at >= since),
            )
        )
    ).scalars()
    for demand in demands:
        active = demand.dispatch_status in ("dispatched", "running")
        last_at = demand.updated_at
        if historical:
            began, finished = dispatch_interval(demand)
            if began is not None and began <= now and (finished is None or finished > now):
                active, last_at = True, now
            elif began is not None and began <= now and finished is not None and finished >= since:
                active, last_at = False, finished
            elif since <= demand.created_at <= now:
                active, last_at = False, demand.created_at
            else:
                continue
        from_agent = demand.from_agent_id if demand.from_agent_id in agent_ids else None
        if from_agent == demand.target_agent_id:
            from_agent = None  # self-addressed work reads as the system handing it over
        source = "agent" if from_agent else ("system" if demand.from_agent_id else "owner")
        upsert(ActivityLinkOut(
            key=f"message:{from_agent or source}:{demand.target_agent_id}",
            kind="message", source_type=source, source_agent_id=from_agent,
            target_agent_id=demand.target_agent_id, channel="messages",
            active=active, last_at=last_at, message_number=demand.number,
        ))

    return sorted(links.values(), key=lambda link: link.last_at, reverse=True)


async def build_live_snapshot(
    db: AsyncSession, *, now: datetime | None = None, historical: bool = False
) -> AgentLiveSnapshotOut:
    """One live frame. ``historical`` (replay, phase 4): the frame as it stood at ``now``,
    a past instant -- every read bounded at it; ForgeRouter usage and queue counts, which
    have no recorded past, are left out (shown as "—"/0) rather than borrowed from today."""
    now = now or datetime.now(timezone.utc)
    agents = list(
        (await db.execute(select(Agent).where(Agent.is_active.is_(True)).order_by(Agent.name))).scalars()
    )
    live_states = await load_live_states(db, agents, now=now, historical=historical)

    hour_ago = now - timedelta(hours=1)
    rows = (
        await db.execute(
            select(AgentActivityEvent.agent_id, AgentActivityEvent.occurred_at).where(
                AgentActivityEvent.occurred_at >= hour_ago,
                (AgentActivityEvent.occurred_at <= now) if historical else true(),
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
                AgentActivityEvent.occurred_at >= hour_ago,
                (AgentActivityEvent.occurred_at <= now) if historical else true(),
                AgentActivityEvent.kind == "turn_started",
            )
        )
    ).scalars().all()
    reporting_agents = (
        await db.execute(
            select(func.count(func.distinct(AgentActivityEvent.agent_id))).where(
                AgentActivityEvent.occurred_at <= now
            )
        )
    ).scalar_one()

    usage = None if historical else await _cached_forgerouter_usage()
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
    links = await build_links(
        db, now=now, agent_ids={item.agent_id for item in items}, live_states=live_states,
        historical=historical,
    )
    return AgentLiveSnapshotOut(generated_at=now, agents=items, pulse=pulse, links=links)
