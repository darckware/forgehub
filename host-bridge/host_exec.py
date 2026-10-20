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
import os
import re
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Literal

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
    # Only for one-off runs on a machine ForgeHub has no key for yet ("Enroll
    # station" over SSH). Travels to sshpass through the environment, never
    # argv, and is never logged or stored.
    password: str | None = field(default=None, repr=False)
    # ssh-agent socket holding a key fetched from ForgeVault for this one run
    # (ephemeral_agent below); replaces `key` when set.
    agent_sock: str | None = None


def ssh_base(target: ExecTarget) -> list[str]:
    if target.password:
        args = [
            "sshpass", "-e", "ssh",
            "-o", "BatchMode=no",
            "-o", "PubkeyAuthentication=no",
            "-o", "PreferredAuthentications=password,keyboard-interactive",
            "-o", "NumberOfPasswordPrompts=1",
            "-o", "ConnectTimeout=10",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=4",
        ]
        if target.port != 22:
            args += ["-p", str(target.port)]
        return [*args, f"{target.user}@{target.host}"]
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
    if target.agent_sock:
        args += ["-o", f"IdentityAgent={target.agent_sock}"]
    elif target.key:
        args += ["-i", target.key, "-o", "IdentitiesOnly=yes"]
    if target.port != 22:
        args += ["-p", str(target.port)]
    return [*args, f"{target.user}@{target.host}"]


@contextlib.asynccontextmanager
async def ephemeral_agent(private_key: str):
    """An ssh-agent living only for one run, holding one key fetched from
    ForgeVault. The key goes to `ssh-add -` on stdin -- never to a file -- and
    the agent (and its socket dir, 0700) is gone when the block exits."""
    tmp = tempfile.mkdtemp(prefix="fh-agent-", dir="/dev/shm" if os.path.isdir("/dev/shm") else None)
    os.chmod(tmp, 0o700)
    sock = os.path.join(tmp, "agent.sock")
    agent = await asyncio.create_subprocess_exec(
        "ssh-agent", "-D", "-a", sock, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
    )
    try:
        for _ in range(50):
            if os.path.exists(sock):
                break
            await asyncio.sleep(0.05)
        add = await asyncio.create_subprocess_exec(
            "ssh-add", "-q", "-",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "SSH_AUTH_SOCK": sock},
        )
        _, err = await add.communicate((private_key.rstrip("\n") + "\n").encode())
        if add.returncode != 0:
            raise ValueError("Could not load the machine's key from ForgeVault")
        yield sock
    finally:
        with contextlib.suppress(ProcessLookupError):
            agent.kill()
        await agent.wait()
        shutil.rmtree(tmp, ignore_errors=True)


class AgentCache:
    """Long-lived counterpart of ephemeral_agent for interactive use (the
    Workspace SSH terminal and Explorer): one ssh-agent per ForgeVault key,
    reused while in use and killed after `ttl` seconds idle. The key still
    never touches a file -- it lives only in the agent's memory -- and the
    socket sits in a 0700 directory under /dev/shm."""

    def __init__(self, reveal: Callable[[str], Awaitable[str]], ttl: float = 1800.0):
        self._reveal = reveal
        self._ttl = ttl
        self._agents: dict[str, tuple[asyncio.subprocess.Process, str, str, float]] = {}
        self._lock = asyncio.Lock()
        self._reaper: asyncio.Task | None = None

    async def socket_for(self, key_ref: str) -> str:
        async with self._lock:
            entry = self._agents.get(key_ref)
            if entry and entry[0].returncode is None and os.path.exists(entry[1]):
                self._agents[key_ref] = (entry[0], entry[1], entry[2], time.monotonic())
                return entry[1]
            if entry:
                self._stop(key_ref)
            private_key = await self._reveal(key_ref)
            tmp = tempfile.mkdtemp(prefix="fh-agent-", dir="/dev/shm" if os.path.isdir("/dev/shm") else None)
            os.chmod(tmp, 0o700)
            sock = os.path.join(tmp, "agent.sock")
            agent = await asyncio.create_subprocess_exec(
                "ssh-agent", "-D", "-a", sock, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
            )
            for _ in range(50):
                if os.path.exists(sock):
                    break
                await asyncio.sleep(0.05)
            add = await asyncio.create_subprocess_exec(
                "ssh-add", "-q", "-", stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                env={**os.environ, "SSH_AUTH_SOCK": sock},
            )
            await add.communicate((private_key.rstrip("\n") + "\n").encode())
            if add.returncode != 0:
                with contextlib.suppress(ProcessLookupError):
                    agent.kill()
                shutil.rmtree(tmp, ignore_errors=True)
                raise ValueError("Could not load the machine's key from ForgeVault")
            self._agents[key_ref] = (agent, sock, tmp, time.monotonic())
            if self._reaper is None or self._reaper.done():
                self._reaper = asyncio.create_task(self._reap())
            return sock

    def _stop(self, key_ref: str) -> None:
        agent, _sock, tmp, _ = self._agents.pop(key_ref)
        with contextlib.suppress(ProcessLookupError):
            agent.kill()
        shutil.rmtree(tmp, ignore_errors=True)

    async def reap_idle(self) -> int:
        async with self._lock:
            idle = [ref for ref, (_, _, _, used) in self._agents.items() if time.monotonic() - used > self._ttl]
            for ref in idle:
                self._stop(ref)
            return len(idle)

    async def _reap(self) -> None:
        while self._agents:
            await asyncio.sleep(60)
            await self.reap_idle()


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


def _powershell_remote(script: str) -> str:
    return (
        "powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass "
        f"-EncodedCommand {encode_powershell(script)}"
    )


def build_command(target: ExecTarget, shell: Shell, script: str) -> tuple[list[str], bytes | None]:
    """argv for the local `ssh` and the bytes to feed its stdin. A PowerShell
    script longer than MAX_POWERSHELL_CHARS doesn't fit cmd.exe's command line;
    run_script uploads those in chunks instead (powershell_upload_commands)."""
    if shell == "sh":
        return [*ssh_base(target), "sh -s"], script.encode()
    if len(script) > MAX_POWERSHELL_CHARS:
        raise ValueError(f"PowerShell script is limited to {MAX_POWERSHELL_CHARS} characters in one command")
    return [*ssh_base(target), _powershell_remote(POWERSHELL_PRELUDE + script)], None


UPLOAD_CHUNK_BYTES = 1500


def powershell_upload_commands(script: str, token: str | None = None) -> tuple[list[str], str]:
    """Remote commands that write the script to %TEMP% piece by piece (UTF-8
    with BOM, so Windows PowerShell 5.1 reads accents right) and one that runs
    it as a file and deletes it. Each piece fits cmd.exe's 8191-char line."""
    token = token or uuid.uuid4().hex
    path = f"$env:TEMP\\forgehub-{token}.ps1"
    data = (POWERSHELL_PRELUDE + script).encode("utf-8")
    uploads = []
    for i in range(0, len(data), UPLOAD_CHUNK_BYTES):
        b64 = base64.b64encode(data[i:i + UPLOAD_CHUNK_BYTES]).decode("ascii")
        uploads.append(_powershell_remote(
            f'[IO.File]::AppendAllText("{path}", '
            f"[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{b64}')), [Text.Encoding]::UTF8)"
        ))
    run = _powershell_remote(
        f'& powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{path}"; '
        f'$c = $LASTEXITCODE; Remove-Item -Force "{path}" -ErrorAction SilentlyContinue; exit $c'
    )
    return [*uploads, run], path


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


async def _exec_once(
    argv: list[str], stdin: bytes | None, timeout: float, env: dict | None
) -> tuple[int | None, bytes, bytes, bool, bool]:
    """(exit_code or None on timeout, stdout, stderr, truncated, timed_out)."""
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    async def feed() -> None:
        if stdin is not None and proc.stdin is not None:
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                proc.stdin.write(stdin)
                await proc.stdin.drain()
            proc.stdin.close()

    gathered = asyncio.gather(
        feed(),
        _read_capped(proc.stdout, MAX_OUTPUT_BYTES),
        _read_capped(proc.stderr, MAX_OUTPUT_BYTES),
        proc.wait(),
    )
    try:
        _, (out, out_cut), (err, err_cut), _ = await asyncio.wait_for(gathered, timeout=timeout)
    except asyncio.TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.wait()
        return None, b"", b"", False, True
    return proc.returncode, out, err, out_cut or err_cut, False


def _env_for(target: ExecTarget) -> dict | None:
    if not target.password:
        return None
    return {**os.environ, "SSHPASS": target.password}


async def run_script(
    target: ExecTarget,
    shell: Shell,
    script: str,
    timeout: float,
    *,
    build: Callable[[ExecTarget, Shell, str], tuple[list[str], bytes | None]] | None = None,
) -> dict:
    started = time.monotonic()
    env = _env_for(target)
    if shell == "powershell" and len(script) > MAX_POWERSHELL_CHARS and build is None:
        commands, _ = powershell_upload_commands(script)
        base = ssh_base(target)
        for upload in commands[:-1]:
            code, _out, err, _cut, timed_out = await _exec_once([*base, upload], None, 60, env)
            if timed_out or code != 0:
                stderr = decode_clixml(err.decode(errors="replace"))
                return {
                    "exit_code": None if timed_out else code, "stdout": "",
                    "stderr": "Could not upload the script to the machine.\n" + stderr,
                    "truncated": False, "timed_out": timed_out,
                    "duration_ms": int((time.monotonic() - started) * 1000),
                    "failure": classify_failure(code, stderr, timed_out) or "command",
                }
        argv, stdin = [*base, commands[-1]], None
    else:
        argv, stdin = (build or build_command)(target, shell, script)
    remaining = max(5.0, timeout - (time.monotonic() - started))
    exit_code, out, err, truncated, timed_out = await _exec_once(argv, stdin, remaining, env)
    stderr = err.decode(errors="replace")
    if shell == "powershell":
        stderr = decode_clixml(stderr)
    return {
        "exit_code": exit_code,
        "stdout": out.decode(errors="replace"),
        "stderr": stderr,
        "truncated": truncated,
        "timed_out": timed_out,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "failure": classify_failure(exit_code, stderr, timed_out),
    }


async def detect_os(target: ExecTarget) -> dict:
    """Which OS answers on the other side: `uname -s` first (Linux/macOS),
    then PowerShell (Windows). Raises ValueError("auth"/"connection") when
    the login itself fails."""
    env = _env_for(target)
    base = ssh_base(target)
    code, out, err, _cut, timed_out = await _exec_once([*base, "uname -s"], None, 30, env)
    text = out.decode(errors="replace").strip()
    if code == 255 or timed_out:
        failure = classify_failure(code, err.decode(errors="replace"), timed_out)
        raise ValueError(failure if failure in ("auth", "connection") else "connection")
    if code == 0 and text in ("Linux", "Darwin"):
        return {"os_family": "linux" if text == "Linux" else "macos", "detail": text}
    code, out, _err, _cut, _to = await _exec_once(
        [*base, _powershell_remote("[Environment]::OSVersion.VersionString")], None, 60, env
    )
    text = out.decode(errors="replace").strip()
    if code == 0 and "Windows" in text:
        return {"os_family": "windows", "detail": text}
    return {"os_family": None, "detail": text[:200] or "unknown"}


class ExecRequest(BaseModel):
    host: str
    user: str
    port: int = Field(default=22, ge=1, le=65535)
    key_path: str | None = None
    # ForgeVault secret id of the machine's private key; preferred over key_path.
    key_ref: str | None = Field(default=None, min_length=36, max_length=36)
    password: str | None = Field(default=None, min_length=1, max_length=256)
    shell: Shell
    script: str = Field(min_length=1, max_length=200_000)
    timeout_seconds: int = Field(default=300, ge=5, le=MAX_TIMEOUT_SECONDS)


class DetectOsRequest(BaseModel):
    host: str
    user: str
    port: int = Field(default=22, ge=1, le=65535)
    key_path: str | None = None
    key_ref: str | None = Field(default=None, min_length=36, max_length=36)
    password: str | None = Field(default=None, min_length=1, max_length=256)


class ForgetHostKeyRequest(BaseModel):
    host: str
    port: int = Field(default=22, ge=1, le=65535)


KNOWN_HOSTS = os.path.expanduser("~/.ssh/known_hosts")


async def forget_host_key(host: str, port: int, known_hosts: str = KNOWN_HOSTS) -> bool:
    """Drops the recorded host key of one address from this host's
    known_hosts, so the next connection records the machine's new key
    (trust on first use again). Returns whether an entry existed."""
    name = host if port == 22 else f"[{host}]:{port}"
    proc = await asyncio.create_subprocess_exec(
        "ssh-keygen", "-R", name, "-f", known_hosts,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    text = (out + err).decode(errors="replace")
    if proc.returncode != 0 and "not found" not in text:
        raise RuntimeError(text.strip()[:300] or "ssh-keygen failed")
    return "updated" in text or "removed" in text.lower()


def make_host_exec_router(
    check_token: Callable[[str | None], None],
    resolve_key_path: Callable[[str], str],
    reveal_secret: Callable[[str], Awaitable[str]] | None = None,
) -> APIRouter:
    router = APIRouter()

    @contextlib.asynccontextmanager
    async def target_for(req):
        """The run's ExecTarget; with key_ref, the key comes from ForgeVault into
        an agent that exists only inside this block."""
        if req.key_ref:
            if reveal_secret is None:
                raise HTTPException(status_code=503, detail="ForgeVault is not available on this bridge")
            private_key = await reveal_secret(req.key_ref)
            async with ephemeral_agent(private_key) as sock:
                yield ExecTarget(host=req.host, user=req.user, port=req.port, agent_sock=sock)
            return
        yield _target(req)

    @router.post("/v1/servers/forget-host-key")
    async def forget_server_host_key(req: ForgetHostKeyRequest, x_bridge_token: str | None = Header(default=None)) -> dict:
        check_token(x_bridge_token)
        if not _HOST_RE.match(req.host):
            raise HTTPException(status_code=400, detail="Invalid host")
        try:
            return {"removed": await forget_host_key(req.host, req.port)}
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.post("/v1/servers/exec")
    async def exec_on_server(req: ExecRequest, x_bridge_token: str | None = Header(default=None)) -> dict:
        check_token(x_bridge_token)
        if not _HOST_RE.match(req.host):
            raise HTTPException(status_code=400, detail="Invalid host")
        if not _USER_RE.match(req.user):
            raise HTTPException(status_code=400, detail="Invalid user")
        try:
            async with target_for(req) as target:
                return await run_script(target, req.shell, req.script, req.timeout_seconds)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/v1/servers/detect-os")
    async def detect_server_os(req: DetectOsRequest, x_bridge_token: str | None = Header(default=None)) -> dict:
        check_token(x_bridge_token)
        if not _HOST_RE.match(req.host):
            raise HTTPException(status_code=400, detail="Invalid host")
        if not _USER_RE.match(req.user):
            raise HTTPException(status_code=400, detail="Invalid user")
        try:
            async with target_for(req) as target:
                return await detect_os(target)
        except ValueError as exc:
            reason = str(exc)
            detail = "Login refused (check user and password)" if reason == "auth" else "Machine unreachable on SSH"
            raise HTTPException(status_code=502, detail=detail) from exc

    def _target(req) -> ExecTarget:
        return ExecTarget(
            host=req.host,
            user=req.user,
            port=req.port,
            key=resolve_key_path(req.key_path) if req.key_path else None,
            password=req.password,
        )

    return router


__all__ = ["ExecTarget", "build_command", "make_host_exec_router", "run_script"]
