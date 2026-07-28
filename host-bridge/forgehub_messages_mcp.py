#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp[cli]>=1.2.0", "httpx>=0.27"]
# ///
"""MCP server exposing ForgeHub's Agent Message channel as tools.

Wraps the bridge-token endpoints of the canonical agent-to-agent
communication mechanism (`POST /api/v1/demands/submit`,
`GET /api/v1/demands/pending`, `GET /api/v1/demands/for-agent`; see
/root/.hermes/foundation/docs/FORGEHUB_MESSAGE.md) so any MCP-capable
runtime can send, list and pull messages as native tool calls, instead of
shelling out to `send_agent_message.sh` / `check_agent_inbox.sh`. Same
channel, same table (`company.agent_demands`), same "Messages" page — this
is a second front door to the existing mechanism, not a parallel one.

Four tools, two of which are read-only:

    send_agent_message    file a note, or address (and dispatch) a message
    list_agent_messages   filter own messages by status; consumes nothing
    get_agent_message     read one in full by #number; consumes nothing
    check_agent_inbox     pull new mail -- pulling IS the acknowledgment

Auth: the shared `CHAT_BRIDGE_TOKEN` (env `FORGEHUB_BRIDGE_TOKEN`, else read
from /root/project/forgehub/.env — the same trust boundary the shell scripts
already use). It is a shared secret, not a per-agent credential: any caller
can post as any `from_agent`, so `FORGEHUB_AGENT_SLUG` below is a convenience
default, not an identity guarantee.

Env:
  FORGEHUB_API_URL     default http://localhost:8000 (the always-on Docker
                       deploy -- deliberately not :8001's ephemeral dev
                       instance, which is only up while someone iterates)
  FORGEHUB_BRIDGE_TOKEN  overrides reading .env
  FORGEHUB_ENV_FILE    where to read CHAT_BRIDGE_TOKEN from
  FORGEHUB_AGENT_SLUG  this runtime's own profile_slug; used as the default
                       agent on every tool, so it never has to name itself
"""
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

BASE_URL = os.environ.get("FORGEHUB_API_URL", "http://localhost:8000").rstrip("/")
ENV_FILE = Path(os.environ.get("FORGEHUB_ENV_FILE", "/root/project/forgehub/.env"))
SELF_SLUG = os.environ.get("FORGEHUB_AGENT_SLUG", "").strip()

mcp = FastMCP("forgehub-messages")


class ForgeHubError(Exception):
    """An error worth showing the model verbatim, already phrased for it."""


def _bridge_token() -> str:
    token = os.environ.get("FORGEHUB_BRIDGE_TOKEN", "").strip()
    if token:
        return token
    try:
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.startswith("CHAT_BRIDGE_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError as exc:
        raise ForgeHubError(f"Cannot read {ENV_FILE} for CHAT_BRIDGE_TOKEN: {exc}") from exc
    raise ForgeHubError(
        f"CHAT_BRIDGE_TOKEN not found in {ENV_FILE} and FORGEHUB_BRIDGE_TOKEN is unset"
    )


async def _call(method: str, path: str, **kwargs: Any) -> Any:
    """One request against ForgeHub, with the token attached and HTTP errors
    turned into a ForgeHubError carrying the API's own `detail`.

    Every tool goes through here: each one used to open its own client and
    repeat the same try/raise_for_status/format dance, which is how the four
    of them drifted into three slightly different error strings.
    """
    async with httpx.AsyncClient(
        base_url=BASE_URL, headers={"X-Bridge-Token": _bridge_token()}, timeout=60.0
    ) as client:
        try:
            response = await client.request(method, path, **kwargs)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text
            try:
                detail = exc.response.json().get("detail", detail)
            except ValueError:
                pass
            raise ForgeHubError(
                f"ForgeHub returned HTTP {exc.response.status_code}: {detail}"
            ) from exc
        except httpx.HTTPError as exc:
            # Connection refused/timeout: the deploy being down is an operator
            # fact, not a tool misuse, and must not read as an empty inbox.
            raise ForgeHubError(f"Could not reach ForgeHub at {BASE_URL}: {exc}") from exc
        return response.json()


def _resolve_agent(agent: str | None) -> str:
    """The profile_slug a call is about -- the explicit argument, else this
    runtime's own. Used for the sender of a message and for whose mail is
    being read; both fail the same way when neither is available."""
    slug = (agent or SELF_SLUG).strip()
    if not slug:
        raise ForgeHubError(
            "No agent: pass the agent explicitly, or set FORGEHUB_AGENT_SLUG "
            "in this MCP server's environment to this agent's profile_slug."
        )
    return slug


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_message(demand: dict[str, Any], *, body: str = "none") -> str:
    """One message as text. `body` is "none", "preview" or "full" -- a listing
    wants a teaser, a single read wants everything, and both want the same
    header so the two views stay recognisably the same object."""
    lines = [
        f"#{demand.get('number', '?')} [{demand.get('origin_type')}] {demand.get('subject')}",
        f"  From: {demand.get('from_agent') or '(unknown)'}",
    ]
    if demand.get("requires_response"):
        lines.append("  Reply expected: yes (a return message routes back to the sender)")
    # Two independent axes: the read/convert lifecycle and the execution one.
    # "not dispatched" is a real state (a plain note), not missing data.
    lines.append(
        f"  Status: {demand.get('status') or '?'}"
        f" | dispatch: {demand.get('dispatch_status') or 'not dispatched'}"
    )
    if demand.get("task_execution_at"):
        lines.append(f"  Executed: {demand['task_execution_at']}")
    if demand.get("scheduled_at"):
        lines.append(f"  Scheduled for: {demand['scheduled_at']}")
    lines.append(f"  Created: {demand.get('created_at')}")
    lines.append(f"  Id: {demand.get('id')}")

    text = demand.get("body") or ""
    if body == "full":
        lines.append("  ---")
        lines.extend(f"  {line}" for line in text.splitlines())
        # "processamento" -- the agent's own output, recorded on this same
        # message when it was dispatched with requires_response=false (see
        # send_agent_message's docstring). Shown separately from body,
        # which stays the original request text.
        if demand.get("dispatch_result"):
            lines.append("  --- Resultado ---")
            lines.extend(f"  {line}" for line in demand["dispatch_result"].splitlines())
    elif body == "preview":
        flat = text.strip().replace("\n", " ")
        lines.append(f"  Preview: {flat[:160]}{'…' if len(flat) > 160 else ''}")
    return "\n".join(lines)


@mcp.tool()
async def send_agent_message(
    subject: str,
    body: str,
    to_agent: str | None = None,
    from_agent: str | None = None,
    requires_response: bool = False,
    scheduled_at: str | None = None,
    origin_task_number: int | None = None,
) -> str:
    """Send a message through ForgeHub's Agent Message channel (the canonical
    agent-to-agent communication mechanism of the Hermes ecosystem).

    Two distinct uses:
    - **Note** (no `to_agent`): files a note/discovery/"look at this later"
      for the operator to triage on the Messages page. Nothing executes.
    - **Message to another agent** (`to_agent` set): the recipient's CLI is
      really dispatched with this body as its prompt, automatically — by
      default scheduled for now and picked up by the backend's dispatch loop
      within ~30s, with no human involved. Set `requires_response=True` when
      you want a real return message once the recipient finishes — it lands
      in your own inbox (read it later with `check_agent_inbox`), sent from
      the recipient back to you, body = the recipient's own output. Default
      is `False`: the recipient's output is still recorded (as this
      message's own `dispatch_result`, visible via `get_agent_message`), but
      no second message is created — "só processamento".

    Args:
        subject: 1-255 chars, the message subject.
        body: markdown. When `to_agent` is set this text IS the prompt the
            recipient agent executes — write it as an instruction, self
            contained, since the recipient sees no other context.
        to_agent: recipient's profile_slug (athos, atlas, themis, aegis,
            hephaestus, mnemosyne, scriba, daedalus, kairos, porthos, aramis,
            dartan, vector). Omit to file a plain note instead.
        from_agent: sender label; defaults to this runtime's own slug.
        requires_response: create a real return message once the recipient
            finishes, instead of only recording the result on this message.
        scheduled_at: ISO-8601 datetime to defer dispatch (e.g.
            "2026-07-28T14:00:00-03:00"). Only meaningful with `to_agent`;
            omit to dispatch now.
        origin_task_number: Kanboard task number this came from (a label,
            no referential integrity).

    Prefer this over a tracked Kanboard task for a direct handoff or request
    that doesn't need ownership and a lifecycle.
    """
    try:
        sender = _resolve_agent(from_agent)
        if scheduled_at and not to_agent:
            raise ForgeHubError(
                "scheduled_at only applies to a message addressed to an agent (set to_agent)."
            )

        payload: dict[str, Any] = {
            "from_agent": sender,
            "subject": subject,
            "body": body,
            "requires_response": requires_response,
            # Default Tipo for every MCP-created message is Task (2026-07-28,
            # Marcelo: "criação MCP padrão é task") -- a plain note with no
            # to_agent still lands as Task here, but the backend's own
            # _reconcile_task_origin (demand.py) silently downgrades any
            # Task with no target_agent_id to Backlog, so this never needs a
            # branch for the no-to_agent case. Tipo is mandatory now (no
            # None/"demand" values left, see FORGEHUB_MESSAGE.md).
            "origin_type": "task",
        }
        if to_agent:
            payload["target_agent_slug"] = to_agent
            # Automatic communication: a message addressed to an agent
            # dispatches now unless the caller deliberately deferred it --
            # matches send_agent_message.sh, so both front doors act alike.
            payload["scheduled_at"] = scheduled_at or _utc_now_iso()
        if origin_task_number is not None:
            payload["origin_number"] = origin_task_number

        demand = await _call("POST", "/api/v1/demands/submit", json=payload)
    except ForgeHubError as exc:
        return str(exc)

    lines = [f"Sent message #{demand.get('number')} ({demand.get('id')}) as {sender!r}."]
    if to_agent:
        lines.append(
            f"Addressed to {to_agent!r} and scheduled for {payload['scheduled_at']} — "
            "the backend dispatch loop runs the recipient's CLI (poll ~30s)."
        )
        if requires_response:
            lines.append(
                f"Its reply will land in {sender!r}'s inbox; read it with check_agent_inbox."
            )
    else:
        lines.append(
            "Filed as a note for the operator to triage on the Messages page (nothing dispatched)."
        )
    return "\n".join(lines)


@mcp.tool()
async def list_agent_messages(
    status: str | None = None,
    dispatch_status: str | None = None,
    direction: str = "all",
    agent: str | None = None,
    limit: int = 20,
) -> str:
    """List this agent's messages by status, newest first, **without consuming
    them** — unlike `check_agent_inbox`, which is a queue and permanently marks
    whatever it returns as delivered. Use this one to check state (did the
    message I sent finish? did anything fail?) and to re-read what an inbox
    pull already handed over; use `check_agent_inbox` only when you intend to
    take delivery of new mail.

    Bodies are truncated here; read one in full with `get_agent_message`.

    Args:
        status: the read/convert lifecycle — "new", "read", "converted" or
            "archived". Omit for any.
        dispatch_status: the execution lifecycle — "pending", "dispatched",
            "running", "completed", "failed", or "none" for messages that
            were never dispatched at all (a plain note, or one still waiting
            on a target). Omit for any.
        direction: "outgoing" (sent by this agent), "incoming" (addressed to
            it), or "all".
        agent: whose messages to list; defaults to this runtime's own slug.
        limit: max messages to return (1-200, default 20).
    """
    try:
        slug = _resolve_agent(agent)
        params: dict[str, Any] = {"agent": slug, "direction": direction, "limit": limit}
        if status:
            params["status_filter"] = status
        if dispatch_status:
            params["dispatch_status"] = dispatch_status
        messages = await _call("GET", "/api/v1/demands/for-agent", params=params)
    except ForgeHubError as exc:
        return str(exc)

    if not messages:
        return f"No messages for {slug!r} matching that filter."
    parts = [f"{len(messages)} message(s) for {slug!r} (newest first, nothing consumed):"]
    parts.extend(_format_message(item, body="preview") for item in messages)
    return "\n\n".join(parts)


@mcp.tool()
async def get_agent_message(number: int, agent: str | None = None) -> str:
    """Read one of this agent's own messages in full, by its number (#N), with
    no side effect. Only messages this agent sent or received are visible.
    """
    try:
        slug = _resolve_agent(agent)
        messages = await _call(
            "GET",
            "/api/v1/demands/for-agent",
            params={"agent": slug, "number": number, "limit": 1},
        )
    except ForgeHubError as exc:
        return str(exc)

    if not messages:
        return f"No message #{number} sent to or from {slug!r}."
    return _format_message(messages[0], body="full")


@mcp.tool()
async def check_agent_inbox(agent: str | None = None) -> str:
    """Pull this agent's unread messages from the ForgeHub Agent Message channel.

    Returns every message addressed to `agent` that it has not been handed
    yet, including replies routed back from messages it sent with
    `requires_response=True`.

    **Pulling IS the acknowledgment**: each message is stamped as processed in
    the same call and will never be returned again. Act on what you get in
    this turn — there is no way to re-read it here afterwards (it stays
    visible to a human on ForgeHub's Messages page, and to
    `list_agent_messages`).

    Args:
        agent: profile_slug whose inbox to read; defaults to this runtime's
            own slug. Reading another agent's inbox consumes their mail —
            don't pass this unless you mean to.
    """
    try:
        slug = _resolve_agent(agent)
        pending = await _call("GET", "/api/v1/demands/pending", params={"agent": slug})
    except ForgeHubError as exc:
        return str(exc)

    if not pending:
        return f"No pending messages for {slug!r}."
    parts = [f"{len(pending)} pending message(s) for {slug!r} (now marked as delivered):"]
    parts.extend(_format_message(item, body="full") for item in pending)
    return "\n\n".join(parts)


if __name__ == "__main__":
    mcp.run()
