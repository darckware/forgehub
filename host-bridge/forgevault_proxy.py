"""ForgeVault access for ForgeHub's Remote Access (2026-10-16, Marcelo: "todas
as senhas e key cadastradas no forgevault").

The ForgeHub backend runs in a container: it can't reach ForgeVault (bound to
the host's 127.0.0.1 only) and must not hold the vault token. This bridge runs
on the host and does both, narrowly:

* identity: the `forgehub-remote-access` service account, whose token is kept
  encrypted with the host's systemd credential key
  (~/.config/forgevault/forgehub-remote-access-token) and decrypted per call,
  never written anywhere in clear;
* scope: only the `infra/Production` environment recorded in
  ~/.config/forgevault/forgehub-remote-access.json -- the account's role exists
  nowhere else, so even a wrong call can't touch another project;
* three operations: upsert (create, or rotate = new immutable version) a secret
  by name, reveal one by id, and reveal one by name (a shared value a script
  reads at run time, e.g. the RustDesk server key). Names are restricted to UPPER_SNAKE so a
  request body can't smuggle anything else.

Values travel only in request/response bodies between the backend and this
bridge (bridge token required) and between this bridge and ForgeVault; they are
never logged.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Callable

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

CRED_DIR = Path(os.path.expanduser("~/.config/forgevault"))
STATE_FILE = CRED_DIR / "forgehub-remote-access.json"
TOKEN_FILE = CRED_DIR / "forgehub-remote-access-token"
TOKEN_NAME = "forgehub-remote-access-token"
NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,119}$")
SECRET_TYPES = ("Password", "GenericSecret", "SshPrivateKey", "ApiKey")


class VaultUnavailable(Exception):
    pass


def _state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, ValueError) as exc:
        raise VaultUnavailable("ForgeVault is not provisioned for ForgeHub (state file missing)") from exc


def _token() -> str:
    result = subprocess.run(
        ["systemd-creds", "decrypt", f"--name={TOKEN_NAME}", str(TOKEN_FILE), "-"],
        capture_output=True, text=True, timeout=10,
    )
    token = result.stdout.strip()
    if result.returncode != 0 or not token.startswith("fv_sa_"):
        raise VaultUnavailable("ForgeHub's ForgeVault credential can't be read")
    return token


class VaultClient:
    def __init__(self, base_url: str | None = None, token: Callable[[], str] = _token):
        self._token = token
        self._base = base_url

    def _url(self) -> str:
        return (self._base or _state().get("url") or "http://127.0.0.1:8080").rstrip("/")

    async def _call(self, method: str, path: str, body: dict | None = None) -> dict | list | None:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.request(
                    method, f"{self._url()}{path}", json=body,
                    headers={"Authorization": f"Bearer {self._token()}"},
                )
        except httpx.HTTPError as exc:
            raise VaultUnavailable(f"ForgeVault unreachable: {type(exc).__name__}") from exc
        if resp.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"ForgeVault refused ({resp.status_code})")
        return resp.json() if resp.content else None

    async def upsert(self, name: str, value: str, description: str | None, secret_type: str) -> dict:
        env_id = _state()["environmentId"]
        match = await self.find(name)
        if match:
            rotated = await self._call("POST", f"/api/v1/secrets/{match}/rotate", {"value": value})
            version = (rotated or {}).get("currentVersion") if isinstance(rotated, dict) else None
            return {"id": match, "created": False, "version": version}
        created = await self._call("POST", "/api/v1/secrets", {
            "environmentId": env_id, "name": name, "type": secret_type, "provider": "forgehub",
            "description": description, "value": value, "expiresAt": None,
        })
        return {"id": created["id"], "created": True, "version": 1}

    async def find(self, name: str) -> str | None:
        env_id = _state()["environmentId"]
        existing = await self._call("GET", f"/api/v1/secrets?environmentId={env_id}") or []
        return next((s["id"] for s in existing if s.get("name") == name), None)

    async def reveal(self, secret_id: str) -> str:
        got = await self._call("GET", f"/api/v1/secrets/{secret_id}/value?mode=REVEAL")
        value = (got or {}).get("credentials", {}).get("value") if isinstance(got, dict) else None
        if value is None:
            raise HTTPException(status_code=404, detail="Secret not readable")
        return value


class UpsertRequest(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    value: str = Field(min_length=1, max_length=20_000)
    description: str | None = Field(default=None, max_length=500)
    type: str = "Password"


class RevealRequest(BaseModel):
    id: str = Field(min_length=36, max_length=36)


class RevealByNameRequest(BaseModel):
    name: str = Field(min_length=3, max_length=120)


def make_forgevault_router(check_token: Callable[[str | None], None], client: VaultClient | None = None) -> APIRouter:
    router = APIRouter(prefix="/v1/forgevault")
    vault = client or VaultClient()

    @router.post("/secrets:upsert")
    async def upsert_secret(req: UpsertRequest, x_bridge_token: str | None = Header(default=None)) -> dict:
        check_token(x_bridge_token)
        if not NAME_RE.match(req.name):
            raise HTTPException(status_code=400, detail="Secret name must be UPPER_SNAKE_CASE")
        if req.type not in SECRET_TYPES:
            raise HTTPException(status_code=400, detail="Unsupported secret type")
        try:
            return await vault.upsert(req.name, req.value, req.description, req.type)
        except VaultUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.post("/secrets:reveal")
    async def reveal_secret(req: RevealRequest, x_bridge_token: str | None = Header(default=None)) -> dict:
        check_token(x_bridge_token)
        try:
            return {"value": await vault.reveal(req.id)}
        except VaultUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.post("/secrets:reveal-by-name")
    async def reveal_secret_by_name(req: RevealByNameRequest, x_bridge_token: str | None = Header(default=None)) -> dict:
        check_token(x_bridge_token)
        if not NAME_RE.match(req.name):
            raise HTTPException(status_code=400, detail="Secret name must be UPPER_SNAKE_CASE")
        try:
            secret_id = await vault.find(req.name)
            if secret_id is None:
                raise HTTPException(status_code=404, detail=f"Secret {req.name} not found in ForgeVault")
            return {"id": secret_id, "value": await vault.reveal(secret_id)}
        except VaultUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.get("/status")
    async def vault_status(x_bridge_token: str | None = Header(default=None)) -> dict:
        check_token(x_bridge_token)
        try:
            state = _state()
            _token()
            return {"configured": True, "environmentId": state.get("environmentId")}
        except VaultUnavailable as exc:
            return {"configured": False, "detail": str(exc)}

    return router
