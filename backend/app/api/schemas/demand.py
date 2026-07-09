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
    """Partial update -- only fields actually sent by the client are
    applied (route uses `model_dump(exclude_unset=True)`, same convention
    as artifact.py/backlog.py/product.py's PATCH routes). Lets the Inbox's
    drag-and-drop send `group_id` alone without touching `status`, while
    still supporting the plain "mark as read"/"archive" `status`-only
    calls the reading pane already made before groups existed."""

    status: str | None = None
    # Only meaningful once archived -- see AgentDemand.group_id's docstring.
    # Sending group_id (non-null) without an explicit status forces
    # status="archived" at the route layer.
    group_id: uuid.UUID | None = None

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str | None) -> str | None:
        if v is not None and v not in DEMAND_STATUSES:
            raise ValueError(f"status must be one of {DEMAND_STATUSES}")
        return v


class DemandGroupCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: uuid.UUID | None = None


class DemandGroupUpdateIn(BaseModel):
    """Partial update (rename and/or reparent) -- `exclude_unset=True` at
    the route layer, so `{"parent_id": null}` (move to the Arquivados root)
    is distinguishable from omitting parent_id entirely (leave it alone)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    parent_id: uuid.UUID | None = None


class DemandGroupOut(BaseModel):
    class Config:
        from_attributes = True

    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class DemandAttachmentOut(BaseModel):
    class Config:
        from_attributes = True

    id: uuid.UUID
    filename: str
    size_bytes: int
    content_type: str | None
    created_at: datetime


class DemandOut(BaseModel):
    class Config:
        from_attributes = True

    id: uuid.UUID
    from_agent: str
    subject: str
    body: str
    status: str
    group_id: uuid.UUID | None
    converted_entity_type: str | None
    converted_reference: str | None
    created_at: datetime
    updated_at: datetime
    attachments: list[DemandAttachmentOut] = []


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
    # task (existing planning item)
    planning_item_id: uuid.UUID | None = None
    # Destination path for target=doc / knowledge_base / artifact's
    # backing doc file. Defaulted per-target when omitted (see the routes).
    path: str | None = Field(default=None, max_length=500)
    # artifact
    artifact_type: str | None = None
    # planning_item / project_doc / quick_task -- which project this demand
    # becomes work for.
    project_id: uuid.UUID | None = None
    # planning_item / quick_task -- one of PLANNING_ITEM_TYPES; defaulted to
    # "documentation" at the route layer when omitted (matches the common
    # case: a procedure doc sent to a project).
    item_type: str | None = None
    # doc (Inbox only) -- which "área de criação" (docs_creation_areas) to
    # write into, per docs.py's multi-area model. Omitted = the original
    # single /root/docs mount (DOCS_ROOT), kept for docs.py's own /convert
    # entry point which isn't area-aware yet.
    area_id: uuid.UUID | None = None

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
