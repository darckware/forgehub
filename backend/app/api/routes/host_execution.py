"""Command executions on machines – Remote Access phase 4
(docs/architecture/REMOTE_MAINTENANCE_PLAN.md). Admin-only: this runs
arbitrary commands as the machine's login.

Endpoints:
  POST /api/v1/host-executions                 – run a command on machines/groups
  GET  /api/v1/host-executions                 – recent executions with counts
  GET  /api/v1/host-executions/{id}            – one execution, result per machine
  POST /api/v1/host-executions/{id}:follow-up  – run another command on the
                                                 machines that failed
  POST /api/v1/host-executions/{id}:cancel     – machines not started yet are skipped

Machines are checked before anything runs; one that can't take the command is
recorded as "skipped" with the reason, never silently dropped: parked in
ForgeHub, no login yet, OS incompatible with the shell, or already running
another command (one execution per machine at a time).
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.host_execution import (
    MAX_TARGETS,
    HostExecutionCounts,
    HostExecutionCreate,
    HostExecutionDetail,
    HostExecutionFollowUp,
    HostExecutionResultOut,
    HostExecutionSummary,
)
from app.core import host_exec_runner
from app.core.deps import get_current_admin
from app.core.secret_masking import mask_secrets
from app.db.base import get_db
from app.db.models.governance import AuditEvent
from app.db.models.host_execution import HostExecution, HostExecutionResult
from app.db.models.server import HostGroup, HostGroupMember, Server
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/host-executions", tags=["remote-access"])

ACTIVE_RESULT_STATUSES = ("pending", "running")


async def busy_server_ids(db: AsyncSession) -> set[uuid.UUID]:
    """Machines with a command queued or running right now. Shared with the
    readiness endpoint, which reports them as "busy"."""
    rows = await db.execute(
        select(HostExecutionResult.server_id).where(
            # Not filtered by the execution's status: a cancelled execution can
            # still have one machine finishing its command.
            HostExecutionResult.status.in_(ACTIVE_RESULT_STATUSES),
            HostExecutionResult.server_id.is_not(None),
        )
    )
    return set(rows.scalars())


def skip_reason(server: Server, shell: str, busy: set[uuid.UUID]) -> str | None:
    if not server.access_enabled:
        return "Access is turned off in ForgeHub"
    if not server.remote_user:
        return "No login set for this machine yet"
    if shell == "powershell" and server.os_family != "windows":
        return "PowerShell runs only on Windows machines"
    if shell == "sh" and server.os_family == "windows":
        return "sh does not run on Windows machines"
    if server.id in busy:
        return "Already running another command"
    return None


def _counts_and_verdict(statuses: list[str]) -> tuple[HostExecutionCounts, str]:
    counts = HostExecutionCounts(total=len(statuses))
    for s in statuses:
        setattr(counts, s, getattr(counts, s) + 1)
    if counts.pending or counts.running:
        verdict = "running"
    elif counts.failed:
        verdict = "failed"
    elif counts.succeeded:
        verdict = "succeeded"
    else:
        verdict = "nothing_ran"
    return counts, verdict


async def _summaries(db: AsyncSession, executions: list[HostExecution]) -> list[HostExecutionSummary]:
    ids = [e.id for e in executions]
    statuses: dict[uuid.UUID, list[str]] = {i: [] for i in ids}
    if ids:
        rows = await db.execute(
            select(HostExecutionResult.execution_id, HostExecutionResult.status).where(
                HostExecutionResult.execution_id.in_(ids)
            )
        )
        for execution_id, result_status in rows.all():
            statuses[execution_id].append(result_status)
    out = []
    for execution in executions:
        summary = HostExecutionSummary.model_validate(execution)
        summary.counts, summary.verdict = _counts_and_verdict(statuses[execution.id])
        out.append(summary)
    return out


async def _detail(db: AsyncSession, execution: HostExecution) -> HostExecutionDetail:
    results = list(
        (
            await db.execute(
                select(HostExecutionResult)
                .where(HostExecutionResult.execution_id == execution.id)
                .order_by(HostExecutionResult.server_name)
            )
        ).scalars()
    )
    follow_ups = list(
        (
            await db.execute(
                select(HostExecution.id)
                .where(HostExecution.parent_execution_id == execution.id)
                .order_by(HostExecution.started_at)
            )
        ).scalars()
    )
    detail = HostExecutionDetail.model_validate(execution)
    detail.results = [HostExecutionResultOut.model_validate(r) for r in results]
    detail.counts, detail.verdict = _counts_and_verdict([r.status for r in results])
    detail.follow_up_ids = follow_ups
    return detail


async def launch_execution(
    db: AsyncSession,
    *,
    servers: list[Server],
    command: str,
    shell: str,
    timeout_seconds: int,
    actor: str,
    target_summary: str,
    parent_execution_id: uuid.UUID | None = None,
    secrets: list[str] | None = None,
) -> HostExecution:
    """Creates the execution + one result per machine (skipped ones already
    closed with their reason), audits it and starts the background run.
    Phase 3's preparation/rotation will call this with `secrets` so the
    passwords it generates are masked everywhere."""
    busy = await busy_server_ids(db)
    now = datetime.now(timezone.utc)
    masked = mask_secrets(command, secrets or []) or ""
    execution = HostExecution(
        parent_execution_id=parent_execution_id,
        shell=shell,
        command=masked,
        timeout_seconds=timeout_seconds,
        status="running",
        requested_by=actor,
        target_summary=target_summary[:500],
        started_at=now,
    )
    db.add(execution)
    await db.flush()
    for server in servers:
        reason = skip_reason(server, shell, busy)
        db.add(
            HostExecutionResult(
                execution_id=execution.id,
                server_id=server.id,
                server_name=server.name,
                status="skipped" if reason else "pending",
                skip_reason=reason,
                finished_at=now if reason else None,
            )
        )
    db.add(
        AuditEvent(
            entity_type="host_execution",
            entity_id=execution.id,
            event_type="started",
            actor=actor,
            payload={
                "shell": shell,
                "command": masked,
                "machines": [str(s.id) for s in servers],
                "parent_execution_id": str(parent_execution_id) if parent_execution_id else None,
            },
        )
    )
    await db.commit()
    await db.refresh(execution)
    host_exec_runner.start_execution(execution.id, shell, command, timeout_seconds, secrets)
    return execution


@router.post("", response_model=HostExecutionDetail, status_code=status.HTTP_201_CREATED)
async def create_execution(
    payload: HostExecutionCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    wanted = set(payload.server_ids)
    group_names: list[str] = []
    if payload.group_ids:
        groups = list((await db.execute(select(HostGroup).where(HostGroup.id.in_(payload.group_ids)))).scalars())
        if len(groups) != len(set(payload.group_ids)):
            raise HTTPException(status_code=422, detail="Unknown group")
        group_names = [g.name for g in groups]
        members = await db.execute(
            select(HostGroupMember.server_id).where(HostGroupMember.group_id.in_(payload.group_ids))
        )
        wanted |= set(members.scalars())
    if not wanted:
        raise HTTPException(status_code=422, detail="Pick at least one machine or a group with machines")
    if len(wanted) > MAX_TARGETS:
        raise HTTPException(status_code=422, detail=f"At most {MAX_TARGETS} machines per execution")
    servers = list((await db.execute(select(Server).where(Server.id.in_(wanted)).order_by(Server.name))).scalars())
    if len(servers) != len(wanted):
        raise HTTPException(status_code=422, detail="Unknown machine")

    loose = len(payload.server_ids)
    parts = [*group_names]
    if loose:
        parts.append(servers[0].name if len(servers) == 1 else f"{loose} machine(s)")
    execution = await launch_execution(
        db,
        servers=servers,
        command=payload.command,
        shell=payload.shell,
        timeout_seconds=payload.timeout_seconds,
        actor=admin.username,
        target_summary=" + ".join(parts),
    )
    return await _detail(db, execution)


@router.get("", response_model=list[HostExecutionSummary])
async def list_executions(
    limit: int = Query(default=30, ge=1, le=200),
    server_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    await host_exec_runner.recover_interrupted_executions()
    query = select(HostExecution).order_by(HostExecution.started_at.desc()).limit(limit)
    if server_id is not None:
        query = query.where(
            HostExecution.id.in_(
                select(HostExecutionResult.execution_id).where(HostExecutionResult.server_id == server_id)
            )
        )
    executions = list((await db.execute(query)).scalars())
    return await _summaries(db, executions)


@router.get("/{execution_id}", response_model=HostExecutionDetail)
async def get_execution(
    execution_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    execution = await db.get(HostExecution, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return await _detail(db, execution)


@router.post("/{execution_id}:follow-up", response_model=HostExecutionDetail, status_code=status.HTTP_201_CREATED)
async def follow_up_execution(
    execution_id: uuid.UUID,
    payload: HostExecutionFollowUp,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    parent = await db.get(HostExecution, execution_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Execution not found")
    failed_ids = set(
        (
            await db.execute(
                select(HostExecutionResult.server_id).where(
                    HostExecutionResult.execution_id == execution_id,
                    HostExecutionResult.status == "failed",
                    HostExecutionResult.server_id.is_not(None),
                )
            )
        ).scalars()
    )
    if not failed_ids:
        raise HTTPException(status_code=409, detail="No machine failed in this execution")
    servers = list((await db.execute(select(Server).where(Server.id.in_(failed_ids)).order_by(Server.name))).scalars())
    execution = await launch_execution(
        db,
        servers=servers,
        command=payload.command,
        shell=payload.shell,
        timeout_seconds=payload.timeout_seconds,
        actor=admin.username,
        target_summary=f"{len(servers)} failed machine(s) of {parent.target_summary or 'previous run'}",
        parent_execution_id=parent.id,
    )
    return await _detail(db, execution)


@router.post("/{execution_id}:cancel", response_model=HostExecutionDetail)
async def cancel_execution(
    execution_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Machines that haven't started are skipped; one already running is left
    to finish (or time out) -- killing a half-applied change midway is worse
    than letting it end and reporting what it did."""
    execution = await db.get(HostExecution, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    if execution.status != "running":
        raise HTTPException(status_code=409, detail="Execution is not running")
    execution.status = "cancelled"
    now = datetime.now(timezone.utc)
    pending = await db.execute(
        select(HostExecutionResult).where(
            HostExecutionResult.execution_id == execution_id, HostExecutionResult.status == "pending"
        )
    )
    for result in pending.scalars():
        result.status, result.skip_reason, result.finished_at = "skipped", "Cancelled before it started", now
    db.add(
        AuditEvent(
            entity_type="host_execution", entity_id=execution.id, event_type="cancelled",
            actor=admin.username, payload=None,
        )
    )
    await db.commit()
    await db.refresh(execution)
    return await _detail(db, execution)

