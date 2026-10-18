"""Tool-versions domain routes.

Backs the Dashboard's "Tool Versions" card. Every actual version check and
update command runs on the HOST via the chat bridge (host-bridge/app.py's
/v1/tool-versions endpoints -- same proxy pattern as the chat/terminal
domains, see their route modules); this router only persists the
last-known result per tool (so the Dashboard has something to render
without a host round-trip on every page load) and the on/off state of the
periodic background poll (see app/main.py's startup hook).
"""
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.toolversions import (
    ToolInstallResult,
    ToolSyncSettingOut,
    ToolSyncSettingUpdate,
    ToolUpdateResult,
    ToolVersionOut,
)
from app.core.config import settings
from app.db.base import get_db
from app.db.models.toolversions import (
    MONITORED_TOOLS,
    SYNC_SETTING_ID,
    ToolSyncSetting,
    ToolVersionStatus,
)

router = APIRouter(prefix="/api/v1/tool-versions", tags=["tool-versions"])


class ForgeRouterConfigUpdate(BaseModel):
    enabled: bool
    api_key: str = ""

# Periodic background poll checks all monitored tools, passing POLL_NO_MUTATE
# so antigravity's installed version (`agy --version`) stays up-to-date in the
# DB without running a mutating `agy update` (antigravity already has its own
# ~15min auto-updater on the host; explicit user "Check now" or "Update" clicks
# still run the full check/update).
POLL_TOOLS = MONITORED_TOOLS
POLL_NO_MUTATE = ("antigravity",)


def _bridge_headers() -> dict[str, str]:
    return {"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN}


async def get_or_create_sync_setting(db: AsyncSession) -> ToolSyncSetting:
    result = await db.execute(select(ToolSyncSetting).where(ToolSyncSetting.id == SYNC_SETTING_ID))
    setting = result.scalar_one_or_none()
    if setting is not None:
        return setting
    setting = ToolSyncSetting(id=SYNC_SETTING_ID, enabled=True)
    db.add(setting)
    try:
        await db.commit()
    except IntegrityError:
        # Lost a create-on-first-read race (e.g. against the background poll
        # loop's own session) -- the fixed id means the other writer's row
        # is the same singleton, so just re-select it.
        await db.rollback()
        result = await db.execute(select(ToolSyncSetting).where(ToolSyncSetting.id == SYNC_SETTING_ID))
        setting = result.scalar_one()
    else:
        await db.refresh(setting)
    return setting


async def _get_or_create_status_row(db: AsyncSession, tool: str) -> ToolVersionStatus:
    result = await db.execute(select(ToolVersionStatus).where(ToolVersionStatus.tool == tool))
    row = result.scalar_one_or_none()
    if row is not None:
        return row
    row = ToolVersionStatus(tool=tool)
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        # Lost a create-on-first-read race -- `tool` is unique, so re-select
        # the row the other writer just created instead of erroring out.
        await db.rollback()
        result = await db.execute(select(ToolVersionStatus).where(ToolVersionStatus.tool == tool))
        row = result.scalar_one()
    else:
        await db.refresh(row)
    return row


async def refresh_all_tool_versions(
    db: AsyncSession, tools: tuple[str, ...] = MONITORED_TOOLS, no_mutate: tuple[str, ...] = ()
) -> list[ToolVersionStatus]:
    """Call the host bridge for the given tools and persist the results.
    Shared by the manual POST /check route, the post-update/install refresh,
    and the periodic background poll in app/main.py (which passes
    `no_mutate=POLL_NO_MUTATE` so antigravity is checked via `agy --version`
    without running `agy update`).

    `no_mutate`: passed through to the host bridge so it can skip running
    a real `agy update` for antigravity during periodic polls or right after
    an explicit update/install."""
    params: dict[str, str] = {"tools": ",".join(tools)}
    if no_mutate:
        params["no_mutate"] = ",".join(no_mutate)
    async with httpx.AsyncClient(timeout=650.0) as client:
        resp = await client.get(
            f"{settings.CHAT_BRIDGE_URL}/v1/tool-versions", params=params, headers=_bridge_headers()
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Chat bridge error: {resp.text[:500]}"
        )
    results = resp.json()

    rows = []
    for tool in tools:
        row = await _get_or_create_status_row(db, tool)
        if tool in results:
            data = results[tool]
            row.installed_version = data.get("installed_version")
            row.latest_version = data.get("latest_version")
            row.update_available = bool(data.get("update_available"))
            row.last_error = data.get("error")
        rows.append(row)
    await db.commit()
    for row in rows:
        await db.refresh(row)
    return rows


@router.get("", response_model=list[ToolVersionOut])
async def list_tool_versions(db: AsyncSession = Depends(get_db)) -> list[ToolVersionStatus]:
    """The last-known status per tool, from the DB cache -- does not hit the
    host. Use POST /check to force a fresh check."""
    rows = [await _get_or_create_status_row(db, tool) for tool in MONITORED_TOOLS]
    return rows


@router.post("/check", response_model=list[ToolVersionOut])
async def check_tool_versions(db: AsyncSession = Depends(get_db)) -> list[ToolVersionStatus]:
    """Force an immediate check of every monitored tool via the host bridge."""
    return await refresh_all_tool_versions(db)


@router.post("/{tool}/update", response_model=ToolUpdateResult)
async def update_tool(tool: str, db: AsyncSession = Depends(get_db)) -> ToolUpdateResult:
    """Run the tool's real update command on the host, then refresh and
    return its status row."""
    if tool not in MONITORED_TOOLS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown tool: {tool}")

    async with httpx.AsyncClient(timeout=650.0) as client:
        resp = await client.post(
            f"{settings.CHAT_BRIDGE_URL}/v1/tool-versions/update",
            json={"tool": tool},
            headers=_bridge_headers(),
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Chat bridge error: {resp.text[:500]}"
        )
    update_result = resp.json()

    # tools=(tool,), no_mutate=(tool,): refresh only the updated tool and skip
    # running `agy update` a second time for antigravity.
    rows = await refresh_all_tool_versions(db, tools=(tool,), no_mutate=(tool,))
    row = next(r for r in rows if r.tool == tool)
    return ToolUpdateResult(
        success=update_result["success"],
        output=update_result["output"],
        error=update_result.get("error"),
        status=ToolVersionOut.model_validate(row),
    )


@router.post("/{tool}/install", response_model=ToolInstallResult)
async def install_tool(tool: str, db: AsyncSession = Depends(get_db)) -> ToolInstallResult:
    """Run the tool's installation command on the host, then refresh and
    return its status row."""
    if tool not in MONITORED_TOOLS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown tool: {tool}")

    async with httpx.AsyncClient(timeout=650.0) as client:
        resp = await client.post(
            f"{settings.CHAT_BRIDGE_URL}/v1/tool-versions/install",
            json={"tool": tool},
            headers=_bridge_headers(),
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Chat bridge error: {resp.text[:500]}"
        )
    install_result = resp.json()

    rows = await refresh_all_tool_versions(db, tools=(tool,), no_mutate=(tool,))
    row = next(r for r in rows if r.tool == tool)
    return ToolInstallResult(
        success=install_result["success"],
        output=install_result["output"],
        error=install_result.get("error"),
        status=ToolVersionOut.model_validate(row),
    )


@router.get("/sync", response_model=ToolSyncSettingOut)
async def get_sync_setting(db: AsyncSession = Depends(get_db)) -> ToolSyncSetting:
    return await get_or_create_sync_setting(db)


@router.put("/sync", response_model=ToolSyncSettingOut)
async def update_sync_setting(
    body: ToolSyncSettingUpdate, db: AsyncSession = Depends(get_db)
) -> ToolSyncSetting:
    setting = await get_or_create_sync_setting(db)
    setting.enabled = body.enabled
    await db.commit()
    await db.refresh(setting)
    return setting


@router.put("/{tool}/forgerouter-config")
async def set_forgerouter_config(tool: str, body: ForgeRouterConfigUpdate) -> dict:
    if tool not in {"claude", "codex"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ForgeRouter configuration is supported only for Claude and Codex")
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.put(
            f"{settings.CHAT_BRIDGE_URL}/v1/tool-integrations/{tool}",
            json=body.model_dump(), headers=_bridge_headers(),
        )
    if response.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Chat bridge error: {response.text[:500]}")
    return response.json()
