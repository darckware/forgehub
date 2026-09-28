"""Traceability for the Agent Activity screen (phase 4, 2026-09-28).

``GET /api/v1/agent-activity/timeline`` answers "what did each agent do between A and B?"
-- the acceptance test in AGENT_ACTIVITY_REDESIGN_PLAN.md is reconstructing what Athos did
between 14h and 15h from the screen alone, with a click through to the canonical record.

Three sources, each already ForgeHub's own record (nothing reads a runtime's store):

- ``agent_activity_events`` -- runtime turns and tool calls, paired start/end here;
- ``agent_demands`` -- Messages dispatches (``dispatched_at`` -> ``task_execution_at``)
  and agent-to-agent messages;
- ``active_turns`` -- Workspace chat turns.

The pairing is pure (``pair_runtime_events``) so it is testable without a database and is
the same rule ``derive_live_state`` uses: a turn with no end after ``TURN_STALE_MINUTES``
was abandoned, never "still thinking".

Replay reuses ``build_live_snapshot(at=...)`` rather than a second model of the past: the
same functions, bounded at the instant being replayed.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Iterable

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.agent_activity import (
    AgentActivityTimelineOut,
    TimelineBlockOut,
    TimelineEventOut,
    TimelineLaneOut,
    TimelineMessageOut,
    TimelineToolOut,
)
from app.core.agent_live_state import TURN_STALE_MINUTES
from app.db.models.active_turn import ActiveTurn
from app.db.models.agent import Agent
from app.db.models.agent_activity_event import AgentActivityEvent
from app.db.models.demand import AgentDemand

MAX_WINDOW = timedelta(hours=24)
EVENT_TABLE_LIMIT = 2000
TERMINAL_DISPATCH_STATUSES = {"completed", "failed"}
RUNNING_DISPATCH_STATUSES = {"dispatched", "running"}


def _same_turn(start: Any, other: Any) -> bool:
    if start.turn_id and other.turn_id:
        return start.turn_id == other.turn_id
    return bool(start.session_id) and start.session_id == other.session_id


def pair_runtime_events(events: Iterable[Any], *, now: datetime) -> list[TimelineBlockOut]:
    """Turns (with their tool calls) of ONE agent, from its lifecycle events, any order.

    A turn's end is its ``turn_ended``; without one it is open while younger than
    ``TURN_STALE_MINUTES`` and ``abandoned`` after that, ending at its last known event.
    Tools pair by ``tool_call_id``; a ``tool_ended`` whose start is missing is placed by
    its ``duration_ms``.
    """
    ordered = sorted(events, key=lambda e: e.occurred_at)
    starts = [e for e in ordered if e.kind == "turn_started"]
    blocks: list[TimelineBlockOut] = []
    for index, start in enumerate(starts):
        # A turn owns the events up to the next start of the same turn (a runtime can
        # reuse a session id for successive turns).
        next_start = next(
            (s.occurred_at for s in starts[index + 1:] if _same_turn(start, s)), None
        )
        mine = [
            e for e in ordered
            if e.occurred_at >= start.occurred_at
            and (next_start is None or e.occurred_at < next_start)
            and e.kind != "turn_started"
            and _same_turn(start, e)
        ]
        ended = next((e for e in mine if e.kind == "turn_ended"), None)
        if ended is not None:
            mine = [e for e in mine if e.occurred_at <= ended.occurred_at]
        end: datetime | None
        status: str | None
        if ended is not None:
            end, status = ended.occurred_at, ended.status or "completed"
        elif now - start.occurred_at >= timedelta(minutes=TURN_STALE_MINUTES):
            end = mine[-1].occurred_at if mine else start.occurred_at
            status = "abandoned"
        else:
            end, status = None, "open"

        tool_starts = {e.tool_call_id: e for e in mine if e.kind == "tool_started" and e.tool_call_id}
        tools: list[TimelineToolOut] = []
        paired: set[str] = set()
        for event in mine:
            if event.kind == "tool_ended":
                began = tool_starts.get(event.tool_call_id) if event.tool_call_id else None
                if began is not None:
                    paired.add(event.tool_call_id)
                    tool_start = began.occurred_at
                elif event.duration_ms:
                    tool_start = event.occurred_at - timedelta(milliseconds=event.duration_ms)
                else:
                    tool_start = event.occurred_at
                tools.append(TimelineToolOut(
                    start=tool_start, end=event.occurred_at,
                    tool_name=event.tool_name or (began.tool_name if began else None),
                    status=event.status, duration_ms=event.duration_ms,
                ))
        for call_id, began in tool_starts.items():
            if call_id not in paired:
                tools.append(TimelineToolOut(start=began.occurred_at, tool_name=began.tool_name))
        for event in mine:
            if event.kind == "tool_started" and not event.tool_call_id:
                tools.append(TimelineToolOut(start=event.occurred_at, tool_name=event.tool_name))
        tools.sort(key=lambda tool: tool.start)

        blocks.append(TimelineBlockOut(
            key=f"turn:{start.agent_id}:{start.turn_id or start.session_id or start.occurred_at.isoformat()}",
            kind="turn",
            start=start.occurred_at,
            end=end,
            platform=start.platform,
            counterpart_kind=start.counterpart_kind,
            counterpart_ref=start.counterpart_ref,
            model=start.model,
            status=status,
            error_type=ended.error_type if ended is not None else None,
            session_id=start.session_id,
            turn_id=start.turn_id,
            tools=tools,
            canonical_path=f"/agents/{start.agent_id}" if start.agent_id else None,
        ))
    return blocks


def dispatch_interval(demand: Any) -> tuple[datetime | None, datetime | None]:
    """(start, end) of a message's latest dispatch; end None while it still runs.

    ``dispatched_at`` only exists since 2026-09-28; older rows fall back to
    ``scheduled_at``. A terminal dispatch ends at ``task_execution_at``, or at its last
    write when a failure never stamped one.
    """
    start = getattr(demand, "dispatched_at", None) or demand.scheduled_at
    if demand.dispatch_status in TERMINAL_DISPATCH_STATUSES:
        return start, demand.task_execution_at or demand.updated_at
    if demand.dispatch_status in RUNNING_DISPATCH_STATUSES:
        return start, None
    return None, None


def _overlaps(start: datetime, end: datetime | None, window_start: datetime, window_end: datetime) -> bool:
    return start <= window_end and (end is None or end >= window_start)


async def build_timeline(
    db: AsyncSession,
    *,
    start: datetime,
    end: datetime,
    now: datetime,
    agent_id: uuid.UUID | None = None,
) -> AgentActivityTimelineOut:
    agents = list(
        (await db.execute(select(Agent).where(Agent.is_active.is_(True)).order_by(Agent.name))).scalars()
    )
    agent_ids = {agent.id for agent in agents}
    if agent_id is not None:
        agent_ids &= {agent_id}
    lanes: dict[uuid.UUID, list[TimelineBlockOut]] = defaultdict(list)
    table: list[TimelineEventOut] = []

    # Runtime turns. Read TURN_STALE_MINUTES past both edges: a turn that began just
    # before the window is drawn from its real start, and one still running at its end
    # keeps its real end instead of reading as open or abandoned.
    lookback = start - timedelta(minutes=TURN_STALE_MINUTES)
    lookahead = end + timedelta(minutes=TURN_STALE_MINUTES)
    runtime_events = list(
        (
            await db.execute(
                select(AgentActivityEvent)
                .where(
                    AgentActivityEvent.agent_id.in_(agent_ids),
                    AgentActivityEvent.occurred_at >= lookback,
                    AgentActivityEvent.occurred_at <= lookahead,
                )
                .order_by(AgentActivityEvent.occurred_at)
            )
        ).scalars()
    )
    by_agent: dict[uuid.UUID, list[AgentActivityEvent]] = defaultdict(list)
    for event in runtime_events:
        by_agent[event.agent_id].append(event)
    for owner, events in by_agent.items():
        for block in pair_runtime_events(events, now=now):
            if _overlaps(block.start, block.end, start, end):
                lanes[owner].append(block)
    for event in runtime_events:
        if not start <= event.occurred_at <= end:
            continue
        table.append(TimelineEventOut(
            key=f"runtime:{event.id}", occurred_at=event.occurred_at, agent_id=event.agent_id,
            profile=event.profile, source="runtime", kind=event.kind, platform=event.platform,
            counterpart_kind=event.counterpart_kind, counterpart_ref=event.counterpart_ref,
            model=event.model, tool_name=event.tool_name, status=event.status,
            error_type=event.error_type, duration_ms=event.duration_ms,
            session_id=event.session_id, turn_id=event.turn_id,
            canonical_path=f"/agents/{event.agent_id}" if event.agent_id else None,
        ))

    # Messages: dispatch spans on the executor's lane, and agent-to-agent arrows.
    demand_rows = list(
        (
            await db.execute(
                select(AgentDemand).where(
                    or_(
                        AgentDemand.target_agent_id.in_(agent_ids),
                        AgentDemand.from_agent_id.in_(agent_ids),
                    ),
                    or_(
                        and_(AgentDemand.created_at >= start, AgentDemand.created_at <= end),
                        and_(
                            or_(AgentDemand.dispatched_at <= end, AgentDemand.scheduled_at <= end),
                            or_(
                                AgentDemand.dispatch_status.in_(RUNNING_DISPATCH_STATUSES),
                                AgentDemand.task_execution_at >= start,
                                AgentDemand.updated_at >= start,
                            ),
                        ),
                    ),
                )
            )
        ).scalars()
    )
    messages: list[TimelineMessageOut] = []
    for demand in demand_rows:
        path = f"/demands?message={demand.id}"
        began, finished = dispatch_interval(demand)
        if (
            began is not None
            and demand.target_agent_id in agent_ids
            and _overlaps(began, finished, start, end)
        ):
            from_agent = demand.from_agent_id if demand.from_agent_id != demand.target_agent_id else None
            lanes[demand.target_agent_id].append(TimelineBlockOut(
                key=f"dispatch:{demand.id}", kind="dispatch", start=began, end=finished,
                platform="messages",
                counterpart_kind="agent" if from_agent else ("system" if demand.from_agent_id else "owner"),
                counterpart_agent_id=from_agent,
                status=demand.dispatch_status, message_number=demand.number, canonical_path=path,
            ))
            for moment, kind in ((began, "dispatch_started"), (finished, f"dispatch_{demand.dispatch_status}")):
                if moment is not None and start <= moment <= end:
                    table.append(TimelineEventOut(
                        key=f"{kind}:{demand.id}", occurred_at=moment, agent_id=demand.target_agent_id,
                        source="messages", kind=kind, platform="messages",
                        status=demand.dispatch_status, message_number=demand.number, canonical_path=path,
                    ))
        if (
            demand.from_agent_id is not None
            and demand.target_agent_id is not None
            and demand.from_agent_id != demand.target_agent_id
            and start <= demand.created_at <= end
            and (demand.from_agent_id in agent_ids or demand.target_agent_id in agent_ids)
        ):
            messages.append(TimelineMessageOut(
                id=demand.id, number=demand.number, at=demand.created_at,
                from_agent_id=demand.from_agent_id, target_agent_id=demand.target_agent_id,
                subject=demand.subject, canonical_path=path,
            ))
            table.append(TimelineEventOut(
                key=f"message:{demand.id}", occurred_at=demand.created_at, agent_id=demand.from_agent_id,
                source="messages", kind="message_sent", platform="messages", counterpart_kind="agent",
                message_number=demand.number, canonical_path=path,
            ))

    # Workspace chat turns.
    workspace_turns = (
        await db.execute(
            select(ActiveTurn).where(
                ActiveTurn.agent_id.in_(agent_ids),
                ActiveTurn.created_at <= end,
                or_(ActiveTurn.finished_at.is_(None), ActiveTurn.finished_at >= start),
            )
        )
    ).scalars()
    for turn in workspace_turns:
        finished = turn.finished_at if turn.status != "running" else None
        if turn.status != "running" and finished is None:
            finished = turn.updated_at
        lanes[turn.agent_id].append(TimelineBlockOut(
            key=f"workspace:{turn.id}", kind="workspace", start=turn.created_at, end=finished,
            platform="workspace", counterpart_kind="owner", status=turn.status,
            canonical_path="/workspace",
        ))
        if start <= turn.created_at <= end:
            table.append(TimelineEventOut(
                key=f"workspace:{turn.id}", occurred_at=turn.created_at, agent_id=turn.agent_id,
                source="workspace", kind="workspace_turn", platform="workspace",
                counterpart_kind="owner", status=turn.status, canonical_path="/workspace",
            ))

    table.sort(key=lambda row: row.occurred_at, reverse=True)
    truncated = len(table) > EVENT_TABLE_LIMIT
    ordered_ids = [agent.id for agent in agents if agent.id in lanes]
    return AgentActivityTimelineOut(
        start=start,
        end=end,
        generated_at=now,
        lanes=[
            TimelineLaneOut(agent_id=owner, blocks=sorted(lanes[owner], key=lambda block: block.start))
            for owner in ordered_ids
        ],
        messages=sorted(messages, key=lambda message: message.at),
        events=table[:EVENT_TABLE_LIMIT],
        truncated=truncated,
    )
