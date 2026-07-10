"""FastAPI dependencies for auth and permission checks."""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.base import get_db
from app.db.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exc
    username: str | None = payload.get("sub")
    if not username:
        raise credentials_exc
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exc
    return user


async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


def require_perm(module: str, op: str):
    """Factory returning a dep that enforces a specific module permission.

    Usage:
        @router.post("/foo")
        async def create_foo(user = Depends(require_perm("product", "write"))):
            ...

    Admin users (is_admin=True) bypass all permission checks.
    op must be one of: "view", "query", "write", "delete".
    """
    async def _dep(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        if current_user.is_admin:
            return current_user
        if current_user.profile_id is None:
            raise HTTPException(status_code=403, detail=f"No profile assigned — cannot access {module}")
        from app.db.models.profile import ProfilePermission
        result = await db.execute(
            select(ProfilePermission).where(
                ProfilePermission.profile_id == current_user.profile_id,
                ProfilePermission.module == module,
            )
        )
        perm = result.scalar_one_or_none()
        if perm is None or not getattr(perm, f"can_{op}", False):
            raise HTTPException(status_code=403, detail=f"Permission denied: {module}.{op}")
        return current_user

    return _dep
