"""Host-bridge client for file/git evidence (Plano Integrado M0.6a).

The backend container has no `git` and no project folders, so `file:` and
`git:` evidence is checked on the host by host-bridge/evidence_probe.py
(`POST /v1/evidence/verify`, `POST /v1/git/is-ancestor`), reached through
`settings.CHAT_BRIDGE_URL` like every other bridge call.

An answer the bridge could not give -- unreachable, timeout, 5xx, refused
root -- is `EvidenceUnverifiable`: the caller treats it as "not verified",
never as verified and never as proven false.
"""
from __future__ import annotations

from datetime import datetime

import httpx

from app.core.config import settings

TIMEOUT_SECONDS = 20


class EvidenceUnverifiable(Exception):
    """The bridge couldn't answer; the evidence stays unverified."""


def _client() -> httpx.AsyncClient:
    """Swapped by tests for a client bound to the real evidence router."""
    return httpx.AsyncClient(timeout=TIMEOUT_SECONDS)


async def _post(path: str, body: dict) -> dict:
    base = (settings.CHAT_BRIDGE_URL or "").rstrip("/")
    if not base:
        raise EvidenceUnverifiable("host-bridge is not configured (CHAT_BRIDGE_URL is empty)")
    try:
        async with _client() as client:
            response = await client.post(
                f"{base}{path}", json=body, headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN}
            )
    except httpx.HTTPError as exc:
        raise EvidenceUnverifiable(f"host-bridge unreachable: {type(exc).__name__}") from exc
    if response.status_code != 200:
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = None
        raise EvidenceUnverifiable(
            f"host-bridge refused the evidence check ({response.status_code}): {detail or 'no detail'}"
        )
    return response.json()


async def verify_on_host(kind: str, root: str, ref: str, since: datetime | None) -> tuple[bool, str]:
    """(ok, reason) for a `file:`/`git:` ref under `root`; raises
    EvidenceUnverifiable when the bridge can't say."""
    body: dict = {"kind": kind, "root": root, "ref": ref}
    if since is not None:
        body["since"] = since.isoformat()
    result = await _post("/v1/evidence/verify", body)
    return bool(result.get("ok")), str(result.get("reason") or "")


async def commit_is_integrated(repo: str, commit: str, ref: str) -> tuple[bool, str]:
    """(is_ancestor, reason) of `commit` in branch `ref`; raises
    EvidenceUnverifiable when the bridge can't say."""
    result = await _post("/v1/git/is-ancestor", {"repo": repo, "commit": commit, "ref": ref})
    return bool(result.get("is_ancestor")), str(result.get("reason") or "")
