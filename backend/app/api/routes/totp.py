"""TOTP two-factor authentication routes — /api/v1/auth/totp.

Setup, enable, disable, and verify endpoints that let users manage
TOTP-based 2FA from the UserSettingsMenu and complete the second login
step when 2FA is active.
"""
import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.user import (
    TotpDisableRequest,
    TotpEnableRequest,
    TotpSetupOut,
    TotpVerifyRequest,
    TokenOut,
    UserOut,
)
from app.core.deps import get_current_user
from app.core.security import create_access_token, decode_access_token, verify_password
from app.core.totp import (
    generate_provisioning_uri,
    generate_qr_code_data_url,
    generate_recovery_codes,
    generate_totp_secret,
    hash_recovery_code,
    verify_recovery_code,
    verify_totp_code,
)
from app.db.base import get_db
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/auth/totp", tags=["totp"])


@router.post("/setup", response_model=TotpSetupOut)
async def totp_setup(
    current_user: User = Depends(get_current_user),
) -> TotpSetupOut:
    """Generate a new TOTP secret, QR code, and recovery codes.

    Does NOT enable 2FA yet — the user must call /enable with a valid
    code to prove they scanned the QR successfully.
    """
    secret = generate_totp_secret()
    uri = generate_provisioning_uri(secret, current_user.username)
    qr = generate_qr_code_data_url(uri)
    codes = generate_recovery_codes()
    return TotpSetupOut(
        secret=secret,
        provisioning_uri=uri,
        qr_code_data_url=qr,
        recovery_codes=codes,
    )


@router.post("/enable", status_code=status.HTTP_200_OK)
async def totp_enable(
    body: TotpEnableRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    """Validate a TOTP code against the pending secret and enable 2FA.

    The frontend sends the secret it received from /setup together with
    the 6-digit code the user typed after scanning the QR.
    """
    if current_user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA is already enabled")

    if not verify_totp_code(body.secret, body.code):
        raise HTTPException(status_code=400, detail="Invalid TOTP code")

    # Persist the secret and generate/save hashed recovery codes.
    codes = body.recovery_codes if body.recovery_codes else generate_recovery_codes()
    hashed = [hash_recovery_code(c) for c in codes]
    current_user.totp_secret = body.secret
    current_user.totp_enabled = True
    current_user.totp_recovery_codes = json.dumps(hashed)
    await db.commit()

    return {"enabled": True}


@router.post("/disable", status_code=status.HTTP_200_OK)
async def totp_disable(
    body: TotpDisableRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    """Disable 2FA — requires the current password plus a valid TOTP code."""
    if not current_user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA is not enabled")

    if not verify_password(body.password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect password")

    if not verify_totp_code(current_user.totp_secret or "", body.code):
        raise HTTPException(status_code=400, detail="Invalid TOTP code")

    current_user.totp_secret = None
    current_user.totp_enabled = False
    current_user.totp_recovery_codes = None
    await db.commit()

    return {"enabled": False}


@router.post("/verify", response_model=TokenOut)
async def totp_verify(
    body: TotpVerifyRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenOut:
    """Second step of the 2FA login flow.

    Validates the TOTP code (or a recovery code) against the pending
    token issued by /auth/token, and returns a full access token.
    """
    from app.api.routes.auth import _build_action_permissions, _build_permissions

    payload = decode_access_token(body.totp_pending_token)
    if payload is None or payload.get("purpose") != "totp_pending":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired pending token",
        )

    from sqlalchemy import select
    username = payload["sub"]
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or not user.totp_enabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user")

    clean_code = body.code.strip().replace("-", "").replace(" ", "")

    # Try TOTP code first, then recovery code.
    code_valid = verify_totp_code(user.totp_secret or "", clean_code)

    if not code_valid:
        # Try recovery codes.
        stored_hashes: list[str] = json.loads(user.totp_recovery_codes or "[]")
        matched_idx = None
        for idx, h in enumerate(stored_hashes):
            if verify_recovery_code(clean_code, h):
                matched_idx = idx
                break
        if matched_idx is not None:
            # Consume the used recovery code.
            stored_hashes.pop(matched_idx)
            user.totp_recovery_codes = json.dumps(stored_hashes)
            await db.commit()
            await db.refresh(user)
            code_valid = True

    if not code_valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid TOTP code")

    # Issue the real access token.
    token = create_access_token(subject=username)
    permissions = await _build_permissions(user, db)
    actions = await _build_action_permissions(user, db)
    return TokenOut(
        access_token=token,
        token_type="bearer",
        user=UserOut.model_validate(user),
        permissions=permissions,
        actions=actions,
    )
