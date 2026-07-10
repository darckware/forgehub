"""Pydantic schemas for the Profile/RBAC domain."""
import uuid
from datetime import datetime

from pydantic import BaseModel


class PermissionIn(BaseModel):
    module: str
    can_view: bool = True
    can_query: bool = True
    can_write: bool = False
    can_delete: bool = False


class PermissionOut(BaseModel):
    module: str
    can_view: bool
    can_query: bool
    can_write: bool
    can_delete: bool

    model_config = {"from_attributes": True}


class ProfileCreate(BaseModel):
    name: str
    description: str | None = None
    permissions: list[PermissionIn] = []


class ProfileUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    permissions: list[PermissionIn] | None = None


class ProfileOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    permissions: list[PermissionOut]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# Flat map returned in auth responses: module → {can_view, …}
PermissionMap = dict[str, dict[str, bool]]
