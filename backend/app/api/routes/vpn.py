from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.vpn import (
    VpnActionRequest,
    VpnActionResult,
    VpnNode,
    VpnOperationsOut,
    VpnOperationOut,
    VpnStatus,
)
from app.core.config import settings
from app.core.deps import get_current_admin
from app.db.base import get_db
from app.db.models.user import User
from app.db.models.vpn import VpnOperationEvent

router = APIRouter(prefix="/api/v1/vpn", tags=["vpn"])

SELF_NODE = "self"
SELF_ACTIONS = frozenset({"restart"})
PEER_ACTIONS = frozenset({"test"})
# Tailscale stable node IDs ("nKqVMEy38E11CNTRL"). The bridge re-validates and
# resolves the address from a fresh status read; this only rejects garbage early.
_PEER_ID_RE = re.compile(r"^[A-Za-z0-9]{1,64}$")
_LOGIN_URL_RE = re.compile(r"https://login\.tailscale\.com/\S+", re.IGNORECASE)
_PRIVATE_PATH_RE = re.compile(r"/root/(?:\.ssh|agents|\.hermes)/\S+")


def validate_action(node: str, action: str) -> str:
    """Returns the operation's target kind ("self" or "peer")."""
    if node == SELF_NODE:
        if action in SELF_ACTIONS:
            return SELF_NODE
    elif _PEER_ID_RE.fullmatch(node) and action in PEER_ACTIONS:
        return "peer"
    raise ValueError("action_not_allowed")


def sanitize_summary(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return "VPN operation requires attention."
    if _LOGIN_URL_RE.search(value) or _PRIVATE_PATH_RE.search(value):
        return "VPN operation requires attention."
    return value.strip()[:500]


def normalize_status(payload: dict[str, Any], *, checked_at: datetime | None = None) -> VpnStatus:
    raw_server = payload.get("self")
    if not isinstance(raw_server, dict):
        raw_server = {"id": SELF_NODE, "state": "unavailable"}
    peers = []
    raw_peers = payload.get("peers")
    if isinstance(raw_peers, list):
        for raw in raw_peers:
            if isinstance(raw, dict):
                try:
                    peers.append(VpnNode.model_validate(raw))
                except ValueError:
                    continue
    error = payload.get("error")
    source_error = sanitize_summary(error.get("summary")) if isinstance(error, dict) else None
    return VpnStatus(
        backend_state=str(payload.get("backend_state", "Unavailable")),
        server=VpnNode.model_validate({**raw_server, "id": SELF_NODE}),
        peers=peers,
        checked_at=checked_at or datetime.now(timezone.utc),
        source_error=source_error,
        sources=payload.get("sources", []),
    )


async def _bridge_call(method: str, path: str, payload: dict | None = None) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=35.0) as client:
            response = await client.request(
                method,
                f"{settings.CHAT_BRIDGE_URL}{path}",
                headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, "VPN bridge timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "VPN bridge is unavailable") from exc
    if response.status_code != 200:
        try:
            bridge_error = response.json().get("detail")
        except (ValueError, AttributeError):
            bridge_error = None
        # An operation that ran and failed (device offline, no reply, timeout)
        # is a result to record and show, not a transport error.
        if isinstance(bridge_error, dict) and isinstance(bridge_error.get("code"), str):
            return {"success": False, **bridge_error}
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "VPN bridge rejected the operation")
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "VPN bridge returned invalid data") from exc
    if not isinstance(data, dict):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "VPN bridge returned invalid data")
    return data


async def fetch_tailnet_status() -> VpnStatus:
    """The tailnet as this server sees it. Never raises: an unreachable bridge
    reads as an "unavailable" server with no peers, which callers must treat as
    "unknown", not as every device being offline. Shared with the server
    inventory's tailnet sync and readiness (api/routes/server.py)."""
    try:
        payload = await _bridge_call("GET", "/v1/vpn/status")
    except HTTPException:
        payload = {
            "backend_state": "Unavailable",
            "self": {"id": SELF_NODE, "state": "unavailable"},
            "peers": [],
            "error": {"summary": "VPN bridge is unavailable."},
        }
    return normalize_status(payload)


@router.get("/status", response_model=VpnStatus)
async def get_vpn_status(_user: User = Depends(get_current_admin)) -> VpnStatus:
    return await fetch_tailnet_status()


@router.post("/nodes/{node}/actions", response_model=VpnActionResult)
async def run_vpn_action(
    node: str,
    request: VpnActionRequest,
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> VpnActionResult:
    """`node` is "self" (this server: restart) or a peer's stable Tailscale ID
    (test). Connect/disconnect were removed on 2026-10-15: on this host they
    would rename the VPS or cut the only private path to the clients."""
    try:
        target = validate_action(node, request.action)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "action_not_allowed") from exc

    event = VpnOperationEvent(
        actor_user_id=user.id,
        target=target,
        target_node_id=None if target == SELF_NODE else node,
        action=request.action,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    db.add(event)
    await db.commit()
    try:
        result = await _bridge_call("POST", f"/v1/vpn/nodes/{node}/actions", {"action": request.action})
    except HTTPException as exc:
        event.status = "failed"
        event.result_code = "timeout" if exc.status_code == status.HTTP_504_GATEWAY_TIMEOUT else "bridge_error"
        event.summary = sanitize_summary(exc.detail)
        event.completed_at = datetime.now(timezone.utc)
        await db.commit()
        raise
    success = result.get("success") is True
    target_name = result.get("target_name")
    event.status = "succeeded" if success else "failed"
    event.result_code = str(result.get("code", "ok" if success else "command_failed"))[:50]
    event.summary = sanitize_summary(result.get("summary"))
    event.target_name = target_name[:255] if isinstance(target_name, str) else None
    event.completed_at = datetime.now(timezone.utc)
    await db.commit()
    latency = result.get("latency_ms")
    path = result.get("kind")
    return VpnActionResult(
        success=success,
        code=event.result_code or "command_failed",
        summary=event.summary or "VPN operation requires attention.",
        operation_id=event.id,
        target_name=event.target_name,
        latency_ms=float(latency) if isinstance(latency, (int, float)) else None,
        path=path if path in {"direct", "derp"} else None,
    )


@router.get("/operations", response_model=VpnOperationsOut)
async def list_vpn_operations(
    limit: int = Query(default=25, ge=1, le=100),
    _user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> VpnOperationsOut:
    rows = list(
        (
            await db.execute(
                select(VpnOperationEvent)
                .order_by(VpnOperationEvent.created_at.desc())
                .limit(limit)
            )
        ).scalars()
    )
    operations = [
        VpnOperationOut(
            id=row.id,
            actor_username=getattr(row.actor, "username", None),
            target=row.target,
            target_name=row.target_name,
            action=row.action,
            status=row.status,
            result_code=row.result_code,
            summary=row.summary,
            started_at=row.started_at,
            completed_at=row.completed_at,
            created_at=row.created_at,
        )
        for row in rows
    ]
    return VpnOperationsOut(operations=operations, limit=limit)
