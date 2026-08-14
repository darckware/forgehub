"""Server domain – SSH-accessible infrastructure registry.

Endpoints:
  GET    /api/v1/servers            – list all
  POST   /api/v1/servers            – create
  GET    /api/v1/servers/{id}       – get one
  PUT    /api/v1/servers/{id}       – full update
  DELETE /api/v1/servers/{id}       – delete
  POST   /api/v1/servers/import     – bulk CSV import (upsert by name)
  POST   /api/v1/servers/{id}/check – on-demand SSH reachability probe
  POST   /api/v1/servers/{id}/key:backup   – vault the host's identity file
  PUT    /api/v1/servers/{id}/key          – vault a pasted private key
  POST   /api/v1/servers/{id}/key:restore  – write the vaulted key to the host
  DELETE /api/v1/servers/{id}/key          – drop the vaulted copy
"""
import asyncio
import csv
import io
import logging
import socket
import uuid

import httpx
import paramiko
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

# paramiko's Transport runs its handshake in a background thread and logs
# protocol errors (e.g. probing a non-SSH port) at ERROR level by default --
# that's expected/handled noise here (_probe_ssh already returns "offline"
# for it), so keep it out of the app's logs.
logging.getLogger("paramiko").setLevel(logging.CRITICAL)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.server import (
    ServerCheckResult,
    ServerCreate,
    ServerImportRequest,
    ServerImportResult,
    ServerInstallKeyRequest,
    ServerInstallKeyResult,
    ServerKeyStoreRequest,
    ServerKeyVaultResult,
    ServerOut,
    ServerUpdate,
)
from app.core.config import settings
from app.core.deps import get_current_admin
from app.core.secrets import decrypt_secret, encrypt_secret
from app.db.base import get_db
from app.db.models.server import Server
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/servers", tags=["servers"])

REQUIRED_CSV_COLUMNS = {"SERVER_NAME", "SERVER_IP", "REMOTE_USER"}

CHECK_TIMEOUT_SECONDS = 4


# The Workspace terminal's `ssh` runs on the HOST via the bridge, so the
# host's default identities/agent are what actually matter for "ready to
# use". This container has no ~/.ssh of its own -- probing from here with
# paramiko can only ever validate an explicit ssh_key_path, which is why a
# server that connects fine from the terminal used to show "No key" when
# its ssh_key_path field was blank. The bridge probe uses the same `ssh`
# binary/keys the terminal does; the paramiko probe below is only a
# degraded fallback for when the bridge is down.
BRIDGE_STATUS_MAP: dict[str, tuple[str, str]] = {
    "active": ("online", "SSH authentication succeeded from the host — ready to use"),
    "off": ("offline", "Host is unreachable on the SSH port"),
    "not_installed": (
        "no_key",
        "Host is reachable but SSH key authentication failed (no working key on the host)",
    ),
}


async def _check_via_bridge(server: Server) -> tuple[str, str] | None:
    """Probe through the host bridge's /v1/servers/check-status (TCP check +
    real `ssh ... true` with the host's keys). Returns None when the bridge
    is unreachable or answers something unexpected, so the caller can fall
    back to the in-container paramiko probe.
    """
    payload = {
        "servers": [
            {
                "id": str(server.id),
                "ip_address": server.ip_address,
                "remote_user": server.remote_user,
                "ssh_port": server.ssh_port,
                "ssh_key_path": server.ssh_key_path,
            }
        ]
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{settings.CHAT_BRIDGE_URL}/v1/servers/check-status",
                json=payload,
                headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
            )
        if resp.status_code != 200:
            return None
        bridge_status = resp.json()["statuses"].get(str(server.id))
    except (httpx.HTTPError, KeyError, ValueError):
        return None
    return BRIDGE_STATUS_MAP.get(bridge_status)


def _probe_ssh(ip_address: str, port: int, remote_user: str, ssh_key_path: str | None) -> tuple[str, str]:
    """Blocking SSH reachability probe -- run via asyncio.to_thread, never
    directly on the event loop. Returns (status, detail).

    Fallback path only: runs inside the backend container, so it cannot see
    the host's default keys -- see _check_via_bridge above.
    """
    if not ssh_key_path:
        try:
            with socket.create_connection((ip_address, port), timeout=CHECK_TIMEOUT_SECONDS):
                pass
            return "no_key", "Port is reachable but no SSH key is configured for this server"
        except OSError as exc:
            return "offline", f"No SSH key configured, and host is unreachable: {exc}"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            ip_address,
            port=port,
            username=remote_user,
            key_filename=ssh_key_path,
            timeout=CHECK_TIMEOUT_SECONDS,
            banner_timeout=CHECK_TIMEOUT_SECONDS,
            auth_timeout=CHECK_TIMEOUT_SECONDS,
            look_for_keys=False,
            allow_agent=False,
        )
        return "online", "SSH connection and key authentication succeeded"
    except paramiko.AuthenticationException:
        return "offline", "Host is reachable but the configured SSH key was rejected"
    except FileNotFoundError:
        return "offline", f"SSH key file not found at {ssh_key_path}"
    except (paramiko.SSHException, socket.error, OSError) as exc:
        return "offline", f"Could not connect: {exc}"
    finally:
        client.close()


@router.get("", response_model=list[ServerOut])
async def list_servers(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Server).order_by(Server.name))
    return list(result.scalars().all())


@router.post("", response_model=ServerOut, status_code=status.HTTP_201_CREATED)
async def create_server(payload: ServerCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Server).where(Server.name == payload.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Server '{payload.name}' already exists")
    server = Server(**payload.model_dump())
    db.add(server)
    await db.commit()
    await db.refresh(server)
    return server


@router.get("/{server_id}", response_model=ServerOut)
async def get_server(server_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    server = await db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    return server


@router.put("/{server_id}", response_model=ServerOut)
async def update_server(server_id: uuid.UUID, payload: ServerUpdate, db: AsyncSession = Depends(get_db)):
    server = await db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(server, field, value)
    await db.commit()
    await db.refresh(server)
    return server


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(server_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    server = await db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    await db.delete(server)
    await db.commit()


@router.post("/{server_id}/check", response_model=ServerCheckResult)
async def check_server_status(server_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Runs a live SSH reachability probe against the server (not persisted --
    called on demand from the Servers page to answer "which servers are up,
    which have a working key, which have none configured").

    Probes through the host bridge first so the answer reflects the same
    environment the Workspace SSH terminal runs in; falls back to the
    in-container paramiko probe if the bridge is down.
    """
    server = await db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    bridge_result = await _check_via_bridge(server)
    if bridge_result is not None:
        check_status, detail = bridge_result
    else:
        check_status, detail = await asyncio.to_thread(
            _probe_ssh, server.ip_address, server.ssh_port, server.remote_user, server.ssh_key_path
        )
    return ServerCheckResult(server_id=server.id, status=check_status, detail=detail)


@router.post("/{server_id}/install-key", response_model=ServerInstallKeyResult)
async def install_server_key(
    server_id: uuid.UUID,
    payload: ServerInstallKeyRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Generates a dedicated ed25519 key pair on the host (via the bridge —
    same environment the Workspace terminal's ssh runs in) and installs the
    public half in the server's authorized_keys using the password provided.
    On success the row is updated: ssh_key_path points at the new private
    key (so the status probe and terminal use it from now on) and public_key
    records the installed .pub for auditing. Admin-only: takes a server
    credential and writes files on the host.
    """
    server = await db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    remote_user = (payload.remote_user or server.remote_user).strip()
    admin_user = payload.admin_user.strip() if payload.admin_user else None

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{settings.CHAT_BRIDGE_URL}/v1/servers/install-key",
                json={
                    "ip_address": server.ip_address,
                    "remote_user": remote_user,
                    "password": payload.password,
                    "ssh_port": server.ssh_port,
                    "admin_user": admin_user,
                },
                headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Host bridge unreachable: {exc}") from exc
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Host bridge error: {resp.text[:300]}")
    data = resp.json()

    if not data.get("ok"):
        return ServerInstallKeyResult(
            ok=False,
            steps=data.get("steps", []),
            error=data.get("error"),
            failed_step=data.get("step"),
        )

    server.ssh_key_path = data["key_path"]
    server.public_key = data["public_key"]
    if remote_user != server.remote_user:
        server.remote_user = remote_user
    await db.commit()
    return ServerInstallKeyResult(
        ok=True,
        steps=data.get("steps", []),
        key_path=data["key_path"],
        public_key=data["public_key"],
    )


@router.post("/{server_id}/public-key", response_model=ServerOut)
async def read_and_store_public_key(
    server_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Reads the public key from the row's configured ssh_key_path on the
    host (via the bridge) and persists it into the server's public_key
    column, then returns the updated row. Backs the "copy public key" button
    for servers whose key was set manually (path known, public_key not yet
    recorded). Admin-only: reads a host file path."""
    server = await db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    if not server.ssh_key_path:
        raise HTTPException(status_code=400, detail="No SSH key path configured for this server")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{settings.CHAT_BRIDGE_URL}/v1/servers/read-public-key",
                json={"key_path": server.ssh_key_path},
                headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Host bridge unreachable: {exc}") from exc
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail=resp.json().get("detail", "Public key file not found on host"))
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Host bridge error: {resp.text[:300]}")

    server.public_key = resp.json()["public_key"]
    await db.commit()
    await db.refresh(server)
    return server


# ---------------------------------------------------------------------------
# Key vault -- an encrypted copy of the identity file on the row itself.
#
# The inventory always knew *where* a key was, never *what* it was, and a path
# is not a backup: recreating the Aegis profile directory on 2026-07-07 left
# the 172.15.2.4/172.15.2.5 keys behind in a backup dir and the terminal lost
# those servers outright (2026-08-14, Marcelo: "seria melhor criptografar a
# chave no banco de dados para não perder"). These three routes are the round
# trip -- read from host, keep encrypted, pour back when the file is gone --
# and are admin-only, since each one handles private key material.
#
# Deliberately not automatic: nothing backs a key up on save, and nothing
# restores one when a connection fails. A key silently reappearing on disk
# from a stale DB copy is a worse surprise than a connection that reports it
# is missing.
# ---------------------------------------------------------------------------


async def _bridge_post(path: str, payload: dict, timeout: float = 20.0) -> httpx.Response:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            return await client.post(
                f"{settings.CHAT_BRIDGE_URL}{path}",
                json=payload,
                headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Host bridge unreachable: {exc}") from exc


def _bridge_detail(resp: httpx.Response) -> str:
    try:
        return str(resp.json().get("detail", resp.text[:300]))
    except ValueError:
        return resp.text[:300]


@router.post("/{server_id}/key:backup", response_model=ServerKeyVaultResult)
async def backup_server_key(
    server_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Reads the row's identity file from the host and stores it encrypted on
    the row. Overwrites any previous vaulted copy — the file on the host is
    the one ssh actually uses, so it is the authority when both exist."""
    server = await db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    if not server.ssh_key_path:
        raise HTTPException(status_code=400, detail="No SSH key path configured for this server")

    resp = await _bridge_post("/v1/servers/read-private-key", {"key_path": server.ssh_key_path})
    if resp.status_code in (400, 404):
        raise HTTPException(status_code=resp.status_code, detail=_bridge_detail(resp))
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Host bridge error: {resp.text[:300]}")
    data = resp.json()

    server.private_key_encrypted = encrypt_secret(data["private_key"])
    if data.get("public_key") and not server.public_key:
        server.public_key = data["public_key"]
    await db.commit()
    return ServerKeyVaultResult(
        server_id=server.id, private_key_stored=True, key_path=data.get("key_path")
    )


@router.put("/{server_id}/key", response_model=ServerKeyVaultResult)
async def store_server_key(
    server_id: uuid.UUID,
    payload: ServerKeyStoreRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Vaults a pasted private key, for a server whose file ForgeHub cannot
    read from this host. Validated only by shape here — whether it is the key
    the server accepts is answered by the status probe, not by this route."""
    server = await db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    material = payload.private_key.strip()
    if "PRIVATE KEY" not in material:
        raise HTTPException(status_code=422, detail="Payload does not look like an SSH private key")

    server.private_key_encrypted = encrypt_secret(material)
    if payload.public_key:
        server.public_key = payload.public_key.strip()
    await db.commit()
    return ServerKeyVaultResult(server_id=server.id, private_key_stored=True)


@router.post("/{server_id}/key:restore", response_model=ServerKeyVaultResult)
async def restore_server_key(
    server_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Writes the vaulted key back to the host at the row's ssh_key_path
    (0600). The bridge refuses when a file is already there, which surfaces as
    409 rather than replacing a working identity."""
    server = await db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    if not server.private_key_encrypted:
        raise HTTPException(status_code=400, detail="No key is vaulted for this server")
    if not server.ssh_key_path:
        raise HTTPException(status_code=400, detail="No SSH key path configured for this server")

    resp = await _bridge_post(
        "/v1/servers/write-private-key",
        {
            "key_path": server.ssh_key_path,
            "private_key": decrypt_secret(server.private_key_encrypted),
            "public_key": server.public_key,
        },
    )
    if resp.status_code in (400, 409):
        raise HTTPException(status_code=resp.status_code, detail=_bridge_detail(resp))
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Host bridge error: {resp.text[:300]}")
    return ServerKeyVaultResult(
        server_id=server.id,
        private_key_stored=True,
        key_path=server.ssh_key_path,
        written=resp.json().get("written", []),
    )


@router.delete("/{server_id}/key", response_model=ServerKeyVaultResult)
async def clear_server_key(
    server_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Drops the vaulted copy. Never touches the file on the host."""
    server = await db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    server.private_key_encrypted = None
    await db.commit()
    return ServerKeyVaultResult(server_id=server.id, private_key_stored=False)


@router.post("/import", response_model=ServerImportResult)
async def import_servers(payload: ServerImportRequest, db: AsyncSession = Depends(get_db)):
    """Upsert servers from CSV text (header required):
    SERVER_NAME,SERVER_IP,REMOTE_USER,DESCRIPTION

    Matches existing rows by SERVER_NAME (case-sensitive, exact match) and
    updates ip_address/remote_user/description in place; unmatched names are
    created. SSH port is not part of the CSV format (defaults to 22) and is
    left untouched on update.
    """
    reader = csv.DictReader(io.StringIO(payload.csv_text))
    if reader.fieldnames is None or not REQUIRED_CSV_COLUMNS.issubset(set(reader.fieldnames)):
        raise HTTPException(
            status_code=422,
            detail=f"CSV header must include: {', '.join(sorted(REQUIRED_CSV_COLUMNS))}",
        )

    existing_result = await db.execute(select(Server))
    existing_by_name = {s.name: s for s in existing_result.scalars().all()}

    created = 0
    updated = 0
    errors: list[str] = []

    for i, row in enumerate(reader, start=2):  # row 1 is the header
        name = (row.get("SERVER_NAME") or "").strip()
        ip_address = (row.get("SERVER_IP") or "").strip()
        remote_user = (row.get("REMOTE_USER") or "").strip()
        description = (row.get("DESCRIPTION") or "").strip() or None

        if not name or not ip_address or not remote_user:
            errors.append(f"Line {i}: SERVER_NAME, SERVER_IP and REMOTE_USER are required")
            continue

        if name in existing_by_name:
            server = existing_by_name[name]
            server.ip_address = ip_address
            server.remote_user = remote_user
            server.description = description
            updated += 1
        else:
            server = Server(
                name=name,
                ip_address=ip_address,
                remote_user=remote_user,
                description=description,
            )
            db.add(server)
            existing_by_name[name] = server
            created += 1

    if created or updated:
        await db.commit()

    return ServerImportResult(created=created, updated=updated, errors=errors)
