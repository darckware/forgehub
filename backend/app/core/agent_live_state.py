"""Live state of each agent, derived from the lifecycle events its runtime pushes.

Two halves, both pure functions (the route and the aggregator own the session):

- ``normalize_hermes_hook`` turns one Hermes outbound-webhook body (``hooks.outbound``,
  see ``db/models/agent_activity_event.py``) into the metadata-only columns of an
  ``AgentActivityEvent``. The body carries the whole conversation history; nothing of it
  survives this function except ids, platform, a masked counterpart, model and tool name.
- ``derive_live_state`` answers "what is this agent doing right now?" from its recent
  events: executing a tool, thinking, just replied, failed, or idle since when.

The state is inferred from start/end pairs rather than trusted from a heartbeat, so a
runtime that dies mid-turn must not read "thinking" forever: an open turn older than
``TURN_STALE_MINUTES`` is treated as abandoned.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Literal

HERMES_HOOK_KINDS = {
    "pre_llm_call": "turn_started",
    "on_session_end": "turn_ended",
    "pre_tool_call": "tool_started",
    "post_tool_call": "tool_ended",
    "on_session_start": "session_started",
}

# Platforms where the other side is a person typing in a chat app.
MESSAGING_PLATFORMS = {
    "telegram", "whatsapp", "discord", "slack", "signal", "matrix", "email", "sms",
    "mattermost", "webhook", "homeassistant", "dingtalk", "feishu", "wecom", "weixin",
}
# A person at this host's terminal is the operator.
OPERATOR_PLATFORMS = {"cli", "tui", "acp"}
# Work the ecosystem started on its own behalf.
SYSTEM_PLATFORMS = {"cron", "kanban", "subagent", "tool", "api_server", "recovered"}

# External CLI runtimes (Porthus/claude, Aramis/codex, Dartan/agy, Vector/openclaw) are
# executors, not residents: they only act when Messages dispatches a message to them
# (Marcelo, 2026-09-28: "são agentes externo só interagem quando são executados pelo
# Messages"). No runtime telemetry is collected for them; their live state is the dispatch
# itself, and while nothing is dispatched to them they are simply not on the live board.
ON_DEMAND_RUNTIMES = {"claude", "codex", "agy", "openclaw"}


def is_on_demand_runtime(runtime_type: str | None) -> bool:
    return (runtime_type or "").lower() in ON_DEMAND_RUNTIMES


TURN_STALE_MINUTES = 30
CONVERSING_WINDOW = timedelta(minutes=2)
FAILURE_WINDOW = timedelta(minutes=15)
ACTIVITY_WINDOW = timedelta(hours=1)

LiveStateName = Literal["executing", "thinking", "conversing", "waiting", "degraded", "idle"]


def verify_signature(secret: str, body: bytes, header: str | None) -> bool:
    """``X-Hermes-Signature-256: sha256=<hex>`` over the raw body (outbound_webhooks.py)."""
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[len("sha256="):].strip())


def mask_ref(value: Any) -> str | None:
    text = str(value).strip() if value not in (None, "") else ""
    if not text:
        return None
    return f"···{text[-4:]}" if len(text) > 4 else f"···{text}"


def classify_counterpart(
    platform: str | None, sender_id: str | None, home_chat: str | None
) -> tuple[str | None, str | None]:
    """(counterpart_kind, counterpart_ref) -- never the raw id of an outside person."""
    if not platform:
        return None, None
    if platform in OPERATOR_PLATFORMS:
        return "owner", None
    if platform in SYSTEM_PLATFORMS:
        return "system", None
    if platform in MESSAGING_PLATFORMS:
        if sender_id and home_chat and str(sender_id) == str(home_chat):
            return "owner", None
        return "human", mask_ref(sender_id)
    return None, None


def _clip(value: Any, size: int) -> str | None:
    if value in (None, ""):
        return None
    return str(value)[:size]


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def normalize_hermes_hook(body: dict[str, Any], *, home_chat: str | None) -> dict[str, Any] | None:
    """Column values for one webhook body, or None for an event we don't record."""
    kind = HERMES_HOOK_KINDS.get(str(body.get("hook_event_name") or ""))
    if kind is None:
        return None
    extra = body.get("extra") if isinstance(body.get("extra"), dict) else {}
    platform = _clip(extra.get("platform"), 40)
    platform = platform.lower() if platform else None
    counterpart_kind, counterpart_ref = (None, None)
    if kind in ("turn_started", "session_started"):
        counterpart_kind, counterpart_ref = classify_counterpart(
            platform, _clip(extra.get("sender_id"), 128), home_chat
        )

    status = None
    error_type = None
    if kind == "tool_ended":
        status = _clip(extra.get("status"), 30)
        error_type = _clip(extra.get("error_type"), 120)
    elif kind == "turn_ended":
        if extra.get("failed"):
            status = "failed"
        elif extra.get("interrupted"):
            status = "interrupted"
        else:
            status = "completed"
        if status != "completed":
            error_type = _clip(extra.get("turn_exit_reason"), 120)

    duration = extra.get("duration_ms")
    return {
        "profile": _clip(body.get("profile"), 100) or "default",
        "runtime": "hermes",
        "kind": kind,
        "occurred_at": _parse_ts(body.get("timestamp")),
        "session_id": _clip(body.get("session_id") or extra.get("session_id"), 128),
        "turn_id": _clip(extra.get("turn_id"), 128),
        "tool_call_id": _clip(extra.get("tool_call_id"), 128),
        "platform": platform,
        "counterpart_kind": counterpart_kind,
        "counterpart_ref": counterpart_ref,
        "model": _clip(extra.get("model"), 120),
        "tool_name": _clip(body.get("tool_name"), 120),
        "status": status,
        "error_type": error_type,
        "duration_ms": int(duration) if isinstance(duration, (int, float)) else None,
        "delivery_id": _clip(body.get("delivery_id"), 64),
    }


@dataclass(frozen=True)
class EventView:
    """The fields derive_live_state reads -- an ORM row satisfies it as-is."""

    kind: str
    occurred_at: datetime
    session_id: str | None = None
    turn_id: str | None = None
    tool_call_id: str | None = None
    platform: str | None = None
    counterpart_kind: str | None = None
    counterpart_ref: str | None = None
    model: str | None = None
    tool_name: str | None = None
    status: str | None = None
    error_type: str | None = None


@dataclass
class LiveState:
    state: LiveStateName
    since: datetime | None = None
    source: str | None = None
    platform: str | None = None
    counterpart_kind: str | None = None
    counterpart_ref: str | None = None
    model: str | None = None
    tool_name: str | None = None
    session_id: str | None = None
    turn_id: str | None = None
    last_event_at: datetime | None = None
    reason: str | None = None
    message_number: int | None = None
    turns_last_hour: int = 0
    tools_last_hour: int = 0
    failures_last_hour: int = 0
    pending_count: int = 0


def _same_turn(start: Any, other: Any) -> bool:
    if start.turn_id and other.turn_id:
        return start.turn_id == other.turn_id
    return bool(start.session_id) and start.session_id == other.session_id


def derive_live_state(
    events: Iterable[Any],
    *,
    now: datetime,
    workspace_turn_started_at: datetime | None = None,
    pending_count: int = 0,
) -> LiveState:
    """What the agent is doing now. ``events`` = its recent events, any order."""
    ordered = sorted(events, key=lambda e: e.occurred_at)
    hour_ago = now - ACTIVITY_WINDOW
    recent = [e for e in ordered if e.occurred_at >= hour_ago]
    counters = {
        "turns_last_hour": sum(1 for e in recent if e.kind == "turn_started"),
        "tools_last_hour": sum(1 for e in recent if e.kind == "tool_started"),
        "failures_last_hour": sum(
            1 for e in recent
            if (e.kind == "turn_ended" and e.status == "failed")
            or (e.kind == "tool_ended" and e.status == "error")
        ),
        "pending_count": pending_count,
    }
    last_event_at = ordered[-1].occurred_at if ordered else None

    starts = [e for e in ordered if e.kind == "turn_started"]
    turn = starts[-1] if starts else None
    if turn is not None:
        after = [e for e in ordered if e.occurred_at >= turn.occurred_at and _same_turn(turn, e)]
        ended = next((e for e in after if e.kind == "turn_ended"), None)
        common = {
            "source": "runtime",
            "platform": turn.platform,
            "counterpart_kind": turn.counterpart_kind,
            "counterpart_ref": turn.counterpart_ref,
            "model": turn.model,
            "session_id": turn.session_id,
            "turn_id": turn.turn_id,
            "last_event_at": last_event_at,
            **counters,
        }
        if ended is None and now - turn.occurred_at < timedelta(minutes=TURN_STALE_MINUTES):
            closed = {e.tool_call_id for e in after if e.kind == "tool_ended" and e.tool_call_id}
            open_tools = [
                e for e in after
                if e.kind == "tool_started" and (not e.tool_call_id or e.tool_call_id not in closed)
            ]
            # A tool_started with no id can't be paired; only trust it while it's the newest event.
            open_tools = [e for e in open_tools if e.tool_call_id or e is after[-1]]
            if open_tools:
                tool = open_tools[-1]
                return LiveState(state="executing", since=tool.occurred_at, tool_name=tool.tool_name, **common)
            last_step = max(
                (e.occurred_at for e in after if e.kind == "tool_ended"), default=turn.occurred_at
            )
            return LiveState(state="thinking", since=last_step, **common)
        if ended is not None:
            if ended.status == "failed" and now - ended.occurred_at < FAILURE_WINDOW:
                return LiveState(
                    state="degraded", since=ended.occurred_at,
                    reason=ended.error_type or "turn_failed", **common,
                )
            if ended.status == "completed" and now - ended.occurred_at < CONVERSING_WINDOW:
                return LiveState(state="conversing", since=ended.occurred_at, **common)

    if workspace_turn_started_at is not None:
        return LiveState(
            state="thinking", since=workspace_turn_started_at, source="workspace",
            platform="workspace", counterpart_kind="owner",
            last_event_at=last_event_at, **counters,
        )
    if pending_count > 0:
        return LiveState(state="waiting", since=last_event_at, last_event_at=last_event_at, **counters)
    return LiveState(state="idle", since=last_event_at, last_event_at=last_event_at, **counters)
