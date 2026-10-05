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

def client_ops_error(status_code: int, code: str, message: str, **params: Any) -> HTTPException:
    """Error the Clients screens translate: `code` picks the text in the user's
    language (pt-BR/en/es, `clientOps.errors.<code>`), `params` fills it, and
    `message` (English) is only the fallback for other callers."""
    return HTTPException(status_code=status_code, detail={"code": code, "message": message, "params": params})


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
        raise client_ops_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "integration_not_configured",
            f"Darckware integration is not configured ({which} / DARCKWARE_API_URL).",
            setting=which,
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
        raise client_ops_error(
            status.HTTP_502_BAD_GATEWAY,
            "darckware_unreachable",
            f"Darckware unreachable: {exc.__class__.__name__}",
            error=exc.__class__.__name__,
        ) from exc

    if resp.status_code >= 500:
        raise client_ops_error(
            status.HTTP_502_BAD_GATEWAY,
            "darckware_error",
            f"Darckware error {resp.status_code}: {resp.text[:300]}",
            status=resp.status_code,
        )
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        if resp.status_code in (401, 403):
            # A credential problem on our side is an integration failure, not
            # the logged-in user's lack of permission.
            raise client_ops_error(
                status.HTTP_502_BAD_GATEWAY,
                "darckware_credential",
                f"Darckware refused ForgeHub's credential ({credential}): {detail}",
                credential=credential,
            )
        # Darckware's own reason (Portuguese, its data): shown as-is under a
        # translated "Darckware refused" prefix.
        raise client_ops_error(resp.status_code, "darckware_rejected", str(detail), reason=str(detail))
    return resp.json()
