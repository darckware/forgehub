from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.vpn import (
    TailscaleApiKeyIn,
    TailscaleApiKeyStatus,
    TailnetPolicyAnalysisOut,
    TailnetPolicyCreate,
    TailnetPolicyOut,
    TailnetPolicyStateOut,
    TailnetPolicyVersionOut,
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
from app.core.tailnet_policy import SERVER_TAG, PolicyParseError, analyze_policy, parse_hujson
from app.db.models.governance import AuditEvent
from app.core.secrets import decrypt_secret, encrypt_secret
from app.core.tailscale_api import API_KEY_NAME
from app.db.models.vpn import RemoteAccessSecret, TailnetPolicyVersion, VpnOperationEvent

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


def _policy_out(row: TailnetPolicyVersion) -> TailnetPolicyOut:
    out = TailnetPolicyOut(id=row.id, note=row.note, saved_by=row.saved_by, created_at=row.created_at, content=row.content)
    try:
        analysis = analyze_policy(parse_hujson(row.content))
    except PolicyParseError as exc:
        out.parse_error = str(exc)
        return out
    out.analysis = TailnetPolicyAnalysisOut(**analysis.__dict__, server_tag=SERVER_TAG)
    return out


@router.get("/policy", response_model=TailnetPolicyStateOut)
async def get_tailnet_policy(
    version_id: uuid.UUID | None = None,
    _user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> TailnetPolicyStateOut:
    """The recorded tailnet policy (latest, or `version_id`), analyzed, plus
    the version history."""
    rows = list(
        (await db.execute(select(TailnetPolicyVersion).order_by(TailnetPolicyVersion.created_at.desc()).limit(50))).scalars()
    )
    current = next((r for r in rows if r.id == version_id), None) if version_id else (rows[0] if rows else None)
    if version_id and current is None:
        current = await db.get(TailnetPolicyVersion, version_id)
        if current is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Policy version not found")
    return TailnetPolicyStateOut(
        current=_policy_out(current) if current else None,
        versions=[TailnetPolicyVersionOut(id=r.id, note=r.note, saved_by=r.saved_by, created_at=r.created_at) for r in rows],
    )


@router.post("/policy", response_model=TailnetPolicyOut, status_code=status.HTTP_201_CREATED)
async def save_tailnet_policy(
    payload: TailnetPolicyCreate,
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> TailnetPolicyOut:
    """Records a pasted copy of the policy. Refused when it doesn't parse --
    a record that can't be read back is no record. Saving here does not
    change Tailscale; the admin console stays the place the policy is applied."""
    try:
        parse_hujson(payload.content)
    except PolicyParseError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    row = TailnetPolicyVersion(content=payload.content, note=(payload.note or "").strip() or None, saved_by=user.username)
    db.add(row)
    await db.flush()
    db.add(AuditEvent(entity_type="tailnet_policy", entity_id=row.id, event_type="recorded", actor=user.username,
                      payload={"note": row.note}))
    await db.commit()
    await db.refresh(row)
    return _policy_out(row)


async def _api_key_row(db: AsyncSession) -> RemoteAccessSecret | None:
    return (
        await db.execute(select(RemoteAccessSecret).where(RemoteAccessSecret.name == API_KEY_NAME))
    ).scalar_one_or_none()


def _api_key_status(row: RemoteAccessSecret | None) -> TailscaleApiKeyStatus:
    if row is None:
        return TailscaleApiKeyStatus(configured=False)
    try:
        hint = decrypt_secret(row.value_encrypted)[-4:]
    except ValueError:
        hint = None
    return TailscaleApiKeyStatus(configured=True, hint=hint, updated_by=row.updated_by, updated_at=row.updated_at)


@router.get("/tailscale-api-key", response_model=TailscaleApiKeyStatus)
async def get_tailscale_api_key_status(
    _user: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> TailscaleApiKeyStatus:
    """Whether the key "Enroll station" uses is configured. The key itself is
    never returned."""
    return _api_key_status(await _api_key_row(db))


@router.put("/tailscale-api-key", response_model=TailscaleApiKeyStatus)
async def set_tailscale_api_key(
    payload: TailscaleApiKeyIn,
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> TailscaleApiKeyStatus:
    row = await _api_key_row(db)
    if row is None:
        row = RemoteAccessSecret(name=API_KEY_NAME, value_encrypted="", updated_by=user.username)
        db.add(row)
    row.value_encrypted = encrypt_secret(payload.api_key)
    row.updated_by = user.username
    await db.flush()
    db.add(AuditEvent(entity_type="remote_access_secret", entity_id=row.id, event_type="tailscale_api_key_set",
                      actor=user.username, payload=None))
    await db.commit()
    await db.refresh(row)
    return _api_key_status(row)


@router.delete("/tailscale-api-key", response_model=TailscaleApiKeyStatus)
async def delete_tailscale_api_key(
    user: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> TailscaleApiKeyStatus:
    row = await _api_key_row(db)
    if row is not None:
        db.add(AuditEvent(entity_type="remote_access_secret", entity_id=row.id, event_type="tailscale_api_key_removed",
                          actor=user.username, payload=None))
        await db.delete(row)
        await db.commit()
    return TailscaleApiKeyStatus(configured=False)
