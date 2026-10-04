"""HTTP client for Darckware's internal API (client demands, 2026-10-04).

Darckware is the CRM and source of truth for clients, tickets, demands and
every e-mail to a client; ForgeHub only operates it. Nothing read here is
cached as truth -- each call goes to Darckware.

Two credentials (see `DARCKWARE_*` in core/config.py): `agent` calls use the
agent token under `/api/internal/agent`, `approver` calls use the approver
token under `/api/internal/approver`. Darckware refuses an approval made
with the agent token, so the drafter can never approve its own text.

Error mapping: integration not configured -> 503; Darckware unreachable or
5xx -> 502; Darckware 4xx -> the same status and its `detail`, so a 409
("text changed after it was shown") or 422 ("recipient not linked") reaches
the screen as-is.
"""
from __future__ import annotations

from typing import Any, Literal

import httpx
from fastapi import HTTPException, status

from app.core.config import settings

Credential = Literal["agent", "approver"]

_TIMEOUT = httpx.Timeout(20.0, connect=5.0)
_BASE_PATHS: dict[Credential, str] = {
    "agent": "/api/internal/agent",
    "approver": "/api/internal/approver",
}

#: Swapped by tests for an `httpx.MockTransport`.
transport: httpx.AsyncBaseTransport | None = None


def is_configured() -> bool:
    return bool(settings.DARCKWARE_API_URL and settings.DARCKWARE_AGENT_TOKEN)


def _token(credential: Credential) -> str:
    return settings.DARCKWARE_AGENT_TOKEN if credential == "agent" else settings.DARCKWARE_APPROVER_TOKEN


async def request(
    method: str,
    path: str,
    *,
    credential: Credential = "agent",
    json: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    """Call Darckware and return the decoded JSON body."""
    token = _token(credential)
    if not settings.DARCKWARE_API_URL or not token:
        which = "DARCKWARE_APPROVER_TOKEN" if credential == "approver" else "DARCKWARE_AGENT_TOKEN"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Darckware integration is not configured ({which} / DARCKWARE_API_URL).",
        )
    clean_params = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
    url = f"{settings.DARCKWARE_API_URL.rstrip('/')}{_BASE_PATHS[credential]}{path}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, transport=transport) as client:
            resp = await client.request(
                method,
                url,
                json=json,
                params=clean_params,
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Darckware unreachable: {exc.__class__.__name__}",
        ) from exc

    if resp.status_code >= 500:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Darckware error {resp.status_code}: {resp.text[:300]}",
        )
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        if resp.status_code in (401, 403):
            # A credential problem on our side is an integration failure, not
            # the logged-in user's lack of permission.
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Darckware refused ForgeHub's credential ({credential}): {detail}",
            )
        raise HTTPException(status_code=resp.status_code, detail=detail)
    return resp.json()
