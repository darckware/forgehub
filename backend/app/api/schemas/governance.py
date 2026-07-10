"""Pydantic Create/Update/Read schemas for the Governance domain.

Covers: Approval (primary, full CRUD-ish lifecycle), AuditEvent
(read-mostly: create + list/get, no update/delete by design — audit
integrity), Policy (secondary: create/list/get + update for
activate/deactivate).
"""
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------
class PolicyBase(BaseModel):
    name: str = Field(max_length=150)
    description: str | None = None
    policy_type: str = Field(max_length=100)
    rules: dict[str, Any] | None = None
    is_active: bool = True
    entity_type: str | None = Field(default=None, max_length=100)
    entity_id: uuid.UUID | None = None


class PolicyCreate(PolicyBase):
    pass


class PolicyUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=150)
    description: str | None = None
    policy_type: str | None = Field(default=None, max_length=100)
    rules: dict[str, Any] | None = None
    is_active: bool | None = None
    entity_type: str | None = Field(default=None, max_length=100)
    entity_id: uuid.UUID | None = None


class PolicyOut(PolicyBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Approval
# ---------------------------------------------------------------------------
class ApprovalBase(BaseModel):
    entity_type: str = Field(max_length=100)
    entity_id: uuid.UUID
    approval_type: str = Field(max_length=100)
    policy_id: uuid.UUID | None = None
    requested_by: str = Field(max_length=150)
    comments: str | None = None


class ApprovalCreate(ApprovalBase):
    pass


class ApprovalDecision(BaseModel):
    """Body for deciding (approving/rejecting) a pending approval."""

    decided_by: str = Field(max_length=150)
    comments: str | None = None


class ApprovalOut(ApprovalBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    decided_by: str | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# AuditEvent
# ---------------------------------------------------------------------------
class AuditEventBase(BaseModel):
    entity_type: str = Field(max_length=100)
    entity_id: uuid.UUID
    event_type: str = Field(max_length=100)
    actor: str = Field(max_length=150)
    payload: dict[str, Any] | None = None


class AuditEventCreate(AuditEventBase):
    pass


class AuditEventOut(AuditEventBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
