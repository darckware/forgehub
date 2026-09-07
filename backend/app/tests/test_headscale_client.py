"""Headscale policy rendering and host-bridge boundary tests."""

import json
import uuid
from datetime import datetime, timezone
from json import dumps

import pytest
from fastapi import HTTPException
from sqlalchemy import delete

from app.core import headscale_client as hc
from app.db.base import AsyncSessionLocal
from app.db.models.client import Client, Workstation, WorkstationPeerGrant


def test_slugify_client_name_uses_headscale_safe_fallback():
    assert hc.slugify_client_name("Clube de Tiro Gatling") == "clube-de-tiro-gatling"
    assert hc.slugify_client_name("  Multi   Space!! ") == "multi-space"
    assert hc.slugify_client_name("---") == "cliente"


def test_render_policy_is_deterministic_and_default_deny():
    result = hc.render_policy(["tag:cliente-b", "tag:cliente-a"], [])
    policy = json.loads(result)
    assert list(policy["tagOwners"]) == ["tag:cliente-a", "tag:cliente-b"]
    assert policy["hosts"] == {}
    assert policy["grants"] == [
        {"src": ["group:admins"], "dst": ["tag:cliente-a"], "ip": ["*"]},
        {"src": ["group:admins"], "dst": ["tag:cliente-b"], "ip": ["*"]},
    ]


def test_render_policy_adds_only_the_explicit_peer_direction():
    pair = hc.PeerPairIPs(
        alias_a="ws-a",
        ip_a="100.64.0.1",
        alias_b="ws-b",
        ip_b="100.64.0.2",
    )
    policy = json.loads(hc.render_policy(["tag:cliente-a"], [pair]))
    assert policy["hosts"] == {"ws-a": "100.64.0.1", "ws-b": "100.64.0.2"}
    assert {"src": ["ws-a"], "dst": ["ws-b"], "ip": ["*"]} in policy["grants"]
    assert {"src": ["ws-b"], "dst": ["ws-a"], "ip": ["*"]} not in policy["grants"]


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class FakeBridgeClient:
    calls: list[tuple[str, str, dict | None]] = []
    nodes = [
        {"given_name": "ws-host-a", "ip_addresses": ["100.64.0.1", "fd7a::1"]},
        {"given_name": "ws-host-b", "ip_addresses": ["100.64.0.2"]},
    ]

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def request(self, method, url, headers=None, json=None, **kwargs):
        self.calls.append((method, url, json))
        if url.endswith("/v1/exec"):
            command = (json or {}).get("command", "")
            stdout = dumps(self.nodes) if "nodes list" in command else ""
            return FakeResponse({"stdout": stdout, "stderr": "", "exit_code": 0})
        if url.endswith("/v1/fs/write"):
            return FakeResponse({"ok": True})
        raise AssertionError(f"unexpected bridge call: {method} {url}")


@pytest.mark.asyncio
async def test_list_node_ips_uses_first_ipv4(monkeypatch):
    monkeypatch.setattr(hc.httpx, "AsyncClient", FakeBridgeClient)
    assert await hc.list_node_ips() == {
        "ws-host-a": "100.64.0.1",
        "ws-host-b": "100.64.0.2",
    }


async def _create_active_grant():
    async with AsyncSessionLocal() as db:
        client = Client(
            name=f"Test Client {uuid.uuid4()}",
            headscale_tag=f"tag:cliente-{uuid.uuid4().hex[:8]}",
        )
        db.add(client)
        await db.flush()
        ws_a = Workstation(
            client_id=client.id,
            os_kind="linux",
            hostname="ws-host-a",
            device_token_hash=uuid.uuid4().hex,
            device_token_issued_at=datetime.now(timezone.utc),
        )
        ws_b = Workstation(
            client_id=client.id,
            os_kind="linux",
            hostname="ws-host-b",
            device_token_hash=uuid.uuid4().hex,
            device_token_issued_at=datetime.now(timezone.utc),
        )
        db.add_all([ws_a, ws_b])
        await db.flush()
        db.add(
            WorkstationPeerGrant(
                workstation_a_id=ws_a.id,
                workstation_b_id=ws_b.id,
                granted_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()
        return client.id, ws_a.id


async def _cleanup_client(client_id: uuid.UUID):
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Client).where(Client.id == client_id))
        await db.commit()


@pytest.mark.asyncio
async def test_rebuild_resolves_active_grants_and_pushes_full_policy(monkeypatch):
    FakeBridgeClient.calls = []
    FakeBridgeClient.nodes = [
        {"given_name": "ws-host-a", "ip_addresses": ["100.64.0.1"]},
        {"given_name": "ws-host-b", "ip_addresses": ["100.64.0.2"]},
    ]
    monkeypatch.setattr(hc.httpx, "AsyncClient", FakeBridgeClient)
    client_id, ws_a_id = await _create_active_grant()
    try:
        async with AsyncSessionLocal() as db:
            await hc.rebuild_and_push_policy(db)
        writes = [call for call in FakeBridgeClient.calls if call[1].endswith("/v1/fs/write")]
        assert len(writes) == 1
        policy = json.loads(writes[0][2]["content"])
        assert policy["hosts"][f"ws-{ws_a_id}"] == "100.64.0.1"
        assert len([call for call in FakeBridgeClient.calls if "policy set" in str(call[2])]) == 1
    finally:
        await _cleanup_client(client_id)


@pytest.mark.asyncio
async def test_rebuild_refuses_to_silently_omit_an_unresolved_active_grant(monkeypatch):
    FakeBridgeClient.calls = []
    FakeBridgeClient.nodes = []
    monkeypatch.setattr(hc.httpx, "AsyncClient", FakeBridgeClient)
    client_id, _ = await _create_active_grant()
    try:
        async with AsyncSessionLocal() as db:
            with pytest.raises(HTTPException) as error:
                await hc.rebuild_and_push_policy(db)
        assert error.value.status_code == 409
        assert not any(call[1].endswith("/v1/fs/write") for call in FakeBridgeClient.calls)
    finally:
        await _cleanup_client(client_id)
