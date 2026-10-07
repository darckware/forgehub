"""Request schemas for the client_ops proxy domain (Darckware CRM).

Responses are Darckware's own JSON, normalized in the route module -- there
is no ForgeHub table behind this domain, so there is no ORM shape to mirror.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
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
    #: Time spent on the solution (2026-10-04: a resolved demand consumes the
    #: client's quota). Required; 0 only for an item with no client (a lead's
    #: demand has no quota to consume).
    minutes: int = Field(..., ge=0, le=24 * 60)
    service_type: Literal["remoto", "presencial"] = "remoto"
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


# ---------------------------------------------------------------------------
# Onda 2 -- contracts and lead conversion
# ---------------------------------------------------------------------------

ContractType = Literal["suporte_horas", "desenvolvimento"]
ContractStatus = Literal["ativo", "suspenso", "encerrado"]


_EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class ClientProfileFields(BaseModel):
    """Company registry kept by Darckware (2026-10-06): CNPJ, trade name, phone, address.
    Darckware validates CNPJ check digits, UF and CEP; an empty string clears the field."""

    cnpj: str | None = Field(default=None, max_length=20)
    trade_name: str | None = Field(default=None, max_length=200)
    company_phone: str | None = Field(default=None, max_length=40)
    address_street: str | None = Field(default=None, max_length=200)
    address_number: str | None = Field(default=None, max_length=20)
    address_complement: str | None = Field(default=None, max_length=100)
    address_district: str | None = Field(default=None, max_length=100)
    address_city: str | None = Field(default=None, max_length=100)
    address_state: str | None = Field(default=None, max_length=2)
    address_zip: str | None = Field(default=None, max_length=10)


class ClientAccountIn(ClientProfileFields):
    """A client registered straight from ForgeHub (no lead). No portal access until issued."""

    company_name: str = Field(..., min_length=1, max_length=200)
    contact_name: str = Field(..., min_length=1, max_length=200)
    email: str = Field(..., max_length=255, pattern=_EMAIL)
    phone: str | None = Field(default=None, max_length=40)
    department: str | None = Field(default=None, max_length=100)


class ClientAccountPatch(ClientProfileFields):
    company_name: str | None = Field(default=None, min_length=1, max_length=200)
    contact_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=255, pattern=_EMAIL)
    phone: str | None = Field(default=None, max_length=40)
    department: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None


class ContractIn(BaseModel):
    contract_type: ContractType = "suporte_horas"
    plan_name: str = Field(..., min_length=1, max_length=100)
    monthly_hours_quota: float | None = Field(default=None, gt=0)
    monthly_price: float | None = Field(default=None, ge=0)
    extra_hour_rate: float | None = Field(default=None, ge=0)
    billing_cycle_day: int | None = Field(default=None, ge=1, le=28)
    start_date: str | None = None
    end_date: str | None = None
    total_value: float | None = Field(default=None, ge=0)
    scope_summary: str | None = None
    document_url: str | None = Field(default=None, max_length=500)


class ContractPatch(BaseModel):
    status: ContractStatus | None = None
    plan_name: str | None = Field(default=None, max_length=100)
    monthly_hours_quota: float | None = Field(default=None, gt=0)
    monthly_price: float | None = Field(default=None, ge=0)
    extra_hour_rate: float | None = Field(default=None, ge=0)
    billing_cycle_day: int | None = Field(default=None, ge=1, le=28)
    start_date: str | None = None
    end_date: str | None = None
    total_value: float | None = Field(default=None, ge=0)
    scope_summary: str | None = None
    document_url: str | None = Field(default=None, max_length=500)


class ConversionData(BaseModel):
    """What the approver confirms (possibly edited from Lara's proposal)."""

    company_name: str | None = Field(default=None, max_length=200)
    contact_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    department: str | None = Field(default=None, max_length=100)
    contract: ContractIn


class ConversionApprove(BaseModel):
    data: ConversionData
    existing_client_account_id: uuid.UUID | None = None


class RegistrationApprove(ClientProfileFields):
    """Approving a client registration an agent asked for, with Marcelo's edits (2026-10-06)."""

    company_name: str | None = Field(default=None, min_length=1, max_length=200)
    contact_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=255, pattern=_EMAIL)
    phone: str | None = Field(default=None, max_length=40)
    department: str | None = Field(default=None, max_length=100)


class ConversionReject(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)


class LeadConvert(BaseModel):
    """Marcelo converting a lead directly from ForgeHub (propose + approve)."""

    data: ConversionData
    notes: str | None = Field(default=None, max_length=2000)
    existing_client_account_id: uuid.UUID | None = None


# ---------------------------------------------------------------------------
# Onda 3 -- Software Factory per client
# ---------------------------------------------------------------------------


class CreateProjectFromItem(BaseModel):
    """Open a Software Factory project for a client ticket/demand.

    Exactly one of `product_id` (an existing product of this client, or one
    not linked to any client yet) and `new_product_name`.
    """

    product_id: uuid.UUID | None = None
    new_product_name: str | None = Field(default=None, min_length=1, max_length=255)
    product_version_id: uuid.UUID | None = None
    project_name: str | None = Field(default=None, min_length=1, max_length=255)
    start_work: bool = True


class LinkProduct(BaseModel):
    product_id: uuid.UUID


# ---------------------------------------------------------------------------
# Onda 4 -- hours and monthly report
# ---------------------------------------------------------------------------


class LogTimeIn(BaseModel):
    start_time: datetime
    end_time: datetime
    description: str = Field(..., min_length=1, max_length=4000)
    service_type: Literal["remoto", "presencial"] = "remoto"


class MonthlyReportIn(BaseModel):
    """`reference`: any day inside the cycle to report (default: yesterday)."""

    reference: date | None = None
