"""Remote-access router — controls a Cloudflare quick tunnel that exposes
the whole app (frontend + API, unified on one origin by frontend/nginx.conf)
to a temporary public *.trycloudflare.com URL. Backs the Dashboard's
remote-access card (see host-bridge/app.py's /v1/remote-access/* for the
actual cloudflared process management — this is a thin, admin-gated proxy).

Admin-only: flipping this on hands anyone with the link a login screen for
the whole app, and RequireAuthMiddleware (app/main.py) now guards every
other /api/v1/* route behind that login — but the decision to expose the
app publicly at all shouldn't be available to a non-admin user.
"""
import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import settings
from app.core.deps import get_current_admin
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/remote-access", tags=["remote-access"])


async def _bridge_call(method: str, path: str) -> dict:
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.request(
            method,
            f"{settings.CHAT_BRIDGE_URL}{path}",
            headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Chat bridge error: {resp.text[:500]}"
        )
    return resp.json()


@router.post("/start")
async def start(user: User = Depends(get_current_admin)) -> dict:
    return await _bridge_call("POST", "/v1/remote-access/start")


@router.post("/stop")
async def stop(user: User = Depends(get_current_admin)) -> dict:
    return await _bridge_call("POST", "/v1/remote-access/stop")


@router.get("/status")
async def get_status(user: User = Depends(get_current_admin)) -> dict:
    return await _bridge_call("GET", "/v1/remote-access/status")
