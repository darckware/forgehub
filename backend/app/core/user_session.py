"""Creation and validation of revocable browser sessions."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.agent_session import request_origin
from app.core.config import settings
from app.core.security import create_access_token
from app.db.models.user_session import UserSession


def session_hash(identifier: str) -> str:
    return hashlib.sha256(identifier.encode()).hexdigest()


async def create_session(db, user, request, *, agent_name=None, lifetime=None, claims=None, remember_me=False):
    identifier = secrets.token_urlsafe(32)
    lifetime = lifetime or session_lifetime(remember_me)
    if agent_name is None and settings.SESSION_MAX_CONCURRENT:
        from app.db.models.user import User
        await db.execute(select(User.id).where(User.id == user.id).with_for_update())
        active = (await db.execute(select(UserSession).where(
            UserSession.user_id == user.id, UserSession.is_active.is_(True),
            UserSession.expires_at > datetime.now(timezone.utc),
        ).order_by(UserSession.created_at, UserSession.id))).scalars().all()
        for old in active[:max(0, len(active) - settings.SESSION_MAX_CONCURRENT + 1)]:
            old.is_active = False
    origin = request_origin(request)
    db.add(UserSession(user_id=user.id, token_hash=session_hash(identifier),
                       ip_address=origin["ip_address"], user_agent=origin["user_agent"],
                       device_summary=origin["user_agent"], agent_name=agent_name, remember_me=remember_me,
                       expires_at=datetime.now(timezone.utc) + lifetime))
    await db.commit()
    return create_access_token(user.username, expires_delta=lifetime,
                               extra_claims={**(claims or {}), "sid": identifier})


async def session_is_live(db, payload):
    identifier = payload.get("sid")
    if identifier is None:
        return True  # JWTs issued before sessions were introduced.
    if not isinstance(identifier, str) or len(identifier) > 128:
        return False
    from app.db.models.user import User
    row = (await db.execute(select(UserSession).join(User, User.id == UserSession.user_id).where(
        UserSession.token_hash == session_hash(identifier), User.username == payload.get("sub"),
        User.is_active.is_(True), UserSession.is_active.is_(True),
        UserSession.expires_at > datetime.now(timezone.utc),
    ))).scalar_one_or_none()
    if row is None:
        return False
    now = datetime.now(timezone.utc)
    if row.last_activity_at < now - timedelta(minutes=5):
        row.last_activity_at = now
        await db.commit()
    return True


def session_lifetime(remember_me):
    return timedelta(days=settings.SESSION_REMEMBER_DAYS) if remember_me else timedelta(minutes=settings.SESSION_TIMEOUT_MINUTES)


async def refresh_session(db, identifier):
    now = datetime.now(timezone.utc)
    row = (await db.execute(select(UserSession).where(
        UserSession.token_hash == session_hash(identifier), UserSession.is_active.is_(True),
        UserSession.expires_at > now,
    ).with_for_update())).scalar_one_or_none()
    if row is None:
        return None
    lifetime = session_lifetime(row.remember_me)
    row.expires_at = now + lifetime
    await db.commit()
    return lifetime
