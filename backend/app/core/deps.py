"""FastAPI dependencies for auth, principals, and permission checks."""
import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.base import get_db
from app.db.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class ActorPrincipal:
    principal_type: str
    principal_id: uuid.UUID
    display_name: str
    is_admin: bool = False
    profile_id: uuid.UUID | None = None


async def get_actor_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> ActorPrincipal:
    if credentials is None:
        raise HTTPException(401, "Authentication required")
    token = credentials.credentials
    if token.startswith("agt_"):
        from app.db.models.agent import Agent, AgentServiceCredential
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        credential = (await db.execute(select(AgentServiceCredential).where(
            AgentServiceCredential.token_hash == token_hash,
            AgentServiceCredential.revoked_at.is_(None),
        ))).scalar_one_or_none()
        if credential is None or (credential.expires_at and credential.expires_at <= datetime.now(timezone.utc)):
            raise HTTPException(401, "Invalid or expired agent credential")
        agent = await db.get(Agent, credential.agent_id)
        if agent is None or not agent.is_active or agent.status != "active":
            raise HTTPException(403, "Agent principal is inactive")
        return ActorPrincipal("agent", agent.id, agent.name)
    payload = decode_access_token(token)
    username = payload.get("sub") if payload else None
    if not username:
        raise HTTPException(401, "Could not validate credentials")
    user = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(401, "Could not validate credentials")
    return ActorPrincipal("user", user.id, user.username, user.is_admin, user.profile_id)


async def authorize_action(
    db: AsyncSession,
    principal: ActorPrincipal,
    action_key: str,
    product_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    action_risk: str = "low",
    action_cost: float | None = None,
):
    """Return authority source/delegation or raise deny-by-default 403.

    action_risk/action_cost let a caller declare the risk level and cost of
    the action being authorized so a delegation's max_risk/budget_limit
    ceiling (GPA-08 acceptance criterion 8) is actually enforced instead of
    only stored. Callers that don't yet have a real risk/cost figure to
    supply (no per-project/task risk classification exists yet — see
    docs/PLANNING_DELIVERY_ARCHITECTURE.md §2.2) fall back to "low"/None,
    which only satisfies delegations at or above that ceiling.
    """
    if principal.principal_type == "user":
        if principal.is_admin:
            return "admin", None
        if principal.profile_id is None:
            raise HTTPException(403, f"Permission denied: {action_key}")
        from app.db.models.profile import ProfileActionPermission
        allowed = (await db.execute(select(ProfileActionPermission).where(
            ProfileActionPermission.profile_id == principal.profile_id,
            ProfileActionPermission.action_key == action_key,
            ProfileActionPermission.allowed.is_(True),
        ))).scalar_one_or_none()
        if not allowed:
            raise HTTPException(403, f"Permission denied: {action_key}")
        return "profile", None

    from app.db.models.governance import DELEGATION_RISK_ORDER, AuthorityDelegation
    now = datetime.now(timezone.utc)
    rows = list((await db.execute(select(AuthorityDelegation).where(
        AuthorityDelegation.grantee_type == "agent",
        AuthorityDelegation.grantee_id == principal.principal_id,
        AuthorityDelegation.status == "active",
        AuthorityDelegation.valid_from <= now,
        AuthorityDelegation.expires_at > now,
    ))).scalars())
    requested_risk = DELEGATION_RISK_ORDER.get(action_risk, 0)
    for row in rows:
        if action_key not in row.allowed_actions:
            continue
        if row.product_id and row.product_id != product_id:
            continue
        if row.project_id and row.project_id != project_id:
            continue
        if requested_risk > DELEGATION_RISK_ORDER.get(row.max_risk, 0):
            continue
        if action_cost is not None and row.budget_limit is not None and action_cost > float(row.budget_limit):
            continue
        return "delegation", row
    raise HTTPException(403, f"No active delegation permits: {action_key}")


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


async def get_current_username(token: str = Depends(oauth2_scheme)) -> str:
    """Just the JWT subject, no `User` row lookup -- unlike get_current_user,
    safe to use as a display-only "who did this" value (e.g.
    ChatChannel.created_by) in routes that, like almost every other domain
    router in this codebase (see main.py's RequireAuthMiddleware docstring:
    "almost none of the domain routers were wired up with their own auth
    dependency"), don't otherwise gate on a real Users-domain row."""
    payload = decode_access_token(token)
    username = payload.get("sub") if payload else None
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return username


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
