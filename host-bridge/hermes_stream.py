#!/usr/bin/env python
"""Streaming helper — runs as a subprocess of the bridge.

Writes lines to stdout:
  {"stream_id": "<uuid>"}                                — first line, always
  {"delta": "<text>"}                                     — one per token
  {"tool_start": {"tool_id", "name", "context"}}          — tool call begins
  {"tool_complete": {"tool_id", "name"}}                  — tool call ends
  {"approval_request": {"stream_id", "command", "description"}} — blocks until
                                                              an approval_response
                                                              line arrives on stdin
  {"done": true, "session_id": "...", "reply": "..."}     — final line
  {"error": "..."}                                        — on failure (final line)

Reads lines from stdin:
  {"approval_response": {"choice": "once"|"deny"}}  — answers the most recent
                                                        approval_request

Must be run from HERMES_HOME set to the target profile directory, e.g.:
  HERMES_HOME=/root/.hermes/profiles/athos python hermes_stream.py ...
"""
import json
import os
import re
import sys
import threading
import uuid


def _emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


# Codex/Harmony tool-call serialization (``to=functions.search_files {...}``,
# optionally prefixed with ``assistant`` or a ``<|channel|>`` marker) that the
# model sometimes emits as plain assistant text instead of a real structured
# tool call -- e.g. because the target profile's model.api_mode is
# "chat_completions", which doesn't get the Responses-API leak recovery in
# hermes-agent's agent/codex_responses_adapter.py. Mirrors that module's
# _TOOL_CALL_LEAK_PATTERN so this stream never persists the raw leaked tokens
# as the assistant's reply (see forgehub#chat garbled-reply reports).
_TOOL_CALL_LEAK_PATTERN = re.compile(
    r"(?:^|[\s>|])to=functions\.[A-Za-z_][\w.]*",
    re.IGNORECASE,
)


# Slash commands ForgeHub's web chat will actually execute via Hermes's own
# process_command() dispatcher instead of forwarding the text to the LLM.
# Deliberately small: read-only/session-scoped commands only. Excludes
# anything destructive (/new, /undo -- they open a confirmation modal that
# can't be answered through this one-shot, non-interactive subprocess),
# anything that bypasses safety (/yolo), and anything stateful/long-running
# (/cron, /kanban, /skills, /billing) that doesn't fit a per-message process.
# Excludes "usage": it reads agent.session_api_calls, in-memory state on the
# `agent` object that's rebuilt from scratch by every one-shot subprocess --
# it would always report "No API calls made yet" regardless of real usage.
SAFE_SLASH_COMMANDS = {
    "model", "status", "help", "version", "title", "profile",
    # Added 2026-07: read-only, no self.agent dependency (checked against
    # cli.py's dispatcher -- config/toolsets read cli_inst attributes set in
    # __init__, platforms/plugins read straight from disk). "whoami" was
    # considered too but dropped: it's registered in hermes_cli/commands.py
    # but process_command() has no actual elif branch for it (dead entry).
    "config", "toolsets", "platforms", "plugins",
}


def _run_slash_command(cli_inst, message: str, canonical: str) -> str:
    """Execute a whitelisted slash command and capture its output.

    process_command() doesn't return text -- commands print via _cprint()
    (routes through prompt_toolkit's print_formatted_text, not Console) or
    via self.console.print() (Rich). Capture both: swap in a buffer-backed
    Console, and monkeypatch the module-level _pt_print this file's `cli`
    module calls internally, for the duration of the call only.
    """
    import contextlib
    import io
    import cli as cli_module
    from rich.console import Console
    from tools.ansi_strip import strip_ansi

    buf = io.StringIO()
    stdout_buf = io.StringIO()
    original_console = cli_inst.console
    original_pt_print = cli_module._pt_print
    captured_ansi: list[str] = []

    def fake_pt_print(value, **_kwargs) -> None:
        text = getattr(value, "value", None)
        captured_ansi.append(strip_ansi(text if text is not None else str(value)))

    cli_inst.console = Console(file=buf, force_terminal=False, width=100)
    cli_module._pt_print = fake_pt_print
    try:
        # Some commands (e.g. /usage, /version) print via the plain builtin
        # print() instead of self.console/_cprint -- redirect_stdout catches
        # those too. Safe here because nothing else writes to stdout while
        # process_command() runs (no _emit() calls inside this block).
        with contextlib.redirect_stdout(stdout_buf):
            cli_inst.process_command(message)
    finally:
        cli_inst.console = original_console
        cli_module._pt_print = original_pt_print

    parts = [
        p
        for p in (buf.getvalue().strip(), "\n".join(captured_ansi).strip(), stdout_buf.getvalue().strip())
        if p
    ]
    text = "\n".join(parts) or "(comando executado, sem saída)"

    if canonical == "status":
        # agent.session_total_tokens (read by _show_session_status) is
        # in-memory state on the `agent` object, rebuilt from scratch by
        # every one-shot subprocess -- it never reflects real usage from
        # earlier turns in this same chat thread. Drop the line rather than
        # show a confidently wrong number (see SAFE_SLASH_COMMANDS comment
        # on why "usage" itself is excluded entirely for the same reason).
        text = "\n".join(
            line for line in text.split("\n") if not line.strip().lower().startswith("tokens:")
        )

    return text


def _start_approval_listener(stream_id: str) -> None:
    """Background thread: relays stdin {"approval_response": {...}} lines into
    tools.approval's blocking queue. Exits naturally when stdin closes (the
    bridge closes it once the request is done/killed)."""
    from tools.approval import resolve_gateway_approval

    def reader() -> None:
        for raw_line in sys.stdin:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                data = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            resp = data.get("approval_response")
            if resp:
                resolve_gateway_approval(stream_id, resp.get("choice") or "deny")

    threading.Thread(target=reader, daemon=True).start()


def main() -> None:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--profile-home", required=True)
    p.add_argument("--message", required=True)
    p.add_argument("--session-id", default=None)
    p.add_argument("--cwd", default=None)
    args = p.parse_args()

    os.environ["HERMES_HOME"] = args.profile_home
    os.environ.setdefault("HERMES_SESSION_SOURCE", "tool")
    # Without this, MCP tools (forgehub-messages included) are never
    # available to the model during a chat.py-driven turn (2026-07-28).
    # This process instantiates HermesCLI directly and calls _init_agent()
    # itself, skipping hermes_cli/main.py's main() -- which is the only
    # place that normally calls start_background_mcp_discovery() before a
    # real hermes chat session. _init_agent() already calls
    # _prepare_deferred_agent_startup() (cli.py) unconditionally and then
    # waits on wait_for_mcp_discovery() (mcp_startup.py) -- but
    # _prepare_deferred_agent_startup() is itself a no-op unless this env
    # var is set, so the wait was returning instantly with nothing ever
    # discovered. Setting it here reuses hermes-agent's own existing
    # deferred-startup path (built for Termux) instead of duplicating MCP
    # discovery logic in this file or patching the installed package.
    os.environ.setdefault("HERMES_DEFER_AGENT_STARTUP", "1")

    sys.path.insert(0, "/usr/local/lib/hermes-agent")
    # ChatSession.working_directory_path (see chat.py's /stream) -- runs the
    # turn's terminal/tools from a project's folder instead of the agent's
    # own profile home, without losing the profile's identity/config
    # (HERMES_HOME above still points at profile_home regardless). Falls
    # back to profile_home rather than raising if the path is stale/gone
    # (e.g. a project folder moved/deleted after the session picked it) --
    # stderr is discarded by the host-bridge caller, so an unhandled
    # exception here would silently kill the whole turn with no output.
    cwd = args.cwd if args.cwd and os.path.isdir(args.cwd) else args.profile_home
    os.chdir(cwd)

    stream_id = str(uuid.uuid4())
    _emit({"stream_id": stream_id})

    try:
        from cli import HermesCLI  # type: ignore
    except Exception as exc:
        _emit({"error": f"import failed: {exc}"})
        return

    session_key_token = None
    try:
        from tools.approval import (
            register_gateway_notify,
            reset_current_session_key,
            set_current_session_key,
            unregister_gateway_notify,
        )

        cli_inst = HermesCLI(resume=args.session_id)
        cli_inst.tool_progress_mode = "off"  # keep the CLI's own print()s out of our JSON-line stdout

        full_parts: list[str] = []
        any_tool_ran = False

        def on_delta(delta: str) -> None:
            full_parts.append(delta)
            _emit({"delta": delta})

        def on_tool_start(tool_id, name, tool_args) -> None:
            nonlocal any_tool_ran
            any_tool_ran = True
            try:
                from agent.display import build_tool_label
                context = build_tool_label(name, tool_args, max_len=80) or name
            except Exception:
                context = name
            payload = {"tool_id": str(tool_id), "name": name, "context": context}
            # `context` is truncated to 80 chars -- also ship the exact
            # primary argument (full command/path/query) so the UI can show
            # it verbatim instead of an elided label.
            if isinstance(tool_args, dict):
                for key in ("command", "cmd", "code", "path", "file_path", "query", "url"):
                    val = tool_args.get(key)
                    if isinstance(val, str) and val.strip():
                        payload["detail"] = val[:2000]
                        break
            _emit({"tool_start": payload})

        def on_tool_complete(tool_id, name, tool_args, result) -> None:
            payload = {"tool_id": str(tool_id), "name": name}
            if name in ("write_file", "patch") and isinstance(tool_args, dict) and tool_args.get("path"):
                payload["summary"] = f"Artefato criado: {tool_args['path']}"
                payload["path"] = tool_args["path"]
            # Delegating to another agent mid-conversation (2026-07-28, see
            # FORGEHUB_MESSAGE.md's "Delegating to another agent
            # mid-conversation"): forgehub-messages' send_agent_message
            # always replies with "Sent message #<N> (...)" as its first
            # line (forgehub_messages_mcp.py). Surfacing the number here --
            # not by having the frontend re-parse the model's own paraphrase
            # of it -- lets ChatPane render a live status card for the
            # message this tool call just created, backed by the same
            # dispatch_status the Messages page already polls.
            if name == "mcp__forgehub_messages__send_agent_message" and isinstance(result, str):
                match = re.search(r"Sent message #(\d+)", result)
                if match:
                    payload["demand_number"] = int(match.group(1))
            _emit({"tool_complete": payload})

        def on_approval_request(approval_data: dict) -> None:
            _emit({
                "approval_request": {
                    "stream_id": stream_id,
                    "command": approval_data.get("command", ""),
                    "description": approval_data.get("description", ""),
                    "pattern_keys": approval_data.get("pattern_keys", []),
                }
            })

        # Check for a whitelisted slash command *before* paying for
        # _init_agent() (credential checks, MCP discovery wait, etc.) --
        # none of SAFE_SLASH_COMMANDS touch self.agent (status/usage even
        # explicitly tolerate self.agent is None, see cli.py's own
        # slash-worker-subprocess comment), so initializing the agent first
        # only adds failure surface unrelated to what the command needs.
        from cli import _looks_like_slash_command
        from hermes_cli.commands import resolve_command

        if _looks_like_slash_command(args.message):
            base = args.message.split(None, 1)[0].lstrip("/").lower()
            resolved = resolve_command(base)
            if resolved and resolved.name in SAFE_SLASH_COMMANDS:
                reply_text = _run_slash_command(cli_inst, args.message, resolved.name)
                _emit({"delta": reply_text})
                # Slash commands never go through _init_agent()'s resume
                # validation or run_conversation(), so cli_inst.session_id
                # here was never written to Hermes's own SQLite session
                # store. Echoing it back as the thread's session_id would
                # poison continuity: the next real message would try to
                # --resume a session that doesn't exist, and _init_agent()
                # would fail with "Session not found" / return False for
                # the *whole conversation*, not just the slash command (see
                # the bug this fixes -- a slash command run as the first
                # message of a chat broke every real message after it).
                # Echo back whatever session_id was already real instead.
                _emit({"done": True, "session_id": args.session_id, "reply": reply_text})
                return

        if not cli_inst._init_agent():
            raise RuntimeError("_init_agent() returned False")

        cli_inst.agent.tool_start_callback = on_tool_start
        cli_inst.agent.tool_complete_callback = on_tool_complete

        register_gateway_notify(stream_id, on_approval_request)
        session_key_token = set_current_session_key(stream_id)
        _start_approval_listener(stream_id)

        result = cli_inst.agent.run_conversation(
            user_message=args.message,
            conversation_history=cli_inst.conversation_history,
            stream_callback=on_delta,
        )
        new_sid = cli_inst.session_id
        full_reply = result.get("final_response", "".join(full_parts))
        if not any_tool_ran and _TOOL_CALL_LEAK_PATTERN.search(full_reply):
            # The model tried to call a tool and degenerated into emitting
            # the raw serialization as text instead (no tool actually ran).
            # Persisting that garbage as the reply is worse than saying we
            # don't have a real answer -- ask the user to retry the turn.
            full_reply = (
                "O agente tentou chamar uma ferramenta, mas o modelo não formatou "
                "a chamada corretamente e nenhuma ferramenta rodou. Tente reenviar "
                "a mensagem."
            )
        _emit({"done": True, "session_id": new_sid, "reply": full_reply})

    except Exception as exc:
        _emit({"error": str(exc)})
    finally:
        try:
            unregister_gateway_notify(stream_id)
            if session_key_token is not None:
                reset_current_session_key(session_key_token)
        except Exception:
            pass


if __name__ == "__main__":
    main()
