"""Pydantic schemas for the agent-demand inbox and its conversions."""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.conversions import CONVERT_TARGETS
from app.db.models.demand import DEMAND_STATUSES


class DemandSubmitIn(BaseModel):
    """Body for POST /demands/submit (agents, via the shared bridge token)."""

    from_agent: str = Field(min_length=1, max_length=50)
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)


class DemandUpdateIn(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str) -> str:
        if v not in DEMAND_STATUSES:
            raise ValueError(f"status must be one of {DEMAND_STATUSES}")
        return v


class DemandOut(BaseModel):
    class Config:
        from_attributes = True

    id: uuid.UUID
    from_agent: str
    subject: str
    body: str
    status: str
    converted_entity_type: str | None
    converted_reference: str | None
    created_at: datetime
    updated_at: datetime


class ConvertIn(BaseModel):
    """Body for POST /demands/{id}/convert and POST /docs/convert.

    Which extra fields are required depends on `target` -- validated in
    the route layer (the error message can name the missing field), same
    pattern as ProjectTaskCreate's cross-field check.
    """

    target: str
    title: str | None = Field(default=None, max_length=255)
    # Which existing /root/docs note to convert -- only used by
    # POST /docs/convert (demand.py's /demands/{id}/convert gets its
    # content from the demand row instead).
    source_path: str | None = Field(default=None, max_length=500)
    # task
    planning_item_id: uuid.UUID | None = None
    # Destination path for target=doc / knowledge_base / artifact's
    # backing doc file. Defaulted per-target when omitted (see the routes).
    path: str | None = Field(default=None, max_length=500)
    # artifact
    artifact_type: str | None = None

    @field_validator("target")
    @classmethod
    def _check_target(cls, v: str) -> str:
        if v not in CONVERT_TARGETS:
            raise ValueError(f"target must be one of {CONVERT_TARGETS}")
        return v


class ConvertOut(BaseModel):
    entity_type: str
    entity_id: str | None = None
    reference: str
