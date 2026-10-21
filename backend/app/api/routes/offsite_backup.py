"""Off-site backup control (System Control -> "Backup externo", 2026-10-20).

ForgeHub owns the list of what is backed up (one target per project, plus the
system) and the history of every run; the backup itself runs on the host in
Athos' worker (`backup_offsite_projects.sh` -> `backup_offsite_projects.py`),
scheduled by `hermes cron` like every other ecosystem job. The worker pulls
its plan from `/internal/plan` and reports each target through
`/internal/runs` and `/internal/runs:finish`; those three are in main.py's
_PUBLIC_API_PATHS and check the bridge token themselves, like
/client-ops/reports/run-internal.

"Run now" launches the same script through the host-bridge. The script
detaches the worker and returns at once: a first backup takes hours, longer
than both the bridge's exec timeout and Hermes' 1 h script timeout.
"""
from __future__ import annotations

import json
import shlex
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.offsite_backup import (
    OffsiteBackupOverview,
    OffsiteBackupRunFinish,
    OffsiteBackupRunOut,
    OffsiteBackupRunRequest,
    OffsiteBackupRunStart,
    OffsiteBackupSchedule,
    OffsiteBackupTargetCreate,
    OffsiteBackupTargetOut,
    OffsiteBackupTargetWrite,
)
from app.core.config import settings
from app.core.deps import get_current_admin
from app.db.base import get_db
from app.db.models.notification import Notification
from app.db.models.offsite_backup import REPOSITORY_RUN_NAME, OffsiteBackupRun, OffsiteBackupTarget
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/offsite-backup", tags=["offsite-backup"])

ATHOS_SCRIPTS = "/root/.hermes/profiles/athos/scripts"
SCRIPT_NAME = "backup_offsite_projects.sh"
JOBS_FILE = "/root/.hermes/profiles/athos/cron/jobs.json"
REPOSITORY = "rclone:gdrive:vps-backup/restic"
# A worker that died without reporting (host reboot, OOM) leaves its run
# "running"; past this age the UI shows it as interrupted instead.
STALE_RUN_AFTER = timedelta(hours=24)
ALREADY_RUNNING_EXIT = 75


async def _bridge_exec(command: str, *, timeout_seconds: int = 60) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds + 10) as client:
            resp = await client.post(
                f"{settings.CHAT_BRIDGE_URL}/v1/exec",
                headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
                json={"command": command, "timeout_seconds": timeout_seconds},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Host-bridge unreachable: {exc}") from exc
    if resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Host-bridge error: {resp.text[:500]}")
    return resp.json()


def _check_bridge_token(token: str | None) -> None:
    if not settings.CHAT_BRIDGE_TOKEN or token != settings.CHAT_BRIDGE_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bridge token")


def _run_out(run: OffsiteBackupRun | None) -> OffsiteBackupRunOut | None:
    if run is None:
        return None
    out = OffsiteBackupRunOut.model_validate(run)
    if out.status == "running" and datetime.now(timezone.utc) - out.started_at > STALE_RUN_AFTER:
        out.status = "interrupted"
    return out


async def _latest_runs(db: AsyncSession) -> tuple[dict[str, OffsiteBackupRun], dict[str, OffsiteBackupRun]]:
    """Newest run and newest successful run per target name -- by name, not
    id, so the repository maintenance row (no target) is included too."""
    rows = (
        await db.execute(
            select(OffsiteBackupRun)
            .where(OffsiteBackupRun.started_at > datetime.now(timezone.utc) - timedelta(days=400))
            .order_by(OffsiteBackupRun.started_at.desc())
        )
    ).scalars().all()
    last: dict[str, OffsiteBackupRun] = {}
    last_ok: dict[str, OffsiteBackupRun] = {}
    for run in rows:
        last.setdefault(run.target_name, run)
        if run.status == "ok":
            last_ok.setdefault(run.target_name, run)
    return last, last_ok


_SCHEDULE_READER = (
    "python3 - <<'PYEOF'\n"
    "import json\n"
    f"d = json.load(open({JOBS_FILE!r}))\n"
    "jobs = d.get('jobs', d) if isinstance(d, dict) else d\n"
    f"print(json.dumps([j for j in jobs if j.get('script') == {SCRIPT_NAME!r}][:1]))\n"
    "PYEOF"
)


async def _read_schedule() -> tuple[OffsiteBackupSchedule | None, str | None]:
    try:
        data = await _bridge_exec(_SCHEDULE_READER, timeout_seconds=20)
    except HTTPException as exc:
        return None, str(exc.detail)
    if data.get("exit_code") != 0:
        return None, (data.get("stderr") or "").strip()[:300] or "could not read the cron jobs"
    try:
        jobs = json.loads((data.get("stdout") or "").strip() or "[]")
    except ValueError:
        return None, "unexpected cron jobs output"
    if not jobs:
        return None, "not_scheduled"
    job = jobs[0]
    schedule = job.get("schedule") or {}
    return OffsiteBackupSchedule(
        job_id=str(job.get("id") or ""),
        expression=str(job.get("schedule_display") or schedule.get("expr") or ""),
        enabled=bool(job.get("enabled")),
        next_run_at=job.get("next_run_at"),
        last_run_at=job.get("last_run_at"),
        last_status=job.get("last_status"),
    ), None


async def _target_or_404(db: AsyncSession, target_id: uuid.UUID) -> OffsiteBackupTarget:
    target = await db.get(OffsiteBackupTarget, target_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup target not found")
    return target


async def _assert_paths_exist(paths: list[str]) -> None:
    """A typo'd folder would only show up as a failed backup the next night;
    refuse it while the operator is still on the form."""
    command = "for p in " + " ".join(shlex.quote(p) for p in paths) + '; do [ -e "$p" ] || printf "%s\\n" "$p"; done'
    data = await _bridge_exec(command, timeout_seconds=20)
    missing = [line for line in (data.get("stdout") or "").splitlines() if line.strip()]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "These paths don't exist on the host", "missing": missing},
        )


def _target_out(
    target: OffsiteBackupTarget, last: dict[str, OffsiteBackupRun], last_ok: dict[str, OffsiteBackupRun]
) -> OffsiteBackupTargetOut:
    out = OffsiteBackupTargetOut.model_validate(target)
    out.last_run = _run_out(last.get(target.name))
    out.last_success = _run_out(last_ok.get(target.name))
    return out


@router.get("/overview", response_model=OffsiteBackupOverview)
async def overview(_admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    targets = (
        await db.execute(select(OffsiteBackupTarget).order_by(OffsiteBackupTarget.sort_order, OffsiteBackupTarget.label))
    ).scalars().all()
    last, last_ok = await _latest_runs(db)
    schedule, schedule_error = await _read_schedule()
    target_outs = [_target_out(t, last, last_ok) for t in targets]
    maintenance = _run_out(last.get(REPOSITORY_RUN_NAME))
    running = any(t.last_run and t.last_run.status == "running" for t in target_outs) or bool(
        maintenance and maintenance.status == "running"
    )
    return OffsiteBackupOverview(
        repository=REPOSITORY,
        script=f"{ATHOS_SCRIPTS}/{SCRIPT_NAME}",
        schedule=schedule,
        schedule_error=schedule_error,
        running=running,
        repository_maintenance=maintenance,
        targets=target_outs,
    )


@router.post("/targets", response_model=OffsiteBackupTargetOut, status_code=status.HTTP_201_CREATED)
async def create_target(
    payload: OffsiteBackupTargetCreate, _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
):
    if payload.name == REPOSITORY_RUN_NAME:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reserved name")
    await _assert_paths_exist(payload.paths)
    target = OffsiteBackupTarget(**payload.model_dump())
    db.add(target)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A target with this identifier already exists") from exc
    await db.refresh(target)
    return _target_out(target, {}, {})


@router.put("/targets/{target_id}", response_model=OffsiteBackupTargetOut)
async def update_target(
    target_id: uuid.UUID,
    payload: OffsiteBackupTargetWrite,
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    target = await _target_or_404(db, target_id)
    if payload.paths != target.paths:
        await _assert_paths_exist(payload.paths)
    for field, value in payload.model_dump().items():
        setattr(target, field, value)
    await db.commit()
    await db.refresh(target)
    last, last_ok = await _latest_runs(db)
    return _target_out(target, last, last_ok)


@router.delete("/targets/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_target(
    target_id: uuid.UUID, _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> Response:
    """Stops backing the target up. Snapshots already in the repository stay
    (restic's own retention ages them out), and so does the run history."""
    target = await _target_or_404(db, target_id)
    await db.delete(target)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/runs", response_model=list[OffsiteBackupRunOut])
async def list_runs(
    target: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=30, ge=1, le=200),
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(OffsiteBackupRun).order_by(OffsiteBackupRun.started_at.desc()).limit(limit)
    if target:
        query = query.where(OffsiteBackupRun.target_name == target)
    return [_run_out(run) for run in (await db.execute(query)).scalars().all()]


@router.get("/postgres-containers")
async def postgres_containers(_admin: User = Depends(get_current_admin)) -> dict[str, list[str]]:
    data = await _bridge_exec("docker ps --format '{{.Names}}\t{{.Image}}'", timeout_seconds=20)
    names = []
    for line in (data.get("stdout") or "").splitlines():
        name, _, image = line.partition("\t")
        if "postgres" in image.lower() or "postgres" in name.lower() or "pgvector" in image.lower():
            names.append(name.strip())
    return {"containers": sorted(names)}


@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
async def run_now(
    payload: OffsiteBackupRunRequest, _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    enabled = {
        t.name for t in (await db.execute(select(OffsiteBackupTarget).where(OffsiteBackupTarget.enabled.is_(True)))).scalars()
    }
    unknown = [name for name in payload.targets if name not in enabled]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail={"message": "Unknown or disabled targets", "targets": unknown}
        )
    if not enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No enabled backup target")
    command = f"{shlex.quote(f'{ATHOS_SCRIPTS}/{SCRIPT_NAME}')} --trigger manual"
    if payload.targets:
        command += " --targets " + shlex.quote(",".join(payload.targets))
    data = await _bridge_exec(command, timeout_seconds=30)
    if data.get("exit_code") == ALREADY_RUNNING_EXIT:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An off-site backup is already running")
    if data.get("exit_code") != 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=((data.get("stderr") or data.get("stdout") or "").strip()[-500:]) or "Could not start the backup",
        )
    return {"started": True, "targets": payload.targets or sorted(enabled)}


# --- Internal: Athos' worker --------------------------------------------------


@router.get("/internal/plan")
async def internal_plan(
    targets: str | None = Query(default=None, max_length=8000),
    x_bridge_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _check_bridge_token(x_bridge_token)
    query = select(OffsiteBackupTarget).where(OffsiteBackupTarget.enabled.is_(True)).order_by(
        OffsiteBackupTarget.sort_order, OffsiteBackupTarget.label
    )
    rows = (await db.execute(query)).scalars().all()
    if targets:
        wanted = {name.strip() for name in targets.split(",") if name.strip()}
        rows = [t for t in rows if t.name in wanted]
    return {
        "repository": REPOSITORY,
        "targets": [
            {
                "name": t.name,
                "label": t.label,
                "paths": t.paths,
                "excludes": t.excludes,
                "postgres_container": t.postgres_container,
                "include_system_state": t.include_system_state,
            }
            for t in rows
        ],
    }


@router.post("/internal/runs")
async def internal_start_run(
    payload: OffsiteBackupRunStart,
    x_bridge_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    _check_bridge_token(x_bridge_token)
    target = None
    if payload.target_name != REPOSITORY_RUN_NAME:
        target = (
            await db.execute(select(OffsiteBackupTarget).where(OffsiteBackupTarget.name == payload.target_name))
        ).scalar_one_or_none()
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown backup target")
    now = datetime.now(timezone.utc)
    # The worker holds a host lock, so an older run of the same target still
    # "running" here is one that died without reporting.
    for stale in (
        await db.execute(
            select(OffsiteBackupRun).where(
                OffsiteBackupRun.target_name == payload.target_name, OffsiteBackupRun.status == "running"
            )
        )
    ).scalars():
        stale.status = "interrupted"
        stale.finished_at = now
        stale.error = stale.error or "The worker stopped before reporting this run"
    run = OffsiteBackupRun(
        target_id=target.id if target else None,
        target_name=payload.target_name,
        trigger=payload.trigger,
        status="running",
        started_at=now,
    )
    db.add(run)
    await db.commit()
    return {"run_id": str(run.id)}


@router.post("/internal/runs:finish")
async def internal_finish_run(
    payload: OffsiteBackupRunFinish,
    x_bridge_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    _check_bridge_token(x_bridge_token)
    run = await db.get(OffsiteBackupRun, payload.run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown run")
    now = datetime.now(timezone.utc)
    run.status = payload.status
    run.finished_at = now
    run.snapshot_id = payload.snapshot_id
    run.files_new = payload.files_new
    run.data_added = payload.data_added
    run.total_bytes = payload.total_bytes
    run.error = payload.error
    if payload.status == "failed":
        # Every failure reaches the bell: a backup that silently stopped is
        # exactly how this repository went three weeks without a snapshot.
        label = run.target_name
        if run.target_id:
            target = await db.get(OffsiteBackupTarget, run.target_id)
            label = target.label if target else label
        if run.target_name == REPOSITORY_RUN_NAME:
            label = "repository maintenance"
        db.add(
            Notification(
                source="system",
                severity="error",
                title=f"Off-site backup failed: {label}"[:255],
                message=(payload.error or "No error detail reported")[-2000:],
                event_key=f"offsite-backup:{run.id}",
                occurred_at=now,
            )
        )
    await db.commit()
    return {"status": run.status}
