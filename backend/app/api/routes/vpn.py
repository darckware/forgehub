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
    VpnConnection,
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

ALLOWED_ACTIONS = {
    "local": frozenset({"connect", "disconnect", "restart", "test"}),
    "remote": frozenset({"restart", "test"}),
}
_LOGIN_URL_RE = re.compile(r"https://login\.tailscale\.com/\S+", re.IGNORECASE)
_PRIVATE_PATH_RE = re.compile(r"/root/(?:\.ssh|agents|\.hermes)/\S+")


def validate_action(node: str, action: str) -> tuple[str, str]:
    if node not in ALLOWED_ACTIONS or action not in ALLOWED_ACTIONS[node]:
        raise ValueError("action_not_allowed")
    return node, action


def sanitize_summary(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return "VPN operation requires attention."
    if _LOGIN_URL_RE.search(value) or _PRIVATE_PATH_RE.search(value):
        return "VPN operation requires attention."
    return value.strip()[:500]


def normalize_status(payload: dict[str, Any], *, checked_at: datetime | None = None) -> VpnStatus:
    nodes = []
    for role in ("local", "remote"):
        raw = payload.get(role)
        if not isinstance(raw, dict):
            raw = {"role": role, "state": "unavailable"}
        nodes.append(VpnNode.model_validate({"role": role, **raw}))
    raw_connection = payload.get("connection")
    if not isinstance(raw_connection, dict):
        raw_connection = {"kind": "unavailable"}
    error = payload.get("error")
    source_error = sanitize_summary(error.get("summary")) if isinstance(error, dict) else None
    return VpnStatus(
        backend_state=str(payload.get("backend_state", "Unavailable")),
        nodes=nodes,
        connection=VpnConnection.model_validate(raw_connection),
        checked_at=checked_at or datetime.now(timezone.utc),
        source_error=source_error,
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
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "VPN bridge rejected the operation")
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "VPN bridge returned invalid data") from exc
    if not isinstance(data, dict):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "VPN bridge returned invalid data")
    return data


@router.get("/status", response_model=VpnStatus)
async def get_vpn_status(_user: User = Depends(get_current_admin)) -> VpnStatus:
    try:
        payload = await _bridge_call("GET", "/v1/vpn/status")
    except HTTPException:
        payload = {
            "backend_state": "Unavailable",
            "local": {"role": "local", "state": "unavailable"},
            "remote": {"role": "remote", "state": "unavailable"},
            "connection": {"kind": "unavailable"},
            "error": {"summary": "VPN bridge is unavailable."},
        }
    return normalize_status(payload)


@router.post("/nodes/{node}/actions", response_model=VpnActionResult)
async def run_vpn_action(
    node: str,
    request: VpnActionRequest,
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> VpnActionResult:
    try:
        validate_action(node, request.action)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "action_not_allowed") from exc

    now = datetime.now(timezone.utc)
    event = VpnOperationEvent(
        actor_user_id=user.id,
        target=node,
        action=request.action,
        status="running",
        started_at=now,
    )
    db.add(event)
    await db.commit()
    try:
        result = await _bridge_call(
            "POST",
            f"/v1/vpn/nodes/{node}/actions",
            {"action": request.action},
        )
        success = result.get("success") is True
        event.status = "succeeded" if success else "failed"
        event.result_code = str(result.get("code", "ok" if success else "command_failed"))[:50]
        event.summary = sanitize_summary(result.get("summary"))
    except HTTPException as exc:
        event.status = "failed"
        event.result_code = "bridge_error"
        event.summary = sanitize_summary(exc.detail)
        event.completed_at = datetime.now(timezone.utc)
        await db.commit()
        raise
    event.completed_at = datetime.now(timezone.utc)
    await db.commit()
    return VpnActionResult(
        success=success,
        code=event.result_code or "command_failed",
        summary=event.summary or "VPN operation requires attention.",
        operation_id=event.id,
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
