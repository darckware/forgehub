"""System control routes for Git status and Hermes backup management."""
from __future__ import annotations

import shlex
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.deps import get_current_admin
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/system-control", tags=["system-control"])


class CommitRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    # Same KNOWN_REPOS key as GET /status's `repo` query param -- omitted/
    # unknown falls back to DEFAULT_REPO, same as status.
    repo: str | None = None

# The container's own copy of the source (under /app) is not a git checkout
# at all -- git status/log must run against the real repo on the HOST, via
# the host-bridge's /v1/exec (same bridge already used below for fs/backup
# ops; the container image doesn't even have a `git` binary installed).
#
# Known checkouts under /root/project that Git Control can switch between --
# hardcoded rather than auto-discovered (same host-bridge round-trip either
# way; this only changes when a new project actually gets checked out on
# the host). Add an entry here when a new repo shows up.
KNOWN_REPOS: dict[str, str] = {
    "forgehub": "/root/project/forgehub",
    "forgerouter": "/root/project/forgerouter",
}
DEFAULT_REPO = "forgehub"
BACKUP_DIR = "/root/backup"


async def _bridge(method: str, path: str, **kwargs) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.request(
            method,
            f"{settings.CHAT_BRIDGE_URL}{path}",
            headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
            **kwargs,
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Host-bridge error: {resp.text[:500]}")
    return resp.json()


async def _run_git(repo_root: str, *args: str) -> str:
    command = "git -C " + shlex.quote(repo_root) + " " + " ".join(shlex.quote(a) for a in args)
    data = await _bridge("POST", "/v1/exec", json={"command": command})
    if data["exit_code"] != 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(data["stderr"] or "").strip() or "git failed",
        )
    return (data["stdout"] or "").strip()


@router.get("/status")
async def get_system_control_status(
    repo: str | None = None, _admin: User = Depends(get_current_admin)
) -> dict[str, Any]:
    # Unknown/omitted repo key falls back to the default instead of 400ing --
    # a stale key in a saved link/bookmark should still load something.
    repo_key = repo if repo in KNOWN_REPOS else DEFAULT_REPO
    repo_root = KNOWN_REPOS[repo_key]
    branch = await _run_git(repo_root, "branch", "--show-current")
    head = await _run_git(repo_root, "rev-parse", "HEAD")
    short_head = await _run_git(repo_root, "rev-parse", "--short", "HEAD")
    last_commit = await _run_git(repo_root, "log", "-1", "--pretty=format:%H%n%an%n%ad%n%s")
    status_short = await _run_git(repo_root, "status", "--short")
    status_lines = [line for line in status_short.splitlines() if line.strip()]
    try:
        await _bridge("POST", "/v1/fs/mkdir", json={"path": BACKUP_DIR})
    except HTTPException:
        pass
    backup_listing = await _bridge("GET", "/v1/fs/list", params={"path": BACKUP_DIR})
    backups = [
        {
            "name": entry.get("name"),
            "path": entry.get("path"),
            "size": entry.get("size"),
            "type": entry.get("type"),
        }
        for entry in backup_listing.get("entries", [])
        if entry.get("type") == "file"
    ]
    backups.sort(key=lambda item: item["name"] or "")
    commit_lines = last_commit.splitlines()
    return {
        "git": {
            "repo_key": repo_key,
            "repo_root": repo_root,
            "branch": branch or "detached",
            "head": head,
            "short_head": short_head,
            "dirty_count": len(status_lines),
            "status_lines": status_lines,
            "last_commit": {
                "hash": commit_lines[0] if len(commit_lines) > 0 else head,
                "author": commit_lines[1] if len(commit_lines) > 1 else None,
                "date": commit_lines[2] if len(commit_lines) > 2 else None,
                "subject": commit_lines[3] if len(commit_lines) > 3 else None,
            },
        },
        "available_repos": [{"key": key, "path": path} for key, path in KNOWN_REPOS.items()],
        "backups": {
            "path": BACKUP_DIR,
            "count": len(backups),
            "entries": backups,
        },
    }


@router.post("/commit")
async def commit_changes(payload: CommitRequest, _admin: User = Depends(get_current_admin)) -> dict[str, Any]:
    """Stages everything (`git add -A`) and commits with the given message --
    no partial/selective staging, since Git Control only ever shows the
    flat status_lines list, not a per-file selection UI. Never pushes:
    that's a separate, more consequential action this button deliberately
    doesn't take on."""
    repo_key = payload.repo if payload.repo in KNOWN_REPOS else DEFAULT_REPO
    repo_root = KNOWN_REPOS[repo_key]
    await _run_git(repo_root, "add", "-A")
    await _run_git(repo_root, "commit", "-m", payload.message)
    last_commit = await _run_git(repo_root, "log", "-1", "--pretty=format:%H%n%an%n%ad%n%s")
    commit_lines = last_commit.splitlines()
    return {
        "repo_key": repo_key,
        "hash": commit_lines[0] if len(commit_lines) > 0 else None,
        "author": commit_lines[1] if len(commit_lines) > 1 else None,
        "date": commit_lines[2] if len(commit_lines) > 2 else None,
        "subject": commit_lines[3] if len(commit_lines) > 3 else None,
    }


@router.post("/backup-hermes")
async def backup_hermes(_admin: User = Depends(get_current_admin)) -> dict[str, Any]:
    return await _bridge(
        "POST",
        "/v1/system/hermes-backup",
        json={"source_path": "/root/.hermes", "backup_dir": BACKUP_DIR},
    )


@router.delete("/backup/{filename}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_backup(filename: str, _admin: User = Depends(get_current_admin)) -> None:
    # Backup entries are flat files directly inside BACKUP_DIR (see
    # get_system_control_status) -- a bare filename only, reject anything
    # that could climb out of that directory.
    if "/" in filename or "\\" in filename or filename in (".", ".."):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
    await _bridge("DELETE", "/v1/fs/delete", params={"path": f"{BACKUP_DIR}/{filename}", "recursive": False})
