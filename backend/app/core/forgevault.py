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

Since 2026-11-12 every machine secret ForgeHub writes goes under a FRESH name,
`WS_<CLIENT>_<MACHINE>_<SUFFIX>_<PURPOSE>` (`fresh_machine_secret_name`). The
bridge's upsert rotates whatever secret already has the name, and a machine
renamed or moved to another client keeps its old name in the vault, so a name
computed from the row could belong to another machine -- writing under it
would replace that machine's key or password (rule 3, one key per machine).
The bridge has no lookup that returns a name's id without its value (only
`secrets:reveal-by-name`, which reads the secret and would itself be an SSH
key read for ECO-060), so a fresh name, which upsert can only create, is the
one write that can never land on someone else's secret. The purpose stays the
last segment, so `*_SSH_KEY`/`*_LOGIN` still say what a secret is.
"""
from __future__ import annotations

import re
import unicodedata
import uuid

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


def fresh_machine_secret_name(server, purpose: str) -> str:
    """WS_<CLIENT>_<MACHINE>_<SUFFIX>_<PURPOSE>: a name no secret has yet
    (12 random hex digits), at most 120 chars, purpose kept intact at the end.
    The one name every machine-secret write uses -- see the module docstring."""
    suffix = uuid.uuid4().hex[:12].upper()
    tail = f"_{suffix}_{purpose}"
    client = _slug(server.darckware_client_name, "SEM_CLIENTE")[:40]
    machine = _slug(server.name, "MAQUINA")[:50]
    head = f"WS_{client}_{machine}"[: 120 - len(tail)].rstrip("_")
    return f"{head}{tail}"


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
