"""Agent artifact transfers. Only the bridge opens local files and SSH keys.

The backend supplies trusted task/run roots, never the requesting agent. File
bytes flow in bounded chunks between local descriptors and SSH, never JSON.
"""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
import re
import stat
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

import remote_fs

MAX_BYTES = 200 * 1024 * 1024
CHUNK = 1024 * 1024
FORBIDDEN = {'.ssh', '.config', '.hermes', '.codex', '.aws', '.gnupg', '.agents', '.git', 'credentials', 'credentials.json', 'config.json', 'config.yaml', 'config.yml', 'agent.yaml', 'agent.yml', 'AGENTS.md', 'settings.json', 'settings.local.json', 'secrets.json', 'secrets.yaml', 'token', 'token.json', 'private_key', 'ssh_key'}
BROAD_ROOTS = {'/', '/root', '/home', '/tmp', '/var', '/var/lib', '/etc', '/usr', '/opt'}


def validate_path(raw: str) -> None:
    parts = Path(raw).parts
    if not raw.startswith('/') or '\x00' in raw or '..' in parts:
        raise HTTPException(403, 'Absolute path without traversal required')
    for part in parts:
        lower = part.lower()
        if part in FORBIDDEN or lower.startswith('.env') or lower.startswith('id_') or lower.endswith(('.key', '.pem', '.p12', '.pfx', '.kdbx')):
            raise HTTPException(403, 'Sensitive/configuration path is forbidden')


def safe_local_path(raw: str, roots: list[str]) -> Path:
    validate_path(raw)
    path = Path(raw).resolve()
    validate_path(str(path))
    allowed = []
    for root in roots:
        canonical = Path(root).resolve()
        validate_path(str(canonical))
        if str(canonical) in BROAD_ROOTS:
            raise HTTPException(403, 'Task working directory is too broad for file transfers')
        allowed.append(canonical)
    if not any(path.is_relative_to(root) and path != root for root in allowed):
        raise HTTPException(403, 'Local path is outside task/run directories')
    return path


def ensure_private_directory(path: Path) -> None:
    """Create the trusted run directory with fd traversal, never symlink parents."""
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            try:
                os.mkdir(part, mode=0o700, dir_fd=fd)
            except FileExistsError:
                pass
            following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = following
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise HTTPException(403, 'Run directory must be owned by the bridge and private (0700)')
    finally:
        os.close(fd)


def _parent_fd(path: Path) -> int:
    """Walk without following links; parent renames cannot redirect the open fd."""
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parent.parts[1:]:
            following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = following
        return fd
    except BaseException:
        os.close(fd)
        raise


_REMOTE_CHECK = '''
p=$(realpath -m -- "$1") || exit 43
case "$p" in
 */.ssh/*|*/.config/*|*/.hermes/*|*/.codex/*|*/.aws/*|*/.gnupg/*|*/.agents/*|*/.git/*|*/.env*|*/id_*|*.pem|*.key|*.p12|*.pfx) exit 43;;
esac
'''
_UPLOAD = _REMOTE_CHECK + '''
part="$p.$4.part"
trap 'rm -f -- "$part"' EXIT HUP INT TERM
[ "$3" = 1 ] || { [ ! -e "$p" ] && [ ! -L "$p" ]; } || exit 46
(umask 077; set -C; cat > "$part") || exit 48
size=$(stat -c %s -- "$part") || exit 48
[ "$size" -le "$5" ] || exit 45
[ "$size" = "$6" ] || exit 48
hash=$(sha256sum -- "$part") || exit 48
hash=${hash%% *}
[ "$hash" = "$2" ] || exit 48
if [ "$3" = 1 ]; then mv -fT -- "$part" "$p" || exit 48
else ln -- "$part" "$p" || exit 46; rm -f -- "$part"; fi
printf '%s %s' "$size" "$hash"
'''
_METADATA = _REMOTE_CHECK + '''
[ -f "$p" ] || exit 44
size=$(stat -c %s -- "$p") || exit 44
[ "$size" -le "$2" ] || exit 45
grep -aEq -- '-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----|"private_key"[[:space:]]*:' "$p" && exit 43
hash=$(sha256sum -- "$p") || exit 44
printf '%s %s' "$size" "${hash%% *}"
'''
_DOWNLOAD = _REMOTE_CHECK + '\ncat -- "$p"'


async def transfer_file(target, direction: str, local: Path, remote: str, overwrite: bool) -> dict:
    validate_path(remote)
    parent = _parent_fd(local)
    proc = None
    part = f'.{local.name}.{uuid.uuid4().hex}.part'
    try:
        if direction == 'upload':
            fd = os.open(local.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            with os.fdopen(fd, 'rb') as source:
                st = os.fstat(source.fileno())
                if not stat.S_ISREG(st.st_mode):
                    raise HTTPException(403, 'Only regular files can be transferred')
                if st.st_size > MAX_BYTES:
                    raise HTTPException(413, 'File exceeds 200 MiB transfer limit')
                digest = hashlib.sha256()
                hashed = 0
                tail = b''
                while chunk := source.read(CHUNK):
                    hashed += len(chunk)
                    if hashed > MAX_BYTES:
                        raise HTTPException(413, 'File exceeds transfer limit')
                    scan = tail + chunk
                    if re.search(rb'-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----|"private_key"\s*:', scan):
                        raise HTTPException(403, 'Private key material cannot be transferred')
                    tail = scan[-128:]
                    digest.update(chunk)
                expected = digest.hexdigest()
                source.seek(0)
                os.makedirs(remote_fs._CONTROL_DIR, mode=0o700, exist_ok=True)
                proc = await asyncio.create_subprocess_exec(*remote_fs.ssh_args(target), remote_fs.remote_command(
                    _UPLOAD, remote, expected, str(int(overwrite)), uuid.uuid4().hex, str(MAX_BYTES), str(st.st_size)),
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
                sent = 0
                while chunk := source.read(CHUNK):
                    sent += len(chunk)
                    if sent > MAX_BYTES:
                        raise HTTPException(413, 'File exceeds transfer limit')
                    proc.stdin.write(chunk)
                    await proc.stdin.drain()
                proc.stdin.close()
                result = await proc.stdout.read(256)
                code = await proc.wait()
                _check_exit(code)
                size, sha = result.decode().split()
                if int(size) != st.st_size or sha != expected:
                    raise HTTPException(409, 'Transfer hash verification failed')
                return {'size': int(size), 'sha256': sha}
        if not overwrite and os.path.lexists(local):
            raise HTTPException(409, 'Destination already exists; pass overwrite=true')
        code, metadata, _ = await remote_fs.run(target, _METADATA, remote, str(MAX_BYTES))
        _check_exit(code)
        size, expected = metadata.decode().split()
        size = int(size)
        if size > MAX_BYTES:
            raise HTTPException(413, 'File exceeds transfer limit')
        fd = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(fd, 'wb') as destination:
            proc = await asyncio.create_subprocess_exec(*remote_fs.ssh_args(target), remote_fs.remote_command(_DOWNLOAD, remote),
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            received = 0
            digest = hashlib.sha256()
            while chunk := await proc.stdout.read(CHUNK):
                received += len(chunk)
                if received > MAX_BYTES or received > size:
                    raise HTTPException(413, 'Remote file grew beyond declared size')
                digest.update(chunk)
                destination.write(chunk)
            _check_exit(await proc.wait())
            if received != size or digest.hexdigest() != expected:
                raise HTTPException(409, 'Transfer hash verification failed')
            destination.flush()
            os.fsync(destination.fileno())
        if overwrite:
            os.replace(part, local.name, src_dir_fd=parent, dst_dir_fd=parent)
        else:
            try:
                os.link(part, local.name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
            except FileExistsError:
                raise HTTPException(409, 'Destination already exists; pass overwrite=true') from None
        return {'size': size, 'sha256': expected}
    except (BrokenPipeError, ConnectionResetError):
        if proc:
            _check_exit(await proc.wait())
        raise HTTPException(502, 'Transfer interrupted') from None
    finally:
        if proc and proc.stdin:
            proc.stdin.close()
        if proc and proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            await proc.wait()
        with contextlib.suppress(FileNotFoundError):
            os.unlink(part, dir_fd=parent)
        os.close(parent)


def _check_exit(code: int) -> None:
    if code:
        raise HTTPException({43: 403, 44: 404, 45: 413, 46: 409}.get(code, 502),
                            {43: 'Sensitive remote path forbidden', 44: 'Remote file unavailable', 45: 'File exceeds transfer limit',
                             46: 'Destination exists; pass overwrite=true'}.get(code, 'Transfer interrupted or verification failed'))


class TransferRequest(BaseModel):
    direction: Literal['upload', 'download']
    local_path: str = Field(min_length=1, max_length=4096)
    remote_path: str = Field(min_length=1, max_length=4096)
    roots: list[str] = Field(min_length=1, max_length=2)
    host: str
    user: str
    port: int = Field(default=22, ge=1, le=65535)
    key_ref: str | None = None
    key_path: str | None = None
    overwrite: bool = False


def make_transfer_router(check_token, resolve_key_path, agent_socket_for):
    router = APIRouter()

    @router.post('/v1/remote-files/transfer')
    async def transfer(payload: TransferRequest, x_bridge_token: str | None = Header(default=None)):
        check_token(x_bridge_token)
        if not remote_fs._HOST_RE.fullmatch(payload.host) or not remote_fs._USER_RE.fullmatch(payload.user):
            raise HTTPException(400, 'Invalid SSH target')
        local = safe_local_path(payload.local_path, payload.roots)
        run_root = payload.roots[-1]
        if (re.fullmatch(r'/var/lib/forgehub/transfers/[0-9a-f-]{36}/[A-Za-z0-9_-]{1,64}', run_root)
                and local.is_relative_to(Path(run_root))):
            ensure_private_directory(Path(run_root))
        sock = None
        if payload.key_ref:
            if not re.fullmatch(r'[0-9a-f-]{36}', payload.key_ref):
                raise HTTPException(400, 'Invalid key reference')
            sock = await agent_socket_for(payload.key_ref)
        target = remote_fs.SshTarget(payload.host, payload.user, payload.port,
            resolve_key_path(payload.key_path) if payload.key_path and not sock else None, sock)
        try:
            return await asyncio.wait_for(transfer_file(target, payload.direction, local, payload.remote_path, payload.overwrite), 600)
        except asyncio.TimeoutError:
            raise HTTPException(504, 'File transfer timed out') from None
        except OSError:
            raise HTTPException(403, 'Local file unavailable or path is unsafe') from None

    return router
