"""Rule 3 of remote access: one SSH key per machine (Marcelo, 2026-11-12).

No write path may give a machine a key (identified by its public blob, or by
its ForgeVault secret id) that another machine row already has. ForgeVault and
the host bridge are stubbed; every key here is a throwaway generated in
process -- never a real one.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.api.routes import server as server_routes
from app.core import ssh_key_uniqueness as uniq
from app.db.base import AsyncSessionLocal
from app.db.models.governance import AuditEvent
from app.db.models.server import Server


def _keypair(passphrase: bytes | None = None, kind: str = "ed25519") -> tuple[str, str]:
    key = ed25519.Ed25519PrivateKey.generate() if kind == "ed25519" else rsa.generate_private_key(65537, 2048)
    encryption = serialization.BestAvailableEncryption(passphrase) if passphrase else serialization.NoEncryption()
    fmt = serialization.PrivateFormat.OpenSSH if kind == "ed25519" else serialization.PrivateFormat.PKCS8
    private = key.private_bytes(serialization.Encoding.PEM, fmt, encryption).decode()
    public = key.public_key().public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode()
    return private, public


# --- pure helpers -------------------------------------------------------------


def test_blob_ignores_comment_and_rejects_garbage():
    _, public = _keypair()
    assert uniq.public_key_blob(public) == uniq.public_key_blob(f"{public} forgehub@pc01")
    assert uniq.public_key_blob("ssh-ed25519 not-base64!") is None
    assert uniq.public_key_blob("hunter2") is None
    # Type in the line must match the type inside the blob.
    assert uniq.public_key_blob(public.replace("ssh-ed25519", "ssh-rsa")) is None


@pytest.mark.parametrize("kind", ["ed25519", "rsa"])
def test_public_key_is_derived_from_openssh_and_pem(kind):
    private, public = _keypair(kind=kind)
    assert uniq.public_key_blob(uniq.derive_public_key(private)) == uniq.public_key_blob(public)


def test_encrypted_key_derives_only_with_its_passphrase():
    private, public = _keypair(passphrase=b"frase-de-teste")
    with pytest.raises(ValueError):
        uniq.derive_public_key(private)
    assert uniq.public_key_blob(uniq.derive_public_key(private, "frase-de-teste")) == uniq.public_key_blob(public)


def test_duplicate_report_groups_by_public_key_ref_and_file():
    _, public = _keypair()
    a = Server(id=uuid.uuid4(), name="a", ip_address="x", remote_user="u", ssh_key_path="/root/.ssh/shared")
    b = Server(id=uuid.uuid4(), name="b", ip_address="x", remote_user="u", ssh_key_path="/root/.ssh/shared")
    c = Server(id=uuid.uuid4(), name="c", ip_address="x", remote_user="u", ssh_key_ref="ref-1")
    d = Server(id=uuid.uuid4(), name="d", ip_address="x", remote_user="u", ssh_key_ref="ref-1")
    e = Server(id=uuid.uuid4(), name="e", ip_address="x", remote_user="u")
    f = Server(id=uuid.uuid4(), name="f", ip_address="x", remote_user="u")
    e.public_key, f.public_key = public, f"{public} other-comment"
    lone = Server(id=uuid.uuid4(), name="lone", ip_address="x", remote_user="u", ssh_key_ref="ref-2")
    report = uniq.duplicate_keys_by_server([a, b, c, d, e, f, lone])
    assert report[a.id] == ["b"] and report[c.id] == ["d"] and report[f.id] == ["e"]
    assert lone.id not in report


# --- routes -------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(admin_headers):
    app = FastAPI()
    app.include_router(server_routes.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=admin_headers) as ac:
        yield ac


@pytest_asyncio.fixture
async def machines():
    """Two throwaway rows: `owner` already holds a key, `other` is the target."""
    _, owner_public = _keypair()
    tag = uuid.uuid4().hex[:8]
    owner = Server(name=f"uniq-owner-{tag}", ip_address="192.0.2.10", remote_user="darckware",
                   kind="workstation", os_family="windows", ssh_key_ref=str(uuid.uuid4()))
    owner.public_key = owner_public
    other = Server(name=f"uniq-other-{tag}", ip_address="192.0.2.11", remote_user="administrador",
                   kind="workstation", os_family="windows")
    async with AsyncSessionLocal() as db:
        db.add_all([owner, other])
        await db.commit()
    yield owner, other, owner_public
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_([owner.id, other.id])))
        await db.execute(delete(Server).where(Server.id.in_([owner.id, other.id])))
        await db.commit()


def _vault_store(ref: str | None = None):
    return AsyncMock(side_effect=lambda *a, **k: ref or str(uuid.uuid4()))


async def _row(server_id):
    async with AsyncSessionLocal() as db:
        return await db.get(Server, server_id)


@pytest.mark.asyncio
async def test_public_key_not_matching_the_pasted_private_key_is_refused(client, machines):
    owner, other, owner_public = machines
    private, _ = _keypair()
    store = _vault_store()
    with patch.object(server_routes, "vault_store", store):
        resp = await client.put(f"/api/v1/servers/{other.id}/key",
                                json={"private_key": private, "public_key": f"{owner_public} copied"})
    # The public half matches the owner's, but the private half doesn't -> mismatch, never stored.
    assert resp.status_code == 422 and resp.json()["detail"]["code"] == "SSH_PUBLIC_KEY_MISMATCH"
    store.assert_not_called()


@pytest.mark.asyncio
async def test_private_key_only_is_derived_and_a_duplicate_is_refused(client, machines):
    owner, other, _ = machines
    private, public = _keypair()
    async with AsyncSessionLocal() as db:
        row = await db.get(Server, owner.id)
        row.public_key = public
        await db.commit()
    store = _vault_store()
    with patch.object(server_routes, "vault_store", store):
        resp = await client.put(f"/api/v1/servers/{other.id}/key", json={"private_key": private})
    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "SSH_KEY_IN_USE" and owner.name in detail["message"]
    assert "regra 3" in detail["message"]
    assert "PRIVATE KEY" not in resp.text and public.split()[1] not in resp.text
    store.assert_not_called()
    after = await _row(other.id)
    assert after.ssh_key_ref is None and after.public_key is None


@pytest.mark.asyncio
async def test_public_key_given_for_an_encrypted_private_key_is_checked(client, machines):
    owner, other, owner_public = machines
    private, _ = _keypair(passphrase=b"nao-sei")
    # Encrypted, ForgeHub has no passphrase: the given public half decides.
    store = _vault_store()
    with patch.object(server_routes, "vault_store", store):
        resp = await client.put(f"/api/v1/servers/{other.id}/key",
                                json={"private_key": private, "public_key": owner_public})
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "SSH_KEY_IN_USE"
    store.assert_not_called()


@pytest.mark.asyncio
async def test_undecodable_private_key_without_public_key_is_422(client, machines):
    _, other, _ = machines
    private, _ = _keypair(passphrase=b"nao-sei")
    store = _vault_store()
    with patch.object(server_routes, "vault_store", store):
        resp = await client.put(f"/api/v1/servers/{other.id}/key", json={"private_key": private})
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "SSH_PUBLIC_KEY_REQUIRED"
    store.assert_not_called()


@pytest.mark.asyncio
async def test_same_key_on_the_same_machine_is_fine_and_public_half_is_recorded(client, machines):
    owner, _, _ = machines
    private, public = _keypair()
    with patch.object(server_routes, "vault_store", _vault_store(owner.ssh_key_ref)):
        first = await client.put(f"/api/v1/servers/{owner.id}/key", json={"private_key": private})
        again = await client.put(f"/api/v1/servers/{owner.id}/key", json={"private_key": private})
    assert first.status_code == 200 and again.status_code == 200, again.text
    row = await _row(owner.id)
    assert uniq.public_key_blob(row.public_key) == uniq.public_key_blob(public)


@pytest.mark.asyncio
async def test_vault_returning_another_machines_secret_id_is_refused(client, machines):
    owner, other, _ = machines
    private, _ = _keypair()
    with patch.object(server_routes, "vault_store", _vault_store(owner.ssh_key_ref)):
        resp = await client.put(f"/api/v1/servers/{other.id}/key", json={"private_key": private})
    assert resp.status_code == 409 and owner.name in resp.json()["detail"]["message"]
    after = await _row(other.id)
    assert after.ssh_key_ref is None and after.public_key is None


def _generate_bridge(ref: str, public: str):
    calls: list[str] = []

    async def bridge(path, payload, timeout=20.0):
        calls.append(path)
        assert path == "/v1/servers/generate-key", path
        return httpx.Response(200, json={"ssh_key_ref": ref, "public_key": public},
                              request=httpx.Request("POST", "http://bridge"))

    return bridge, calls


@pytest.mark.asyncio
async def test_preparation_with_a_duplicated_generated_key_changes_nothing(client, machines):
    owner, other, owner_public = machines
    bridge, calls = _generate_bridge(str(uuid.uuid4()), owner_public)
    store = _vault_store()
    with (
        patch.object(server_routes, "_bridge_post", AsyncMock(side_effect=bridge)),
        patch.object(server_routes, "vault_store", store),
    ):
        resp = await client.post(f"/api/v1/servers/{other.id}/preparation", json={"mode": "copy", "admin_user": "administrador"})
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "SSH_KEY_IN_USE"
    assert calls == ["/v1/servers/generate-key"]
    store.assert_not_called()  # the login password was never generated/stored
    after = await _row(other.id)
    assert after.ssh_key_ref is None and after.public_key is None and after.remote_user == "administrador"


@pytest.mark.asyncio
async def test_install_key_with_a_duplicated_secret_id_never_reaches_the_machine(client, machines):
    owner, other, _ = machines
    _, fresh_public = _keypair()
    bridge, _ = _generate_bridge(owner.ssh_key_ref, fresh_public)
    # The route's own httpx (install-key on the machine) must never be used.
    fake_httpx = MagicMock()
    fake_httpx.AsyncClient.side_effect = AssertionError("install-key must not run")
    install = fake_httpx.AsyncClient
    with (
        patch.object(server_routes, "_bridge_post", AsyncMock(side_effect=bridge)),
        patch.object(server_routes, "httpx", fake_httpx),
    ):
        resp = await client.post(f"/api/v1/servers/{other.id}/install-key", json={"password": "x"})
    assert resp.status_code == 409 and owner.name in resp.json()["detail"]["message"]
    install.assert_not_called()
    after = await _row(other.id)
    assert after.ssh_key_ref is None and after.public_key is None


@pytest.mark.asyncio
async def test_rotation_with_a_duplicated_key_fails_and_keeps_the_row(machines):
    owner, other, owner_public = machines
    bridge, _ = _generate_bridge(str(uuid.uuid4()), owner_public)
    run = AsyncMock(side_effect=AssertionError("nothing may run on the machine"))
    with (
        patch.object(server_routes, "_bridge_post", AsyncMock(side_effect=bridge)),
        patch.object(server_routes, "call_bridge_exec_as", run),
    ):
        async with AsyncSessionLocal() as db:
            result = await server_routes._rotate_key(db, await db.get(Server, other.id))
    assert result["failure"] and owner.name in (result["stderr"] or "")
    run.assert_not_called()
    after = await _row(other.id)
    assert after.ssh_key_ref is None and after.public_key is None


@pytest.mark.asyncio
async def test_a_secret_name_shared_with_another_machine_gets_a_unique_name(client, machines):
    """The vault upserts by name: writing under another machine's secret name
    would replace that machine's key. Same client + names that slug alike."""
    owner, other, _ = machines
    async with AsyncSessionLocal() as db:
        row = await db.get(Server, other.id)
        row.name = owner.name.replace("-", "_")  # slugs to the same WS_..._SSH_KEY
        await db.commit()
    private, _ = _keypair()
    store = _vault_store()
    with patch.object(server_routes, "vault_store", store):
        resp = await client.put(f"/api/v1/servers/{other.id}/key", json={"private_key": private})
    assert resp.status_code == 200, resp.text
    async with AsyncSessionLocal() as db:
        owner_row = await db.get(Server, owner.id)
        used_name = store.call_args.args[0]
        assert used_name != server_routes.machine_secret_name(owner_row, "SSH_KEY")


@pytest.mark.asyncio
async def test_list_reports_existing_duplicates_without_changing_them(client, machines):
    owner, other, owner_public = machines
    async with AsyncSessionLocal() as db:
        row = await db.get(Server, other.id)
        row.public_key = owner_public  # a pre-rule duplicate, written directly
        await db.commit()
    resp = await client.get("/api/v1/servers")
    assert resp.status_code == 200
    by_id = {item["id"]: item for item in resp.json()}
    assert by_id[str(owner.id)]["duplicate_key_with"] == [other.name]
    assert by_id[str(other.id)]["duplicate_key_with"] == [owner.name]
    after = await _row(other.id)
    assert after.public_key == owner_public
