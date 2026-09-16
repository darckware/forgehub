"""Authentication for the dedicated server-to-server client read API."""
import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models.client_report import ClientReadCredential

_bearer = HTTPBearer(auto_error=False)


def issue_client_read_token() -> str:
    return "clr_" + secrets.token_urlsafe(32)


def hash_client_read_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def get_client_read_credential(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> ClientReadCredential:
    if credentials is None or not credentials.credentials.startswith("clr_"):
        raise HTTPException(401, "Invalid client read credential")
    credential = (await db.execute(select(ClientReadCredential).where(
        ClientReadCredential.token_hash == hash_client_read_token(credentials.credentials),
        ClientReadCredential.revoked_at.is_(None),
    ))).scalar_one_or_none()
    if credential is None or (credential.expires_at is not None and credential.expires_at <= datetime.now(timezone.utc)):
        raise HTTPException(401, "Invalid client read credential")
    return credential
