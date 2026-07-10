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

With no chat id in --target, send_message_tool resolves the platform's
configured home channel (~/.hermes/config.yaml) -- for a single-user
Hermes install that's "my own Telegram", no id lookup needed.
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
    args = p.parse_args()

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
