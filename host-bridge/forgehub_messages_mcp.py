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
        channel: **the medium the request reached you through**, when you are
            passing on work someone else asked for: "telegram", "workspace",
            "assistant", "factory" or "agent". Set it whenever a human asked
            you for something somewhere and you are delegating it — without
            it the result has no way back to them and dies in ForgeHub.
        channel_ref: the concrete address to answer at within that medium --
            for Telegram, the chat_id the request came from. Naming the
            medium alone is not enough: "telegram" on its own only reaches
            the configured home channel, never the conversation that asked.
        requires_response: create a real return message once the recipient
            finishes, instead of only recording the result on this message.
        scheduled_at: ISO-8601 datetime to defer dispatch (e.g.
            "2026-07-28T14:00:00-03:00"). Only meaningful with `to_agent`;
            omit to dispatch now.
        origin_task_number: ForgeHub task number (ProjectTask.number) this
            came from.

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
            # to_agent still lands as Task here, but the backend's own
            # _reconcile_task_origin (demand.py) silently downgrades any
            # Task with no target_agent_id to Backlog, so this never needs a
            # branch for the no-to_agent case. Tipo is mandatory now (no
            # None/"demand" values left, see FORGEHUB_MESSAGE.md).
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


if __name__ == "__main__":
    mcp.run()
