#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp[cli]>=1.2.0,<2", "httpx>=0.27"]
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

Seven tools, five of which are read-only:

    send_agent_message     file a note, or address (and dispatch) a message
    list_agent_messages    filter own messages by status; consumes nothing
    get_agent_message      read one in full by #number; consumes nothing
    check_agent_inbox      pull new mail -- pulling IS the acknowledgment
    list_channel_members   who's in a Software Factory channel, and their role
    propose_channel_task   propose a task for yourself or a channel-mate
    list_agent_skills      one agent's declared function and granted skills

The middle two wrap the ChatChannel domain (`POST/GET /api/v1/channels/...`,
see backend/app/db/models/channel.py and
docs/architecture/CHANNEL_AGENT_ROLES_AND_ORCHESTRATION.md) -- a different
domain than the letter-model Messages above, added to this same
already-installed server so no agent needs any new MCP configuration to use
them (2026-08-05, Marcelo: "Agentes podem propor tarefas para colegas, mas
ficam pendentes de validação sua"). Deciding a proposed task (approve/reject)
is deliberately NOT a tool here -- it's the existing Governance domain's own
decision, either Marcelo through the UI or a delegated orchestrator-agent
calling POST /api/v1/governance/approvals/{id}/approve directly with its own
agt_ credential. list_agent_skills (2026-08-06) wraps the Agent domain's own
skills endpoints (`GET /api/v1/agents/{id}/skills`, `GET
/api/v1/agents/skills`) the same read-only way -- it does not create,
install or grant anything; requesting a missing skill still goes through a
human (or delegated orchestrator) via the channel, same as any other
proposal.

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
from datetime import datetime, timedelta, timezone
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
    development_request_id: str | None = None,
    channel: str | None = None,
    channel_ref: str | None = None,
) -> str:
    """Send a message through ForgeHub's Agent Message channel (the canonical
    agent-to-agent communication mechanism of the Hermes ecosystem).

    Two distinct uses:
    - **Note** (no `to_agent`): files a note/discovery/"look at this later"
      for the operator to triage on the Messages page. Nothing executes.
    - **Message to another agent** (`to_agent` set): the recipient's CLI is
      really dispatched with this body as its prompt, automatically — by
      default scheduled for now and signalled to the backend's dispatch
      worker immediately, with no human involved. Set `requires_response=True` when
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
            hephaestus, mnemosyne, scriba, daedalus, kairos, porthus, aramis,
            dartan, vector). Omit to file a plain note instead.
            NOTE: the Claude Code agent's slug is "porthus", not "porthos" --
            the two names differ by one letter and are easy to confuse, but
            only "porthus" resolves; "porthos" 404s.
        from_agent: sender label; defaults to this runtime's own slug.
        channel: **the medium the request reached you through**, when you are
            passing on work someone else asked for: "telegram", "workspace",
            "assistant", "factory" or "agent". Set it whenever a human asked
            you for something somewhere and you are delegating it — without
            it the result has no way back to them and dies in ForgeHub.
        channel_ref: the concrete address to answer at within that medium --
            for Telegram, preferably the chat_id the request came from. The
            destination bot/agent name (for example ``HermesAtlas2bot`` or
            ``Atlas``) is also accepted as an alias for that profile's
            configured home channel.
        requires_response: create a real return message once the recipient
            finishes, instead of only recording the result on this message.
        scheduled_at: ISO-8601 datetime to defer dispatch (e.g.
            "2026-07-28T14:00:00-03:00"). Only meaningful with `to_agent`;
            omit to dispatch now.
        origin_task_number: ForgeHub task number (ProjectTask.number) this
            came from.
        development_request_id: DevelopmentRequest UUID for a pre-project
            Software Factory conception. The link remains valid after a
            Project and Task are created.

    Prefer this over a tracked task for a direct handoff or request that
    doesn't need ownership and a lifecycle.
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
            # to_agent is self-addressed by the backend when this runtime's
            # From agent resolves to a registered agent. If the sender also
            # cannot be resolved, reconciliation safely leaves the item in
            # Incubation. Tipo is mandatory now (no None/"demand" values).
            "origin_type": "task",
        "channel": channel,
        "channel_ref": channel_ref,
        }
        if to_agent:
            payload["target_agent_slug"] = to_agent
            # Automatic communication: a message addressed to an agent
            # dispatches now unless the caller deliberately deferred it --
            # matches send_agent_message.sh, so both front doors act alike.
            payload["scheduled_at"] = scheduled_at or _utc_now_iso()
        if origin_task_number is not None:
            payload["origin_number"] = origin_task_number
        if development_request_id is not None:
            payload["development_request_id"] = development_request_id

        demand = await _call("POST", "/api/v1/demands/submit", json=payload)
    except ForgeHubError as exc:
        return str(exc)

    lines = [f"Sent message #{demand.get('number')} ({demand.get('id')}) as {sender!r}."]
    if to_agent:
        lines.append(
            f"Addressed to {to_agent!r} and scheduled for {payload['scheduled_at']} — "
            "the backend wakes its dispatch worker immediately to run the recipient's CLI."
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
        dispatch_status: the execution lifecycle — "dispatched", "running",
            "completed", "failed", or "none" for messages that
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


async def _own_message_id(slug: str, number: int) -> str:
    """The demand id behind a human-typed #number, restricted to what this
    agent actually sent -- write routes take an id, people type numbers.
    Mirrors _own_incubation_id below, for ordinary (non-incubation) mail."""
    items = await _call(
        "GET",
        "/api/v1/demands/for-agent",
        params={"agent": slug, "number": number, "direction": "outgoing", "limit": 1},
    )
    if not items:
        raise ForgeHubError(
            f"No message #{number} sent by {slug!r}. You can only edit/archive mail you sent."
        )
    return items[0]["id"]


@mcp.tool()
async def update_agent_message(
    number: int,
    subject: str | None = None,
    body: str | None = None,
    to_agent: str | None = None,
    requires_response: bool | None = None,
    agent: str | None = None,
) -> str:
    """Edit a message you sent, by its number (#N).

    Closes the write half of the channel: the read tools above
    (`list_agent_messages`/`get_agent_message`/`check_agent_inbox`) already
    let you look at any agent's mail by passing its slug, but there was no
    way to change one at all except the human-only ForgeHub web UI. Writing
    stays scoped to your own outgoing mail -- editing something another
    agent sent is out of scope, same ownership line `receive_incubation`/
    `drop_incubation` already draw for incubation.

    Args:
        number: the message's #number (see list_agent_messages/check_agent_inbox).
        subject: new subject, if changing it.
        body: new body, if changing it.
        to_agent: re-address it to a different agent's profile_slug, or ""
            to clear the target entirely. Leave unset to keep the current one.
        requires_response: change whether a reply comes back once dispatched.
        agent: your own profile_slug; defaults to this runtime's own.
    """
    try:
        slug = _resolve_agent(agent)
        demand_id = await _own_message_id(slug, number)
        payload: dict[str, Any] = {"agent": slug}
        if subject is not None:
            payload["subject"] = subject
        if body is not None:
            payload["body"] = body
        if to_agent is not None:
            payload["target_agent"] = to_agent or None
        if requires_response is not None:
            payload["requires_response"] = requires_response
        result = await _call("PATCH", f"/api/v1/demands/{demand_id}/agent", json=payload)
    except ForgeHubError as exc:
        return str(exc)
    return f"Updated #{number}.\n\n{_format_message(result, body='full')}"


@mcp.tool()
async def archive_agent_message(number: int, agent: str | None = None) -> str:
    """Archive a message you sent, by its number (#N) -- files it under
    Arquivadas without deleting it. Only the sender can archive it; a
    message someone else sent you is not yours to file away.

    Args:
        number: the message's #number.
        agent: your own profile_slug; defaults to this runtime's own.
    """
    try:
        slug = _resolve_agent(agent)
        demand_id = await _own_message_id(slug, number)
        result = await _call("POST", f"/api/v1/demands/{demand_id}/agent-archive", params={"agent": slug})
    except ForgeHubError as exc:
        return str(exc)
    return f"Archived #{number}.\n\n{_format_message(result, body='preview')}"


@mcp.tool()
async def list_my_incubation(agent: str | None = None, limit: int = 20) -> str:
    """List the thoughts parked for THIS agent to decide on — its incubation.

    Incubation is where an idea waits to mature until you either take it on
    (`receive_incubation`) or decline it (`drop_incubation`). It is not work
    yet and never runs on its own. Distinct from the project backlog, which
    is version planning and lives elsewhere in ForgeHub entirely.

    Only what YOU own is listed: a thought addressed to you is yours to
    decide, even if someone else wrote it. Nothing is consumed by looking.

    Args:
        agent: whose incubation to list; defaults to this runtime's own slug.
        limit: max thoughts to return (1-200, default 20).
    """
    try:
        slug = _resolve_agent(agent)
        items = await _call(
            "GET",
            "/api/v1/demands/for-agent",
            params={
                "agent": slug,
                "origin_type": "incubation",
                "owned_only": True,
                "limit": limit,
            },
        )
    except ForgeHubError as exc:
        return str(exc)

    if not items:
        return f"Nothing incubating for {slug!r}."
    parts = [
        f"{len(items)} thought(s) incubating for {slug!r} — "
        f"receive_incubation(number) to take one on, drop_incubation(number, reason) to decline:"
    ]
    for item in items:
        matures = item.get("matures_at") or "—"
        parts.append(f"{_format_message(item, body='preview')}\nDecide by: {matures}")
    return "\n\n".join(parts)


async def _own_incubation_id(slug: str, number: int) -> str:
    """The demand id behind a human-typed #number, restricted to what this
    agent owns -- the decision routes take an id, people type numbers."""
    items = await _call(
        "GET",
        "/api/v1/demands/for-agent",
        params={
            "agent": slug,
            "number": number,
            "origin_type": "incubation",
            "owned_only": True,
            "limit": 1,
        },
    )
    if not items:
        raise ForgeHubError(
            f"No incubating thought #{number} owned by {slug!r}. "
            f"Use list_my_incubation to see what is yours to decide."
        )
    return items[0]["id"]


@mcp.tool()
async def receive_incubation(number: int, agent: str | None = None) -> str:
    """Take an incubated thought on: it becomes a Task addressed to you.

    One of the two ways a thought leaves incubation — the other is
    `drop_incubation`. Deciding is the point of incubation: a thought left
    undecided is exactly what this design exists to prevent.

    Needs both a sender and a target on the message, since the result is a
    Task; if either is missing you will be told, and the thought stays put
    rather than becoming work nobody can run.

    Args:
        number: the thought's #number (see `list_my_incubation`).
        agent: whose thought to decide; defaults to this runtime's own slug.
            You can only decide what you own.
    """
    try:
        slug = _resolve_agent(agent)
        demand_id = await _own_incubation_id(slug, number)
        result = await _call(
            "POST", f"/api/v1/demands/{demand_id}/incubation:receive", params={"agent": slug}
        )
    except ForgeHubError as exc:
        return str(exc)
    return f"Received #{number} — it is a Task now and scheduled to run.\n\n{_format_message(result, body='preview')}"


@mcp.tool()
async def drop_incubation(number: int, reason: str, agent: str | None = None) -> str:
    """Decline an incubated thought, saying why. The record is kept.

    The reason is required, not a formality: a drop without one is
    indistinguishable from the thought having been forgotten, and there
    would be no way to notice a pattern of discarding what mattered. The
    message is archived, never deleted.

    Args:
        number: the thought's #number (see `list_my_incubation`).
        reason: why this isn't worth taking on. Be specific — this is the
            only trace left of the decision.
        agent: whose thought to decide; defaults to this runtime's own slug.
    """
    try:
        slug = _resolve_agent(agent)
        if not reason.strip():
            raise ForgeHubError("A drop needs a reason — say why this thought isn't worth taking on.")
        demand_id = await _own_incubation_id(slug, number)
        await _call(
            "POST",
            f"/api/v1/demands/{demand_id}/incubation:drop",
            params={"agent": slug, "reason": reason},
        )
    except ForgeHubError as exc:
        return str(exc)
    return f"Dropped #{number} — archived with the reason on record: {reason.strip()}"


async def _resolve_channel_id(channel: str) -> str:
    """`channel` may be a UUID or a name -- most callers will type the name.
    No name-lookup endpoint exists server-side (channels are few enough
    that GET /channels + a client-side filter is simpler than adding one),
    same spirit as _resolve_agent resolving a slug locally."""
    try:
        import uuid as _uuid
        _uuid.UUID(channel)
        return channel
    except ValueError:
        pass
    channels = await _call("GET", "/api/v1/channels")
    matches = [c for c in channels if c.get("name", "").strip().lower() == channel.strip().lower()]
    if not matches:
        raise ForgeHubError(f"No channel named {channel!r}. Use list_channel_members with the exact name or its id.")
    if len(matches) > 1:
        raise ForgeHubError(
            f"{len(matches)} channels are named {channel!r} -- use one of their ids instead: "
            + ", ".join(f"{c['id']} ({c.get('project_id') or 'no project'})" for c in matches)
        )
    return matches[0]["id"]


async def _resolve_agent_id(agent: str) -> tuple[str, dict[str, Any]]:
    """`agent` may be a UUID, a profile_slug or a display name -- returns
    (id, roster_row) so callers get the name/default_role back for free
    instead of a second lookup. Same "list + client-side filter" spirit as
    _resolve_channel_id (the roster is small enough that a dedicated
    lookup-by-slug endpoint isn't worth adding server-side)."""
    agents = await _call("GET", "/api/v1/agents")
    try:
        import uuid as _uuid
        _uuid.UUID(agent)
        match = next((a for a in agents if a.get("id") == agent), None)
        if match is None:
            raise ForgeHubError(f"No agent with id {agent!r}.")
        return agent, match
    except ValueError:
        pass
    needle = agent.strip().lower()
    matches = [
        a for a in agents
        if (a.get("profile_slug") or "").strip().lower() == needle
        or (a.get("name") or "").strip().lower() == needle
    ]
    if not matches:
        raise ForgeHubError(f"No agent named or slugged {agent!r}.")
    if len(matches) > 1:
        raise ForgeHubError(
            f"{len(matches)} agents match {agent!r} -- use one of their ids instead: "
            + ", ".join(f"{a['id']} ({a.get('name')})" for a in matches)
        )
    return matches[0]["id"], matches[0]


@mcp.tool()
async def list_agent_skills(agent: str) -> str:
    """What one agent's declared function and granted skills are -- check
    this before proposing a task for a channel-mate (see
    propose_channel_task) so you don't hand work to someone missing the
    skill it needs. If nothing fits, ask the human orchestrator (Marcelo,
    or whoever holds "channel.member.role.assign"/"governance.approval.
    decide" for that channel) to have the skill authored -- this tool only
    reads, it never installs or creates a skill.

    Args:
        agent: the agent's name, profile_slug, or id.
    """
    try:
        agent_id, roster_row = await _resolve_agent_id(agent)
        agent_skills = await _call("GET", f"/api/v1/agents/{agent_id}/skills")
        catalog = await _call("GET", "/api/v1/agents/skills")
    except ForgeHubError as exc:
        return str(exc)

    skills_by_id = {s["id"]: s for s in catalog}
    name = roster_row.get("name", agent)
    lines = [
        f"{name} -- function: {roster_row.get('default_role') or '(none set)'}",
    ]
    if roster_row.get("description"):
        lines.append(f"  {roster_row['description']}")
    if not agent_skills:
        lines.append("  No skills granted yet.")
        return "\n".join(lines)
    lines.append("  Skills:")
    for grant in agent_skills:
        skill = skills_by_id.get(grant.get("skill_id"), {})
        approved = "approved" if skill.get("is_approved") else "NOT approved"
        lines.append(
            f"    - {skill.get('name', '?')} v{skill.get('version', '?')}"
            f" (risk: {skill.get('risk_level', '?')}, {approved})"
        )
    return "\n".join(lines)


@mcp.tool()
async def list_channel_members(channel: str) -> str:
    """Who's in a Software Factory channel and what their function is there
    -- check this before proposing a task so you know your own channel role
    (see propose_channel_task) and who else can take on what.

    Args:
        channel: the channel's name or id.
    """
    try:
        channel_id = await _resolve_channel_id(channel)
        detail = await _call("GET", f"/api/v1/channels/{channel_id}")
    except ForgeHubError as exc:
        return str(exc)

    members = detail.get("members", [])
    if not members:
        return f"Channel {detail.get('name')!r} has no members."
    lines = [f"Members of {detail.get('name')!r}:"]
    for member in members:
        if member.get("is_human"):
            lines.append("  - (human) Marcelo -- final authority in this channel")
            continue
        role = member.get("role") or "(no role set)"
        lines.append(f"  - agent {member.get('agent_id')}: role={role}")
    return "\n".join(lines)


@mcp.tool()
async def propose_channel_task(
    channel: str,
    title: str,
    assignee_agent: str,
    from_agent: str | None = None,
    role_required: str | None = None,
) -> str:
    """Propose a task in a Software Factory channel -- for yourself, or for
    a channel-mate.

    Two outcomes:
    - **Claiming your own work** (`assignee_agent` == you, and it matches
      your own role in that channel, or `role_required` is left unset):
      the task is created ready to work on immediately, no one needs to
      confirm it.
    - **Delegating to someone else** (or claiming work outside your own
      declared role): the task is created but blocked behind a real
      Governance Approval, pending until Marcelo (or an agent he has
      delegated "governance.approval.decide" to) decides it. This is
      deliberate -- responsibilities in a channel are meant to stay
      well-defined, so one agent proposing work FOR another always needs
      sign-off first (see list_channel_members to check roles beforehand).

    Args:
        channel: the channel's name or id.
        title: short task title.
        assignee_agent: profile_slug of who should do this work.
        from_agent: your own profile_slug; defaults to this runtime's own.
        role_required: optional -- tag which channel function this task is
            for (e.g. "documentation", "qa", "designer"). Only matters for
            the self-claim fast path above; omit if you don't need it.
    """
    try:
        channel_id = await _resolve_channel_id(channel)
        proposer = _resolve_agent(from_agent)
        payload: dict[str, Any] = {
            "acting_agent_slug": proposer,
            "title": title,
            "assignee_agent_slug": assignee_agent,
        }
        if role_required:
            payload["role_required"] = role_required
        task = await _call("POST", f"/api/v1/channels/{channel_id}/tasks/propose", json=payload)
    except ForgeHubError as exc:
        return str(exc)

    if task.get("approval_id"):
        return (
            f"Proposed task {task['title']!r} for {assignee_agent!r}, pending approval "
            f"(approval id {task['approval_id']}) -- it will not be worked on until "
            "Marcelo or a delegated orchestrator decides it."
        )
    return f"Task {task['title']!r} created for {assignee_agent!r}, ready to work on now (no approval needed)."


# ---------------------------------------------------------------------------
# Agents & AI — Registry, Profiles, Skills, and Tools Management
# ---------------------------------------------------------------------------


async def _resolve_skill_id(skill: str) -> tuple[str, dict[str, Any]]:
    """`skill` may be a UUID, slug or name -- returns (id, skill_row)."""
    skills = await _call("GET", "/api/v1/agents/skills")
    try:
        import uuid as _uuid
        _uuid.UUID(skill)
        match = next((s for s in skills if s.get("id") == skill), None)
        if match is None:
            raise ForgeHubError(f"No skill with id {skill!r}.")
        return skill, match
    except ValueError:
        pass
    needle = skill.strip().lower()
    matches = [
        s for s in skills
        if (s.get("slug") or "").strip().lower() == needle
        or (s.get("name") or "").strip().lower() == needle
    ]
    if not matches:
        raise ForgeHubError(f"No skill named or slugged {skill!r}.")
    if len(matches) > 1:
        raise ForgeHubError(
            f"{len(matches)} skills match {skill!r} -- use one of their ids instead: "
            + ", ".join(f"{s['id']} ({s.get('name')})" for s in matches)
        )
    return matches[0]["id"], matches[0]


@mcp.tool()
async def list_agents(status: str | None = None, runtime: str | None = None) -> str:
    """List all agents registered in ForgeHub, with their function, runtime, tier,
    and status. Use this to discover ecosystem agents or inspect the roster.

    Args:
        status: optional filter by status ('active', 'inactive', 'retired').
        runtime: optional filter by runtime ('hermes', 'claude', 'codex', 'agy', 'openclaw').
    """
    try:
        agents = await _call("GET", "/api/v1/agents")
    except ForgeHubError as exc:
        return str(exc)

    if status:
        agents = [a for a in agents if a.get("status") == status]
    if runtime:
        agents = [a for a in agents if a.get("runtime_type") == runtime]

    if not agents:
        return "No agents match the specified criteria."

    lines = [f"Registered Agents ({len(agents)}):"]
    for a in agents:
        slug = a.get("profile_slug") or "no-slug"
        r_type = a.get("runtime_type") or "hermes"
        tier = a.get("runtime_tier") or "Tier B"
        dept = [a.get("department"), a.get("sector")]
        dept_str = " · ".join(filter(None, dept)) or "Unclassified"
        status_tag = a.get("status") or "active"
        mission = a.get("mission") or a.get("description") or "(no mission statement)"
        lines.append(
            f"- {a.get('name')} (@{slug}) | {r_type} ({tier}) | Status: {status_tag} | Dept: {dept_str}\n"
            f"  ID: {a.get('id')}\n"
            f"  Mission: {mission}"
        )
    return "\n".join(lines)


@mcp.tool()
async def get_agent_profile(agent: str) -> str:
    """Get the full detailed profile of an agent by id, profile_slug or name.
    Returns identity, mission, department, sub-agents, approved skills, profile files, and tools.

    Args:
        agent: UUID, profile_slug (e.g. 'aegis', 'athos', 'porthos') or display name.
    """
    try:
        agent_id, roster_row = await _resolve_agent_id(agent)
        detail = await _call("GET", f"/api/v1/agents/{agent_id}")
        tools = await _call("GET", f"/api/v1/tools?agent_id={agent_id}")
    except ForgeHubError as exc:
        return str(exc)

    name = detail.get("name")
    slug = detail.get("profile_slug") or "no-slug"
    lines = [
        f"Agent Profile: {name} (@{slug})",
        f"ID: {detail.get('id')}",
        f"Type: {detail.get('agent_type')} | Runtime: {detail.get('runtime_type')} ({detail.get('runtime_tier')})",
        f"Status: {detail.get('status')} (Active: {detail.get('is_active')})",
        f"Department: {detail.get('department') or '—'} | Sector: {detail.get('sector') or '—'}",
        f"Home Path: {detail.get('effective_home_path') or detail.get('home_path') or '—'}",
        f"Mission: {detail.get('mission') or '—'}",
        f"Description: {detail.get('description') or '—'}",
        f"ForgeRouter Configured: {detail.get('forgerouter_api_key_configured')}",
    ]

    sub_agents = detail.get("sub_agents", [])
    lines.append(f"\nSub-agents ({len(sub_agents)}):")
    if not sub_agents:
        lines.append("  (none)")
    else:
        for sa in sub_agents:
            lines.append(f"  - {sa.get('name')} (ID: {sa.get('id')}): {sa.get('description') or sa.get('permission_scope') or 'scoped worker'}")

    skills = detail.get("skills", [])
    approved = [s for s in skills if s.get("is_approved")]
    lines.append(f"\nApproved Skills ({len(approved)} of {len(skills)} granted):")
    if not approved:
        lines.append("  (no approved skills granted)")
    else:
        for s in approved:
            lines.append(f"  - {s.get('name')} (v{s.get('version')}) [ID: {s.get('id')}] - {s.get('description') or ''}")

    profile_files = detail.get("profile_files", [])
    lines.append(f"\nProfile Files ({len(profile_files)}):")
    if not profile_files:
        lines.append("  (none found)")
    else:
        for pf in profile_files:
            exists_tag = "exists" if pf.get("exists") else "missing"
            lines.append(f"  - {pf.get('filename')} ({exists_tag}, {pf.get('size_bytes', 0)} bytes) -> {pf.get('path')}")

    lines.append(f"\nRegistered Tools ({len(tools)}):")
    if not tools:
        lines.append("  (no tools registered)")
    else:
        for t in tools:
            lines.append(f"  - {t.get('name')} [{t.get('category')}] ({t.get('status')}): {t.get('file_path')}\n    {t.get('description') or ''}")

    return "\n".join(lines)


@mcp.tool()
async def update_agent_profile(
    agent: str,
    mission: str | None = None,
    description: str | None = None,
    department: str | None = None,
    sector: str | None = None,
    runtime_type: str | None = None,
    runtime_tier: str | None = None,
    status: str | None = None,
    home_path: str | None = None,
) -> str:
    """Update/correct an agent's registration details in ForgeHub.
    Allows agents to correct their own or fellow agents' missions, departments, sectors,
    runtime configurations, or profile home directories.

    Args:
        agent: the agent's name, profile_slug, or UUID.
        mission: concise primary mission statement.
        description: extended functional description.
        department: organizational department name.
        sector: organizational sector name.
        runtime_type: runtime engine ('hermes', 'claude', 'codex', 'agy', 'openclaw').
        runtime_tier: tier classification (e.g. 'Tier A', 'Tier B').
        status: lifecycle status ('active', 'inactive', 'retired').
        home_path: absolute host profile directory path.
    """
    try:
        agent_id, roster_row = await _resolve_agent_id(agent)
        payload: dict[str, Any] = {}
        if mission is not None:
            payload["mission"] = mission
        if description is not None:
            payload["description"] = description
        if department is not None:
            payload["department"] = department
        if sector is not None:
            payload["sector"] = sector
        if runtime_type is not None:
            payload["runtime_type"] = runtime_type
        if runtime_tier is not None:
            payload["runtime_tier"] = runtime_tier
        if status is not None:
            payload["status"] = status
        if home_path is not None:
            payload["home_path"] = home_path

        if not payload:
            return "No fields provided to update."

        updated = await _call("PATCH", f"/api/v1/agents/{agent_id}", json=payload)
    except ForgeHubError as exc:
        return str(exc)

    return (
        f"Successfully updated agent {updated.get('name')!r} (@{updated.get('profile_slug')}).\n"
        f"Updated fields: {', '.join(payload.keys())}"
    )


@mcp.tool()
async def get_agent_profile_file(agent: str, filename: str) -> str:
    """Read a specific profile markdown file (SOUL.md, IDENTITY.md, TOOLS.md, AGENTS.md,
    USER.md, MEMORY.md, HEARTBEAT.md, CONTINUITY.md, SUBAGENTS.md, FOUNDATION_LINK.md) for an agent.

    Args:
        agent: the agent's name, profile_slug, or UUID.
        filename: name of the profile file to read (e.g. 'SOUL.md', 'TOOLS.md').
    """
    try:
        agent_id, roster_row = await _resolve_agent_id(agent)
        res = await _call("GET", f"/api/v1/agents/{agent_id}/profile-files/{filename}")
    except ForgeHubError as exc:
        return str(exc)

    return (
        f"# Profile File: {res.get('filename')} for {roster_row.get('name')}\n"
        f"Path: {res.get('path')}\n"
        f"Exists: {res.get('exists')}\n"
        f"----------------------------------------\n"
        f"{res.get('content', '')}"
    )


@mcp.tool()
async def update_agent_profile_file(agent: str, filename: str, content: str) -> str:
    """Update/write the contents of an agent's profile file (SOUL.md, IDENTITY.md, TOOLS.md, etc.).
    Allows agents to maintain, calibrate, and refine their profile instructions and memory.

    Args:
        agent: the agent's name, profile_slug, or UUID.
        filename: name of the profile file to write (e.g. 'SOUL.md', 'TOOLS.md', 'MEMORY.md').
        content: the complete new markdown text to write to the file.
    """
    try:
        agent_id, roster_row = await _resolve_agent_id(agent)
        res = await _call("PUT", f"/api/v1/agents/{agent_id}/profile-files/{filename}", json={"content": content})
    except ForgeHubError as exc:
        return str(exc)

    return (
        f"Successfully saved {res.get('filename')} ({res.get('size_bytes')} bytes) "
        f"for agent {roster_row.get('name')} at {res.get('path')}."
    )


@mcp.tool()
async def list_skills(category: str | None = None, approved_only: bool = False) -> str:
    """List skills registered across ForgeHub, including their slug, version, risk level,
    governance approval status, and granted agents.

    Args:
        category: optional category filter.
        approved_only: if true, returns only governance-approved skills.
    """
    try:
        skills = await _call("GET", "/api/v1/agents/skills")
    except ForgeHubError as exc:
        return str(exc)

    if category:
        skills = [s for s in skills if s.get("category") == category]
    if approved_only:
        skills = [s for s in skills if s.get("is_approved")]

    if not skills:
        return "No skills found matching the criteria."

    lines = [f"Skills Catalog ({len(skills)}):"]
    for s in skills:
        app_str = "approved" if s.get("is_approved") else "pending approval"
        agents_count = len(s.get("agents", []))
        lines.append(
            f"- {s.get('name')} (@{s.get('slug')}) v{s.get('version')} | Risk: {s.get('risk_level')} | [{app_str}]\n"
            f"  ID: {s.get('id')} | Category: {s.get('category') or 'general'} | Granted to: {agents_count} agents\n"
            f"  {s.get('description') or ''}"
        )
    return "\n".join(lines)


@mcp.tool()
async def grant_agent_skill(agent: str, skill: str, inheritable: bool = True) -> str:
    """Grant an approved skill to an agent so it has authorization and capability to use it.

    Args:
        agent: the agent's name, profile_slug, or UUID.
        skill: the skill's name, slug, or UUID.
        inheritable: whether sub-agents of this agent inherit this skill (default True).
    """
    try:
        agent_id, roster_row = await _resolve_agent_id(agent)
        skill_id, skill_row = await _resolve_skill_id(skill)
        grant = await _call(
            "POST",
            f"/api/v1/agents/{agent_id}/skills",
            json={"skill_id": skill_id, "inheritable": inheritable},
        )
    except ForgeHubError as exc:
        return str(exc)

    return (
        f"Successfully granted skill {skill_row.get('name')!r} to agent {roster_row.get('name')!r} "
        f"(inheritable={inheritable})."
    )


@mcp.tool()
async def revoke_agent_skill(agent: str, skill: str) -> str:
    """Revoke a granted skill from an agent.

    Args:
        agent: the agent's name, profile_slug, or UUID.
        skill: the skill's name, slug, or UUID.
    """
    try:
        agent_id, roster_row = await _resolve_agent_id(agent)
        skill_id, skill_row = await _resolve_skill_id(skill)
        await _call("DELETE", f"/api/v1/agents/{agent_id}/skills/{skill_id}")
    except ForgeHubError as exc:
        return str(exc)

    return f"Successfully revoked skill {skill_row.get('name')!r} from agent {roster_row.get('name')!r}."


@mcp.tool()
async def issue_agent_credential(
    agent: str,
    label: str = "MCP Service Token",
    expires_in_days: int | None = None,
) -> str:
    """Generate and issue a new, active API Service Credential (agt_...) for an agent on demand.

    Args:
        agent: the agent's name, profile_slug, or UUID.
        label: purpose or description of this credential.
        expires_in_days: optional number of days until expiration (None = never expires).
    """
    try:
        agent_id, roster_row = await _resolve_agent_id(agent)
        expires_at = None
        if expires_in_days is not None:
            expires_at = (datetime.now(timezone.utc) + timedelta(days=expires_in_days)).isoformat()
        res = await _call(
            "POST",
            f"/api/v1/agents/{agent_id}/credentials",
            json={"label": label, "expires_at": expires_at},
        )
    except ForgeHubError as exc:
        return str(exc)

    return (
        f"Successfully issued new credential for agent {roster_row.get('name')!r}:\n"
        f"Credential ID: {res.get('id')}\n"
        f"Label: {res.get('label')}\n"
        f"Token: {res.get('token')}\n"
        f"Expires: {res.get('expires_at') or 'never'}\n\n"
        f"Note: This token ('agt_...') is only shown once upon creation."
    )


@mcp.tool()
async def list_agent_credentials(agent: str) -> str:
    """List active service credentials issued for an agent.

    Args:
        agent: the agent's name, profile_slug, or UUID.
    """
    try:
        agent_id, roster_row = await _resolve_agent_id(agent)
        creds = await _call("GET", f"/api/v1/agents/{agent_id}/credentials")
    except ForgeHubError as exc:
        return str(exc)

    if not creds:
        return f"No active credentials found for agent {roster_row.get('name')!r}."

    lines = [f"Active Credentials for {roster_row.get('name')} ({len(creds)}):"]
    for c in creds:
        lines.append(
            f"- ID: {c.get('id')} | Label: {c.get('label')} | Created: {c.get('created_at')} | Expires: {c.get('expires_at') or 'never'}"
        )
    return "\n".join(lines)


@mcp.tool()
async def revoke_agent_credential(agent: str, credential_id: str) -> str:
    """Revoke an agent's service credential by ID.

    Args:
        agent: the agent's name, profile_slug, or UUID.
        credential_id: UUID of the credential to revoke.
    """
    try:
        agent_id, roster_row = await _resolve_agent_id(agent)
        await _call("DELETE", f"/api/v1/agents/{agent_id}/credentials/{credential_id}")
    except ForgeHubError as exc:
        return str(exc)

    return f"Successfully revoked credential {credential_id!r} for agent {roster_row.get('name')!r}."


@mcp.tool()
async def list_agent_tools(
    agent: str | None = None,
    category: str | None = None,
    status: str | None = None,
) -> str:
    """List registered agent tools/scripts in ForgeHub with their location and purpose.

    Args:
        agent: optional filter by responsible agent (name, slug, or UUID).
        category: optional filter by category ('monitoring', 'maintenance', 'backup', 'database', etc.).
        status: optional filter by status ('active', 'deprecated', 'archived').
    """
    try:
        params: dict[str, str] = {}
        if agent:
            agent_id, _ = await _resolve_agent_id(agent)
            params["agent_id"] = agent_id
        if category:
            params["category"] = category
        if status:
            params["status"] = status
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        path = f"/api/v1/tools?{qs}" if qs else "/api/v1/tools"
        tools = await _call("GET", path)
    except ForgeHubError as exc:
        return str(exc)

    if not tools:
        return "No tools found matching the specified filter."

    lines = [f"Registered Tools ({len(tools)}):"]
    for t in tools:
        lines.append(
            f"- {t.get('name')} [{t.get('category')}] ({t.get('status')}) — Agent: {t.get('agent_name') or t.get('agent_id')}\n"
            f"  ID: {t.get('id')}\n"
            f"  Path: {t.get('file_path')}\n"
            f"  Description: {t.get('description') or '—'}"
        )
    return "\n".join(lines)


@mcp.tool()
async def register_agent_tool(
    agent: str,
    name: str,
    file_path: str,
    description: str,
    category: str = "general",
    status: str = "active",
) -> str:
    """Register a new script or utility tool in the ForgeHub tool catalog for an agent.

    Args:
        agent: responsible agent's name, profile_slug, or UUID.
        name: tool identifier (e.g. 'health_check.sh', 'db_backup.py').
        file_path: absolute path on disk to the executable script or entrypoint.
        description: what the tool does and when to run it.
        category: tool classification ('monitoring', 'maintenance', 'backup', 'database', 'reporting', etc.).
        status: lifecycle status ('active', 'deprecated', 'archived').
    """
    try:
        agent_id, roster_row = await _resolve_agent_id(agent)
        payload = {
            "agent_id": agent_id,
            "name": name,
            "file_path": file_path,
            "description": description,
            "category": category,
            "status": status,
        }
        tool = await _call("POST", "/api/v1/tools", json=payload)
    except ForgeHubError as exc:
        return str(exc)

    return (
        f"Successfully registered tool {tool.get('name')!r} (ID: {tool.get('id')}) "
        f"for agent {roster_row.get('name')!r} at {tool.get('file_path')}."
    )


@mcp.tool()
async def update_agent_tool(
    tool_id: str,
    name: str | None = None,
    file_path: str | None = None,
    description: str | None = None,
    category: str | None = None,
    status: str | None = None,
) -> str:
    """Update metadata, file path, description, category, or status of an existing registered tool.

    Args:
        tool_id: UUID of the tool to update.
        name: new name for the tool.
        file_path: updated absolute file path.
        description: updated functional description.
        category: updated category.
        status: updated status ('active', 'deprecated', 'archived').
    """
    try:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if file_path is not None:
            payload["file_path"] = file_path
        if description is not None:
            payload["description"] = description
        if category is not None:
            payload["category"] = category
        if status is not None:
            payload["status"] = status

        if not payload:
            return "No fields provided to update."

        tool = await _call("PATCH", f"/api/v1/tools/{tool_id}", json=payload)
    except ForgeHubError as exc:
        return str(exc)

    return (
        f"Successfully updated tool {tool.get('name')!r} (ID: {tool.get('id')}).\n"
        f"Updated fields: {', '.join(payload.keys())}"
    )


@mcp.tool()
async def scan_agent_tools() -> str:
    """Scan the filesystem (/root/.hermes/profiles/*/scripts and central script catalogs)
    to automatically discover and register uncataloged tools.
    """
    try:
        result = await _call("POST", "/api/v1/tools/scan")
    except ForgeHubError as exc:
        return str(exc)

    return (
        f"Tool scan completed: {result.get('scanned', 0)} files scanned, "
        f"{result.get('created', 0)} newly registered, {result.get('skipped', 0)} already registered."
    )


@mcp.tool()
async def sync_hermes_agents() -> str:
    """Reconcile and sync canonical agents, sub-agents, and skills from the Hermes Foundation
    contract files (/root/.hermes/foundation/agents).
    """
    try:
        result = await _call("POST", "/api/v1/agents/sync/hermes-foundation")
    except ForgeHubError as exc:
        return str(exc)

    agents = result.get("agents", {})
    sub_agents = result.get("sub_agents", {})
    skills = result.get("skills", {})
    grants = result.get("agent_skills", {})
    warnings = result.get("warnings", [])

    lines = [
        "Hermes Foundation sync completed:",
        f"- Agents: {agents.get('created', 0)} created, {agents.get('updated', 0)} updated",
        f"- Sub-agents: {sub_agents.get('created', 0)} created, {sub_agents.get('updated', 0)} updated",
        f"- Skills: {skills.get('created', 0)} created, {skills.get('updated', 0)} updated",
        f"- Skill Grants: {grants.get('created', 0)} created",
    ]
    if warnings:
        lines.append(f"Warnings ({len(warnings)}): " + "; ".join(warnings))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Operations — System Control, Auditor, Deploy, Database, and Infrastructure
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_system_status() -> str:
    """Get the live operational status of the host and ForgeHub platform,
    including CPU, memory, disk usage, active background services, and health status.
    """
    try:
        data = await _call("GET", "/api/v1/system-control/status")
    except ForgeHubError as exc:
        return str(exc)

    host = data.get("host", {})
    disk = data.get("disk", {})
    mem = data.get("memory", {})
    cpu = data.get("cpu", {})

    lines = [
        "System Operational Status:",
        f"- Hostname: {host.get('hostname', 'unknown')} | Platform: {host.get('platform', 'linux')}",
        f"- CPU Usage: {cpu.get('percent', 0)}% ({cpu.get('count', 0)} cores)",
        f"- Memory: {mem.get('used_gb', 0):.1f} GB / {mem.get('total_gb', 0):.1f} GB ({mem.get('percent', 0)}% used)",
        f"- Disk: {disk.get('used_gb', 0):.1f} GB / {disk.get('total_gb', 0):.1f} GB ({disk.get('percent', 0)}% used)",
    ]

    services = data.get("services", [])
    if services:
        lines.append(f"\nServices ({len(services)}):")
        for s in services:
            lines.append(f"  - {s.get('name')}: {s.get('status')} (port {s.get('port') or 'internal'})")

    containers = data.get("containers", [])
    if containers:
        lines.append(f"\nContainers ({len(containers)}):")
        for c in containers:
            lines.append(f"  - {c.get('name')}: {c.get('status')} ({c.get('state')})")

    return "\n".join(lines)


@mcp.tool()
async def list_system_backups() -> str:
    """List available system and database backup snapshots in ForgeHub."""
    try:
        data = await _call("GET", "/api/v1/system-control/backups")
    except ForgeHubError as exc:
        return str(exc)

    backups = data.get("backups", []) if isinstance(data, dict) else data
    if not backups:
        return "No backup archives found."

    lines = [f"System Backups ({len(backups)}):"]
    for b in backups:
        lines.append(
            f"- {b.get('filename')} | Target: {b.get('target')} | Size: {b.get('size_human', 'unknown')} | Created: {b.get('created_at')}"
        )
    return "\n".join(lines)


@mcp.tool()
async def run_system_backup(target: str = "all") -> str:
    """Trigger an immediate backup creation for the system, database, or specific target.

    Args:
        target: backup target ('all', 'database', 'hermes', 'forgehub').
    """
    try:
        res = await _call("POST", "/api/v1/system-control/backups/run", json={"target": target})
    except ForgeHubError as exc:
        return str(exc)

    return f"Backup completed successfully: {res.get('filename')} ({res.get('size_human', 'unknown')}) created at {res.get('path')}."


@mcp.tool()
async def list_audit_checks() -> str:
    """List ecosystem auditor checks with their latest run results, status, and compliance health.
    """
    try:
        checks = await _call("GET", "/api/v1/audit/checks")
    except ForgeHubError as exc:
        return str(exc)

    if not checks:
        return "No audit checks registered."

    lines = [f"Auditor Checks ({len(checks)}):"]
    for c in checks:
        last_status = c.get("last_run_status") or "never_ran"
        lines.append(
            f"- {c.get('name')} [{c.get('category')}] | Status: {last_status} | Severity: {c.get('severity')}\n"
            f"  ID: {c.get('id')}\n"
            f"  Description: {c.get('description') or '—'}"
        )
    return "\n".join(lines)


@mcp.tool()
async def run_audit_checks() -> str:
    """Execute all ecosystem audit checks and return an aggregated compliance & integrity report.
    """
    try:
        res = await _call("POST", "/api/v1/audit/run")
    except ForgeHubError as exc:
        return str(exc)

    passed = res.get("passed", 0)
    failed = res.get("failed", 0)
    total = res.get("total", 0)
    lines = [
        f"Audit run completed: {passed}/{total} passed, {failed} failed.",
    ]
    runs = res.get("results", [])
    for r in runs:
        if r.get("status") != "passed":
            lines.append(f"- [FAILED] {r.get('name')}: {r.get('message') or r.get('details')}")
    return "\n".join(lines)


@mcp.tool()
async def list_deploy_containers() -> str:
    """List all deployment containers running the ForgeHub stack with their health and ports.
    """
    try:
        containers = await _call("GET", "/api/v1/deploy/containers")
    except ForgeHubError as exc:
        return str(exc)

    if not containers:
        return "No deploy containers found."

    lines = [f"Deploy Containers ({len(containers)}):"]
    for c in containers:
        ports = ", ".join(c.get("ports", [])) or "no exposed ports"
        lines.append(
            f"- {c.get('name')} | Image: {c.get('image')} | Status: {c.get('status')} ({c.get('state')}) | Ports: {ports}"
        )
    return "\n".join(lines)


@mcp.tool()
async def restart_deploy_container(container_name: str) -> str:
    """Restart a deployment container (e.g. 'forgehub-backend', 'forgehub-frontend', 'hindsight').

    Args:
        container_name: name of the docker container to restart.
    """
    try:
        res = await _call("POST", f"/api/v1/deploy/containers/{container_name}/restart")
    except ForgeHubError as exc:
        return str(exc)

    return f"Successfully restarted container {container_name!r}."


@mcp.tool()
async def get_container_logs(container_name: str, tail: int = 100) -> str:
    """Read the latest execution logs from a running deployment container.

    Args:
        container_name: name of the docker container (e.g. 'forgehub-backend', 'forgehub-frontend').
        tail: number of lines from the end to retrieve (default 100).
    """
    try:
        res = await _call("GET", f"/api/v1/deploy/containers/{container_name}/logs?tail={tail}")
    except ForgeHubError as exc:
        return str(exc)

    logs = res.get("logs") if isinstance(res, dict) else str(res)
    return f"Logs for {container_name} (last {tail} lines):\n----------------------------------------\n{logs}"


@mcp.tool()
async def list_managed_servers() -> str:
    """List managed servers and host infrastructure registered in ForgeHub.
    """
    try:
        servers = await _call("GET", "/api/v1/servers")
    except ForgeHubError as exc:
        return str(exc)

    if not servers:
        return "No managed servers registered."

    lines = [f"Managed Servers ({len(servers)}):"]
    for s in servers:
        lines.append(
            f"- {s.get('name')} ({s.get('host')}:{s.get('port', 22)}) | Status: {s.get('status')} | OS: {s.get('os_type', 'linux')}\n"
            f"  ID: {s.get('id')} | Environment: {s.get('environment', 'production')}"
        )
    return "\n".join(lines)


@mcp.tool()
async def execute_database_query(
    query: str,
    instance: str = "forgehub_postgres",
    database: str = "forgehub",
) -> str:
    """Execute a safe SQL query against one of ForgeHub's PostgreSQL databases and return tabular results.

    Args:
        query: SQL query (SELECT / introspection).
        instance: database instance ('forgehub_postgres', 'forgerouter_postgres' or 'hindsight_postgres').
        database: database name ('forgehub', 'foundation', 'forgerouter').
    """
    try:
        clean_sql = query.strip().rstrip(";")
        res = await _call(
            "POST",
            "/api/v1/database/query",
            json={"sql": clean_sql, "instance": instance, "db": database},
        )
    except ForgeHubError as exc:
        return str(exc)

    columns = res.get("columns", [])
    rows = res.get("rows", [])
    elapsed_ms = res.get("elapsed_ms", 0)

    if not rows:
        return f"Query returned 0 rows in {elapsed_ms:.1f}ms.\nColumns: {', '.join(columns)}"

    lines = [
        f"Query Results ({len(rows)} rows in {elapsed_ms:.1f}ms):",
        " | ".join(columns),
        "-" * 50,
    ]
    for r in rows[:50]:
        if isinstance(r, list):
            lines.append(" | ".join(str(val) for val in r))
        elif isinstance(r, dict):
            lines.append(" | ".join(str(r.get(c, "")) for c in columns))
        else:
            lines.append(str(r))
    if len(rows) > 50:
        lines.append(f"... and {len(rows) - 50} more rows.")

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
