"""ForgeHub chat bridge.

Runs on the HOST (not in Docker) because the real Hermes Foundation agents
(Athos, Atlas, ...) are host processes invoked via the `hermes` CLI -- the
forgehub-backend container has no access to that CLI or its venv. This
service is the only thing that shells out to `hermes chat`; the backend
container reaches it over the Docker bridge network
(http://host.docker.internal:<port>) and never touches the CLI directly.

Endpoints:
  POST /v1/chat          -- send a message to a profile, get the agent's reply
  POST /v1/transcribe    -- speech-to-text for an uploaded audio clip
  WS   /v1/terminal/ws   -- a real PTY (bash) on the host, proxied to the
                            browser through forgehub-backend's own WS relay

Auth: every HTTP request must carry `X-Bridge-Token` matching BRIDGE_TOKEN
below (shared secret with forgehub-backend's CHAT_BRIDGE_TOKEN); the
terminal WS takes the same token as a query param since browsers can't set
custom headers on a WebSocket handshake -- but the browser never connects
here directly, only forgehub-backend does (see api/routes/terminal.py),
so the token never reaches client JS. Without this check, any container on
the same Docker network could otherwise drive these agents or get a root
shell on the host.
"""

import asyncio
import base64
import codecs
import contextlib
import fcntl
import io
import json
import os
import pty
import re
import shlex
import shutil
import signal
import socket
import sqlite3
import struct
import subprocess
import tarfile
import tempfile
import termios
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

import httpx
import yaml
import websockets

from fastapi import FastAPI, Header, HTTPException, Query, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from vpn_control import VpnControl, VpnPolicyError

BRIDGE_TOKEN = os.environ["FORGEHUB_BRIDGE_TOKEN"]
HERMES_PYTHON = "/usr/local/lib/hermes-agent/venv/bin/python"
PROFILES_DIR = Path("/root/.hermes/profiles")

# A profile is chattable if it's a real Hermes profile directory -- matches
# whatever ForgeHub's Hermes sync populated as Agent.profile_slug (24
# profiles as of writing, not just the 8 with an active gateway service;
# `hermes chat -p <profile>` doesn't need the gateway running). The name
# pattern guards against path traversal (e.g. "../../etc") since it's
# concatenated into a filesystem path below.
PROFILE_NAME_RE = re.compile(r"^[a-z0-9_-]+$")

CHAT_TIMEOUT_SECONDS = 600
SESSION_ID_RE = re.compile(r"session_id:\s*(\S+)")

# stream_id (minted by hermes_stream.py per request, see its --stream-id-less
# self-generated id) -> the live subprocess, so POST /v1/chat/approve can
# write an approval decision into the right agent's stdin.
_active_streams: dict[str, "asyncio.subprocess.Process"] = {}

# Governed non-interactive CLI runs. This registry intentionally stores only
# process state/output, never ForgeRouter credentials or prompts. ForgeHub's DB
# remains the durable source of task/execution metadata.
AGENT_RUN_STATE_DIR = Path(os.environ.get("FORGEHUB_RUN_STATE_DIR", "/root/.forgehub/agent-runs"))
AGENT_RUN_STATE_DIR.mkdir(parents=True, exist_ok=True)
AGENT_RUN_ADAPTER_VERSION = "forgehub-host-runner/v1"
_agent_runs: dict[str, dict] = {}
_agent_runs_lock = threading.Lock()

# Shared Chromium session for ForgeHub's Workspace. Athos attaches to this
# exact browser over CDP (browser.cdp_url), while the Workspace polls CDP
# screenshots through the authenticated backend proxy. The browser profile is
# persistent so cookies/localStorage survive bridge restarts; credentials are
# never stored here.
WORKSPACE_BROWSER_PORT = int(os.environ.get("FORGEHUB_BROWSER_CDP_PORT", "9223"))
WORKSPACE_BROWSER_CDP_URL = f"http://127.0.0.1:{WORKSPACE_BROWSER_PORT}"
WORKSPACE_BROWSER_PROFILE_DIR = Path(
    os.environ.get("FORGEHUB_BROWSER_PROFILE_DIR", "/root/.forgehub/browser/athos")
)
WORKSPACE_BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
WORKSPACE_BROWSER_BINARY = os.environ.get(
    "FORGEHUB_BROWSER_BINARY", "/root/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome"
)
_workspace_browser_process: subprocess.Popen | None = None
_workspace_browser_lock = threading.Lock()
# Last known pointer position in viewport coordinates, set by either a human
# drag/click (dispatchMouseEvent) or a routine "click"/"type"/"select" step
# (resolved from the target element's own bounding box, since those steps
# call el.click()/el.focus() directly rather than dispatching a real mouse
# event at a coordinate). Surfaced on every /state poll so the frontend can
# draw a transient cursor marker -- otherwise an agent-driven interaction is
# invisible in the shared live view.
_last_pointer: dict | None = None
# Who is currently driving the browser: "user" (a real human action through
# this pane's own controls) or "agent" (a routine step, or a click the
# injected DOM listener saw that this process didn't just dispatch itself --
# Athos's native browser_* toolset talks to the same CDP target directly,
# bypassing every endpoint below, so that's the only way to notice it).
# Cleared back to None after CONTROL_RELEASE_SECONDS of inactivity so the
# frontend's "agent in control" border goes away once nothing is happening.
_control_owner: str | None = None
_control_at: datetime | None = None
_last_seen_click_ms: float = 0.0
CONTROL_RELEASE_SECONDS = 2.5

# A native window.alert/confirm/prompt() called by the page being shown.
# Confirmed by direct reproduction (2026-07-28) that this headless Chrome
# build does NOT reliably support CDP's Page.javascriptDialogOpening/
# handleJavaScriptDialog round-trip: an unhandled dialog freezes the
# renderer's entire CDP command queue indefinitely (Runtime.evaluate,
# Page.captureScreenshot, Input.dispatchMouseEvent, even a *second*
# connection's Page.enable -- everything), and Page.handleJavaScriptDialog
# itself unreliably reports "No dialog is showing" even from a session that
# had Page enabled before the dialog opened, with no way found to actually
# resolve one once stuck (recovery required killing and relaunching the
# whole process, twice, during investigation). Since this is a single
# shared browser, one page's confirm() would otherwise take the whole
# Workspace Browser down for every viewer.
#
# Given that, this never lets a real native dialog happen at all:
# _hold_dialog_override_connection (a persistent background task, kept
# alive for the browser process's lifetime -- see its own docstring for why
# a persistent connection specifically is required) injects a
# Page.addScriptToEvaluateOnNewDocument script that replaces
# window.alert/confirm/prompt before any page script runs, recording the
# call and resolving it immediately (confirm() -> true, matching "the
# operator already clicked the button that asked for this confirmation")
# instead of ever blocking on a native dialog. The frontend surfaces the
# most recent one as a transient, already-resolved notice
# (WorkspaceBrowserState.last_dialog) -- there is nothing to answer.
_workspace_browser_dialog_override_task: "asyncio.Task | None" = None

DIALOG_OVERRIDE_SCRIPT = """
(() => {
  const record = (type, message) => { window.__fhLastDialog = { type, message: String(message ?? ''), at: Date.now() }; };
  window.alert = (message) => { record('alert', message); };
  window.confirm = (message) => { record('confirm', message); return true; };
  window.prompt = (message, defaultValue) => { record('prompt', message); return defaultValue ?? ''; };
})();
"""

# Last successful screenshot -- re-served whenever a call is made with
# include_image=False (e.g. the resize endpoint), so that response's
# image_base64 doesn't clobber the frontend's currently-displayed frame
# with None.
_last_workspace_browser_image: str | None = None


def _run_state_path(run_id: str) -> Path:
    return AGENT_RUN_STATE_DIR / f"{run_id}.json"


def _safe_run_state(run: dict) -> dict:
    """Persist process metadata and bounded output, never prompts or credentials."""
    return {
        key: value for key, value in run.items()
        if key != "process" and key not in {"prompt", "api_key", "command", "environment"}
    }


def _persist_agent_run(run_id: str) -> None:
    run = _agent_runs.get(run_id)
    if run is None:
        return
    target = _run_state_path(run_id)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(_safe_run_state(run), sort_keys=True))
    temporary.replace(target)


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _redact_run_output(value: str) -> str:
    value = re.sub(r"(?i)(authorization:\s*bearer\s+)[^\s]+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)((?:api[_-]?key|auth[_-]?token)\s*[=:]\s*)[^\s,}\"]+", r"\1[REDACTED]", value)
    value = re.sub(r"\b(?:sk|key)-[A-Za-z0-9_-]{16,}\b", "[REDACTED]", value)
    return value


def _load_agent_runs() -> None:
    for state_file in AGENT_RUN_STATE_DIR.glob("*.json"):
        try:
            run = json.loads(state_file.read_text())
            if run.get("status") in {"starting", "running"}:
                if _pid_alive(run.get("pid")):
                    run["status"] = "running"
                    run["reconciled_at"] = datetime.now().isoformat()
                else:
                    run["status"] = "stale"
                    run["error"] = "Runner restarted and the recorded process is no longer alive"
                    run["finished_at"] = datetime.now().isoformat()
            _agent_runs[run["run_id"]] = run
            _persist_agent_run(run["run_id"])
        except (OSError, ValueError, KeyError, TypeError):
            continue


_load_agent_runs()



def _is_valid_profile(profile: str) -> bool:
    return bool(PROFILE_NAME_RE.match(profile)) and (PROFILES_DIR / profile).is_dir()


# "/plugins <agent>" peeks at a different profile's plugins without leaving
# the current chat tab -- see chat_stream's handling below. Hermes's own
# /plugins handler ignores any argument after the command, so redirecting
# which profile-home the one-shot subprocess runs against is the only way
# to make the argument do anything.
PLUGINS_CROSS_AGENT_RE = re.compile(r"^/plugins\s+([a-z0-9_-]+)\s*$", re.IGNORECASE)

UPLOAD_DIR = Path(tempfile.gettempdir()) / "forgehub-chat-uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="ForgeHub chat bridge")
_vpn_control = VpnControl()


def _check_token(x_bridge_token: str | None) -> None:
    if not x_bridge_token or x_bridge_token != BRIDGE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing bridge token")


def _workspace_browser_running() -> bool:
    if _workspace_browser_process is not None and _workspace_browser_process.poll() is None:
        return True
    try:
        with socket.create_connection(("127.0.0.1", WORKSPACE_BROWSER_PORT), timeout=0.2):
            return True
    except OSError:
        return False


def _launch_workspace_browser() -> None:
    """Start the one shared CDP browser without accepting shell arguments."""
    global _workspace_browser_process
    with _workspace_browser_lock:
        if not _workspace_browser_running():
            binary = Path(WORKSPACE_BROWSER_BINARY)
            if not binary.is_file():
                raise HTTPException(status_code=503, detail=f"Chromium binary not found: {binary}")
            _workspace_browser_process = subprocess.Popen(
                [
                    str(binary), "--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
                    "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                    "--remote-allow-origins=*", "--remote-debugging-address=127.0.0.1",
                    f"--remote-debugging-port={WORKSPACE_BROWSER_PORT}",
                    f"--user-data-dir={WORKSPACE_BROWSER_PROFILE_DIR}", "--window-size=1440,900",
                    "about:blank",
                ],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
    _ensure_dialog_override_task()


def _ensure_dialog_override_task() -> None:
    global _workspace_browser_dialog_override_task
    if _workspace_browser_dialog_override_task is None or _workspace_browser_dialog_override_task.done():
        _workspace_browser_dialog_override_task = asyncio.create_task(_hold_dialog_override_connection())


async def _hold_dialog_override_connection() -> None:
    """Keeps one CDP connection open for the browser process's entire
    lifetime, solely to keep DIALOG_OVERRIDE_SCRIPT registered via
    Page.addScriptToEvaluateOnNewDocument -- confirmed by reproduction that
    this registration is scoped to the session/connection that made it, not
    the browser process: it's silently dropped the instant that connection
    closes, so the connect-register-disconnect every other CDP call in this
    file does (_workspace_browser_cdp) doesn't survive to the next
    navigation. Page.enable must be called on this SAME connection *before*
    addScriptToEvaluateOnNewDocument, or the registration silently has no
    effect on future navigations either -- also confirmed by reproduction
    (isolated repro: identical calls without a prior Page.enable left the
    injected marker undefined after navigating; with it, the marker
    survived). Also applies the override immediately (via Runtime.evaluate)
    to whatever page happens to be loaded right when this connection is
    established, since addScriptToEvaluateOnNewDocument only covers *future*
    navigations. Retries quietly on disconnect (browser not up yet, process
    killed/relaunched, transient CDP hiccup)."""
    while True:
        try:
            target = await _workspace_browser_target()
            async with websockets.connect(
                target["webSocketDebuggerUrl"], open_timeout=5, close_timeout=2, max_size=16 * 1024 * 1024
            ) as socket:
                await socket.send(json.dumps({"id": 1, "method": "Page.enable", "params": {}}))
                await asyncio.wait_for(socket.recv(), timeout=5)
                await socket.send(
                    json.dumps({"id": 2, "method": "Page.addScriptToEvaluateOnNewDocument", "params": {"source": DIALOG_OVERRIDE_SCRIPT}})
                )
                await asyncio.wait_for(socket.recv(), timeout=5)
                await socket.send(json.dumps({"id": 3, "method": "Runtime.evaluate", "params": {"expression": DIALOG_OVERRIDE_SCRIPT}}))
                await asyncio.wait_for(socket.recv(), timeout=5)
                # Nothing else is ever sent on this connection -- just block
                # here until the browser process dies/disconnects it, so the
                # registration (tied to this connection staying open) lasts
                # exactly as long as the browser does.
                await socket.wait_closed()
        except Exception:
            # Deliberately broad: this task silently dying (an uncaught
            # exception on an asyncio.create_task is otherwise only ever
            # logged to stderr, never restarted) would quietly bring back
            # the exact freeze this whole mechanism exists to prevent, with
            # no visible symptom until the next confirm() call hangs the
            # shared browser again. Retrying past anything unexpected here
            # is strictly safer than that.
            await asyncio.sleep(1)


async def _workspace_browser_target() -> dict:
    _launch_workspace_browser()
    async with httpx.AsyncClient(timeout=3.0) as client:
        for _ in range(30):
            try:
                response = await client.get(f"{WORKSPACE_BROWSER_CDP_URL}/json/list")
                response.raise_for_status()
                page = next((item for item in response.json() if item.get("type") == "page"), None)
                if page and page.get("webSocketDebuggerUrl"):
                    return page
            except (httpx.HTTPError, ValueError):
                pass
            await asyncio.sleep(0.1)
    raise HTTPException(status_code=503, detail="Workspace browser did not expose a CDP page")


async def _workspace_browser_cdp(method: str, params: dict | None = None) -> dict:
    target = await _workspace_browser_target()
    async with websockets.connect(
        target["webSocketDebuggerUrl"], open_timeout=5, close_timeout=2, max_size=16 * 1024 * 1024
    ) as socket:
        await socket.send(json.dumps({"id": 1, "method": method, "params": params or {}}))
        while True:
            payload = json.loads(await asyncio.wait_for(socket.recv(), timeout=15))
            if payload.get("id") != 1:
                continue
            if "error" in payload:
                raise HTTPException(status_code=502, detail=f"Browser CDP error: {payload['error']}")
            return payload.get("result", {})



async def _workspace_browser_state(include_image: bool = True) -> dict:
    global _last_seen_click_ms, _last_workspace_browser_image
    runtime = await _workspace_browser_cdp(
        "Runtime.evaluate",
        {
            # Installs a capturing click listener once per document (wiped by
            # navigation, so this idempotently reinstalls it every poll) so a
            # click from ANY CDP client -- including Athos's native browser_*
            # toolset, which talks to this same target directly and never
            # touches the endpoints below -- still surfaces here. Also reads
            # window.__fhLastDialog, set by DIALOG_OVERRIDE_SCRIPT whenever
            # the page calls alert/confirm/prompt (already auto-resolved by
            # then -- see that script's own docstring for why).
            "expression": """(() => {
              if (!window.__fhClickInstalled) {
                window.__fhClickInstalled = true;
                window.addEventListener('click', (e) => { window.__fhLastClick = {x: e.clientX, y: e.clientY, at: Date.now()}; }, true);
              }
              return JSON.stringify({url:location.href,title:document.title,readyState:document.readyState,viewportWidth:innerWidth,viewportHeight:innerHeight,click:window.__fhLastClick||null,dialog:window.__fhLastDialog||null});
            })()""",
            "returnByValue": True,
        },
    )
    try:
        metadata = json.loads(runtime.get("result", {}).get("value") or "{}")
    except ValueError:
        metadata = {}
    click = metadata.get("click")
    if click and click.get("at", 0) > _last_seen_click_ms:
        _last_seen_click_ms = click["at"]
        recently_explained = _control_at is not None and (datetime.now() - _control_at).total_seconds() < 1.2
        _mark_pointer(click["x"], click["y"])
        _mark_control(_control_owner if recently_explained and _control_owner else "agent")
    control_owner = _control_owner
    if _control_at is not None and (datetime.now() - _control_at).total_seconds() > CONTROL_RELEASE_SECONDS:
        control_owner = None
    image_base64 = None
    if include_image:
        screenshot = await _workspace_browser_cdp(
            "Page.captureScreenshot", {"format": "jpeg", "quality": 75, "fromSurface": True}
        )
        image_base64 = screenshot.get("data")
        _last_workspace_browser_image = image_base64
    return {
        "running": _workspace_browser_running(), "cdp_url": WORKSPACE_BROWSER_CDP_URL,
        "url": metadata.get("url", "about:blank"), "title": metadata.get("title", ""),
        "ready_state": metadata.get("readyState", ""),
        # Never clobber the last real screenshot with None just because
        # this particular call was include_image=False (e.g. the resize
        # endpoint) -- only a genuinely fresh capture replaces it.
        "image_base64": image_base64 if image_base64 is not None else _last_workspace_browser_image,
        "viewport_width": metadata.get("viewportWidth", 1440),
        "viewport_height": metadata.get("viewportHeight", 900),
        "captured_at": datetime.now().isoformat(),
        "last_pointer": _last_pointer,
        "control_owner": control_owner,
        "last_dialog": metadata.get("dialog"),
    }


class WorkspaceBrowserStartRequest(BaseModel):
    url: str = "about:blank"


class WorkspaceBrowserNavigateRequest(BaseModel):
    url: str


class WorkspaceBrowserPointerRequest(BaseModel):
    x: float
    y: float
    end_x: float | None = None
    end_y: float | None = None


class WorkspaceBrowserTextRequest(BaseModel):
    text: str


class WorkspaceBrowserScrollRequest(BaseModel):
    x: float
    y: float
    delta_y: float


class WorkspaceBrowserLoginRequest(BaseModel):
    url: str
    username: str
    password: str


class WorkspaceBrowserRoutineRequest(BaseModel):
    start_url: str
    steps: list[dict]


class WorkspaceBrowserResizeRequest(BaseModel):
    width: int
    height: int


# Guards against a zero/negative size (a pane measured before its first
# layout pass) and an absurd one (a stray value from a bad ResizeObserver
# read) -- Chrome's own headless window is comfortable at any size in
# between.
_WORKSPACE_BROWSER_MIN_DIMENSION = 400
_WORKSPACE_BROWSER_MAX_DIMENSION = 4000


def _validated_browser_url(value: str) -> str:
    if value == "about:blank":
        return value
    if not re.match(r"^https?://", value, flags=re.IGNORECASE):
        raise HTTPException(status_code=400, detail="Only HTTP(S) browser URLs are allowed")
    return value


@app.post("/v1/workspace-browser/start")
async def start_workspace_browser(req: WorkspaceBrowserStartRequest, x_bridge_token: str | None = Header(default=None)) -> dict:
    _check_token(x_bridge_token)
    _launch_workspace_browser()
    _mark_control("user")
    url = _validated_browser_url(req.url)
    if url != "about:blank":
        await _workspace_browser_cdp("Page.navigate", {"url": url})
        await asyncio.sleep(0.8)
    return await _workspace_browser_state()


@app.get("/v1/workspace-browser/state")
async def get_workspace_browser_state(x_bridge_token: str | None = Header(default=None)) -> dict:
    _check_token(x_bridge_token)
    return await _workspace_browser_state()


@app.post("/v1/workspace-browser/navigate")
async def navigate_workspace_browser(req: WorkspaceBrowserNavigateRequest, x_bridge_token: str | None = Header(default=None)) -> dict:
    _check_token(x_bridge_token)
    _mark_control("user")
    await _workspace_browser_cdp("Page.navigate", {"url": _validated_browser_url(req.url)})
    await asyncio.sleep(0.8)
    return await _workspace_browser_state()


@app.post("/v1/workspace-browser/reload")
async def reload_workspace_browser(x_bridge_token: str | None = Header(default=None)) -> dict:
    _check_token(x_bridge_token)
    _mark_control("user")
    await _workspace_browser_cdp("Page.reload", {"ignoreCache": True})
    await asyncio.sleep(0.6)
    return await _workspace_browser_state()


@app.post("/v1/workspace-browser/back")
async def back_workspace_browser(x_bridge_token: str | None = Header(default=None)) -> dict:
    _check_token(x_bridge_token)
    _mark_control("user")
    history = await _workspace_browser_cdp("Page.getNavigationHistory")
    index, entries = history.get("currentIndex", 0), history.get("entries", [])
    if index > 0:
        await _workspace_browser_cdp("Page.navigateToHistoryEntry", {"entryId": entries[index - 1]["id"]})
        await asyncio.sleep(0.6)
    return await _workspace_browser_state()


@app.post("/v1/workspace-browser/resize")
async def resize_workspace_browser(
    req: WorkspaceBrowserResizeRequest, x_bridge_token: str | None = Header(default=None)
) -> dict:
    """Overrides the page's own layout viewport to match the actual on-screen
    size of whichever WebAppPane is currently showing it (see frontend's
    ResizeObserver in WebAppPane.tsx) -- without this, the shared headless
    browser stays at its fixed launch size (_launch_workspace_browser's
    --window-size=1440,900) regardless of the pane's real aspect ratio,
    which the frontend's `object-contain` rendering then letterboxes (dead
    space on two sides) and, more importantly, is exactly the mismatch that
    made click coordinates in browserCoordinates() land in the wrong place
    near the letterboxed edges. Uses Emulation.setDeviceMetricsOverride
    (page-level) rather than Browser.setWindowBounds (the outer OS window)
    deliberately: the latter's `bounds` is the window's outer rect, which
    silently loses height to window-chrome overhead the resulting
    innerHeight/screenshot never gets back -- confirmed requesting height
    600 landing at innerHeight 457. The device-metrics override instead
    fixes the *content* viewport at exactly the requested size regardless
    of any window chrome, which is what actually needs to match the pane."""
    _check_token(x_bridge_token)
    width = max(_WORKSPACE_BROWSER_MIN_DIMENSION, min(_WORKSPACE_BROWSER_MAX_DIMENSION, req.width))
    height = max(_WORKSPACE_BROWSER_MIN_DIMENSION, min(_WORKSPACE_BROWSER_MAX_DIMENSION, req.height))
    await _workspace_browser_cdp(
        "Emulation.setDeviceMetricsOverride",
        {"width": width, "height": height, "deviceScaleFactor": 0, "mobile": False},
    )
    return await _workspace_browser_state(include_image=False)


@app.post("/v1/workspace-browser/pointer")
async def pointer_workspace_browser(req: WorkspaceBrowserPointerRequest, x_bridge_token: str | None = Header(default=None)) -> dict:
    _check_token(x_bridge_token)
    _mark_control("user")
    end_x = req.end_x if req.end_x is not None else req.x
    end_y = req.end_y if req.end_y is not None else req.y
    if not all(0 <= value <= 10_000 for value in (req.x, req.y, end_x, end_y)):
        raise HTTPException(status_code=400, detail="Pointer coordinates are outside the browser viewport")
    await _workspace_browser_cdp(
        "Input.dispatchMouseEvent",
        {"type": "mousePressed", "x": req.x, "y": req.y, "button": "left", "buttons": 1, "clickCount": 1},
    )
    if end_x != req.x or end_y != req.y:
        await _workspace_browser_cdp(
            "Input.dispatchMouseEvent",
            {"type": "mouseMoved", "x": end_x, "y": end_y, "button": "left", "buttons": 1},
        )
    await _workspace_browser_cdp(
        "Input.dispatchMouseEvent",
        {"type": "mouseReleased", "x": end_x, "y": end_y, "button": "left", "buttons": 0, "clickCount": 1},
    )
    global _last_pointer
    _last_pointer = {"x": end_x, "y": end_y, "at": datetime.now().isoformat()}
    await asyncio.sleep(0.25)
    return await _workspace_browser_state()


@app.post("/v1/workspace-browser/text")
async def text_workspace_browser(req: WorkspaceBrowserTextRequest, x_bridge_token: str | None = Header(default=None)) -> dict:
    _check_token(x_bridge_token)
    _mark_control("user")
    await _workspace_browser_cdp("Input.insertText", {"text": req.text})
    await asyncio.sleep(0.2)
    return await _workspace_browser_state()


@app.post("/v1/workspace-browser/scroll")
async def scroll_workspace_browser(
    req: WorkspaceBrowserScrollRequest, x_bridge_token: str | None = Header(default=None)
) -> dict:
    _check_token(x_bridge_token)
    _mark_control("user")
    if not 0 <= req.x <= 10_000 or not 0 <= req.y <= 10_000:
        raise HTTPException(status_code=400, detail="Scroll coordinates are outside the browser viewport")
    delta_y = max(-5_000, min(5_000, req.delta_y))
    await _workspace_browser_cdp(
        "Input.dispatchMouseEvent",
        {
            "type": "mouseWheel",
            "x": req.x,
            "y": req.y,
            "deltaX": 0,
            "deltaY": delta_y,
        },
    )
    await asyncio.sleep(0.15)
    return await _workspace_browser_state()


@app.post("/v1/workspace-browser/login-forgehub")
async def login_workspace_browser(req: WorkspaceBrowserLoginRequest, x_bridge_token: str | None = Header(default=None)) -> dict:
    """Login without persisting or returning the supplied credential."""
    _check_token(x_bridge_token)
    _mark_control("user")
    await _workspace_browser_cdp("Page.navigate", {"url": _validated_browser_url(req.url)})
    await asyncio.sleep(1.0)
    script = f"""
      (() => {{
        const setValue = (element, value) => {{
          const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
          setter.call(element, value);
          element.dispatchEvent(new Event('input', {{ bubbles: true }}));
          element.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }};
        const username = document.querySelector('#username');
        const password = document.querySelector('#password');
        if (!username || !password) return 'login-fields-not-found';
        setValue(username, {json.dumps(req.username)});
        setValue(password, {json.dumps(req.password)});
        return username.closest('form') ? 'filled' : 'login-form-not-found';
      }})()
    """
    result = await _workspace_browser_cdp(
        "Runtime.evaluate", {"expression": script, "returnByValue": True, "awaitPromise": True}
    )
    outcome = result.get("result", {}).get("value")
    if outcome != "filled":
        raise HTTPException(status_code=409, detail=f"ForgeHub login failed: {outcome}")
    # React applies controlled-input state asynchronously; submitting in the
    # same JS turn leaves the button disabled and the handler sees old values.
    await asyncio.sleep(0.2)
    submit = await _workspace_browser_cdp(
        "Runtime.evaluate",
        {
            "expression": "document.querySelector('#username')?.closest('form')?.querySelector('button[type=submit]')?.click(); 'submitted'",
            "returnByValue": True,
        },
    )
    if submit.get("result", {}).get("value") != "submitted":
        raise HTTPException(status_code=409, detail="ForgeHub login submit failed")
    await asyncio.sleep(1.2)
    return await _workspace_browser_state()


async def _routine_evaluate(expression: str):
    result = await _workspace_browser_cdp(
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": True},
    )
    remote = result.get("result", {})
    if remote.get("subtype") == "error":
        raise HTTPException(status_code=409, detail=remote.get("description", "Browser expression failed"))
    return remote.get("value")


def _mark_pointer(x: float, y: float) -> None:
    """Record where a routine step just interacted, for the /state cursor overlay."""
    global _last_pointer
    _last_pointer = {"x": x, "y": y, "at": datetime.now().isoformat()}


def _mark_control(owner: str) -> None:
    """Record who is currently driving the browser (see _control_owner docstring)."""
    global _control_owner, _control_at
    _control_owner = owner
    _control_at = datetime.now()


async def _element_center_evaluate(expression_body: str, selector: str) -> str | None:
    """Run a JS expression that resolves to {outcome, x, y} on the element's center,
    or null if the element wasn't found. Marks the pointer and returns outcome."""
    raw = await _routine_evaluate(
        f"""(() => {{
          const el=document.querySelector({json.dumps(selector)});
          if(!el) return null;
          {expression_body}
          const rect = el.getBoundingClientRect();
          return JSON.stringify({{outcome, x: rect.left + rect.width/2, y: rect.top + rect.height/2}});
        }})()"""
    )
    if raw is None:
        return None
    result = json.loads(raw)
    _mark_pointer(result["x"], result["y"])
    return result["outcome"]


async def _run_browser_routine_step(step: dict) -> str:
    _mark_control("agent")
    action = step.get("action")
    selector = step.get("selector")
    value = step.get("value")
    if action == "navigate":
        await _workspace_browser_cdp("Page.navigate", {"url": _validated_browser_url(str(step.get("url", "")))})
        await asyncio.sleep(0.8)
        return "navigated"
    if action == "click":
        outcome = await _element_center_evaluate(
            "el.scrollIntoView({block:'center'}); el.click(); const outcome='clicked';", selector
        )
        if outcome != "clicked":
            raise HTTPException(status_code=409, detail=f"Selector not found: {selector}")
        await asyncio.sleep(0.3)
        return outcome
    if action == "type":
        outcome = await _element_center_evaluate(
            """el.scrollIntoView({block:'center'}); el.focus();
              if ('value' in el) {
                const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
                const setter=Object.getOwnPropertyDescriptor(proto,'value')?.set;
                setter ? setter.call(el,'') : (el.value='');
                el.dispatchEvent(new Event('input',{bubbles:true}));
              } else if (el.isContentEditable) el.textContent='';
              const outcome='focused';""",
            selector,
        )
        if outcome != "focused":
            raise HTTPException(status_code=409, detail=f"Selector not found: {selector}")
        await _workspace_browser_cdp("Input.insertText", {"text": str(value or "")})
        await asyncio.sleep(0.2)
        return "typed"
    if action == "select":
        outcome = await _element_center_evaluate(
            f"""if(!(el instanceof HTMLSelectElement)) return null;
              el.value={json.dumps(value)}; el.dispatchEvent(new Event('input',{{bubbles:true}}));
              el.dispatchEvent(new Event('change',{{bubbles:true}})); const outcome='selected';""",
            selector,
        )
        if outcome != "selected":
            raise HTTPException(status_code=409, detail=f"Select not found: {selector}")
        return outcome
    if action == "press":
        key = str(value or "")
        if key not in {"Enter", "Tab", "Escape", "ArrowUp", "ArrowDown", "Space"}:
            raise HTTPException(status_code=400, detail=f"Unsupported key: {key}")
        await _workspace_browser_cdp("Input.dispatchKeyEvent", {"type": "keyDown", "key": key})
        await _workspace_browser_cdp("Input.dispatchKeyEvent", {"type": "keyUp", "key": key})
        await asyncio.sleep(0.2)
        return f"pressed:{key}"
    if action == "scroll":
        delta = max(-5000, min(5000, int(step.get("delta_y") or 500)))
        await _routine_evaluate(f"window.scrollBy({{top:{delta},behavior:'instant'}}); 'scrolled'")
        await asyncio.sleep(0.15)
        return "scrolled"
    if action == "wait":
        wait_ms = max(0, min(30_000, int(step.get("wait_ms") or 500)))
        await asyncio.sleep(wait_ms / 1000)
        return f"waited:{wait_ms}"
    if action == "assert_text":
        outcome = await _routine_evaluate(
            f"(() => {{ const root={json.dumps(selector)} ? document.querySelector({json.dumps(selector)}) : document.body; if(!root) return 'not-found'; return (root.innerText || root.textContent || '').includes({json.dumps(value)}); }})()"
        )
        if outcome is not True:
            raise HTTPException(status_code=409, detail=f"Expected text not found: {value}")
        return "asserted"
    raise HTTPException(status_code=400, detail=f"Unsupported routine action: {action}")


@app.post("/v1/workspace-browser/run-routine")
async def run_workspace_browser_routine(
    req: WorkspaceBrowserRoutineRequest, x_bridge_token: str | None = Header(default=None)
) -> dict:
    """Execute reviewed structured steps; arbitrary JavaScript is never accepted."""
    _check_token(x_bridge_token)
    if not 1 <= len(req.steps) <= 100:
        raise HTTPException(status_code=400, detail="A routine must contain 1 to 100 steps")
    _mark_control("agent")
    # Skip the implicit start_url navigation when the routine's own first
    # step already navigates -- otherwise every run flashes start_url (the
    # product's registered application_url, which may not even be the host
    # currently running it) before immediately navigating away again.
    if not (req.steps and req.steps[0].get("action") == "navigate"):
        await _workspace_browser_cdp("Page.navigate", {"url": _validated_browser_url(req.start_url)})
        await asyncio.sleep(0.8)
    results: list[dict] = []
    status_value = "passed"
    for index, step in enumerate(req.steps, 1):
        try:
            outcome = await _run_browser_routine_step(step)
            results.append({"index": index, "action": step.get("action"), "status": "passed", "outcome": outcome})
        except HTTPException as exc:
            status_value = "failed"
            results.append({"index": index, "action": step.get("action"), "status": "failed", "outcome": str(exc.detail)})
            break
    return {"status": status_value, "steps": results, "browser": await _workspace_browser_state()}


# ---------------------------------------------------------------------------
# Isolated background test browser -- a dedicated, throwaway CDP Chromium
# per test run, deliberately separate from the shared Workspace Browser
# above (own port, own ephemeral profile dir per run). A background test
# must never compete with whatever the operator/agent is doing live in the
# shared instance -- that's the whole reason this isn't a `headless: true`
# flag on run-routine (which was already headless; isolation, not
# visibility, is what a background test needs -- see the plan's Fase 3).
#
# The step-execution logic here (_run_test_browser_step and its helpers)
# deliberately duplicates _run_browser_routine_step's ~80 lines rather than
# refactoring that shared function to take an explicit CDP target: the
# shared version is called from many other live endpoints above, threading
# a target through all of them is a large, risky change for a
# comparatively small amount of duplication.
# ---------------------------------------------------------------------------

TEST_BROWSER_CDP_PORT_BASE = int(os.environ.get("FORGEHUB_TEST_BROWSER_CDP_PORT_BASE", "9300"))
TEST_BROWSER_PROFILE_ROOT = Path(
    os.environ.get("FORGEHUB_TEST_BROWSER_PROFILE_ROOT", "/root/.forgehub/browser/test-runs")
)
TEST_BROWSER_PROFILE_ROOT.mkdir(parents=True, exist_ok=True)
TEST_RUN_STATE_DIR = Path(os.environ.get("FORGEHUB_TEST_RUN_STATE_DIR", "/root/.forgehub/test-runs"))
TEST_RUN_STATE_DIR.mkdir(parents=True, exist_ok=True)
TEST_RUN_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")

_test_runs: dict[str, dict] = {}
_test_runs_lock = threading.Lock()


def _test_run_state_path(test_run_id: str) -> Path:
    return TEST_RUN_STATE_DIR / f"{test_run_id}.json"


def _persist_test_run(test_run_id: str) -> None:
    run = _test_runs.get(test_run_id)
    if run is None:
        return
    target = _test_run_state_path(test_run_id)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(run, sort_keys=True))
    tmp.replace(target)


def _allocate_test_browser_port() -> int:
    """First port in the range with nothing listening on it. Racy in theory
    (another process could grab it between the check and Chromium's own
    bind), but concurrent background test runs are rare enough that a
    50-port range makes a real collision very unlikely, and Chromium simply
    fails to start cleanly if one does happen."""
    for offset in range(50):
        port = TEST_BROWSER_CDP_PORT_BASE + offset
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.05):
                continue
        except OSError:
            return port
    raise HTTPException(status_code=503, detail="No free port available for an isolated test browser")


def _launch_test_browser(test_run_id: str, port: int) -> subprocess.Popen:
    binary = Path(WORKSPACE_BROWSER_BINARY)
    if not binary.is_file():
        raise HTTPException(status_code=503, detail=f"Chromium binary not found: {binary}")
    profile_dir = TEST_BROWSER_PROFILE_ROOT / test_run_id
    profile_dir.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        [
            str(binary), "--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
            "--disable-gpu", "--no-first-run", "--no-default-browser-check",
            "--remote-allow-origins=*", "--remote-debugging-address=127.0.0.1",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}", "--window-size=1440,900",
            "about:blank",
        ],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


async def _test_browser_target(port: int) -> dict:
    async with httpx.AsyncClient(timeout=3.0) as client:
        for _ in range(50):
            try:
                response = await client.get(f"http://127.0.0.1:{port}/json/list")
                response.raise_for_status()
                page = next((item for item in response.json() if item.get("type") == "page"), None)
                if page and page.get("webSocketDebuggerUrl"):
                    return page
            except (httpx.HTTPError, ValueError):
                pass
            await asyncio.sleep(0.1)
    raise HTTPException(status_code=503, detail="Isolated test browser did not expose a CDP page")


async def _test_browser_cdp(ws_url: str, method: str, params: dict | None = None) -> dict:
    async with websockets.connect(
        ws_url, open_timeout=5, close_timeout=2, max_size=16 * 1024 * 1024
    ) as socket_conn:
        await socket_conn.send(json.dumps({"id": 1, "method": method, "params": params or {}}))
        while True:
            payload = json.loads(await asyncio.wait_for(socket_conn.recv(), timeout=15))
            if payload.get("id") != 1:
                continue
            if "error" in payload:
                raise HTTPException(status_code=502, detail=f"Test browser CDP error: {payload['error']}")
            return payload.get("result", {})


async def _test_routine_evaluate(ws_url: str, expression: str):
    result = await _test_browser_cdp(
        ws_url, "Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True}
    )
    remote = result.get("result", {})
    if remote.get("subtype") == "error":
        raise HTTPException(status_code=409, detail=remote.get("description", "Browser expression failed"))
    return remote.get("value")


async def _test_element_center_evaluate(ws_url: str, expression_body: str, selector: str) -> str | None:
    raw = await _test_routine_evaluate(
        ws_url,
        f"""(() => {{
          const el=document.querySelector({json.dumps(selector)});
          if(!el) return null;
          {expression_body}
          const rect = el.getBoundingClientRect();
          return JSON.stringify({{outcome, x: rect.left + rect.width/2, y: rect.top + rect.height/2}});
        }})()""",
    )
    if raw is None:
        return None
    return json.loads(raw)["outcome"]


async def _test_browser_screenshot(ws_url: str) -> str:
    result = await _test_browser_cdp(ws_url, "Page.captureScreenshot", {"format": "jpeg", "quality": 70, "fromSurface": True})
    return result.get("data", "")


async def _run_test_browser_step(ws_url: str, step: dict) -> str:
    """Mirrors _run_browser_routine_step exactly (same actions, same
    outcomes) but against an explicit CDP target and with none of the
    shared browser's control-owner/pointer-overlay side effects, which are
    UI feedback for the live shared pane and meaningless for an isolated
    run nobody is watching."""
    action = step.get("action")
    selector = step.get("selector")
    value = step.get("value")
    if action == "navigate":
        await _test_browser_cdp(ws_url, "Page.navigate", {"url": _validated_browser_url(str(step.get("url", "")))})
        await asyncio.sleep(0.8)
        return "navigated"
    if action == "click":
        outcome = await _test_element_center_evaluate(
            ws_url, "el.scrollIntoView({block:'center'}); el.click(); const outcome='clicked';", selector
        )
        if outcome != "clicked":
            raise HTTPException(status_code=409, detail=f"Selector not found: {selector}")
        await asyncio.sleep(0.3)
        return outcome
    if action == "type":
        outcome = await _test_element_center_evaluate(
            ws_url,
            """el.scrollIntoView({block:'center'}); el.focus();
              if ('value' in el) {
                const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
                const setter=Object.getOwnPropertyDescriptor(proto,'value')?.set;
                setter ? setter.call(el,'') : (el.value='');
                el.dispatchEvent(new Event('input',{bubbles:true}));
              } else if (el.isContentEditable) el.textContent='';
              const outcome='focused';""",
            selector,
        )
        if outcome != "focused":
            raise HTTPException(status_code=409, detail=f"Selector not found: {selector}")
        await _test_browser_cdp(ws_url, "Input.insertText", {"text": str(value or "")})
        await asyncio.sleep(0.2)
        return "typed"
    if action == "select":
        outcome = await _test_element_center_evaluate(
            ws_url,
            f"""if(!(el instanceof HTMLSelectElement)) return null;
              el.value={json.dumps(value)}; el.dispatchEvent(new Event('input',{{bubbles:true}}));
              el.dispatchEvent(new Event('change',{{bubbles:true}})); const outcome='selected';""",
            selector,
        )
        if outcome != "selected":
            raise HTTPException(status_code=409, detail=f"Select not found: {selector}")
        return outcome
    if action == "press":
        key = str(value or "")
        if key not in {"Enter", "Tab", "Escape", "ArrowUp", "ArrowDown", "Space"}:
            raise HTTPException(status_code=400, detail=f"Unsupported key: {key}")
        await _test_browser_cdp(ws_url, "Input.dispatchKeyEvent", {"type": "keyDown", "key": key})
        await _test_browser_cdp(ws_url, "Input.dispatchKeyEvent", {"type": "keyUp", "key": key})
        await asyncio.sleep(0.2)
        return f"pressed:{key}"
    if action == "scroll":
        delta = max(-5000, min(5000, int(step.get("delta_y") or 500)))
        await _test_routine_evaluate(ws_url, f"window.scrollBy({{top:{delta},behavior:'instant'}}); 'scrolled'")
        await asyncio.sleep(0.15)
        return "scrolled"
    if action == "wait":
        wait_ms = max(0, min(30_000, int(step.get("wait_ms") or 500)))
        await asyncio.sleep(wait_ms / 1000)
        return f"waited:{wait_ms}"
    if action == "assert_text":
        outcome = await _test_routine_evaluate(
            ws_url,
            f"(() => {{ const root={json.dumps(selector)} ? document.querySelector({json.dumps(selector)}) : document.body; if(!root) return 'not-found'; return (root.innerText || root.textContent || '').includes({json.dumps(value)}); }})()",
        )
        if outcome is not True:
            raise HTTPException(status_code=409, detail=f"Expected text not found: {value}")
        return "asserted"
    raise HTTPException(status_code=400, detail=f"Unsupported routine action: {action}")


async def _execute_test_browser_run(test_run_id: str, start_url: str, steps: list[dict]) -> None:
    """Runs entirely in the background (kicked off via asyncio.create_task
    by the endpoint below, which has already returned 202) -- launches the
    isolated Chromium, runs every step capturing a screenshot after each
    one (best-effort: a screenshot failure never aborts the test itself),
    tears the process and its profile dir down unconditionally, and writes
    the final result to both the in-memory dict and disk (same
    survives-a-restart pattern as _agent_runs/_persist_agent_run)."""
    port = _allocate_test_browser_port()
    proc: subprocess.Popen | None = None
    screenshot_dir = TEST_RUN_STATE_DIR / test_run_id
    screenshot_paths: list[str] = []
    step_results: list[dict] = []
    status_value = "passed"
    error_text: str | None = None
    try:
        proc = _launch_test_browser(test_run_id, port)
        page = await _test_browser_target(port)
        ws_url = page["webSocketDebuggerUrl"]

        if not (steps and steps[0].get("action") == "navigate"):
            await _test_browser_cdp(ws_url, "Page.navigate", {"url": _validated_browser_url(start_url)})
            await asyncio.sleep(0.8)

        for index, step in enumerate(steps, 1):
            try:
                outcome = await _run_test_browser_step(ws_url, step)
                step_results.append({"index": index, "action": step.get("action"), "status": "passed", "outcome": outcome})
            except HTTPException as exc:
                status_value = "failed"
                step_results.append(
                    {"index": index, "action": step.get("action"), "status": "failed", "outcome": str(exc.detail)}
                )
                break
            finally:
                try:
                    shot = await _test_browser_screenshot(ws_url)
                    if shot:
                        screenshot_dir.mkdir(parents=True, exist_ok=True)
                        shot_path = screenshot_dir / f"step-{index}.jpg"
                        shot_path.write_bytes(base64.b64decode(shot))
                        screenshot_paths.append(str(shot_path))
                except Exception:
                    pass
    except HTTPException as exc:
        status_value = "error"
        error_text = str(exc.detail)
    except Exception as exc:
        status_value = "error"
        error_text = str(exc)
    finally:
        if proc is not None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGTERM)
            with contextlib.suppress(Exception):
                proc.wait(timeout=5)
        with contextlib.suppress(OSError):
            shutil.rmtree(TEST_BROWSER_PROFILE_ROOT / test_run_id, ignore_errors=True)

    report_lines = [f"{'PASSED' if status_value == 'passed' else status_value.upper()} -- {len(step_results)} step(s) executed"]
    for r in step_results:
        report_lines.append(f"  [{r['status']}] {r['index']}. {r['action']}: {r['outcome']}")
    if error_text:
        report_lines.append(f"Error: {error_text}")

    with _test_runs_lock:
        _test_runs[test_run_id] = {
            "test_run_id": test_run_id,
            "status": status_value,
            "steps": step_results,
            "report": "\n".join(report_lines),
            "screenshot_paths": screenshot_paths,
            "error": error_text,
            "finished_at": datetime.now().isoformat(),
        }
        _persist_test_run(test_run_id)


class TestBrowserRunRequest(BaseModel):
    test_run_id: str
    start_url: str
    steps: list[dict]


@app.post("/v1/workspace-browser/test-run", status_code=202)
async def start_test_browser_run(
    req: TestBrowserRunRequest, x_bridge_token: str | None = Header(default=None)
) -> dict:
    """Fire-and-forget: returns as soon as the isolated browser is queued to
    launch, never waits for the test to finish. Poll GET .../test-run/{id}."""
    _check_token(x_bridge_token)
    if not TEST_RUN_ID_RE.match(req.test_run_id):
        raise HTTPException(status_code=400, detail="Invalid test_run_id")
    if not 1 <= len(req.steps) <= 100:
        raise HTTPException(status_code=400, detail="A test run must contain 1 to 100 steps")
    with _test_runs_lock:
        _test_runs[req.test_run_id] = {
            "test_run_id": req.test_run_id, "status": "running", "steps": [], "report": None,
            "screenshot_paths": [], "error": None, "started_at": datetime.now().isoformat(),
        }
        _persist_test_run(req.test_run_id)
    asyncio.create_task(_execute_test_browser_run(req.test_run_id, req.start_url, req.steps))
    return {"test_run_id": req.test_run_id, "status": "running"}


@app.get("/v1/workspace-browser/test-run/{test_run_id}")
async def get_test_browser_run(test_run_id: str, x_bridge_token: str | None = Header(default=None)) -> dict:
    _check_token(x_bridge_token)
    with _test_runs_lock:
        run = _test_runs.get(test_run_id)
    if run is not None:
        return run
    path = _test_run_state_path(test_run_id)
    if path.exists():
        return json.loads(path.read_text())
    raise HTTPException(status_code=404, detail="Test run not found")


class ForgeRouterIntegrationRequest(BaseModel):
    enabled: bool
    api_key: str = ""


@app.put("/v1/tool-integrations/{tool}")
async def set_forgerouter_integration(tool: str, req: ForgeRouterIntegrationRequest, x_bridge_token: str | None = Header(default=None)) -> dict:
    """DEPRECATED — use PUT /v1/project-forgerouter for per-project config.
    This endpoint is kept for backwards compatibility but now rejects requests
    to prevent accidental global ForgeRouter configuration."""
    _check_token(x_bridge_token)
    raise HTTPException(
        status_code=400,
        detail=(
            "Global ForgeRouter configuration is no longer supported. "
            "Use PUT /v1/project-forgerouter with a project_path to configure ForgeRouter "
            "in the scope of a specific project only."
        ),
    )


# ---------------------------------------------------------------------------
# Per-project ForgeRouter configuration
# Config files are written inside the project's working directory, never in
# global user directories (~/.claude, ~/.codex, etc.).
#
# Claude:       {project}/.claude/settings.local.json
#               Claude Code reads .claude/settings.local.json from the working
#               directory hierarchy before falling back to the global one.
#
# Codex:        {project}/.codex/forgerouter.env
#               Codex CLI >= 0.144 silently ignores `model_provider` and
#               `model_providers.*` when they come from a project-local
#               .codex/config.toml -- only `model` is honored from that file
#               (confirmed 2026-07-18: it logs "Ignored unsupported
#               project-local config keys ... model_provider, model_providers"
#               and, since the provider registration never lands, falls back
#               to the default OpenAI provider, which then rejects
#               "forgerouter/auto" as an unknown model under ChatGPT auth).
#               Those two keys only take effect from the user-level
#               ~/.codex/config.toml or from `-c key=value` CLI overrides --
#               writing them to the user-level file would violate the
#               never-global rule above, so every Codex launch instead reads
#               FORGEROUTER_API_KEY from this project-local env sidecar and
#               passes the provider registration as `-c` overrides at
#               invocation time (see FORGEROUTER_CODEX_OVERRIDES below). This
#               file replaces the old (broken) approach of writing
#               model_provider/model_providers into .codex/config.toml.
#
# Antigravity:  {project}/.forgerouter/antigravity.env
#               Antigravity CLI doesn't natively support proxy config; this
#               env file documents the required vars and can be sourced by
#               wrapper scripts. The UI marks this as "env-based".
# ---------------------------------------------------------------------------

FORGEROUTER_OPENAI_BASE_URL = "http://localhost:2100/v1"
FORGEROUTER_OPENAI_MODEL = "forgerouter/auto"
FORGEROUTER_ANTHROPIC_BASE_URL = "http://localhost:2100"
FORGEROUTER_ANTHROPIC_MODEL = "forgerouter/auto"
FORGEROUTER_CLAUDE_KEYS = [
    "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL",
    "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY",
]
# `-c key=value` overrides Codex trusts at invocation time, unlike the
# equivalent keys in a project-local config.toml (see comment above). Kept as
# a single source shared by the interactive terminal launcher and the
# orchestrated `codex exec` path so both register the provider identically.
FORGEROUTER_CODEX_OVERRIDES = [
    'model_provider="forgerouter"',
    'model_providers.forgerouter.name="ForgeRouter"',
    f'model_providers.forgerouter.base_url="{FORGEROUTER_OPENAI_BASE_URL}"',
    'model_providers.forgerouter.env_key="FORGEROUTER_API_KEY"',
    "model_providers.forgerouter.requires_openai_auth=false",
    'model_providers.forgerouter.wire_api="responses"',
    # "forgerouter/auto" isn't a real OpenAI model id, so Codex's built-in
    # model catalog has no context-window/pricing entry for it and warns
    # "Model metadata for `forgerouter/auto` not found" on every launch.
    # Harmless (only affects the TUI's own display), but this silences it.
    "model_context_window=200000",
]


class ProjectForgeRouterRequest(BaseModel):
    project_path: str
    tools: list[str]  # ["claude", "codex", "antigravity"]
    enabled: bool
    api_key: str = ""


def _validate_project_path(project_path: str) -> Path:
    path = Path(project_path)
    if not path.is_absolute():
        raise HTTPException(status_code=400, detail=f"project_path must be absolute: {project_path}")
    if not path.exists():
        raise HTTPException(status_code=400, detail=f"project_path does not exist: {project_path}")
    return path


class AgentRunRequest(BaseModel):
    run_id: str
    runtime_type: str  # claude | codex | agy (antigravity accepted as legacy alias) | hermes
    project_path: str
    prompt: str
    model_ref: str = "forgerouter/auto"
    routing_group: str = "auto"
    api_key: str = ""
    mode: str = "execute"  # plan | execute
    max_seconds: int = 1800
    # Required when runtime_type == "hermes": which /root/.hermes/profiles/<slug>
    # to run as (Athos, Aegis, ...). Ignored for every other runtime_type.
    hermes_profile: str | None = None
    max_budget_usd: float | None = None
    work_package_hash: str | None = None


def _antigravity_env(project_dir: Path) -> dict[str, str]:
    """Read the project-scoped ForgeRouter env without invoking a shell."""
    env = os.environ.copy()
    env_file = project_dir / ".forgerouter" / "antigravity.env"
    if not env_file.exists():
        return env
    for raw_line in env_file.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:]
        if "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        if re.fullmatch(r"[A-Z_][A-Z0-9_]*", key):
            values = shlex.split(raw_value)
            env[key] = values[0] if values else ""
    return env


def _agent_run_command(req: AgentRunRequest, project_dir: Path) -> tuple[list[str], dict[str, str]]:
    if req.mode not in {"plan", "execute"}:
        raise HTTPException(status_code=400, detail="mode must be plan or execute")
    if req.runtime_type not in {"claude", "codex", "agy", "antigravity", "hermes", "openclaw"}:
        raise HTTPException(status_code=400, detail="unsupported runtime_type")
    if not 30 <= req.max_seconds <= 7200:
        raise HTTPException(status_code=400, detail="max_seconds must be between 30 and 7200")
    if len(req.prompt) > 100_000:
        raise HTTPException(status_code=400, detail="prompt is too large")

    if req.runtime_type == "hermes":
        # Classic Hermes-profile agents (Athos, Aegis, ...) already have
        # their own model/provider configured per-profile (config.yaml) --
        # unlike claude/codex/agy they don't take a ForgeRouter credential
        # from this request, so model_args/agent_env below don't apply.
        # This is a one-shot CLI invocation scoped to the profile's own
        # HERMES_HOME; it runs alongside that profile's persistent
        # `gateway run` daemon (same HERMES_HOME/state.db, SQLite WAL mode
        # -- verified concurrent-safe 2026-07-25), not a replacement for it.
        if not req.hermes_profile:
            raise HTTPException(status_code=400, detail="hermes_profile is required for hermes runtime_type")
        profile_home = Path("/root/.hermes/profiles") / req.hermes_profile
        if not profile_home.is_dir():
            raise HTTPException(status_code=400, detail=f"unknown hermes profile: {req.hermes_profile}")
        hermes_env = os.environ.copy()
        hermes_env["HERMES_HOME"] = str(profile_home)
        return (
            [
                "/usr/local/bin/hermes",
                "chat",
                "-q",
                req.prompt,
                "-Q",
                "--yolo",
            ],
            hermes_env,
        )

    if req.runtime_type == "openclaw":
        # Vector (Marcelo's personal OpenClaw assistant) already runs as a
        # persistent daemon (openclaw-gateway.service) with its own
        # ForgeRouter credential wired into openclaw.json
        # (models.providers.forgerouter) -- same "agent already has its own
        # credential" pattern as "hermes" above, no req.api_key needed. The
        # only configured agent id on this host is "main" (identity: Vector
        # -- confirmed via `openclaw agents list` 2026-07-25).
        return (
            [
                "/root/.npm-global/bin/openclaw",
                "agent",
                "--agent",
                "main",
                "--message",
                req.prompt,
                "--json",
            ],
            os.environ.copy(),
        )

    routing_groups = {"auto", "simple", "standard", "complex", "reasoning", "vision", "audio", "code"}
    if req.routing_group not in routing_groups:
        raise HTTPException(status_code=400, detail="unsupported ForgeRouter routing_group")
    # req.api_key is only set when the Agent row in ForgeHub has a
    # ForgeRouter credential configured. Porthus/Aramis/Dartan each have
    # their own native CLI auth already logged in on this host (Claude
    # Code subscription, Codex's own auth.json, Antigravity's own OAuth
    # token under ~/.gemini/antigravity-cli/) -- with no ForgeRouter key
    # on file, dispatch falls back to that native auth instead of forcing
    # ForgeRouter with an empty/invalid key (which would 401). Same
    # "agent already has its own credential" pattern as runtime_type ==
    # "hermes" above.
    use_forgerouter = bool(req.api_key)
    effective_model = (
        f"forgerouter/{req.routing_group}"
        if req.model_ref == "forgerouter/auto"
        else req.model_ref
    )
    model_args = ["--model", effective_model] if use_forgerouter else []
    agent_env = os.environ.copy()
    if use_forgerouter:
        agent_env.update({
            "FORGEROUTER_API_KEY": req.api_key,
            "FORGEROUTER_MODEL": effective_model,
            "OPENAI_API_KEY": req.api_key,
            "ANTHROPIC_AUTH_TOKEN": req.api_key,
            "ANTHROPIC_API_KEY": req.api_key,
        })
    if req.runtime_type == "claude":
        if use_forgerouter:
            # Without this, ANTHROPIC_API_KEY above still points `claude` at
            # the real Anthropic API with a ForgeRouter-issued key -> 401
            # Invalid API key. Same fix
            # /root/.claude/scripts/claude_fallback.sh already applies, and
            # the same constant _configure_claude_forgerouter already uses
            # for the project-settings.json flow -- just never wired into
            # this ad hoc agent-runs dispatch path before now.
            agent_env = {**agent_env, "ANTHROPIC_BASE_URL": FORGEROUTER_ANTHROPIC_BASE_URL}
        command = [
            "/root/.local/bin/claude",
            "--print",
            "--output-format",
            "json",
            "--permission-mode",
            "plan" if req.mode == "plan" else "acceptEdits",
            "--no-session-persistence",
            *model_args,
        ]
        if req.max_budget_usd is not None:
            command.extend(["--max-budget-usd", str(req.max_budget_usd)])
        command.append(req.prompt)
        return command, agent_env

    if req.runtime_type == "codex":
        codex_overrides: list[str] = []
        if use_forgerouter and effective_model.startswith("forgerouter/"):
            # -c overrides, not the project's .codex/config.toml: Codex
            # ignores model_provider/model_providers from project-local
            # files (see FORGEROUTER_CODEX_OVERRIDES comment above). Skipped
            # entirely when running on Codex's own native auth.json login
            # (use_forgerouter False) -- those overrides would otherwise
            # force Codex's provider back to ForgeRouter.
            for override in FORGEROUTER_CODEX_OVERRIDES:
                codex_overrides += ["-c", override]
        return (
            [
                "/root/.npm-global/bin/codex",
                "exec",
                "--json",
                "--sandbox",
                "read-only" if req.mode == "plan" else "workspace-write",
                "-C",
                str(project_dir),
                *codex_overrides,
                *model_args,
                req.prompt,
            ],
            agent_env,
        )

    return (
        [
            "/root/.local/bin/agy",
            "--print",
            req.prompt,
            "--mode",
            "plan" if req.mode == "plan" else "accept-edits",
            "--sandbox",
            "--print-timeout",
            f"{req.max_seconds}s",

        ],
        {**_antigravity_env(project_dir), **agent_env} if use_forgerouter else agent_env,
    )


def _monitor_agent_run(run_id: str, proc: subprocess.Popen, max_seconds: int) -> None:
    try:
        stdout, stderr = proc.communicate(timeout=max_seconds)
        state = "completed" if proc.returncode == 0 else "failed"
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGTERM)
        try:
            stdout, stderr = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate()
        state = "timed_out"
    except Exception as exc:
        stdout, stderr, state = "", str(exc), "failed"

    with _agent_runs_lock:
        run = _agent_runs.get(run_id)
        if run is None:
            return
        run.update(
            {
                "status": state,
                "exit_code": proc.returncode,
                "output": _redact_run_output((stdout or "")[-200_000:]),
                "error": _redact_run_output((stderr or "")[-200_000:]),
                "finished_at": datetime.now().isoformat(),
                "heartbeat_at": datetime.now().isoformat(),
            }
        )
        run.pop("process", None)
        _persist_agent_run(run_id)


@app.post("/v1/agent-runs", status_code=202)
async def start_agent_run(
    req: AgentRunRequest, x_bridge_token: str | None = Header(default=None)
) -> dict:
    """Start one governed CLI run without accepting an arbitrary shell command."""
    _check_token(x_bridge_token)
    try:
        uuid.UUID(req.run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="run_id must be a UUID") from exc
    project_dir = _validate_project_path(req.project_path)
    command, env = _agent_run_command(req, project_dir)

    with _agent_runs_lock:
        if req.run_id in _agent_runs:
            raise HTTPException(status_code=409, detail="run_id already exists")
        _agent_runs[req.run_id] = {
            "run_id": req.run_id,
            "runtime_type": "agy" if req.runtime_type == "antigravity" else req.runtime_type,
            "model_ref": req.model_ref,
            "mode": req.mode,
            "project_path": str(project_dir),
            "status": "starting",
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
            "exit_code": None,
            "output": "",
            "error": "",
            "adapter_version": AGENT_RUN_ADAPTER_VERSION,
            "work_package_hash": req.work_package_hash,
            "heartbeat_at": datetime.now().isoformat(),
        }
        _persist_agent_run(req.run_id)

    try:
        proc = subprocess.Popen(
            command,
            cwd=project_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
    except (FileNotFoundError, OSError) as exc:
        with _agent_runs_lock:
            _agent_runs.pop(req.run_id, None)
        raise HTTPException(status_code=500, detail=f"failed to start {req.runtime_type}: {exc}") from exc

    with _agent_runs_lock:
        _agent_runs[req.run_id]["status"] = "running"
        _agent_runs[req.run_id]["process"] = proc
        _agent_runs[req.run_id]["pid"] = proc.pid
        _agent_runs[req.run_id]["heartbeat_at"] = datetime.now().isoformat()
        _persist_agent_run(req.run_id)
    threading.Thread(
        target=_monitor_agent_run,
        args=(req.run_id, proc, req.max_seconds),
        daemon=True,
    ).start()
    return {"run_id": req.run_id, "status": "running", "runtime_type": "agy" if req.runtime_type == "antigravity" else req.runtime_type, "pid": proc.pid, "adapter_version": AGENT_RUN_ADAPTER_VERSION}


@app.get("/v1/agent-runs/health")
async def agent_runner_health(x_bridge_token: str | None = Header(default=None)) -> dict:
    _check_token(x_bridge_token)
    adapters = {
        "claude": {"available": Path("/root/.local/bin/claude").exists()},
        "codex": {"available": Path("/root/.npm-global/bin/codex").exists()},
        "agy": {"available": Path("/root/.local/bin/agy").exists()},
        "hermes": {"available": Path("/usr/local/bin/hermes").exists()},
        "openclaw": {"available": Path("/root/.npm-global/bin/openclaw").exists()},
    }
    return {
        "status": "ok" if any(item["available"] for item in adapters.values()) else "degraded",
        "adapter_version": AGENT_RUN_ADAPTER_VERSION,
        "capabilities": {"adapters": adapters, "persistence": True, "cancel": True, "reconcile": True},
    }


@app.get("/v1/agent-runs/{run_id}")
async def get_agent_run(
    run_id: str, x_bridge_token: str | None = Header(default=None)
) -> dict:
    _check_token(x_bridge_token)
    with _agent_runs_lock:
        run = _agent_runs.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="agent run not found")
        if run.get("status") == "running" and not _pid_alive(run.get("pid")):
            run["status"] = "stale"
            run["error"] = "Recorded process is no longer alive"
            run["finished_at"] = datetime.now().isoformat()
        run["heartbeat_at"] = datetime.now().isoformat()
        _persist_agent_run(run_id)
        return {key: value for key, value in run.items() if key != "process"}


@app.post("/v1/agent-runs/{run_id}/cancel")
async def cancel_agent_run(
    run_id: str, x_bridge_token: str | None = Header(default=None)
) -> dict:
    _check_token(x_bridge_token)
    with _agent_runs_lock:
        run = _agent_runs.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="agent run not found")
        proc = run.get("process")
        pid = proc.pid if proc is not None else run.get("pid")
        if not pid or run["status"] != "running":
            return {"run_id": run_id, "status": run["status"]}
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pid, signal.SIGTERM)
        run["status"] = "cancelled"
        run["finished_at"] = datetime.now().isoformat()
        run["heartbeat_at"] = datetime.now().isoformat()
        run.pop("process", None)
        _persist_agent_run(run_id)
    return {"run_id": run_id, "status": "cancelled"}


def _configure_claude_forgerouter(project_dir: Path, enabled: bool, api_key: str) -> str:
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    settings_path = claude_dir / "settings.local.json"

    # Backup before any write
    if settings_path.exists():
        backup = claude_dir / "settings.local.json.forgerouter.bak"
        backup.write_text(settings_path.read_text())

    try:
        current = json.loads(settings_path.read_text()) if settings_path.exists() else {}
    except json.JSONDecodeError:
        current = {}

    env = current.setdefault("env", {})
    if enabled:
        current["model"] = FORGEROUTER_ANTHROPIC_MODEL
        env.update({
            "ANTHROPIC_BASE_URL": FORGEROUTER_ANTHROPIC_BASE_URL,
            "ANTHROPIC_AUTH_TOKEN": api_key,
            "ANTHROPIC_MODEL": FORGEROUTER_ANTHROPIC_MODEL,
            "ANTHROPIC_DEFAULT_OPUS_MODEL": FORGEROUTER_ANTHROPIC_MODEL,
            "ANTHROPIC_DEFAULT_SONNET_MODEL": FORGEROUTER_ANTHROPIC_MODEL,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": FORGEROUTER_ANTHROPIC_MODEL,
            "CLAUDE_CODE_SUBAGENT_MODEL": FORGEROUTER_ANTHROPIC_MODEL,
            "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY": "1",
        })
    else:
        for key in FORGEROUTER_CLAUDE_KEYS:
            env.pop(key, None)
        if not env:
            current.pop("env", None)
        if current.get("model") == FORGEROUTER_ANTHROPIC_MODEL:
            current.pop("model", None)

    settings_path.write_text(json.dumps(current, indent=2) + "\n")
    os.chmod(settings_path, 0o600)
    return str(settings_path)


def _configure_codex_forgerouter(project_dir: Path, enabled: bool, api_key: str) -> str:
    codex_dir = project_dir / ".codex"
    codex_dir.mkdir(parents=True, exist_ok=True)
    env_path = codex_dir / "forgerouter.env"

    # Self-heal projects set up by the earlier (broken) approach: Codex
    # ignores model_provider/model_providers from this file (see
    # FORGEROUTER_CODEX_OVERRIDES comment above), so a config.toml we wrote
    # only produces a misleading "model: forgerouter/auto" banner with no
    # working provider behind it. Restore whatever it backed up, or remove
    # it if we created it from nothing.
    legacy_config_path = codex_dir / "config.toml"
    legacy_backup = codex_dir / "config.toml.forgerouter.bak"
    if legacy_config_path.exists() and 'model_provider = "forgerouter"' in legacy_config_path.read_text():
        if legacy_backup.exists():
            legacy_config_path.write_text(legacy_backup.read_text())
            legacy_backup.unlink()
        else:
            legacy_config_path.unlink()

    if enabled:
        env_path.write_text(f"FORGEROUTER_API_KEY={api_key}\n")
        os.chmod(env_path, 0o600)
    else:
        env_path.unlink(missing_ok=True)

    return str(env_path)


def _configure_antigravity_forgerouter(project_dir: Path, enabled: bool, api_key: str) -> str:
    fr_dir = project_dir / ".forgerouter"
    fr_dir.mkdir(parents=True, exist_ok=True)
    env_path = fr_dir / "antigravity.env"

    if enabled:
        env_path.write_text(
            "# ForgeRouter configuration for Antigravity CLI\n"
            "# Source this file before running agy in this project:\n"
            "#   source .forgerouter/antigravity.env\n"
            "#\n"
            "# NOTE: Antigravity CLI does not natively support proxy configuration.\n"
            "# These variables are provided for custom wrapper scripts.\n"
            f'export FORGEROUTER_BASE_URL="{FORGEROUTER_OPENAI_BASE_URL}"\n'
            f'export FORGEROUTER_API_KEY="{api_key}"\n'
            f'export FORGEROUTER_MODEL="{FORGEROUTER_OPENAI_MODEL}"\n'
        )
        os.chmod(env_path, 0o600)
    else:
        env_path.unlink(missing_ok=True)

    return str(env_path)


@app.put("/v1/project-forgerouter")
async def set_project_forgerouter(
    req: ProjectForgeRouterRequest,
    x_bridge_token: str | None = Header(default=None),
) -> dict:
    """Configure ForgeRouter for the specified tools inside a project directory.

    Config files are written inside project_path, never in global user dirs.
    When enabled=False, config files are removed (or restored from backup).
    """
    _check_token(x_bridge_token)
    project_dir = _validate_project_path(req.project_path)

    results: dict[str, dict] = {}
    for tool in req.tools:
        if tool == "claude":
            config_path = _configure_claude_forgerouter(project_dir, req.enabled, req.api_key)
            results["claude"] = {"enabled": req.enabled, "config_path": config_path}
        elif tool == "codex":
            config_path = _configure_codex_forgerouter(project_dir, req.enabled, req.api_key)
            results["codex"] = {"enabled": req.enabled, "config_path": config_path}
        elif tool == "antigravity":
            config_path = _configure_antigravity_forgerouter(project_dir, req.enabled, req.api_key)
            results["antigravity"] = {"enabled": req.enabled, "config_path": config_path, "note": "env-based, requires shell sourcing"}
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported tool: {tool}")

    return {"project_path": req.project_path, "tools": results}


@app.get("/v1/project-forgerouter/status")
async def get_project_forgerouter_status(
    project_path: str,
    x_bridge_token: str | None = Header(default=None),
) -> dict:
    """Return the live filesystem status of ForgeRouter config files for a project."""
    _check_token(x_bridge_token)
    project_dir = _validate_project_path(project_path)

    claude_path = project_dir / ".claude" / "settings.local.json"
    claude_enabled = False
    if claude_path.exists():
        try:
            s = json.loads(claude_path.read_text())
            env = s.get("env", {})
            base_url = env.get("ANTHROPIC_BASE_URL", "")
            claude_enabled = bool(base_url and ("localhost:2100" in base_url or "forgerouter" in base_url.lower()))
        except (OSError, json.JSONDecodeError):
            pass

    codex_path = project_dir / ".codex" / "forgerouter.env"
    codex_enabled = codex_path.exists()

    agy_path = project_dir / ".forgerouter" / "antigravity.env"
    agy_enabled = agy_path.exists()

    return {
        "project_path": project_path,
        "claude": claude_enabled,
        "codex": codex_enabled,
        "antigravity": agy_enabled,
        "claude_config_path": str(claude_path),
        "codex_config_path": str(codex_path),
        "antigravity_env_path": str(agy_path),
    }


# ---------------------------------------------------------------------------
# Global CLI ForgeRouter configuration (User Home ~/.claude, ~/.codex, ~/.forgerouter)
# ---------------------------------------------------------------------------

class CliToggleRequest(BaseModel):
    tool: str
    enabled: bool


def _configure_global_claude_forgerouter(enabled: bool) -> str:
    claude_dir = Path.home() / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    settings_path = claude_dir / "settings.json"
    if not settings_path.exists() and (claude_dir / "settings.local.json").exists():
        target_path = claude_dir / "settings.local.json"
    else:
        target_path = settings_path

    if target_path.exists():
        backup_path = target_path.with_suffix(target_path.suffix + ".forgerouter.bak")
        backup_path.write_text(target_path.read_text())

    try:
        current = json.loads(target_path.read_text()) if target_path.exists() else {}
    except (OSError, json.JSONDecodeError):
        current = {}

    env = current.setdefault("env", {})
    if enabled:
        env["ANTHROPIC_BASE_URL"] = FORGEROUTER_ANTHROPIC_BASE_URL
        current["model"] = FORGEROUTER_ANTHROPIC_MODEL
    else:
        env.pop("ANTHROPIC_BASE_URL", None)
        if not env:
            current.pop("env", None)
        if current.get("model") == FORGEROUTER_ANTHROPIC_MODEL:
            current.pop("model", None)

    target_path.write_text(json.dumps(current, indent=2) + "\n")
    os.chmod(target_path, 0o600)
    return str(target_path)


def _configure_global_codex_forgerouter(enabled: bool) -> str:
    codex_dir = Path.home() / ".codex"
    codex_dir.mkdir(parents=True, exist_ok=True)
    config_path = codex_dir / "config.toml"

    if config_path.exists():
        backup_path = codex_dir / "config.toml.forgerouter.bak"
        backup_path.write_text(config_path.read_text())
        content = config_path.read_text()
    else:
        content = ""

    lines = content.splitlines(keepends=True)
    out_lines = []
    i = 0
    in_fr_table = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("[model_providers.forgerouter"):
            in_fr_table = True
            i += 1
            continue

        if in_fr_table:
            if stripped.startswith("["):
                in_fr_table = False
            else:
                i += 1
                continue

        if (stripped.startswith("model_provider =") or stripped.startswith("model_provider=")) and "forgerouter" in stripped:
            i += 1
            continue

        out_lines.append(line)
        i += 1

    cleaned = "".join(out_lines)

    if enabled:
        cleaned_lines = cleaned.splitlines(keepends=True)
        first_table_idx = len(cleaned_lines)
        for idx, l in enumerate(cleaned_lines):
            if l.strip().startswith("["):
                first_table_idx = idx
                break

        top_lines = cleaned_lines[:first_table_idx]
        table_lines = cleaned_lines[first_table_idx:]

        top_lines.insert(0, 'model_provider = "forgerouter"\n')

        fr_table = (
            "[model_providers.forgerouter]\n"
            'name = "ForgeRouter"\n'
            f'base_url = "{FORGEROUTER_OPENAI_BASE_URL}"\n'
            'env_key = "FORGEROUTER_API_KEY"\n'
            "requires_openai_auth = false\n"
            'wire_api = "responses"\n'
        )

        top_part = "".join(top_lines).rstrip("\n")
        table_part = "".join(table_lines).lstrip("\n")

        if table_part:
            final_content = f"{top_part}\n\n{fr_table}\n{table_part}"
        else:
            final_content = f"{top_part}\n\n{fr_table}"
    else:
        final_content = cleaned

    config_path.write_text(final_content)
    os.chmod(config_path, 0o600)
    return str(config_path)


def _configure_global_antigravity_forgerouter(enabled: bool) -> str:
    fr_dir = Path.home() / ".forgerouter"
    fr_dir.mkdir(parents=True, exist_ok=True)
    env_path = fr_dir / "antigravity.env"

    if env_path.exists():
        backup_path = fr_dir / "antigravity.env.forgerouter.bak"
        backup_path.write_text(env_path.read_text())

    if enabled:
        env_path.write_text(
            "# ForgeRouter configuration for Antigravity CLI\n"
            "# Source this file before running agy:\n"
            "#   source ~/.forgerouter/antigravity.env\n"
            "#\n"
            f'export FORGEROUTER_BASE_URL="{FORGEROUTER_OPENAI_BASE_URL}"\n'
            f'export FORGEROUTER_MODEL="{FORGEROUTER_OPENAI_MODEL}"\n'
        )
        os.chmod(env_path, 0o600)
    else:
        env_path.unlink(missing_ok=True)

    return str(env_path)


@app.get("/v1/forgerouter/cli-status")
async def get_forgerouter_cli_status(
    x_bridge_token: str | None = Header(default=None),
) -> dict:
    """Return the live global CLI ForgeRouter status across Claude, Codex, and Antigravity."""
    _check_token(x_bridge_token)

    # Claude check: looks at ~/.claude/settings.json or ~/.claude/settings.local.json
    claude_enabled = False
    claude_paths = [Path.home() / ".claude" / "settings.json", Path.home() / ".claude" / "settings.local.json"]
    for cp in claude_paths:
        if cp.exists():
            try:
                s = json.loads(cp.read_text())
                env = s.get("env", {})
                base_url = env.get("ANTHROPIC_BASE_URL", "")
                if base_url and ("2100" in base_url or "forgerouter" in base_url.lower()):
                    claude_enabled = True
                    break
            except (OSError, json.JSONDecodeError):
                pass

    # Codex check: looks at ~/.codex/config.toml for model_provider = "forgerouter"
    codex_enabled = False
    codex_cfg = Path.home() / ".codex" / "config.toml"
    if codex_cfg.exists():
        try:
            content = codex_cfg.read_text()
            if 'model_provider = "forgerouter"' in content or 'model_provider="forgerouter"' in content:
                codex_enabled = True
        except OSError:
            pass

    # Antigravity check: looks at ~/.forgerouter/antigravity.env for FORGEROUTER_BASE_URL
    agy_enabled = False
    agy_path = Path.home() / ".forgerouter" / "antigravity.env"
    if agy_path.exists():
        try:
            content = agy_path.read_text()
            if "FORGEROUTER_BASE_URL" in content:
                agy_enabled = True
        except OSError:
            pass

    return {
        "claude": claude_enabled,
        "codex": codex_enabled,
        "antigravity": agy_enabled,
    }


@app.put("/v1/forgerouter/cli-toggle")
async def set_forgerouter_cli_toggle(
    req: CliToggleRequest,
    x_bridge_token: str | None = Header(default=None),
) -> dict:
    """Set or remove global ForgeRouter configuration for a CLI tool."""
    _check_token(x_bridge_token)
    tool = req.tool.lower()

    if tool == "claude":
        config_path = _configure_global_claude_forgerouter(req.enabled)
    elif tool == "codex":
        config_path = _configure_global_codex_forgerouter(req.enabled)
    elif tool == "antigravity":
        config_path = _configure_global_antigravity_forgerouter(req.enabled)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported tool: {req.tool}")

    status = await get_forgerouter_cli_status(x_bridge_token=x_bridge_token)
    return {
        "tool": tool,
        "enabled": req.enabled,
        "config_path": config_path,
        "status": status,
    }


# ---------------------------------------------------------------------------
# Project-scoped MCP servers -- Claude Code's `.mcp.json` at the project
# root, ForgeHub's counterpart to per-agent MCP (agent_mcp.py, a different
# Python process/venv entirely -- this file can't import from it, so the
# JSON entry upsert is reimplemented here, minimal since .mcp.json is plain
# JSON with no comments to preserve, unlike Hermes YAML/Codex TOML). Only
# "claude" is supported today -- confirmed 2026-07-28 that Codex/Hermes/agy/
# OpenClaw have no equivalent project-local MCP mechanism; extend
# PROJECT_MCP_SUPPORTED_RUNTIMES only after confirming a runtime's own CLI
# genuinely reads one, never from documentation alone.
# ---------------------------------------------------------------------------

PROJECT_MCP_SUPPORTED_RUNTIMES = {"claude"}
# Mirrors app/core/mcp_config_io.py's SERVER_NAME_RE -- a server name lands
# inside a JSON object key, kept to characters that can't change the file's
# meaning. Duplicated (not imported) for the same cross-process reason as
# the rest of this section.
_MCP_SERVER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class ProjectMcpServerRequest(BaseModel):
    project_path: str
    runtime_type: str
    name: str
    transport: str = "stdio"
    command: str | None = None
    args: list[str] = []
    env: dict[str, str] = {}
    url: str | None = None
    enabled: bool = True


def _project_mcp_config_path(project_dir: Path, runtime_type: str) -> Path:
    # Only "claude" today -- see PROJECT_MCP_SUPPORTED_RUNTIMES above.
    return project_dir / ".mcp.json"


@app.put("/v1/project-mcp-servers")
async def set_project_mcp_server(
    req: ProjectMcpServerRequest,
    x_bridge_token: str | None = Header(default=None),
) -> dict:
    """Upsert one MCP server entry in a project's `.mcp.json`
    (`mcpServers[name]`) -- the project-scoped counterpart of
    PUT /agents/{id}/mcp-servers/{name}, written here (not the backend
    container) for the same reason every other project-file route in
    project.py proxies through this bridge: an arbitrary project
    working_directory_path isn't guaranteed reachable from the backend
    container."""
    _check_token(x_bridge_token)
    if req.runtime_type not in PROJECT_MCP_SUPPORTED_RUNTIMES:
        raise HTTPException(
            status_code=400,
            detail=f"runtime_type {req.runtime_type!r} has no project-scoped MCP mechanism.",
        )
    if not _MCP_SERVER_NAME_RE.match(req.name):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid MCP server name {req.name!r}: use letters, digits, '.', '_' or '-' (max 64 chars).",
        )
    if bool(req.command) == bool(req.url):
        raise HTTPException(status_code=400, detail="Provide either command or url, not both.")

    project_dir = _validate_project_path(req.project_path)
    config_path = _project_mcp_config_path(project_dir, req.runtime_type)

    try:
        document = json.loads(config_path.read_text()) if config_path.exists() else {}
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"{config_path} is not valid JSON: {exc}") from exc

    servers = document.setdefault("mcpServers", {})
    entry: dict = {}
    if req.url:
        entry["url"] = req.url
    else:
        entry["command"] = req.command
        entry["args"] = list(req.args)
    if req.env:
        entry["env"] = dict(req.env)
    if not req.enabled:
        # Claude Code's .mcp.json has no enable/disable field -- "off" is
        # removal only, same as the per-agent format (agent_mcp.py's
        # FORMATS["claude"] has no toggle_field either). The route layer
        # (backend/app/api/routes/project.py) rejects this before it ever
        # reaches here; this is a defense-in-depth 400, not the primary gate.
        raise HTTPException(
            status_code=400,
            detail="Claude Code's .mcp.json has no enable/disable flag -- remove the server instead.",
        )
    existing = servers.get(req.name) if isinstance(servers.get(req.name), dict) else {}
    merged = {**{k: v for k, v in existing.items() if k in {"type", "transport"}}, **entry}
    if "type" not in merged and not entry.get("url"):
        merged = {"type": "stdio", **merged}
    servers[req.name] = merged

    config_path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n")
    os.chmod(config_path, 0o600)
    return {"project_path": req.project_path, "config_path": str(config_path), "name": req.name}


@app.delete("/v1/project-mcp-servers")
async def delete_project_mcp_server(
    project_path: str,
    runtime_type: str,
    name: str,
    x_bridge_token: str | None = Header(default=None),
) -> dict:
    """Remove one MCP server entry from a project's `.mcp.json`."""
    _check_token(x_bridge_token)
    if runtime_type not in PROJECT_MCP_SUPPORTED_RUNTIMES:
        raise HTTPException(
            status_code=400,
            detail=f"runtime_type {runtime_type!r} has no project-scoped MCP mechanism.",
        )
    project_dir = _validate_project_path(project_path)
    config_path = _project_mcp_config_path(project_dir, runtime_type)
    if not config_path.exists():
        return {"project_path": project_path, "config_path": str(config_path), "removed": False}

    try:
        document = json.loads(config_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"{config_path} is not valid JSON: {exc}") from exc
    servers = document.get("mcpServers")
    removed = isinstance(servers, dict) and servers.pop(name, None) is not None
    if removed:
        config_path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n")
    return {"project_path": project_path, "config_path": str(config_path), "removed": removed}


@app.get("/v1/project-mcp-servers/status")
async def get_project_mcp_servers_status(
    project_path: str,
    runtime_type: str,
    x_bridge_token: str | None = Header(default=None),
) -> dict:
    """Live filesystem read of a project's `.mcp.json` -- the disk-truth
    counterpart of the DB-stored ProjectMcpServer rows, same role as
    GET /project-forgerouter/status above."""
    _check_token(x_bridge_token)
    if runtime_type not in PROJECT_MCP_SUPPORTED_RUNTIMES:
        raise HTTPException(
            status_code=400,
            detail=f"runtime_type {runtime_type!r} has no project-scoped MCP mechanism.",
        )
    project_dir = _validate_project_path(project_path)
    config_path = _project_mcp_config_path(project_dir, runtime_type)
    if not config_path.exists():
        return {"project_path": project_path, "config_path": str(config_path), "config_exists": False, "servers": []}

    try:
        document = json.loads(config_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"{config_path} is not valid JSON: {exc}") from exc
    servers_raw = document.get("mcpServers") or {}
    servers = [
        {
            "name": name,
            "command": entry.get("command"),
            "args": entry.get("args") or [],
            "env": entry.get("env") or {},
            "url": entry.get("url"),
        }
        for name, entry in servers_raw.items()
        if isinstance(entry, dict)
    ]
    return {
        "project_path": project_path,
        "config_path": str(config_path),
        "config_exists": True,
        "servers": servers,
    }


@app.get("/v1/forgerouter/global-audit")
async def audit_global_forgerouter(
    x_bridge_token: str | None = Header(default=None),
) -> dict:
    """Scan for global ForgeRouter configurations that should be per-project."""
    _check_token(x_bridge_token)
    findings = []

    # Check global Claude settings
    global_claude = Path.home() / ".claude" / "settings.local.json"
    if global_claude.exists():
        try:
            s = json.loads(global_claude.read_text())
            env = s.get("env", {})
            base_url = env.get("ANTHROPIC_BASE_URL", "")
            if base_url and ("localhost:2100" in base_url or "forgerouter" in base_url.lower()):
                findings.append({
                    "tool": "claude",
                    "type": "global",
                    "path": str(global_claude),
                    "detail": f"ANTHROPIC_BASE_URL={base_url}",
                })
        except (OSError, json.JSONDecodeError):
            pass

    # Check global Codex forgerouter config (old format: forgerouter.config.toml)
    global_codex_fr = Path.home() / ".codex" / "forgerouter.config.toml"
    if global_codex_fr.exists():
        findings.append({
            "tool": "codex",
            "type": "global",
            "path": str(global_codex_fr),
            "detail": "Legacy global forgerouter.config.toml detected",
        })

    # Check global Codex config.toml for forgerouter model provider
    # Check global Codex config.toml for actual ForgeRouter model routing
    # (trust_level entries for paths containing "forgerouter" are not routing config)
    global_codex_cfg = Path.home() / ".codex" / "config.toml"
    if global_codex_cfg.exists():
        try:
            content = global_codex_cfg.read_text()
            if 'model_provider = "forgerouter"' in content or 'model_provider="forgerouter"' in content:
                findings.append({
                    "tool": "codex",
                    "type": "global",
                    "path": str(global_codex_cfg),
                    "detail": "Global config.toml sets model_provider = forgerouter",
                })
        except OSError:
            pass

    return {"clean": len(findings) == 0, "findings": findings}


class ChatRequest(BaseModel):
    profile: str
    message: str
    session_id: str | None = None
    image_paths: list[str] | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str | None = None


def _run_hermes_chat(
    req: ChatRequest, *, autonomous_remediation: bool = False
) -> ChatResponse:
    if not _is_valid_profile(req.profile):
        raise HTTPException(status_code=400, detail=f"Unknown or disallowed profile: {req.profile}")

    args = [
        HERMES_PYTHON,
        "-m",
        "hermes_cli.main",
        "-p",
        req.profile,
        "chat",
        "-q",
        req.message,
        "-Q",
        "--source",
        "tool",
    ]
    if req.session_id:
        args += ["--resume", req.session_id]
    if autonomous_remediation:
        # This mode is exposed only by the dedicated, token-protected Auditor
        # route below. The administrator has already confirmed the action in
        # ForgeHub; checkpoints keep file mutations recoverable.
        args += ["--yolo", "--checkpoints"]
    for image_path in req.image_paths or []:
        args += ["--image", image_path]

    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=CHAT_TIMEOUT_SECONDS,
            cwd=str(Path.home()),
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Agent did not respond in time") from None

    if proc.returncode != 0:
        raise HTTPException(
            status_code=502,
            detail=f"hermes chat exited {proc.returncode}: {proc.stderr.strip()[-2000:]}",
        )

    reply_lines = [
        line for line in proc.stdout.splitlines() if not line.startswith("Warning:")
    ]
    reply = "\n".join(reply_lines).strip()

    session_match = SESSION_ID_RE.search(proc.stderr)
    session_id = session_match.group(1) if session_match else req.session_id

    return ChatResponse(reply=reply, session_id=session_id)


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, x_bridge_token: str | None = Header(default=None)) -> ChatResponse:
    _check_token(x_bridge_token)
    return _run_hermes_chat(req)


@app.post("/v1/audit/remediate", response_model=ChatResponse)
async def audit_remediate(
    req: ChatRequest, x_bridge_token: str | None = Header(default=None)
) -> ChatResponse:
    """Run an administrator-confirmed ecosystem correction through Athos."""
    _check_token(x_bridge_token)
    if req.profile != "athos":
        raise HTTPException(status_code=400, detail="Audit remediation must use the athos profile")
    return _run_hermes_chat(req, autonomous_remediation=True)


class MessageSendRequest(BaseModel):
    # "telegram" (home channel) or "telegram:<chat_id>" -- same format
    # send_message_tool itself takes.
    target: str
    message: str
    # Which agent's bot sends it (profile_slug, e.g. "athos"). Every agent
    # has its own Telegram bot with its own token, so answering a request
    # that arrived through one agent means sending through that agent's bot
    # -- otherwise the reply arrives from the wrong sender (2026-08-13).
    # Omitted, the global install's bot is used, exactly as before.
    profile: str | None = None


@app.get("/v1/telegram/{profile}/messages")
async def telegram_messages(
    profile: str,
    limit: int = Query(default=100, ge=1, le=500),
    x_bridge_token: str | None = Header(default=None),
) -> dict:
    """Read the visible transcript of a profile's latest Telegram chat.

    Hermes' own state database remains authoritative. Only active user and
    assistant text is exposed; tool calls, reasoning and configuration never
    cross this boundary.
    """
    _check_token(x_bridge_token)
    if not _is_valid_profile(profile):
        raise HTTPException(status_code=404, detail=f"No Hermes profile named {profile!r}")
    state_db = PROFILES_DIR / profile / "state.db"
    if not state_db.is_file():
        return {"profile": profile, "session_id": None, "chat_id": None, "messages": []}

    try:
        with sqlite3.connect(f"file:{state_db}?mode=ro", uri=True, timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            session = conn.execute(
                """
                SELECT id, chat_id
                FROM sessions
                WHERE source = 'telegram' AND chat_id IS NOT NULL
                ORDER BY COALESCE(last_activity_at, started_at) DESC
                LIMIT 1
                """
            ).fetchone()
            if session is None:
                return {"profile": profile, "session_id": None, "chat_id": None, "messages": []}
            rows = conn.execute(
                """
                SELECT id, role, content, timestamp, platform_message_id
                FROM messages
                WHERE session_id = ?
                  AND active = 1
                  AND role IN ('user', 'assistant')
                  AND content IS NOT NULL
                  AND trim(content) != ''
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
                """,
                (session["id"], limit),
            ).fetchall()
    except sqlite3.Error as exc:
        raise HTTPException(status_code=502, detail=f"Could not read Telegram history: {exc}") from exc

    messages = [dict(row) for row in reversed(rows)]
    return {
        "profile": profile,
        "session_id": session["id"],
        "chat_id": session["chat_id"],
        "messages": messages,
    }


@app.post("/v1/messages/send")
async def send_message(
    req: MessageSendRequest, x_bridge_token: str | None = Header(default=None)
) -> dict:
    """Forward a message through Hermes's cross-channel gateway (Telegram,
    Discord, Slack, ...) -- shells out to send_message.py (HERMES_PYTHON,
    same subprocess pattern as _run_hermes_chat / hermes_stream.py) since
    the gateway's `tools`/`gateway` packages aren't importable from this
    process directly (see that script's docstring)."""
    _check_token(x_bridge_token)
    helper = str(Path(__file__).parent / "send_message.py")
    cmd = [HERMES_PYTHON, "-u", helper, "--target", req.target, "--message", req.message]
    if req.profile:
        # Resolved here rather than trusting a caller-supplied path: the
        # request carries a slug, and only slugs under the profiles dir are
        # reachable, so a caller can't point the send at an arbitrary
        # directory.
        # _valid_profile also checks the name against PROFILE_NAME_RE, so a
        # slug can't traverse out of the profiles dir.
        if not _is_valid_profile(req.profile):
            raise HTTPException(
                status_code=404, detail=f"No Hermes profile named {req.profile!r}"
            )
        profile_home = PROFILES_DIR / req.profile
        cmd += ["--profile-home", str(profile_home)]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Message send timed out") from None

    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1]) if proc.stdout.strip() else {}
    except (json.JSONDecodeError, IndexError):
        result = {}

    if proc.returncode != 0 or "error" in result:
        raise HTTPException(
            status_code=502,
            detail=result.get("error") or proc.stderr.strip()[-2000:] or "Message send failed",
        )
    return result


def _load_profile_llm_config(profile: str) -> dict:
    """Read ForgeRouter URL, API key, and model from the profile's config.yaml."""
    cfg_path = PROFILES_DIR / profile / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text())
    model_cfg = cfg.get("model", {})
    base_url = model_cfg.get("base_url", "http://localhost:2100/v1").rstrip("/")
    api_key = model_cfg.get("api_key", "")
    model_id = (model_cfg.get("main") or {}).get("model") or model_cfg.get("default", "forgerouter/auto")
    soul_file = PROFILES_DIR / profile / "SOUL.md"
    system_prompt = soul_file.read_text() if soul_file.exists() else ""
    return {"base_url": base_url, "api_key": api_key, "model": model_id, "system_prompt": system_prompt}


VOICE_MODEL = "cerebras/gpt-oss-120b"  # fast inference chip, consistent ~1.3s cold+warm


async def _direct_stream(profile: str, message: str, history: list) -> StreamingResponse:
    """Fast path: call ForgeRouter/LLM directly — no subprocess, ~1.5s to first token."""
    cfg = _load_profile_llm_config(profile)
    messages = [{"role": "system", "content": cfg["system_prompt"]}] + history + [{"role": "user", "content": message}]

    async def event_stream():
        full_reply = ""
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{cfg['base_url']}/chat/completions",
                    json={"model": VOICE_MODEL, "messages": messages, "stream": True, "max_tokens": 500},
                    headers={"Authorization": f"Bearer {cfg['api_key']}"},
                ) as resp:
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if raw == "[DONE]":
                            break
                        try:
                            data = json.loads(raw)
                            delta = data["choices"][0]["delta"].get("content", "")
                            if delta:
                                full_reply += delta
                                yield f'data: {json.dumps({"delta": delta})}\n\n'
                        except Exception:
                            pass
        except Exception as exc:
            yield f'data: {json.dumps({"error": str(exc)})}\n\n'
            return
        yield f'data: {json.dumps({"done": True, "session_id": None, "reply": full_reply})}\n\n'

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Chat for the external CLI runtimes (2026-08-14).
#
# /v1/chat/stream only ever spoke Hermes: it validated `profile` against
# /root/.hermes/profiles and ran hermes_cli. Aramis (codex), Dartan (agy),
# Vector (openclaw) and Porthus (claude) are not Hermes profiles, so every
# chat turn addressed to them died on "Unknown profile" -- the Workspace
# offered a conversation that could never happen.
#
# Each CLI already has a one-shot mode with machine-readable output (the same
# ones /v1/agent-runs dispatches), so the work here is translation, not a new
# execution path: run it, and map its native events onto the SSE contract
# hermes_stream.py defines ({stream_id} / {delta} / {tool_start} / {done}).
# Formats verified by hand against the installed binaries on 2026-08-14:
#
#   claude   --output-format stream-json: JSONL, system/init carries
#            session_id, assistant messages carry content[].text and
#            tool_use blocks, final {"type":"result","result":...}.
#   codex    exec --json: JSONL, thread.started carries thread_id,
#            item.completed/agent_message carries text.
#   agy      --print: plain text on stdout, no structure at all.
#   openclaw agent --json: a single JSON document at the end,
#            result.payloads[].text.
#
# Approval prompts have no equivalent here -- these CLIs decide permissions
# from their own flags, so a turn either runs or does not. The `stream_id`
# is still emitted and registered, so the Stop button and the reattach-turn
# machinery work exactly as they do for Hermes.
# ---------------------------------------------------------------------------

EXTERNAL_CHAT_RUNTIMES = ("claude", "codex", "agy", "openclaw")

# A chat turn is a conversation, not a work package: read-only sandboxes and
# plan modes would make the agent unable to do what it is being asked in the
# very screen built to ask it. Matches what /v1/agent-runs uses for
# mode="execute".
def _external_chat_command(runtime: str, message: str, cwd: str, session_id: str | None) -> list[str]:
    if runtime == "claude":
        cmd = [
            "/root/.local/bin/claude",
            "--print",
            "--output-format",
            "stream-json",
            "--verbose",
            "--permission-mode",
            "acceptEdits",
        ]
        # Claude Code is the only one of the four whose one-shot mode can
        # resume a previous conversation by id, which is what makes a chat
        # tab keep its context across turns.
        if session_id:
            cmd += ["--resume", session_id]
        cmd.append(message)
        return cmd
    if runtime == "codex":
        return [
            "/root/.npm-global/bin/codex",
            "exec",
            "--json",
            "--sandbox",
            "workspace-write",
            "--skip-git-repo-check",
            "-C",
            cwd,
            message,
        ]
    if runtime == "agy":
        return [
            "/root/.local/bin/agy",
            "--print",
            message,
            "--mode",
            "accept-edits",
            "--sandbox",
            "--print-timeout",
            "1800s",
        ]
    # openclaw: Vector runs as a persistent daemon with its own session
    # store, so continuity is the daemon's business, not ours -- there is no
    # session id to pass and none to give back.
    return [
        "/root/.npm-global/bin/openclaw",
        "agent",
        "--agent",
        "main",
        "--message",
        message,
        "--json",
    ]


def _claude_events(data: dict) -> tuple[list[dict], str | None, str | None]:
    """(events, session_id, final_reply) for one Claude Code stream-json line."""
    events: list[dict] = []
    kind = data.get("type")
    if kind == "system":
        # init also carries the tool list, hooks fire their own system lines --
        # only the session id matters to us, and none of it is worth relaying.
        return events, data.get("session_id"), None
    if kind == "assistant":
        for block in (data.get("message") or {}).get("content") or []:
            if block.get("type") == "text" and block.get("text"):
                events.append({"delta": block["text"]})
            elif block.get("type") == "tool_use":
                events.append({
                    "tool_start": {
                        "tool_id": block.get("id"),
                        "name": block.get("name"),
                        "context": _tool_context(block.get("input")),
                    }
                })
        return events, data.get("session_id"), None
    if kind == "result":
        return events, data.get("session_id"), data.get("result") or ""
    return events, None, None


def _codex_events(data: dict) -> tuple[list[dict], str | None, str | None]:
    """(events, session_id, final_reply) for one `codex exec --json` line."""
    kind = data.get("type")
    if kind == "thread.started":
        return [], data.get("thread_id"), None
    if kind == "item.completed":
        item = data.get("item") or {}
        if item.get("type") == "agent_message":
            text = item.get("text") or ""
            # Codex emits the whole message at once rather than token by
            # token: one delta, then the same text closes the turn.
            return ([{"delta": text}] if text else []), None, text
        if item.get("type") == "command_execution":
            return [{
                "tool_start": {
                    "tool_id": item.get("id"),
                    "name": "shell",
                    "context": (item.get("command") or "")[:80],
                }
            }], None, None
    return [], None, None


def _tool_context(tool_input) -> str:
    """80-char label for a tool call, matching what hermes_stream.py sends."""
    if isinstance(tool_input, dict):
        for key in ("command", "file_path", "path", "pattern", "query", "url"):
            if tool_input.get(key):
                return str(tool_input[key])[:80]
    return ""


async def _external_chat_stream(
    runtime: str, message: str, cwd: str | None, session_id: str | None
) -> StreamingResponse:
    work_dir = cwd if cwd and Path(cwd).is_dir() else "/root"
    command = _external_chat_command(runtime, message, work_dir, session_id)

    async def event_stream():
        stream_id = str(uuid.uuid4())
        yield f'data: {json.dumps({"stream_id": stream_id})}\n\n'
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir,
            env=os.environ.copy(),
        )
        _active_streams[stream_id] = proc
        new_session_id: str | None = None
        final_reply: str | None = None
        collected: list[str] = []
        # openclaw prints one JSON document at the end instead of a stream, so
        # its output is buffered whole and parsed after the process exits.
        buffer_whole = runtime == "openclaw"
        raw_buffer: list[str] = []
        idle_ping = 20
        idle_budget = 1800
        idle = 0
        try:
            while True:
                try:
                    line_bytes = await asyncio.wait_for(proc.stdout.readline(), timeout=idle_ping)
                except asyncio.TimeoutError:
                    idle += idle_ping
                    if idle >= idle_budget:
                        yield f'data: {json.dumps({"error": f"agent timeout: no output for {idle_budget}s, turn aborted"})}\n\n'
                        break
                    yield ": ping\n\n"
                    continue
                idle = 0
                if not line_bytes:
                    break
                line = line_bytes.decode(errors="replace").rstrip("\n")
                if not line.strip():
                    continue
                if buffer_whole:
                    raw_buffer.append(line)
                    continue
                if runtime == "agy":
                    # No structure to parse: every line the CLI prints is the
                    # answer itself.
                    collected.append(line)
                    yield f'data: {json.dumps({"delta": line + chr(10)})}\n\n'
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                events, sid, reply = (
                    _claude_events(data) if runtime == "claude" else _codex_events(data)
                )
                if sid:
                    new_session_id = sid
                for event in events:
                    if "delta" in event:
                        collected.append(event["delta"])
                    yield f"data: {json.dumps(event)}\n\n"
                if reply is not None:
                    final_reply = reply

            stderr_bytes = await proc.stderr.read()
            await proc.wait()

            if buffer_whole:
                try:
                    payload = json.loads("\n".join(raw_buffer))
                    texts = [
                        p.get("text") or ""
                        for p in (payload.get("result") or {}).get("payloads") or []
                    ]
                    final_reply = "\n".join(t for t in texts if t)
                    if final_reply:
                        yield f'data: {json.dumps({"delta": final_reply})}\n\n'
                except (json.JSONDecodeError, AttributeError):
                    final_reply = "\n".join(raw_buffer)
                    if final_reply:
                        yield f'data: {json.dumps({"delta": final_reply})}\n\n'

            reply = final_reply if final_reply is not None else "".join(collected).strip()
            if not reply and proc.returncode not in (0, None):
                # An empty answer plus a non-zero exit is a failure, not a
                # silent turn -- surface the CLI's own stderr instead of
                # persisting an empty assistant message.
                detail = stderr_bytes.decode(errors="replace").strip()[:400] or f"exit code {proc.returncode}"
                yield f'data: {json.dumps({"error": f"{runtime}: {detail}"})}\n\n'
                return
            done: dict = {"done": True, "reply": reply}
            if new_session_id:
                done["session_id"] = new_session_id
            yield f"data: {json.dumps(done)}\n\n"
        finally:
            _active_streams.pop(stream_id, None)
            try:
                proc.kill()
            except Exception:
                pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/v1/chat/stream")
async def chat_stream(
    profile: str,
    message: str,
    session_id: str | None = None,
    history: str | None = None,  # JSON array of {role,content} — enables direct ForgeRouter path
    cwd: str | None = None,  # ChatSession.working_directory_path, see chat.py's /stream
    runtime: str = "hermes",  # Agent.runtime_type; non-hermes takes the external-CLI path
    x_bridge_token: str | None = Header(default=None),
) -> StreamingResponse:
    """SSE endpoint — streams token deltas from the agent.

    Fast path (voice): when `history` is provided, calls ForgeRouter directly (~2s first token).
    Slow path (text): hermes_stream.py subprocess with full agent capabilities (~16s first token).
    """
    _check_token(x_bridge_token)

    # Voice's direct-ForgeRouter fast path is runtime-agnostic (it never
    # touches a CLI at all), so it takes precedence over the external-runtime
    # branch below regardless of which runtime the agent is.
    if history is not None:
        return await _direct_stream(profile, message, json.loads(history))

    if runtime in EXTERNAL_CHAT_RUNTIMES:
        # `profile` is the agent's profile_slug, not a Hermes profile
        # directory -- meaningless to _is_valid_profile, which is exactly
        # the check that used to 400 every external-runtime chat turn.
        return await _external_chat_stream(runtime, message, cwd, session_id)

    if not _is_valid_profile(profile):
        raise HTTPException(status_code=400, detail=f"Unknown profile: {profile}")

    # Subprocess path (full Hermes agent with tools, memory, etc.)
    profile_home = str(PROFILES_DIR / profile)
    effective_session_id = session_id

    cross_agent = PLUGINS_CROSS_AGENT_RE.match(message.strip())
    if cross_agent and _is_valid_profile(cross_agent.group(1)):
        # Stateless lookup of another agent's plugins, not a turn in this
        # conversation -- the current session_id belongs to `profile`'s own
        # session store, so resuming it against a different profile-home
        # would either fail or silently start an unrelated session. Drop it;
        # the backend already no-ops its own bookkeeping when `done` comes
        # back without a session_id (see chat.py's `if new_hsid:` guard).
        profile_home = str(PROFILES_DIR / cross_agent.group(1))
        effective_session_id = None

    helper = str(Path(__file__).parent / "hermes_stream.py")
    cmd = [HERMES_PYTHON, "-u", helper, "--profile-home", profile_home, "--message", message]
    if effective_session_id:
        cmd += ["--session-id", effective_session_id]
    if cwd:
        cmd += ["--cwd", cwd]

    async def event_stream():
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env={
                **os.environ,
                "HERMES_HOME": profile_home,
                "HERMES_SESSION_SOURCE": "tool",
                # Routes dangerous-command approval through hermes_stream.py's
                # register_gateway_notify callback instead of CLI input()
                # (see tools.approval._is_gateway_approval_context()).
                "HERMES_GATEWAY_SESSION": "1",
            },
        )
        stream_id: str | None = None
        # An agent turn can think/run tools for minutes without emitting a
        # single delta. Every proxy hop between here and the browser
        # (nginx, Cloudflare tunnel ~100s, etc.) kills a byte-silent
        # connection, which the UI surfaces as "network error" -- so emit
        # an SSE comment ping during silence. Only *consecutive* silence
        # counts toward the timeout (any output resets it); the budget must
        # cover a single long silent tool run (e.g. a ~200MB pip install),
        # because hitting it kills the agent subprocess mid-turn.
        idle_ping = 20
        idle_budget = 1800
        try:
            idle = 0
            while True:
                try:
                    line_bytes = await asyncio.wait_for(proc.stdout.readline(), timeout=idle_ping)  # type: ignore[union-attr]
                except asyncio.TimeoutError:
                    idle += idle_ping
                    if idle >= idle_budget:
                        yield f'data: {json.dumps({"error": f"agent timeout: no output for {idle_budget}s, turn aborted"})}\n\n'
                        break
                    yield ": ping\n\n"
                    continue
                idle = 0
                if not line_bytes:
                    break
                line = line_bytes.decode().strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if data.get("stream_id") and stream_id is None:
                    stream_id = data["stream_id"]
                    _active_streams[stream_id] = proc
                    # Also relayed below, not just bookkept (2026-08-14): this
                    # line used to `continue` here, silently swallowed. The
                    # bridge registering the process for /v1/chat/approve was
                    # always enough for approvals, but chat.py's ActiveTurn
                    # (added 2026-08-13, after this) opens a turn keyed off
                    # exactly this event -- without it reaching the caller,
                    # `open_turn` never ran for a single Hermes agent turn,
                    # and a reconnecting client had nothing to find (Marcelo:
                    # "ao sair do chat... ao retornar não apareceu nenhum
                    # processo"). The reply still landed once the turn
                    # finished (persistence never depended on turn_id), which
                    # is exactly why this went unnoticed -- only the *live*
                    # reattach view was silently empty the whole time.
                    yield f"data: {line}\n\n"
                    continue
                yield f"data: {line}\n\n"
                if data.get("done") or data.get("error"):
                    break
        finally:
            if stream_id is not None:
                _active_streams.pop(stream_id, None)
            try:
                if proc.stdin is not None:
                    proc.stdin.close()
            except Exception:
                pass
            try:
                proc.kill()
            except Exception:
                pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class ChatApproveRequest(BaseModel):
    stream_id: str
    choice: str  # "once" | "session" | "always" | "deny" -- see tools/approval.py's resolve_gateway_approval


@app.post("/v1/chat/approve")
async def chat_approve(req: ChatApproveRequest, x_bridge_token: str | None = Header(default=None)) -> dict:
    _check_token(x_bridge_token)
    proc = _active_streams.get(req.stream_id)
    if proc is None or proc.stdin is None:
        raise HTTPException(status_code=404, detail="No pending approval for this stream_id")
    # Was previously collapsed to "once"/"deny" only, silently discarding
    # "session"/"always" -- resolve_gateway_approval accepts all four and
    # only "session"/"always" call approve_session()/approve_permanent(),
    # so forwarding anything else as "once" broke "remember this session".
    resolved_choice = req.choice if req.choice in {"once", "session", "always", "deny"} else "once"
    line = json.dumps({"approval_response": {"choice": resolved_choice}}) + "\n"
    proc.stdin.write(line.encode())
    await proc.stdin.drain()
    return {"status": "ok"}


class ChatStopRequest(BaseModel):
    stream_id: str


@app.post("/v1/chat/stop")
async def chat_stop(req: ChatStopRequest, x_bridge_token: str | None = Header(default=None)) -> dict:
    """Kills the subprocess for a running chat turn (2026-08-14) -- the
    explicit counterpart to the browser simply disconnecting.

    Backend turns no longer die when a browser tab navigates away or closes
    (see chat.py's `_run_chat_turn`, detached from the request lifecycle),
    so the Stop button needs its own way to actually end a turn instead of
    relying on connection-drop-kills-the-process, which used to kill every
    turn on any disconnect -- Stop and "left the page" were indistinguishable.

    Not finding the process is not an error: it may have already finished, or
    this bridge may have restarted and lost its in-memory registry -- either
    way, the caller's goal (nothing runs) is already true.
    """
    _check_token(x_bridge_token)
    proc = _active_streams.get(req.stream_id)
    if proc is None:
        return {"status": "not_running"}
    try:
        proc.kill()
    except ProcessLookupError:
        pass
    return {"status": "stopping"}


class ExecRequest(BaseModel):
    command: str
    cwd: str | None = None
    # Auditor controls expose at most 600s; five additional seconds let the
    # inner `timeout` command finish and return exit 124 before the bridge
    # terminates its subprocess.
    timeout_seconds: int = Field(default=60, ge=1, le=605)


class ExecResponse(BaseModel):
    stdout: str
    stderr: str
    exit_code: int


@app.post("/v1/exec", response_model=ExecResponse)
async def exec_command(req: ExecRequest, x_bridge_token: str | None = Header(default=None)) -> ExecResponse:
    """One-shot bash execution backing the chat composer's "!" prefix --
    runs directly, no agent/LLM involved, output shown inline in the
    thread like a slash command reply. Not a live/interactive shell (see
    /v1/terminal/ws for that); a single command, one captured result."""
    _check_token(x_bridge_token)
    loop = asyncio.get_event_loop()

    def run() -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", "-c", req.command],
            cwd=req.cwd or None,
            capture_output=True,
            text=True,
            timeout=req.timeout_seconds,
        )

    try:
        proc = await loop.run_in_executor(None, run)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail=f"Command timed out after {req.timeout_seconds}s") from None
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail=f"cwd not found: {req.cwd}") from None
    return ExecResponse(stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode)


@app.post("/v1/chat-with-image", response_model=ChatResponse)
async def chat_with_image(
    profile: str = Form(...),
    message: str = Form(...),
    session_id: str | None = Form(default=None),
    images: list[UploadFile] = File(...),
    x_bridge_token: str | None = Header(default=None),
) -> ChatResponse:
    """Same as /v1/chat, but accepts the image(s) as bytes (the backend
    container has no path the host can resolve) and writes each to a host
    tmp dir before invoking --image (repeated, one per image)."""
    _check_token(x_bridge_token)

    dests: list[Path] = []
    for image in images:
        suffix = Path(image.filename or "image").suffix or ".png"
        dest = UPLOAD_DIR / f"{os.urandom(8).hex()}{suffix}"
        dest.write_bytes(await image.read())
        dests.append(dest)

    try:
        return _run_hermes_chat(
            ChatRequest(
                profile=profile,
                message=message,
                session_id=session_id,
                image_paths=[str(dest) for dest in dests],
            )
        )
    finally:
        for dest in dests:
            dest.unlink(missing_ok=True)


_whisper_model = None


def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel

        _whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
    return _whisper_model


@app.post("/v1/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    x_bridge_token: str | None = Header(default=None),
) -> dict:
    _check_token(x_bridge_token)

    suffix = Path(audio.filename or "audio").suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await audio.read())
        tmp_path = tmp.name

    try:
        model = _get_whisper_model()
        segments, _info = model.transcribe(tmp_path, beam_size=5)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return {"text": text}
    finally:
        os.unlink(tmp_path)


PIPER_MODEL = Path("/root/.local/share/piper/models/pt_BR-faber-medium/pt_BR-faber-medium.onnx")
PIPER_SAMPLE_RATE = 22050


@app.post("/v1/tts")
async def text_to_speech(
    payload: dict,
    x_bridge_token: str | None = Header(default=None),
):
    """Synthesise text with Piper (pt_BR-faber-medium) and return a WAV file."""
    _check_token(x_bridge_token)
    text = str(payload.get("text", "")).strip()
    if not text:
        from fastapi import Response as FResponse
        return FResponse(content=b"", media_type="audio/wav")

    proc = await asyncio.create_subprocess_exec(
        "piper",
        "-m", str(PIPER_MODEL),
        "--output-raw",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        raw_pcm, _ = await asyncio.wait_for(proc.communicate(input=text.encode()), timeout=30)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        raise HTTPException(status_code=504, detail="Piper TTS timeout")

    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(PIPER_SAMPLE_RATE)
        wf.writeframes(raw_pcm)
    buf.seek(0)
    from fastapi import Response as FResponse
    return FResponse(content=buf.read(), media_type="audio/wav")


@app.post("/v1/terminal/upload-image")
async def terminal_upload_image(
    image: UploadFile = File(...),
    x_bridge_token: str | None = Header(default=None),
) -> dict:
    """Save an image pasted into a terminal pane to a host tmp dir and hand
    back its absolute path. Unlike /v1/chat-with-image's upload, this file
    is not deleted afterwards -- we have no signal for when (or whether) the
    CLI agent running in the PTY actually reads it, only that the user is
    about to type/paste its path into their next prompt. It's still under
    the OS tmp dir, so it gets swept on reboot like any other tmp file."""
    _check_token(x_bridge_token)

    suffix = Path(image.filename or "image").suffix or ".png"
    dest = UPLOAD_DIR / f"{os.urandom(8).hex()}{suffix}"
    dest.write_bytes(await image.read())
    return {"path": str(dest)}


@app.post("/v1/workspace/upload")
async def workspace_upload(
    dir: str = Form(...),
    files: list[UploadFile] = File(...),
    x_bridge_token: str | None = Header(default=None),
) -> dict:
    """Write one or more browser-uploaded files straight into a host
    directory -- backs the workspace toolbar's "send files" button next to
    WorkingDirPicker, for pushing local files onto the box a terminal's cwd
    points at without going through the PTY (unlike upload-image above,
    these land in the real working directory, not a tmp dir, since the
    point is for a CLI agent's cwd to see them as project files)."""
    _check_token(x_bridge_token)
    target = Path(dir)
    if not target.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {dir}")
    saved = []
    for f in files:
        # basename only -- an uploaded filename carrying "../" must not be
        # able to write outside the chosen directory.
        name = Path(f.filename or "file").name
        if not name or name in (".", ".."):
            continue
        dest = target / name
        dest.write_bytes(await f.read())
        saved.append(str(dest))
    return {"saved": saved}


# ---------------------------------------------------------------------------
# Remote access -- backs the Dashboard's remote-access card. Spawns a
# Cloudflare "quick tunnel" (cloudflared tunnel --url ...), which needs
# neither a Cloudflare account nor a domain: it gets a random, temporary
# *.trycloudflare.com hostname each time it starts, torn down when stopped.
# Points at the frontend's nginx (frontend/nginx.conf), which itself
# reverse-proxies /api to forgehub-backend -- one tunnel covers the whole
# app. State is process-global since host-bridge runs as a single uvicorn
# worker (see the systemd unit).
# ---------------------------------------------------------------------------

TRYCLOUDFLARE_RE = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")

_tunnel_proc: "asyncio.subprocess.Process | None" = None
_tunnel_url: str | None = None
_tunnel_pump_task: "asyncio.Task | None" = None


async def _pump_tunnel_output(proc: "asyncio.subprocess.Process") -> None:
    global _tunnel_url
    assert proc.stdout is not None
    async for raw_line in proc.stdout:
        if _tunnel_url is not None:
            continue
        match = TRYCLOUDFLARE_RE.search(raw_line.decode(errors="ignore"))
        if match:
            _tunnel_url = match.group(0)


@app.post("/v1/remote-access/start")
async def remote_access_start(x_bridge_token: str | None = Header(default=None)) -> dict:
    _check_token(x_bridge_token)
    global _tunnel_proc, _tunnel_url, _tunnel_pump_task
    if _tunnel_proc is not None and _tunnel_proc.returncode is None:
        return {"status": "running", "url": _tunnel_url}
    _tunnel_url = None
    _tunnel_proc = await asyncio.create_subprocess_exec(
        "cloudflared", "tunnel", "--url", "http://localhost:4173",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    _tunnel_pump_task = asyncio.create_task(_pump_tunnel_output(_tunnel_proc))
    # cloudflared usually announces its assigned hostname within a couple of
    # seconds (see the manual timing check this was based on) -- give it up
    # to 15s before reporting back without a URL.
    for _ in range(75):
        if _tunnel_url is not None or _tunnel_proc.returncode is not None:
            break
        await asyncio.sleep(0.2)
    if _tunnel_proc.returncode is not None:
        _tunnel_proc = None
        return {"status": "error", "url": None}
    return {"status": "running", "url": _tunnel_url}


@app.post("/v1/remote-access/stop")
async def remote_access_stop(x_bridge_token: str | None = Header(default=None)) -> dict:
    _check_token(x_bridge_token)
    global _tunnel_proc, _tunnel_url, _tunnel_pump_task
    if _tunnel_proc is not None and _tunnel_proc.returncode is None:
        _tunnel_proc.terminate()
        try:
            await asyncio.wait_for(_tunnel_proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            _tunnel_proc.kill()
    _tunnel_proc = None
    _tunnel_url = None
    _tunnel_pump_task = None
    return {"status": "stopped"}


@app.get("/v1/remote-access/status")
async def remote_access_status(x_bridge_token: str | None = Header(default=None)) -> dict:
    _check_token(x_bridge_token)
    running = _tunnel_proc is not None and _tunnel_proc.returncode is None
    return {"status": "running" if running else "stopped", "url": _tunnel_url if running else None}


# ---------------------------------------------------------------------------
# VPN control -- fixed Tailscale operations only. This deliberately does not
# reuse /v1/exec: callers choose a logical node/action, never a command line.
# ---------------------------------------------------------------------------


class VpnActionRequest(BaseModel):
    action: Literal["connect", "disconnect", "restart", "test"]


@app.get("/v1/vpn/status")
async def vpn_status(x_bridge_token: str | None = Header(default=None)) -> dict:
    _check_token(x_bridge_token)
    return await asyncio.to_thread(_vpn_control.status)


@app.post("/v1/vpn/nodes/{node}/actions")
async def vpn_action(
    node: str,
    req: VpnActionRequest,
    x_bridge_token: str | None = Header(default=None),
) -> dict:
    _check_token(x_bridge_token)
    try:
        result = await asyncio.to_thread(_vpn_control.action, node, req.action)
    except VpnPolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result.get("success") is True:
        return result
    code = result.get("code")
    status_code = 409 if code == "peer_offline" else 504 if code == "timeout" else 502
    raise HTTPException(
        status_code=status_code,
        detail={"code": code or "command_failed", "summary": result.get("summary", "VPN operation failed.")},
    )


# ---------------------------------------------------------------------------
# Server status -- backs the Servers page's status column. A ping/TCP check
# alone can't tell "server is up" apart from "server is up but our key
# isn't authorized on it" -- Marcelo's own point when this was designed --
# so this does both: TCP reachability first, then (only if that succeeds) a
# non-interactive SSH auth probe with the configured identity.
# ---------------------------------------------------------------------------


class ServerCheckEntry(BaseModel):
    id: str
    ip_address: str
    remote_user: str
    ssh_port: int = 22
    ssh_key_path: str | None = None


class ServerCheckRequest(BaseModel):
    servers: list[ServerCheckEntry]


async def _check_one_server(entry: ServerCheckEntry) -> str:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(entry.ip_address, entry.ssh_port), timeout=3.0
        )
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()
    except Exception:
        return "off"

    ssh_args = [
        "ssh",
        "-o", "BatchMode=yes",  # never prompt for a password -- an auth
                                 # failure must return promptly, not hang
        "-o", "ConnectTimeout=3",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
    ]
    if entry.ssh_key_path:
        ssh_args += ["-i", entry.ssh_key_path]
    if entry.ssh_port != 22:
        ssh_args += ["-p", str(entry.ssh_port)]
    ssh_args += [f"{entry.remote_user}@{entry.ip_address}", "true"]

    try:
        proc = await asyncio.create_subprocess_exec(
            *ssh_args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )
        returncode = await asyncio.wait_for(proc.wait(), timeout=6.0)
    except Exception:
        return "not_installed"
    return "active" if returncode == 0 else "not_installed"


@app.post("/v1/servers/check-status")
async def check_server_status(
    req: ServerCheckRequest, x_bridge_token: str | None = Header(default=None)
) -> dict:
    _check_token(x_bridge_token)
    results = await asyncio.gather(*(_check_one_server(e) for e in req.servers))
    return {"statuses": {e.id: status for e, status in zip(req.servers, results)}}


# ---------------------------------------------------------------------------
# SSH key installation -- backs the Servers page's "install key" action.
# Parameterized, non-interactive version of /root/.hermes/scripts/
# configure_ssh.sh (same three steps, same key-naming convention): generate
# an ed25519 pair on THIS host (where the terminal's ssh runs), push the
# .pub into the server's authorized_keys using the password the user typed
# (sshpass -e: password travels via env, never argv, never logged), then
# verify with BatchMode. Idempotent: an existing key pair is reused.
# ---------------------------------------------------------------------------

SSH_KEYS_DIR = "/root/agents/aegis/server-management/ssh_keys"


class InstallKeyRequest(BaseModel):
    ip_address: str
    remote_user: str  # key owner on the server (e.g. "aegis")
    # Password of the LOGIN account: admin_user when set, remote_user otherwise.
    password: str
    ssh_port: int = 22
    # When set (and different from remote_user), log in as this account
    # instead and CREATE remote_user on the server if it doesn't exist yet —
    # covers inventory users (aegis) not provisioned on the box. Must be
    # root or have passwordless sudo.
    admin_user: str | None = None


def _install_hint(out: str, login_user: str) -> str:
    """Turns the raw ssh/sudo failure into an actionable hint. Crucially,
    distinguishes an SSH *login* rejection (wrong password / password auth
    disabled) from a *sudo* rejection (needs passwordless sudo) -- these look
    unrelated but were being conflated into one misleading message."""
    low = (out or "").lower()
    if "permission denied" in low and "sudo" not in low:
        return (
            f" — hint: SSH login as '{login_user}' was rejected. Check the password, "
            "or the server may not allow password login for this account "
            "(try 'root', or another admin that permits password SSH)."
        )
    if "sudo" in low or "a terminal is required" in low or "a password is required" in low:
        return f" — hint: '{login_user}' logged in but sudo failed; it needs passwordless sudo (or use 'root')."
    if "could not resolve" in low or "connection refused" in low or "timed out" in low or "no route to host" in low:
        return " — hint: the host is unreachable on this SSH port."
    return ""


async def _run_step(
    args: list[str], timeout: float, env: dict | None = None, input_text: str | None = None
) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE if input_text is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
    )
    try:
        out, _ = await asyncio.wait_for(
            proc.communicate(input_text.encode() if input_text is not None else None), timeout=timeout
        )
    except asyncio.TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        return 124, "timed out"
    return proc.returncode or 0, out.decode(errors="replace")[-800:]


# Identity files may only be read from / written to these roots. The vault
# endpoints below move private key material, so the path -- which arrives in a
# request body -- is never trusted on its own: without this, any caller
# holding the bridge token could name an arbitrary file and have its contents
# returned. Covers where SSH keys actually live on this host: the shell's own
# ~/.ssh, the Aegis profile's forgenet/server-management key directories, and
# whatever SSH_KEYS_DIR is set to.
PRIVATE_KEY_ROOTS = (
    "/root/.ssh",
    "/root/agents",
    "/root/.hermes/profiles",
    SSH_KEYS_DIR,
)


def _resolve_key_path(raw: str) -> str:
    """Validates a private-key path against PRIVATE_KEY_ROOTS. Resolves
    symlinks first (/root/agents/aegis is one), so `..` or a symlink pointing
    outside can't smuggle a path past the prefix check."""
    path = (raw or "").strip()
    if not path:
        raise HTTPException(status_code=400, detail="key_path is required")
    if path.endswith(".pub"):
        raise HTTPException(status_code=400, detail="key_path must be the private key, not the .pub")
    resolved = os.path.realpath(path)
    roots = [os.path.realpath(root) for root in PRIVATE_KEY_ROOTS]
    if not any(resolved == root or resolved.startswith(root + os.sep) for root in roots):
        raise HTTPException(status_code=400, detail="key_path is outside the allowed SSH key directories")
    return resolved


class PrivateKeyRequest(BaseModel):
    key_path: str


class WritePrivateKeyRequest(BaseModel):
    key_path: str
    private_key: str
    public_key: str | None = None


@app.post("/v1/servers/read-private-key")
async def read_private_key(
    req: PrivateKeyRequest, x_bridge_token: str | None = Header(default=None)
) -> dict:
    """Reads an identity file so ForgeHub can keep an encrypted copy of it
    (see servers.private_key_encrypted). The material crosses the wire on
    localhost, token-checked, and is encrypted before it is stored -- the
    alternative, leaving the only copy on disk, is what lost the 172.15.2.5
    key when the Aegis profile directory was recreated."""
    _check_token(x_bridge_token)
    path = _resolve_key_path(req.key_path)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"No identity file at {path}")
    with open(path, encoding="utf-8", errors="replace") as fh:
        private_key = fh.read()
    if "PRIVATE KEY" not in private_key:
        raise HTTPException(status_code=400, detail="File does not look like an SSH private key")
    public_key = None
    if os.path.isfile(path + ".pub"):
        with open(path + ".pub", encoding="utf-8", errors="replace") as fh:
            public_key = fh.read().strip()
    return {"private_key": private_key, "public_key": public_key, "key_path": path}


@app.post("/v1/servers/write-private-key")
async def write_private_key(
    req: WritePrivateKeyRequest, x_bridge_token: str | None = Header(default=None)
) -> dict:
    """Pours a vaulted identity file back onto the host at key_path (0600,
    parent directory created if needed), so a lost key can be restored without
    touching the server's authorized_keys. Refuses to overwrite an existing
    file: restoring is for a key that is *missing*, and silently replacing a
    working identity would be a much worse failure than reporting the
    conflict."""
    _check_token(x_bridge_token)
    path = _resolve_key_path(req.key_path)
    if "PRIVATE KEY" not in req.private_key:
        raise HTTPException(status_code=400, detail="Payload does not look like an SSH private key")
    if os.path.exists(path):
        raise HTTPException(status_code=409, detail=f"An identity file already exists at {path}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Create with 0600 from the start -- writing then chmod'ing would leave a
    # window where the private key is world-readable.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(req.private_key if req.private_key.endswith("\n") else req.private_key + "\n")
    written = [path]
    if req.public_key and not os.path.exists(path + ".pub"):
        with open(path + ".pub", "w", encoding="utf-8") as fh:
            fh.write(req.public_key.strip() + "\n")
        os.chmod(path + ".pub", 0o644)
        written.append(path + ".pub")
    return {"ok": True, "written": written}


class ReadPubKeyRequest(BaseModel):
    key_path: str


@app.post("/v1/servers/read-public-key")
async def read_public_key(req: ReadPubKeyRequest, x_bridge_token: str | None = Header(default=None)) -> dict:
    """Reads the public half of a configured SSH identity file on the host.
    Backs the Servers page's "copy public key" button: given the row's
    ssh_key_path, returns the contents of "<path>.pub" (or the path itself
    when it already ends in .pub). Read-only, .pub files only -- never
    returns a private key."""
    _check_token(x_bridge_token)
    path = req.key_path.strip()
    if not path:
        raise HTTPException(status_code=400, detail="key_path is required")
    pub_path = path if path.endswith(".pub") else path + ".pub"
    if not os.path.isfile(pub_path):
        raise HTTPException(status_code=404, detail=f"Public key not found at {pub_path}")
    with open(pub_path, encoding="utf-8", errors="replace") as fh:
        content = fh.read().strip()
    if not content.startswith("ssh-") and "ssh-" not in content.split(" ", 1)[0]:
        raise HTTPException(status_code=400, detail="File does not look like an SSH public key")
    return {"public_key": content, "pub_path": pub_path}


@app.post("/v1/servers/install-key")
async def install_server_key(
    req: InstallKeyRequest, x_bridge_token: str | None = Header(default=None)
) -> dict:
    _check_token(x_bridge_token)
    if not re.fullmatch(r"[\w.:-]+", req.ip_address) or not re.fullmatch(r"[\w.-]+", req.remote_user):
        raise HTTPException(status_code=400, detail="Invalid ip_address or remote_user")
    if not req.password:
        raise HTTPException(status_code=400, detail="Password is required")

    key_name = re.sub(r"[.:]", "_", req.ip_address) + "_key"
    key_path = os.path.join(SSH_KEYS_DIR, key_name)
    pub_path = key_path + ".pub"
    os.makedirs(SSH_KEYS_DIR, exist_ok=True)
    steps: list[str] = []

    if os.path.exists(key_path) and os.path.exists(pub_path):
        steps.append(f"Key pair already exists at {key_path} — reusing (idempotent)")
    else:
        code, out = await _run_step(
            ["ssh-keygen", "-t", "ed25519", "-f", key_path, "-N", "", "-C", f"monitoramento-{req.ip_address}"],
            timeout=30,
        )
        if code != 0:
            return {"ok": False, "step": "generate", "error": out, "steps": steps}
        steps.append(f"Generated ed25519 key pair at {key_path}")
    os.chmod(key_path, 0o600)

    with open(pub_path, encoding="utf-8") as fh:
        public_key = fh.read().strip()

    if req.admin_user and req.admin_user != req.remote_user:
        # Admin path: log in as admin_user, create remote_user if missing
        # (useradd → adduser → FreeBSD pw fallbacks), prepare its ~/.ssh with
        # correct ownership/permissions and append the public key. Both
        # usernames are regex-validated above/below; the pubkey is
        # host-generated base64 — safe to embed in the script.
        if not re.fullmatch(r"[\w.-]+", req.admin_user):
            raise HTTPException(status_code=400, detail="Invalid admin_user")
        script = f"""set -e
U='{req.remote_user}'
if ! id -u "$U" >/dev/null 2>&1; then
  useradd -m -s /bin/bash "$U" 2>/dev/null || adduser -D "$U" 2>/dev/null || pw useradd "$U" -m
  echo "__CREATED_USER__"
fi
H=$(getent passwd "$U" | cut -d: -f6); [ -n "$H" ] || H=$(eval echo "~$U")
mkdir -p "$H/.ssh"
grep -qxF '{public_key}' "$H/.ssh/authorized_keys" 2>/dev/null || echo '{public_key}' >> "$H/.ssh/authorized_keys"
chmod 700 "$H/.ssh"; chmod 600 "$H/.ssh/authorized_keys"
chown -R "$U":"$U" "$H/.ssh" 2>/dev/null || chown -R "$U" "$H/.ssh"
echo "__KEY_INSTALLED__"
"""
        # Carry the script as a base64 argument, NOT via stdin. sshpass owns
        # ssh's pty and forwards its own stdin into it -- piping the script
        # there races the password exchange and corrupts auth (surfaces as a
        # bogus "Permission denied"). With stdin empty, sshpass only injects
        # the password. The remote decodes and runs it via `sh` / `sudo sh`.
        script_b64 = base64.b64encode(script.encode()).decode()
        decode_run = "sh" if req.admin_user == "root" else "sudo -n sh"
        remote_cmd = f"echo {script_b64} | base64 -d | {decode_run}"
        admin_args = [
            "sshpass", "-e", "ssh",
            "-T",  # no remote tty -- we're not typing into it
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=15",
            "-o", "NumberOfPasswordPrompts=1",
            # Force password auth: don't offer the host's own identities
            # (which would waste tries / muddy the error), the user typed a
            # password precisely because key auth isn't set up yet. The host's
            # ~/.ssh/config hardens 172.15.* with `PasswordAuthentication no`
            # + `BatchMode yes` (key-only policy) -- override both here so the
            # one-time password bootstrap can run without editing that file.
            "-o", "PreferredAuthentications=password",
            "-o", "PubkeyAuthentication=no",
            "-o", "PasswordAuthentication=yes",
            "-o", "BatchMode=no",
        ]
        if req.ssh_port != 22:
            admin_args += ["-p", str(req.ssh_port)]
        admin_args += [f"{req.admin_user}@{req.ip_address}", remote_cmd]
        code, out = await _run_step(
            admin_args, timeout=60, env={**os.environ, "SSHPASS": req.password}
        )
        if code != 0 or "__KEY_INSTALLED__" not in out:
            return {
                "ok": False,
                "step": "install",
                "error": (out or "no output") + _install_hint(out, req.admin_user),
                "steps": steps,
            }
        if "__CREATED_USER__" in out:
            steps.append(f"User '{req.remote_user}' created on the server (was missing)")
        else:
            steps.append(f"User '{req.remote_user}' already exists on the server")
        steps.append(f"Public key installed in ~{req.remote_user}/.ssh/authorized_keys (via {req.admin_user})")
    else:
        copy_args = [
            "sshpass", "-e", "ssh-copy-id",
            "-i", pub_path,
            # Same rationale as the admin path: override the host's key-only
            # ~/.ssh/config hardening for 172.15.* so password bootstrap works.
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=15",
            "-o", "NumberOfPasswordPrompts=1",
            "-o", "PreferredAuthentications=password",
            "-o", "PubkeyAuthentication=no",
            "-o", "PasswordAuthentication=yes",
            "-o", "BatchMode=no",
        ]
        if req.ssh_port != 22:
            copy_args += ["-p", str(req.ssh_port)]
        copy_args.append(f"{req.remote_user}@{req.ip_address}")
        code, out = await _run_step(copy_args, timeout=45, env={**os.environ, "SSHPASS": req.password})
        if code != 0:
            return {"ok": False, "step": "install", "error": out + _install_hint(out, req.remote_user), "steps": steps}
        steps.append(f"Public key installed in {req.remote_user}@{req.ip_address}:~/.ssh/authorized_keys")

    verify_args = ["ssh", "-i", key_path, "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=accept-new"]
    if req.ssh_port != 22:
        verify_args += ["-p", str(req.ssh_port)]
    verify_args += [f"{req.remote_user}@{req.ip_address}", "true"]
    code, out = await _run_step(verify_args, timeout=25)
    if code != 0:
        return {"ok": False, "step": "verify", "error": out, "steps": steps}
    steps.append("Key authentication verified (BatchMode)")

    return {"ok": True, "key_path": key_path, "public_key": public_key, "steps": steps}


@app.get("/v1/health")
async def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# System stats -- backs the Dashboard's memory/disk card. Reads /proc/meminfo
# and the root filesystem directly rather than pulling in psutil, since this
# runs straight on the host (see module docstring) and that's the only thing
# that makes "the computer's" memory/disk meaningful -- the backend
# container's own view of either would just reflect its cgroup limits, not
# the host's.
# ---------------------------------------------------------------------------


def _memory_stats() -> dict:
    fields = {}
    with open("/proc/meminfo") as f:
        for line in f:
            key, _, rest = line.partition(":")
            parts = rest.strip().split()
            if not parts or not parts[0].isdigit():
                continue
            fields[key] = int(parts[0]) * 1024  # kB -> bytes

    total = fields.get("MemTotal", 0)
    available = fields.get("MemAvailable", 0)
    used = max(total - available, 0)
    return {
        "total_bytes": total,
        "used_bytes": used,
        "available_bytes": available,
        "percent_used": round(used / total * 100, 1) if total else 0.0,
    }


def _disk_stats() -> dict:
    # This host runs under WSL2: "/" is the distro's own ext4.vhdx, a
    # separate virtual disk from the real Windows machine and a poor proxy
    # for "is the computer's disk full" -- it stays mostly empty regardless
    # of how full the actual C: drive gets. /mnt/c (Windows' C:\ via drvfs)
    # is the disk that actually matters; fall back to "/" if it's unmounted
    # (e.g. running outside WSL).
    path = "/mnt/c" if os.path.ismount("/mnt/c") else "/"
    usage = shutil.disk_usage(path)
    return {
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "percent_used": round(usage.used / usage.total * 100, 1) if usage.total else 0.0,
    }


def _default_iface() -> str | None:
    """The interface carrying the default route -- the one whose counters
    in /proc/net/dev mean "this host's network traffic". Reading the route
    table avoids summing /proc/net/dev across all interfaces, which would
    double-count traffic relayed between Docker's veth/bridge pairs."""
    try:
        with open("/proc/net/route") as f:
            next(f)  # header
            for line in f:
                fields = line.split()
                if len(fields) > 1 and fields[1] == "00000000":
                    return fields[0]
    except OSError:
        return None
    return None


def _network_stats() -> dict:
    iface = _default_iface()
    rx_bytes = tx_bytes = 0
    if iface:
        with open("/proc/net/dev") as f:
            for line in f:
                name, _, rest = line.partition(":")
                if name.strip() != iface:
                    continue
                parts = rest.split()
                rx_bytes, tx_bytes = int(parts[0]), int(parts[8])
                break
    return {"interface": iface, "rx_bytes": rx_bytes, "tx_bytes": tx_bytes}


@app.get("/v1/system-stats")
async def get_system_stats(x_bridge_token: str | None = Header(default=None)) -> dict:
    """Read-only host memory/disk/network snapshot -- backs the Dashboard's
    system-stats card. Polled directly by the backend on every page load
    (no DB cache, unlike tool-versions) since this is cheap and always
    fresh."""
    _check_token(x_bridge_token)
    return {"memory": _memory_stats(), "disk": _disk_stats(), "network": _network_stats()}


# ---------------------------------------------------------------------------
# Tool version checks -- backs the Dashboard's "Tool Versions" card. Each
# tool exposes a different update interface (hermes has a true --check flag;
# claude/codex have neither a check-only flag nor an npm-independent version
# probe, so we diff the installed version against the npm registry; agy has
# no check-only mode at all -- `agy update` itself checks-and-applies in one
# step, same as its own background auto-updater which already does this
# every ~15 min regardless of this endpoint) -- so each check is tool-specific
# rather than a single generic path.
# ---------------------------------------------------------------------------


class ToolVersionResult(BaseModel):
    installed_version: str | None
    latest_version: str | None
    update_available: bool
    error: str | None = None


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout, proc.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        return 1, "", str(exc)


# npm registry lookups are a real network call; the installed CLI's "latest
# release" doesn't change minute to minute, so cache it briefly rather than
# hitting the registry on every 900s background poll tick.
_NPM_VERSION_CACHE_TTL_SECONDS = 3600
_npm_version_cache: dict[str, tuple[float, str | None]] = {}


def _npm_latest_version(package: str) -> str | None:
    now = time.monotonic()
    cached = _npm_version_cache.get(package)
    if cached is not None and now - cached[0] < _NPM_VERSION_CACHE_TTL_SECONDS:
        return cached[1]
    code, out, _err = _run(["npm", "view", package, "version"], timeout=20)
    version = out.strip() if code == 0 and out.strip() else None
    _npm_version_cache[package] = (now, version)
    return version


def _check_hermes() -> ToolVersionResult:
    code, out, err = _run(["/root/.local/bin/hermes", "--version"])
    if code != 0:
        return ToolVersionResult(installed_version=None, latest_version=None, update_available=False, error=err.strip()[:500])
    installed_m = re.search(r"Hermes Agent v(\S+)", out)
    installed = installed_m.group(1) if installed_m else None

    # `hermes --version` prints a free-text trailer ("Update available: 66
    # commits behind — run 'hermes update'") that isn't a version string and
    # was previously captured verbatim. `hermes update --check` is a
    # dedicated, non-mutating check (confirmed via --help: "Check whether an
    # update is available without installing anything") whose own output
    # keeps the actionable status on its own line, so the same capture regex
    # against it yields a clean, bounded value instead.
    check_code, check_out, check_err = _run(["/root/.local/bin/hermes", "update", "--check"], timeout=30)
    if check_code != 0:
        return ToolVersionResult(
            installed_version=installed, latest_version=None, update_available=False, error=check_err.strip()[:500] or None
        )
    update_m = re.search(r"Update available:\s*(.+)", check_out)
    return ToolVersionResult(
        installed_version=installed,
        latest_version=update_m.group(1).strip().rstrip(".") if update_m else None,
        update_available=bool(update_m),
    )


def _check_npm_backed(binary: str, version_pattern: str, npm_package: str) -> ToolVersionResult:
    code, out, err = _run([binary, "--version"])
    if code != 0:
        return ToolVersionResult(installed_version=None, latest_version=None, update_available=False, error=err.strip()[:500])
    installed_m = re.search(version_pattern, out)
    installed = installed_m.group(1) if installed_m else out.strip() or None
    latest = _npm_latest_version(npm_package)
    return ToolVersionResult(
        installed_version=installed,
        latest_version=latest,
        update_available=bool(installed and latest and installed != latest),
    )


def _check_antigravity(run_update: bool = True) -> ToolVersionResult:
    """agy has no check-only mode -- `agy update` itself checks-and-applies in
    one step (confirmed via `agy update --help` / `agy --version`: there is
    no separate --check/--dry-run flag). `run_update=False` skips re-running
    it and only reports the installed version, for callers that already just
    ran a real update themselves and don't want to trigger a second one."""
    if run_update:
        code, out, err = _run(["/root/.local/bin/agy", "update"], timeout=180)
    else:
        code, out, err = 0, "", ""
    version_code, version_out, _ = _run(["/root/.local/bin/agy", "--version"])
    installed = version_out.strip() if version_code == 0 else None
    if run_update and code != 0:
        return ToolVersionResult(installed_version=installed, latest_version=None, update_available=False, error=err.strip()[:500])
    updated = run_update and "update successful" in out.lower()
    return ToolVersionResult(
        installed_version=installed,
        latest_version="updated just now" if updated else installed,
        update_available=updated,
    )


TOOL_CHECKS = {
    "hermes": _check_hermes,
    "claude": lambda: _check_npm_backed("/root/.local/bin/claude", r"^(\S+)\s*\(Claude Code\)", "@anthropic-ai/claude-code"),
    "codex": lambda: _check_npm_backed("/root/.npm-global/bin/codex", r"codex-cli (\S+)", "@openai/codex"),
    "antigravity": _check_antigravity,
    # pi and opencode both print a bare version string ("0.80.2") with no
    # surrounding label, and both are also published to the npm registry
    # under a different name than their binary (pi: @earendil-works/
    # pi-coding-agent; opencode: opencode-ai) -- same npm-diff strategy as
    # claude/codex above, just with a simpler capture pattern.
    "pi": lambda: _check_npm_backed("/root/.npm-global/bin/pi", r"(\d+\.\d+\.\d+)", "@earendil-works/pi-coding-agent"),
    "opencode": lambda: _check_npm_backed("/root/.opencode/bin/opencode", r"(\d+\.\d+\.\d+)", "opencode-ai"),
    # `openclaw --version` prints "OpenClaw 2026.7.1-2 (0790d9f)" -- a label
    # prefix and a trailing commit hash, unlike pi/opencode's bare version
    # string -- and is published to npm under its own binary name (unlike
    # pi/codex above), so the capture group only needs to isolate the
    # middle token.
    "openclaw": lambda: _check_npm_backed("/root/.npm-global/bin/openclaw", r"OpenClaw (\S+)", "openclaw"),
}

TOOL_UPDATE_COMMANDS = {
    "hermes": ["/root/.local/bin/hermes", "update", "--yes"],
    "claude": ["/root/.local/bin/claude", "update"],
    "codex": ["/root/.npm-global/bin/codex", "update"],
    "antigravity": ["/root/.local/bin/agy", "update"],
    # Both have a built-in self-update subcommand that no-ops cleanly (exit
    # 0, no prompt) when already current.
    "pi": ["/root/.npm-global/bin/pi", "update"],
    "opencode": ["/root/.opencode/bin/opencode", "upgrade"],
    "openclaw": ["/root/.npm-global/bin/openclaw", "update", "--yes"],
}


@app.get("/v1/tool-versions")
async def get_tool_versions(
    tools: str | None = None,
    no_mutate: str | None = None,
    x_bridge_token: str | None = Header(default=None),
) -> dict:
    """Read-only version/update-available check for every monitored CLI --
    backs the Dashboard's tool-version card and its periodic sync poll.
    (The antigravity check is the one exception that isn't truly read-only;
    see _check_antigravity.)

    `tools`: optional comma-separated subset to check (default: all). Lets
    callers exclude antigravity from the unattended periodic poll, since its
    "check" is a real `agy update` and it already has its own ~15min
    auto-updater independent of this loop.
    `no_mutate`: optional comma-separated subset to check without
    side-effects (only meaningful for antigravity) -- used right after an
    explicit POST /update for that tool, so the immediate status refresh
    doesn't run `agy update` a second time.
    """
    _check_token(x_bridge_token)
    selected = tools.split(",") if tools else list(TOOL_CHECKS)
    skip_mutation = set(no_mutate.split(",")) if no_mutate else set()

    def check_fn_for(tool: str):
        if tool == "antigravity" and "antigravity" in skip_mutation:
            return lambda: _check_antigravity(run_update=False)
        return TOOL_CHECKS[tool]

    loop = asyncio.get_event_loop()
    entries = [(tool, check_fn_for(tool)) for tool in selected if tool in TOOL_CHECKS]
    values = await asyncio.gather(*(loop.run_in_executor(None, fn) for _, fn in entries))
    return {tool: value.model_dump() for (tool, _), value in zip(entries, values)}


class ToolUpdateRequest(BaseModel):
    tool: str


class ToolUpdateResponse(BaseModel):
    success: bool
    output: str
    error: str | None = None


@app.post("/v1/tool-versions/update", response_model=ToolUpdateResponse)
async def update_tool(req: ToolUpdateRequest, x_bridge_token: str | None = Header(default=None)) -> ToolUpdateResponse:
    """Run the tool's real update command -- triggered only by an explicit
    user click on the Dashboard, not by the periodic sync poll above."""
    _check_token(x_bridge_token)
    cmd = TOOL_UPDATE_COMMANDS.get(req.tool)
    if cmd is None:
        raise HTTPException(status_code=400, detail=f"Unknown tool: {req.tool}")
    runner = lambda: _run(cmd, timeout=600)  # noqa: E731
    loop = asyncio.get_event_loop()
    code, out, err = await loop.run_in_executor(None, runner)
    return ToolUpdateResponse(success=code == 0, output=out[-4000:], error=(err[-2000:] or None) if code != 0 else None)


# ---------------------------------------------------------------------------
# OpenClaw dashboard -- the "Web" side of the Workspace's OpenClaw launcher
# menu (the "Terminal" side just types `openclaw` into a tmux pane, see
# LAUNCHER_COMMANDS below). OpenClaw's own Control UI (dist/control-ui) sends
# `X-Frame-Options: DENY` and can't be iframed at all, and its gateway auth
# token is required at the WebSocket handshake before the dashboard can do
# anything -- per OpenClaw's own docs (docs/web/dashboard.md), the supported
# one-time bootstrap is a `#token=<value>` URL fragment, which its own JS
# reads once into sessionStorage and then strips from the URL. `openclaw
# dashboard` itself refuses to embed this automatically because the token is
# configured as a SecretRef (`gateway.auth.token.source: "env"`) rather than
# a literal value, and deliberately avoids printing/copying a tokenized URL
# for an externally-managed secret -- this endpoint does the same lookup
# (read `OPENCLAW_GATEWAY_TOKEN` from OpenClaw's own env file) but is fine
# handing it back over the already bridge-token-authenticated /v1 surface,
# same trust boundary as every other endpoint below that hands back
# host-level access (browse-dirs, fs/list, the terminal PTY itself).
# ---------------------------------------------------------------------------

OPENCLAW_ENV_FILE = Path("/root/.openclaw/.env")
OPENCLAW_DASHBOARD_URL = "http://127.0.0.1:28340/"


def _openclaw_gateway_token() -> str | None:
    if not OPENCLAW_ENV_FILE.is_file():
        return None
    for line in OPENCLAW_ENV_FILE.read_text().splitlines():
        if line.startswith("OPENCLAW_GATEWAY_TOKEN="):
            return line.split("=", 1)[1].strip() or None
    return None


@app.get("/v1/openclaw/dashboard-url")
async def openclaw_dashboard_url(x_bridge_token: str | None = Header(default=None)) -> dict:
    _check_token(x_bridge_token)
    token = _openclaw_gateway_token()
    url = f"{OPENCLAW_DASHBOARD_URL}#token={token}" if token else OPENCLAW_DASHBOARD_URL
    return {"url": url, "has_token": token is not None}


# Read/write access to the raw token itself -- backs ForgeHub Settings' "OpenClaw"
# card (2026-07-29, Marcelo: wants the token visible/settable from ForgeHub instead
# of SSHing in and editing this file by hand). Same trust boundary as the endpoint
# above, which already hands this exact value back to the browser embedded in a URL
# fragment. Writing preserves every other line in the file untouched (upsert, not
# overwrite) -- OPENCLAW_ENV_FILE also carries FORGEROUTER_API_KEY/TELEGRAM_BOT_TOKEN/
# etc. for this same OpenClaw instance (Vector), not just the gateway token. A write
# here does NOT restart openclaw-gateway.service: the running daemon only reads this
# value once at process start (it's wired as a SecretRef, `gateway.auth.token.source:
# "env"`, per the docstring above), so a change only takes effect on its next restart.
def _set_openclaw_gateway_token(token: str) -> None:
    lines = OPENCLAW_ENV_FILE.read_text().splitlines() if OPENCLAW_ENV_FILE.is_file() else []
    new_line = f"OPENCLAW_GATEWAY_TOKEN={token}"
    for i, line in enumerate(lines):
        if line.startswith("OPENCLAW_GATEWAY_TOKEN="):
            lines[i] = new_line
            break
    else:
        lines.append(new_line)
    OPENCLAW_ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    OPENCLAW_ENV_FILE.write_text("\n".join(lines) + "\n")


class OpenclawGatewayTokenRequest(BaseModel):
    token: str


@app.get("/v1/openclaw/gateway-token")
async def get_openclaw_gateway_token(x_bridge_token: str | None = Header(default=None)) -> dict:
    _check_token(x_bridge_token)
    return {"token": _openclaw_gateway_token()}


@app.put("/v1/openclaw/gateway-token")
async def set_openclaw_gateway_token(req: OpenclawGatewayTokenRequest, x_bridge_token: str | None = Header(default=None)) -> dict:
    _check_token(x_bridge_token)
    token = req.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token cannot be empty")
    _set_openclaw_gateway_token(token)
    return {"token": token}


# ---------------------------------------------------------------------------
# Terminal -- a real PTY on the host, one per WebSocket connection.
#
# "Launcher" buttons (Claude CLI, Codex CLI, Antigravity's "agy" CLI, ...)
# don't exec the tool directly -- they spawn a normal login shell and type
# the command into it, same as a user would. That way "command not found"
# (e.g. a launcher that isn't on PATH yet) behaves exactly like a real
# terminal instead of needing special-cased error handling here.
# ---------------------------------------------------------------------------

LAUNCHER_COMMANDS = {"hermes --tui", "claude", "codex", "agy", "pi", "opencode", "openclaw"}

# The Servers domain's "SSH" launcher (ForgeHub frontend's buildSshCommand)
# sends a per-server command that can't be a fixed whitelist entry like the
# ones above -- constrained by shape instead: `ssh`, any number of a small
# WHITELIST of auth-related `-o Key=Value` options (the password-flow uses
# these to override the host's key-only ~/.ssh/config for one connection),
# optional `-i <path>`, optional `-p <port>`, then `user@host`. Only those
# fixed option names are allowed and values are limited to word/comma/dot/
# dash chars -- no spaces or shell metacharacters -- so this still can't be
# turned into anything but an ssh invocation (in particular, dangerous
# options like ProxyCommand/LocalCommand are not in the whitelist).
SSH_LAUNCHER_RE = re.compile(
    r"^ssh"
    r"(?: -o (?:PubkeyAuthentication|PasswordAuthentication|BatchMode|"
    r"PreferredAuthentications|StrictHostKeyChecking|ConnectTimeout|"
    r"NumberOfPasswordPrompts)=[\w,.-]+)*"
    r"(?: -i [\w./_-]+)?(?: -p \d{1,5})? [\w.-]+@[\w.:-]+$"
)


def _is_allowed_launcher_command(command: str | None) -> bool:
    if command is None:
        return False
    return command in LAUNCHER_COMMANDS or bool(SSH_LAUNCHER_RE.match(command))


def _set_winsize(fd: int, rows: int, cols: int) -> None:
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


class DirEntry(BaseModel):
    name: str
    path: str


class BrowseDirsResponse(BaseModel):
    path: str
    parent: str | None
    entries: list[DirEntry]


@app.get("/v1/browse-dirs", response_model=BrowseDirsResponse)
async def browse_dirs(
    path: str | None = Query(default=None),
    x_bridge_token: str | None = Header(default=None),
) -> BrowseDirsResponse:
    """List subdirectories of a host path, for the chat UI's working
    -directory picker (used before launching a terminal/CLI launcher)."""
    _check_token(x_bridge_token)

    target = Path(path).expanduser() if path else Path.home()
    try:
        target = target.resolve()
    except OSError:
        raise HTTPException(status_code=400, detail="Invalid path") from None
    if not target.is_dir():
        raise HTTPException(status_code=404, detail="Not a directory")

    try:
        children = sorted(target.iterdir(), key=lambda p: p.name.lower())
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied") from None

    entries = []
    for entry in children:
        try:
            if entry.is_dir():
                entries.append(DirEntry(name=entry.name, path=str(entry)))
        except OSError:
            continue  # broken symlink or similar -- skip rather than 500

    parent = str(target.parent) if target.parent != target else None
    return BrowseDirsResponse(path=str(target), parent=parent, entries=entries)


SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _tmux(*args: str, timeout: int = 10) -> subprocess.CompletedProcess:
    return subprocess.run(["tmux", *args], capture_output=True, text=True, timeout=timeout)


def _tmux_session_exists(name: str) -> bool:
    return _tmux("has-session", "-t", name).returncode == 0


def _list_forgehub_tmux_sessions() -> list[dict]:
    """Shared by the `/v1/terminal/sessions` listing endpoint (Fase 6.2)
    and the inactivity sweep below (Fase 6.4) -- one source of truth for
    parsing tmux's own session table, so the two never drift out of sync
    on what counts as a "forgehub" session."""
    result = _tmux(
        "list-sessions",
        "-F",
        "#{session_name}\t#{session_created}\t#{session_activity}\t#{session_attached}",
    )
    sessions = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 4 or not parts[0].startswith("forgehub-"):
            continue
        name, created, activity, attached = parts
        sessions.append(
            {
                "session_id": name[len("forgehub-") :],
                "created_at": int(created),
                "last_activity_at": int(activity),
                "attached": attached == "1",
            }
        )
    return sessions


@app.get("/v1/terminal/sessions")
async def list_terminal_sessions(x_bridge_token: str | None = Header(default=None)) -> dict:
    """Lists every live `forgehub-*` tmux session on the host (Fase 6.2,
    2026-07-28) -- a tab closed without going through the UI's own close
    button (browser crash, F5 outside the Workspace flow) leaves its tmux
    session running forever with nothing in ForgeHub aware it exists. This
    is the disk-truth read the System Control screen's cleanup card uses
    to surface and kill those orphans, same reasoning as
    `_list_scripts`/`_audit_check_script_refs` elsewhere in this file."""
    _check_token(x_bridge_token)
    return {"sessions": _list_forgehub_tmux_sessions()}


# Fase 6.4 (2026-07-28): a tmux session never expires on its own -- an
# orphan (see Fase 6.2 above) sits there forever, invisible unless someone
# happens to open System Control. This sweep kills only what tmux's own
# `session_activity` (real last input/output, not creation time) proves
# has been quiet past the timeout -- never a young session, only a
# genuinely forgotten one. Both knobs are env-configurable since "how long
# is too long" is an operational judgment call, not a constant worth
# hardcoding.
TERMINAL_INACTIVITY_TIMEOUT_SECONDS = int(os.environ.get("FORGEHUB_TERMINAL_INACTIVITY_TIMEOUT_HOURS", "24")) * 3600
TERMINAL_INACTIVITY_SWEEP_INTERVAL_SECONDS = int(os.environ.get("FORGEHUB_TERMINAL_SWEEP_INTERVAL_SECONDS", "1800"))
_terminal_inactivity_sweep_task: asyncio.Task | None = None


async def _terminal_inactivity_sweep_loop() -> None:
    while True:
        try:
            now = int(time.time())
            for session in _list_forgehub_tmux_sessions():
                if now - session["last_activity_at"] >= TERMINAL_INACTIVITY_TIMEOUT_SECONDS:
                    _tmux("kill-session", "-t", f"forgehub-{session['session_id']}")
        except Exception:
            pass
        await asyncio.sleep(TERMINAL_INACTIVITY_SWEEP_INTERVAL_SECONDS)


@app.on_event("startup")
async def _start_terminal_inactivity_sweep() -> None:
    global _terminal_inactivity_sweep_task
    _terminal_inactivity_sweep_task = asyncio.create_task(_terminal_inactivity_sweep_loop())


@app.on_event("shutdown")
async def _stop_terminal_inactivity_sweep() -> None:
    if _terminal_inactivity_sweep_task:
        _terminal_inactivity_sweep_task.cancel()


@app.post("/v1/terminal/sessions/{session_id}/kill")
async def kill_terminal_session(session_id: str, x_bridge_token: str | None = Header(default=None)) -> dict:
    """Fully ends a terminal tab's session (vs. just disconnecting the
    WebSocket, which only detaches -- see terminal_ws). Called when the user
    explicitly closes a tab in the UI."""
    _check_token(x_bridge_token)
    if not SESSION_ID_RE.match(session_id):
        raise HTTPException(status_code=422, detail="Invalid session id")
    _tmux("kill-session", "-t", f"forgehub-{session_id}")
    return {"status": "ok"}


class HermesSessionCheckItem(BaseModel):
    profile: str
    session_id: str


class HermesSessionCheckRequest(BaseModel):
    sessions: list[HermesSessionCheckItem]


@app.post("/v1/hermes/sessions/check")
async def check_hermes_sessions(
    req: HermesSessionCheckRequest, x_bridge_token: str | None = Header(default=None)
) -> dict:
    """Batch liveness check for Hermes CLI sessions, one profile's `state.db`
    at a time -- backs the Workspace's "Chat Sessions" card (System Control,
    2026-08-24), same disk-truth idea as `/v1/terminal/sessions` above but
    for a `ChatSession.hermes_session_id` instead of a tmux pane. Unlike a
    tmux session, a Hermes session row never disappears on its own (no
    auto_prune by default -- see hermes_cli/config_defaults.py); it going
    missing means it was pruned, the profile's state.db was rebuilt, or
    similar host-side housekeeping outside ForgeHub's control. That's
    exactly the failure this card exists to surface (Athos Workspace chat
    stuck resuming a session ten days gone, root-caused 2026-08-24) --
    `_init_agent()` (hermes_cli/cli_agent_setup_mixin.py) just returns False
    with no detail reaching the caller, so this is the only way to tell
    "stale" apart from "credentials broken" ahead of the next message
    failing.

    Grouped by profile so N sessions in the same profile cost one query,
    not N -- callers are expected to batch every ChatSession/
    ChatSessionParticipant row across every agent in one request.
    """
    _check_token(x_bridge_token)
    by_profile: dict[str, list[str]] = {}
    for item in req.sessions:
        if not _is_valid_profile(item.profile) or not SESSION_ID_RE.match(item.session_id):
            continue
        by_profile.setdefault(item.profile, []).append(item.session_id)

    results: list[dict] = []
    for profile, session_ids in by_profile.items():
        state_db = PROFILES_DIR / profile / "state.db"
        found: dict[str, sqlite3.Row] = {}
        if state_db.is_file():
            try:
                with sqlite3.connect(f"file:{state_db}?mode=ro", uri=True, timeout=5) as conn:
                    conn.row_factory = sqlite3.Row
                    placeholders = ",".join("?" for _ in session_ids)
                    rows = conn.execute(
                        f"""
                        SELECT id, title, started_at, last_activity_at, ended_at, message_count
                        FROM sessions
                        WHERE id IN ({placeholders})
                        """,
                        session_ids,
                    ).fetchall()
                    found = {row["id"]: row for row in rows}
            except sqlite3.Error:
                found = {}
        for sid in session_ids:
            row = found.get(sid)
            if row is None:
                results.append({"profile": profile, "session_id": sid, "exists": False})
            else:
                results.append({
                    "profile": profile,
                    "session_id": sid,
                    "exists": True,
                    "title": row["title"],
                    "started_at": row["started_at"],
                    "last_activity_at": row["last_activity_at"] or row["started_at"],
                    "ended_at": row["ended_at"],
                    "message_count": row["message_count"],
                })
    return {"sessions": results}


@app.websocket("/v1/terminal/ws")
async def terminal_ws(
    websocket: WebSocket,
    token: str = Query(...),
    session: str = Query(...),
    command: str | None = Query(default=None),
    cwd: str | None = Query(default=None),
) -> None:
    if token != BRIDGE_TOKEN or not SESSION_ID_RE.match(session):
        await websocket.close(code=4401)
        return
    await websocket.accept()

    home = str(Path.home())
    # Each terminal tab maps 1:1 to a tmux session named after the tab's id,
    # namespaced so it can't collide with unrelated tmux sessions on the
    # host. Reusing an existing session (rather than always spawning a fresh
    # shell) is what makes reconnecting after a navigation/disconnect resume
    # a running CLI agent instead of losing it -- see terminal_ws's finally
    # block, which only detaches on disconnect, never kills the session.
    session_name = f"forgehub-{session}"
    is_new = not _tmux_session_exists(session_name)
    if is_new:
        # -c sets the pane's starting directory directly (no typed `cd`
        # needed, so no risk of it ever flashing on screen on first attach).
        _tmux("new-session", "-d", "-s", session_name, "-x", "80", "-y", "24", "-c", cwd or home)
        # Without this, the mouse wheel/scrollbar over the pane does nothing --
        # tmux owns the pane's scrollback itself (it's not exposed through
        # xterm.js's native viewport), and only enters copy-mode to scroll it
        # when the client has mouse reporting on. Session-scoped (no -g) so it
        # doesn't change behavior for unrelated sessions on the shared host.
        _tmux("set-option", "-t", session_name, "mouse", "on")
        if _is_allowed_launcher_command(command):
            # Only on creation -- reattaching to an existing session must
            # never re-type the launcher, or every reconnect would relaunch
            # claude/codex/agy on top of whatever's already running.
            #
            # Bare `command` is intentional even for a ForgeRouter-enabled
            # Codex project: this pane runs an interactive bash that sources
            # ~/.bashrc, whose `codex()` function already routes through
            # /root/.local/bin/codex -- a wrapper that detects the project's
            # .codex/forgerouter.env itself and injects the same -c overrides
            # (see FORGEROUTER_CODEX_OVERRIDES comment above). Injecting them
            # here too double-registers `-m`, which Codex's arg parser
            # rejects ("the argument '--model <MODEL>' cannot be used
            # multiple times"). The orchestrated codex-exec path in
            # _agent_run_command has no such shell/wrapper in its execution
            # chain, so it still builds the overrides itself.
            _tmux("send-keys", "-t", session_name, "-l", command)
            _tmux("send-keys", "-t", session_name, "Enter")

    master_fd, slave_fd = pty.openpty()
    _set_winsize(master_fd, 24, 80)

    proc = subprocess.Popen(
        ["tmux", "attach-session", "-t", session_name],
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        env={**os.environ, "TERM": "xterm-256color"},
        close_fds=True,
    )
    os.close(slave_fd)  # the child has its own copy; the parent doesn't need this end
    fd = master_fd

    loop = asyncio.get_event_loop()
    output_queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    def reader_thread() -> None:
        while True:
            try:
                data = os.read(fd, 4096)
            except OSError:
                data = b""
            loop.call_soon_threadsafe(output_queue.put_nowait, data or None)
            if not data:
                return

    threading.Thread(target=reader_thread, daemon=True).start()

    async def pump_output() -> None:
        # An incremental decoder carries an incomplete trailing multi-byte
        # UTF-8 sequence over to the next chunk instead of mangling it into
        # a replacement character when a 4096-byte read happens to split it.
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        while True:
            chunk = await output_queue.get()
            if chunk is None:
                await websocket.close()
                return
            await websocket.send_text(decoder.decode(chunk))

    output_task = asyncio.create_task(pump_output())

    try:
        while True:
            message = await websocket.receive_text()
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                continue
            if payload.get("type") == "input":
                os.write(fd, payload.get("data", "").encode())
            elif payload.get("type") == "resize":
                _set_winsize(fd, int(payload.get("rows", 24)), int(payload.get("cols", 80)))
                # Unlike a plain bash PTY, the tmux client here doesn't have
                # this PTY as its controlling terminal (it was never set up
                # via setsid + TIOCSCTTY, which is what makes the kernel
                # deliver SIGWINCH automatically on TIOCSWINSZ) -- so the
                # resize above is invisible to it until nudged explicitly,
                # leaving the tmux window stuck at its creation size while
                # xterm.js on the browser side resizes freely. Confirmed via
                # direct testing: tmux only picks up the new size once it
                # actually receives SIGWINCH itself.
                try:
                    os.kill(proc.pid, signal.SIGWINCH)
                except ProcessLookupError:
                    pass
    except WebSocketDisconnect:
        pass
    finally:
        output_task.cancel()
        # Only end *our* `tmux attach-session` client, never the session
        # itself -- the pane (and whatever's running inside it, claude/codex/
        # antigravity/...) belongs to the tmux server, a separate long-lived
        # process, and keeps running so a later reconnect with the same
        # session id can resume it. Explicit kill is a separate endpoint
        # (kill_terminal_session) for when the user actually closes the tab.
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        try:
            os.close(fd)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Project file browser -- generic read/write file manager over a host path,
# backing the Project Delivery > Projects detail page's working-directory
# file tree. Unlike foundation_docs.py (backend container, jailed to one
# mounted .md-only root), a project's working_directory_path is an arbitrary
# HOST path the backend container can't see -- so, same reasoning as the
# terminal/browse-dirs endpoints above, this service does the actual
# filesystem work. There is deliberately no root jail here, matching
# browse_dirs' own trust model: the bridge token is the boundary, and
# forgehub-backend is the one that scopes every path to the calling
# project's working_directory_path before it ever reaches this service
# (see api/routes/project.py's _safe_join).
# ---------------------------------------------------------------------------

_MAX_READABLE_FILE_BYTES = 2 * 1024 * 1024


class FsEntry(BaseModel):
    name: str
    path: str
    type: str  # "file" | "dir"
    size: int | None = None


class FsListResponse(BaseModel):
    path: str
    parent: str | None
    entries: list[FsEntry]


@app.get("/v1/fs/list", response_model=FsListResponse)
async def fs_list(path: str | None = Query(default=None), x_bridge_token: str | None = Header(default=None)) -> FsListResponse:
    _check_token(x_bridge_token)
    target = Path(path).expanduser() if path else Path.home()
    if not target.is_dir():
        raise HTTPException(status_code=404, detail="Not a directory")
    try:
        children = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied") from None

    entries = []
    for entry in children:
        try:
            is_dir = entry.is_dir()
            entries.append(
                FsEntry(
                    name=entry.name,
                    path=str(entry),
                    type="dir" if is_dir else "file",
                    size=None if is_dir else entry.stat().st_size,
                )
            )
        except OSError:
            continue  # broken symlink or similar -- skip rather than 500

    return FsListResponse(
        path=str(target),
        parent=str(target.parent) if target.parent != target else None,
        entries=entries,
    )


class FsContent(BaseModel):
    path: str
    content: str


def _is_probably_binary(data: bytes) -> bool:
    return b"\x00" in data


@app.get("/v1/fs/read", response_model=FsContent)
async def fs_read(path: str = Query(...), x_bridge_token: str | None = Header(default=None)) -> FsContent:
    _check_token(x_bridge_token)
    target = Path(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    size = target.stat().st_size
    if size > _MAX_READABLE_FILE_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large to view ({size} bytes)")
    data = target.read_bytes()
    if _is_probably_binary(data):
        raise HTTPException(status_code=415, detail="File appears to be binary")
    return FsContent(path=str(target), content=data.decode("utf-8", errors="replace"))


class FsWriteRequest(BaseModel):
    path: str
    content: str


@app.put("/v1/fs/write", response_model=FsContent)
async def fs_write(req: FsWriteRequest, x_bridge_token: str | None = Header(default=None)) -> FsContent:
    """Writes (creating the file, and any missing parent dirs, if needed) --
    doubles as the host side of both "save edit" and "create new file"."""
    _check_token(x_bridge_token)
    target = Path(req.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(req.content, encoding="utf-8")
    return FsContent(path=str(target), content=req.content)


class FsPathRequest(BaseModel):
    path: str


@app.post("/v1/fs/mkdir", response_model=FsEntry)
async def fs_mkdir(req: FsPathRequest, x_bridge_token: str | None = Header(default=None)) -> FsEntry:
    _check_token(x_bridge_token)
    target = Path(req.path)
    if target.exists():
        raise HTTPException(status_code=409, detail="Already exists")
    target.mkdir(parents=True)
    return FsEntry(name=target.name, path=str(target), type="dir")


@app.post("/v1/fs/create-file", response_model=FsEntry)
async def fs_create_file(req: FsPathRequest, x_bridge_token: str | None = Header(default=None)) -> FsEntry:
    """Distinct from fs_write: errors (409) if the file already exists,
    since this backs "new file" in the UI, where silently overwriting an
    existing one would be the wrong behavior."""
    _check_token(x_bridge_token)
    target = Path(req.path)
    if target.exists():
        raise HTTPException(status_code=409, detail="Already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch()
    return FsEntry(name=target.name, path=str(target), type="file", size=0)


class FsRenameRequest(BaseModel):
    path: str
    new_path: str


@app.patch("/v1/fs/rename", response_model=FsEntry)
async def fs_rename(req: FsRenameRequest, x_bridge_token: str | None = Header(default=None)) -> FsEntry:
    """Renames or moves -- a plain `Path.rename`, so it also relocates a
    file/dir to a different parent directory if new_path's parent differs
    from path's, same as `mv`."""
    _check_token(x_bridge_token)
    source = Path(req.path)
    dest = Path(req.new_path)
    if not source.exists():
        raise HTTPException(status_code=404, detail="Source not found")
    if dest.exists():
        raise HTTPException(status_code=409, detail="Destination already exists")
    dest.parent.mkdir(parents=True, exist_ok=True)
    source.rename(dest)
    return FsEntry(name=dest.name, path=str(dest), type="dir" if dest.is_dir() else "file")


@app.delete("/v1/fs/delete")
async def fs_delete(
    path: str = Query(...),
    recursive: bool = Query(default=False),
    x_bridge_token: str | None = Header(default=None),
) -> dict:
    _check_token(x_bridge_token)
    target = Path(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Not found")
    if target.is_dir():
        if any(target.iterdir()) and not recursive:
            raise HTTPException(
                status_code=400, detail="Directory not empty (pass recursive=true to delete anyway)"
            )
        shutil.rmtree(target)
    else:
        target.unlink()
    return {"status": "ok"}


class FsChmodRequest(BaseModel):
    path: str
    lock: bool  # True = remove write bits (a-w), False = restore owner write (u+w)


@app.post("/v1/fs/chmod")
async def fs_chmod(req: FsChmodRequest, x_bridge_token: str | None = Header(default=None)) -> dict:
    """Apply or remove write-protection on a path and all its children.

    lock=True  → chmod -R a-w  (read-only for everyone; root can always override)
    lock=False → chmod -R u+w  (restore write for the owner)

    This is a best-effort operation: missing paths are silently skipped so that
    a structure node with a non-existent path doesn't block lock/unlock.
    """
    _check_token(x_bridge_token)
    target = Path(req.path)
    if not target.exists():
        return {"status": "skipped", "reason": "path does not exist"}

    mode_arg = "a-w" if req.lock else "u+w"
    result = subprocess.run(
        ["chmod", "-R", mode_arg, str(target)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"chmod failed: {result.stderr.strip()}",
        )
    return {"status": "ok", "path": str(target), "lock": req.lock}


# ---------------------------------------------------------------------------
# Filesystem tar/untar  (used by the product backup/restore endpoints)
# ---------------------------------------------------------------------------

# Directories commonly excluded from project archives to keep sizes small.
_TAR_EXCLUDES = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache",
    ".pytest_cache", "dist", "build", ".next", ".nuxt", ".turbo", ".parcel-cache",
    "coverage", ".coverage", "htmlcov", "target",
}


def _tar_filter(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo | None:
    """Skip heavy/irrelevant directories during backup."""
    name = Path(tarinfo.name).name
    if name in _TAR_EXCLUDES:
        return None
    return tarinfo


class FsTarRequest(BaseModel):
    path: str


@app.post("/v1/fs/tar")
async def fs_tar(req: FsTarRequest, x_bridge_token: str | None = Header(default=None)) -> dict:
    """Create a compressed tar of a path, return base64-encoded bytes.

    Common heavy directories (.git, node_modules, .venv, …) are excluded
    so that typical code projects remain a manageable download size.
    """
    _check_token(x_bridge_token)
    target = Path(req.path)
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {req.path}")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(str(target), arcname=target.name, filter=_tar_filter)
    raw = buf.getvalue()
    return {
        "status": "ok",
        "archive_b64": base64.b64encode(raw).decode(),
        "size_bytes": len(raw),
    }


class FsUntarRequest(BaseModel):
    path: str          # target directory where archive will be extracted
    archive_b64: str   # base64-encoded tar.gz bytes


@app.post("/v1/fs/untar")
async def fs_untar(req: FsUntarRequest, x_bridge_token: str | None = Header(default=None)) -> dict:
    """Extract a base64-encoded tar.gz into the given directory."""
    _check_token(x_bridge_token)
    target = Path(req.path)
    target.mkdir(parents=True, exist_ok=True)
    raw = base64.b64decode(req.archive_b64)
    buf = io.BytesIO(raw)
    with tarfile.open(fileobj=buf, mode="r:gz") as tar:
        tar.extractall(str(target))
    return {"status": "ok", "path": str(target)}


class HermesBackupRequest(BaseModel):
    source_path: str = "/root/.hermes"
    backup_dir: str = "/root/backup"
    archive_name: str | None = None


@app.post("/v1/system/hermes-backup")
async def create_hermes_backup(
    req: HermesBackupRequest,
    x_bridge_token: str | None = Header(default=None),
) -> dict:
    """Create a compressed backup of /root/.hermes inside /root/backup."""
    _check_token(x_bridge_token)
    source = Path(req.source_path)
    if not source.exists():
        raise HTTPException(status_code=404, detail=f"Source not found: {req.source_path}")
    backup_dir = Path(req.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    # Local time, not UTC -- the filename timestamp is meant to read as the
    # wall-clock moment the backup was taken, not an absolute instant (the
    # only caller passing archive_name explicitly, ForgeHub's System
    # Control, applies the same rule -- see its own comment).
    archive_name = req.archive_name or f"hermes-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.tar.gz"
    archive_path = backup_dir / archive_name
    result = subprocess.run(
        ["tar", "-czf", str(archive_path), "-C", str(source.parent), source.name],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"tar failed: {result.stderr.strip() or result.stdout.strip()}",
        )
    return {
        "status": "ok",
        "source_path": str(source),
        "archive_path": str(archive_path),
        "size_bytes": archive_path.stat().st_size,
    }


# ---------------------------------------------------------------------------
# Docker management endpoints
# ---------------------------------------------------------------------------

_CONTAINER_NAME_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.\-]+$')


class DockerRestartRequest(BaseModel):
    container_name: str


class DockerLogsRequest(BaseModel):
    container_name: str
    lines: int = 100


@app.post("/v1/docker/ps")
async def docker_ps(x_bridge_token: str | None = Header(default=None)) -> dict:
    """List all Docker containers (running and stopped)."""
    _check_token(x_bridge_token)
    result = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{json .}}"],
        capture_output=True, text=True, timeout=15,
    )
    containers = []
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if line:
            try:
                containers.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return {"containers": containers}


@app.post("/v1/docker/restart")
async def docker_restart(
    req: DockerRestartRequest,
    x_bridge_token: str | None = Header(default=None),
) -> dict:
    """Restart a Docker container by name."""
    _check_token(x_bridge_token)
    if not _CONTAINER_NAME_RE.match(req.container_name):
        raise HTTPException(status_code=400, detail="Invalid container name")
    result = subprocess.run(
        ["docker", "restart", req.container_name],
        capture_output=True, text=True, timeout=60,
    )
    return {
        "success": result.returncode == 0,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


@app.post("/v1/docker/rm")
async def docker_rm(
    req: DockerRestartRequest,   # reuse: container_name field
    x_bridge_token: str | None = Header(default=None),
) -> dict:
    """Remove a Docker container by name (forced, works on running containers)."""
    _check_token(x_bridge_token)
    if not _CONTAINER_NAME_RE.match(req.container_name):
        raise HTTPException(status_code=400, detail="Invalid container name")
    result = subprocess.run(
        ["docker", "rm", "-f", req.container_name],
        capture_output=True, text=True, timeout=60,
    )
    return {
        "success": result.returncode == 0,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


@app.post("/v1/docker/logs")
async def docker_logs(
    req: DockerLogsRequest,
    x_bridge_token: str | None = Header(default=None),
) -> dict:
    """Return the last N lines of a container's logs (stdout + stderr combined)."""
    _check_token(x_bridge_token)
    if not _CONTAINER_NAME_RE.match(req.container_name):
        raise HTTPException(status_code=400, detail="Invalid container name")
    result = subprocess.run(
        ["docker", "logs", "--tail", str(min(req.lines, 2000)), req.container_name],
        capture_output=True, text=True, timeout=30,
    )
    return {
        "logs": result.stdout + result.stderr,
        "success": result.returncode == 0,
    }


@app.post("/v1/docker/inspect")
async def docker_inspect(
    req: DockerRestartRequest,   # reuse: container_name field
    x_bridge_token: str | None = Header(default=None),
) -> dict:
    """Return full docker inspect JSON for a single container."""
    _check_token(x_bridge_token)
    if not _CONTAINER_NAME_RE.match(req.container_name):
        raise HTTPException(status_code=400, detail="Invalid container name")
    result = subprocess.run(
        ["docker", "inspect", req.container_name],
        capture_output=True, text=True, timeout=15,
    )
    try:
        data = json.loads(result.stdout)
        return {"inspect": data[0] if data else {}}
    except Exception:
        return {"inspect": {}}


class DockerVolumeRmRequest(BaseModel):
    volume_name: str


@app.post("/v1/docker/volume-rm")
async def docker_volume_rm(
    req: DockerVolumeRmRequest,
    x_bridge_token: str | None = Header(default=None),
) -> dict:
    """Remove a named Docker volume. Fails if the volume is in use."""
    _check_token(x_bridge_token)
    if not _CONTAINER_NAME_RE.match(req.volume_name):
        raise HTTPException(status_code=400, detail="Invalid volume name")
    result = subprocess.run(
        ["docker", "volume", "rm", req.volume_name],
        capture_output=True, text=True, timeout=30,
    )
    return {
        "success": result.returncode == 0,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


@app.post("/v1/docker/volumes")
async def docker_volumes(x_bridge_token: str | None = Header(default=None)) -> dict:
    """List all Docker volumes with inspect details (driver, mountpoint, usage)."""
    _check_token(x_bridge_token)
    ls = subprocess.run(
        ["docker", "volume", "ls", "--format", "{{json .}}"],
        capture_output=True, text=True, timeout=15,
    )
    names = []
    for line in ls.stdout.strip().split("\n"):
        line = line.strip()
        if line:
            try:
                names.append(json.loads(line).get("Name", ""))
            except Exception:
                pass
    names = [n for n in names if n]

    volumes = []
    if names:
        insp = subprocess.run(
            ["docker", "volume", "inspect"] + names,
            capture_output=True, text=True, timeout=30,
        )
        try:
            volumes = json.loads(insp.stdout)
        except Exception:
            volumes = []

    # Map which containers use each volume
    ps = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{json .}}"],
        capture_output=True, text=True, timeout=15,
    )
    container_names = []
    for line in ps.stdout.strip().split("\n"):
        line = line.strip()
        if line:
            try:
                container_names.append(json.loads(line).get("Names", ""))
            except Exception:
                pass

    # Build volume → containers map via inspect of all containers, and
    # collect bind mounts (host folders shared into containers) so they show
    # up alongside named volumes.
    vol_containers: dict[str, list[str]] = {}
    bind_mounts: dict[str, list[str]] = {}
    if container_names:
        ci = subprocess.run(
            ["docker", "inspect"] + container_names,
            capture_output=True, text=True, timeout=30,
        )
        try:
            cdata = json.loads(ci.stdout)
            for c in cdata:
                cname = c.get("Name", "").lstrip("/")
                for m in c.get("Mounts", []):
                    vname = m.get("Name") or m.get("Source", "")
                    if vname:
                        vol_containers.setdefault(vname, []).append(cname)
                    if m.get("Type") == "bind" and m.get("Source"):
                        entry = bind_mounts.setdefault(m["Source"], [])
                        if cname not in entry:
                            entry.append(cname)
        except Exception:
            pass

    result = []
    for v in volumes:
        vname = v.get("Name", "")
        result.append({
            "name": vname,
            "driver": v.get("Driver", ""),
            "mountpoint": v.get("Mountpoint", ""),
            "scope": v.get("Scope", ""),
            "labels": v.get("Labels") or {},
            "containers": vol_containers.get(vname, []),
        })
    for source in sorted(bind_mounts):
        result.append({
            "name": source,
            "driver": "bind",
            "mountpoint": source,
            "scope": "local",
            "labels": {},
            "containers": bind_mounts[source],
        })
    return {"volumes": result}


class DockerNetworkRmRequest(BaseModel):
    network_name: str


@app.post("/v1/docker/network-rm")
async def docker_network_rm(
    req: DockerNetworkRmRequest,
    x_bridge_token: str | None = Header(default=None),
) -> dict:
    """Remove a Docker network. Fails on predefined networks or if in use."""
    _check_token(x_bridge_token)
    if not _CONTAINER_NAME_RE.match(req.network_name):
        raise HTTPException(status_code=400, detail="Invalid network name")
    result = subprocess.run(
        ["docker", "network", "rm", req.network_name],
        capture_output=True, text=True, timeout=30,
    )
    return {
        "success": result.returncode == 0,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


@app.post("/v1/docker/networks")
async def docker_networks(x_bridge_token: str | None = Header(default=None)) -> dict:
    """List all Docker networks with inspect details (driver, subnets, containers)."""
    _check_token(x_bridge_token)
    ls = subprocess.run(
        ["docker", "network", "ls", "--format", "{{json .}}"],
        capture_output=True, text=True, timeout=15,
    )
    names = []
    for line in ls.stdout.strip().split("\n"):
        line = line.strip()
        if line:
            try:
                names.append(json.loads(line).get("Name", ""))
            except Exception:
                pass
    names = [n for n in names if n]

    networks = []
    if names:
        insp = subprocess.run(
            ["docker", "network", "inspect"] + names,
            capture_output=True, text=True, timeout=30,
        )
        try:
            networks = json.loads(insp.stdout)
        except Exception:
            networks = []

    result = []
    for n in networks:
        ipam = n.get("IPAM", {})
        subnets = [
            cfg.get("Subnet", "")
            for cfg in (ipam.get("Config") or [])
            if cfg.get("Subnet")
        ]
        containers = [
            {"name": v.get("Name", k), "ipv4": v.get("IPv4Address", "")}
            for k, v in (n.get("Containers") or {}).items()
        ]
        result.append({
            "id": n.get("Id", "")[:12],
            "name": n.get("Name", ""),
            "driver": n.get("Driver", ""),
            "scope": n.get("Scope", ""),
            "internal": n.get("Internal", False),
            "ipv6": n.get("EnableIPv6", False),
            "subnets": subnets,
            "containers": containers,
        })
    return {"networks": result}


class DockerImageRmRequest(BaseModel):
    ref: str


# Repo:tag references can contain a registry host/port and namespace path
# ("ghcr.io/vectorize-io/hindsight:latest"), unlike container/volume/network
# names -- so this allows "/" and ":" on top of _CONTAINER_NAME_RE's charset.
# Still just a sanity gate: subprocess.run below passes argv as a list (no
# shell), so this isn't a shell-injection control.
_IMAGE_REF_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._\-/:]*$')


@app.post("/v1/docker/image-rm")
async def docker_image_rm(
    req: DockerImageRmRequest,
    x_bridge_token: str | None = Header(default=None),
) -> dict:
    """Remove a Docker image by its "repo:tag" reference (or, for dangling/
    untagged images, by ID).

    Deliberately takes the tag rather than the bare image ID: when two tags
    share the same underlying ID (e.g. one repo re-tagged from another),
    `docker rmi <id>` refuses with "must be forced - image is referenced in
    multiple repositories" -- forcing it would delete every tag at once,
    which is surprising when the user only asked to remove one row. Removing
    by a specific tag only drops that reference; the underlying image stays
    until its last tag is gone.
    """
    _check_token(x_bridge_token)
    if not _IMAGE_REF_RE.match(req.ref):
        raise HTTPException(status_code=400, detail="Invalid image reference")
    result = subprocess.run(
        ["docker", "rmi", req.ref],
        capture_output=True, text=True, timeout=60,
    )
    return {
        "success": result.returncode == 0,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


@app.post("/v1/docker/images")
async def docker_images(x_bridge_token: str | None = Header(default=None)) -> dict:
    """List all Docker images with size/tag info and whether any container
    (running or stopped) currently references them."""
    _check_token(x_bridge_token)
    ls = subprocess.run(
        ["docker", "images", "-a", "--format", "{{json .}}"],
        capture_output=True, text=True, timeout=15,
    )
    images = []
    for line in ls.stdout.strip().split("\n"):
        line = line.strip()
        if line:
            try:
                images.append(json.loads(line))
            except Exception:
                pass

    # Resolve the actual image ID each container was created from (docker ps's
    # own "Image" column is often a tag, not an ID) so it can be matched
    # reliably against `docker images`' short ID column.
    ps = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{json .}}"],
        capture_output=True, text=True, timeout=15,
    )
    container_names = []
    for line in ps.stdout.strip().split("\n"):
        line = line.strip()
        if line:
            try:
                container_names.append(json.loads(line).get("Names", ""))
            except Exception:
                pass

    used_image_ids: set[str] = set()
    if container_names:
        ci = subprocess.run(
            ["docker", "inspect"] + container_names,
            capture_output=True, text=True, timeout=30,
        )
        try:
            cdata = json.loads(ci.stdout)
            for c in cdata:
                image_ref = c.get("Image", "")
                if image_ref:
                    used_image_ids.add(image_ref.split(":")[-1][:12])
        except Exception:
            pass

    result = []
    for img in images:
        image_id = img.get("ID", "")
        repo = img.get("Repository", "")
        tag = img.get("Tag", "")
        result.append({
            "id": image_id,
            "repository": repo,
            "tag": tag,
            "size": img.get("Size", ""),
            "created_since": img.get("CreatedSince", ""),
            "dangling": repo == "<none>" and tag == "<none>",
            "in_use": image_id in used_image_ids,
        })
    return {"images": result}


# ---------------------------------------------------------------------------
# Hindsight memory observability
# ---------------------------------------------------------------------------

HINDSIGHT_PROFILE_DIR = Path.home() / ".hindsight" / "profiles"
HERMES_HOME_DIR = Path.home() / ".hermes"
HERMES_PROFILES_DIR = HERMES_HOME_DIR / "profiles"


def _read_json_file(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_yaml_file(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return values


def _tail_text(path: Path, max_lines: int = 80) -> dict:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        stat = path.stat()
        return {
            "path": str(path),
            "exists": True,
            "updated_at": stat.st_mtime,
            "lines": lines[-max_lines:],
        }
    except OSError:
        return {"path": str(path), "exists": False, "updated_at": None, "lines": []}


def _hindsight_processes() -> list[dict]:
    try:
        proc = subprocess.run(
            ["ps", "-eo", "pid,etimes,cmd"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return []
    rows = []
    for line in proc.stdout.splitlines()[1:]:
        lower = line.lower()
        if "hindsight" not in lower or "rg -i" in lower:
            continue
        parts = line.strip().split(None, 2)
        if len(parts) < 3:
            continue
        command = parts[2]
        command_lower = command.lower()
        if (
            "/api/v1/hindsight/status" in command_lower
            or "/v1/hindsight/status" in command_lower
            or command_lower.startswith("curl ")
        ):
            continue
        rows.append({"pid": parts[0], "uptime_seconds": int(parts[1]), "command": command})
    return rows


async def _probe_hindsight(api_url: str | None) -> dict:
    if not api_url:
        return {"ok": False, "status_code": None, "error": "No api_url configured", "version": None}
    base = api_url.rstrip("/")
    result = {"ok": False, "status_code": None, "error": None, "version": None, "health": None}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            health = await client.get(f"{base}/health")
            result["status_code"] = health.status_code
            result["ok"] = 200 <= health.status_code < 300
            try:
                result["health"] = health.json()
            except Exception:
                result["health"] = health.text[:500]
            try:
                version = await client.get(f"{base}/version")
                if 200 <= version.status_code < 300:
                    result["version"] = version.json()
            except Exception:
                pass
    except Exception as exc:
        result["error"] = str(exc)
    return result


@app.get("/v1/hindsight/status")
async def hindsight_status(x_bridge_token: str | None = Header(default=None)) -> dict:
    """Read-only operational view of Hermes' Hindsight memory provider."""
    _check_token(x_bridge_token)

    profiles = []
    active_profiles = []
    profile_configs = []
    for cfg_path in sorted(HERMES_PROFILES_DIR.glob("*/config.yaml")):
        profile = cfg_path.parent.name
        cfg = _read_yaml_file(cfg_path)
        memory = cfg.get("memory") if isinstance(cfg.get("memory"), dict) else {}
        provider = memory.get("provider")
        hindsight_config_path = cfg_path.parent / "hindsight" / "config.json"
        hindsight_config = _read_json_file(hindsight_config_path)
        uses_hindsight = provider == "hindsight"
        if uses_hindsight:
            active_profiles.append(profile)
        if hindsight_config:
            profile_configs.append(profile)
        profiles.append({
            "profile": profile,
            "uses_hindsight": uses_hindsight,
            "memory_enabled": memory.get("memory_enabled"),
            "user_profile_enabled": memory.get("user_profile_enabled"),
            "write_approval": memory.get("write_approval"),
            "memory_char_limit": memory.get("memory_char_limit"),
            "user_char_limit": memory.get("user_char_limit"),
            "config_path": str(cfg_path),
            "hindsight_config_path": str(hindsight_config_path) if hindsight_config_path.exists() else None,
            "hindsight_configured": bool(hindsight_config),
        })

    # "athos" is Hermes' designated primary/default profile in this
    # install -- pick it deterministically when it's a candidate. Falling
    # back to "first alphabetically" only made sense back when athos was
    # the *only* profile with its own hindsight/config.json; now that
    # every profile has one (see forgehub_dev's config replication,
    # 2026-07-08), that tiebreaker becomes arbitrary (picks "aegis").
    primary_profile = (
        "athos" if "athos" in profile_configs
        else profile_configs[0] if profile_configs
        else "athos" if "athos" in active_profiles
        else active_profiles[0] if active_profiles
        else None
    )
    primary_config_path = (
        HERMES_PROFILES_DIR / primary_profile / "hindsight" / "config.json"
        if primary_profile else None
    )
    config = _read_json_file(primary_config_path) if primary_config_path else {}
    api_url = config.get("api_url") or os.environ.get("HINDSIGHT_API_URL")
    env_path = HINDSIGHT_PROFILE_DIR / f"{primary_profile}.env" if primary_profile else None
    env = _read_env_file(env_path) if env_path else {}

    llm = {
        "provider": config.get("llm_provider") or env.get("HINDSIGHT_API_LLM_PROVIDER"),
        "model": config.get("llm_model") or env.get("HINDSIGHT_API_LLM_MODEL"),
        "base_url": config.get("llm_base_url") or env.get("HINDSIGHT_API_LLM_BASE_URL"),
        "api_key_present": bool(
            config.get("llm_api_key")
            or env.get("HINDSIGHT_API_LLM_API_KEY")
            or os.environ.get("HINDSIGHT_LLM_API_KEY")
        ),
    }

    connection = {
        "mode": config.get("mode") or os.environ.get("HINDSIGHT_MODE") or "cloud",
        "api_url": api_url,
        "timeout": config.get("timeout"),
        "idle_timeout": config.get("idle_timeout") or env.get("HINDSIGHT_EMBED_DAEMON_IDLE_TIMEOUT"),
        "config_path": str(primary_config_path) if primary_config_path and primary_config_path.exists() else None,
        "env_path": str(env_path) if env_path and env_path.exists() else None,
    }
    bank_id = config.get("bank_id") or os.environ.get("HINDSIGHT_BANK_ID") or "hermes"
    banks = config.get("banks") if isinstance(config.get("banks"), dict) else {}
    bank = banks.get(bank_id) if isinstance(banks.get(bank_id), dict) else {}
    memory_flow = {
        "bank_id": bank_id,
        "bank_enabled": bank.get("enabled"),
        "recall_budget": config.get("recall_budget") or bank.get("budget"),
        "auto_recall": config.get("auto_recall", True),
        "auto_retain": config.get("auto_retain", True),
        "retain_async": config.get("retain_async", True),
        "retain_every_n_turns": config.get("retain_every_n_turns", 1),
        "memory_mode": config.get("memory_mode", "hybrid"),
        "retain_tags": config.get("retain_tags"),
        "retain_source": config.get("retain_source"),
    }

    probe = await _probe_hindsight(api_url)
    runtime_log = _tail_text(HINDSIGHT_PROFILE_DIR / f"{primary_profile}.log") if primary_profile else {"exists": False, "lines": []}
    default_log = _tail_text(HINDSIGHT_PROFILE_DIR / "default.log")
    startup_log = _tail_text(HERMES_HOME_DIR / "logs" / "hindsight-embed.log")
    latest_errors = []
    for source, log in (("runtime", runtime_log), ("default", default_log), ("startup", startup_log)):
        for line in log.get("lines", []):
            if any(token in line.lower() for token in ("error", "exception", "failed", "traceback")):
                latest_errors.append({"source": source, "line": line})

    recording_configured = bool(active_profiles) and memory_flow["auto_retain"] is not False
    return {
        "summary": {
            "configured": bool(active_profiles),
            "daemon_active": bool(probe.get("ok")),
            "recording_configured": recording_configured,
            "recording_effective": recording_configured and bool(probe.get("ok")),
            "active_profile_count": len(active_profiles),
            "profile_config_count": len(profile_configs),
            "primary_profile": primary_profile,
        },
        "connection": connection,
        "probe": probe,
        "llm": llm,
        "memory": memory_flow,
        "profiles": profiles,
        "processes": _hindsight_processes(),
        "logs": {
            "runtime": runtime_log,
            "default": default_log,
            "startup": startup_log,
            "latest_errors": latest_errors[-12:] if latest_errors else [],
        },
        "analysis": {
            "storage_source": "Active memory lives in foundation_postgres schema hindsight; ForgeHub should only mirror operational metadata and control state.",
            "database_control_recommendation": "Track daemon health, schema growth, async job status, profile coverage, and policy drift in ForgeHub. Keep raw memory content inside Hindsight unless you need export or indexing.",
            "current_risk": "Profiles without profile-scoped hindsight/config.json inherit defaults or environment and can silently drift from athos.",
        },
    }


def _primary_hindsight_profile() -> str | None:
    """Same primary-profile selection as hindsight_status (profile with its
    own hindsight/config.json wins, else the first active-hindsight
    profile) -- recomputed standalone here rather than refactoring that
    endpoint's larger body."""
    active_profiles, profile_configs = [], []
    for cfg_path in sorted(HERMES_PROFILES_DIR.glob("*/config.yaml")):
        profile = cfg_path.parent.name
        cfg = _read_yaml_file(cfg_path)
        memory = cfg.get("memory") if isinstance(cfg.get("memory"), dict) else {}
        if memory.get("provider") == "hindsight":
            active_profiles.append(profile)
        if _read_json_file(cfg_path.parent / "hindsight" / "config.json"):
            profile_configs.append(profile)
    if "athos" in profile_configs:
        return "athos"
    if profile_configs:
        return profile_configs[0]
    if "athos" in active_profiles:
        return "athos"
    return active_profiles[0] if active_profiles else None


_HINDSIGHT_LOG_TARGETS = {"runtime", "default", "startup"}


@app.post("/v1/hindsight/clear-log")
async def clear_hindsight_log(
    body: dict, x_bridge_token: str | None = Header(default=None)
) -> dict:
    """Truncates one of the log files hindsight_status reads (stale crash
    traces otherwise sit there indefinitely -- these processes don't log-
    rotate on their own)."""
    _check_token(x_bridge_token)
    target = body.get("target")
    if target not in _HINDSIGHT_LOG_TARGETS:
        raise HTTPException(status_code=400, detail=f"target must be one of {sorted(_HINDSIGHT_LOG_TARGETS)}")

    if target == "startup":
        path = HERMES_HOME_DIR / "logs" / "hindsight-embed.log"
    else:
        primary_profile = _primary_hindsight_profile()
        if target == "default" or not primary_profile:
            path = HINDSIGHT_PROFILE_DIR / "default.log"
        else:
            path = HINDSIGHT_PROFILE_DIR / f"{primary_profile}.log"

    if not path.exists():
        return {"success": True, "path": str(path), "cleared": False, "note": "File did not exist"}
    path.write_text("", encoding="utf-8")
    return {"success": True, "path": str(path), "cleared": True}
