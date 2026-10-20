import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ApprovalRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    target_revision_id: uuid.UUID | None
    target_hash: str
    approval_type: str
    policy_evaluation_id: uuid.UUID
    status: str
    requested_by_type: str
    requested_by_id: uuid.UUID
    requested_by_name: str
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PolicyEvaluationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    policy_binding_id: uuid.UUID
    policy_version_id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    target_revision_id: uuid.UUID | None
    target_hash: str
    input_hash: str
    outcome: str
    result: dict
    evaluator_version: str
    evaluated_at: datetime


class GovernedDecisionIn(BaseModel):
    decision: Literal["approved", "rejected", "changes_requested", "abstained"]
    comments: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=150)


class GovernedDecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    approval_request_id: uuid.UUID
    decision: str
    decided_by_type: str
    decided_by_id: uuid.UUID
    decided_by_name: str
    authority_source: str
    delegation_id: uuid.UUID | None
    comments: str | None
    created_at: datetime


class DelegationCreate(BaseModel):
    grantee_agent_id: uuid.UUID
    allowed_actions: list[str] = Field(min_length=1)
    scope_type: Literal["organization", "product", "project"] = "organization"
    product_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    max_risk: Literal["low", "medium", "high", "critical"] = "low"
    budget_limit: float | None = Field(default=None, ge=0)
    valid_from: datetime | None = None
    expires_at: datetime
    reason: str | None = None

    @model_validator(mode="after")
    def validate_scope(self):
        if self.scope_type == "product" and not self.product_id:
            raise ValueError("product_id is required for product scope")
        if self.scope_type == "project" and not self.project_id:
            raise ValueError("project_id is required for project scope")
        return self


class DelegationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    grantor_user_id: uuid.UUID
    grantee_type: str
    grantee_id: uuid.UUID
    scope_type: str
    product_id: uuid.UUID | None
    project_id: uuid.UUID | None
    allowed_actions: list[str]
    max_risk: str
    budget_limit: float | None
    valid_from: datetime
    expires_at: datetime
    status: str
    revoked_at: datetime | None
    reason: str | None


class AgentCredentialCreate(BaseModel):
    agent_id: uuid.UUID
    label: str = Field(min_length=1, max_length=150)
    expires_at: datetime | None = None


class AgentCredentialIssued(BaseModel):
    credential_id: uuid.UUID
    agent_id: uuid.UUID
    token: str
    expires_at: datetime | None
