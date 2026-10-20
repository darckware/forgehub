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
from collections.abc import Awaitable, Callable
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
# Scheduled runs: an unreachable machine is retried this often until the
# execution's retry_until, then reads "not run" (decision: closed window =
# not executed).
RETRY_INTERVAL_SECONDS = 60
HEARTBEAT_SECONDS = 20
STALE_AFTER = timedelta(seconds=90)
# Called after a machine's run succeeded: (server_id, outcome). Used by system
# scripts to record what they changed (RustDesk ID/password).
OnSuccess = Callable[[uuid.UUID, dict], Awaitable[None]]
# Replaces the single bridge call for a machine with a custom sequence (e.g.
# preparation: run as the client's admin, verify the new login, then lock the
# admin). Returns the same outcome dict as call_bridge_exec.
Executor = Callable[[Server], Awaitable[dict]]

CANARY_SKIP_REASON = "Canary failed on the first machine; the others were not run"

# Kept so the tasks aren't garbage-collected mid-run.
_running: dict[uuid.UUID, asyncio.Task] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def call_bridge_exec(server: Server, shell: str, script: str, timeout_seconds: int) -> dict:
    return await call_bridge_exec_as(
        host=server.ip_address, user=server.remote_user, port=server.ssh_port,
        key_path=server.ssh_key_path, key_ref=server.ssh_key_ref, password=None,
        shell=shell, script=script, timeout_seconds=timeout_seconds,
    )


async def call_bridge_exec_as(
    *, host: str, user: str, port: int, key_path: str | None, password: str | None,
    shell: str, script: str, timeout_seconds: int, key_ref: str | None = None,
) -> dict:
    """One machine. Never raises: a bridge that can't be reached is reported
    as a connection failure on that machine, like an unreachable station."""
    payload = {
        "host": host,
        "user": user,
        "port": port,
        # A key kept in ForgeVault wins over the file path (the bridge loads it
        # into a per-run agent).
        "key_path": None if key_ref else key_path,
        "key_ref": key_ref,
        "password": password,
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


async def _run_one(
    result_id: uuid.UUID, shell: str, script: str, timeout: int, secrets: list[str],
    retry_until: datetime | None = None,
    on_success: OnSuccess | None = None,
    executor: Executor | None = None,
) -> None:
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

    outcome = await executor(server) if executor else await call_bridge_exec(server, shell, script, timeout)
    while outcome.get("failure") == "connection" and retry_until and _now() < retry_until:
        async with AsyncSessionLocal() as db:
            execution = await db.get(HostExecution, result.execution_id)
            if execution is None or execution.status == "cancelled":
                break
        await asyncio.sleep(RETRY_INTERVAL_SECONDS)
        outcome = await call_bridge_exec(server, shell, script, timeout)

    async with AsyncSessionLocal() as db:
        result = await db.get(HostExecutionResult, result_id)
        failure = outcome.get("failure")
        if failure == "connection" and retry_until:
            result.status, result.failure = "skipped", None
            result.skip_reason = "Unreachable until the scheduled window closed"
            result.stderr = mask_secrets(outcome.get("stderr"), secrets)
            result.finished_at = _now()
            await db.commit()
            return
        result.status = "failed" if failure else "succeeded"
        result.failure = failure
        result.exit_code = outcome.get("exit_code")
        result.stdout = mask_secrets(outcome.get("stdout"), secrets)
        result.stderr = mask_secrets(outcome.get("stderr"), secrets)
        result.truncated = bool(outcome.get("truncated"))
        result.duration_ms = outcome.get("duration_ms")
        result.finished_at = _now()
        await db.commit()
    if not failure and on_success is not None and server is not None:
        try:
            await on_success(server.id, outcome)
        except Exception:
            logger.exception("host execution: on_success hook failed for %s", server.id)


async def _run_execution(
    execution_id: uuid.UUID, shell: str, script: str, timeout: int, secrets: list[str],
    retry_until: datetime | None = None,
    on_success: OnSuccess | None = None,
    executor: Executor | None = None,
    canary: bool = False,
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
                    await _run_one(result_id, shell, script, timeout, secrets, retry_until, on_success, executor)
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
            if canary and len(pending) > 1:
                # Canary: one machine first; the rest only if it succeeded.
                first, rest = pending[0], pending[1:]
                await guarded(first)
                async with AsyncSessionLocal() as db:
                    went_well = (await db.get(HostExecutionResult, first)).status == "succeeded"
                    if not went_well:
                        await db.execute(
                            update(HostExecutionResult)
                            .where(HostExecutionResult.id.in_(rest), HostExecutionResult.status == "pending")
                            .values(status="skipped", skip_reason=CANARY_SKIP_REASON, finished_at=_now())
                        )
                        await db.commit()
                if went_well:
                    await asyncio.gather(*(guarded(rid) for rid in rest))
            else:
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
    execution_id: uuid.UUID, shell: str, script: str, timeout: int, secrets: list[str] | None = None,
    retry_until: datetime | None = None,
    on_success: OnSuccess | None = None,
    executor: Executor | None = None,
    canary: bool = False,
) -> asyncio.Task:
    task = asyncio.create_task(
        _run_execution(execution_id, shell, script, timeout, list(secrets or []), retry_until, on_success, executor, canary),
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
