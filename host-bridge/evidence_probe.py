"""Read-only evidence probes for the task completion guard (Plano Integrado M0.6a).

The ForgeHub backend container has neither `git` nor the project folders, so
`core/task_evidence.py`'s `file:`/`git:` checks always failed there. The
backend asks the host instead, through two narrow endpoints:

- ``POST /v1/evidence/verify`` ``{kind: git|file, root, ref, since?}`` -- does
  the file exist under ``root`` (and was it modified after ``since``), or does
  the commit exist in the repository at ``root`` (and was it committed after
  ``since``)?
- ``POST /v1/git/is-ancestor`` ``{repo, commit, ref}`` -- is ``commit``
  integrated into ``ref`` (``git merge-base --is-ancestor``)?

Both are read-only and answer only metadata (existence, timestamps, a reason),
never the content of a file. ``root``/``repo`` arrive in a request body, so
they are checked against EVIDENCE_ROOTS *after* ``realpath`` (a symlink or
``..`` pointing outside can't pass a prefix check on the raw string), and a
``file:`` ref is resolved the same way and must stay inside ``root``.
"""
from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timezone
from typing import Callable, Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

# Where project working directories live on this host. Overridable for tests
# and for a host with projects elsewhere (comma-separated absolute paths).
DEFAULT_EVIDENCE_ROOTS = ("/root/project",)

SHA_RE = re.compile(r"^[0-9a-f]{7,64}$")
# A branch/ref name: no option injection (leading "-"), no "..", no revision
# syntax beyond plain names (`^`, `~`, `:`, `@{` are all refused).
REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
GIT_TIMEOUT_SECONDS = 15


def evidence_roots_from_env() -> tuple[str, ...]:
    raw = os.environ.get("FORGEHUB_EVIDENCE_ROOTS", "")
    roots = tuple(p.strip() for p in raw.split(",") if p.strip())
    return roots or DEFAULT_EVIDENCE_ROOTS


class VerifyEvidenceRequest(BaseModel):
    kind: Literal["git", "file"]
    root: str = Field(min_length=1, max_length=1000)
    ref: str = Field(min_length=1, max_length=500)
    since: datetime | None = None


class IsAncestorRequest(BaseModel):
    repo: str = Field(min_length=1, max_length=1000)
    commit: str = Field(min_length=7, max_length=64)
    ref: str = Field(min_length=1, max_length=200)


def _inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def resolve_root(raw: str, allowed_roots: tuple[str, ...]) -> str:
    """Realpath of `raw`, refused unless it is an existing directory inside
    one of `allowed_roots` (also realpath'd)."""
    if not os.path.isabs(raw):
        raise HTTPException(status_code=400, detail="root must be an absolute path")
    resolved = os.path.realpath(raw)
    roots = [os.path.realpath(r) for r in allowed_roots]
    if not any(_inside(resolved, r) for r in roots):
        raise HTTPException(status_code=403, detail="root is outside the allowed evidence roots")
    if not os.path.isdir(resolved):
        raise HTTPException(status_code=404, detail="root does not exist")
    return resolved


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


async def _git(repo: str, *args: str) -> tuple[int, str]:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", repo, *args,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, env=env,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=GIT_TIMEOUT_SECONDS)
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise HTTPException(status_code=504, detail="git did not answer in time") from exc
    return proc.returncode, stdout.decode(errors="replace").strip()


def verify_file(root: str, ref: str, since: datetime | None) -> dict:
    if os.path.isabs(ref) or ".." in ref.split("/"):
        raise HTTPException(status_code=400, detail="file evidence must be a relative path inside the root")
    resolved = os.path.realpath(os.path.join(root, ref))
    if not _inside(resolved, root):
        raise HTTPException(status_code=403, detail="file evidence resolves outside the root")
    if not os.path.isfile(resolved):
        return {"kind": "file", "ok": False, "exists": False, "reason": "file does not exist"}
    mtime = datetime.fromtimestamp(os.path.getmtime(resolved), tz=timezone.utc)
    since = _as_utc(since)
    if since is not None and mtime < since:
        return {
            "kind": "file", "ok": False, "exists": True, "modified_at": mtime.isoformat(),
            "reason": "file was last modified before the execution started",
        }
    return {"kind": "file", "ok": True, "exists": True, "modified_at": mtime.isoformat(),
            "reason": "file exists and was modified after the execution started"}


async def verify_git(root: str, ref: str, since: datetime | None) -> dict:
    sha = ref.strip().lower()
    if not SHA_RE.match(sha):
        raise HTTPException(status_code=400, detail="git evidence must be a commit sha")
    code, _ = await _git(root, "rev-parse", "--is-inside-work-tree")
    if code != 0:
        return {"kind": "git", "ok": False, "exists": False, "reason": "root is not a git repository"}
    code, full_sha = await _git(root, "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}")
    if code != 0 or not full_sha:
        return {"kind": "git", "ok": False, "exists": False, "reason": "commit not found in the repository"}
    code, committed = await _git(root, "log", "-1", "--format=%cI", full_sha)
    try:
        committed_at = datetime.fromisoformat(committed)
    except ValueError:
        return {"kind": "git", "ok": False, "exists": True, "commit": full_sha,
                "reason": "commit date could not be read"}
    since = _as_utc(since)
    if since is not None and committed_at < since:
        return {"kind": "git", "ok": False, "exists": True, "commit": full_sha,
                "committed_at": committed_at.isoformat(),
                "reason": "commit predates the execution start"}
    return {"kind": "git", "ok": True, "exists": True, "commit": full_sha,
            "committed_at": committed_at.isoformat(), "reason": "commit exists"}


async def is_ancestor(repo: str, commit: str, ref: str) -> dict:
    sha = commit.strip().lower()
    if not SHA_RE.match(sha):
        raise HTTPException(status_code=400, detail="commit must be a sha")
    if not REF_RE.match(ref) or ".." in ref or ref.endswith((".lock", "/", ".")):
        raise HTTPException(status_code=400, detail="ref must be a plain branch name")
    code, full_sha = await _git(repo, "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}")
    if code != 0 or not full_sha:
        return {"is_ancestor": False, "commit_found": False, "ref_found": None,
                "reason": "commit not found in the repository"}
    code, ref_sha = await _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{ref}^{{commit}}")
    if code != 0 or not ref_sha:
        return {"is_ancestor": False, "commit_found": True, "ref_found": False,
                "reason": f"branch {ref} not found in the repository"}
    code, _ = await _git(repo, "merge-base", "--is-ancestor", full_sha, ref_sha)
    if code not in (0, 1):
        raise HTTPException(status_code=502, detail="git merge-base failed")
    integrated = code == 0
    return {"is_ancestor": integrated, "commit_found": True, "ref_found": True,
            "commit": full_sha, "ref": ref,
            "reason": f"commit is in {ref}" if integrated else f"commit is not in {ref}"}


def make_evidence_router(
    check_token: Callable[[str | None], None],
    roots: tuple[str, ...] | None = None,
) -> APIRouter:
    allowed = roots or evidence_roots_from_env()
    router = APIRouter()

    @router.post("/v1/evidence/verify")
    async def verify_evidence(req: VerifyEvidenceRequest, x_bridge_token: str | None = Header(default=None)) -> dict:
        check_token(x_bridge_token)
        root = resolve_root(req.root, allowed)
        if req.kind == "file":
            return verify_file(root, req.ref, req.since)
        return await verify_git(root, req.ref, req.since)

    @router.post("/v1/git/is-ancestor")
    async def git_is_ancestor(req: IsAncestorRequest, x_bridge_token: str | None = Header(default=None)) -> dict:
        check_token(x_bridge_token)
        repo = resolve_root(req.repo, allowed)
        return await is_ancestor(repo, req.commit, req.ref)

    return router
