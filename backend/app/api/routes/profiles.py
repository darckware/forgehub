"""Profile management routes — /api/v1/profiles.

Admin-only CRUD.  Profiles define per-module permissions for non-admin
users.  Admin users (is_admin=True) bypass all profile checks.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas.profile import ProfileCreate, ProfileOut, ProfileUpdate
from app.core.deps import get_current_admin
from app.db.base import get_db
from app.db.models.profile import Profile, ProfilePermission
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/profiles", tags=["profiles"])


async def _get_or_404(db: AsyncSession, profile_id: uuid.UUID) -> Profile:
    result = await db.execute(
        select(Profile)
        .where(Profile.id == profile_id)
        .options(selectinload(Profile.permissions))
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.get("", response_model=list[ProfileOut])
async def list_profiles(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> list[ProfileOut]:
    result = await db.execute(
        select(Profile)
        .options(selectinload(Profile.permissions))
        .order_by(Profile.name)
    )
    return [ProfileOut.model_validate(p) for p in result.scalars().all()]


@router.post("", response_model=ProfileOut, status_code=status.HTTP_201_CREATED)
async def create_profile(
    body: ProfileCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> ProfileOut:
    existing = await db.execute(select(Profile).where(Profile.name == body.name))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="Profile name already exists")

    profile = Profile(name=body.name, description=body.description)
    db.add(profile)
    await db.flush()

    for perm_in in body.permissions:
        db.add(ProfilePermission(
            profile_id=profile.id,
            module=perm_in.module,
            can_view=perm_in.can_view,
            can_query=perm_in.can_query,
            can_write=perm_in.can_write,
            can_delete=perm_in.can_delete,
        ))

    await db.commit()
    return ProfileOut.model_validate(await _get_or_404(db, profile.id))


@router.get("/{profile_id}", response_model=ProfileOut)
async def get_profile(
    profile_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> ProfileOut:
    return ProfileOut.model_validate(await _get_or_404(db, profile_id))


@router.patch("/{profile_id}", response_model=ProfileOut)
async def update_profile(
    profile_id: uuid.UUID,
    body: ProfileUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> ProfileOut:
    profile = await _get_or_404(db, profile_id)

    if body.name is not None and body.name != profile.name:
        dup = await db.execute(select(Profile).where(Profile.name == body.name))
        if dup.scalar_one_or_none() is not None:
            raise HTTPException(status_code=400, detail="Profile name already exists")
        profile.name = body.name
    if body.description is not None:
        profile.description = body.description

    if body.permissions is not None:
        # Full replace: delete existing then re-create
        await db.execute(
            ProfilePermission.__table__.delete().where(
                ProfilePermission.profile_id == profile_id
            )
        )
        for perm_in in body.permissions:
            db.add(ProfilePermission(
                profile_id=profile_id,
                module=perm_in.module,
                can_view=perm_in.can_view,
                can_query=perm_in.can_query,
                can_write=perm_in.can_write,
                can_delete=perm_in.can_delete,
            ))

    await db.commit()
    return ProfileOut.model_validate(await _get_or_404(db, profile_id))


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    profile_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> None:
    profile = await _get_or_404(db, profile_id)
    await db.delete(profile)
    await db.commit()
