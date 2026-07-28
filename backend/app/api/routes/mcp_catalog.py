"""MCP catalog routes -- register a server once, assign it to agents/
projects from one place, instead of retyping the same command/args/env for
each agent's own `/mcp` entry by hand.

Mounted at /api/v1/mcp-catalog (this router owns its full prefix per the
foundation convention). Does not replace `/agents/mcp-servers` (agent.py) or
`/projects/{id}/mcp-servers` (project.py) -- those stay the direct,
per-target editors; this is a layer on top that can push one definition to
many targets, with `apply_to_all_agents` covering "every agent, including
ones registered later" (see core/mcp_catalog_apply.py and agent.py's
create_agent/sync_agent_runtimes hooks).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.mcp_catalog import (
    McpCatalogAssignIn,
    McpCatalogAssignmentOut,
    McpCatalogServerIn,
    McpCatalogServerOut,
)
from app.core import agent_mcp
from app.core.mcp_catalog_apply import (
    apply_catalog_server_to_agent,
    apply_global_server_to_all_agents,
)
from app.db.base import get_db
from app.db.models.agent import Agent
from app.db.models.mcp_catalog import (
    MCP_CATALOG_ASSIGNMENT_TARGET_TYPES,
    McpCatalogAssignment,
    McpCatalogServer,
)
from app.db.models.project import Project

router = APIRouter(prefix="/api/v1/mcp-catalog", tags=["mcp-catalog"])


async def _get_server_or_404(db: AsyncSession, server_id: uuid.UUID) -> McpCatalogServer:
    server = await db.get(McpCatalogServer, server_id)
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP catalog server not found")
    return server


@router.get("/servers", response_model=list[McpCatalogServerOut])
async def list_catalog_servers(db: AsyncSession = Depends(get_db)) -> list[McpCatalogServer]:
    result = await db.execute(select(McpCatalogServer).order_by(McpCatalogServer.name))
    return list(result.scalars().all())


@router.post("/servers", response_model=McpCatalogServerOut, status_code=status.HTTP_201_CREATED)
async def create_catalog_server(
    payload: McpCatalogServerIn, db: AsyncSession = Depends(get_db)
) -> McpCatalogServer:
    if bool(payload.command) == bool(payload.url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either a command (stdio server) or a url (HTTP server), not both.",
        )
    server = McpCatalogServer(**payload.model_dump())
    db.add(server)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A catalog server with this name already exists"
        ) from None
    await db.refresh(server)
    if server.apply_to_all_agents:
        await apply_global_server_to_all_agents(db, server)
        await db.commit()
    return server


@router.put("/servers/{server_id}", response_model=McpCatalogServerOut)
async def update_catalog_server(
    server_id: uuid.UUID, payload: McpCatalogServerIn, db: AsyncSession = Depends(get_db)
) -> McpCatalogServer:
    server = await _get_server_or_404(db, server_id)
    if bool(payload.command) == bool(payload.url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either a command (stdio server) or a url (HTTP server), not both.",
        )
    was_global = server.apply_to_all_agents
    for field, value in payload.model_dump().items():
        setattr(server, field, value)
    await db.commit()
    await db.refresh(server)

    # Only re-push to every agent when the flag just turned on, or the
    # definition itself changed while already global -- an edit to a
    # non-global server never silently starts touching every agent.
    if server.apply_to_all_agents:
        await apply_global_server_to_all_agents(db, server)
        await db.commit()
    elif was_global and not server.apply_to_all_agents:
        # Turning "apply to all" off does not retroactively remove the
        # server from agents it already reached -- same posture as /mcp's
        # own removal-is-explicit rule. The operator can still remove it
        # per agent from /mcp if that's what they want.
        pass
    return server


@router.delete("/servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_catalog_server(server_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    """Deletes the catalog entry and its assignment records. Does NOT remove
    the server from any agent/project config file it was already written
    to -- the catalog is a registry of desired assignments, not a live
    handle on every file it ever touched; remove it from `/mcp` or the
    project's own MCP card if you want it actually uninstalled."""
    server = await _get_server_or_404(db, server_id)
    await db.delete(server)
    await db.commit()


@router.get("/servers/{server_id}/assignments", response_model=list[McpCatalogAssignmentOut])
async def list_catalog_assignments(
    server_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[McpCatalogAssignment]:
    await _get_server_or_404(db, server_id)
    result = await db.execute(
        select(McpCatalogAssignment).where(McpCatalogAssignment.catalog_server_id == server_id)
    )
    return list(result.scalars().all())


@router.post(
    "/servers/{server_id}/assign",
    response_model=McpCatalogAssignmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def assign_catalog_server(
    server_id: uuid.UUID, payload: McpCatalogAssignIn, db: AsyncSession = Depends(get_db)
) -> McpCatalogAssignment:
    server = await _get_server_or_404(db, server_id)
    if payload.target_type not in MCP_CATALOG_ASSIGNMENT_TARGET_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"target_type must be one of {MCP_CATALOG_ASSIGNMENT_TARGET_TYPES}",
        )

    if payload.target_type == "agent":
        agent = await db.get(Agent, payload.target_id)
        if agent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
        assignment = await apply_catalog_server_to_agent(db, server, agent)
        await db.commit()
        await db.refresh(assignment)
        return assignment

    # target_type == "project" -- reuse the project MCP write path
    # (project.py's own upsert route) rather than duplicating the
    # host-bridge call here, same reasoning as this module's docstring.
    from app.api.routes.project import upsert_project_mcp_server  # local import: avoids a routes-import-routes cycle at module load
    from app.api.schemas.project_mcp import ProjectMcpServerIn

    project = await db.get(Project, payload.target_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    assignment = await _get_or_create_project_assignment(db, server.id, project.id)
    try:
        await upsert_project_mcp_server(
            project.id,
            server.name,
            ProjectMcpServerIn(
                runtime_type=payload.runtime_type,
                transport=server.transport,
                command=server.command,
                args=server.args or [],
                env=server.env or {},
                url=server.url,
                enabled=True,
            ),
            db,
        )
    except HTTPException as exc:
        assignment.last_sync_error = str(exc.detail)[:2000]
        await db.commit()
        await db.refresh(assignment)
        return assignment

    from datetime import datetime, timezone

    assignment.last_synced_at = datetime.now(timezone.utc)
    assignment.last_sync_error = None
    await db.commit()
    await db.refresh(assignment)
    return assignment


async def _get_or_create_project_assignment(
    db: AsyncSession, catalog_server_id: uuid.UUID, project_id: uuid.UUID
) -> McpCatalogAssignment:
    result = await db.execute(
        select(McpCatalogAssignment).where(
            McpCatalogAssignment.catalog_server_id == catalog_server_id,
            McpCatalogAssignment.target_type == "project",
            McpCatalogAssignment.target_id == project_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = McpCatalogAssignment(
            catalog_server_id=catalog_server_id, target_type="project", target_id=project_id
        )
        db.add(row)
    return row


@router.delete("/servers/{server_id}/assign/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_catalog_assignment(
    server_id: uuid.UUID, assignment_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> None:
    """Un-assigns AND actually removes the server from the target's own
    config file -- same real-removal behavior as /mcp's own DELETE, so
    unchecking an agent/project here genuinely turns it off rather than
    just silently stopping the catalog's own bookkeeping while the file
    still has it installed."""
    assignment = await db.get(McpCatalogAssignment, assignment_id)
    if assignment is None or assignment.catalog_server_id != server_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    server = await _get_server_or_404(db, server_id)

    if assignment.target_type == "agent":
        agent = await db.get(Agent, assignment.target_id)
        if agent is not None:
            fmt = agent_mcp.format_for(agent.runtime_type)
            host_path = agent_mcp.config_host_path(agent.effective_home_path, fmt) if fmt else None
            if fmt is not None and host_path:
                try:
                    agent_mcp.write_server(host_path, fmt, server.name, None)
                except agent_mcp.McpConfigError:
                    pass  # already gone, or file unreachable -- unassign regardless
    else:
        from app.api.routes.project import delete_project_mcp_server  # local import: avoids a routes-import-routes cycle

        project = await db.get(Project, assignment.target_id)
        if project is not None and project.working_directory_path:
            try:
                await delete_project_mcp_server(project.id, server.name, "claude", db)
            except HTTPException:
                pass

    await db.delete(assignment)
    await db.commit()
