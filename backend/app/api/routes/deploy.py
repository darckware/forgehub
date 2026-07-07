"""Deploy domain – Docker installation registry + live container status.

Endpoints:
  GET  /api/v1/deploy/containers                      – live docker ps (host-bridge)
  POST /api/v1/deploy/containers/{name}/restart       – docker restart (host-bridge)
  GET  /api/v1/deploy/containers/{name}/logs          – docker logs --tail N (host-bridge)
  DELETE /api/v1/deploy/containers/{name}             – docker rm -f + drop registry rows
  GET  /api/v1/deploy/images                          – docker images -a (host-bridge)
  DELETE /api/v1/deploy/images?ref=<repo:tag|id>      – docker rmi (host-bridge)
  GET  /api/v1/deploy/installations                   – list registered installations
  POST /api/v1/deploy/installations                   – create
  GET  /api/v1/deploy/installations/{id}              – get one
  PUT  /api/v1/deploy/installations/{id}              – full update
  DELETE /api/v1/deploy/installations/{id}            – delete
  GET  /api/v1/deploy/groups                          – list groups
  POST /api/v1/deploy/groups                          – create group
  PUT  /api/v1/deploy/groups/{id}                     – rename (propagates to installations)
  DELETE /api/v1/deploy/groups/{id}                   – delete (installations become ungrouped)
"""
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.deploy import (
    DeployGroupCreate,
    DeployGroupOut,
    DeployGroupUpdate,
    DeployInstallationCreate,
    DeployInstallationOut,
    DeployInstallationOutEnriched,
    DeployInstallationUpdate,
    DockerContainerOut,
    DockerImageOut,
    DockerVolumeOut,
    DockerNetworkOut,
)
from app.core.config import settings
from app.db.base import get_db
from app.db.models.deploy import DeployGroup, DeployInstallation, DeploySyncIgnore
from app.db.models.product import Product

router = APIRouter(prefix="/api/v1/deploy", tags=["deploy"])

BRIDGE_HEADERS = {"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN}


async def _bridge(method: str, path: str, **kwargs) -> Any:
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            resp = await c.request(
                method,
                f"{settings.CHAT_BRIDGE_URL}{path}",
                headers=BRIDGE_HEADERS,
                **kwargs,
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Host-bridge error: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# Live Docker container endpoints (via host-bridge)
# ---------------------------------------------------------------------------

@router.get("/containers", response_model=list[DockerContainerOut])
async def list_containers():
    """Return all Docker containers (running and stopped) from the host."""
    data = await _bridge("POST", "/v1/docker/ps")
    containers = []
    for c in data.get("containers", []):
        raw_status = c.get("Status", "")
        health = None
        if "(healthy)" in raw_status:
            health = "healthy"
        elif "(unhealthy)" in raw_status:
            health = "unhealthy"
        elif "starting" in raw_status.lower():
            health = "starting"
        state = "running" if raw_status.startswith("Up") else "stopped"
        containers.append(DockerContainerOut(
            id=c.get("ID", ""),
            name=c.get("Names", ""),
            image=c.get("Image", ""),
            status=raw_status,
            ports=c.get("Ports", ""),
            state=state,
            health=health,
        ))
    return containers


@router.post("/containers/{container_name}/restart")
async def restart_container(container_name: str):
    """Restart a Docker container via the host-bridge."""
    result = await _bridge("POST", "/v1/docker/restart", json={"container_name": container_name})
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.get("stderr", "Restart failed"),
        )
    return {"ok": True, "container": container_name}


@router.delete("/containers/{container_name}")
async def remove_container(container_name: str, db: AsyncSession = Depends(get_db)):
    """Remove a container from Docker (forced) and drop its registry rows.

    Deletes the DeployInstallation(s) registered for this container_name and
    any sync-ignore entry (the container no longer exists, so /sync cannot
    resurrect it). The Docker removal happens first — if it fails, the DB is
    left untouched.
    """
    result = await _bridge("POST", "/v1/docker/rm", json={"container_name": container_name})
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.get("stderr", "Container removal failed"),
        )
    inst_result = await db.execute(
        select(DeployInstallation).where(DeployInstallation.container_name == container_name)
    )
    removed_installations = 0
    for inst in inst_result.scalars().all():
        await db.delete(inst)
        removed_installations += 1
    ignore_result = await db.execute(
        select(DeploySyncIgnore).where(DeploySyncIgnore.container_name == container_name)
    )
    for ignore in ignore_result.scalars().all():
        await db.delete(ignore)
    await db.commit()
    return {"ok": True, "container": container_name, "installations_removed": removed_installations}


@router.get("/containers/{container_name}/logs")
async def get_container_logs(
    container_name: str,
    lines: int = Query(default=100, le=2000),
):
    """Return the last N log lines for a container."""
    result = await _bridge(
        "POST", "/v1/docker/logs",
        json={"container_name": container_name, "lines": lines},
    )
    return {"logs": result.get("logs", ""), "container": container_name}


@router.get("/containers/{container_name}/inspect")
async def inspect_container(container_name: str):
    """Return full docker inspect output for a container."""
    result = await _bridge("POST", "/v1/docker/inspect", json={"container_name": container_name})
    return result.get("inspect", {})


@router.get("/volumes", response_model=list[DockerVolumeOut])
async def list_volumes():
    """Return all Docker volumes with driver, mountpoint and container usage."""
    data = await _bridge("POST", "/v1/docker/volumes")
    return [DockerVolumeOut(**v) for v in data.get("volumes", [])]


@router.delete("/volumes/{volume_name}")
async def remove_volume(volume_name: str):
    """Remove a named Docker volume via the host-bridge.

    Docker refuses to remove volumes still in use by a container — that error
    is surfaced as a 502 with the docker message.
    """
    result = await _bridge("POST", "/v1/docker/volume-rm", json={"volume_name": volume_name})
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.get("stderr", "Volume removal failed"),
        )
    return {"ok": True, "volume": volume_name}


@router.get("/networks", response_model=list[DockerNetworkOut])
async def list_networks():
    """Return all Docker networks with driver, subnets and attached containers."""
    data = await _bridge("POST", "/v1/docker/networks")
    return [DockerNetworkOut(**n) for n in data.get("networks", [])]


@router.delete("/networks/{network_name}")
async def remove_network(network_name: str):
    """Remove a Docker network via the host-bridge.

    Docker refuses predefined networks (bridge/host/none) and networks with
    attached containers — those errors surface as 502 with the docker message.
    """
    result = await _bridge("POST", "/v1/docker/network-rm", json={"network_name": network_name})
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.get("stderr", "Network removal failed"),
        )
    return {"ok": True, "network": network_name}


@router.get("/images", response_model=list[DockerImageOut])
async def list_images():
    """Return all Docker images, flagging which ones no container (running
    or stopped) currently references."""
    data = await _bridge("POST", "/v1/docker/images")
    return [DockerImageOut(**i) for i in data.get("images", [])]


@router.delete("/images")
async def remove_image(ref: str = Query(..., description='Image "repo:tag", or ID for dangling images')):
    """Remove a Docker image via the host-bridge.

    Takes the reference as a query param (not a path segment) because a
    "repo:tag" can itself contain slashes (e.g. a registry namespace like
    "ghcr.io/org/image:latest"), which would otherwise collide with FastAPI's
    path-segment routing. Docker refuses to remove an image still
    referenced by a container (running or stopped) — that error surfaces as
    a 502 with the docker message.
    """
    result = await _bridge("POST", "/v1/docker/image-rm", json={"ref": ref})
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.get("stderr", "Image removal failed"),
        )
    return {"ok": True, "image": ref}


# ---------------------------------------------------------------------------
# Installation registry CRUD
# ---------------------------------------------------------------------------

@router.get("/installations", response_model=list[DeployInstallationOutEnriched])
async def list_installations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DeployInstallation).order_by(DeployInstallation.order_index, DeployInstallation.name)
    )
    installations = list(result.scalars().all())
    # Resolve product names in one batch
    product_ids = {i.product_id for i in installations if i.product_id}
    product_names: dict[uuid.UUID, str] = {}
    if product_ids:
        prod_result = await db.execute(
            select(Product).where(Product.id.in_(product_ids))
        )
        for p in prod_result.scalars().all():
            product_names[p.id] = p.name
    enriched = []
    for inst in installations:
        out = DeployInstallationOutEnriched.model_validate(inst)
        out.product_name = product_names.get(inst.product_id) if inst.product_id else None
        enriched.append(out)
    return enriched


@router.post("/installations", response_model=DeployInstallationOut, status_code=status.HTTP_201_CREATED)
async def create_installation(payload: DeployInstallationCreate, db: AsyncSession = Depends(get_db)):
    inst = DeployInstallation(**payload.model_dump())
    db.add(inst)
    # Re-registering a container the user previously deleted lifts its
    # sync-ignore entry so /sync manages it again.
    if inst.container_name:
        result = await db.execute(
            select(DeploySyncIgnore).where(DeploySyncIgnore.container_name == inst.container_name)
        )
        for ignore in result.scalars().all():
            await db.delete(ignore)
    await db.commit()
    await db.refresh(inst)
    return inst


@router.get("/installations/{installation_id}", response_model=DeployInstallationOut)
async def get_installation(installation_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    inst = await db.get(DeployInstallation, installation_id)
    if not inst:
        raise HTTPException(status_code=404, detail="Installation not found")
    return inst


@router.put("/installations/{installation_id}", response_model=DeployInstallationOut)
async def update_installation(
    installation_id: uuid.UUID,
    payload: DeployInstallationUpdate,
    db: AsyncSession = Depends(get_db),
):
    inst = await db.get(DeployInstallation, installation_id)
    if not inst:
        raise HTTPException(status_code=404, detail="Installation not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(inst, field, value)
    await db.commit()
    await db.refresh(inst)
    return inst


@router.delete("/installations/{installation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_installation(installation_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    inst = await db.get(DeployInstallation, installation_id)
    if not inst:
        raise HTTPException(status_code=404, detail="Installation not found")
    # Remember the container name so /sync doesn't auto-recreate the
    # installation while the container still exists in Docker.
    if inst.container_name:
        result = await db.execute(
            select(DeploySyncIgnore).where(DeploySyncIgnore.container_name == inst.container_name)
        )
        if not result.scalars().first():
            db.add(DeploySyncIgnore(container_name=inst.container_name))
    await db.delete(inst)
    await db.commit()


# ---------------------------------------------------------------------------
# Group CRUD
#
# Installations reference groups by name (group_name string), so rename and
# delete keep the two in sync here at the API layer.
# ---------------------------------------------------------------------------

@router.get("/groups", response_model=list[DeployGroupOut])
async def list_groups(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DeployGroup).order_by(DeployGroup.order_index, DeployGroup.name)
    )
    return list(result.scalars().all())


@router.post("/groups", response_model=DeployGroupOut, status_code=status.HTTP_201_CREATED)
async def create_group(payload: DeployGroupCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DeployGroup).where(DeployGroup.name == payload.name))
    if result.scalars().first():
        raise HTTPException(status_code=409, detail=f"Group '{payload.name}' already exists")
    group = DeployGroup(**payload.model_dump())
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return group


@router.put("/groups/{group_id}", response_model=DeployGroupOut)
async def update_group(
    group_id: uuid.UUID,
    payload: DeployGroupUpdate,
    db: AsyncSession = Depends(get_db),
):
    group = await db.get(DeployGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    data = payload.model_dump(exclude_unset=True)
    new_name = data.get("name")
    if new_name and new_name != group.name:
        result = await db.execute(select(DeployGroup).where(DeployGroup.name == new_name))
        if result.scalars().first():
            raise HTTPException(status_code=409, detail=f"Group '{new_name}' already exists")
        # Propagate the rename to installations that reference the old name.
        await db.execute(
            sa_update(DeployInstallation)
            .where(DeployInstallation.group_name == group.name)
            .values(group_name=new_name)
        )
    for field, value in data.items():
        setattr(group, field, value)
    await db.commit()
    await db.refresh(group)
    return group


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(group_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    group = await db.get(DeployGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    # Installations keep existing but become ungrouped.
    await db.execute(
        sa_update(DeployInstallation)
        .where(DeployInstallation.group_name == group.name)
        .values(group_name=None)
    )
    await db.delete(group)
    await db.commit()


# ---------------------------------------------------------------------------
# Sync: auto-register Docker containers not yet in the registry
# ---------------------------------------------------------------------------

@router.post("/sync")
async def sync_from_docker(db: AsyncSession = Depends(get_db)):
    """Compare live Docker containers with the registry.

    For every container returned by `docker ps -a` that has no matching
    DeployInstallation (matched on container_name), create a new installation
    with sensible defaults derived from the live docker output. Containers
    listed in deploy_sync_ignores (user deleted the installation while the
    container still existed) are never auto-recreated.

    Also updates the `ports` field on existing installations whose container
    is currently live and whose registered ports list is empty.

    Returns { created: int, updated: int, skipped: int, ignored: int, names_created: [...] }
    """
    # Fetch live containers (may raise 502 if host-bridge is down).
    data = await _bridge("POST", "/v1/docker/ps")
    live_containers: list[dict] = data.get("containers", [])

    # Build a map of container_name → existing installation.
    result = await db.execute(select(DeployInstallation))
    existing = {inst.container_name: inst for inst in result.scalars().all() if inst.container_name}

    ignore_result = await db.execute(select(DeploySyncIgnore.container_name))
    ignored_names = set(ignore_result.scalars().all())

    created_names: list[str] = []
    updated_names: list[str] = []
    skipped = 0
    ignored = 0

    for c in live_containers:
        cname: str = c.get("Names", "").strip()
        if not cname:
            continue
        if cname not in existing and cname in ignored_names:
            ignored += 1
            continue

        raw_ports: str = c.get("Ports", "") or ""
        # Parse "0.0.0.0:8000->8000/tcp, ..." into ["8000:8000", ...]
        port_list: list[str] = []
        for seg in raw_ports.split(","):
            seg = seg.strip()
            if "->" in seg:
                # "0.0.0.0:8000->8000/tcp" → "8000:8000"
                host_part = seg.split("->")[0]
                container_port = seg.split("->")[1].split("/")[0]
                host_port = host_part.split(":")[-1]
                mapping = f"{host_port}:{container_port}"
                if mapping not in port_list:
                    port_list.append(mapping)

        if cname in existing:
            inst = existing[cname]
            # Update ports if previously empty and now we have data.
            if port_list and not inst.ports:
                inst.ports = port_list
                updated_names.append(cname)
            else:
                skipped += 1
        else:
            # Auto-register with defaults.
            new_inst = DeployInstallation(
                name=cname,
                container_name=cname,
                restart_command=f"docker restart {cname}",
                ports=port_list or None,
            )
            db.add(new_inst)
            created_names.append(cname)

    if created_names or updated_names:
        await db.commit()

    return {
        "created": len(created_names),
        "updated": len(updated_names),
        "skipped": skipped,
        "ignored": ignored,
        "names_created": created_names,
        "names_updated": updated_names,
    }
