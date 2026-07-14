"""Pydantic schemas for the User domain."""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


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
    is_active: bool
    is_admin: bool
    profile_id: uuid.UUID | None
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


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


# Flat permissions map returned on login / GET /auth/me
PermissionMap = dict[str, dict[str, bool]]


class TokenOut(BaseModel):
    access_token: str
    token_type: str
    user: UserOut
    permissions: PermissionMap
    actions: dict[str, bool] = Field(default_factory=dict)
