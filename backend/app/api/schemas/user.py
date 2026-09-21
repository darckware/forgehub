"""Pydantic schemas for the User domain."""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.db.models.user import UI_LANGUAGES


class UserCreate(BaseModel):
    username: str
    password: str
    email: str | None = None
    full_name: str | None = None
    is_admin: bool = False
    profile_id: uuid.UUID | None = None


class UserUpdate(BaseModel):
    email: str | None = None
    full_name: str | None = None
    is_active: bool | None = None
    is_admin: bool | None = None
    password: str | None = None
    profile_id: uuid.UUID | None = None


class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    email: str | None
    full_name: str | None
    avatar_data_url: str | None
    totp_enabled: bool
    is_active: bool
    is_admin: bool
    profile_id: uuid.UUID | None
    ui_language: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SelfUserUpdate(BaseModel):
    """Self-service profile edit (GET/PATCH /users/me) -- deliberately
    excludes password/is_admin/is_active/profile_id, which stay behind
    get_current_admin on the /{user_id} routes."""

    email: str | None = None
    full_name: str | None = None
    avatar_data_url: str | None = None
    ui_language: str | None = None

    @field_validator("ui_language")
    @classmethod
    def _check_ui_language(cls, v: str | None) -> str | None:
        if v is not None and v not in UI_LANGUAGES:
            raise ValueError(f"ui_language must be one of {UI_LANGUAGES}")
        return v


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


# Flat permissions map returned on login / GET /auth/me
PermissionMap = dict[str, dict[str, bool]]


class TokenOut(BaseModel):
    access_token: str
    token_type: str
    user: UserOut | None = None
    permissions: PermissionMap | None = None
    actions: dict[str, bool] = Field(default_factory=dict)
    requires_totp: bool = False
    totp_pending_token: str | None = None


class TotpSetupOut(BaseModel):
    """Returned by POST /auth/totp/setup."""
    secret: str
    provisioning_uri: str
    qr_code_data_url: str
    recovery_codes: list[str]


class TotpEnableRequest(BaseModel):
    """Sent to POST /auth/totp/enable after scanning the QR."""
    secret: str
    code: str
    recovery_codes: list[str] | None = None


class TotpDisableRequest(BaseModel):
    """Sent to POST /auth/totp/disable — requires current password + TOTP code."""
    password: str
    code: str


class TotpVerifyRequest(BaseModel):
    """Second step of the 2FA login — validates a TOTP or recovery code."""
    totp_pending_token: str
    code: str
