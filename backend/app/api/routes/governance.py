"""Governance domain routes: approvals, audit_events, policies.

Business rules implemented here (SPEC.md section 6, esp. 6.2 Pipeline
Rules and 5.7 Audit and Approval):

- Approvals are created in `pending` status and can only be decided
  (approved/rejected) once. Attempting to decide an already-decided
  approval is a 409 Conflict (rule: gated decisions are final; SPEC
  6.2.10 "Release approval is allowed only when all required gates
  pass" implies a decided gate approval is not silently re-opened).
- Deciding an approval automatically writes a companion AuditEvent
  (event_type "approval_approved"/"approval_rejected") so the decision
  is itself part of the audit trail (SPEC 5.7 "Record audit events for
  every major entity transition").
- AuditEvent is append-only: only create + read endpoints exist (no
  update/delete) to preserve audit integrity (SPEC 6.4.4 "Every task
  completion must be auditable" implies the audit record itself must
  not be mutable after the fact).
- Policy supports full CRUD since it's a governance configuration
  registry, not a transactional log; deactivating (is_active=False) is
  the intended way to retire a policy rather than deleting it, but
  delete is still offered for completeness/test cleanup.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.governance import (
    ApprovalCreate,
    ApprovalDecision,
    ApprovalOut,
    AuditEventCreate,
    AuditEventOut,
    PolicyCreate,
    PolicyOut,
    PolicyUpdate,
)
from app.db.base import get_db
from app.db.models.governance import Approval, AuditEvent, Policy
from app.core.deps import ActorPrincipal, authorize_action, get_actor_principal

router = APIRouter(prefix="/api/v1/governance", tags=["governance"])


# ---------------------------------------------------------------------------
# Approvals (primary entity)
# ---------------------------------------------------------------------------
@router.post("/approvals", response_model=ApprovalOut, status_code=status.HTTP_201_CREATED)
async def create_approval(
    payload: ApprovalCreate, db: AsyncSession = Depends(get_db),
    principal: ActorPrincipal = Depends(get_actor_principal),
) -> Approval:
    await authorize_action(db, principal, "governance.approval.decide")
    if payload.policy_id is not None:
        policy = await db.get(Policy, payload.policy_id)
        if policy is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="policy_id does not reference an existing policy",
            )

    approval = Approval(**payload.model_dump(exclude={"requested_by"}), requested_by=principal.display_name, status="pending")
    db.add(approval)
    await db.commit()
    await db.refresh(approval)

    # Audit the creation of the gated request itself.
    db.add(
        AuditEvent(
            entity_type="approval",
            entity_id=approval.id,
            event_type="approval_requested",
            actor=approval.requested_by,
            payload={
                "target_entity_type": approval.entity_type,
                "target_entity_id": str(approval.entity_id),
                "approval_type": approval.approval_type,
            },
        )
    )
    await db.commit()
    return approval


@router.get("/approvals", response_model=list[ApprovalOut])
async def list_approvals(
    status_filter: str | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[Approval]:
    query = select(Approval)
    if status_filter is not None:
        query = query.where(Approval.status == status_filter)
    if entity_type is not None:
        query = query.where(Approval.entity_type == entity_type)
    if entity_id is not None:
        query = query.where(Approval.entity_id == entity_id)
    result = await db.execute(query.order_by(Approval.created_at.desc()))
    return list(result.scalars().all())


@router.get("/approvals/{approval_id}", response_model=ApprovalOut)
async def get_approval(approval_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Approval:
    approval = await db.get(Approval, approval_id)
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found")
    return approval


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalOut)
async def approve_approval(
    approval_id: uuid.UUID, payload: ApprovalDecision, db: AsyncSession = Depends(get_db),
    principal: ActorPrincipal = Depends(get_actor_principal),
) -> Approval:
    return await _decide_approval(approval_id, payload, "approved", db, principal)


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalOut)
async def reject_approval(
    approval_id: uuid.UUID, payload: ApprovalDecision, db: AsyncSession = Depends(get_db),
    principal: ActorPrincipal = Depends(get_actor_principal),
) -> Approval:
    return await _decide_approval(approval_id, payload, "rejected", db, principal)


async def _decide_approval(
    approval_id: uuid.UUID,
    payload: ApprovalDecision,
    new_status: str,
    db: AsyncSession,
    principal: ActorPrincipal,
) -> Approval:
    await authorize_action(db, principal, "governance.approval.decide")
    approval = await db.get(Approval, approval_id)
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found")

    # Business rule: a decided approval is final and cannot be re-decided.
    if approval.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Approval already {approval.status}; decisions are final",
        )

    approval.status = new_status
    approval.decided_by = principal.display_name
    if payload.comments is not None:
        approval.comments = payload.comments
    await db.commit()
    await db.refresh(approval)

    db.add(
        AuditEvent(
            entity_type="approval",
            entity_id=approval.id,
            event_type=f"approval_{new_status}",
            actor=principal.display_name,
            payload={
                "target_entity_type": approval.entity_type,
                "target_entity_id": str(approval.entity_id),
                "approval_type": approval.approval_type,
                "comments": payload.comments,
            },
        )
    )
    await db.commit()
    return approval


# ---------------------------------------------------------------------------
# Audit Events (read-mostly: create + list/get only, no update/delete)
# ---------------------------------------------------------------------------
@router.post(
    "/audit-events", response_model=AuditEventOut, status_code=status.HTTP_201_CREATED
)
async def create_audit_event(
    payload: AuditEventCreate, db: AsyncSession = Depends(get_db)
) -> AuditEvent:
    event = AuditEvent(**payload.model_dump())
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


@router.get("/audit-events", response_model=list[AuditEventOut])
async def list_audit_events(
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    event_type: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[AuditEvent]:
    query = select(AuditEvent)
    if entity_type is not None:
        query = query.where(AuditEvent.entity_type == entity_type)
    if entity_id is not None:
        query = query.where(AuditEvent.entity_id == entity_id)
    if event_type is not None:
        query = query.where(AuditEvent.event_type == event_type)
    result = await db.execute(query.order_by(AuditEvent.created_at.desc()))
    return list(result.scalars().all())


@router.get("/audit-events/{audit_event_id}", response_model=AuditEventOut)
async def get_audit_event(
    audit_event_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> AuditEvent:
    event = await db.get(AuditEvent, audit_event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit event not found")
    return event


# ---------------------------------------------------------------------------
# Policies (secondary entity: full CRUD, reasonably scoped)
# ---------------------------------------------------------------------------
@router.post("/policies", response_model=PolicyOut, status_code=status.HTTP_201_CREATED)
async def create_policy(payload: PolicyCreate, db: AsyncSession = Depends(get_db)) -> Policy:
    existing = await db.execute(select(Policy).where(Policy.name == payload.name))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A policy with this name already exists",
        )

    policy = Policy(**payload.model_dump())
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return policy


@router.get("/policies", response_model=list[PolicyOut])
async def list_policies(
    is_active: bool | None = None,
    policy_type: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[Policy]:
    query = select(Policy)
    if is_active is not None:
        query = query.where(Policy.is_active == is_active)
    if policy_type is not None:
        query = query.where(Policy.policy_type == policy_type)
    result = await db.execute(query.order_by(Policy.name))
    return list(result.scalars().all())


@router.get("/policies/{policy_id}", response_model=PolicyOut)
async def get_policy(policy_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Policy:
    policy = await db.get(Policy, policy_id)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    return policy


@router.put("/policies/{policy_id}", response_model=PolicyOut)
async def update_policy(
    policy_id: uuid.UUID, payload: PolicyUpdate, db: AsyncSession = Depends(get_db)
) -> Policy:
    policy = await db.get(Policy, policy_id)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")

    updates = payload.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"] != policy.name:
        existing = await db.execute(select(Policy).where(Policy.name == updates["name"]))
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A policy with this name already exists",
            )

    for field, value in updates.items():
        setattr(policy, field, value)

    await db.commit()
    await db.refresh(policy)
    return policy


@router.delete("/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(policy_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    policy = await db.get(Policy, policy_id)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    await db.delete(policy)
    await db.commit()
