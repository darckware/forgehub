"""Idempotent agent commands: receipts, limits and the tools switch (M0.2a).

Contract: docs/architecture/MCP_MISSION_TOOLS_SPEC.md §0.4 (idempotency),
§0.6 (``MISSION_TOOLS_ENABLED``) and §5 (64 KiB body, 60 writes/min per agent).
Reusable by every mission write route (M0.2a-d). The pattern a route follows::

    # route: dependencies=[Depends(limit_command_body)]  # 64 KiB, before parsing
    enforce_command_limits(principal)                   # switch, rate
    replay = await begin_command(db, principal, key, command, body_hash)
    if replay is not None:
        return replay                                   # 200 + Idempotent-Replay: true
    ... do the effect, without committing ...
    record_command(db, principal, key, command, body_hash, 201, out, target_type=..., target_id=...)
    await db.commit()                                   # effect + receipt, one transaction

``begin_command`` takes a transaction-scoped advisory lock on (principal,
key), so two concurrent calls with the same key serialize: the second one
sees the first one's receipt instead of acting a second time.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import ActorPrincipal
from app.db.models.command_receipt import RECEIPT_RETENTION_DAYS, AgentCommandReceipt

MAX_COMMAND_BODY_BYTES = 64 * 1024
AGENT_WRITES_PER_MINUTE = 60
REPLAY_HEADER = "Idempotent-Replay"


def command_error(status_code: int, code: str, message: str, **context: Any) -> HTTPException:
    return HTTPException(status_code, detail={"code": code, "message": message, **context})


def request_hash(command: str, body: dict[str, Any]) -> str:
    """sha256 of the canonical JSON of the request (the key itself excluded,
    path parameters included by the caller in ``body``)."""
    canonical = json.dumps(
        jsonable_encoder({"command": command, **{k: v for k, v in body.items() if k != "idempotency_key"}}),
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Switch, size and rate (§0.6, §5)
# ---------------------------------------------------------------------------
class _WriteRateLimiter:
    """In-process sliding window per agent. One uvicorn worker serves the API,
    so a process-local counter is the whole picture; a restart resets it."""

    def __init__(self, limit: int, window_seconds: float = 60.0):
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[uuid.UUID, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, principal_id: uuid.UUID, now: float | None = None) -> float | None:
        """Record one write; return the seconds to wait when over the limit."""
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[principal_id]
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return self.window - (now - hits[0])
            hits.append(now)
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


agent_write_limiter = _WriteRateLimiter(AGENT_WRITES_PER_MINUTE)


def assert_mission_tools_enabled() -> None:
    if not settings.MISSION_TOOLS_ENABLED:
        raise command_error(503, "MISSION_TOOLS_DISABLED", "Mission tools are disabled (MISSION_TOOLS_ENABLED=false)")


def limit_command_body(request: Request) -> None:
    """Route dependency: refuses a body over 64 KiB before it is parsed (a
    dependency runs before body validation, so the 413 is not masked by a 422)."""
    length = request.headers.get("content-length")
    if length is not None and length.isdigit() and int(length) > MAX_COMMAND_BODY_BYTES:
        raise command_error(413, "PAYLOAD_TOO_LARGE", "Request body exceeds 64 KiB", limit=MAX_COMMAND_BODY_BYTES)


def require_mission_tools() -> None:
    """Route dependency form of assert_mission_tools_enabled."""
    assert_mission_tools_enabled()


def enforce_command_limits(principal: ActorPrincipal) -> None:
    """Switch first (nothing is read or written when off), then the per-agent
    rate. A person is admin-gated anyway, so the rate applies to agents only."""
    assert_mission_tools_enabled()
    if principal.principal_type == "agent":
        retry_after = agent_write_limiter.hit(principal.principal_id)
        if retry_after is not None:
            raise HTTPException(
                429,
                detail={"code": "RATE_LIMITED", "message": "More than 60 writes per minute",
                        "limit_per_minute": AGENT_WRITES_PER_MINUTE},
                headers={"Retry-After": str(max(1, int(retry_after + 0.999)))},
            )


# ---------------------------------------------------------------------------
# Receipts (§0.4)
# ---------------------------------------------------------------------------
async def begin_command(
    db: AsyncSession, principal: ActorPrincipal, idempotency_key: str, command: str, body_hash: str,
) -> JSONResponse | None:
    """Lock the key and return the replay of a previous call, or None to act.

    Raises 409 ``IDEMPOTENCY_KEY_REUSED`` when the key was used for another
    command or another body."""
    await db.execute(select(func.pg_advisory_xact_lock(
        func.hashtextextended(f"receipt:{principal.principal_type}:{principal.principal_id}:{idempotency_key}", 0)
    )))
    receipt = (await db.execute(select(AgentCommandReceipt).where(
        AgentCommandReceipt.principal_type == principal.principal_type,
        AgentCommandReceipt.principal_id == principal.principal_id,
        AgentCommandReceipt.idempotency_key == idempotency_key,
    ))).scalar_one_or_none()
    if receipt is None:
        return None
    if receipt.command != command or receipt.request_hash != body_hash:
        raise command_error(409, "IDEMPOTENCY_KEY_REUSED",
                            "This idempotency key was already used for a different request",
                            original_command=receipt.command)
    return JSONResponse(status_code=200, content=receipt.response_body, headers={REPLAY_HEADER: "true"})


def record_command(
    db: AsyncSession,
    principal: ActorPrincipal,
    idempotency_key: str,
    command: str,
    body_hash: str,
    response_status: int,
    response_body: Any,
    *,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
) -> AgentCommandReceipt:
    """Add the receipt to the session; the caller commits it with the effect."""
    receipt = AgentCommandReceipt(
        principal_type=principal.principal_type,
        principal_id=principal.principal_id,
        idempotency_key=idempotency_key,
        command=command,
        request_hash=body_hash,
        response_status=response_status,
        response_body=jsonable_encoder(response_body),
        target_type=target_type,
        target_id=target_id,
    )
    db.add(receipt)
    return receipt


async def run_command_receipt_retention(db: AsyncSession) -> int:
    """Delete receipts older than 30 days. Hard delete: a receipt only answers
    "did I already do this?" for a retry window; the AuditEvent is the record."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=RECEIPT_RETENTION_DAYS)
    result = await db.execute(delete(AgentCommandReceipt).where(AgentCommandReceipt.created_at < cutoff))
    await db.commit()
    return result.rowcount or 0
