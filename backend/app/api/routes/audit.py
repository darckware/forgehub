"""Audit domain routes: ecosystem checkpoints and their executions.

The checklist (audit_checks) is fully editable from the Auditor page;
POST /run executes every enabled check by shipping its command to the
host through the chat bridge's /v1/exec (exit 0 = ok) and recording an
audit_check_runs row per check. /run-internal is the same trigger for
the `hermes cron` job (forgehub-audit-checklist in the athos store) --
it bypasses user auth but requires the shared bridge token, the same
trust boundary the bridge itself uses.
"""
import asyncio
import shlex
import time
import uuid

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.audit import (
    AuditCheckCreate,
    AuditCheckOut,
    AuditCheckUpdate,
    AuditRunAllOut,
    AuditRunOut,
    AuditRemediationOut,
    AuditStatusOut,
)
from app.core.config import settings
from app.core.deps import get_current_admin
from app.db.base import get_db
from app.db.models.audit import AuditCheck, AuditCheckRun

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])

_OUTPUT_LIMIT = 10_000
# The bridge /v1/exec hard-kills at 60s; leave headroom for transport.
_MAX_TIMEOUT = 55


async def _execute_command(
    check: AuditCheck, command: str, requested_by: str
) -> AuditCheckRun:
    """Run one check on the host via the bridge and build (not persist)
    its AuditCheckRun. `timeout(1)` wraps the command so a hung check
    yields exit 124 -> "timeout" instead of tripping the bridge's cap."""
    seconds = min(check.timeout_seconds or _MAX_TIMEOUT, _MAX_TIMEOUT)
    wrapped = f"timeout {seconds} bash -c {shlex.quote(command)}"
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=_MAX_TIMEOUT + 15) as client:
            resp = await client.post(
                f"{settings.CHAT_BRIDGE_URL}/v1/exec",
                json={"command": wrapped, "cwd": check.workdir},
                headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
            )
        resp.raise_for_status()
        data = resp.json()
        exit_code = data.get("exit_code")
        output = ((data.get("stdout") or "") + (data.get("stderr") or ""))[:_OUTPUT_LIMIT]
        if exit_code == 0:
            run_status = "ok"
        elif exit_code == 124:
            run_status = "timeout"
        else:
            run_status = "fail"
    except (httpx.HTTPError, ValueError) as exc:
        exit_code = None
        output = f"bridge error: {exc}"[:_OUTPUT_LIMIT]
        run_status = "error"
    return AuditCheckRun(
        check_id=check.id,
        status=run_status,
        exit_code=exit_code,
        output=output or None,
        duration_ms=round((time.monotonic() - started) * 1000),
        requested_by=requested_by,
    )


async def _execute_check(check: AuditCheck, requested_by: str) -> AuditCheckRun:
    return await _execute_command(check, check.command, requested_by)


async def _run_enabled_checks(db: AsyncSession, requested_by: str) -> list[AuditCheckRun]:
    result = await db.execute(
        select(AuditCheck).where(AuditCheck.enabled == True).order_by(AuditCheck.name)  # noqa: E712
    )
    checks = list(result.scalars().all())
    # Bounded concurrency: the bridge runs each command in a thread.
    sem = asyncio.Semaphore(4)

    async def _one(check: AuditCheck) -> AuditCheckRun:
        async with sem:
            return await _execute_check(check, requested_by)

    runs = await asyncio.gather(*(_one(c) for c in checks))
    for run in runs:
        db.add(run)
    await db.commit()
    for run in runs:
        await db.refresh(run)
    return list(runs)


async def _get_check_or_404(db: AsyncSession, check_id: uuid.UUID) -> AuditCheck:
    check = (
        await db.execute(select(AuditCheck).where(AuditCheck.id == check_id))
    ).scalar_one_or_none()
    if check is None:
        raise HTTPException(status_code=404, detail="Audit check not found")
    return check


async def _latest_runs_by_check(db: AsyncSession) -> dict[uuid.UUID, AuditCheckRun]:
    """Newest run per check (Postgres DISTINCT ON)."""
    result = await db.execute(
        select(AuditCheckRun)
        .distinct(AuditCheckRun.check_id)
        .order_by(AuditCheckRun.check_id, AuditCheckRun.created_at.desc())
    )
    return {run.check_id: run for run in result.scalars().all()}


def _check_out(check: AuditCheck, last_run: AuditCheckRun | None) -> AuditCheckOut:
    out = AuditCheckOut.model_validate(check)
    out.last_run = AuditRunOut.model_validate(last_run) if last_run else None
    return out


@router.get("/checks", response_model=list[AuditCheckOut])
async def list_checks(db: AsyncSession = Depends(get_db)) -> list[AuditCheckOut]:
    """Full checklist with each check's latest run embedded."""
    result = await db.execute(select(AuditCheck).order_by(AuditCheck.name))
    latest = await _latest_runs_by_check(db)
    return [_check_out(c, latest.get(c.id)) for c in result.scalars().all()]


@router.post("/checks", response_model=AuditCheckOut, status_code=status.HTTP_201_CREATED)
async def create_check(
    payload: AuditCheckCreate, db: AsyncSession = Depends(get_db)
) -> AuditCheckOut:
    check = AuditCheck(**payload.model_dump())
    db.add(check)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An audit check with this name already exists",
        ) from None
    await db.refresh(check)
    return _check_out(check, None)


@router.patch("/checks/{check_id}", response_model=AuditCheckOut)
async def update_check(
    check_id: uuid.UUID, payload: AuditCheckUpdate, db: AsyncSession = Depends(get_db)
) -> AuditCheckOut:
    check = await _get_check_or_404(db, check_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(check, field, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An audit check with this name already exists",
        ) from None
    await db.refresh(check)
    latest = await _latest_runs_by_check(db)
    return _check_out(check, latest.get(check.id))


@router.delete("/checks/{check_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_check(check_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    check = await _get_check_or_404(db, check_id)
    await db.delete(check)
    await db.commit()


@router.post("/checks/{check_id}/run", response_model=AuditRunOut)
async def run_check(check_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> AuditRunOut:
    """Execute a single check now and record its run."""
    check = await _get_check_or_404(db, check_id)
    run = await _execute_check(check, "manual")
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return AuditRunOut.model_validate(run)


@router.post("/checks/{check_id}/remediate", response_model=AuditRemediationOut)
async def remediate_check(
    check_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> AuditRemediationOut:
    """Apply an explicitly configured repair, then always verify the check.

    Repairs are deliberately separate from normal/manual/cron runs and require
    an administrator. Both command results are persisted for accountability.
    """
    check = await _get_check_or_404(db, check_id)
    if not check.remediation_command:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This audit check has no automatic remediation configured",
        )
    repair = await _execute_command(check, check.remediation_command, "remediation")
    db.add(repair)
    await db.flush()
    verification = await _execute_check(check, "remediation-verification")
    db.add(verification)
    await db.commit()
    await db.refresh(repair)
    await db.refresh(verification)
    return AuditRemediationOut(
        remediation_run=AuditRunOut.model_validate(repair),
        verification_run=AuditRunOut.model_validate(verification),
    )


@router.post("/run", response_model=AuditRunAllOut)
async def run_all(db: AsyncSession = Depends(get_db)) -> AuditRunAllOut:
    """Execute every enabled check ("solicitar checagem"): dispatches all
    of them (bounded concurrency) and records one run per check."""
    runs = await _run_enabled_checks(db, "manual")
    return AuditRunAllOut(runs=[AuditRunOut.model_validate(r) for r in runs])


@router.post("/run-internal", response_model=AuditRunAllOut)
async def run_internal(
    x_bridge_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> AuditRunAllOut:
    """Cron trigger (see module docstring): listed in main.py's
    _PUBLIC_API_PATHS, so it must validate the shared bridge token itself."""
    if not settings.CHAT_BRIDGE_TOKEN or x_bridge_token != settings.CHAT_BRIDGE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid bridge token")
    runs = await _run_enabled_checks(db, "cron")
    return AuditRunAllOut(runs=[AuditRunOut.model_validate(r) for r in runs])


@router.get("/runs", response_model=list[AuditRunOut])
async def list_runs(
    check_id: uuid.UUID | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[AuditRunOut]:
    query = select(AuditCheckRun).order_by(AuditCheckRun.created_at.desc()).limit(min(limit, 200))
    if check_id is not None:
        query = query.where(AuditCheckRun.check_id == check_id)
    result = await db.execute(query)
    return [AuditRunOut.model_validate(r) for r in result.scalars().all()]


@router.get("/status", response_model=AuditStatusOut)
async def audit_status(db: AsyncSession = Depends(get_db)) -> AuditStatusOut:
    """Summary for the Auditor header and any future dashboard card."""
    checks = (await db.execute(select(AuditCheck))).scalars().all()
    latest = await _latest_runs_by_check(db)
    enabled = [c for c in checks if c.enabled]
    ok = sum(1 for c in enabled if latest.get(c.id) and latest[c.id].status == "ok")
    fail = sum(1 for c in enabled if latest.get(c.id) and latest[c.id].status != "ok")
    never = sum(1 for c in enabled if c.id not in latest)
    last_at = (
        await db.execute(select(func.max(AuditCheckRun.created_at)))
    ).scalar_one_or_none()
    return AuditStatusOut(
        total=len(checks),
        enabled=len(enabled),
        ok=ok,
        fail=fail,
        never_ran=never,
        last_run_at=last_at,
    )
