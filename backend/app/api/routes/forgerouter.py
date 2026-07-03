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

from app.core.config import settings
from app.core.deps import get_current_admin
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/forgerouter", tags=["forgerouter"])


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
