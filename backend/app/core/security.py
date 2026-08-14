"""JWT creation/decoding and password hashing helpers.

Used today only by the temporary placeholder auth endpoint
(app/api/routes/auth.py). A future real Users/Auth domain should keep
using these helpers rather than reinventing them.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings


def hash_password(plain_password: str) -> str:
    """Create a bcrypt password hash."""
    return bcrypt.hashpw(plain_password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify existing and newly generated bcrypt hashes."""
    try:
        return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())
    except (TypeError, ValueError):
        return False


def create_access_token(
    subject: str, expires_delta: timedelta | None = None
) -> str:
    """Create a signed JWT access token for `subject` (e.g. username)."""
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode: dict[str, Any] = {"sub": subject, "exp": expire}
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode and validate a JWT, returning its payload or None if invalid."""
    try:
        return jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        return None
