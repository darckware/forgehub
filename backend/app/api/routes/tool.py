"""Tool domain — registry of tools built by agents.

Every agent creates its own operational tooling (e.g. Aegis, the
cybersecurity agent, builds network scanners, system monitors and report
generators). This CRUD surface records each tool's file location, what it
does, its category and the responsible agent, keeping the PRD's core
traceability invariant: no tool exists without an owner.

Endpoints:
  GET    /api/v1/tools           – list (filters: agent_id, category,
                                   status, q free-text over name/
                                   description/file_path); each row carries
                                   agent_name resolved via join
  GET    /api/v1/tools/categories – distinct categories in use (feeds the
                                   category filter/autocomplete in the UI)
  POST   /api/v1/tools/scan      – populate the registry from the live
                                   filesystem (profile scripts + central
                                   cron/scripts catalogs); ownership falls
                                   back to Athos when no responsible agent
                                   can be determined
  POST   /api/v1/tools           – create (agent must exist; name unique
                                   per agent)
  GET    /api/v1/tools/{id}      – get one
  GET    /api/v1/tools/{id}/content – read the tool's file from disk
  PUT    /api/v1/tools/{id}/content – overwrite the tool's file on disk
  PATCH  /api/v1/tools/{id}      – partial update
  DELETE /api/v1/tools/{id}      – delete registry entry; ?delete_file=true
                                   also removes the file from disk

file_path is always stored as the HOST path (/root/.hermes/...); the
content endpoints remap it to this container's mounts at access time
(see _to_container_path).

Note (2026-07-06): the old central catalogs (/root/.hermes/scripts,
/root/.hermes/crons) were migrated into the athos profile and removed --
existing rows' file_path was rewritten to the profile path at the same time
(one-off DB UPDATE, not a migration since it's data, not schema).
"""
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.cron_scripts import _load_all_cron_jobs, _scan_script_paths
from app.api.schemas.tool import ToolContentIn, ToolContentOut
from app.api.schemas.tool import ToolCreate, ToolOut, ToolScanOut, ToolUpdate
from app.db.base import get_db
from app.db.models.agent import Agent
from app.db.models.tool import AGENT_TOOL_STATUSES, AgentTool

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])

# Coordinator agent that inherits ownership of any scanned tool whose
# responsible agent can't be determined from its location or cron usage.
FALLBACK_PROFILE_SLUG = "athos"

# Application-type classification for agent tools ("tipo de aplicação").
# Ordered: the first type whose keywords match the tool's name/description
# wins, so more specific types come before broader ones. This is the same
# taxonomy offered in the UI's category field; manual entries may still use
# free-form values.
APPLICATION_TYPE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("network", ("network", "net", "ssh", "dns", "firewall", "vpn", "port", "wifi", "proxy")),
    ("security", ("security", "secur", "hardening", "credential", "auth", "cert", "intrusion", "threat")),
    ("backup", ("backup", "restore", "snapshot")),
    ("database", ("db", "database", "sql", "postgres", "sqlite", "integrity")),
    ("monitoring", ("monitor", "watchdog", "health", "status", "battery", "heartbeat", "uptime", "check")),
    ("reporting", ("report", "summary", "digest", "news", "notify", "telegram", "alert")),
    ("maintenance", ("cleanup", "clean", "trash", "purge", "rotate", "archive", "audit", "maintenance", "fix", "logs")),
    ("deployment", ("deploy", "install", "setup", "provision", "release", "boot")),
    ("integration", ("github", "sync", "webhook", "gateway", "bridge")),
    ("automation", ("cron", "wrapper", "wrapped", "tick", "schedule", "task")),
]

_TOKEN_RE = re.compile(r"[^a-z0-9]+")

# Host path prefix ↔ container mount (matches docker-compose.yml volumes).
# file_path is stored host-side so the UI shows real server paths; file
# access from inside this container goes through the mounted equivalent.
# The old central catalogs (/root/.hermes/scripts, /root/.hermes/crons) have
# no mount anymore -- they were migrated into /root/.hermes/profiles/athos.
_HOST_TO_CONTAINER: tuple[tuple[str, str], ...] = (
    ("/root/.hermes/profiles/", "/profiles/"),
)

_MAX_CONTENT_BYTES = 1_000_000


def _to_host_path(path: str) -> str:
    for host_prefix, container_prefix in _HOST_TO_CONTAINER:
        if path.startswith(container_prefix):
            return host_prefix + path[len(container_prefix):]
    return path


def _to_container_path(tool: "AgentTool") -> Path:
    """Resolve the tool's stored host path to this container's mount.

    Raises 400 when the path is outside the known catalogs (manual entries
    may point anywhere on the host — those files aren't reachable from the
    backend container, so content endpoints refuse them).
    """
    for host_prefix, container_prefix in _HOST_TO_CONTAINER:
        if tool.file_path.startswith(host_prefix):
            resolved = Path(container_prefix + tool.file_path[len(host_prefix):])
            # Guard against ../ escapes out of the mounted catalog dirs.
            if ".." in resolved.parts:
                break
            return resolved
    raise HTTPException(
        status_code=400,
        detail=(
            "File is outside the managed catalog (/root/.hermes/profiles) "
            "— access it directly on the host"
        ),
    )


def _classify_application_type(name: str, description: str | None) -> str:
    """Infer the tool's application type from its name (primary signal) and
    header description (secondary). Matches whole tokens (or their prefixes:
    'scanner' → 'scan'), never raw substrings — 'report' must not hit the
    network type via 'port'."""
    for hay in (name.lower(), (description or "").lower()):
        tokens = [t for t in _TOKEN_RE.split(hay) if t]
        for app_type, keywords in APPLICATION_TYPE_KEYWORDS:
            if any(t.startswith(kw) for kw in keywords for t in tokens):
                return app_type
    return "general"


def _to_out(tool: AgentTool, agent_name: str | None) -> ToolOut:
    out = ToolOut.model_validate(tool)
    out.agent_name = agent_name
    return out


def _validate_status(value: str) -> None:
    if value not in AGENT_TOOL_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{value}'. Allowed: {', '.join(AGENT_TOOL_STATUSES)}",
        )


async def _require_agent(db: AsyncSession, agent_id: uuid.UUID) -> Agent:
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.get("", response_model=list[ToolOut])
async def list_tools(
    agent_id: uuid.UUID | None = None,
    category: str | None = None,
    tool_status: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, max_length=200),
    db: AsyncSession = Depends(get_db),
) -> list[ToolOut]:
    filters = []
    if agent_id is not None:
        filters.append(AgentTool.agent_id == agent_id)
    if category is not None:
        filters.append(AgentTool.category == category)
    if tool_status is not None:
        _validate_status(tool_status)
        filters.append(AgentTool.status == tool_status)
    if q:
        pattern = f"%{q}%"
        filters.append(
            or_(
                AgentTool.name.ilike(pattern),
                AgentTool.description.ilike(pattern),
                AgentTool.file_path.ilike(pattern),
            )
        )

    rows = await db.execute(
        select(AgentTool, Agent.name)
        .join(Agent, Agent.id == AgentTool.agent_id)
        .where(*filters)
        .order_by(Agent.name, AgentTool.name)
    )
    return [_to_out(tool, agent_name) for tool, agent_name in rows.all()]


@router.get("/categories", response_model=list[str])
async def list_categories(db: AsyncSession = Depends(get_db)) -> list[str]:
    rows = await db.execute(
        select(AgentTool.category).distinct().order_by(AgentTool.category)
    )
    return list(rows.scalars())


@router.post("/scan", response_model=ToolScanOut)
async def scan_tools(db: AsyncSession = Depends(get_db)) -> ToolScanOut:
    """Populate the registry from the live filesystem.

    Scans every profile's scripts/ dir (see cron_scripts._scan_script_paths)
    and registers each script found as an agent tool:

    - responsible agent: the profile that owns the file; otherwise the
      fallback coordinator (Athos).
    - category: application type inferred from name/description
      (_classify_application_type).
    - description: extracted from the file's header comment/docstring; a
      placeholder asking for review when the file has none.

    Idempotent: a file whose path is already registered is skipped, so
    re-scanning never duplicates or clobbers manual edits.
    """
    agents = (await db.execute(select(Agent))).scalars().all()
    agents_by_slug = {a.profile_slug: a for a in agents if a.profile_slug}
    fallback = agents_by_slug.get(FALLBACK_PROFILE_SLUG)
    if fallback is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Fallback agent (profile '{FALLBACK_PROFILE_SLUG}') not found — "
                "run the Hermes agents sync first"
            ),
        )

    # Script name -> owning profile, according to who schedules it via cron.
    cron_profile_by_script = {
        job["script"]: job.get("profile")
        for job in _load_all_cron_jobs()
        if job.get("script")
    }

    existing_rows = (
        await db.execute(select(AgentTool.file_path, AgentTool.agent_id, AgentTool.name))
    ).all()
    existing_paths = {r.file_path for r in existing_rows}
    existing_names = {(r.agent_id, r.name) for r in existing_rows}

    scanned = 0
    created = 0
    skipped = 0
    for entry in _scan_script_paths():
        if not entry["exists"]:
            continue
        scanned += 1
        host_path = _to_host_path(entry["path"])
        if host_path in existing_paths:
            skipped += 1
            continue

        slug = entry["agent"] or cron_profile_by_script.get(entry["name"])
        owner = agents_by_slug.get(slug) if slug else None
        agent = owner or fallback

        name = entry["name"][:150]
        if (agent.id, name) in existing_names:
            skipped += 1
            continue
        description = entry["description"] or (
            "No description found in the file header — review and complete."
        )
        db.add(
            AgentTool(
                id=uuid.uuid4(),
                agent_id=agent.id,
                name=name,
                description=description,
                file_path=host_path,
                category=_classify_application_type(name, entry["description"]),
                status="active",
            )
        )
        existing_paths.add(host_path)
        existing_names.add((agent.id, name))
        created += 1

    if created:
        await db.commit()
    return ToolScanOut(scanned=scanned, created=created, skipped=skipped)


@router.post("", response_model=ToolOut, status_code=status.HTTP_201_CREATED)
async def create_tool(payload: ToolCreate, db: AsyncSession = Depends(get_db)) -> ToolOut:
    _validate_status(payload.status)
    agent = await _require_agent(db, payload.agent_id)

    duplicate = await db.execute(
        select(func.count())
        .select_from(AgentTool)
        .where(AgentTool.agent_id == payload.agent_id, AgentTool.name == payload.name)
    )
    if duplicate.scalar_one():
        raise HTTPException(
            status_code=409,
            detail=f"Agent '{agent.name}' already has a tool named '{payload.name}'",
        )

    tool = AgentTool(id=uuid.uuid4(), **payload.model_dump())
    db.add(tool)
    await db.commit()
    await db.refresh(tool)
    return _to_out(tool, agent.name)


@router.get("/{tool_id}", response_model=ToolOut)
async def get_tool(tool_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ToolOut:
    row = (
        await db.execute(
            select(AgentTool, Agent.name)
            .join(Agent, Agent.id == AgentTool.agent_id)
            .where(AgentTool.id == tool_id)
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Tool not found")
    tool, agent_name = row
    return _to_out(tool, agent_name)


@router.get("/{tool_id}/content", response_model=ToolContentOut)
async def get_tool_content(tool_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ToolContentOut:
    """Read the tool's file from disk (host path remapped to this
    container's mounts)."""
    tool = await db.get(AgentTool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    path = _to_container_path(tool)
    if not path.is_file():
        return ToolContentOut(file_path=tool.file_path, content=None, exists=False)
    if path.stat().st_size > _MAX_CONTENT_BYTES:
        raise HTTPException(status_code=413, detail="File is too large to open here (>1 MB)")
    try:
        content = path.read_text(errors="replace")
    except OSError as exc:
        raise HTTPException(status_code=502, detail=f"Could not read file: {exc}") from exc
    return ToolContentOut(file_path=tool.file_path, content=content, exists=True)


@router.put("/{tool_id}/content", response_model=ToolContentOut)
async def save_tool_content(
    tool_id: uuid.UUID, payload: ToolContentIn, db: AsyncSession = Depends(get_db)
) -> ToolContentOut:
    """Overwrite the tool's file on disk with the given content."""
    tool = await db.get(AgentTool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    path = _to_container_path(tool)
    if len(payload.content.encode()) > _MAX_CONTENT_BYTES:
        raise HTTPException(status_code=413, detail="Content too large (>1 MB)")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload.content)
    except OSError as exc:
        raise HTTPException(status_code=502, detail=f"Could not write file: {exc}") from exc
    return ToolContentOut(file_path=tool.file_path, content=payload.content, exists=True)


@router.patch("/{tool_id}", response_model=ToolOut)
async def update_tool(
    tool_id: uuid.UUID, payload: ToolUpdate, db: AsyncSession = Depends(get_db)
) -> ToolOut:
    tool = await db.get(AgentTool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    updates = payload.model_dump(exclude_unset=True)
    if "status" in updates:
        _validate_status(updates["status"])
    if "agent_id" in updates:
        await _require_agent(db, updates["agent_id"])

    for field, value in updates.items():
        setattr(tool, field, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="The responsible agent already has a tool with this name",
        ) from None
    await db.refresh(tool)
    agent = await db.get(Agent, tool.agent_id)
    return _to_out(tool, agent.name if agent else None)


@router.delete("/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool(
    tool_id: uuid.UUID,
    delete_file: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete the registry entry; with ?delete_file=true also remove the
    tool's file from disk (file removal happens first — if it fails, the
    registry entry survives). Files outside the managed catalogs can't be
    reached from this container, so only the registry entry is removed."""
    tool = await db.get(AgentTool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    if delete_file:
        try:
            path = _to_container_path(tool)
        except HTTPException:
            path = None
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                raise HTTPException(status_code=502, detail=f"Could not delete file: {exc}") from exc
    await db.delete(tool)
    await db.commit()
