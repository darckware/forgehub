"""Notifications routes — persistent, DB-backed notification record.

Provides:
- GET  /api/v1/notifications            list (newest first) + unread count;
                                        ingests the current cron run outcomes
                                        from the live jobs.json stores first,
                                        so listing is always up to date without
                                        a separate sync step
- POST /api/v1/notifications/mark-read  mark specific ids (or all) as read
- POST /api/v1/notifications/cleanup    delete all, or keep the last N days
                                        (UI offers 15/30)

Ingestion maps every cron to its notifications: each distinct run
(job_id + last_run_at) becomes exactly one row, deduped by `event_key`, so
the history accumulates across runs even though jobs.json only holds the
latest run per job. Failures ingest as severity 'error' (with last_error as
the message), successful runs as 'success'. Each row also carries a
`summary` of what the run did, extracted from the scheduler's per-run
output file (output/<job_id>/<timestamp>.md — the '## Response' or
'## Script Error' section) when one matches the run time.
"""
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.cron_scripts import HERMES_CRON_DIR, PROFILES_DIR, _load_all_cron_jobs
from app.api.schemas.notification import (
    CleanupIn,
    CleanupOut,
    MarkReadIn,
    MarkReadOut,
    NotificationListOut,
    NotificationOut,
)
from app.db.base import get_db
from app.db.models.notification import NOTIFICATION_SEVERITIES, Notification

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


def _parse_run_at(raw: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


SUMMARY_MAX_CHARS = 2000
# Output filenames encode the run's local wall-clock time; accept a match
# within this window of the job's last_run_at (observed skew is ~1-2s)
_OUTPUT_MATCH_TOLERANCE = timedelta(minutes=10)

# "2026-07-02_12-08-22.md" (per-job dirs) / "<job_id>_20260702_120822.txt" (legacy flat)
_MD_TS_FORMAT = "%Y-%m-%d_%H-%M-%S"
_TXT_TS_FORMAT = "%Y%m%d_%H%M%S"


def _candidate_output_files(job_id: str, profile: str | None) -> list[tuple[datetime, Path]]:
    """All output files for a job, as (naive local run time, path) pairs."""
    out: list[tuple[datetime, Path]] = []

    def _add_dir(d: Path) -> None:
        if not d.is_dir():
            return
        for f in d.iterdir():
            try:
                out.append((datetime.strptime(f.stem, _MD_TS_FORMAT), f))
            except ValueError:
                continue

    _add_dir(HERMES_CRON_DIR / "output" / job_id)
    if profile:
        profile_out = PROFILES_DIR / profile / "cron" / "output"
        _add_dir(profile_out / job_id)
        if profile_out.is_dir():
            for f in profile_out.glob(f"{job_id}_*.txt"):
                try:
                    out.append(
                        (datetime.strptime(f.stem[len(job_id) + 1:], _TXT_TS_FORMAT), f)
                    )
                except ValueError:
                    continue
    return out


def _extract_summary(text: str) -> str | None:
    """Digest of what the run did. For .md outputs, prefer the '## Response'
    section (the agent's own report), then '## Script Error' / '## Script
    Output'. For legacy .txt outputs, strip the 'Cronjob Response:' header."""
    for header in ("## Response", "## Script Error", "## Script Output"):
        idx = text.find(header)
        if idx == -1:
            continue
        section = text[idx + len(header):]
        nxt = section.find("\n## ")
        if nxt != -1:
            section = section[:nxt]
        section = section.strip()
        if section:
            return section[:SUMMARY_MAX_CHARS]

    body = re.sub(r"^Cronjob Response:.*?\n-{3,}\n", "", text, flags=re.DOTALL).strip()
    return body[:SUMMARY_MAX_CHARS] if body else None


def _find_run_summary(job_id: str | None, profile: str | None, run_at_raw: str) -> str | None:
    """Locate the output file written for this specific run (filename
    timestamp closest to last_run_at's local wall-clock, within tolerance)
    and extract its summary."""
    if not job_id:
        return None
    try:
        local_wall_clock = datetime.fromisoformat(run_at_raw).replace(tzinfo=None)
    except ValueError:
        return None

    candidates = _candidate_output_files(job_id, profile)
    if not candidates:
        return None
    ts, path = min(candidates, key=lambda c: abs(c[0] - local_wall_clock))
    if abs(ts - local_wall_clock) > _OUTPUT_MATCH_TOLERANCE:
        return None
    try:
        return _extract_summary(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None


async def _ingest_cron_notifications(db: AsyncSession) -> int:
    """Upsert one notification per cron run currently visible in the
    jobs.json stores. Returns the number of newly inserted rows."""
    candidates: dict[str, dict] = {}
    for job in _load_all_cron_jobs():
        run_at_raw = job.get("last_run_at")
        job_key = job.get("id") or job.get("name")
        if not run_at_raw or not job_key:
            continue  # never ran (or unidentifiable) — nothing to record
        occurred_at = _parse_run_at(run_at_raw)
        if occurred_at is None:
            continue
        status = job.get("last_status") or "unknown"
        failed = status not in ("ok", "success")
        event_key = f"cron:{job_key}:{run_at_raw}"
        candidates[event_key] = {
            "severity": "error" if failed else "success",
            "title": job.get("name") or str(job_key),
            "message": job.get("last_error") if failed else None,
            "summary": _find_run_summary(job.get("id"), job.get("profile"), run_at_raw),
            "job_id": job.get("id"),
            "job_name": job.get("name"),
            "profile": job.get("profile"),
            "script_name": job.get("script"),
            "occurred_at": occurred_at,
        }

    if not candidates:
        return 0

    existing = (
        await db.execute(
            select(Notification.event_key).where(
                Notification.event_key.in_(candidates.keys())
            )
        )
    ).scalars().all()
    new_keys = set(candidates.keys()) - set(existing)
    for key in new_keys:
        db.add(Notification(id=uuid.uuid4(), source="cron", event_key=key, **candidates[key]))
    if new_keys:
        await db.commit()
    return len(new_keys)


def _to_out(row: Notification) -> NotificationOut:
    return NotificationOut(
        id=str(row.id),
        source=row.source,
        severity=row.severity,
        title=row.title,
        message=row.message,
        summary=row.summary,
        job_id=row.job_id,
        job_name=row.job_name,
        profile=row.profile,
        script_name=row.script_name,
        occurred_at=row.occurred_at,
        read_at=row.read_at,
        created_at=row.created_at,
    )


@router.get("", response_model=NotificationListOut)
async def list_notifications(
    unread_only: bool = False,
    severity: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> NotificationListOut:
    """List recorded notifications, newest first, after ingesting the
    current cron run outcomes."""
    if severity is not None and severity not in NOTIFICATION_SEVERITIES:
        raise HTTPException(status_code=400, detail=f"Invalid severity '{severity}'")
    await _ingest_cron_notifications(db)

    filters = []
    if unread_only:
        filters.append(Notification.read_at.is_(None))
    if severity is not None:
        filters.append(Notification.severity == severity)

    rows = (
        await db.execute(
            select(Notification)
            .where(*filters)
            .order_by(Notification.occurred_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    total = (
        await db.execute(select(func.count()).select_from(Notification).where(*filters))
    ).scalar_one()
    unread_count = (
        await db.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.read_at.is_(None))
        )
    ).scalar_one()

    return NotificationListOut(
        notifications=[_to_out(r) for r in rows],
        total=total,
        unread_count=unread_count,
    )


@router.post("/mark-read", response_model=MarkReadOut)
async def mark_read(payload: MarkReadIn, db: AsyncSession = Depends(get_db)) -> MarkReadOut:
    """Mark notifications as read (records read state server-side)."""
    if not payload.all and not payload.ids:
        raise HTTPException(status_code=400, detail="Provide 'ids' or set 'all' to true")

    stmt = (
        update(Notification)
        .where(Notification.read_at.is_(None))
        .values(read_at=datetime.now(timezone.utc))
    )
    if not payload.all:
        try:
            ids = [uuid.UUID(i) for i in payload.ids or []]
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid notification id") from None
        stmt = stmt.where(Notification.id.in_(ids))

    result = await db.execute(stmt)
    await db.commit()
    return MarkReadOut(marked=result.rowcount or 0)


@router.post("/cleanup", response_model=CleanupOut)
async def cleanup(payload: CleanupIn, db: AsyncSession = Depends(get_db)) -> CleanupOut:
    """Purge the notification record: everything, or older than keep_days."""
    stmt = delete(Notification)
    if payload.mode == "keep_days":
        if payload.keep_days is None:
            raise HTTPException(status_code=400, detail="keep_days is required for mode 'keep_days'")
        cutoff = datetime.now(timezone.utc) - timedelta(days=payload.keep_days)
        stmt = stmt.where(Notification.occurred_at < cutoff)

    result = await db.execute(stmt)
    await db.commit()
    return CleanupOut(deleted=result.rowcount or 0)
