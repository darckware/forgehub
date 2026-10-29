"""Tailscale API, for "Enroll station" (Remote Access, 2026-10-16).

The API key lives encrypted in `remote_access_secrets` ("tailscale_api_key");
it is used for one thing: minting a **single-use, pre-authorized, pre-tagged
auth key that expires in a day** for each station being enrolled. A leaked
enrollment script is then worth one device join with that one client's tag,
for a day -- unlike a reusable key pasted into every script.
"""
from __future__ import annotations

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.secrets import decrypt_secret
from app.db.models.vpn import RemoteAccessSecret

API_KEY_NAME = "tailscale_api_key"
AUTH_KEY_TTL_SECONDS = 24 * 3600


async def load_api_key(db: AsyncSession) -> str | None:
    row = (
        await db.execute(select(RemoteAccessSecret).where(RemoteAccessSecret.name == API_KEY_NAME))
    ).scalar_one_or_none()
    if row is None:
        return None
    try:
        return decrypt_secret(row.value_encrypted)
    except ValueError:
        return None


async def create_auth_key(api_key: str, tag: str, description: str, preauthorized: bool = True) -> str:
    """One-use auth key carrying `tag`. `preauthorized=False` leaves the device
    waiting for approval in the Tailscale console (the installers' choice).
    Raises HTTPException with a message a person can act on (wrong key, tag
    not owned, Tailscale down)."""
    body = {
        "capabilities": {
            "devices": {
                "create": {"reusable": False, "ephemeral": False, "preauthorized": preauthorized, "tags": [tag]}
            }
        },
        "expirySeconds": AUTH_KEY_TTL_SECONDS,
        "description": description[:50],
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{settings.TAILSCALE_API_URL.rstrip('/')}/tailnet/-/keys",
                json=body,
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Tailscale API unreachable: {type(exc).__name__}") from exc
    if resp.status_code in (401, 403):
        raise HTTPException(
            status_code=502,
            detail="Tailscale refused the API key (expired, revoked, or without permission to create auth keys)",
        )
    if resp.status_code != 200:
        try:
            message = resp.json().get("message")
        except ValueError:
            message = None
        raise HTTPException(status_code=502, detail=f"Tailscale API error: {message or resp.status_code}")
    key = resp.json().get("key")
    if not isinstance(key, str) or not key.startswith("tskey-"):
        raise HTTPException(status_code=502, detail="Tailscale API returned no auth key")
    return key
