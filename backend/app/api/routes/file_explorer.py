"""Workspace Explorer -- a Windows-Explorer-style file manager over the host.

Backs the Workspace's Explorer tab (frontend/src/components/explorer/).
The files live on the HOST, not in this container, so -- same reasoning as
project.py's project file browser and terminal.py -- every filesystem op is
performed by the host-bridge (/v1/fs/*) and this layer only authenticates,
normalizes paths and records the audit trail.

Unlike the project file browser, this one is deliberately not jailed to a
project root: it is the file-manager counterpart of the Workspace terminal,
which is already a root shell on the same host. That is exactly why every
route requires an admin (get_current_admin), mirroring terminal.py, rather
than relying on RequireAuthMiddleware's "any valid session".

Paths are absolute host paths. _normalize rejects relative paths and
collapses "."/".." with posixpath.normpath (pure string work -- the path
does not exist inside this container, so Path.resolve() would be wrong).

Every mutation and every download writes an AuditEvent
(entity_type="host_file", entity_id = uuid5 of the path, so the history of
one path can be queried back) -- listing/searching/reading are not audited,
the same line terminal.py draws at not logging keystrokes.

Remote servers (2026-09-27): every route takes an optional `server_id` (a
row of the SSH inventory, `servers`). With it, the same operation runs on
that server instead of the VPS -- the bridge's /v1/remote-fs/* mirror of
/v1/fs/*, over this host's `ssh` (see host-bridge/remote_fs.py) -- which is
how the Explorer tab opened from a Workspace SSH tab browses that server.
The audit entity for a remote path is keyed by server + path, so the same
path on two machines never shares a history.
"""

import posixpath
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.file_explorer import (
    ExplorerContentUpdate,
    ExplorerEntry,
    ExplorerFileContent,
    ExplorerListing,
    ExplorerMove,
    ExplorerPath,
    ExplorerSearchResult,
    ExplorerZipRequest,
    QuickAccessEntryOut,
    QuickAccessPin,
)
from app.core.config import settings
from app.core.deps import get_current_admin
from app.db.base import AsyncSessionLocal, get_db
from app.db.models.file_explorer import ExplorerQuickAccessEntry
from app.db.models.governance import AuditEvent
from app.db.models.server import Server
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/file-explorer", tags=["file-explorer"])

DEFAULT_ROOT = "/root"


def _normalize(path: str | None) -> str:
    raw = (path or "").strip()
    if not raw:
        return DEFAULT_ROOT
    if not raw.startswith("/"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Path must be absolute")
    return posixpath.normpath(raw).replace("//", "/")


def _assert_not_root(path: str) -> None:
    if path == "/":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The filesystem root cannot be changed")


def _headers() -> dict[str, str]:
    return {"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN}


@dataclass(frozen=True)
class ExplorerTarget:
    """Which machine a request operates on: the VPS (no server) or one SSH
    inventory server. `url(op)` is the bridge route for a /v1/fs/<op>."""

    server: Server | None = None
    headers: dict[str, str] = field(default_factory=_headers)

    def url(self, op: str) -> str:
        prefix = "/v1/remote-fs" if self.server else "/v1/fs"
        return f"{settings.CHAT_BRIDGE_URL}{prefix}/{op}"

    def entity_id(self, path: str) -> uuid.UUID:
        key = f"ssh://{self.server.id}{path}" if self.server else f"file://{path}"
        return uuid.uuid5(uuid.NAMESPACE_URL, key)

    def audit_payload(self) -> dict:
        if not self.server:
            return {}
        return {"server_id": str(self.server.id), "server": self.server.name}


async def explorer_target(
    server_id: uuid.UUID | None = Query(default=None), db: AsyncSession = Depends(get_db)
) -> ExplorerTarget:
    if server_id is None:
        return ExplorerTarget()
    server = await db.get(Server, server_id)
    if server is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Server not found")
    if not server.access_enabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Access to {server.name} is disabled in ForgeHub")
    headers = {
        **_headers(),
        "X-Ssh-Host": server.ip_address,
        "X-Ssh-User": server.remote_user,
        "X-Ssh-Port": str(server.ssh_port or 22),
    }
    if server.ssh_key_path:
        headers["X-Ssh-Key"] = server.ssh_key_path
    return ExplorerTarget(server=server, headers=headers)


async def _bridge(target: ExplorerTarget, method: str, op: str, *, timeout: float = 30.0, **kwargs) -> dict:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(method, target.url(op), headers=target.headers, **kwargs)
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Host bridge unavailable: {exc}") from exc
    if resp.status_code >= 400:
        raise HTTPException(resp.status_code, _bridge_detail(resp))
    return resp.json()


def _bridge_detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        if isinstance(body, dict) and isinstance(body.get("detail"), str):
            return body["detail"]
    except ValueError:
        pass
    return resp.text[:500] or f"Host bridge error ({resp.status_code})"


async def _audit(
    target: ExplorerTarget, event_type: str, path: str, user: User, payload: dict | None = None
) -> None:
    async with AsyncSessionLocal() as db:
        db.add(
            AuditEvent(
                entity_type="host_file",
                entity_id=target.entity_id(path),
                event_type=event_type,
                actor=user.username,
                payload={"path": path, **target.audit_payload(), **(payload or {})},
            )
        )
        await db.commit()


@router.get("", response_model=ExplorerListing)
async def list_directory(
    path: str | None = Query(default=None),
    target: ExplorerTarget = Depends(explorer_target),
    user: User = Depends(get_current_admin),
) -> dict:
    # No path on a remote server means its user's home, which only the
    # server knows -- /root is the VPS's default, not everyone's.
    params = {"path": _normalize(path)} if path or not target.server else {}
    return await _bridge(target, "GET", "list", params=params)


@router.get("/search", response_model=ExplorerSearchResult)
async def search(
    path: str = Query(...),
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(default=500, ge=1, le=5000),
    target: ExplorerTarget = Depends(explorer_target),
    user: User = Depends(get_current_admin),
) -> dict:
    return await _bridge(
        target, "GET", "search", timeout=60.0, params={"path": _normalize(path), "q": q, "limit": limit}
    )


@router.get("/content", response_model=ExplorerFileContent)
async def read_file(
    path: str = Query(...), target: ExplorerTarget = Depends(explorer_target), user: User = Depends(get_current_admin)
) -> dict:
    return await _bridge(target, "GET", "read", params={"path": _normalize(path)})


@router.put("/content", response_model=ExplorerFileContent)
async def write_file(
    payload: ExplorerContentUpdate,
    path: str = Query(...),
    target: ExplorerTarget = Depends(explorer_target),
    user: User = Depends(get_current_admin),
) -> dict:
    file_path = _normalize(path)
    data = await _bridge(target, "PUT", "write", json={"path": file_path, "content": payload.content})
    await _audit(target, "file_edited", file_path, user, {"bytes": len(payload.content.encode())})
    return data


@router.post("/directory", response_model=ExplorerEntry, status_code=status.HTTP_201_CREATED)
async def create_directory(
    payload: ExplorerPath, target: ExplorerTarget = Depends(explorer_target), user: User = Depends(get_current_admin)
) -> dict:
    folder = _normalize(payload.path)
    data = await _bridge(target, "POST", "mkdir", json={"path": folder})
    await _audit(target, "folder_created", folder, user)
    return data


@router.post("/file", response_model=ExplorerEntry, status_code=status.HTTP_201_CREATED)
async def create_file(
    payload: ExplorerPath, target: ExplorerTarget = Depends(explorer_target), user: User = Depends(get_current_admin)
) -> dict:
    file_path = _normalize(payload.path)
    data = await _bridge(target, "POST", "create-file", json={"path": file_path})
    await _audit(target, "file_created", file_path, user)
    return data


@router.patch("/move", response_model=ExplorerEntry)
async def move(
    payload: ExplorerMove, target: ExplorerTarget = Depends(explorer_target), user: User = Depends(get_current_admin)
) -> dict:
    """Rename (same parent) and cut/paste (different parent) are one op."""
    source, dest = _normalize(payload.path), _normalize(payload.new_path)
    _assert_not_root(source)
    if dest == source or dest.startswith(source.rstrip("/") + "/"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot move a folder into itself")
    data = await _bridge(target, "PATCH", "rename", json={"path": source, "new_path": dest})
    event = "renamed" if posixpath.dirname(source) == posixpath.dirname(dest) else "moved"
    await _audit(target, event, source, user, {"new_path": dest})
    return data


@router.post("/copy", response_model=ExplorerEntry, status_code=status.HTTP_201_CREATED)
async def copy(
    payload: ExplorerMove, target: ExplorerTarget = Depends(explorer_target), user: User = Depends(get_current_admin)
) -> dict:
    source, dest = _normalize(payload.path), _normalize(payload.new_path)
    data = await _bridge(target, "POST", "copy", timeout=600.0, json={"path": source, "new_path": dest})
    await _audit(target, "copied", source, user, {"new_path": dest})
    return data


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete(
    path: str = Query(...),
    recursive: bool = Query(default=False),
    target: ExplorerTarget = Depends(explorer_target),
    user: User = Depends(get_current_admin),
) -> None:
    doomed = _normalize(path)
    _assert_not_root(doomed)
    await _bridge(target, "DELETE", "delete", timeout=300.0, params={"path": doomed, "recursive": recursive})
    await _audit(target, "deleted", doomed, user, {"recursive": recursive})


@router.put("/upload", response_model=ExplorerEntry)
async def upload(
    request: Request,
    path: str = Query(...),
    overwrite: bool = Query(default=False),
    target: ExplorerTarget = Depends(explorer_target),
    user: User = Depends(get_current_admin),
) -> dict:
    """Raw request body (not multipart) streamed straight through to the
    bridge, so neither hop ever holds the whole file in memory. A folder
    upload is one call per file with its relative path appended to the
    destination; the bridge creates missing parent folders."""
    destination = _normalize(path)
    _assert_not_root(destination)

    async def body() -> AsyncIterator[bytes]:
        async for chunk in request.stream():
            yield chunk

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=10.0)) as client:
            resp = await client.put(
                target.url("upload"),
                params={"path": destination, "overwrite": overwrite},
                headers=target.headers,
                content=body(),
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Host bridge unavailable: {exc}") from exc
    if resp.status_code >= 400:
        raise HTTPException(resp.status_code, _bridge_detail(resp))
    data = resp.json()
    await _audit(target, "uploaded", destination, user, {"bytes": data.get("size"), "overwrite": overwrite})
    return data


async def _stream_from_bridge(target: ExplorerTarget, method: str, op: str, **kwargs) -> StreamingResponse:
    """Open a streamed bridge response and relay it chunk by chunk, keeping
    the bridge's Content-Disposition/Length so the browser gets the name."""
    client = httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=10.0))
    try:
        req = client.build_request(method, target.url(op), headers=target.headers, **kwargs)
        resp = await client.send(req, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Host bridge unavailable: {exc}") from exc
    if resp.status_code >= 400:
        await resp.aread()
        detail = _bridge_detail(resp)
        await resp.aclose()
        await client.aclose()
        raise HTTPException(resp.status_code, detail)

    async def relay() -> AsyncIterator[bytes]:
        try:
            async for chunk in resp.aiter_raw():
                yield chunk
        finally:
            await resp.aclose()
            await client.aclose()

    headers = {k: v for k, v in resp.headers.items() if k.lower() in ("content-disposition", "content-length")}
    return StreamingResponse(relay(), media_type=resp.headers.get("content-type"), headers=headers)


@router.get("/download")
async def download(
    path: str = Query(...), target: ExplorerTarget = Depends(explorer_target), user: User = Depends(get_current_admin)
) -> StreamingResponse:
    """A file as-is, a folder as <name>.zip (<name>.tar.gz on a remote server)."""
    file_path = _normalize(path)
    response = await _stream_from_bridge(target, "GET", "download", params={"path": file_path})
    await _audit(target, "downloaded", file_path, user)
    return response


@router.post("/download-zip")
async def download_zip(
    payload: ExplorerZipRequest,
    target: ExplorerTarget = Depends(explorer_target),
    user: User = Depends(get_current_admin),
) -> StreamingResponse:
    """Multi-selection (files and folders together) as a single .zip
    (.tar.gz on a remote server)."""
    paths = [_normalize(p) for p in payload.paths]
    response = await _stream_from_bridge(
        target, "POST", "download-zip", json={"paths": paths, "name": payload.name}
    )
    for p in paths:
        await _audit(target, "downloaded", p, user, {"archive": payload.name})
    return response


# ---------------------------------------------------------------------------
# Quick access (per user). Only the user's deviations from the built-in list
# are stored -- see db/models/file_explorer.py. No host-bridge call and no
# audit event: this is navigation preference, not a filesystem change.
# ---------------------------------------------------------------------------


@router.get("/quick-access", response_model=list[QuickAccessEntryOut])
async def list_quick_access(
    user: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> list[ExplorerQuickAccessEntry]:
    result = await db.execute(
        select(ExplorerQuickAccessEntry)
        .where(ExplorerQuickAccessEntry.user_id == user.id)
        .order_by(ExplorerQuickAccessEntry.created_at)
    )
    return list(result.scalars())


@router.put("/quick-access", response_model=QuickAccessEntryOut)
async def pin_quick_access(
    payload: QuickAccessPin, user: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> ExplorerQuickAccessEntry:
    """Upsert by path: pin a folder (hidden=false) or remove a built-in
    entry (hidden=true). Re-pinning an existing path keeps its position."""
    path = _normalize(payload.path)
    entry = (
        await db.execute(
            select(ExplorerQuickAccessEntry).where(
                ExplorerQuickAccessEntry.user_id == user.id, ExplorerQuickAccessEntry.path == path
            )
        )
    ).scalar_one_or_none()
    if entry is None:
        entry = ExplorerQuickAccessEntry(user_id=user.id, path=path)
        db.add(entry)
    entry.hidden = payload.hidden
    entry.label = (payload.label or "").strip() or None
    await db.commit()
    await db.refresh(entry)
    return entry


@router.delete("/quick-access", status_code=status.HTTP_204_NO_CONTENT)
async def unpin_quick_access(
    path: str = Query(...), user: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> None:
    """Drop this user's row for `path`: a pinned folder disappears, a hidden
    built-in comes back. Idempotent."""
    await db.execute(
        sa_delete(ExplorerQuickAccessEntry).where(
            ExplorerQuickAccessEntry.user_id == user.id, ExplorerQuickAccessEntry.path == _normalize(path)
        )
    )
    await db.commit()
