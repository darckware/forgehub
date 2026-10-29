"""Integration stub for the isolated test environment (Plano Integrado T.3, 2026-10-29).

One small HTTP service, `forgehub_test_stubs` (172.25.0.13:8900 inside
forgehub_test_network; 127.0.0.1:8003 through forgehub_test_gateway), stands in
for every external integration a test backend could reach. Under
ENVIRONMENT=test the backend's integration URLs can only point here (see
app/core/test_integration_policy.py), so no route knows it is talking to a stub.

Each integration has its own path prefix:

- ``/v1/...`` -- the host-bridge. Simulated: ``/v1/agent-runs`` (a run that
  never executes anything and finishes at once), ``/v1/messages/send``
  (Telegram and every cross-channel message: nothing is sent), ``/v1/servers/*``
  for fictitious targets only (RFC 5737 / ``.test``; a client's or production
  host is refused). Refused: ``/v1/exec``, ``/v1/fs/*``, ``/v1/remote-fs/*``,
  ``/v1/forgevault/*`` (ForgeVault: no secret exists here) and everything else.
- ``/darckware/api/internal/{agent|approver}/...`` -- Darckware. Clients are the
  seed's two fictitious ones; an e-mail is queued in memory and never sent, even
  when approved.
- ``/forgerouter/...`` -- ForgeRouter: a fixed chat completion, SSO refused.
- ``/tailscale/...``, ``/weather/...`` -- refused.

Every call is recorded -- integration, operation, destination, time, outcome --
as one JSON line in ``calls.jsonl`` on the stub's own volume, and listed by
``GET /_stub/calls``. Never recorded: bodies, message or e-mail text, prompts,
query strings, tokens. A destination is an address (a Telegram chat id, an
e-mail recipient, a host), all fictitious in the test data.

Credentials are checked against the test's own (test-env/.env.test): the
bridge's X-Bridge-Token against CHAT_BRIDGE_TOKEN, Darckware's Bearer against
the agent/approver token of the path, ForgeRouter's Bearer against
FORGEROUTER_TEST_API_KEY (which must also carry the ``frtest_`` prefix). A call
with any other token -- a production one -- is answered 401 and recorded as
``auth=rejected``; the value is never recorded.
"""
from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.test_integration_policy import (
    FORGEROUTER_TEST_KEY_PREFIX,
    check_test_credential,
    is_fictitious_host,
)
from app.scripts.seed_test_database import CLIENTS, seed_id

#: Swapped by tests for a temporary file. The container mounts its volume here.
LOG_PATH = Path("/stub-log/calls.jsonl")

STUB_ADAPTER_VERSION = "forgehub-test-stub"
STUB_RUN_OUTPUT = "[forgehub test stub] simulated run: no agent was started.\nSTATUS: DONE"

_lock = threading.Lock()
_runs: dict[str, dict[str, Any]] = {}
_emails: dict[str, dict[str, Any]] = {}

app = FastAPI(title="ForgeHub test integration stub", docs_url=None, redoc_url=None, openapi_url=None)


# --- recording ---------------------------------------------------------------


def record(
    integration: str,
    request: Request,
    *,
    operation: str,
    outcome: str,
    status: int,
    destination: str | None = None,
    auth: str | None = None,
) -> None:
    entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "integration": integration,
        "method": request.method,
        "path": request.url.path,  # never the query string
        "operation": operation,
        "destination": destination,
        "outcome": outcome,  # "stubbed" | "refused" | "unauthorized" | "not_found"
        "status": status,
        "auth": auth,  # "test" | "rejected" | "missing" | None (not checked)
    }
    line = json.dumps(entry, ensure_ascii=False)
    with _lock:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def read_calls() -> list[dict[str, Any]]:
    with _lock:
        if not LOG_PATH.is_file():
            return []
        lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _reply(
    integration: str, request: Request, status: int, body: Any, *, operation: str, outcome: str,
    destination: str | None = None, auth: str | None = None,
) -> JSONResponse:
    record(integration, request, operation=operation, outcome=outcome, status=status,
           destination=destination, auth=auth)
    return JSONResponse(status_code=status, content=body)


def _refuse(integration: str, request: Request, operation: str, reason: str, *,
            destination: str | None = None, auth: str | None = None, status: int = 403) -> JSONResponse:
    return _reply(integration, request, status, {"detail": f"forgehub test stub: {reason}"},
                  operation=operation, outcome="refused", destination=destination, auth=auth)


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization") or ""
    return (header.removeprefix("Bearer ").strip() or None) if header.startswith("Bearer ") else None


async def _json(request: Request) -> Any:
    try:
        return await request.json()
    except ValueError:
        return {}


# --- observability -----------------------------------------------------------


@app.get("/_stub/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "adapter_version": STUB_ADAPTER_VERSION}


@app.get("/_stub/calls")
async def list_calls(integration: str | None = None, since: str | None = None) -> dict[str, Any]:
    """What every stub received, oldest first. `since` is an ISO timestamp."""
    calls = read_calls()
    if integration:
        calls = [c for c in calls if c["integration"] == integration]
    if since:
        calls = [c for c in calls if c["at"] > since]
    return {"total": len(calls), "calls": calls}


# --- host-bridge -------------------------------------------------------------


def _hosts_in(body: Any) -> list[str]:
    """Every machine address a /v1/servers/* body names (`host`, `ip_address`,
    nested lists such as check-status' `servers`)."""
    found: list[str] = []
    if isinstance(body, dict):
        for key, value in body.items():
            if key in ("host", "ip_address", "hostname") and isinstance(value, str):
                found.append(value)
            elif isinstance(value, (dict, list)):
                found.extend(_hosts_in(value))
    elif isinstance(body, list):
        for item in body:
            found.extend(_hosts_in(item))
    return found


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def host_bridge(path: str, request: Request):
    integration = "host-bridge"
    auth = check_test_credential(request.headers.get("x-bridge-token"), settings.CHAT_BRIDGE_TOKEN)
    if auth != "test":
        return _reply(integration, request, 401, {"detail": "invalid bridge token"},
                      operation=path, outcome="unauthorized", auth=auth)
    body = await _json(request) if request.method in ("POST", "PUT", "PATCH") else {}

    if path == "agent-runs" and request.method == "POST":
        run_id = str(body.get("run_id") or "")
        runtime = body.get("runtime_type") or "?"
        destination = f"{runtime}:{body.get('hermes_profile') or ''}".rstrip(":")
        try:
            uuid.UUID(run_id)
        except ValueError:
            return _refuse(integration, request, "agent_run.start", "run_id must be a UUID",
                           destination=destination, auth=auth, status=400)
        now = datetime.now(timezone.utc).isoformat()
        with _lock:
            if run_id in _runs:
                return _refuse(integration, request, "agent_run.start", "run_id already exists",
                               destination=destination, auth=auth, status=409)
            _runs[run_id] = {
                "run_id": run_id, "runtime_type": runtime, "mode": body.get("mode"),
                "project_path": body.get("project_path"), "status": "completed",
                "started_at": now, "finished_at": now, "exit_code": 0,
                "output": STUB_RUN_OUTPUT, "error": "", "adapter_version": STUB_ADAPTER_VERSION,
                "heartbeat_at": now,
            }
        return _reply(integration, request, 202,
                      {"run_id": run_id, "status": "running", "runtime_type": runtime, "pid": 0,
                       "adapter_version": STUB_ADAPTER_VERSION},
                      operation="agent_run.start", outcome="stubbed", destination=destination, auth=auth)
    if path == "agent-runs/health":
        adapters = {name: {"available": True, "stub": True} for name in ("claude", "codex", "agy", "hermes")}
        return _reply(integration, request, 200, {"status": "ok", "adapters": adapters, "stub": True},
                      operation="agent_run.health", outcome="stubbed", auth=auth)
    if path.startswith("agent-runs/"):
        run_id, _, action = path[len("agent-runs/"):].partition("/")
        with _lock:
            run = _runs.get(run_id)
            if run is not None and action == "cancel":
                run["status"] = run["status"] if run["status"] == "completed" else "cancelled"
            snapshot = dict(run) if run else None
        if snapshot is None:
            return _reply(integration, request, 404, {"detail": "run not found"},
                          operation=f"agent_run.{action or 'get'}", outcome="not_found", auth=auth)
        return _reply(integration, request, 200, snapshot, operation=f"agent_run.{action or 'get'}",
                      outcome="stubbed", destination=snapshot["runtime_type"], auth=auth)

    if path == "messages/send" and request.method == "POST":
        target = str(body.get("target") or "")
        profile = body.get("profile")
        platform, _, chat_id = target.partition(":")
        destination = target + (f" via {profile}" if profile else "")
        return _reply(integration, request, 200,
                      {"success": True, "stub": True, "platform": platform, "chat_id": chat_id or None,
                       "message_id": f"stub-{uuid.uuid4().hex[:12]}",
                       "note": "forgehub test stub: nothing was sent"},
                      operation=f"message.send.{platform or 'unknown'}", outcome="stubbed",
                      destination=destination, auth=auth)

    if path.startswith("servers/"):
        operation = f"servers.{path[len('servers/'):]}"
        hosts = _hosts_in(body)
        destination = ",".join(hosts) or None
        real = [h for h in hosts if not is_fictitious_host(h)]
        if real or not hosts:
            reason = (f"{', '.join(real)} is not a fictitious test target (RFC 5737 / .test)"
                      if real else "no target host in the request")
            return _refuse(integration, request, operation, reason, destination=destination, auth=auth)
        if path == "exec":
            result: dict[str, Any] = {"exit_code": 0, "stdout": "[forgehub test stub] nothing ran",
                                      "stderr": "", "stub": True}
        elif path == "check-status":
            entries = body.get("servers") or []
            result = {"statuses": {str(e.get("id")): "offline" for e in entries if isinstance(e, dict)},
                      "stub": True}
        else:
            result = {"ok": True, "stub": True}
        return _reply(integration, request, 200, result, operation=operation, outcome="stubbed",
                      destination=destination, auth=auth)

    family = path.split("/", 1)[0]
    if family == "forgevault":
        return _refuse("forgevault", request, f"forgevault.{path[len('forgevault/'):]}",
                       "ForgeVault is not available in the test environment (no secret exists here)", auth=auth)
    return _refuse(integration, request, path, f"host-bridge /v1/{path} is not simulated in the test environment",
                   auth=auth)


# --- Darckware ---------------------------------------------------------------


def _clients() -> list[dict[str, Any]]:
    return [{"id": str(seed_id("client", key)), "company_name": name, "active": True,
             "contract": None, "stub": True} for key, name in CLIENTS]


@app.api_route("/darckware/api/internal/{credential}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def darckware(credential: str, path: str, request: Request):
    integration = "darckware"
    expected = {"agent": settings.DARCKWARE_AGENT_TOKEN, "approver": settings.DARCKWARE_APPROVER_TOKEN}.get(credential)
    if expected is None:
        return _refuse(integration, request, path, f"unknown credential path {credential!r}", status=404)
    auth = check_test_credential(_bearer(request), expected)
    if auth != "test":
        return _reply(integration, request, 401, {"detail": "invalid token"},
                      operation=path, outcome="unauthorized", auth=auth)
    body = await _json(request) if request.method in ("POST", "PUT", "PATCH") else {}
    segments = [s for s in path.split("/") if s]
    op = f"{credential}.{request.method.lower()}.{segments[0] if segments else ''}"

    if segments == ["clients"] and request.method == "GET":
        clients = _clients()
        return _reply(integration, request, 200, {"items": clients, "total": len(clients)}, operation=op,
                      outcome="stubbed", auth=auth)
    if len(segments) >= 2 and segments[0] == "clients" and request.method == "GET":
        client = next((c for c in _clients() if c["id"] == segments[1]), None)
        if client is None:
            return _reply(integration, request, 404, {"detail": "client not found"}, operation=op,
                          outcome="not_found", auth=auth)
        return _reply(integration, request, 200, client, operation=op, outcome="stubbed",
                      destination=client["company_name"], auth=auth)

    if segments and segments[0] == "outbound-emails":
        if len(segments) == 1 and request.method == "POST":
            content = body.get("body_text") or body.get("body") or ""
            text = f"{body.get('subject') or ''}\n{content}"
            email = {
                "id": str(uuid.uuid4()), "to_email": body.get("to_email"), "kind": body.get("kind"),
                "subject": body.get("subject"), "body_text": content,
                "client_account_id": body.get("client_account_id"), "version": 1,
                "status": "aguardando_aprovacao",
                "body_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "created_at": datetime.now(timezone.utc).isoformat(), "stub": True,
            }
            with _lock:
                _emails[email["id"]] = email
            return _reply(integration, request, 201, email, operation="email.queue", outcome="stubbed",
                          destination=email["to_email"], auth=auth)
        if len(segments) == 1 and request.method == "GET":
            with _lock:
                items = list(_emails.values())
            wanted = request.query_params.get("status")
            if wanted:
                items = [e for e in items if e["status"] in wanted.split(",")]
            pending = {"aguardando_aprovacao": sum(1 for e in _emails.values() if e["status"] == "aguardando_aprovacao")}
            return _reply(integration, request, 200, {"items": items, "total": len(items), "pending": pending},
                          operation="email.list", outcome="stubbed", auth=auth)
        with _lock:
            email = _emails.get(segments[1]) if len(segments) >= 2 else None
        if email is None:
            return _reply(integration, request, 404, {"detail": "e-mail not found"}, operation="email.get",
                          outcome="not_found", auth=auth)
        action = segments[2] if len(segments) >= 3 else None
        with _lock:
            if action == "approve":
                email["status"] = "aprovado"  # the stub never sends, approved or not
                email["approved_hash"] = email["body_hash"]
            elif action in ("reject", "cancel"):
                email["status"] = "rejeitado" if action == "reject" else "cancelado"
            elif action == "hide":
                email["hidden_at"] = datetime.now(timezone.utc).isoformat()
            elif request.method == "PATCH":
                email.update({k: body[k] for k in ("subject", "body_text", "to_email") if k in body})
                email["version"] += 1
                email.pop("approved_hash", None)
                email["status"] = "aguardando_aprovacao"
            snapshot = dict(email)
        return _reply(integration, request, 200, snapshot, operation=f"email.{action or request.method.lower()}",
                      outcome="stubbed", destination=snapshot["to_email"], auth=auth)

    if request.method == "GET":
        if len(segments) >= 2:
            return _reply(integration, request, 404, {"detail": "not found in the test stub"}, operation=op,
                          outcome="not_found", auth=auth)
        return _reply(integration, request, 200, {"items": [], "total": 0}, operation=op, outcome="stubbed",
                      auth=auth)
    return _reply(integration, request, 200, {"id": str(uuid.uuid4()), "status": "ok", "stub": True},
                  operation=op, outcome="stubbed", auth=auth)


# --- ForgeRouter / Tailscale / weather -------------------------------------------


@app.api_route("/forgerouter/{path:path}", methods=["GET", "POST"])
async def forgerouter(path: str, request: Request):
    integration = "forgerouter"
    if path == "v1/chat/completions" and request.method == "POST":
        # Only the test key: FORGEROUTER_TEST_API_KEY of .env.test, frtest_ prefix.
        auth = check_test_credential(_bearer(request), settings.FORGEROUTER_TEST_API_KEY,
                                     prefix=FORGEROUTER_TEST_KEY_PREFIX)
        if auth != "test":
            return _reply(integration, request, 401, {"detail": "invalid API key"}, operation="chat.completions",
                          outcome="unauthorized", auth=auth)
        body = await _json(request)
        return _reply(integration, request, 200, {
            "id": f"stub-{uuid.uuid4().hex[:12]}", "object": "chat.completion", "model": body.get("model"),
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": "[forgehub test stub] simulated completion"}}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }, operation="chat.completions", outcome="stubbed", destination=body.get("model"), auth=auth)
    return _refuse(integration, request, path, f"ForgeRouter /{path} is not simulated in the test environment")


@app.api_route("/tailscale/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def tailscale(path: str, request: Request):
    return _refuse("tailscale", request, path, "the Tailscale API is not available in the test environment")


@app.api_route("/weather/{path:path}", methods=["GET"])
@app.api_route("/weather", methods=["GET"])
async def weather(request: Request, path: str = ""):
    return _refuse("weather", request, path or "forecast", "weather services are not available in the test environment")
