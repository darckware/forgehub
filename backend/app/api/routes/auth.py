"""Auth router — POST /api/v1/auth/token.

Validates username/password against the Users table.  Falls back to the
DEV_USER settings credentials for the bootstrap login (before the admin
row is persisted) so the very first login always works.

When a user has TOTP-based 2FA enabled, the password step returns a
short-lived ``totp_pending_token`` instead of a real access token — the
frontend must call /auth/totp/verify with the 6-digit code to complete
the login and receive the real JWT.
"""
import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.user import PermissionMap, TokenOut, UserOut
from app.core.config import settings
from app.core.agent_session import (
    EVENT_OPENED,
    EVENT_REFUSED,
    agent_as_user,
    audit_access,
    create_agent_session_token,
    is_agent_session,
    request_origin,
)
from app.core.deps import get_current_user, oauth2_scheme
from app.core.recaptcha import verify_recaptcha
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.db.base import get_db
from app.db.models.agent import Agent, AgentServiceCredential
from app.db.models.profile import MODULES, SENSITIVE_ACTIONS, ProfileActionPermission, ProfilePermission
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _all_true_permissions() -> PermissionMap:
    return {m: {"can_view": True, "can_query": True, "can_write": True, "can_delete": True} for m in MODULES}


async def _build_permissions(user: User, db: AsyncSession) -> PermissionMap:
    if user.is_admin:
        return _all_true_permissions()
    if user.profile_id is None:
        return {m: {"can_view": False, "can_query": False, "can_write": False, "can_delete": False} for m in MODULES}
    result = await db.execute(
        select(ProfilePermission).where(ProfilePermission.profile_id == user.profile_id)
    )
    perm_map: PermissionMap = {}
    for row in result.scalars().all():
        perm_map[row.module] = {
            "can_view": row.can_view,
            "can_query": row.can_query,
            "can_write": row.can_write,
            "can_delete": row.can_delete,
        }
    for m in MODULES:
        if m not in perm_map:
            perm_map[m] = {"can_view": False, "can_query": False, "can_write": False, "can_delete": False}
    return perm_map


async def _build_action_permissions(user: User, db: AsyncSession) -> dict[str, bool]:
    if user.is_admin:
        return {action: True for action in SENSITIVE_ACTIONS}
    actions = {action: False for action in SENSITIVE_ACTIONS}
    if user.profile_id is None:
        return actions
    rows = list((await db.execute(select(ProfileActionPermission).where(
        ProfileActionPermission.profile_id == user.profile_id
    ))).scalars())
    for row in rows:
        actions[row.action_key] = row.allowed
    return actions


@router.post("/token", response_model=TokenOut)
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    recaptcha_token: str | None = Form(default=None),
    remember_me: bool = Form(default=False),
    db: AsyncSession = Depends(get_db),
) -> TokenOut:
    if not await verify_recaptcha(recaptcha_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="reCAPTCHA verification failed",
        )

    result = await db.execute(select(User).where(User.username == form_data.username))
    user: User | None = result.scalar_one_or_none()

    authenticated = False
    if user is not None and user.is_active:
        authenticated = verify_password(form_data.password, user.hashed_password)
    elif (
        form_data.username == settings.DEV_USER_USERNAME
        and form_data.password == settings.DEV_USER_PASSWORD
        and user is None
    ):
        authenticated = True

    if not authenticated:
        from app.core.user_audit import record_user_event
        record_user_event(db, "login_refused", form_data.username, user.id if user else None, request)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )


    if user is None:
        # Materialize the bootstrap identity so every later sensitive
        # command resolves the same authenticated database principal.
        user = User(
            username=form_data.username,
            hashed_password=hash_password(form_data.password),
            full_name="Admin (bootstrap)", is_active=True, is_admin=True,
            ui_language=settings.DEFAULT_UI_LANGUAGE,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_out = UserOut.model_validate(user)
        permissions = _all_true_permissions()
        actions = {action: True for action in SENSITIVE_ACTIONS}
    else:
        # ---- 2FA gate ----
        if user.totp_enabled:
            pending_token = create_access_token(
                subject=form_data.username,
                expires_delta=timedelta(minutes=5),
                extra_claims={"purpose": "totp_pending", "remember_me": remember_me},
            )
            return TokenOut(
                access_token="",
                token_type="bearer",
                requires_totp=True,
                totp_pending_token=pending_token,
            )
        user_out = UserOut.model_validate(user)
        permissions = await _build_permissions(user, db)
        actions = await _build_action_permissions(user, db)

    from app.core.user_session import create_session
    from app.core.user_audit import record_user_event
    record_user_event(db, "login_accepted", user.username, user.id, request)
    token = await create_session(db, user, request, remember_me=remember_me)
    return TokenOut(access_token=token, token_type="bearer", user=user_out, permissions=permissions, actions=actions)


@router.post("/agent-session", response_model=TokenOut)
async def open_agent_session(
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> TokenOut:
    """Open the screens for an agent, with its own `agt_` credential and no login.

    The session is the agent's own: read-only, 30 minutes, never renewed, and
    limited by core/agent_session.py. Each agent is allowed in Settings, and
    every attempt, allowed or refused, reaches the access audit.
    """
    origin = request_origin(request)

    async def refuse(code: int, reason: str, agent: Agent | None = None) -> HTTPException:
        name = (agent.profile_slug or agent.name) if agent else "desconhecido"
        audit_access(db, EVENT_REFUSED, agent.id if agent else None, name, reason=reason, **origin)
        await db.commit()
        return HTTPException(code, reason)

    token = authorization[7:] if authorization and authorization.lower().startswith("bearer ") else ""
    credential = None
    if token.startswith("agt_"):
        credential = (await db.execute(select(AgentServiceCredential).where(
            AgentServiceCredential.token_hash == hashlib.sha256(token.encode()).hexdigest(),
            AgentServiceCredential.revoked_at.is_(None),
        ))).scalar_one_or_none()
    if credential is None or (credential.expires_at and credential.expires_at <= datetime.now(timezone.utc)):
        raise await refuse(status.HTTP_401_UNAUTHORIZED, "Invalid or expired agent credential")
    agent = await db.get(Agent, credential.agent_id)
    if agent is None or not agent.is_active or agent.status != "active":
        raise await refuse(status.HTTP_403_FORBIDDEN, "Agent principal is inactive", agent)
    if not agent.screen_access_enabled:
        raise await refuse(status.HTTP_403_FORBIDDEN, "Screen access is not enabled for this agent", agent)
    user = await agent_as_user(db, agent.id)
    if user is None:
        raise await refuse(status.HTTP_403_FORBIDDEN, "Agent access is disabled in this system", agent)
    audit_access(db, EVENT_OPENED, agent.id, agent.profile_slug or agent.name,
                 credential_id=str(credential.id), **origin)
    await db.commit()
    from app.core.user_session import create_session
    from app.core.agent_session import AGENT_SESSION_MINUTES
    agent_payload = decode_access_token(create_agent_session_token(agent, credential.id))
    claims = {k: v for k, v in agent_payload.items() if k not in ("sub", "exp")}
    token = await create_session(db, user, request, agent_id=agent.id, agent_name=agent.profile_slug or agent.name,
                                 lifetime=timedelta(minutes=AGENT_SESSION_MINUTES), claims=claims)
    return TokenOut(
        access_token=token,
        token_type="bearer",
        user=UserOut.model_validate(user),
        permissions=await _build_permissions(user, db),
        actions=await _build_action_permissions(user, db),
    )


@router.get("/me", response_model=TokenOut)
async def get_me(
    request: Request,
    current_user: User = Depends(get_current_user),
    raw_token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> TokenOut:
    """Sliding-session refresh: the frontend's activity tracker (see
    useSessionKeepAlive) calls this periodically while the user is active,
    each call re-minting a fresh access_token here so an actively-used
    session never expires out from under the user -- only a truly idle
    session (no calls for a full token lifetime) hits the 401 in
    lib/api.ts and gets logged out. get_current_user already requires the
    *current* token to still be valid, so this can't resurrect an
    already-expired session, only extend one that hasn't expired yet."""
    # An agent session keeps its token: renewing it here would lift its limits.
    payload = decode_access_token(raw_token)
    if is_agent_session(payload):
        token = raw_token
    elif "sid" not in payload:
        # Moves a JWT from before sessions to a session that can be ended.
        from app.core.user_session import create_session
        token = await create_session(db, current_user, request)
    else:
        from app.core.user_session import refresh_session
        lifetime = await refresh_session(db, payload["sid"])
        if lifetime is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        token = create_access_token(
            subject=current_user.username, expires_delta=lifetime, extra_claims={"sid": payload["sid"]},
        )
    permissions = await _build_permissions(current_user, db)
    actions = await _build_action_permissions(current_user, db)
    return TokenOut(
        access_token=token,
        token_type="bearer",
        user=UserOut.model_validate(current_user),
        permissions=permissions,
        actions=actions,
    )


@router.post("/logout", status_code=204)
async def logout(request: Request, current_user: User = Depends(get_current_user),
                 token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    from sqlalchemy import update
    from app.core.user_audit import record_user_event
    from app.core.user_session import session_hash
    from app.db.models.user_session import UserSession
    payload = decode_access_token(token)
    if payload.get("sid"):
        # Before deactivating the session: same lock order as an agent's collaborative command.
        from app.core.remote_collaboration import end_sessions_for_logout
        await end_sessions_for_logout(db, session_hash(payload["sid"]), current_user.username)
        await db.execute(update(UserSession).where(UserSession.token_hash == session_hash(payload["sid"]),
                                                   UserSession.user_id == current_user.id).values(is_active=False))
    record_user_event(db, "logout", current_user.username, current_user.id, request)
    await db.commit()
