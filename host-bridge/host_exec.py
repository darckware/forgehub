"""Run one script on one machine over SSH -- Remote Access phase 4
(docs/architecture/REMOTE_MAINTENANCE_PLAN.md).

forgehub-backend owns the execution record (who, what, where, result) and
calls `POST /v1/servers/exec` once per machine; this module only runs the
script and reports what happened. Same transport as the Workspace terminal
and Explorer: this host's own `ssh`, BatchMode (never a prompt), the row's key
when set, otherwise this host's ~/.ssh defaults.

How the script reaches the remote side:

* **sh** (Linux/macOS): `ssh <target> sh -s` with the script on stdin -- no
  quoting of the script at all, any size.
* **powershell** (Windows OpenSSH, whose default shell is cmd.exe):
  `powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass
  -EncodedCommand <base64 UTF-16LE>`. Encoded so no cmd.exe/PowerShell quoting
  can mangle it; the price is cmd.exe's 8191-char command line, which caps a
  script at MAX_POWERSHELL_CHARS. Larger scripts arrive with the script
  library (phase 5), copied to the station first.

Output is capped per stream (MAX_OUTPUT_BYTES) while it is read, so a runaway
command can't grow this process's memory; the rest is drained and dropped.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import html
import re
import time
from dataclasses import dataclass
from typing import Callable, Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

Shell = Literal["sh", "powershell"]

MAX_OUTPUT_BYTES = 64 * 1024
MAX_TIMEOUT_SECONDS = 1800
MAX_POWERSHELL_CHARS = 2800
_HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_USER_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class ExecTarget:
    host: str
    user: str
    port: int = 22
    key: str | None = None


def ssh_base(target: ExecTarget) -> list[str]:
    args = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10",
        # Trust on first use until phase 3 pins each station's host key at
        # preparation; a key that *changes* afterwards is refused.
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=4",
    ]
    if target.key:
        args += ["-i", target.key, "-o", "IdentitiesOnly=yes"]
    if target.port != 22:
        args += ["-p", str(target.port)]
    return [*args, f"{target.user}@{target.host}"]


# Prepended to every PowerShell script: no progress records (PowerShell
# serializes them to stderr as CLIXML when it isn't attached to a console),
# and UTF-8 out so accents survive.
POWERSHELL_PRELUDE = (
    "$ProgressPreference='SilentlyContinue';"
    "[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
    "$OutputEncoding=[Text.Encoding]::UTF8\n"
)
_CLIXML_ERROR_RE = re.compile(r'<S S="Error">(.*?)</S>', re.S)
_CLIXML_ESCAPE_RE = re.compile(r"_x([0-9A-Fa-f]{4})_")


def decode_clixml(stderr: str) -> str:
    """PowerShell's `#< CLIXML` stderr -> the plain error lines it carries
    (progress and other records dropped). Anything else is returned as is."""
    if not stderr.lstrip().startswith("#< CLIXML"):
        return stderr
    parts = [
        _CLIXML_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), html.unescape(chunk))
        for chunk in _CLIXML_ERROR_RE.findall(stderr)
    ]
    return "".join(parts).replace("\r\n", "\n")


def encode_powershell(script: str) -> str:
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def build_command(target: ExecTarget, shell: Shell, script: str) -> tuple[list[str], bytes | None]:
    """argv for the local `ssh` and the bytes to feed its stdin."""
    if shell == "sh":
        return [*ssh_base(target), "sh -s"], script.encode()
    if len(script) > MAX_POWERSHELL_CHARS:
        raise ValueError(f"PowerShell script is limited to {MAX_POWERSHELL_CHARS} characters for now")
    remote = (
        "powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass "
        f"-EncodedCommand {encode_powershell(POWERSHELL_PRELUDE + script)}"
    )
    return [*ssh_base(target), remote], None


async def _read_capped(stream: asyncio.StreamReader, cap: int) -> tuple[bytes, bool]:
    kept = bytearray()
    truncated = False
    while chunk := await stream.read(65536):
        room = cap - len(kept)
        if room > 0:
            kept += chunk[:room]
        if len(chunk) > room:
            truncated = True
    return bytes(kept), truncated


def classify_failure(exit_code: int | None, stderr: str, timed_out: bool) -> str | None:
    """None on success; otherwise why it failed, in terms the screen can show:
    "timeout", "auth" (key refused), "connection" (unreachable / ssh error,
    i.e. the script never ran) or "command" (it ran and exited non-zero)."""
    if timed_out:
        return "timeout"
    if exit_code == 0:
        return None
    if exit_code == 255:
        low = stderr.lower()
        if "permission denied" in low or "host key verification failed" in low:
            return "auth"
        return "connection"
    return "command"


async def run_script(
    target: ExecTarget,
    shell: Shell,
    script: str,
    timeout: float,
    *,
    build: Callable[[ExecTarget, Shell, str], tuple[list[str], bytes | None]] | None = None,
) -> dict:
    argv, stdin = (build or build_command)(target, shell, script)
    started = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    async def feed() -> None:
        if stdin is not None and proc.stdin is not None:
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                proc.stdin.write(stdin)
                await proc.stdin.drain()
            proc.stdin.close()

    timed_out = False
    gathered = asyncio.gather(
        feed(),
        _read_capped(proc.stdout, MAX_OUTPUT_BYTES),
        _read_capped(proc.stderr, MAX_OUTPUT_BYTES),
        proc.wait(),
    )
    try:
        _, (out, out_cut), (err, err_cut), _ = await asyncio.wait_for(gathered, timeout=timeout)
    except asyncio.TimeoutError:
        timed_out = True
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.wait()
        out, out_cut, err, err_cut = b"", False, b"", False
    stderr = decode_clixml(err.decode(errors="replace")) if shell == "powershell" else err.decode(errors="replace")
    exit_code = None if timed_out else proc.returncode
    return {
        "exit_code": exit_code,
        "stdout": out.decode(errors="replace"),
        "stderr": stderr,
        "truncated": out_cut or err_cut,
        "timed_out": timed_out,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "failure": classify_failure(exit_code, stderr, timed_out),
    }


class ExecRequest(BaseModel):
    host: str
    user: str
    port: int = Field(default=22, ge=1, le=65535)
    key_path: str | None = None
    shell: Shell
    script: str = Field(min_length=1, max_length=200_000)
    timeout_seconds: int = Field(default=300, ge=5, le=MAX_TIMEOUT_SECONDS)


def make_host_exec_router(
    check_token: Callable[[str | None], None], resolve_key_path: Callable[[str], str]
) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/servers/exec")
    async def exec_on_server(req: ExecRequest, x_bridge_token: str | None = Header(default=None)) -> dict:
        check_token(x_bridge_token)
        if not _HOST_RE.match(req.host):
            raise HTTPException(status_code=400, detail="Invalid host")
        if not _USER_RE.match(req.user):
            raise HTTPException(status_code=400, detail="Invalid user")
        target = ExecTarget(
            host=req.host,
            user=req.user,
            port=req.port,
            key=resolve_key_path(req.key_path) if req.key_path else None,
        )
        try:
            return await run_script(target, req.shell, req.script, req.timeout_seconds)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router


__all__ = ["ExecTarget", "build_command", "make_host_exec_router", "run_script"]
