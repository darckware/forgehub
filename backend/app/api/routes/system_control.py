"""System control routes for Git status and Hermes backup management."""
from __future__ import annotations

import shlex
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import settings
from app.core.deps import get_current_admin
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/system-control", tags=["system-control"])

# The container's own copy of the source (under /app) is not a git checkout
# at all -- git status/log must run against the real repo on the HOST, via
# the host-bridge's /v1/exec (same bridge already used below for fs/backup
# ops; the container image doesn't even have a `git` binary installed).
REPO_ROOT = "/root/project/forgehub"
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


async def _run_git(*args: str) -> str:
    command = "git -C " + shlex.quote(REPO_ROOT) + " " + " ".join(shlex.quote(a) for a in args)
    data = await _bridge("POST", "/v1/exec", json={"command": command})
    if data["exit_code"] != 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(data["stderr"] or "").strip() or "git failed",
        )
    return (data["stdout"] or "").strip()


@router.get("/status")
async def get_system_control_status(_admin: User = Depends(get_current_admin)) -> dict[str, Any]:
    branch = await _run_git("branch", "--show-current")
    head = await _run_git("rev-parse", "HEAD")
    short_head = await _run_git("rev-parse", "--short", "HEAD")
    last_commit = await _run_git("log", "-1", "--pretty=format:%H%n%an%n%ad%n%s")
    status_short = await _run_git("status", "--short")
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
            "repo_root": str(REPO_ROOT),
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
        "backups": {
            "path": BACKUP_DIR,
            "count": len(backups),
            "entries": backups,
        },
    }


@router.post("/backup-hermes")
async def backup_hermes(_admin: User = Depends(get_current_admin)) -> dict[str, Any]:
    return await _bridge(
        "POST",
        "/v1/system/hermes-backup",
        json={"source_path": "/root/.hermes", "backup_dir": BACKUP_DIR},
    )
