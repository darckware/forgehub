"""Auth router — POST /api/v1/auth/token.

Validates username/password against the Users table.  Falls back to the
DEV_USER settings credentials for the bootstrap login (before the admin
row is persisted) so the very first login always works.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.user import PermissionMap, TokenOut, UserOut
from app.core.config import settings
from app.core.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.base import get_db
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
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> TokenOut:
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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(subject=form_data.username)

    if user is None:
        # Materialize the bootstrap identity so every later sensitive
        # command resolves the same authenticated database principal.
        user = User(
            username=form_data.username,
            hashed_password=hash_password(form_data.password),
            full_name="Admin (bootstrap)", is_active=True, is_admin=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_out = UserOut.model_validate(user)
        permissions = _all_true_permissions()
        actions = {action: True for action in SENSITIVE_ACTIONS}
    else:
        user_out = UserOut.model_validate(user)
        permissions = await _build_permissions(user, db)
        actions = await _build_action_permissions(user, db)

    return TokenOut(access_token=token, token_type="bearer", user=user_out, permissions=permissions, actions=actions)


@router.get("/me", response_model=TokenOut)
async def get_me(
    current_user: User = Depends(get_current_user),
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
    token = create_access_token(subject=current_user.username)
    permissions = await _build_permissions(current_user, db)
    actions = await _build_action_permissions(current_user, db)
    return TokenOut(
        access_token=token,
        token_type="bearer",
        user=UserOut.model_validate(current_user),
        permissions=permissions,
        actions=actions,
    )
