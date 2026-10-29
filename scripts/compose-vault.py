#!/usr/bin/env python3
"""Fetch the ForgeHub Darckware credential from ForgeVault before Compose."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

VAULT_URL = "http://127.0.0.1:8080"
TOKEN_CRED = Path("/root/.config/forgevault/forgehub-production-token")
SECRET_ID = "9f96a1a2-bbdf-40f3-b005-d7aa6ab29465"
IDENTITY_ID = "ccc59673-aff0-466b-8258-0ac488054d93"
SECRET_PATH = Path("/run/forgehub-secrets/darckware_agent_token")


def load_vault_token() -> str:
    result = subprocess.run(
        ["systemd-creds", "decrypt", str(TOKEN_CRED), "-"],
        check=True, capture_output=True, text=True, timeout=10,
    )
    token = result.stdout.strip()
    if not token.startswith("fv_sa_"):
        raise RuntimeError("Vault service credential has an invalid format")
    return token


def fetch_secret(vault_token: str) -> str:
    request = urllib.request.Request(
        f"{VAULT_URL}/api/v1/secrets/{SECRET_ID}/value?mode=REVEAL",
        headers={"Authorization": f"Bearer {vault_token}"},
    )
    last_error: Exception | None = None
    for attempt in range(12):
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                envelope = json.loads(response.read())
            break
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt == 11:
                raise
            time.sleep(5)
    else:
        raise RuntimeError("ForgeVault did not become available") from last_error
    if envelope.get("identity") != IDENTITY_ID or envelope.get("resource") != SECRET_ID:
        raise RuntimeError("ForgeVault returned a credential for a different identity or secret")
    if envelope.get("accessMode") != "REVEAL":
        raise RuntimeError("ForgeVault returned an unsupported credential mode")
    value = envelope.get("credentials", {}).get("value", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", value):
        raise RuntimeError("ForgeVault returned a credential with an invalid format")
    return value


def write_runtime_secret(value: str) -> None:
    SECRET_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(SECRET_PATH.parent, 0o700)
    fd, temporary_path = tempfile.mkstemp(prefix=".darckware-agent-", dir=SECRET_PATH.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(value.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, SECRET_PATH)
        dir_fd = os.open(SECRET_PATH.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: compose-vault.py <docker compose arguments>", file=sys.stderr)
        return 2
    try:
        write_runtime_secret(fetch_secret(load_vault_token()))
        return subprocess.run(["docker", "compose", *sys.argv[1:]], cwd="/root/project/forgehub", check=False).returncode
    except (OSError, subprocess.SubprocessError, urllib.error.URLError, ValueError, RuntimeError) as exc:
        # Keep response bodies and subprocess output out of logs; they can contain credentials.
        print(f"ForgeVault-backed ForgeHub deploy failed ({type(exc).__name__})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
