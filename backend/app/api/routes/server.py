"""Server domain – SSH-accessible infrastructure registry.

Endpoints:
  GET    /api/v1/servers            – list all
  POST   /api/v1/servers            – create
  GET    /api/v1/servers/{id}       – get one
  PUT    /api/v1/servers/{id}       – full update
  DELETE /api/v1/servers/{id}       – delete
  POST   /api/v1/servers/import     – bulk CSV import (upsert by name)
  POST   /api/v1/servers/{id}/check – on-demand SSH reachability probe
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
    ServerOut,
    ServerUpdate,
)
from app.core.config import settings
from app.core.deps import get_current_admin
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
