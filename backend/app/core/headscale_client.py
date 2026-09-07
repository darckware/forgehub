"""Headscale policy integration through ForgeHub's host bridge.

This module is the only Headscale boundary. Policy-affecting operations
always derive a complete policy from database state and replace the live
file; no route performs incremental ACL edits.
"""

import json
import re
import shlex
from dataclasses import dataclass

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.client import Client, Workstation, WorkstationPeerGrant


@dataclass(frozen=True)
class PeerPairIPs:
    alias_a: str
    ip_a: str
    alias_b: str
    ip_b: str


def slugify_client_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "cliente"


async def _bridge(
    method: str,
    path: str,
    *,
    timeout_seconds: float = 30.0,
    **kwargs,
) -> dict:
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.request(
                method,
                f"{settings.CHAT_BRIDGE_URL.rstrip('/')}{path}",
                headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
                **kwargs,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Host-bridge unavailable: {exc}",
        ) from exc
    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Host-bridge error: {response.text[:500]}",
        )
    return response.json()


async def _headscale_exec(*args: str) -> str:
    command = "headscale " + " ".join(shlex.quote(argument) for argument in args)
    data = await _bridge("POST", "/v1/exec", json={"command": command})
    if data.get("exit_code") != 0:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(data.get("stderr") or "").strip() or "headscale command failed",
        )
    return (data.get("stdout") or "").strip()


async def list_node_ips() -> dict[str, str]:
    """Return Headscale node name to first advertised IPv4 address."""

    output = await _headscale_exec("nodes", "list", "-o", "json")
    try:
        nodes = json.loads(output) if output else []
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Headscale returned invalid node JSON",
        ) from exc
    result: dict[str, str] = {}
    for node in nodes:
        name = node.get("given_name") or node.get("name")
        ipv4 = next((ip for ip in node.get("ip_addresses") or [] if "." in ip), None)
        if name and ipv4:
            result[name] = ipv4
    return result


def render_policy(client_tags: list[str], peer_pairs: list[PeerPairIPs]) -> str:
    tags = sorted(set(client_tags))
    pairs = sorted(peer_pairs, key=lambda pair: (pair.alias_a, pair.alias_b))
    tag_owners = {tag: [settings.HEADSCALE_ADMIN_PRINCIPAL] for tag in tags}
    grants = [
        {"src": ["group:admins"], "dst": [tag], "ip": ["*"]}
        for tag in tags
    ]
    hosts: dict[str, str] = {}
    for pair in pairs:
        hosts[pair.alias_a] = pair.ip_a
        hosts[pair.alias_b] = pair.ip_b
        grants.append({"src": [pair.alias_a], "dst": [pair.alias_b], "ip": ["*"]})
    return json.dumps(
        {
            "groups": {"group:admins": [settings.HEADSCALE_ADMIN_PRINCIPAL]},
            "tagOwners": tag_owners,
            "hosts": hosts,
            "grants": grants,
        },
        indent=2,
    )


async def push_policy(hujson: str) -> None:
    await _bridge(
        "PUT",
        "/v1/fs/write",
        json={"path": settings.HEADSCALE_ACL_POLICY_PATH, "content": hujson},
    )
    await _headscale_exec("policy", "set", "--file", settings.HEADSCALE_ACL_POLICY_PATH)


async def rebuild_and_push_policy(db: AsyncSession) -> None:
    """Resolve active grants, render all DB-backed ACLs, and push once."""

    client_tags = list(
        (await db.execute(select(Client.headscale_tag).where(Client.headscale_tag.is_not(None))))
        .scalars()
        .all()
    )
    active_grants = list(
        (
            await db.execute(
                select(WorkstationPeerGrant).where(WorkstationPeerGrant.revoked_at.is_(None))
            )
        )
        .scalars()
        .all()
    )

    peer_pairs: list[PeerPairIPs] = []
    unresolved: list[str] = []
    if active_grants:
        node_ips = await list_node_ips()
        workstation_ids = {
            workstation_id
            for grant in active_grants
            for workstation_id in (grant.workstation_a_id, grant.workstation_b_id)
        }
        workstations = list(
            (
                await db.execute(select(Workstation).where(Workstation.id.in_(workstation_ids)))
            )
            .scalars()
            .all()
        )
        workstation_by_id = {workstation.id: workstation for workstation in workstations}
        for grant in active_grants:
            workstation_a = workstation_by_id.get(grant.workstation_a_id)
            workstation_b = workstation_by_id.get(grant.workstation_b_id)
            hostname_a = workstation_a.hostname if workstation_a else None
            hostname_b = workstation_b.hostname if workstation_b else None
            ip_a = node_ips.get(hostname_a) if hostname_a else None
            ip_b = node_ips.get(hostname_b) if hostname_b else None
            if not ip_a or not ip_b:
                unresolved.append(str(grant.id))
                continue
            peer_pairs.append(
                PeerPairIPs(
                    alias_a=f"ws-{workstation_a.id}",
                    ip_a=ip_a,
                    alias_b=f"ws-{workstation_b.id}",
                    ip_b=ip_b,
                )
            )

    if unresolved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Cannot publish Headscale policy because active peer grants "
                f"have unresolved nodes: {', '.join(unresolved)}"
            ),
        )
    await push_policy(render_policy(client_tags, peer_pairs))
