"""Runs a HostExecution in the background: one host-bridge call per machine
(`POST /v1/servers/exec`), at most MAX_PARALLEL at a time, each result saved
as soon as it lands so the execution screen fills in live.

In-process (single uvicorn worker, like every other loop in main.py). The
running process touches `heartbeat_at` every HEARTBEAT_SECONDS; a restart
mid-run stops the heartbeat, and `recover_interrupted_executions` (startup and
every listing) closes executions whose heartbeat is older than STALE_AFTER as
failed/"interrupted": the command may or may not have finished on the machine,
and the screen must say so rather than spin. Stale-by-heartbeat, not "anything
running at my startup", because dev and production share the database.
"""
import asyncio
import contextlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import func, select, update

from app.core.config import settings
from app.core.secret_masking import mask_secrets
from app.db.base import AsyncSessionLocal
from app.db.models.host_execution import HostExecution, HostExecutionResult
from app.db.models.server import Server

logger = logging.getLogger(__name__)

MAX_PARALLEL = 8
HEARTBEAT_SECONDS = 20
STALE_AFTER = timedelta(seconds=90)
# Kept so the tasks aren't garbage-collected mid-run.
_running: dict[uuid.UUID, asyncio.Task] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def call_bridge_exec(server: Server, shell: str, script: str, timeout_seconds: int) -> dict:
    """One machine. Never raises: a bridge that can't be reached is reported
    as a connection failure on that machine, like an unreachable station."""
    payload = {
        "host": server.ip_address,
        "user": server.remote_user,
        "port": server.ssh_port,
        "key_path": server.ssh_key_path,
        "shell": shell,
        "script": script,
        "timeout_seconds": timeout_seconds,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds + 30) as client:
            resp = await client.post(
                f"{settings.CHAT_BRIDGE_URL}/v1/servers/exec",
                json=payload,
                headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
            )
    except httpx.HTTPError as exc:
        return {"failure": "connection", "stderr": f"Host bridge unreachable: {type(exc).__name__}"}
    if resp.status_code != 200:
        try:
            detail = resp.json().get("detail")
        except ValueError:
            detail = None
        return {"failure": "connection", "stderr": f"Host bridge refused the run: {detail or resp.status_code}"}
    return resp.json()


async def _run_one(result_id: uuid.UUID, shell: str, script: str, timeout: int, secrets: list[str]) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.get(HostExecutionResult, result_id)
        execution = await db.get(HostExecution, result.execution_id)
        if result.status != "pending":
            return
        if execution.status == "cancelled":
            result.status, result.skip_reason = "skipped", "Cancelled before it started"
            await db.commit()
            return
        server = await db.get(Server, result.server_id) if result.server_id else None
        if server is None:
            result.status, result.skip_reason = "skipped", "Machine no longer registered"
            await db.commit()
            return
        result.status, result.started_at = "running", _now()
        await db.commit()

    outcome = await call_bridge_exec(server, shell, script, timeout)

    async with AsyncSessionLocal() as db:
        result = await db.get(HostExecutionResult, result_id)
        failure = outcome.get("failure")
        result.status = "failed" if failure else "succeeded"
        result.failure = failure
        result.exit_code = outcome.get("exit_code")
        result.stdout = mask_secrets(outcome.get("stdout"), secrets)
        result.stderr = mask_secrets(outcome.get("stderr"), secrets)
        result.truncated = bool(outcome.get("truncated"))
        result.duration_ms = outcome.get("duration_ms")
        result.finished_at = _now()
        await db.commit()


async def _run_execution(
    execution_id: uuid.UUID, shell: str, script: str, timeout: int, secrets: list[str]
) -> None:
    try:
        async with AsyncSessionLocal() as db:
            pending = list(
                (
                    await db.execute(
                        select(HostExecutionResult.id).where(
                            HostExecutionResult.execution_id == execution_id,
                            HostExecutionResult.status == "pending",
                        )
                    )
                ).scalars()
            )
        gate = asyncio.Semaphore(MAX_PARALLEL)
        heartbeat = asyncio.create_task(_heartbeat(execution_id))

        async def guarded(result_id: uuid.UUID) -> None:
            async with gate:
                try:
                    await _run_one(result_id, shell, script, timeout, secrets)
                except Exception:
                    logger.exception("host execution %s: result %s crashed", execution_id, result_id)
                    async with AsyncSessionLocal() as db:
                        await db.execute(
                            update(HostExecutionResult)
                            .where(
                                HostExecutionResult.id == result_id,
                                HostExecutionResult.status.in_(("pending", "running")),
                            )
                            .values(status="failed", failure="interrupted", finished_at=_now())
                        )
                        await db.commit()

        try:
            await asyncio.gather(*(guarded(rid) for rid in pending))
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat
    finally:
        async with AsyncSessionLocal() as db:
            execution = await db.get(HostExecution, execution_id)
            if execution is not None:
                if execution.status == "running":
                    execution.status = "completed"
                execution.finished_at = _now()
                await db.commit()
        _running.pop(execution_id, None)


async def _heartbeat(execution_id: uuid.UUID) -> None:
    while True:
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(HostExecution).where(HostExecution.id == execution_id).values(heartbeat_at=_now())
                )
                await db.commit()
        except Exception:
            logger.exception("host execution %s: heartbeat failed", execution_id)
        await asyncio.sleep(HEARTBEAT_SECONDS)


def start_execution(
    execution_id: uuid.UUID, shell: str, script: str, timeout: int, secrets: list[str] | None = None
) -> asyncio.Task:
    task = asyncio.create_task(
        _run_execution(execution_id, shell, script, timeout, list(secrets or [])),
        name=f"host-execution-{execution_id}",
    )
    _running[execution_id] = task
    return task


async def recover_interrupted_executions() -> int:
    """Closes executions whose runner stopped beating (a restart, a crash).
    Returns how many machine results it closed."""
    cutoff = _now() - STALE_AFTER
    stale = (
        (HostExecution.status == "running")
        & (func.coalesce(HostExecution.heartbeat_at, HostExecution.started_at) < cutoff)
        & HostExecution.id.not_in(list(_running))
    )
    async with AsyncSessionLocal() as db:
        open_ids = select(HostExecution.id).where(stale)
        closed = await db.execute(
            update(HostExecutionResult)
            .where(
                HostExecutionResult.execution_id.in_(open_ids),
                HostExecutionResult.status.in_(("pending", "running")),
            )
            .values(
                status="failed",
                failure="interrupted",
                stderr="ForgeHub restarted during the run; the command may or may not have finished.",
                finished_at=_now(),
            )
        )
        await db.execute(
            update(HostExecution).where(stale).values(status="completed", finished_at=_now())
        )
        await db.commit()
        return closed.rowcount or 0
