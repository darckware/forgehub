"""Administrative Nexo agent build catalog and installation endpoints."""

from __future__ import annotations

import asyncio
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.nexo_installation import (
    NexoAgentBuildOut,
    NexoBuildCatalogOut,
    NexoSource,
)
from app.api.routes.workstation import _generate_device_token, hash_device_token
from app.core import nexo_builds, nexo_packages
from app.core.deps import get_current_admin
from app.db.base import AsyncSessionLocal, get_db
from app.db.models.client import Workstation
from app.db.models.nexo_installation import (
    NexoAgentBuild,
    WorkstationInstallation,
    WorkstationInstallationEvent,
)
from app.db.models.user import User


router = APIRouter()
build_router = APIRouter(
    prefix="/api/v1/nexo-agent-builds", tags=["nexo-agent-builds"]
)
PLATFORMS: tuple[Literal["linux", "windows"], ...] = ("linux", "windows")
# A live bridge request must time out before another request may reclaim its
# database claim. The extra minute covers request/response and commit overhead.
BUILD_CLAIM_LEASE_SECONDS = nexo_builds.BUILD_TIMEOUT_SECONDS + 60.0


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
    now = datetime.now(timezone.utc)
    building_claim_is_fresh = (
        build.status == "building"
        and build.started_at is not None
        and build.started_at > now - timedelta(seconds=BUILD_CLAIM_LEASE_SECONDS)
    )
    if build.status == "ready" or building_claim_is_fresh:
        await db.commit()
        return build, False

    if build.status in {"failed", "building"}:
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
    build.started_at = now
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


@build_router.get("", response_model=NexoBuildCatalogOut)
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


@build_router.post(
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


async def _stream_package(
    temporary_directory: tempfile.TemporaryDirectory[str],
    metadata: nexo_packages.PackageMetadata,
    installation_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> AsyncIterator[bytes]:
    """Stream a package, recording delivery only after the final yield resumes."""
    try:
        with metadata.path.open("rb") as package:
            while chunk := package.read(64 * 1024):
                yield chunk
        async with AsyncSessionLocal() as db:
            installation = (
                await db.execute(
                    select(WorkstationInstallation)
                    .where(WorkstationInstallation.id == installation_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if (
                installation is not None
                and installation.status == "package_ready"
                and installation.package_generated_at == metadata.generated_at
            ):
                delivered_at = datetime.now(timezone.utc)
                installation.status = "downloaded"
                installation.downloaded_at = delivered_at
                db.add(
                    WorkstationInstallationEvent(
                        installation_id=installation.id,
                        event_type="downloaded",
                        from_status="package_ready",
                        to_status="downloaded",
                        actor_user_id=actor_user_id,
                    )
                )
                await db.commit()
    finally:
        # Keep this in the iterator rather than a response background task:
        # cancellation closes the iterator, removes the secret ZIP, and does
        # not claim the package was delivered.
        temporary_directory.cleanup()


@router.post(
    "/api/v1/workstations/{workstation_id}/installation-package",
    tags=["workstations"],
    response_class=StreamingResponse,
)
async def generate_workstation_installation_package(
    workstation_id: uuid.UUID,
    build_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> StreamingResponse:
    workstation = await db.get(Workstation, workstation_id)
    if workstation is None:
        raise HTTPException(status_code=404, detail="Workstation not found")
    build = await db.get(NexoAgentBuild, build_id)
    if build is None:
        raise HTTPException(status_code=404, detail="Nexo build not found")
    if build.status != "ready":
        raise HTTPException(status_code=409, detail="Nexo build is not ready")
    if workstation.os_kind != build.os_kind:
        raise HTTPException(
            status_code=409,
            detail="Nexo build does not match workstation platform",
        )

    raw_token = _generate_device_token()
    temporary_directory = tempfile.TemporaryDirectory(prefix="forgehub-nexo-package-")
    try:
        metadata = await asyncio.to_thread(
            nexo_packages.materialize_package,
            workstation,
            build,
            raw_token,
            temporary_directory.name,
        )
    except nexo_packages.NexoPackageError as exc:
        temporary_directory.cleanup()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        temporary_directory.cleanup()
        raise

    try:
        locked_workstation = (
            await db.execute(
                select(Workstation)
                .where(Workstation.id == workstation_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if locked_workstation is None:
            raise HTTPException(status_code=404, detail="Workstation not found")
        locked_build = (
            await db.execute(
                select(NexoAgentBuild)
                .where(NexoAgentBuild.id == build_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if locked_build is None:
            raise HTTPException(status_code=404, detail="Nexo build not found")
        if locked_build.status != "ready":
            raise HTTPException(status_code=409, detail="Nexo build is not ready")
        if locked_workstation.os_kind != locked_build.os_kind:
            raise HTTPException(
                status_code=409,
                detail="Nexo build does not match workstation platform",
            )

        installation = (
            await db.execute(
                select(WorkstationInstallation)
                .where(WorkstationInstallation.workstation_id == workstation_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        from_status = installation.status if installation is not None else None
        if installation is None:
            installation = WorkstationInstallation(
                workstation_id=workstation_id,
                build_id=build_id,
                status="package_ready",
                package_generated_at=metadata.generated_at,
            )
            db.add(installation)
            await db.flush()
        else:
            installation.build_id = build_id
            installation.status = "package_ready"
            installation.package_generated_at = metadata.generated_at
            installation.downloaded_at = None
            installation.online_at = None
            installation.last_error = None

        locked_workstation.device_token_hash = hash_device_token(raw_token)
        locked_workstation.device_token_issued_at = metadata.generated_at
        locked_workstation.device_token_revoked_at = None
        locked_workstation.last_report_at = None
        locked_workstation.last_seen_agent_version = None
        db.add(
            WorkstationInstallationEvent(
                installation_id=installation.id,
                event_type="package_generated",
                from_status=from_status,
                to_status="package_ready",
                actor_user_id=admin.id,
            )
        )
        await db.commit()
    except Exception:
        await db.rollback()
        temporary_directory.cleanup()
        raise

    return StreamingResponse(
        _stream_package(temporary_directory, metadata, installation.id, admin.id),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{metadata.filename}"',
            "Content-Length": str(metadata.size),
            "X-Content-Type-Options": "nosniff",
        },
    )


router.include_router(build_router)
