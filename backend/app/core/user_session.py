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


async def create_session(db, user, request, *, agent_name=None, lifetime=None, claims=None):
    identifier = secrets.token_urlsafe(32)
    lifetime = lifetime or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    origin = request_origin(request)
    db.add(UserSession(user_id=user.id, token_hash=session_hash(identifier),
                       ip_address=origin["ip_address"], user_agent=origin["user_agent"],
                       device_summary=origin["user_agent"], agent_name=agent_name,
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


async def refresh_session(db, identifier):
    from sqlalchemy import update
    now = datetime.now(timezone.utc)
    result = await db.execute(update(UserSession).where(
        UserSession.token_hash == session_hash(identifier), UserSession.is_active.is_(True),
        UserSession.expires_at > now,
    ).values(expires_at=now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)))
    await db.commit()
    return result.rowcount == 1
