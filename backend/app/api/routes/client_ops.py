"""Client demands console -- operates Darckware's CRM (2026-10-04).

Plan: docs/superpowers/plans/2026-10-04-client-demands-darckware.md.
"Darckware guarda, ForgeHub opera": clients, tickets, demands and every
e-mail to a client live in Darckware; this domain has no table of its own
(like foundation.py/system_control.py) and calls Darckware's internal API
through core/darckware_client.py on every request.

Darckware has two intake records for client work -- `Ticket` (opened in the
client portal, contract clients) and `ClientDemand` (opened by Lara, e-mail
or here, including prospects). The screen shows both as one list of *work
items*, each keeping its `kind` and id, with one unified `tipo`
(desenvolvimento|servico) and `stage` over the two status vocabularies.
Mapping is by explicit dicts; an unknown value degrades to the safe default
("servico", "novo") rather than being guessed.

E-mails are never sent from here. Status actions can queue a draft in
Darckware's approval queue, and approving one (`:approve`) uses the
ForgeHub-only approver credential; Darckware sends it as Lara.

Every route is admin-only, and every mutation records an AuditEvent
`(entity_type="darckware_<kind>", entity_id=<Darckware uuid>)`.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.client_ops import (
    ContractIn,
    CreateProjectFromItem,
    LinkProduct,
    ContractPatch,
    ConversionApprove,
    ConversionReject,
    EmailDraftIn,
    LeadConvert,
    OutboundEmailApprove,
    OutboundEmailCreate,
    OutboundEmailReject,
    OutboundEmailUpdate,
    WorkItemAction,
    WorkItemCreate,
    WorkItemKind,
    WorkItemReopen,
    WorkItemResolve,
)
from app.core import darckware_client as dw
from app.core.config import settings
from app.core.deps import get_current_admin
from app.db.base import get_db
from app.db.models.governance import AuditEvent
from app.db.models.notification import Notification
from app.db.models.product import Product, ProductVersion
from app.db.models.project import Project
from app.db.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/client-ops", tags=["client-ops"])

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

#: Darckware ClientDemand.category -> tipo. Anything not listed is service work.
_DEMAND_CATEGORY_TIPO = {
    "desenvolvimento": "desenvolvimento",
    "melhoria": "desenvolvimento",
    "integracao": "desenvolvimento",
    "automacao": "desenvolvimento",
    "dados_relatorios": "desenvolvimento",
    "bug": "desenvolvimento",
}
_TICKET_TYPE_TIPO = {"desenvolvimento": "desenvolvimento", "manutencao": "servico"}

#: Raw status -> unified stage, one dict per Darckware vocabulary.
_STAGE_BY_KIND: dict[str, dict[str, str]] = {
    "ticket": {
        "aberto": "novo",
        "em_andamento": "em_andamento",
        "aguardando_cliente": "aguardando_cliente",
        "resolvido": "resolvido",
        "fechado": "fechado",
    },
    "demand": {
        "aberta": "novo",
        "reaberta": "novo",
        "em_atendimento": "em_andamento",
        "encaminhada": "em_andamento",
        "aguardando_cliente": "aguardando_cliente",
        "resolvida": "resolvido",
        "fechada": "fechado",
        "arquivada": "fechado",
    },
}
STAGES = ("novo", "em_andamento", "aguardando_cliente", "resolvido", "fechado")
OPEN_STAGES = ("novo", "em_andamento", "aguardando_cliente")

#: Action -> raw status, per kind.
_ACTION_STATUS: dict[str, dict[str, str]] = {
    "start": {"ticket": "em_andamento", "demand": "em_atendimento"},
    "wait-customer": {"ticket": "aguardando_cliente", "demand": "aguardando_cliente"},
    "resolve": {"ticket": "resolvido", "demand": "resolvida"},
    "reopen": {"ticket": "aberto", "demand": "reaberta"},
}


def _raw_statuses(kind: str, stages: list[str]) -> list[str]:
    return [raw for raw, stage in _STAGE_BY_KIND[kind].items() if stage in stages]


def _stage(kind: str, raw: str | None) -> str:
    return _STAGE_BY_KIND[kind].get(raw or "", "novo")


def _ticket_item(t: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "ticket",
        "id": t["id"],
        "title": t["title"],
        "description": t.get("description"),
        "client_account_id": t.get("client_account_id"),
        "company_name": t.get("company_name"),
        "tipo": _TICKET_TYPE_TIPO.get(t.get("type") or "", "servico"),
        "raw_type": t.get("type"),
        "category": t.get("category"),
        "status": t.get("status"),
        "stage": _stage("ticket", t.get("status")),
        "priority": t.get("priority"),
        "requester_name": t.get("requester_name"),
        "requester_email": t.get("requester_email"),
        "source": "portal",
        "billable_hours": t.get("total_billable_hours"),
        "created_at": t.get("created_at"),
        "updated_at": t.get("updated_at"),
    }


def _demand_item(d: dict[str, Any], companies: dict[str, str]) -> dict[str, Any]:
    account = d.get("client_account") or {}
    lead = d.get("lead") or {}
    client_id = d.get("client_account_id") or account.get("id")
    return {
        "kind": "demand",
        "id": d["id"],
        "title": d["title"],
        "description": d.get("description"),
        "client_account_id": client_id,
        "company_name": account.get("company_name") or companies.get(client_id or "") or lead.get("company"),
        "tipo": _DEMAND_CATEGORY_TIPO.get(d.get("category") or "", "servico"),
        "raw_type": None,
        "category": d.get("category"),
        "status": d.get("status"),
        "stage": _stage("demand", d.get("status")),
        "priority": d.get("priority"),
        "requester_name": lead.get("name") or account.get("contact_name"),
        "requester_email": lead.get("email") or account.get("email"),
        "source": d.get("source_channel") or "lara",
        "billable_hours": None,
        "created_at": d.get("created_at"),
        "updated_at": d.get("updated_at"),
    }


async def _audit(
    db: AsyncSession, kind: str, item_id: str, event_type: str, user: User, payload: dict[str, Any]
) -> None:
    db.add(
        AuditEvent(
            entity_type=f"darckware_{kind}",
            entity_id=uuid.UUID(item_id),
            event_type=event_type,
            actor=user.username,
            payload=payload,
        )
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Status / clients
# ---------------------------------------------------------------------------


@router.get("/status")
async def integration_status(_admin: User = Depends(get_current_admin)) -> dict[str, Any]:
    """Whether the integration is configured and how much is waiting."""
    if not dw.is_configured():
        return {"configured": False, "reachable": False, "pending_emails": 0}
    try:
        data = await dw.request("GET", "/outbound-emails", params={"status": "aguardando_aprovacao", "limit": 1})
    except HTTPException as exc:
        return {"configured": True, "reachable": False, "error": exc.detail, "pending_emails": 0}
    return {
        "configured": True,
        "reachable": True,
        "approver_configured": bool(settings.DARCKWARE_APPROVER_TOKEN),
        "pending_emails": data.get("total", 0),
        "pending_by_status": data.get("pending", {}),
    }


@router.get("/clients")
async def list_clients(
    search: str | None = None, _admin: User = Depends(get_current_admin)
) -> dict[str, Any]:
    return await dw.request("GET", "/clients", params={"search": search, "limit": 100, "active": True})


@router.get("/clients/{client_id}")
async def get_client(client_id: uuid.UUID, _admin: User = Depends(get_current_admin)) -> dict[str, Any]:
    """Client file: contacts, contracts (with the current cycle's hours), open counts."""
    return await dw.request("GET", f"/clients/{client_id}/summary")


# ---------------------------------------------------------------------------
# Work items (tickets + demands)
# ---------------------------------------------------------------------------


@router.get("/work-items")
async def list_work_items(
    client_account_id: uuid.UUID | None = None,
    kind: WorkItemKind | None = None,
    tipo: str | None = Query(None, pattern="^(desenvolvimento|servico)$"),
    stage: str | None = Query(None, description="One stage, or 'open' for every unfinished stage"),
    _admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    stages = list(OPEN_STAGES) if stage == "open" else ([stage] if stage else None)
    if stages and any(s not in STAGES for s in stages):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"stage must be one of {STAGES} or 'open'")

    def raw_statuses(k: str) -> list[str] | None:
        return _raw_statuses(k, stages) if stages else None

    calls = []
    if kind in (None, "ticket"):
        ticket_status = raw_statuses("ticket")
        calls.append(
            dw.request(
                "GET",
                "/tickets",
                params={
                    "client_account_id": client_account_id,
                    "status": ",".join(ticket_status) if ticket_status else None,
                    "limit": 200,
                },
            )
        )
    if kind in (None, "demand"):
        # Darckware's demand list takes a single status; filter stages here.
        calls.append(dw.request("GET", "/demands", params={"client_account_id": client_account_id, "limit": 200}))
    calls.append(dw.request("GET", "/clients", params={"limit": 100}))
    results = await asyncio.gather(*calls)
    clients = results[-1].get("items", [])
    companies = {c["id"]: c["company_name"] for c in clients}

    items: list[dict[str, Any]] = []
    idx = 0
    if kind in (None, "ticket"):
        items.extend(_ticket_item(t) for t in results[idx].get("items", []))
        idx += 1
    if kind in (None, "demand"):
        demand_status = raw_statuses("demand")
        for d in results[idx].get("items", []):
            if demand_status is not None and d.get("status") not in demand_status:
                continue
            items.append(_demand_item(d, companies))
    if tipo:
        items = [i for i in items if i["tipo"] == tipo]
    items.sort(key=lambda i: i.get("updated_at") or "", reverse=True)

    counts = {s: 0 for s in STAGES}
    for i in items:
        counts[i["stage"]] += 1
    return {"items": items, "total": len(items), "by_stage": counts}


async def _load_item(kind: str, item_id: uuid.UUID) -> dict[str, Any]:
    if kind == "ticket":
        raw = await dw.request("GET", f"/tickets/{item_id}")
        item = _ticket_item(raw)
        item["timeline"] = [
            {"at": c["created_at"], "actor": c["author_label"], "type": c["author_type"], "note": c["body"]}
            for c in raw.get("comments", [])
        ]
        item["time_entries"] = raw.get("time_entries", [])
    else:
        raw = await dw.request("GET", f"/demands/{item_id}")
        item = _demand_item(raw, {})
        item["timeline"] = [
            {"at": e["created_at"], "actor": e["actor"], "type": e["event_type"], "note": e["note"]}
            for e in raw.get("events", [])
        ]
        item["time_entries"] = []
    return item


def _check_kind(kind: str) -> str:
    if kind not in ("ticket", "demand"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown work item kind")
    return kind


@router.get("/work-items/{kind}/{item_id}")
async def get_work_item(
    kind: str, item_id: uuid.UUID, _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    _check_kind(kind)
    item, emails = await asyncio.gather(
        _load_item(kind, item_id),
        dw.request("GET", "/outbound-emails", params={f"{kind}_id": item_id, "limit": 50}),
    )
    item["emails"] = emails.get("items", [])
    project = (
        await db.execute(
            select(Project).where(Project.darckware_origin_type == kind, Project.darckware_origin_id == item_id)
        )
    ).scalars().first()
    item["project"] = _project_row(project) if project else None
    return item


@router.post("/work-items", status_code=status.HTTP_201_CREATED)
async def create_work_item(
    payload: WorkItemCreate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Launch a client demand from ForgeHub -- it is stored in Darckware."""
    actor = f"forgehub:{admin.username}"
    if payload.kind == "ticket":
        created = await dw.request(
            "POST",
            "/tickets",
            json={
                "client_account_id": str(payload.client_account_id),
                "client_contact_id": str(payload.client_contact_id) if payload.client_contact_id else None,
                "title": payload.title,
                "description": payload.description,
                "type": "desenvolvimento" if payload.tipo == "desenvolvimento" else "manutencao",
                "category": "manutencao_software" if payload.tipo == "desenvolvimento" else "suporte_ti",
                "priority": payload.priority,
                "actor": actor,
            },
        )
    else:
        created = await dw.request(
            "POST",
            "/demands",
            json={
                "client_account_id": str(payload.client_account_id),
                "client_contact_id": str(payload.client_contact_id) if payload.client_contact_id else None,
                "title": payload.title,
                "description": payload.description,
                "priority": payload.priority,
                "category": payload.category or ("desenvolvimento" if payload.tipo == "desenvolvimento" else "suporte"),
                "source_channel": "forgehub",
                "created_by_agent": actor,
            },
        )
    await _audit(db, payload.kind, created["id"], "created", admin, {"title": payload.title, "tipo": payload.tipo})
    return await _load_item(payload.kind, uuid.UUID(created["id"]))


async def _queue_email(
    kind: str, item: dict[str, Any], draft: EmailDraftIn, email_kind: str, actor: str
) -> dict[str, Any]:
    to_email = (draft.to_email or item.get("requester_email") or "").strip()
    if not to_email:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No recipient: this item has no requester e-mail")
    return await dw.request(
        "POST",
        "/outbound-emails",
        json={
            "to_email": to_email,
            "subject": draft.subject,
            "body_text": draft.body_text,
            "kind": email_kind,
            "client_account_id": item.get("client_account_id"),
            f"{kind}_id": item["id"],
            "source_system": "forgehub",
            "source_ref": f"{kind}:{item['id']}",
            "created_by": actor,
        },
    )


async def _set_status(kind: str, item_id: uuid.UUID, raw_status: str, note: str | None, actor: str) -> None:
    path = f"/tickets/{item_id}" if kind == "ticket" else f"/demands/{item_id}"
    await dw.request("PATCH", path, json={"status": raw_status, "note": note, "actor": actor})


async def _transition(
    kind: str,
    item_id: uuid.UUID,
    action: str,
    note: str | None,
    draft: EmailDraftIn | None,
    email_kind: str,
    admin: User,
    db: AsyncSession,
) -> dict[str, Any]:
    """Status change plus an optional queued e-mail, in the safe order.

    The e-mail is queued first: Darckware validates the recipient there, and
    a refused recipient should block the action rather than leave the item
    "waiting for the customer" with nothing actually sent to them. If the
    status change then fails, the queued draft is cancelled.
    """
    _check_kind(kind)
    actor = f"forgehub:{admin.username}"
    item = await _load_item(kind, item_id)
    queued: dict[str, Any] | None = None
    if draft is not None:
        queued = await _queue_email(kind, item, draft, email_kind, actor)
    try:
        await _set_status(kind, item_id, _ACTION_STATUS[action][kind], note, actor)
    except HTTPException:
        if queued is not None:
            try:
                await dw.request("POST", f"/outbound-emails/{queued['id']}/cancel")
            except HTTPException:
                logger.warning("Could not cancel e-mail %s after a failed transition", queued["id"])
        raise
    await _audit(
        db,
        kind,
        str(item_id),
        action,
        admin,
        {"from": item["status"], "note": note, "email_id": queued["id"] if queued else None},
    )
    updated = await _load_item(kind, item_id)
    updated["queued_email"] = queued
    return updated


@router.post("/work-items/{kind}/{item_id}:start")
async def start_work_item(
    kind: str,
    item_id: uuid.UUID,
    payload: WorkItemAction,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _transition(kind, item_id, "start", payload.note, payload.email, "outro", admin, db)


@router.post("/work-items/{kind}/{item_id}:wait-customer")
async def wait_customer(
    kind: str,
    item_id: uuid.UUID,
    payload: WorkItemAction,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Pause on the customer; the optional e-mail asks them for what's missing."""
    return await _transition(kind, item_id, "wait-customer", payload.note, payload.email, "pendencia", admin, db)


@router.post("/work-items/{kind}/{item_id}:resolve")
async def resolve_work_item(
    kind: str,
    item_id: uuid.UUID,
    payload: WorkItemResolve,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """"Dar baixa": record the resolution; the optional e-mail reports it."""
    email_kind = "solucao"
    if kind == "ticket":
        current = await _load_item(kind, item_id)
        if current["tipo"] == "servico":
            email_kind = "servico_realizado"
    return await _transition(
        kind, item_id, "resolve", f"Resolução: {payload.resolution}", payload.email, email_kind, admin, db
    )


@router.post("/work-items/{kind}/{item_id}:reopen")
async def reopen_work_item(
    kind: str,
    item_id: uuid.UUID,
    payload: WorkItemReopen,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _transition(kind, item_id, "reopen", f"Reaberto: {payload.reason}", None, "outro", admin, db)


# ---------------------------------------------------------------------------
# Outbound e-mail approval
# ---------------------------------------------------------------------------


@router.get("/emails")
async def list_emails(
    status_filter: str | None = Query(None, alias="status"),
    client_account_id: uuid.UUID | None = None,
    limit: int = Query(100, ge=1, le=200),
    _admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    return await dw.request(
        "GET",
        "/outbound-emails",
        params={"status": status_filter, "client_account_id": client_account_id, "limit": limit},
    )


@router.get("/emails/{email_id}")
async def get_email(email_id: uuid.UUID, _admin: User = Depends(get_current_admin)) -> dict[str, Any]:
    return await dw.request("GET", f"/outbound-emails/{email_id}")


@router.post("/emails", status_code=status.HTTP_201_CREATED)
async def create_email(
    payload: OutboundEmailCreate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    body = payload.model_dump(mode="json")
    body.update(source_system="forgehub", created_by=f"forgehub:{admin.username}")
    created = await dw.request("POST", "/outbound-emails", json=body)
    await _audit(db, "email", created["id"], "created", admin, {"to": created["to_email"], "kind": created["kind"]})
    return created


@router.patch("/emails/{email_id}")
async def update_email(
    email_id: uuid.UUID,
    payload: OutboundEmailUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Edit the text -- Darckware bumps the version and voids any approval."""
    updated = await dw.request("PATCH", f"/outbound-emails/{email_id}", json=payload.model_dump(exclude_unset=True))
    await _audit(db, "email", str(email_id), "edited", admin, {"version": updated["version"]})
    return updated


@router.post("/emails/{email_id}:approve")
async def approve_email(
    email_id: uuid.UUID,
    payload: OutboundEmailApprove,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    approved = await dw.request(
        "POST",
        f"/outbound-emails/{email_id}/approve",
        credential="approver",
        json={"version": payload.version, "body_hash": payload.body_hash, "approved_by": admin.username},
    )
    await _audit(
        db, "email", str(email_id), "approved", admin, {"version": payload.version, "body_hash": payload.body_hash}
    )
    return approved


@router.post("/emails/{email_id}:reject")
async def reject_email(
    email_id: uuid.UUID,
    payload: OutboundEmailReject,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rejected = await dw.request(
        "POST",
        f"/outbound-emails/{email_id}/reject",
        credential="approver",
        json={"reason": payload.reason, "rejected_by": admin.username},
    )
    await _audit(db, "email", str(email_id), "rejected", admin, {"reason": payload.reason})
    return rejected


@router.post("/emails/{email_id}:cancel")
async def cancel_email(
    email_id: uuid.UUID,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    cancelled = await dw.request("POST", f"/outbound-emails/{email_id}/cancel")
    await _audit(db, "email", str(email_id), "cancelled", admin, {})
    return cancelled


# ---------------------------------------------------------------------------
# Contracts and lead conversion (Onda 2)
#
# Contract writes and conversion decisions are commercial decisions, so they go
# through the approver credential like e-mail approval. Lara can only propose a
# conversion (Darckware's agent route); approving one creates the client, its
# primary contact, the contract and a welcome e-mail draft -- which still waits
# in the e-mail queue for its own approval.
# ---------------------------------------------------------------------------


def _conversion_body(data: Any) -> dict[str, Any]:
    body = data.model_dump(exclude_none=True)
    body["contract"] = data.contract.model_dump(exclude_none=True)
    return body


@router.post("/clients/{client_id}/contracts", status_code=status.HTTP_201_CREATED)
async def create_contract(
    client_id: uuid.UUID,
    payload: ContractIn,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    created = await dw.request(
        "POST",
        f"/clients/{client_id}/contracts",
        credential="approver",
        json={**payload.model_dump(exclude_none=True), "created_by": admin.username},
    )
    await _audit(db, "contract", created["id"], "created", admin, {"client_id": str(client_id), **payload.model_dump(exclude_none=True)})
    return created


@router.patch("/contracts/{contract_id}")
async def update_contract(
    contract_id: uuid.UUID,
    payload: ContractPatch,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    changes = payload.model_dump(exclude_unset=True)
    updated = await dw.request("PATCH", f"/contracts/{contract_id}", credential="approver", json=changes)
    await _audit(db, "contract", str(contract_id), "updated", admin, changes)
    return updated


@router.get("/conversions")
async def list_conversions(
    status_filter: str | None = Query("proposta", alias="status"),
    _admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    return await dw.request("GET", "/conversion-proposals", params={"status": status_filter or None})


@router.get("/conversions/{proposal_id}")
async def get_conversion(proposal_id: uuid.UUID, _admin: User = Depends(get_current_admin)) -> dict[str, Any]:
    return await dw.request("GET", f"/conversion-proposals/{proposal_id}")


async def _approve_conversion(
    proposal_id: str, data: Any, existing: uuid.UUID | None, admin: User, db: AsyncSession
) -> dict[str, Any]:
    result = await dw.request(
        "POST",
        f"/conversion-proposals/{proposal_id}/approve",
        credential="approver",
        json={
            "decided_by": admin.username,
            "overrides": _conversion_body(data),
            "existing_client_account_id": str(existing) if existing else None,
        },
    )
    await _audit(
        db,
        "conversion",
        proposal_id,
        "approved",
        admin,
        {"client_account_id": result["client_account_id"], "contract_id": result["contract"]["id"], "welcome_email_id": result["welcome_email_id"]},
    )
    return result


@router.post("/conversions/{proposal_id}:approve")
async def approve_conversion(
    proposal_id: uuid.UUID,
    payload: ConversionApprove,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Approve the conversion as shown (with any edits) -- Darckware does it atomically."""
    return await _approve_conversion(str(proposal_id), payload.data, payload.existing_client_account_id, admin, db)


@router.post("/conversions/{proposal_id}:reject")
async def reject_conversion(
    proposal_id: uuid.UUID,
    payload: ConversionReject,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rejected = await dw.request(
        "POST",
        f"/conversion-proposals/{proposal_id}/reject",
        credential="approver",
        json={"decided_by": admin.username, "reason": payload.reason},
    )
    await _audit(db, "conversion", str(proposal_id), "rejected", admin, {"reason": payload.reason})
    return rejected


@router.get("/leads")
async def list_leads(search: str | None = None, _admin: User = Depends(get_current_admin)) -> dict[str, Any]:
    return await dw.request("GET", "/leads", params={"search": search, "limit": 50})


@router.post("/leads/{lead_id}:convert")
async def convert_lead(
    lead_id: uuid.UUID,
    payload: LeadConvert,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Marcelo launches the conversion himself: propose (as ForgeHub) then approve.

    Two Darckware calls, but nothing is created by the first one -- if the
    approval fails, the proposal is left pending in the list for a retry, not
    a half-made client.
    """
    proposal = await dw.request(
        "POST",
        f"/leads/{lead_id}/conversion-proposals",
        json={**_conversion_body(payload.data), "notes": payload.notes, "proposed_by": f"forgehub:{admin.username}"},
    )
    return await _approve_conversion(proposal["id"], payload.data, payload.existing_client_account_id, admin, db)


# ---------------------------------------------------------------------------
# Software Factory per client (Onda 3)
#
# Products and projects carry the Darckware client id (no FK -- other
# database). Opening a project from a ticket/demand reuses the product and
# project routes' own functions, so rule 6.1.3 (a product is never persisted
# without a version) and the client inheritance in create_project hold here
# exactly as they do for the Cockpit's buttons.
# ---------------------------------------------------------------------------


def _product_row(p: Product) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "name": p.name,
        "status": p.status,
        "darckware_client_id": str(p.darckware_client_id) if p.darckware_client_id else None,
        "darckware_client_name": p.darckware_client_name,
    }


def _project_row(p: Project) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "name": p.name,
        "status": p.status,
        "product_version_id": str(p.product_version_id),
        "darckware_origin_type": p.darckware_origin_type,
        "darckware_origin_id": str(p.darckware_origin_id) if p.darckware_origin_id else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


@router.get("/clients/{client_id}/factory")
async def client_factory(
    client_id: uuid.UUID, _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """This client's products and projects in the Software Factory (ForgeHub's own data)."""
    products = (
        await db.execute(select(Product).where(Product.darckware_client_id == client_id).order_by(Product.name))
    ).scalars().all()
    projects = (
        await db.execute(
            select(Project).where(Project.darckware_client_id == client_id).order_by(Project.created_at.desc())
        )
    ).scalars().all()
    unlinked = (
        await db.execute(select(Product).where(Product.darckware_client_id.is_(None)).order_by(Product.name))
    ).scalars().all()
    return {
        "products": [_product_row(p) for p in products],
        "projects": [_project_row(p) for p in projects],
        "unlinked_products": [_product_row(p) for p in unlinked],
    }


async def _link_product(db: AsyncSession, product: Product, client_id: uuid.UUID, company_name: str | None) -> None:
    if product.darckware_client_id not in (None, client_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Product '{product.name}' already belongs to another client ({product.darckware_client_name})",
        )
    product.darckware_client_id = client_id
    product.darckware_client_name = company_name


@router.post("/clients/{client_id}/products")
async def link_product_to_client(
    client_id: uuid.UUID,
    payload: LinkProduct,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Mark an existing product as built for this client. Its projects without a
    client inherit it too (they were created before the link existed)."""
    client = await dw.request("GET", f"/clients/{client_id}/summary")
    product = await db.get(Product, payload.product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    await _link_product(db, product, client_id, client["company_name"])
    projects = (
        await db.execute(
            select(Project)
            .join(ProductVersion, ProductVersion.id == Project.product_version_id)
            .where(ProductVersion.product_id == product.id, Project.darckware_client_id.is_(None))
        )
    ).scalars().all()
    for project in projects:
        project.darckware_client_id = client_id
    db.add(
        AuditEvent(
            entity_type="product",
            entity_id=product.id,
            event_type="darckware_client_linked",
            actor=admin.username,
            payload={"client_id": str(client_id), "projects_updated": len(projects)},
        )
    )
    await db.commit()
    return _product_row(product)


@router.post("/work-items/{kind}/{item_id}:create-project", status_code=status.HTTP_201_CREATED)
async def create_project_from_item(
    kind: str,
    item_id: uuid.UUID,
    payload: CreateProjectFromItem,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Open a Software Factory project for this ticket/demand.

    Idempotent per origin: a second call returns 409 naming the project that
    already exists, so a double click never opens two projects for one demand.
    """
    from app.api.routes.product import create_product
    from app.api.routes.project import create_project
    from app.api.schemas.product import ProductCreate
    from app.api.schemas.project import ProjectCreate

    _check_kind(kind)
    if (payload.product_id is None) == (payload.new_product_name is None):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Give exactly one of product_id or new_product_name")
    item = await _load_item(kind, item_id)
    if not item.get("client_account_id"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "This demand has no client yet (it came from a lead) -- convert the lead to a client first",
        )
    client_id = uuid.UUID(item["client_account_id"])

    existing = (
        await db.execute(
            select(Project).where(Project.darckware_origin_type == kind, Project.darckware_origin_id == item_id)
        )
    ).scalars().first()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Project '{existing.name}' ({existing.id}) already exists for this {kind}")

    if payload.product_id is not None:
        product = await db.get(Product, payload.product_id)
        if product is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
        await _link_product(db, product, client_id, item.get("company_name"))
        await db.commit()
    else:
        product = await create_product(
            ProductCreate(
                name=payload.new_product_name,
                description=f"Produto do cliente {item.get('company_name') or ''}".strip(),
                darckware_client_id=client_id,
                darckware_client_name=item.get("company_name"),
            ),
            db,
        )

    versions = (
        await db.execute(
            select(ProductVersion)
            .where(ProductVersion.product_id == product.id)
            .order_by(ProductVersion.created_at.desc())
        )
    ).scalars().all()
    if payload.product_version_id is not None:
        version = next((v for v in versions if v.id == payload.product_version_id), None)
        if version is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Version does not belong to this product")
    else:
        # A published version is locked for scope/planning edits; prefer one that isn't.
        version = next((v for v in versions if v.status not in ("published", "deprecated")), None)
        if version is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Every version of this product is published -- create a new version in the Cockpit, then pick it",
            )

    description = "\n\n".join(
        part
        for part in (
            item.get("description"),
            f"Origem: {'chamado' if kind == 'ticket' else 'demanda'} Darckware {item_id} — {item['title']}",
        )
        if part
    )
    project = await create_project(
        ProjectCreate(
            name=payload.project_name or item["title"][:255],
            description=description,
            product_version_id=version.id,
            owner=admin.username,
            darckware_client_id=client_id,
            darckware_origin_type=kind,
            darckware_origin_id=item_id,
        ),
        db,
    )

    actor = f"forgehub:{admin.username}"
    note = f"Projeto '{project.name}' aberto na Software Factory do ForgeHub ({project.id})."
    if payload.start_work and item["stage"] == "novo":
        await _set_status(kind, item_id, _ACTION_STATUS["start"][kind], note, actor)
    elif kind == "ticket":
        await dw.request("POST", f"/tickets/{item_id}/comments", json={"body": note, "actor": actor})
    else:
        await dw.request("POST", f"/demands/{item_id}/notes", json={"note": note, "actor": actor})
    await _audit(
        db, kind, str(item_id), "project_created", admin, {"project_id": str(project.id), "product_id": str(product.id)}
    )
    return {"project": _project_row(project), "product": _product_row(product)}


# ---------------------------------------------------------------------------
# Notification pass (background loop in main.py)
# ---------------------------------------------------------------------------


async def run_client_ops_notification_pass(db: AsyncSession) -> int:
    """Surface Darckware arrivals in ForgeHub's bell, once each.

    New tickets/demands, e-mails waiting for approval and lead conversion
    proposals become a
    `Notification(source="system")`, deduplicated by `event_key` (an e-mail
    key carries its version: an edited text needs a fresh look). Silent
    no-op when the integration isn't configured; an unreachable Darckware
    raises so the loop logs it rather than reporting "nothing new".
    """
    if not dw.is_configured():
        return 0
    emails, tickets, demands, conversions = await asyncio.gather(
        dw.request("GET", "/outbound-emails", params={"status": "aguardando_aprovacao", "limit": 200}),
        dw.request("GET", "/tickets", params={"status": "aberto", "limit": 200}),
        dw.request("GET", "/demands", params={"status": "aberta", "limit": 200}),
        dw.request("GET", "/conversion-proposals", params={"status": "proposta", "limit": 200}),
    )
    now = datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []
    for e in emails.get("items", []):
        rows.append(
            {
                "event_key": f"darckware:email:{e['id']}:v{e['version']}",
                "severity": "warning",
                "title": "E-mail ao cliente aguardando aprovação",
                "message": f"{e['subject']} → {e['to_email']}",
            }
        )
    for t in tickets.get("items", []):
        rows.append(
            {
                "event_key": f"darckware:ticket:{t['id']}",
                "severity": "info",
                "title": "Novo chamado de cliente",
                "message": f"{t.get('company_name') or ''}: {t['title']}".strip(": "),
            }
        )
    for d in demands.get("items", []):
        rows.append(
            {
                "event_key": f"darckware:demand:{d['id']}",
                "severity": "info",
                "title": "Nova demanda de cliente",
                "message": d["title"],
            }
        )
    for c in conversions.get("items", []):
        rows.append(
            {
                "event_key": f"darckware:conversion:{c['id']}",
                "severity": "warning",
                "title": "Lead pronto para virar cliente",
                "message": f"{c['payload'].get('company_name') or ''} — proposto por {c['proposed_by']}".strip(" —"),
            }
        )
    if not rows:
        return 0
    stmt = (
        pg_insert(Notification)
        .values(
            [
                {"id": uuid.uuid4(), "source": "system", "occurred_at": now, **row}
                for row in rows
            ]
        )
        .on_conflict_do_nothing(index_elements=["event_key"])
        .returning(Notification.id)
    )
    inserted = (await db.execute(stmt)).scalars().all()
    await db.commit()
    return len(inserted)
