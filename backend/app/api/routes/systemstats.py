"""System-stats domain routes.

Backs the Dashboard's memory/disk card. Like chat/terminal, this domain has
no DB model -- it's a pure live proxy to the host bridge (host-bridge/app.py's
/v1/system-stats), since "the computer's" memory and disk only mean anything
read from the host, not this container's own cgroup view.
"""
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError

from app.api.schemas.systemstats import ServerMonitoringOut, SystemStatsOut
from app.core.deps import get_current_admin
from app.core.config import settings

router = APIRouter(prefix="/api/v1/system-stats", tags=["system-stats"])


@router.get("", response_model=SystemStatsOut)
async def get_system_stats() -> SystemStatsOut:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{settings.CHAT_BRIDGE_URL}/v1/system-stats",
            headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Chat bridge error: {resp.text[:500]}"
        )
    return SystemStatsOut.model_validate(resp.json())



MONITORING_SOURCES = ('memory', 'processes', 'network', 'connections', 'filesystems', 'directories', 'access', 'services', 'containers')


async def _read_monitoring() -> dict:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f'{settings.CHAT_BRIDGE_URL}/v1/server-monitoring',
                headers={'X-Bridge-Token': settings.CHAT_BRIDGE_TOKEN},
            )
            response.raise_for_status()
            return ServerMonitoringOut.model_validate(response.json()).model_dump(mode='json')
    except (httpx.HTTPError, ValueError, ValidationError) as exc:
        raise HTTPException(502, 'Server monitoring source unavailable') from exc


@router.get('/details', response_model=ServerMonitoringOut, dependencies=[Depends(get_current_admin)])
async def get_server_monitoring() -> ServerMonitoringOut:
    return ServerMonitoringOut.model_validate(await _read_monitoring())
