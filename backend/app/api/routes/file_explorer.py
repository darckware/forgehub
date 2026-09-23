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
"""

import posixpath
import uuid
from collections.abc import AsyncIterator

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from app.api.schemas.file_explorer import (
    ExplorerContentUpdate,
    ExplorerEntry,
    ExplorerFileContent,
    ExplorerListing,
    ExplorerMove,
    ExplorerPath,
    ExplorerSearchResult,
    ExplorerZipRequest,
)
from app.core.config import settings
from app.core.deps import get_current_admin
from app.db.base import AsyncSessionLocal
from app.db.models.governance import AuditEvent
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


async def _bridge(method: str, path: str, *, timeout: float = 30.0, **kwargs) -> dict:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(method, f"{settings.CHAT_BRIDGE_URL}{path}", headers=_headers(), **kwargs)
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


async def _audit(event_type: str, path: str, user: User, payload: dict | None = None) -> None:
    async with AsyncSessionLocal() as db:
        db.add(
            AuditEvent(
                entity_type="host_file",
                entity_id=uuid.uuid5(uuid.NAMESPACE_URL, f"file://{path}"),
                event_type=event_type,
                actor=user.username,
                payload={"path": path, **(payload or {})},
            )
        )
        await db.commit()


@router.get("", response_model=ExplorerListing)
async def list_directory(path: str | None = Query(default=None), user: User = Depends(get_current_admin)) -> dict:
    return await _bridge("GET", "/v1/fs/list", params={"path": _normalize(path)})


@router.get("/search", response_model=ExplorerSearchResult)
async def search(
    path: str = Query(...),
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(default=500, ge=1, le=5000),
    user: User = Depends(get_current_admin),
) -> dict:
    return await _bridge(
        "GET", "/v1/fs/search", timeout=60.0, params={"path": _normalize(path), "q": q, "limit": limit}
    )


@router.get("/content", response_model=ExplorerFileContent)
async def read_file(path: str = Query(...), user: User = Depends(get_current_admin)) -> dict:
    return await _bridge("GET", "/v1/fs/read", params={"path": _normalize(path)})


@router.put("/content", response_model=ExplorerFileContent)
async def write_file(
    payload: ExplorerContentUpdate, path: str = Query(...), user: User = Depends(get_current_admin)
) -> dict:
    target = _normalize(path)
    data = await _bridge("PUT", "/v1/fs/write", json={"path": target, "content": payload.content})
    await _audit("file_edited", target, user, {"bytes": len(payload.content.encode())})
    return data


@router.post("/directory", response_model=ExplorerEntry, status_code=status.HTTP_201_CREATED)
async def create_directory(payload: ExplorerPath, user: User = Depends(get_current_admin)) -> dict:
    target = _normalize(payload.path)
    data = await _bridge("POST", "/v1/fs/mkdir", json={"path": target})
    await _audit("folder_created", target, user)
    return data


@router.post("/file", response_model=ExplorerEntry, status_code=status.HTTP_201_CREATED)
async def create_file(payload: ExplorerPath, user: User = Depends(get_current_admin)) -> dict:
    target = _normalize(payload.path)
    data = await _bridge("POST", "/v1/fs/create-file", json={"path": target})
    await _audit("file_created", target, user)
    return data


@router.patch("/move", response_model=ExplorerEntry)
async def move(payload: ExplorerMove, user: User = Depends(get_current_admin)) -> dict:
    """Rename (same parent) and cut/paste (different parent) are one op."""
    source, dest = _normalize(payload.path), _normalize(payload.new_path)
    _assert_not_root(source)
    if dest == source or dest.startswith(source.rstrip("/") + "/"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot move a folder into itself")
    data = await _bridge("PATCH", "/v1/fs/rename", json={"path": source, "new_path": dest})
    event = "renamed" if posixpath.dirname(source) == posixpath.dirname(dest) else "moved"
    await _audit(event, source, user, {"new_path": dest})
    return data


@router.post("/copy", response_model=ExplorerEntry, status_code=status.HTTP_201_CREATED)
async def copy(payload: ExplorerMove, user: User = Depends(get_current_admin)) -> dict:
    source, dest = _normalize(payload.path), _normalize(payload.new_path)
    data = await _bridge("POST", "/v1/fs/copy", timeout=600.0, json={"path": source, "new_path": dest})
    await _audit("copied", source, user, {"new_path": dest})
    return data


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete(
    path: str = Query(...), recursive: bool = Query(default=False), user: User = Depends(get_current_admin)
) -> None:
    target = _normalize(path)
    _assert_not_root(target)
    await _bridge("DELETE", "/v1/fs/delete", timeout=300.0, params={"path": target, "recursive": recursive})
    await _audit("deleted", target, user, {"recursive": recursive})


@router.put("/upload", response_model=ExplorerEntry)
async def upload(
    request: Request,
    path: str = Query(...),
    overwrite: bool = Query(default=False),
    user: User = Depends(get_current_admin),
) -> dict:
    """Raw request body (not multipart) streamed straight through to the
    bridge, so neither hop ever holds the whole file in memory. A folder
    upload is one call per file with its relative path appended to the
    destination; the bridge creates missing parent folders."""
    target = _normalize(path)
    _assert_not_root(target)

    async def body() -> AsyncIterator[bytes]:
        async for chunk in request.stream():
            yield chunk

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=10.0)) as client:
            resp = await client.put(
                f"{settings.CHAT_BRIDGE_URL}/v1/fs/upload",
                params={"path": target, "overwrite": overwrite},
                headers=_headers(),
                content=body(),
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Host bridge unavailable: {exc}") from exc
    if resp.status_code >= 400:
        raise HTTPException(resp.status_code, _bridge_detail(resp))
    data = resp.json()
    await _audit("uploaded", target, user, {"bytes": data.get("size"), "overwrite": overwrite})
    return data


async def _stream_from_bridge(method: str, path: str, **kwargs) -> StreamingResponse:
    """Open a streamed bridge response and relay it chunk by chunk, keeping
    the bridge's Content-Disposition/Length so the browser gets the name."""
    client = httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=10.0))
    try:
        req = client.build_request(method, f"{settings.CHAT_BRIDGE_URL}{path}", headers=_headers(), **kwargs)
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
async def download(path: str = Query(...), user: User = Depends(get_current_admin)) -> StreamingResponse:
    """A file as-is, a folder as <name>.zip."""
    target = _normalize(path)
    response = await _stream_from_bridge("GET", "/v1/fs/download", params={"path": target})
    await _audit("downloaded", target, user)
    return response


@router.post("/download-zip")
async def download_zip(payload: ExplorerZipRequest, user: User = Depends(get_current_admin)) -> StreamingResponse:
    """Multi-selection (files and folders together) as a single .zip."""
    paths = [_normalize(p) for p in payload.paths]
    response = await _stream_from_bridge(
        "POST", "/v1/fs/download-zip", json={"paths": paths, "name": payload.name}
    )
    for p in paths:
        await _audit("downloaded", p, user, {"archive": payload.name})
    return response
