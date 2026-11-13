"""The mission's study material: <working_directory_path>/docs/ (2026-11-12).

Marcelo writes the mission's context and leaves in the project's docs/
folder everything the agents must study before registering the product and
planning (Marcelo: "deixo na pasta docs do projeto todas as documentações
para os agentes estudarem"). The folder lives on the host, so it is read
through the host-bridge's /v1/fs/list, like the Workspace Explorer.

A folder that could not be read is ``unverified`` -- never "present": the
draft -> planning gate refuses it, it never passes.
"""
from __future__ import annotations

import posixpath
from dataclasses import dataclass, field

import httpx

from app.core.config import settings

TIMEOUT_SECONDS = 15
MAX_LISTED = 200


@dataclass
class MissionDocs:
    path: str | None
    status: str  # ok | empty | missing | no_working_directory | unverified
    files: list[str] = field(default_factory=list)
    detail: str | None = None


def docs_path(working_directory_path: str | None) -> str | None:
    if not working_directory_path or not working_directory_path.strip():
        return None
    return posixpath.join(posixpath.normpath(working_directory_path.strip()), "docs")


async def read_mission_docs(working_directory_path: str | None) -> MissionDocs:
    path = docs_path(working_directory_path)
    if path is None:
        return MissionDocs(path=None, status="no_working_directory")
    base = (settings.CHAT_BRIDGE_URL or "").rstrip("/")
    if not base:
        return MissionDocs(path=path, status="unverified", detail="host-bridge is not configured")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.get(f"{base}/v1/fs/list", params={"path": path},
                                    headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN})
    except httpx.HTTPError as exc:
        return MissionDocs(path=path, status="unverified", detail=f"host-bridge unreachable: {type(exc).__name__}")
    if resp.status_code == 404:
        return MissionDocs(path=path, status="missing")
    if resp.status_code != 200:
        return MissionDocs(path=path, status="unverified", detail=f"host-bridge answered {resp.status_code}")
    entries = [e for e in resp.json().get("entries", []) if not str(e.get("name", "")).startswith(".")]
    names = [f"{e['name']}/" if e.get("type") == "dir" else e["name"] for e in entries][:MAX_LISTED]
    return MissionDocs(path=path, status="ok" if names else "empty", files=names)
