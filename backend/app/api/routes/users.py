"""User management routes — /api/v1/users.

Admin-only CRUD.  GET /api/v1/users/me is the self-service endpoint (any
authenticated user).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.user import (
    ChangePasswordRequest,
    SelfUserUpdate,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.core.config import settings
from app.core.deps import get_current_admin, get_current_user
from app.core.security import hash_password, verify_password
from app.db.base import get_db
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("", response_model=list[UserOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> list[UserOut]:
    result = await db.execute(select(User).order_by(User.username))
    return [UserOut.model_validate(u) for u in result.scalars().all()]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> UserOut:
    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="Username already taken")
    user = User(
        username=body.username,
        hashed_password=hash_password(body.password),
        email=body.email,
        full_name=body.full_name,
        is_admin=body.is_admin,
        ui_language=settings.DEFAULT_UI_LANGUAGE,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)


@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)


@router.patch("/me", response_model=UserOut)
async def update_me(
    body: SelfUserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserOut:
    """Self-service profile edit -- any authenticated user, not just admins
    (unlike PATCH /{user_id} below). Deliberately can't touch
    password/is_admin/is_active/profile_id -- see SelfUserUpdate."""
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(current_user, k, v)
    await db.commit()
    await db.refresh(current_user)
    return UserOut.model_validate(current_user)


@router.post("/me/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_my_password(
    body: ChangePasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    current_user.hashed_password = hash_password(body.new_password)
    from app.core.user_audit import record_user_event
    record_user_event(db, "password_changed", current_user.username, current_user.id, request)
    await db.commit()


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> UserOut:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserOut.model_validate(user)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> UserOut:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    data = body.model_dump(exclude_unset=True)
    from app.core.user_audit import record_user_event
    if "profile_id" in data and data["profile_id"] != user.profile_id:
        record_user_event(db, "profile_changed", _admin.username, user.id, request)
    if "password" in data:
        record_user_event(db, "password_changed", _admin.username, user.id, request)
        user.hashed_password = hash_password(data.pop("password"))
    for k, v in data.items():
        setattr(user, k, v)
    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
) -> None:
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    await db.delete(user)
    await db.commit()


@router.get("/{user_id}/sessions")
async def list_user_sessions(user_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                             current_user: User = Depends(get_current_user)):
    from app.db.models.user_session import UserSession
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    rows = (await db.execute(select(UserSession).where(UserSession.user_id == user_id)
                             .order_by(UserSession.created_at.desc()))).scalars().all()
    return [{"id": str(row.id), "ip_address": row.ip_address, "user_agent": row.user_agent,
             "device_summary": row.device_summary, "agent_name": row.agent_name,
             "remember_me": row.remember_me, "is_active": row.is_active,
             "created_at": row.created_at, "last_activity_at": row.last_activity_at,
             "expires_at": row.expires_at} for row in rows]


@router.delete("/{user_id}/sessions/{session_id}", status_code=204)
async def revoke_user_session(user_id: uuid.UUID, session_id: uuid.UUID, request: Request,
                              db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(get_current_user)):
    from app.db.models.user_session import UserSession
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    row = await db.get(UserSession, session_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="Session not found")
    row.is_active = False
    from app.core.user_audit import record_user_event
    record_user_event(db, "session_revoked", current_user.username, user_id, request, session_id=str(session_id))
    await db.commit()


@router.delete("/{user_id}/sessions", status_code=204)
async def revoke_user_sessions(user_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db),
                               current_user: User = Depends(get_current_user)):
    from sqlalchemy import update
    from app.db.models.user_session import UserSession
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    await db.execute(update(UserSession).where(UserSession.user_id == user_id).values(is_active=False))
    from app.core.user_audit import record_user_event
    record_user_event(db, "sessions_revoked", current_user.username, user_id, request)
    await db.commit()


@router.get("/audit/events")
async def list_user_audit(event: str | None = None, actor: str | None = None,
                          db: AsyncSession = Depends(get_db),
                          _admin: User = Depends(get_current_admin)):
    from app.db.models.governance import AuditEvent
    query = select(AuditEvent).where(AuditEvent.entity_type == "user_access")
    if event:
        query = query.where(AuditEvent.event_type == event)
    if actor:
        query = query.where(AuditEvent.actor.ilike(f"%{actor}%"))
    rows = (await db.execute(query.order_by(AuditEvent.created_at.desc()).limit(200))).scalars().all()
    return [{"id": str(row.id), "user_id": str(row.entity_id), "event": row.event_type,
             "actor": row.actor, "details": row.payload, "created_at": row.created_at} for row in rows]
