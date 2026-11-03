"""Environment domain routes (Plano Integrado M0.7).

Contract: docs/architecture/MISSION_EXECUTIONS_SCREEN_SPEC.md §6.

- ``GET  /api/v1/environments/releases``  latest release per (environment, target)
- ``POST /api/v1/environments/releases``  record a release -- the single writer

Who records: an administrator (Marcelo), or an agent with its own ``agt_``
holding an ``environment.release.record`` delegation (Hephaestus' publication
gate, or the publishing task's report). Every write is an AuditEvent with the
principal. Nothing here infers a release from a build or a container: a
target with no row is "no record".
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.environment import EnvironmentReleaseCreate, EnvironmentReleaseOut
from app.core.command_receipts import enforce_command_limits
from app.core.deps import ActorPrincipal, authorize_action, get_actor_principal
from app.db.base import get_db
from app.db.models.environment import EnvironmentRelease
from app.db.models.governance import AuditEvent
from app.db.models.task import ProjectTask

router = APIRouter(prefix="/api/v1/environments", tags=["environments"])

RECORD_ACTION = "environment.release.record"


async def latest_releases(
    db: AsyncSession, *, environment: str | None = None, targets: list[str] | None = None,
) -> list[tuple[EnvironmentRelease, int | None]]:
    """The newest row per (environment, target), with its task number."""
    ranked = select(
        EnvironmentRelease.id,
        func.row_number().over(
            partition_by=(EnvironmentRelease.environment, EnvironmentRelease.target),
            order_by=(EnvironmentRelease.released_at.desc(), EnvironmentRelease.created_at.desc()),
        ).label("rank"),
    )
    if environment is not None:
        ranked = ranked.where(EnvironmentRelease.environment == environment)
    if targets is not None:
        if not targets:
            return []
        ranked = ranked.where(EnvironmentRelease.target.in_(targets))
    ranked = ranked.subquery()
    rows = (await db.execute(
        select(EnvironmentRelease, ProjectTask.number)
        .join(ranked, ranked.c.id == EnvironmentRelease.id)
        .outerjoin(ProjectTask, ProjectTask.id == EnvironmentRelease.task_id)
        .where(ranked.c.rank == 1)
        .order_by(EnvironmentRelease.target, EnvironmentRelease.environment)
    )).all()
    return [(release, number) for release, number in rows]


def release_out(release: EnvironmentRelease, task_number: int | None) -> EnvironmentReleaseOut:
    out = EnvironmentReleaseOut.model_validate(release)
    out.task_number = task_number
    return out


@router.get("/releases", response_model=list[EnvironmentReleaseOut])
async def list_latest_releases(
    environment: str | None = Query(default=None, pattern="^(test|production)$"),
    target: str | None = Query(default=None, max_length=200),
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
) -> list[EnvironmentReleaseOut]:
    rows = await latest_releases(db, environment=environment, targets=[target] if target else None)
    return [release_out(release, number) for release, number in rows]


@router.post("/releases", response_model=EnvironmentReleaseOut, status_code=status.HTTP_201_CREATED)
async def record_release(
    payload: EnvironmentReleaseCreate,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
) -> EnvironmentReleaseOut:
    """Record what was published where. Admin, or an agent with
    environment.release.record; a non-admin person is 403. The same
    (environment, target, released_at) twice is 409."""
    if principal.principal_type == "user":
        if not principal.is_admin:
            raise HTTPException(403, detail={"code": "ADMIN_ONLY", "message": "Only an administrator records a release"})
        source, delegation = "admin", None
    else:
        enforce_command_limits(principal)
        try:
            source, delegation = await authorize_action(db, principal, RECORD_ACTION)
        except HTTPException as exc:
            if exc.status_code != 403:
                raise
            raise HTTPException(403, detail={"code": "DELEGATION_REQUIRED", "action": RECORD_ACTION,
                                             "message": f"No active delegation permits {RECORD_ACTION}"}) from exc
    task_number = None
    if payload.task_id is not None:
        task = await db.get(ProjectTask, payload.task_id)
        if task is None:
            raise HTTPException(404, detail={"code": "TASK_NOT_FOUND", "message": "Task not found"})
        task_number = task.number
    release = EnvironmentRelease(
        id=uuid.uuid4(), environment=payload.environment, target=payload.target, commit_sha=payload.commit_sha,
        branch=payload.branch, released_at=payload.released_at or datetime.now(timezone.utc),
        released_by=principal.display_name, task_id=payload.task_id, evidence_ref=payload.evidence_ref,
        source=payload.source,
    )
    db.add(release)
    db.add(AuditEvent(
        entity_type="environment_release", entity_id=release.id, event_type="environment_release_recorded",
        actor=principal.display_name,
        payload={"principal_type": principal.principal_type, "principal_id": str(principal.principal_id),
                 "authority_source": source, "delegation_id": str(delegation.id) if delegation else None,
                 "environment": release.environment, "target": release.target, "commit_sha": release.commit_sha,
                 "task_id": str(release.task_id) if release.task_id else None, "source": release.source},
    ))
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, detail={"code": "RELEASE_ALREADY_RECORDED",
                                         "message": "A release of this target at this instant is already recorded"}) from exc
    await db.refresh(release)
    return release_out(release, task_number)
