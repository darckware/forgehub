"""Administrative Nexo agent build catalog and installation endpoints."""

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.nexo_installation import (
    NexoAgentBuildOut,
    NexoBuildCatalogOut,
    NexoSource,
)
from app.core import nexo_builds
from app.core.deps import get_current_admin
from app.db.base import get_db
from app.db.models.nexo_installation import NexoAgentBuild
from app.db.models.user import User


router = APIRouter(prefix="/api/v1/nexo-agent-builds", tags=["nexo-agent-builds"])
PLATFORMS: tuple[Literal["linux", "windows"], ...] = ("linux", "windows")


def _project(build: NexoAgentBuild) -> NexoAgentBuildOut:
    return NexoAgentBuildOut.model_validate(build)


async def _ordered_builds(db: AsyncSession) -> list[NexoAgentBuild]:
    result = await db.execute(
        select(NexoAgentBuild).order_by(
            NexoAgentBuild.created_at.desc(),
            NexoAgentBuild.os_kind.asc(),
        )
    )
    return list(result.scalars())


async def _claim_build(
    db: AsyncSession,
    source: NexoSource,
    os_kind: Literal["linux", "windows"],
) -> tuple[NexoAgentBuild, bool]:
    await db.execute(
        insert(NexoAgentBuild)
        .values(
            git_sha=source.git_sha,
            agent_version=source.agent_version,
            os_kind=os_kind,
            status="queued",
        )
        .on_conflict_do_nothing(index_elements=["git_sha", "os_kind"])
    )
    await db.commit()

    build = (
        await db.execute(
            select(NexoAgentBuild)
            .where(
                NexoAgentBuild.git_sha == source.git_sha,
                NexoAgentBuild.os_kind == os_kind,
            )
            .with_for_update()
        )
    ).scalar_one()
    if build.status in {"ready", "building"}:
        await db.commit()
        return build, False

    if build.status == "failed":
        build.status = "queued"
        build.artifact_path = None
        build.artifact_size = None
        build.sha256 = None
        build.build_log_excerpt = None
        build.started_at = None
        build.completed_at = None
        await db.flush()

    build.status = "building"
    build.agent_version = source.agent_version
    build.started_at = datetime.now(timezone.utc)
    build.completed_at = None
    await db.commit()
    await db.refresh(build)
    return build, True


async def _refresh_platform(
    db: AsyncSession,
    source: NexoSource,
    os_kind: Literal["linux", "windows"],
) -> NexoAgentBuild:
    build, claimed = await _claim_build(db, source, os_kind)
    if not claimed:
        return build

    try:
        artifact = await nexo_builds.build_platform(os_kind)
        if artifact.git_sha != source.git_sha:
            raise nexo_builds.NexoBuildBridgeError(
                502,
                "Nexo source changed while the build was requested",
            )
    except nexo_builds.NexoBuildBridgeError as exc:
        build.status = "failed"
        build.artifact_path = None
        build.artifact_size = None
        build.sha256 = None
        build.build_log_excerpt = exc.detail[:2_000]
        build.completed_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    build.agent_version = artifact.agent_version
    build.status = "ready"
    build.artifact_path = artifact.artifact_path
    build.artifact_size = artifact.artifact_size
    build.sha256 = artifact.sha256
    build.build_log_excerpt = artifact.log_excerpt[:2_000]
    build.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(build)
    return build


@router.get("", response_model=NexoBuildCatalogOut)
async def list_nexo_agent_builds(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> NexoBuildCatalogOut:
    try:
        source = await nexo_builds.inspect_nexo_source()
    except nexo_builds.NexoBuildBridgeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    builds = await _ordered_builds(db)
    return NexoBuildCatalogOut(
        source=source, builds=[_project(build) for build in builds]
    )


@router.post(
    "", response_model=list[NexoAgentBuildOut], status_code=status.HTTP_202_ACCEPTED
)
async def refresh_nexo_agent_builds(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> list[NexoAgentBuildOut]:
    try:
        source = await nexo_builds.inspect_nexo_source()
    except nexo_builds.NexoBuildBridgeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    builds = [await _refresh_platform(db, source, os_kind) for os_kind in PLATFORMS]
    return [_project(build) for build in builds]
