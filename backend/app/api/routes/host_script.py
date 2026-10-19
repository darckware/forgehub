"""Script library and schedules – Remote Access plan step 1 (2026-10-16,
docs/architecture/REMOTE_MAINTENANCE_PLAN.md). Admin-only: these scripts run
as an administrator on client machines.

Endpoints:
  GET    /api/v1/host-scripts/categories          – classification list
  POST   /api/v1/host-scripts/categories          – add a classification
  GET    /api/v1/host-scripts                     – library (?platform=&category_id=&include_archived=)
  POST   /api/v1/host-scripts                     – new script (version 1)
  GET    /api/v1/host-scripts/{id}                – script + versions
  PUT    /api/v1/host-scripts/{id}                – edit; content/parameters change = new version
  POST   /api/v1/host-scripts/{id}:archive|:restore
  GET    /api/v1/host-schedules                   – schedules
  POST   /api/v1/host-schedules                   – schedule a script (once / weekly)
  PUT    /api/v1/host-schedules/{id}              – edit (enable/disable included)
  DELETE /api/v1/host-schedules/{id}
  POST   /api/v1/host-schedules/{id}:run-now      – fire it now (does not move the next run)

System scripts (`is_system`, shipped by ForgeHub: preparation, enrollment,
rotations) can be run but not edited or archived here.
"""
import re
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.host_execution import launch_execution, prepare_script_run, resolve_targets
from app.api.schemas.host_execution import HostExecutionDetail
from app.api.schemas.host_script import (
    CategoryCreate,
    CategoryOut,
    ScheduleCreate,
    ScheduleOut,
    ScheduleUpdate,
    ScriptCreate,
    ScriptDetail,
    ScriptOut,
    ScriptRendered,
    ScriptRenderRequest,
    ScriptUpdate,
    ScriptVersionOut,
)
from app.core.deps import get_current_admin
from app.core.host_scripts import ScriptError, next_run, validate_parameters, validate_schedule
from app.db.base import get_db
from app.db.models.governance import AuditEvent
from app.db.models.host_script import HostSchedule, HostScript, HostScriptCategory, HostScriptVersion
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/host-scripts", tags=["remote-access"])
schedules_router = APIRouter(prefix="/api/v1/host-schedules", tags=["remote-access"])


def _slug(label: str) -> str:
    text = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:60] or "categoria"


def _audit(db: AsyncSession, entity_type: str, entity_id: uuid.UUID, event: str, actor: str, payload=None):
    db.add(AuditEvent(entity_type=entity_type, entity_id=entity_id, event_type=event, actor=actor, payload=payload))


# --- categories ---------------------------------------------------------------

@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(db: AsyncSession = Depends(get_db), _admin: User = Depends(get_current_admin)):
    return list((await db.execute(select(HostScriptCategory).order_by(HostScriptCategory.label))).scalars())


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreate, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)
):
    row = HostScriptCategory(slug=_slug(payload.label), label=payload.label.strip(), description=payload.description)
    db.add(row)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="This classification already exists") from None
    _audit(db, "host_script_category", row.id, "created", admin.username, {"label": row.label})
    await db.commit()
    await db.refresh(row)
    return row


# --- scripts ------------------------------------------------------------------

def _parameters(raw) -> list[dict]:
    try:
        return validate_parameters([p.model_dump() if hasattr(p, "model_dump") else p for p in raw or []])
    except ScriptError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _check_category(db: AsyncSession, category_id: uuid.UUID) -> None:
    if not await db.get(HostScriptCategory, category_id):
        raise HTTPException(status_code=422, detail="Unknown classification")


@router.get("", response_model=list[ScriptOut])
async def list_scripts(
    platform: str | None = Query(default=None, pattern="^(windows|linux|macos)$"),
    category_id: uuid.UUID | None = None,
    include_archived: bool = False,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    query = select(HostScript).order_by(HostScript.name)
    if platform:
        query = query.where(HostScript.platform == platform)
    if category_id:
        query = query.where(HostScript.category_id == category_id)
    if not include_archived:
        query = query.where(HostScript.archived.is_(False))
    return list((await db.execute(query)).scalars())


@router.post("", response_model=ScriptOut, status_code=status.HTTP_201_CREATED)
async def create_script(payload: ScriptCreate, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    await _check_category(db, payload.category_id)
    params = _parameters(payload.parameters)
    script = HostScript(
        name=payload.name.strip(), category_id=payload.category_id, description=payload.description,
        platform=payload.platform, risk=payload.risk, timeout_seconds=payload.timeout_seconds,
        parameters=params, content=payload.content, current_version=1,
        created_by=admin.username, updated_by=admin.username,
    )
    db.add(script)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A script with this name already exists for this platform") from None
    db.add(HostScriptVersion(script_id=script.id, version=1, content=payload.content, parameters=params,
                             changed_by=admin.username, note="Criado"))
    _audit(db, "host_script", script.id, "created", admin.username, {"name": script.name, "platform": script.platform})
    await db.commit()
    await db.refresh(script)
    return script


async def _get_script(db: AsyncSession, script_id: uuid.UUID) -> HostScript:
    script = await db.get(HostScript, script_id)
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
    return script


@router.get("/{script_id}", response_model=ScriptDetail)
async def get_script(script_id: uuid.UUID, db: AsyncSession = Depends(get_db), _admin: User = Depends(get_current_admin)):
    script = await _get_script(db, script_id)
    versions = list(
        (await db.execute(
            select(HostScriptVersion).where(HostScriptVersion.script_id == script_id).order_by(HostScriptVersion.version.desc())
        )).scalars()
    )
    detail = ScriptDetail.model_validate(script)
    detail.versions = [ScriptVersionOut.model_validate(v) for v in versions]
    return detail


@router.put("/{script_id}", response_model=ScriptOut)
async def update_script(
    script_id: uuid.UUID, payload: ScriptUpdate, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)
):
    script = await _get_script(db, script_id)
    if script.is_system:
        raise HTTPException(status_code=409, detail="System scripts are maintained by ForgeHub")
    fields = payload.model_dump(exclude_unset=True)
    note = fields.pop("note", None)
    if "category_id" in fields:
        await _check_category(db, fields["category_id"])
    if "parameters" in fields:
        fields["parameters"] = _parameters(payload.parameters)
    new_content = fields.get("content", script.content)
    new_params = fields.get("parameters", script.parameters)
    versioned = new_content != script.content or new_params != script.parameters
    for key, value in fields.items():
        setattr(script, key, value)
    script.updated_by = admin.username
    if versioned:
        script.current_version += 1
        db.add(HostScriptVersion(script_id=script.id, version=script.current_version, content=new_content,
                                 parameters=new_params, changed_by=admin.username, note=note))
    _audit(db, "host_script", script.id, "updated", admin.username,
           {"version": script.current_version, "new_version": versioned})
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A script with this name already exists for this platform") from None
    await db.refresh(script)
    return script


@router.post("/{script_id}:render", response_model=ScriptRendered)
async def render_script_text(
    script_id: uuid.UUID, payload: ScriptRenderRequest, db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """The script with its parameters filled in, to paste on a machine that
    has no SSH yet (through RustDesk). Contains the parameter values as
    typed -- secrets included -- so it is audited and never stored."""
    script = await _get_script(db, script_id)
    command, shell, _secrets = await prepare_script_run(script, payload.parameter_values)
    _audit(db, "host_script", script.id, "rendered_for_copy", admin.username, {"version": script.current_version})
    await db.commit()
    return ScriptRendered(script_id=script.id, version=script.current_version, shell=shell, script=command)


@router.post("/{script_id}:archive", response_model=ScriptOut)
async def archive_script(script_id: uuid.UUID, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    script = await _get_script(db, script_id)
    if script.is_system:
        raise HTTPException(status_code=409, detail="System scripts are maintained by ForgeHub")
    script.archived = True
    _audit(db, "host_script", script.id, "archived", admin.username)
    await db.commit()
    await db.refresh(script)
    return script


@router.post("/{script_id}:restore", response_model=ScriptOut)
async def restore_script(script_id: uuid.UUID, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    script = await _get_script(db, script_id)
    script.archived = False
    _audit(db, "host_script", script.id, "restored", admin.username)
    await db.commit()
    await db.refresh(script)
    return script


# --- schedules ----------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _compute_next(schedule: HostSchedule, after: datetime) -> datetime | None:
    return next_run(schedule.kind, schedule.run_at, schedule.weekdays, schedule.time_of_day, schedule.timezone, after)


async def _schedule_out(db: AsyncSession, schedule: HostSchedule) -> ScheduleOut:
    out = ScheduleOut.model_validate(schedule)
    script = await db.get(HostScript, schedule.script_id)
    out.script_name = script.name if script else None
    return out


def _validate_schedule(schedule: HostSchedule) -> None:
    try:
        validate_schedule(schedule.kind, schedule.run_at, schedule.weekdays, schedule.time_of_day, schedule.timezone)
    except ScriptError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@schedules_router.get("", response_model=list[ScheduleOut])
async def list_schedules(db: AsyncSession = Depends(get_db), _admin: User = Depends(get_current_admin)):
    rows = list((await db.execute(select(HostSchedule).order_by(HostSchedule.next_run_at.nulls_last()))).scalars())
    return [await _schedule_out(db, r) for r in rows]


@schedules_router.post("", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED)
async def create_schedule(payload: ScheduleCreate, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    script = await _get_script(db, payload.script_id)
    await prepare_script_run(script, payload.parameter_values)  # parameters valid now, not at 3 a.m.
    servers, _ = await resolve_targets(db, payload.server_ids, payload.group_ids)
    if not servers:
        raise HTTPException(status_code=422, detail="Pick at least one machine or a group with machines")
    schedule = HostSchedule(
        name=payload.name.strip(), script_id=script.id, parameter_values=payload.parameter_values,
        server_ids=[str(i) for i in payload.server_ids], group_ids=[str(i) for i in payload.group_ids],
        kind=payload.kind, run_at=payload.run_at, weekdays=sorted(set(payload.weekdays or [])) or None,
        time_of_day=payload.time_of_day, timezone=payload.timezone, window_minutes=payload.window_minutes,
        enabled=True, created_by=admin.username,
    )
    _validate_schedule(schedule)
    schedule.next_run_at = _compute_next(schedule, _now())
    if schedule.next_run_at is None:
        raise HTTPException(status_code=422, detail="The chosen date/time is already in the past")
    db.add(schedule)
    await db.flush()
    _audit(db, "host_schedule", schedule.id, "created", admin.username,
           {"script": script.name, "kind": schedule.kind, "next_run_at": schedule.next_run_at.isoformat()})
    await db.commit()
    await db.refresh(schedule)
    return await _schedule_out(db, schedule)


async def _get_schedule(db: AsyncSession, schedule_id: uuid.UUID) -> HostSchedule:
    schedule = await db.get(HostSchedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return schedule


@schedules_router.put("/{schedule_id}", response_model=ScheduleOut)
async def update_schedule(
    schedule_id: uuid.UUID, payload: ScheduleUpdate, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)
):
    schedule = await _get_schedule(db, schedule_id)
    fields = payload.model_dump(exclude_unset=True)
    for key in ("server_ids", "group_ids"):
        if key in fields:
            fields[key] = [str(i) for i in fields[key]]
    if "weekdays" in fields and fields["weekdays"] is not None:
        fields["weekdays"] = sorted(set(fields["weekdays"])) or None
    for key, value in fields.items():
        setattr(schedule, key, value)
    if "parameter_values" in fields:
        await prepare_script_run(await _get_script(db, schedule.script_id), schedule.parameter_values)
    if "server_ids" in fields or "group_ids" in fields:
        servers, _ = await resolve_targets(db, schedule.server_ids, schedule.group_ids)
        if not servers:
            raise HTTPException(status_code=422, detail="Pick at least one machine or a group with machines")
    _validate_schedule(schedule)
    schedule.next_run_at = _compute_next(schedule, _now()) if schedule.enabled else None
    _audit(db, "host_schedule", schedule.id, "updated", admin.username, {"fields": sorted(fields)})
    await db.commit()
    await db.refresh(schedule)
    return await _schedule_out(db, schedule)


@schedules_router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(schedule_id: uuid.UUID, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    schedule = await _get_schedule(db, schedule_id)
    _audit(db, "host_schedule", schedule.id, "deleted", admin.username, {"name": schedule.name})
    await db.delete(schedule)
    await db.commit()


async def fire_schedule(db: AsyncSession, schedule: HostSchedule, actor: str):
    """One run of a schedule: an ordinary execution with trigger="schedule",
    unreachable machines retried until the window closes."""
    script = await db.get(HostScript, schedule.script_id)
    if script is None or script.archived:
        return None
    command, shell, secrets = await prepare_script_run(script, schedule.parameter_values)
    servers, group_names = await resolve_targets(db, schedule.server_ids, schedule.group_ids)
    if not servers:
        return None
    return await launch_execution(
        db, servers=servers, command=command, shell=shell, timeout_seconds=script.timeout_seconds,
        actor=actor, target_summary=f"{schedule.name}: " + (" + ".join(group_names) or f"{len(servers)} machine(s)"),
        secrets=secrets, trigger="schedule", agent_id=schedule.agent_id, schedule_id=schedule.id,
        script=script, retry_until=_now() + timedelta(minutes=schedule.window_minutes),
        values_for_hook=schedule.parameter_values,
    )


@schedules_router.post("/{schedule_id}:run-now", response_model=HostExecutionDetail, status_code=status.HTTP_201_CREATED)
async def run_schedule_now(schedule_id: uuid.UUID, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    from app.api.routes.host_execution import _detail

    schedule = await _get_schedule(db, schedule_id)
    execution = await fire_schedule(db, schedule, admin.username)
    if execution is None:
        raise HTTPException(status_code=409, detail="The script is archived or the schedule has no machines")
    return await _detail(db, execution)


async def run_due_schedules() -> int:
    """Scheduler pass (every minute, main.py). Each due schedule is claimed
    with FOR UPDATE SKIP LOCKED and its next_run_at moved forward in the same
    transaction -- the dev backend and production share this database, so two
    loops must never fire the same run."""
    from app.db.base import AsyncSessionLocal

    fired = 0
    now = _now()
    async with AsyncSessionLocal() as db:
        due = list(
            (await db.execute(
                select(HostSchedule)
                .where(HostSchedule.enabled.is_(True), HostSchedule.next_run_at.is_not(None), HostSchedule.next_run_at <= now)
                .with_for_update(skip_locked=True)
            )).scalars()
        )
        claimed = []
        for schedule in due:
            schedule.last_run_at = now
            schedule.next_run_at = _compute_next(schedule, now)
            if schedule.kind == "once":
                schedule.enabled = False
            claimed.append(schedule.id)
        await db.commit()
    for schedule_id in claimed:
        async with AsyncSessionLocal() as db:
            schedule = await db.get(HostSchedule, schedule_id)
            try:
                execution = await fire_schedule(db, schedule, schedule.created_by)
            except HTTPException:
                execution = None
            if execution is not None:
                schedule.last_execution_id = execution.id
                await db.commit()
                fired += 1
    return fired
