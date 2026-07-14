"""Governed approval, delegation, and agent-principal endpoints."""
import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.governed_approval import (
    AgentCredentialCreate, AgentCredentialIssued, ApprovalRequestOut,
    DelegationCreate, DelegationOut, GovernedDecisionIn, GovernedDecisionOut, PolicyEvaluationOut,
)
from app.core.deps import ActorPrincipal, authorize_action, get_actor_principal
from app.core.governed_approval import decide_concept_approval
from app.db.base import AsyncSessionLocal, get_db
from app.db.models.agent import Agent, AgentServiceCredential
from app.db.models.governance import ApprovalRequest, AuthorityDelegation, AuditEvent, PolicyEvaluation
from app.db.models.notification import Notification
from app.db.models.profile import SENSITIVE_ACTIONS

router = APIRouter(prefix="/api/v1/governed", tags=["governed-approval"])
logger = logging.getLogger(__name__)


@router.get("/policy-evaluations/{evaluation_id}", response_model=PolicyEvaluationOut)
async def get_policy_evaluation(
    evaluation_id: uuid.UUID, db: AsyncSession = Depends(get_db),
    principal: ActorPrincipal = Depends(get_actor_principal),
):
    await authorize_action(db, principal, "governance.approval.view")
    evaluation = await db.get(PolicyEvaluation, evaluation_id)
    if not evaluation:
        raise HTTPException(404, "Policy evaluation not found")
    return evaluation


@router.get("/approval-requests", response_model=list[ApprovalRequestOut])
async def list_requests(
    status_filter: str | None = None, db: AsyncSession = Depends(get_db),
    principal: ActorPrincipal = Depends(get_actor_principal),
):
    await authorize_action(db, principal, "governance.approval.view")
    query = select(ApprovalRequest)
    if status_filter:
        query = query.where(ApprovalRequest.status == status_filter)
    return list((await db.execute(query.order_by(ApprovalRequest.created_at.desc()))).scalars())


@router.get("/approval-requests/{request_id}", response_model=ApprovalRequestOut)
async def get_request(
    request_id: uuid.UUID, db: AsyncSession = Depends(get_db),
    principal: ActorPrincipal = Depends(get_actor_principal),
):
    await authorize_action(db, principal, "governance.approval.view")
    request = await db.get(ApprovalRequest, request_id)
    if not request:
        raise HTTPException(404, "Approval request not found")
    return request


@router.post("/approval-requests/{request_id}:decide", response_model=GovernedDecisionOut)
async def decide_request(
    request_id: uuid.UUID, payload: GovernedDecisionIn,
    db: AsyncSession = Depends(get_db), principal: ActorPrincipal = Depends(get_actor_principal),
):
    request = await db.get(ApprovalRequest, request_id)
    if not request:
        raise HTTPException(404, "Approval request not found")
    if request.target_type != "product_concept":
        raise HTTPException(422, "Unsupported governed target type")
    decision = await decide_concept_approval(
        db, principal, request, payload.decision, payload.comments, payload.idempotency_key
    )
    await db.commit()
    await db.refresh(decision)
    # Notification is intentionally post-commit and best-effort: a delivery
    # failure must never revert or duplicate the governed decision.
    try:
        async with AsyncSessionLocal() as notify_db:
            event_key = f"approval:decision:{request.id}"
            exists = await notify_db.scalar(select(Notification.id).where(Notification.event_key == event_key))
            if not exists:
                notify_db.add(Notification(
                    source="system", severity="success" if payload.decision == "approved" else "warning",
                    title=f"Concept {payload.decision.replace('_', ' ')}",
                    message=f"{principal.display_name} decided approval request {request.id}.",
                    event_key=event_key, occurred_at=datetime.now(timezone.utc),
                ))
                await notify_db.commit()
    except Exception:
        logger.exception("Governed decision persisted but notification delivery failed")
    return decision


@router.get("/authority-delegations", response_model=list[DelegationOut])
async def list_delegations(
    db: AsyncSession = Depends(get_db), principal: ActorPrincipal = Depends(get_actor_principal),
):
    await authorize_action(db, principal, "governance.delegation.manage")
    return list((await db.execute(select(AuthorityDelegation).order_by(
        AuthorityDelegation.created_at.desc()
    ))).scalars())


@router.post("/authority-delegations", response_model=DelegationOut, status_code=201)
async def grant_delegation(
    payload: DelegationCreate, db: AsyncSession = Depends(get_db),
    principal: ActorPrincipal = Depends(get_actor_principal),
):
    await authorize_action(db, principal, "governance.delegation.manage")
    if principal.principal_type != "user":
        raise HTTPException(403, "Only a user can grant authority")
    unknown = sorted(set(payload.allowed_actions) - set(SENSITIVE_ACTIONS))
    if unknown:
        raise HTTPException(422, {"message": "Unknown delegated actions", "actions": unknown})
    for action in payload.allowed_actions:
        await authorize_action(db, principal, action, product_id=payload.product_id, project_id=payload.project_id)
    agent = await db.get(Agent, payload.grantee_agent_id)
    if not agent or not agent.is_active:
        raise HTTPException(422, "Active grantee agent not found")
    now = datetime.now(timezone.utc)
    valid_from = payload.valid_from or now
    if payload.expires_at <= valid_from:
        raise HTTPException(422, "expires_at must be after valid_from")
    delegation = AuthorityDelegation(
        grantor_user_id=principal.principal_id, grantee_type="agent",
        grantee_id=agent.id, valid_from=valid_from,
        **payload.model_dump(exclude={"grantee_agent_id", "valid_from"}),
    )
    db.add(delegation)
    await db.flush()
    db.add(AuditEvent(entity_type="authority_delegation", entity_id=delegation.id,
                      event_type="delegation_granted", actor=principal.display_name,
                      payload={"agent_id": str(agent.id), "actions": payload.allowed_actions}))
    db.add(Notification(
        source="system", severity="info", title="Athos authority granted",
        message=f"{principal.display_name} granted {agent.name} a mandate until {payload.expires_at.isoformat()}.",
        event_key=f"delegation:granted:{delegation.id}", occurred_at=now,
    ))
    await db.commit()
    await db.refresh(delegation)
    return delegation


@router.post("/authority-delegations/{delegation_id}:revoke", response_model=DelegationOut)
async def revoke_delegation(
    delegation_id: uuid.UUID, db: AsyncSession = Depends(get_db),
    principal: ActorPrincipal = Depends(get_actor_principal),
):
    await authorize_action(db, principal, "governance.delegation.manage")
    delegation = await db.get(AuthorityDelegation, delegation_id)
    if not delegation:
        raise HTTPException(404, "Delegation not found")
    if not principal.is_admin and delegation.grantor_user_id != principal.principal_id:
        raise HTTPException(403, "Only the grantor or admin can revoke this delegation")
    delegation.status = "revoked"
    delegation.revoked_at = datetime.now(timezone.utc)
    db.add(AuditEvent(entity_type="authority_delegation", entity_id=delegation.id,
                      event_type="delegation_revoked", actor=principal.display_name))
    db.add(Notification(
        source="system", severity="warning", title="Agent authority revoked",
        message=f"{principal.display_name} revoked delegation {delegation.id}.",
        event_key=f"delegation:revoked:{delegation.id}", occurred_at=delegation.revoked_at,
    ))
    await db.commit()
    await db.refresh(delegation)
    return delegation


@router.post("/agent-credentials", response_model=AgentCredentialIssued, status_code=status.HTTP_201_CREATED)
async def issue_agent_credential(
    payload: AgentCredentialCreate, db: AsyncSession = Depends(get_db),
    principal: ActorPrincipal = Depends(get_actor_principal),
):
    if not principal.is_admin:
        raise HTTPException(403, "Admin access required")
    agent = await db.get(Agent, payload.agent_id)
    if not agent or not agent.is_active:
        raise HTTPException(422, "Active agent not found")
    token = f"agt_{secrets.token_urlsafe(32)}"
    credential = AgentServiceCredential(
        agent_id=agent.id, label=payload.label,
        token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=payload.expires_at,
    )
    db.add(credential)
    await db.commit()
    await db.refresh(credential)
    return AgentCredentialIssued(
        credential_id=credential.id, agent_id=agent.id, token=token, expires_at=credential.expires_at
    )


@router.post("/agent-credentials/{credential_id}:revoke", status_code=204)
async def revoke_agent_credential(
    credential_id: uuid.UUID, db: AsyncSession = Depends(get_db),
    principal: ActorPrincipal = Depends(get_actor_principal),
):
    if not principal.is_admin:
        raise HTTPException(403, "Admin access required")
    credential = await db.get(AgentServiceCredential, credential_id)
    if not credential:
        raise HTTPException(404, "Agent credential not found")
    credential.revoked_at = datetime.now(timezone.utc)
    db.add(AuditEvent(entity_type="agent_service_credential", entity_id=credential.id,
                      event_type="credential_revoked", actor=principal.display_name))
    await db.commit()
