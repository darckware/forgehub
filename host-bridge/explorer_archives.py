"""Portable archive operations for the Workspace Explorer, local or SSH.

Never merges into existing destinations, restores permissions, or follows links.
Only standard-library imports: the same source is sent to a remote Python 3.
"""
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tarfile
import time
import zipfile

MAX_FILES = 10000
MAX_BYTES = 2 * 1024**3


class ArchiveError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def archive_operation(mode, paths, destination):
    dest = Path(destination)
    if not dest.is_absolute() or not dest.parent.is_dir():
        raise ArchiveError('Destination must have an existing parent directory')
    if os.path.lexists(dest):
        raise ArchiveError('Destination already exists; choose another name', 409)
    sources = [Path(p) for p in paths]
    if not sources or any(not p.is_absolute() for p in sources):
        raise ArchiveError('Absolute source paths are required')
    count, total = 0, 0
    started = time.monotonic()

    def budget(size):
        nonlocal count, total
        count += 1
        total += size
        if count > MAX_FILES or total > MAX_BYTES or time.monotonic() - started > 120:
            raise ArchiveError('Archive limit exceeded (10000 entries, 2 GiB, 120 seconds)', 413)

    owned = False
    try:
        if mode == 'compress':
            if dest.suffix.lower() != '.zip':
                raise ArchiveError('The archive name must end in .zip')
            if len({p.name for p in sources}) != len(sources):
                raise ArchiveError('Selected items must have distinct names')
            for p in sources:
                if not p.exists():
                    raise ArchiveError('Source not found', 404)
                if p.resolve() == dest.resolve() or p.is_dir() and p.resolve() in dest.resolve().parents:
                    raise ArchiveError('Cannot create an archive inside a selected folder')
            with dest.open('xb') as output:
                owned = True
                with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
                    def add(path, name):
                        info = path.lstat()
                        if stat.S_ISLNK(info.st_mode) or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                            raise ArchiveError('Links and special files cannot be archived')
                        budget(info.st_size if path.is_file() else 0)
                        archive.write(path, name)
                        if path.is_dir():
                            for child in path.iterdir():
                                add(child, name + '/' + child.name)
                    for p in sources:
                        add(p, p.name)
        elif mode == 'extract':
            if len(sources) != 1 or not sources[0].is_file():
                raise ArchiveError('Select one archive file')
            source = sources[0]
            if source.stat().st_size > MAX_BYTES:
                raise ArchiveError('Archive input exceeds 2 GiB', 413)
            if not zipfile.is_zipfile(source) and not tarfile.is_tarfile(source):
                raise ArchiveError('Unsupported or invalid archive; use ZIP or TAR', 415)
            dest.mkdir(mode=0o700)
            owned = True
            seen = set()

            def target(name, size):
                # Reject Windows separators too; do not reinterpret an unsafe
                # member as a different safe filename.
                p = PurePosixPath(name)
                if not name or '\\' in name or p.is_absolute() or '..' in p.parts or ':' in name or not p.parts:
                    raise ArchiveError('Archive contains an unsafe path')
                budget(size)
                if str(p) in seen:
                    raise ArchiveError('Archive contains duplicate paths')
                seen.add(str(p))
                return dest.joinpath(*p.parts)

            def write_file(path, stream, expected):
                path.parent.mkdir(parents=True, exist_ok=True)
                copied = 0
                with path.open('xb') as out:
                    while True:
                        chunk = stream.read(1024 * 1024)
                        if not chunk:
                            break
                        copied += len(chunk)
                        if copied > expected or time.monotonic() - started > 120:
                            raise ArchiveError('Archive exceeds its declared size or time limit', 413)
                        out.write(chunk)

            if zipfile.is_zipfile(source):
                with zipfile.ZipFile(source) as archive:
                    for member in archive.infolist():
                        mode_bits = member.external_attr >> 16
                        if stat.S_ISLNK(mode_bits) or stat.S_IFMT(mode_bits) not in (0, stat.S_IFREG, stat.S_IFDIR):
                            raise ArchiveError('Archive links and special files are not supported')
                        path = target(member.filename, member.file_size)
                        if member.is_dir():
                            path.mkdir(parents=True, exist_ok=True)
                        else:
                            with archive.open(member) as stream:
                                write_file(path, stream, member.file_size)
            else:
                with tarfile.open(source, 'r:*') as archive:
                    for member in archive:
                        if member.isdir() and member.name in ('.', './'):
                            budget(0)
                            continue
                        if not (member.isfile() or member.isdir()):
                            raise ArchiveError('Archive links and special files are not supported')
                        path = target(member.name, member.size)
                        if member.isdir():
                            path.mkdir(parents=True, exist_ok=True)
                        else:
                            with archive.extractfile(member) as stream:
                                write_file(path, stream, member.size)
        else:
            raise ArchiveError('Unknown archive operation')
    except Exception as exc:
        if owned:
            if mode == 'extract':
                shutil.rmtree(dest)
            else:
                dest.unlink()
        if isinstance(exc, ArchiveError):
            raise
        if isinstance(exc, FileExistsError):
            raise ArchiveError('Destination already exists; choose another name', 409) from exc
        if isinstance(exc, PermissionError):
            raise ArchiveError('Permission denied', 403) from exc
        raise ArchiveError('Cannot process this archive or source file') from exc
    info = dest.stat()
    return dict(name=dest.name, path=str(dest), type='dir' if dest.is_dir() else 'file',
                size=None if dest.is_dir() else info.st_size, modified=info.st_mtime, is_symlink=False)
