"""ForgeRouter integration – trusted SSO for the embedded dashboard.

The ForgeRouter page embeds the external ForgeRouter dashboard (its own app,
own auth) in an iframe. This route lets an already-authenticated ForgeHub
admin skip ForgeRouter's login screen: the shared secret lives only in the
two backends' env (FORGEROUTER_SSO_SECRET here, FORGEHUB_SSO_SECRET there)
and is exchanged server-to-server for a short-lived ForgeRouter session
token, which the frontend hands to the iframe via a URL fragment.

Admin-only, same reasoning as the terminal routes: the ForgeRouter dashboard
manages provider credentials and agent keys, strictly more power than a
non-admin ForgeHub profile grants.
"""
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.core.deps import get_current_admin
from app.core.forgerouter_sync import read_recent_forgerouter_activity
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/forgerouter", tags=["forgerouter"])


class ForgeRouterActivityOut(BaseModel):
    request_id: str
    agent_name: str | None
    required_capability: str
    demand: str | None
    status: str
    created_at: str
    prompt_preview: str | None
    cost: float | None


@router.get("/activity")
async def forgerouter_activity(since_seconds: int = 120, limit: int = 200) -> list[ForgeRouterActivityOut]:
    """Recent `ai_router.route_events` rows -- see
    read_recent_forgerouter_activity's own docstring for what this is and
    isn't (per-LLM-call telemetry, not a per-tool-call log). Auth is the
    global RequireAuthMiddleware (any logged-in user), same as every other
    plain-read domain route -- this isn't admin-gated like /sso above
    because it doesn't touch provider credentials, just request metadata."""
    events = await read_recent_forgerouter_activity(since_seconds=since_seconds, limit=limit)
    return [
        ForgeRouterActivityOut(
            request_id=e.request_id,
            agent_name=e.agent_name,
            required_capability=e.required_capability,
            demand=e.demand,
            status=e.status,
            created_at=e.created_at.isoformat(),
            prompt_preview=e.prompt_preview,
            cost=e.cost,
        )
        for e in events
    ]


@router.post("/sso")
async def forgerouter_sso(user: User = Depends(get_current_admin)) -> dict:
    """Returns {token, username, must_change_password} from ForgeRouter's
    /auth/sso, or 503 when SSO isn't configured (frontend falls back to
    ForgeRouter's own login screen)."""
    if not settings.FORGEROUTER_SSO_SECRET:
        raise HTTPException(status_code=503, detail="ForgeRouter SSO is not configured")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.FORGEROUTER_URL}/auth/sso",
                headers={"X-SSO-Secret": settings.FORGEROUTER_SSO_SECRET},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"ForgeRouter unreachable: {exc}") from exc
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"ForgeRouter SSO error: {resp.text[:300]}")
    return resp.json()


# ---------------------------------------------------------------------------
# Global CLI ForgeRouter integration (Host Bridge proxy)
# ---------------------------------------------------------------------------

class ForgeRouterCliStatusOut(BaseModel):
    claude: bool
    codex: bool
    antigravity: bool


class ForgeRouterCliToggleIn(BaseModel):
    tool: str
    enabled: bool


class ForgeRouterCliToggleOut(BaseModel):
    tool: str
    enabled: bool
    config_path: str
    status: ForgeRouterCliStatusOut


def _bridge_headers() -> dict[str, str]:
    return {"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN}


async def _bridge_request(method: str, path: str, **kwargs) -> dict:
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.request(
            method, f"{settings.CHAT_BRIDGE_URL}{path}", headers=_bridge_headers(), **kwargs
        )
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=f"Chat bridge: {resp.text[:500]}")
    return resp.json()


@router.get("/cli-status", response_model=ForgeRouterCliStatusOut)
async def get_forgerouter_cli_status() -> ForgeRouterCliStatusOut:
    """Return the global CLI ForgeRouter status across Claude, Codex, and Antigravity."""
    data = await _bridge_request("GET", "/v1/forgerouter/cli-status")
    return ForgeRouterCliStatusOut(**data)


@router.put("/cli-toggle", response_model=ForgeRouterCliToggleOut)
async def set_forgerouter_cli_toggle(payload: ForgeRouterCliToggleIn) -> ForgeRouterCliToggleOut:
    """Toggle global ForgeRouter configuration for a CLI tool."""
    data = await _bridge_request("PUT", "/v1/forgerouter/cli-toggle", json=payload.model_dump())
    return ForgeRouterCliToggleOut(**data)
