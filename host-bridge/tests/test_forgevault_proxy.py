"""forgevault_proxy.py: name/type validation, upsert = create or rotate, reveal,
and the vault never reached without the bridge token. ForgeVault is faked."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import forgevault_proxy  # noqa: E402

TOKEN = "t"
H = {"X-Bridge-Token": TOKEN}


def _check(token):
    if token != TOKEN:
        raise HTTPException(status_code=401)


class FakeVault:
    def __init__(self):
        self.secrets: dict[str, dict] = {}

    async def upsert(self, name, value, description, secret_type):
        if name in self.secrets:
            self.secrets[name]["versions"].append(value)
            return {"id": self.secrets[name]["id"], "created": False, "version": len(self.secrets[name]["versions"])}
        sid = f"{len(self.secrets):08d}-0000-0000-0000-000000000000"
        self.secrets[name] = {"id": sid, "versions": [value]}
        return {"id": sid, "created": True, "version": 1}

    async def reveal(self, secret_id):
        for s in self.secrets.values():
            if s["id"] == secret_id:
                return s["versions"][-1]
        raise HTTPException(status_code=404)


def _client():
    app = FastAPI()
    app.include_router(forgevault_proxy.make_forgevault_router(_check, FakeVault()))
    return TestClient(app)


def test_upsert_creates_then_rotates_and_reveal_returns_latest():
    c = _client()
    first = c.post("/v1/forgevault/secrets:upsert", json={"name": "WS_GAT_PC01_LOGIN", "value": "a1"}, headers=H).json()
    assert first["created"] is True
    second = c.post("/v1/forgevault/secrets:upsert", json={"name": "WS_GAT_PC01_LOGIN", "value": "b2"}, headers=H).json()
    assert second == {"id": first["id"], "created": False, "version": 2}
    assert c.post("/v1/forgevault/secrets:reveal", json={"id": first["id"]}, headers=H).json() == {"value": "b2"}


def test_rejects_bad_names_types_and_missing_token():
    c = _client()
    assert c.post("/v1/forgevault/secrets:upsert", json={"name": "ws_lower", "value": "x"}, headers=H).status_code == 400
    assert c.post("/v1/forgevault/secrets:upsert", json={"name": "WS_OK_NAME", "value": "x", "type": "Certificate"}, headers=H).status_code == 400
    assert c.post("/v1/forgevault/secrets:upsert", json={"name": "WS_OK_NAME", "value": "x"}).status_code == 401
