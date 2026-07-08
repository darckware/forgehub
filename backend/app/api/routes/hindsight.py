"""Hindsight memory control routes.

Mostly a read-only proxy to the host bridge because Hindsight runs in the
Hermes host environment, not inside the ForgeHub backend container --
/restart and /clear-log are the two admin-only exceptions that mutate host
state (container restart, log truncation).
"""
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.config import settings
from app.core.deps import get_current_admin
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/hindsight", tags=["hindsight"])


@router.get("/status")
async def get_hindsight_status() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{settings.CHAT_BRIDGE_URL}/v1/hindsight/status",
            headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Host-bridge error: {resp.text[:500]}",
        )
    return resp.json()


@router.post("/restart")
async def restart_hindsight(_admin: User = Depends(get_current_admin)) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.CHAT_BRIDGE_URL}/v1/docker/restart",
            headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
            json={"container_name": "hindsight"},
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Host-bridge error: {resp.text[:500]}",
        )
    data = resp.json()
    if not data.get("success"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(data.get("stderr") or data.get("stdout") or "Failed to restart Hindsight")[:500],
        )
    return data


class ClearLogIn(BaseModel):
    target: str  # "runtime" | "default" | "startup" -- matches /status's logs.* keys


@router.post("/clear-log")
async def clear_hindsight_log(
    payload: ClearLogIn, _admin: User = Depends(get_current_admin)
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{settings.CHAT_BRIDGE_URL}/v1/hindsight/clear-log",
            headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
            json={"target": payload.target},
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Host-bridge error: {resp.text[:500]}",
        )
    return resp.json()
