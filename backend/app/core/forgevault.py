"""ForgeVault for Remote Access machine secrets (2026-10-16, Marcelo: "todas as
senhas e key cadastradas no forgevault").

The backend never talks to ForgeVault directly and never holds its token: the
host-bridge does (host-bridge/forgevault_proxy.py), with the
`forgehub-remote-access` service account scoped to `infra/Production` only.
ForgeHub keeps just the secret's id on the machine row (`*_ref`).

Secret names follow the plan's convention, one per machine and purpose:
`WS_<CLIENT>_<MACHINE>_LOGIN` (the `darckware` account) and
`WS_<CLIENT>_<MACHINE>_RUSTDESK` (RustDesk permanent password). Every write is
a new immutable version in the vault, so a rotation never loses the previous
value's history.
"""
from __future__ import annotations

import re
import unicodedata

import httpx
from fastapi import HTTPException

from app.core.config import settings


class VaultUnavailable(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=503, detail=detail)


def _slug(value: str | None, fallback: str) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().upper()
    text = re.sub(r"[^A-Z0-9]+", "_", text).strip("_")
    return text or fallback


def machine_secret_name(server, purpose: str) -> str:
    """WS_<CLIENT>_<MACHINE>_<PURPOSE>, upper snake, at most 120 chars."""
    client = _slug(server.darckware_client_name, "SEM_CLIENTE")[:40]
    machine = _slug(server.name, "MAQUINA")[:50]
    return f"WS_{client}_{machine}_{purpose}"[:120]


async def _bridge(path: str, body: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.CHAT_BRIDGE_URL}/v1/forgevault/{path}",
                json=body,
                headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
            )
    except httpx.HTTPError as exc:
        raise VaultUnavailable("ForgeVault unreachable (host bridge down)") from exc
    if resp.status_code != 200:
        try:
            detail = resp.json().get("detail")
        except ValueError:
            detail = None
        raise VaultUnavailable(f"ForgeVault: {detail or resp.status_code}")
    return resp.json()


async def vault_store(name: str, value: str, description: str, secret_type: str = "Password") -> str:
    """Creates the secret or records a new version; returns its id."""
    result = await _bridge("secrets:upsert", {"name": name, "value": value, "description": description, "type": secret_type})
    return result["id"]


async def vault_reveal(secret_id: str) -> str:
    return (await _bridge("secrets:reveal", {"id": secret_id}))["value"]


async def vault_reveal_name(name: str) -> str:
    """A shared secret by its name (e.g. RUSTDESK_SERVER_KEY); 503 when missing or unreadable."""
    return (await _bridge("secrets:reveal-by-name", {"name": name}))["value"]
