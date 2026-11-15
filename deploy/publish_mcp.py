#!/usr/bin/env python3
"""Publish the ForgeHub MCP code that agents run, from one commit (MCP split plan, Fase 0, L3/L4).

Agents used to run the MCP straight from the main checkout (`/root/project/forgehub`), so any
session that switched branches or published changed every agent's tools, and the Maia ran a
copy pinned to an old release. Now every agent runs `/root/.forgehub/mcp/current/...`, a
symlink to an immutable copy of exactly one commit:

    python3 deploy/publish_mcp.py <commit>        # publish and switch `current`
    python3 deploy/publish_mcp.py --status        # what `current` points at

The copy keeps the repository layout (`backend/app/mcp/`, `host-bridge/forgehub_messages_mcp.py`)
because factory_server.py finds the Messages server relative to its own repository root.
Already-running MCP processes keep the code they loaded; new sessions get the new one.
The switch is atomic (rename of a temporary symlink) and the previous target stays on disk,
so going back is publishing the previous commit again.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(os.environ.get("FORGEHUB_REPO", "/root/project/forgehub"))
MCP_HOME = Path(os.environ.get("FORGEHUB_MCP_HOME", "/root/.forgehub/mcp"))
# What agents load. Everything else in the repository stays out of the copy.
PATHS = ("backend/app/mcp", "host-bridge/forgehub_messages_mcp.py")
ENTRYPOINTS = ("backend/app/mcp/factory_server.py", "host-bridge/forgehub_messages_mcp.py")


def _git(*args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True)
    if result.returncode:
        raise SystemExit(f"git {args[0]} failed: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout


def status() -> dict:
    current = MCP_HOME / "current"
    if not current.is_symlink():
        return {"current": None}
    target = Path(os.readlink(current))
    meta = target / "release.json"
    return {"current": str(target), **(json.loads(meta.read_text()) if meta.is_file() else {})}


def publish(ref: str) -> dict:
    commit = _git("rev-parse", "--verify", f"{ref}^{{commit}}").decode().strip()
    target = MCP_HOME / "releases" / commit[:12]
    if not target.exists():
        staging = target.with_name(target.name + ".tmp")
        if staging.exists():
            raise SystemExit(f"{staging} exists: an earlier publish was interrupted; inspect and remove it")
        archive = _git("archive", "--format=tar", commit, *PATHS)
        staging.mkdir(parents=True, mode=0o700)
        try:
            with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                tar.extractall(staging, filter="data")
            for entry in ENTRYPOINTS:
                if not (staging / entry).is_file():
                    raise SystemExit(f"{entry} missing at {commit[:12]}")
            for path in sorted(staging.rglob("*.py")):  # SyntaxError anywhere: never switched to
                compile(path.read_text(encoding="utf-8"), str(path), "exec")
            (staging / "release.json").write_text(json.dumps({
                "commit": commit,
                "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "paths": list(PATHS),
            }, indent=2) + "\n")
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        staging.rename(target)
    current = MCP_HOME / "current"
    previous = os.readlink(current) if current.is_symlink() else None
    temporary = MCP_HOME / "current.tmp"
    if temporary.is_symlink() or temporary.exists():
        temporary.unlink()
    temporary.symlink_to(target)
    temporary.rename(current)  # atomic on the same filesystem
    return {"commit": commit, "current": str(target), "previous": previous}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("ref", nargs="?", help="commit (or ref) to publish")
    parser.add_argument("--status", action="store_true", help="show what agents run now")
    args = parser.parse_args()
    if args.status or not args.ref:
        print(json.dumps(status(), indent=2))
        return 0
    print(json.dumps(publish(args.ref), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
