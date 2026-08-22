"""Automatic verification of TaskExecution.evidence_ref against reality --
the piece that was missing from the incident this module exists to prevent
(2026-08-17): an agent narrated concrete progress (a file "initialized", a
project "registered") that never actually happened, and `dispatch_status=
"completed"` was accepted at face value with zero cross-check. See plan
`resilient-twirling-blossom` for the full incident writeup.

`_finalize_dispatch` (api/routes/demand.py) already stops short of ever
writing "completed"/"verified" directly -- a clean process exit becomes
`TaskExecution.status="reported"`, which only means "the agent said it's
done," not that it's true. This module is what promotes "reported" to
"verified" (evidence checked out) or demotes it to "failed" (evidence
missing or checked out false), same two-outcome shape as task_health.py's
health states. Same polling pattern as that module: `run_evidence_
verification_pass` is polled by main.py's own loop, not called inline from
the dispatch path, so a slow/failing filesystem or git check never blocks a
request.

Evidence prefixes (see the convention _dispatch_task_by_id's dispatch body
teaches the recipient agent):
- `file:<relpath>` -- resolved against the task's Project.working_directory_
  path; must exist and have mtime >= the execution's started_at. This is
  the exact check that would have caught the incident (the cited file's
  timestamp predated the message that claimed to have created it).
- `git:<sha>` -- resolved the same way, via `git cat-file -e` + commit date.
- `db:<entity_type>:<uuid>` -- confirms the referenced row actually exists
  (closes "I registered project X" when no such project was ever created).
"""
import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.governed_approval import request_task_approval
from app.db.models.backlog import PlanningItem
from app.db.models.governance import AuditEvent
from app.db.models.notification import Notification
from app.db.models.product import Product
from app.db.models.project import ChangeRequest, Project
from app.db.models.task import ProjectTask, TaskExecution

logger = logging.getLogger(__name__)

# Entity types a db:<type>:<uuid> evidence ref may name, mapped to the model
# that owns that table. Deliberately a small allowlist rather than a generic
# "query any table by name" -- an evidence ref is untrusted input written by
# whichever agent executed the task.
DB_EVIDENCE_ENTITIES: dict[str, type] = {
    "project_task": ProjectTask,
    "project": Project,
    "product": Product,
    "planning_item": PlanningItem,
    "change_request": ChangeRequest,
}


async def _resolve_execution_project(db: AsyncSession, execution: TaskExecution) -> Project | None:
    """Best-effort, never raises -- a poll pass skips what it can't resolve
    instead of failing the whole batch over one orphaned task."""
    task = await db.get(ProjectTask, execution.task_id)
    if task is None:
        return None
    if task.planning_item_id:
        planning_item = await db.get(PlanningItem, task.planning_item_id)
        if planning_item and planning_item.project_id:
            return await db.get(Project, planning_item.project_id)
    if task.change_request_id:
        change_request = await db.get(ChangeRequest, task.change_request_id)
        if change_request:
            return await db.get(Project, change_request.project_id)
    return None


async def _check_file_evidence(db: AsyncSession, execution: TaskExecution, relpath: str) -> tuple[bool, str]:
    project = await _resolve_execution_project(db, execution)
    if project is None or not project.working_directory_path:
        return False, "no project working_directory_path to resolve the file against"
    # Reject absolute paths / traversal outside the project root -- evidence_ref
    # is agent-supplied text, not a trusted path.
    if os.path.isabs(relpath) or ".." in relpath.split("/"):
        return False, "file evidence must be a relative path inside the project"
    full_path = os.path.join(project.working_directory_path, relpath)
    if not os.path.isfile(full_path):
        return False, f"file does not exist: {full_path}"
    mtime = datetime.fromtimestamp(os.path.getmtime(full_path), tz=timezone.utc)
    if execution.started_at and mtime < execution.started_at:
        return False, (
            f"file mtime ({mtime.isoformat()}) predates the execution's start "
            f"({execution.started_at.isoformat()}) -- this is the exact signature "
            "of a narrated-but-not-executed claim"
        )
    return True, "file exists with mtime after execution start"


async def _check_git_evidence(db: AsyncSession, execution: TaskExecution, sha: str) -> tuple[bool, str]:
    project = await _resolve_execution_project(db, execution)
    if project is None or not project.working_directory_path:
        return False, "no project working_directory_path to resolve the repo against"
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", project.working_directory_path, "cat-file", "-e", sha,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    if await proc.wait() != 0:
        return False, f"commit {sha} not found in {project.working_directory_path}"
    log_proc = await asyncio.create_subprocess_exec(
        "git", "-C", project.working_directory_path, "log", "-1", "--format=%cI", sha,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await log_proc.communicate()
    try:
        commit_at = datetime.fromisoformat(stdout.decode().strip())
    except ValueError:
        return True, f"commit {sha} exists (commit date unparsable, skipped timing check)"
    if execution.started_at and commit_at < execution.started_at:
        return False, (
            f"commit date ({commit_at.isoformat()}) predates the execution's start "
            f"({execution.started_at.isoformat()})"
        )
    return True, f"commit {sha} exists with date after execution start"


async def _check_db_evidence(db: AsyncSession, entity_type: str, entity_id: str) -> tuple[bool, str]:
    model = DB_EVIDENCE_ENTITIES.get(entity_type)
    if model is None:
        return False, f"unknown db evidence entity_type {entity_type!r}"
    try:
        entity_uuid = uuid.UUID(entity_id)
    except ValueError:
        return False, f"evidence_ref db id is not a valid uuid: {entity_id!r}"
    row = await db.get(model, entity_uuid)
    if row is None:
        return False, f"no {entity_type} row with id {entity_id} -- the claimed entity does not exist"
    return True, f"{entity_type} {entity_id} exists"


async def verify_evidence(db: AsyncSession, execution: TaskExecution) -> tuple[bool | None, str]:
    """Returns (True, reason) verified, (False, reason) failed, or
    (None, reason) when the ref is absent/unparseable -- stays in "reported"
    for manual verification rather than being silently treated as either
    outcome."""
    ref = (execution.evidence_ref or "").strip()
    if not ref:
        return None, "no evidence_ref declared"
    if ":" not in ref:
        return None, f"evidence_ref has no recognized prefix: {ref!r}"
    prefix, _, rest = ref.partition(":")
    if prefix == "file":
        ok, reason = await _check_file_evidence(db, execution, rest)
        return ok, reason
    if prefix == "git":
        ok, reason = await _check_git_evidence(db, execution, rest)
        return ok, reason
    if prefix == "db":
        entity_type, _, entity_id = rest.partition(":")
        ok, reason = await _check_db_evidence(db, entity_type, entity_id)
        return ok, reason
    return None, f"evidence_ref has an unrecognized prefix: {prefix!r}"


async def run_evidence_verification_pass(db: AsyncSession) -> None:
    """Polled by main.py's `_evidence_verification_poll_loop`. Scans every
    TaskExecution sitting in "reported" and resolves it to "verified" or
    "failed" -- see verify_evidence for the three outcomes. A ref that's
    absent or unparseable is left as-is (manual verification queue, not
    auto-failed -- an agent that forgot the EVIDENCE line shouldn't be
    treated the same as one whose evidence was checked and found false)."""
    result = await db.execute(select(TaskExecution).where(TaskExecution.status == "reported"))
    executions = list(result.scalars().all())
    for execution in executions:
        try:
            ok, reason = await verify_evidence(db, execution)
        except Exception:
            logger.exception("Evidence verification crashed for execution %s", execution.id)
            continue
        if ok is None:
            continue
        if ok:
            execution.status = "verified"
            db.add(
                AuditEvent(
                    entity_type="task_execution",
                    entity_id=execution.id,
                    event_type="execution_auto_verified",
                    actor="system",
                    payload={"evidence_ref": execution.evidence_ref, "reason": reason},
                )
            )
            # Layered task-execution governance, Fase 3: opens the review
            # gate if (and only if) a project_task approval policy is
            # active -- see request_task_approval's own docstring for why
            # this is a silent no-op otherwise.
            task = await db.get(ProjectTask, execution.task_id)
            if task is not None:
                await request_task_approval(db, task, execution)
        else:
            execution.status = "failed"
            db.add(
                Notification(
                    source="system",
                    severity="error",
                    title="Evidence verification failed",
                    message=f"Task execution {execution.id} (attempt {execution.attempt_number}): {reason}",
                    event_key=f"execution-evidence-failed:{execution.id}",
                    occurred_at=datetime.now(timezone.utc),
                )
            )
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Failed to commit evidence verification for execution %s", execution.id)
