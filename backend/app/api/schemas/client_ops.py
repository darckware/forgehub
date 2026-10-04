"""Request schemas for the client_ops proxy domain (Darckware CRM).

Responses are Darckware's own JSON, normalized in the route module -- there
is no ForgeHub table behind this domain, so there is no ORM shape to mirror.
"""
from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

WorkItemKind = Literal["ticket", "demand"]
#: Unified type across Darckware's two vocabularies (ticket.type,
#: demand.category) -- the screen filters by this, not by either raw field.
WorkItemTipo = Literal["desenvolvimento", "servico"]


class EmailDraftIn(BaseModel):
    """Optional e-mail queued (never sent) alongside a status action."""

    subject: str = Field(..., min_length=1, max_length=300)
    body_text: str = Field(..., min_length=1)
    to_email: str | None = Field(default=None, description="Defaults to the item's requester")


class WorkItemCreate(BaseModel):
    kind: WorkItemKind
    client_account_id: uuid.UUID
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=4000)
    tipo: WorkItemTipo = "servico"
    priority: Literal["baixa", "media", "alta", "urgente"] = "media"
    #: Darckware demand category, when kind == "demand" (e.g. "suporte",
    #: "bug", "infraestrutura"). Defaults from `tipo`.
    category: str | None = Field(default=None, max_length=100)
    client_contact_id: uuid.UUID | None = None


class WorkItemAction(BaseModel):
    note: str | None = Field(default=None, max_length=4000)
    email: EmailDraftIn | None = None


class WorkItemResolve(BaseModel):
    resolution: str = Field(..., min_length=1, max_length=4000)
    email: EmailDraftIn | None = None


class WorkItemReopen(BaseModel):
    reason: str = Field(..., min_length=1, max_length=4000)


class OutboundEmailCreate(BaseModel):
    to_email: str
    subject: str = Field(..., min_length=1, max_length=300)
    body_text: str = Field(..., min_length=1)
    kind: str = "outro"
    submit: bool = True
    client_account_id: uuid.UUID | None = None
    lead_id: uuid.UUID | None = None
    demand_id: uuid.UUID | None = None
    ticket_id: uuid.UUID | None = None


class OutboundEmailUpdate(BaseModel):
    to_email: str | None = None
    subject: str | None = Field(default=None, max_length=300)
    body_text: str | None = None
    submit: bool | None = None


class OutboundEmailApprove(BaseModel):
    """The exact version the approver read -- Darckware refuses (409) if the
    text changed after it was shown."""

    version: int
    body_hash: str = Field(..., min_length=64, max_length=64)


class OutboundEmailReject(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)
