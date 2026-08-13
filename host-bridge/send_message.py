#!/usr/bin/env python
"""Send a message through Hermes's cross-channel gateway (Telegram, Discord,
Slack, ...) -- runs as a HERMES_PYTHON subprocess of the bridge, same
pattern as hermes_stream.py (sys.path pointed at the hermes-agent install so
`tools`/`gateway` resolve, since the bridge's own process doesn't have that
on its path).

Prints the raw JSON string send_message_tool already returns
({"success": true, ...} or {"error": "..."}) to stdout -- the bridge route
passes it straight through, no reshaping needed.

Usage:
  python send_message.py --target telegram --message "..."
  python send_message.py --target telegram:123456 --message "..."
  python send_message.py --profile-home /root/.hermes/profiles/athos ...

With no chat id in --target, send_message_tool resolves the platform's
configured home channel (~/.hermes/config.yaml) -- for a single-user
Hermes install that's "my own Telegram", no id lookup needed.

--profile-home picks *which bot sends it* (2026-08-13). Every agent has its
own Telegram bot with its own TELEGRAM_BOT_TOKEN in its profile .env --
Athos is @HermesAthosbot, Atlas @HermesAtlas2bot, and so on -- so replying
to a request that arrived through one agent means sending through that
agent's bot, or the answer shows up from the wrong sender. Without this the
tool resolved HERMES_HOME to the global install and always used whichever
bot that pointed at.

Same mechanism hermes_stream.py already used for chat sessions; this brings
outbound messages to parity. Omitted, behaviour is exactly as before.
"""
import argparse
import json
import os
import sys
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--target", required=True)
    p.add_argument("--message", required=True)
    p.add_argument(
        "--profile-home",
        default=None,
        help="Agent profile dir whose bot/credentials to send with "
             "(e.g. /root/.hermes/profiles/athos). Defaults to the global install.",
    )
    args = p.parse_args()

    if args.profile_home:
        home = Path(args.profile_home)
        if not home.is_dir():
            # Fail loudly rather than silently falling back to the global
            # install: a wrong-but-working send is worse than an error,
            # because the reply arrives from an agent that never ran it.
            print(json.dumps({"error": f"profile home not found: {home}"}))
            sys.exit(1)
        # Overwrite, not setdefault -- the point is to override whatever the
        # parent process had.
        os.environ["HERMES_HOME"] = str(home)
        # The bot token lives in the profile's own .env, which the tool reads
        # relative to HERMES_HOME; load it here too so it is present even if
        # the tool only consults the environment.
        env_file = home / ".env"
        if env_file.is_file():
            for line in env_file.read_text(errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if key.startswith("TELEGRAM_") or key.endswith("_TOKEN"):
                    os.environ[key] = value.split("#")[0].strip().strip('"').strip("'")
    else:
        os.environ.setdefault("HERMES_HOME", str(Path.home() / ".hermes"))
    sys.path.insert(0, "/usr/local/lib/hermes-agent")

    try:
        from tools.send_message_tool import send_message_tool
    except Exception as exc:
        print(json.dumps({"error": f"import failed: {exc}"}))
        sys.exit(1)

    result = send_message_tool({"target": args.target, "message": args.message})
    print(result)


if __name__ == "__main__":
    main()
