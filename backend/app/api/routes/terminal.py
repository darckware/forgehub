"""Terminal proxy route.

Relays a browser WebSocket to a real PTY (bash) on the host, via the chat
bridge's /v1/terminal/ws (see host-bridge/app.py). This container has no
shell of its own to offer -- the actual bash process lives on the host,
same reasoning as the chat domain's bridge proxy in api/routes/chat.py.

This is a transparent byte pipe in both directions: the browser's input/
resize JSON messages and the bridge's raw terminal output text are never
parsed here, just forwarded. The bridge token lives only on this side --
the browser never sees it.

Every route here requires an admin user, not just any authenticated one:
RequireAuthMiddleware (app/main.py) only proves a request carries *some*
valid session, but a shell (and arbitrary-path file writes) is strictly
more powerful than the app's own view/query/write/delete profile
permissions were ever meant to grant a non-admin user -- see the security
review that flagged this file specifically after the Dashboard's
remote-access card made it reachable from the public internet.
"""
import asyncio
import secrets
import time
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel
from sqlalchemy import select
from websockets import connect as ws_connect
from websockets.exceptions import ConnectionClosed

import uuid

from app.core.config import settings
from app.core.deps import get_current_admin
from app.db.base import AsyncSessionLocal
from app.db.models.governance import AuditEvent
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/terminal", tags=["terminal"])


async def _audit_terminal_event(session_id: str, event_type: str, actor: str, payload: dict) -> None:
    """Fase 6.3 (2026-07-28): open/close only, never keystroke content --
    the terminal is otherwise a transparent byte pipe (see this module's
    docstring), and logging every byte typed would be a keylogger, not an
    audit trail. `entity_id` requires session_id to parse as a UUID (true
    for every real tab -- see workspace/index.tsx's crypto.randomUUID());
    silently skips otherwise rather than failing the connection over it."""
    try:
        entity_id = uuid.UUID(session_id)
    except ValueError:
        return
    async with AsyncSessionLocal() as db:
        db.add(
            AuditEvent(entity_type="terminal_session", entity_id=entity_id, event_type=event_type, actor=actor, payload=payload)
        )
        await db.commit()


@router.get("/browse-dirs")
async def browse_dirs(path: str | None = Query(default=None), user: User = Depends(get_current_admin)) -> dict:
    """Proxy to the bridge's host directory listing -- backs the chat
    UI's working-directory picker (see host-bridge/app.py's /v1/browse-dirs)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{settings.CHAT_BRIDGE_URL}/v1/browse-dirs",
            params={"path": path} if path else {},
            headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Chat bridge error: {resp.text[:500]}"
        )
    return resp.json()


@router.get("/fs-list")
async def fs_list(path: str | None = Query(default=None), user: User = Depends(get_current_admin)) -> dict:
    """Proxy to the bridge's host file/dir listing (files included, unlike
    /browse-dirs) -- backs the chat composer's "@" file-mention picker."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{settings.CHAT_BRIDGE_URL}/v1/fs/list",
            params={"path": path} if path else {},
            headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Chat bridge error: {resp.text[:500]}"
        )
    return resp.json()


@router.get("/openclaw-dashboard-url")
async def openclaw_dashboard_url(user: User = Depends(get_current_admin)) -> dict:
    """Proxy to the bridge's OpenClaw gateway-token lookup -- backs the
    Workspace's OpenClaw launcher menu's "Web" option, which opens the
    dashboard in a new external browser tab (2026-07-29, Marcelo: the
    operator's own browser runs on the same host as OpenClaw, so the
    dashboard's `127.0.0.1` URL resolves fine there -- previously routed
    through the internal Workspace Browser for hosts where that wasn't
    true) already carrying the one-time auth token in the URL fragment,
    per host-bridge/app.py's openclaw_dashboard_url docstring. Admin-gated
    same as every other route in this module: the token this returns
    grants the same admin-surface access a plain shell already would."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{settings.CHAT_BRIDGE_URL}/v1/openclaw/dashboard-url",
            headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Chat bridge error: {resp.text[:500]}"
        )
    return resp.json()


class OpenclawGatewayTokenUpdate(BaseModel):
    token: str


@router.get("/openclaw-gateway-token")
async def get_openclaw_gateway_token(user: User = Depends(get_current_admin)) -> dict:
    """Proxy to the bridge's raw OpenClaw gateway-token read -- backs
    Settings' "OpenClaw" card (2026-07-29, Marcelo: wants the token
    visible/settable from ForgeHub instead of SSHing in and editing
    /root/.openclaw/.env by hand). Same trust boundary as
    /openclaw-dashboard-url above, which already hands this same value
    back to the browser embedded in a URL fragment."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{settings.CHAT_BRIDGE_URL}/v1/openclaw/gateway-token",
            headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Chat bridge error: {resp.text[:500]}"
        )
    return resp.json()


@router.put("/openclaw-gateway-token")
async def set_openclaw_gateway_token(body: OpenclawGatewayTokenUpdate, user: User = Depends(get_current_admin)) -> dict:
    """Writes OPENCLAW_GATEWAY_TOKEN back into /root/.openclaw/.env via the
    bridge (upsert -- every other var in that file, e.g.
    FORGEROUTER_API_KEY/TELEGRAM_BOT_TOKEN, is left untouched). Does NOT
    restart openclaw-gateway.service: the daemon only reads this value once
    at process start (SecretRef, per host-bridge's dashboard-url
    docstring), so a change here only takes effect on its next restart."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.put(
            f"{settings.CHAT_BRIDGE_URL}/v1/openclaw/gateway-token",
            headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
            json={"token": body.token},
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Chat bridge error: {resp.text[:500]}"
        )
    return resp.json()


@router.get("/sessions")
async def list_sessions(user: User = Depends(get_current_admin)) -> dict:
    """Proxy to the bridge's live tmux session listing -- backs the
    orphaned-session cleanup view (Fase 6.2). ForgeHub has no DB record of
    terminal tabs at all (see terminal_ws's docstring: this is a
    transparent byte pipe), so this disk-truth read is the only way to see
    a tab that was never closed through the UI."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{settings.CHAT_BRIDGE_URL}/v1/terminal/sessions",
            headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Chat bridge error: {resp.text[:500]}"
        )
    return resp.json()


@router.post("/sessions/{session_id}/kill")
async def kill_session(session_id: str, user: User = Depends(get_current_admin)) -> dict:
    """Proxy to the bridge's session kill -- ends a terminal tab's tmux
    session for good (vs. a WebSocket disconnect, which only detaches it).
    Called when the user explicitly closes a terminal tab."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{settings.CHAT_BRIDGE_URL}/v1/terminal/sessions/{session_id}/kill",
            headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Chat bridge error: {resp.text[:500]}"
        )
    return resp.json()


@router.post("/upload-image")
async def upload_image(file: UploadFile = File(...), user: User = Depends(get_current_admin)) -> dict:
    """Proxy an image pasted into a terminal pane to the bridge, which
    writes it to a host tmp dir and hands back its path -- the path is then
    typed into the terminal so CLI agents (claude/codex/agy) that read
    images by file reference can pick it up, since the PTY has no way to
    carry the browser's clipboard image bytes itself."""
    content = await file.read()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{settings.CHAT_BRIDGE_URL}/v1/terminal/upload-image",
            files={"image": (file.filename or "image.png", content, file.content_type)},
            headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Chat bridge error: {resp.text[:500]}"
        )
    return resp.json()


@router.post("/upload-to-dir")
async def upload_to_dir(
    dir: str = Form(...), files: list[UploadFile] = File(...), user: User = Depends(get_current_admin)
) -> dict:
    """Proxy the workspace toolbar's "send files" button (next to
    WorkingDirPicker) to the bridge, which writes each file straight into
    the given host directory -- unlike /upload-image, these are meant to
    persist as real project files, not a one-shot path typed into a
    prompt."""
    file_tuples = [("files", (f.filename or "file", await f.read(), f.content_type)) for f in files]
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.CHAT_BRIDGE_URL}/v1/workspace/upload",
            data={"dir": dir},
            files=file_tuples,
            headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Chat bridge error: {resp.text[:500]}"
        )
    return resp.json()


# session JWTs live 60 minutes; a WebSocket ticket only needs to survive the
# handful of seconds between minting it and the browser using it to connect.
# Kept this short (rather than reusing the real token in the URL) because a
# WS URL's query string ends up in plaintext in nginx/Cloudflare tunnel
# access logs -- a ticket that's dead in 30s and consumed on first use isn't
# worth anything to whoever reads those logs later.
WS_TICKET_TTL_SECONDS = 30
_ws_tickets: dict[str, tuple[str, float]] = {}  # ticket -> (username, expires_at_monotonic)


@router.post("/ws-ticket")
async def create_ws_ticket(user: User = Depends(get_current_admin)) -> dict:
    """Mint a single-use, short-lived ticket for the /ws handshake below --
    see WS_TICKET_TTL_SECONDS for why this exists instead of just putting
    the session token in the WebSocket URL."""
    ticket = secrets.token_urlsafe(32)
    _ws_tickets[ticket] = (user.username, time.monotonic() + WS_TICKET_TTL_SECONDS)
    return {"ticket": ticket}


@router.websocket("/ws")
async def terminal_ws(
    websocket: WebSocket,
    session: str = Query(...),
    command: str | None = Query(default=None),
    cwd: str | None = Query(default=None),
    ticket: str = Query(...),
    cols: int = Query(default=80),
    rows: int = Query(default=24),
) -> None:
    # WebSocket upgrades skip RequireAuthMiddleware entirely (it only sees
    # "http" scope requests), and get_current_admin's OAuth2PasswordBearer
    # dependency needs an Authorization header a WS handshake can't carry --
    # hence the separate ticket exchanged via POST /ws-ticket above. .pop()
    # makes it single-use regardless of whether this connection succeeds.
    entry = _ws_tickets.pop(ticket, None)
    if entry is None or entry[1] < time.monotonic():
        await websocket.close(code=4401)
        return
    username = entry[0]
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
    if user is None or not user.is_active or not user.is_admin:
        await websocket.close(code=4403)
        return
    await websocket.accept()
    await _audit_terminal_event(session, "opened", user.username, {"command": command, "cwd": cwd})

    bridge_ws_url = settings.CHAT_BRIDGE_URL.replace("http://", "ws://").replace("https://", "wss://")
    bridge_ws_url += f"/v1/terminal/ws?token={settings.CHAT_BRIDGE_TOKEN}&session={quote(session)}"
    if command:
        bridge_ws_url += f"&command={quote(command)}"
    if cwd:
        bridge_ws_url += f"&cwd={quote(cwd)}"
    bridge_ws_url += f"&cols={cols}&rows={rows}"

    try:
        async with ws_connect(bridge_ws_url) as bridge_ws:

            async def pump_to_bridge() -> None:
                try:
                    while True:
                        message = await websocket.receive_text()
                        await bridge_ws.send(message)
                except (WebSocketDisconnect, ConnectionClosed):
                    pass

            async def pump_from_bridge() -> None:
                try:
                    async for message in bridge_ws:
                        await websocket.send_text(message)
                except ConnectionClosed:
                    pass

            _done, pending = await asyncio.wait(
                [asyncio.create_task(pump_to_bridge()), asyncio.create_task(pump_from_bridge())],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
    finally:
        # Covers a dropped connection (Fase 6.1's client-side reconnect
        # loop) exactly like a deliberate tab close -- both are real
        # disconnects from this session's point of view.
        await _audit_terminal_event(session, "closed", user.username, {})
