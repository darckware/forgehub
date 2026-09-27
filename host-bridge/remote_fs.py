"""Workspace Explorer over SSH -- the /v1/fs/* file manager, on a remote server.

2026-09-27 (Marcelo: "quando a aba da ssh estiver sendo usada o explorer deve
usar o servidor do ssh e quando estiver usando a aba do terminal deve usar o
servidor vps"). Every route here mirrors one of app.py's /v1/fs/* routes --
same query/body, same response shape, same status codes -- so forgehub-
backend's file_explorer.py only swaps the path prefix and adds the target.

The target arrives in X-Ssh-Host / X-Ssh-User / X-Ssh-Port / X-Ssh-Key headers
(uniform across GET, JSON bodies and the streamed upload). The work runs
through this host's own `ssh` binary, the one the Workspace SSH terminal uses,
so it authenticates exactly like that terminal: the server's `ssh_key_path`
when set, otherwise this host's ~/.ssh defaults and config. Two deliberate
choices:

* **Nothing is installed on the remote.** Each operation is a short POSIX sh
  script (GNU find/coreutils, present on every mainstream distro), passed as
  arguments rather than interpolated, so a file name is never shell syntax.
* **BatchMode, never a prompt.** A server reachable only by password fails
  fast with a clear message; the terminal (which can prompt) stays the way
  in for those. Connections are multiplexed (ControlMaster), so browsing
  doesn't pay a full SSH handshake per click.

Scripts report failures with an exit code (see _STATUS_BY_EXIT) and the
message on stderr, which becomes the HTTP detail.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import posixpath
import re
import shlex
import uuid
from dataclasses import dataclass
from typing import AsyncIterator, Callable

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

_CONTROL_DIR = os.path.expanduser("~/.cache/forgehub-explorer-ssh")
_MAX_READABLE_FILE_BYTES = 2 * 1024 * 1024
_CHUNK = 1024 * 1024

# Same skip lists as app.py's local search.
_SEARCH_SKIP_DIRS = (
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".next", ".nuxt", ".turbo", ".parcel-cache", ".cache",
)
_SEARCH_SKIP_ROOTS = ("/proc", "/sys", "/dev", "/run", "/snap")

# Exit codes the scripts below use; anything else is a 500.
_STATUS_BY_EXIT = {43: 403, 44: 404, 45: 413, 46: 409, 47: 400, 48: 409, 127: 501}

_HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_USER_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")


class FsEntry(BaseModel):
    name: str
    path: str
    type: str
    size: int | None = None
    modified: float | None = None
    is_symlink: bool = False


class FsListResponse(BaseModel):
    path: str
    parent: str | None
    entries: list[FsEntry]


class FsContent(BaseModel):
    path: str
    content: str


class FsWriteRequest(BaseModel):
    path: str
    content: str


class FsPathRequest(BaseModel):
    path: str


class FsRenameRequest(BaseModel):
    path: str
    new_path: str


class FsSearchResponse(BaseModel):
    path: str
    query: str
    entries: list[FsEntry]
    truncated: bool


class FsZipRequest(BaseModel):
    paths: list[str] = Field(min_length=1, max_length=1000)
    name: str = "download.zip"


@dataclass(frozen=True)
class SshTarget:
    host: str
    user: str
    port: int
    key: str | None

    @property
    def label(self) -> str:
        return f"{self.user}@{self.host}"


def ssh_args(target: SshTarget) -> list[str]:
    args = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=8",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ControlMaster=auto",
        "-o", f"ControlPath={_CONTROL_DIR}/%C",
        "-o", "ControlPersist=300",
        "-o", "ServerAliveInterval=15",
    ]
    if target.key:
        args += ["-i", target.key, "-o", "IdentitiesOnly=yes"]
    if target.port != 22:
        args += ["-p", str(target.port)]
    return [*args, target.label]


def remote_command(script: str, *args: str) -> str:
    """The remote side runs this through the login shell, so the script and
    every argument are quoted once each: `sh -c <script> sh <arg>...`."""
    return " ".join(["sh", "-c", shlex.quote(f"export LC_ALL=C\n{script}"), "sh", *(shlex.quote(a) for a in args)])


def _ssh_error_detail(target: SshTarget, stderr: str) -> str:
    text = stderr.strip()
    lowered = text.lower()
    if "permission denied" in lowered:
        return (
            f"SSH authentication failed for {target.label}. The Explorer needs key-based access "
            "(it can't type a password); use the SSH terminal for this server, or install a key."
        )
    if any(s in lowered for s in ("timed out", "no route to host", "connection refused", "could not resolve")):
        return f"Cannot reach {target.label}: {text.splitlines()[-1]}"
    return f"SSH to {target.label} failed: {text.splitlines()[-1] if text else 'unknown error'}"


def raise_for_exit(target: SshTarget, code: int, stderr: str, default: str = "Remote operation failed") -> None:
    if code == 0:
        return
    if code == 255:
        raise HTTPException(status_code=502, detail=_ssh_error_detail(target, stderr))
    if code == 127:
        raise HTTPException(
            status_code=501,
            detail=f"A required command is missing on {target.label} (the Explorer needs GNU find/coreutils)",
        )
    if code == 124:
        raise HTTPException(status_code=504, detail=f"{target.label} took too long to answer")
    raise HTTPException(status_code=_STATUS_BY_EXIT.get(code, 500), detail=stderr.strip() or default)


async def run(
    target: SshTarget, script: str, *args: str, stdin: bytes | None = None, timeout: float = 60.0
) -> tuple[int, bytes, str]:
    os.makedirs(_CONTROL_DIR, mode=0o700, exist_ok=True)
    proc = await asyncio.create_subprocess_exec(
        *ssh_args(target),
        remote_command(script, *args),
        stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(stdin), timeout=timeout)
    except asyncio.TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        return 124, b"", "timed out"
    return proc.returncode or 0, out, err.decode(errors="replace")


async def run_ok(target: SshTarget, script: str, *args: str, stdin: bytes | None = None, timeout: float = 60.0) -> bytes:
    code, out, err = await run(target, script, *args, stdin=stdin, timeout=timeout)
    raise_for_exit(target, code, err)
    return out


# `find -printf` record: type-following-links, own type, size, mtime, name.
_ENTRY_FORMAT = r"%Y\t%y\t%s\t%T@\t%p\0"


def parse_entries(raw: bytes) -> list[FsEntry]:
    entries = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        parts = record.decode(errors="replace").split("\t", 4)
        if len(parts) != 5:
            continue
        followed, own, size, mtime, path = parts
        if followed in ("", "L", "N", "?"):
            continue  # broken symlink or loop -- skipped, like the local listing
        is_dir = followed == "d"
        is_link = own == "l"
        try:
            modified = float(mtime)
        except ValueError:
            modified = None
        entries.append(
            FsEntry(
                name=posixpath.basename(path.rstrip("/")) or path,
                path=path,
                type="dir" if is_dir else "file",
                size=None if is_dir or is_link or not size.isdigit() else int(size),
                modified=modified,
                is_symlink=is_link,
            )
        )
    return entries


def _parent(path: str) -> str | None:
    parent = posixpath.dirname(path.rstrip("/")) or "/"
    return None if path == "/" else parent


def _download_headers(filename: str, size: int | None) -> dict[str, str]:
    from urllib.parse import quote

    headers = {
        "Content-Disposition": (
            f"attachment; filename=\"{filename.encode('ascii', 'replace').decode().replace(chr(34), '_')}\"; "
            f"filename*=UTF-8''{quote(filename)}"
        )
    }
    if size is not None:
        headers["Content-Length"] = str(size)
    return headers


async def _stream(target: SshTarget, script: str, *args: str) -> AsyncIterator[bytes]:
    """Relay a remote command's stdout. Everything that can fail with a clear
    message is checked before this starts; once bytes flow, the status line is
    already sent, so a mid-stream failure can only cut the download short."""
    proc = await asyncio.create_subprocess_exec(
        *ssh_args(target),
        remote_command(script, *args),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        assert proc.stdout is not None
        while chunk := await proc.stdout.read(_CHUNK):
            yield chunk
        await proc.wait()
    finally:
        if proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()


def make_remote_fs_router(
    check_token: Callable[[str | None], None], resolve_key_path: Callable[[str], str]
) -> APIRouter:
    router = APIRouter(prefix="/v1/remote-fs")

    def target_of(
        token: str | None, host: str | None, user: str | None, port: str | None, key: str | None
    ) -> SshTarget:
        check_token(token)
        if not host or not _HOST_RE.match(host):
            raise HTTPException(status_code=400, detail="Invalid or missing X-Ssh-Host")
        if not user or not _USER_RE.match(user):
            raise HTTPException(status_code=400, detail="Invalid or missing X-Ssh-User")
        try:
            port_number = int(port or 22)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid X-Ssh-Port") from None
        if not 1 <= port_number <= 65535:
            raise HTTPException(status_code=400, detail="Invalid X-Ssh-Port")
        return SshTarget(host=host, user=user, port=port_number, key=resolve_key_path(key) if key else None)

    # One dependency shared by every route: FastAPI reads the headers by
    # parameter name (x_ssh_host -> X-Ssh-Host).
    def headers(
        x_bridge_token: str | None = Header(default=None),
        x_ssh_host: str | None = Header(default=None),
        x_ssh_user: str | None = Header(default=None),
        x_ssh_port: str | None = Header(default=None),
        x_ssh_key: str | None = Header(default=None),
    ) -> SshTarget:
        return target_of(x_bridge_token, x_ssh_host, x_ssh_user, x_ssh_port, x_ssh_key)

    Target = Depends(headers)

    @router.get("/list", response_model=FsListResponse)
    async def list_dir(path: str | None = Query(default=None), target: SshTarget = Target) -> FsListResponse:
        out = await run_ok(
            target,
            'd="${1:-$HOME}"\n'
            '[ -d "$d" ] || { echo "Not a directory" >&2; exit 44; }\n'
            '[ -r "$d" ] && [ -x "$d" ] || { echo "Permission denied" >&2; exit 43; }\n'
            'printf "%s\\0" "$d"\n'
            f'find "$d" -mindepth 1 -maxdepth 1 -printf \'{_ENTRY_FORMAT}\' 2>/dev/null\n'
            "exit 0",
            path or "",
        )
        head, _, rest = out.partition(b"\0")
        directory = head.decode(errors="replace")
        entries = sorted(parse_entries(rest), key=lambda e: (e.type != "dir", e.name.lower()))
        return FsListResponse(path=directory, parent=_parent(directory), entries=entries)

    @router.get("/read", response_model=FsContent)
    async def read(path: str = Query(...), target: SshTarget = Target) -> FsContent:
        out = await run_ok(
            target,
            '[ -f "$1" ] || { echo "File not found" >&2; exit 44; }\n'
            's=$(stat -c %s -- "$1")\n'
            '[ "$s" -le "$2" ] || { echo "File too large to view ($s bytes)" >&2; exit 45; }\n'
            'exec cat -- "$1"',
            path,
            str(_MAX_READABLE_FILE_BYTES),
        )
        if b"\x00" in out:
            raise HTTPException(status_code=415, detail="File appears to be binary")
        return FsContent(path=path, content=out.decode("utf-8", errors="replace"))

    @router.put("/write", response_model=FsContent)
    async def write(req: FsWriteRequest, target: SshTarget = Target) -> FsContent:
        await run_ok(
            target,
            'mkdir -p -- "$(dirname -- "$1")" && cat > "$1"',
            req.path,
            stdin=req.content.encode("utf-8"),
        )
        return FsContent(path=req.path, content=req.content)

    @router.post("/mkdir", response_model=FsEntry)
    async def mkdir(req: FsPathRequest, target: SshTarget = Target) -> FsEntry:
        await run_ok(
            target,
            '{ [ -e "$1" ] || [ -L "$1" ]; } && { echo "Already exists" >&2; exit 46; }\n'
            'mkdir -p -- "$1"',
            req.path,
        )
        return FsEntry(name=posixpath.basename(req.path), path=req.path, type="dir")

    @router.post("/create-file", response_model=FsEntry)
    async def create_file(req: FsPathRequest, target: SshTarget = Target) -> FsEntry:
        await run_ok(
            target,
            '{ [ -e "$1" ] || [ -L "$1" ]; } && { echo "Already exists" >&2; exit 46; }\n'
            'mkdir -p -- "$(dirname -- "$1")" && : > "$1"',
            req.path,
        )
        return FsEntry(name=posixpath.basename(req.path), path=req.path, type="file", size=0)

    @router.patch("/rename", response_model=FsEntry)
    async def rename(req: FsRenameRequest, target: SshTarget = Target) -> FsEntry:
        out = await run_ok(
            target,
            '{ [ -e "$1" ] || [ -L "$1" ]; } || { echo "Source not found" >&2; exit 44; }\n'
            '{ [ -e "$2" ] || [ -L "$2" ]; } && { echo "Destination already exists" >&2; exit 46; }\n'
            'mkdir -p -- "$(dirname -- "$2")" && mv -- "$1" "$2" || exit 1\n'
            '[ -d "$2" ] && echo dir || echo file',
            req.path,
            req.new_path,
        )
        kind = "dir" if out.strip() == b"dir" else "file"
        return FsEntry(name=posixpath.basename(req.new_path), path=req.new_path, type=kind)

    @router.delete("/delete")
    async def delete(
        path: str = Query(...), recursive: bool = Query(default=False), target: SshTarget = Target
    ) -> dict:
        await run_ok(
            target,
            '{ [ -e "$1" ] || [ -L "$1" ]; } || { echo "Not found" >&2; exit 44; }\n'
            'if [ -d "$1" ] && [ ! -L "$1" ]; then\n'
            '  if [ "$2" != 1 ] && [ -n "$(ls -A -- "$1")" ]; then\n'
            '    echo "Directory not empty (pass recursive=true to delete anyway)" >&2; exit 47\n'
            "  fi\n"
            '  rm -rf -- "$1"\n'
            "else\n"
            '  rm -f -- "$1"\n'
            "fi",
            path,
            "1" if recursive else "0",
            timeout=300.0,
        )
        return {"status": "ok"}

    @router.get("/search", response_model=FsSearchResponse)
    async def search(
        path: str = Query(...),
        q: str = Query(..., min_length=1),
        limit: int = Query(default=500, ge=1, le=5000),
        target: SshTarget = Target,
    ) -> FsSearchResponse:
        query = q.strip()
        pattern = query if any(ch in query for ch in "*?[") else f"*{query}*"
        prune_names = " -o ".join(f"-name {shlex.quote(n)}" for n in _SEARCH_SKIP_DIRS)
        prune_roots = " -o ".join(f"-path {shlex.quote(r)}" for r in _SEARCH_SKIP_ROOTS)
        out = await run_ok(
            target,
            '[ -d "$1" ] || { echo "Not a directory" >&2; exit 44; }\n'
            "{ timeout 10 find \"$1\" \\( \\( -type d \\( "
            + prune_names
            + " \\) \\) -o "
            + prune_roots
            + f" \\) -prune -o -iname \"$2\" -printf '{_ENTRY_FORMAT}' 2>/dev/null;"
            ' printf "RC:%s\\0" "$?"; } | head -z -n "$3"',
            path,
            pattern,
            str(limit + 2),
            timeout=30.0,
        )
        records = [r for r in out.split(b"\0") if r]
        rc_records = [r for r in records if r.startswith(b"RC:")]
        entries = parse_entries(b"\0".join(r for r in records if not r.startswith(b"RC:")))
        timed_out = bool(rc_records) and rc_records[-1] == b"RC:124"
        truncated = timed_out or not rc_records or len(entries) > limit
        return FsSearchResponse(path=path, query=q, entries=entries[:limit], truncated=truncated)

    @router.post("/copy", response_model=FsEntry)
    async def copy(req: FsRenameRequest, target: SshTarget = Target) -> FsEntry:
        out = await run_ok(
            target,
            '{ [ -e "$1" ] || [ -L "$1" ]; } || { echo "Source not found" >&2; exit 44; }\n'
            '{ [ -e "$2" ] || [ -L "$2" ]; } && { echo "Destination already exists" >&2; exit 46; }\n'
            'if [ -d "$1" ]; then case "$2/" in "$1"/*) echo "Cannot copy a folder into itself" >&2; exit 47;; esac; fi\n'
            'mkdir -p -- "$(dirname -- "$2")" && cp -a -- "$1" "$2" || exit 1\n'
            f"find \"$2\" -maxdepth 0 -printf '{_ENTRY_FORMAT}'",
            req.path,
            req.new_path,
            timeout=600.0,
        )
        entries = parse_entries(out)
        if not entries:
            return FsEntry(name=posixpath.basename(req.new_path), path=req.new_path, type="file")
        return entries[0]

    @router.get("/download")
    async def download(path: str = Query(...), target: SshTarget = Target):
        """A file streams as-is; a folder as .tar.gz (the remote may have no
        zip, but always has tar)."""
        out = await run_ok(
            target,
            '{ [ -e "$1" ] || [ -L "$1" ]; } || { echo "Not found" >&2; exit 44; }\n'
            '[ -r "$1" ] || { echo "Permission denied" >&2; exit 43; }\n'
            'if [ -d "$1" ]; then echo dir; else stat -L -c %s -- "$1"; fi',
            path,
        )
        name = posixpath.basename(path.rstrip("/")) or "root"
        if out.strip() == b"dir":
            parent = posixpath.dirname(path.rstrip("/")) or "/"
            body = _stream(target, 'exec tar -czf - -C "$1" -- "$2"', parent, name)
            return StreamingResponse(body, media_type="application/gzip", headers=_download_headers(f"{name}.tar.gz", None))
        size = int(out.strip() or 0)
        body = _stream(target, 'exec cat -- "$1"', path)
        return StreamingResponse(body, media_type="application/octet-stream", headers=_download_headers(name, size))

    @router.post("/download-zip")
    async def download_zip(req: FsZipRequest, target: SshTarget = Target):
        """Multi-selection download as one .tar.gz. Items sharing a folder are
        stored by name; a selection spanning folders (search results) keeps
        each item's path from /."""
        names = [posixpath.basename(p.rstrip("/")) for p in req.paths]
        if len(set(names)) != len(names):
            raise HTTPException(status_code=400, detail="Selected items share a name; download them separately")
        await run_ok(
            target,
            'for p in "$@"; do { [ -e "$p" ] || [ -L "$p" ]; } || { echo "Not found: $p" >&2; exit 44; }; done',
            *req.paths,
        )
        parents = {posixpath.dirname(p.rstrip("/")) or "/" for p in req.paths}
        if len(parents) == 1:
            base, members = parents.pop(), names
        else:
            base, members = "/", [p.lstrip("/") for p in req.paths]
        archive = posixpath.basename(req.name) or "download.zip"
        archive = (archive[:-4] if archive.lower().endswith(".zip") else archive) + ".tar.gz"
        body = _stream(target, 'cd -- "$1" && shift && exec tar -czf - -- "$@"', base, *members)
        return StreamingResponse(body, media_type="application/gzip", headers=_download_headers(archive, None))

    @router.put("/upload", response_model=FsEntry)
    async def upload(
        request: Request,
        path: str = Query(...),
        overwrite: bool = Query(default=False),
        target: SshTarget = Target,
    ) -> FsEntry:
        """Same guarantees as the local upload: parents created on demand,
        409 on an existing file unless overwrite, and the body lands in a
        sibling temp file renamed into place only once complete."""
        await run_ok(
            target,
            'p=$(dirname -- "$1")\n'
            '[ -e "$p" ] && [ ! -d "$p" ] && { echo "Destination parent is a file" >&2; exit 48; }\n'
            '[ -d "$1" ] && { echo "A folder with this name already exists" >&2; exit 46; }\n'
            '[ -e "$1" ] && [ "$2" != 1 ] && { echo "File already exists" >&2; exit 46; }\n'
            "exit 0",
            path,
            "1" if overwrite else "0",
        )
        tmp = posixpath.join(posixpath.dirname(path), f".{posixpath.basename(path)}.{uuid.uuid4().hex[:8]}.part")
        os.makedirs(_CONTROL_DIR, mode=0o700, exist_ok=True)
        proc = await asyncio.create_subprocess_exec(
            *ssh_args(target),
            remote_command(
                'mkdir -p -- "$(dirname -- "$1")" || exit 1\n'
                'if cat > "$2"; then mv -f -- "$2" "$1"; else rm -f -- "$2"; exit 1; fi\n'
                f"find \"$1\" -maxdepth 0 -printf '{_ENTRY_FORMAT}'",
                path,
                tmp,
            ),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
        try:
            async for chunk in request.stream():
                proc.stdin.write(chunk)
                await proc.stdin.drain()
            proc.stdin.close()
            out, err = await asyncio.wait_for(
                asyncio.gather(proc.stdout.read(), proc.stderr.read()), timeout=120.0
            )
            await proc.wait()
        except BaseException:
            # Client went away mid-upload: kill ssh; the remote `cat` sees EOF
            # and the script's else-branch never runs, so clean the .part up.
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            with contextlib.suppress(Exception):
                await run(target, 'rm -f -- "$1"', tmp, timeout=15.0)
            raise
        raise_for_exit(target, proc.returncode or 0, err.decode(errors="replace"), "Upload failed")
        entries = parse_entries(out)
        return entries[0] if entries else FsEntry(name=posixpath.basename(path), path=path, type="file")

    return router
