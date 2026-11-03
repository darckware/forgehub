"""Mission planning records (Plano Integrado M0.0b).

Contract: docs/architecture/MCP_MISSION_TOOLS_SPEC.md §2.6. The records the
P1-P8 exit conditions and the dossier transition read (`core/mission_records.py`):

- ``POST /api/v1/missions/{id}/plans``                              register a plan version (author = caller)
- ``POST /api/v1/missions/{id}/plan-reviews``                       per-layer (P3) or cross (P5) opinion, agent only
- ``POST /api/v1/missions/{id}/plan-reviews/{review_id}/items``     what a review raised, its reviewer only
- ``POST /api/v1/missions/{id}/review-items/{item_id}:dispose``     disposition + reason (P4)
- ``POST /api/v1/missions/{id}/review-items/{item_id}:decide``      Marcelo's decision (P6), admin JWT only
- ``POST /api/v1/missions/{id}/review-waivers``                     Marcelo: a layer goes without an opinion
- ``POST /api/v1/missions/{id}/plan-verifications``                 sampled verification (P7), agent only
- ``POST /api/v1/missions/{id}/dossier``                            dossier version + hash (§8 item 1)
- ``GET  /api/v1/missions/{id}/planning-records``                   the current version's records

The reviewer, verifier and decider are always the authenticated principal:
no body field names them (the schemas forbid extra fields). Every write
appends ``AuditEvent(entity_type="mission")``.
"""
import uuid
from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.mission import _audit_payload, _load
from app.api.schemas.mission import (
    DossierCreate,
    DossierOut,
    MissionPlanCreate,
    MissionPlanVersionOut,
    PlanningRecordsOut,
    PlanReviewCreate,
    PlanReviewOut,
    PlanVerificationCreate,
    PlanVerificationOut,
    ReviewItemCreate,
    ReviewItemDecideIn,
    ReviewItemDisposeIn,
    ReviewItemOut,
    ReviewWaiverCreate,
    ReviewWaiverOut,
)
from app.core.deps import ActorPrincipal, authorize_action, get_actor_principal
from app.core.mission import mission_error, utcnow
from app.core.mission_records import (
    APPLIED_DISPOSITIONS,
    current_plan,
    is_planner,
    plan_items,
    required_sample_size,
)
from app.db.base import get_db
from app.db.models.artifact import ArtifactVersion
from app.db.models.governance import AuditEvent
from app.db.models.mission import (
    MissionDossier,
    MissionPlanReview,
    MissionPlanVerification,
    MissionPlanVersion,
    MissionReviewItem,
    MissionReviewWaiver,
    ProjectMission,
)
from app.db.models.orchestration import ProjectAgentMembership
from app.db.models.project import ProjectPlan

router = APIRouter(prefix="/api/v1/missions", tags=["missions"])

STAGE_BY_REVIEW_KIND = {"layer": "critical_review", "cross": "cross_review"}
DISPOSITION_STAGES = ("consolidation", "cross_review", "decisions")


def _audit(project_id: uuid.UUID, event_type: str, principal: ActorPrincipal, source: str, delegation,
           **extra: Any) -> AuditEvent:
    return AuditEvent(entity_type="mission", entity_id=project_id, event_type=event_type,
                      actor=principal.display_name,
                      payload=_audit_payload(principal, source, delegation, **extra))


def _assert_planning(mission: ProjectMission, *stages: str) -> None:
    if mission.state != "planning":
        raise mission_error(409, "MISSION_NOT_PLANNING", "Planning records are written only while planning",
                            state=mission.state)
    if stages and mission.planning_stage not in stages:
        raise mission_error(409, "PLANNING_STAGE_MISMATCH", "This record is not written at the current stage",
                            planning_stage=mission.planning_stage, allowed=list(stages))


def _assert_marcelo(principal: ActorPrincipal) -> tuple[str, None]:
    """Marcelo's decision: an authenticated admin user, never an agent token."""
    if principal.principal_type != "user" or not principal.is_admin:
        raise mission_error(403, "MARCELO_DECISION_REQUIRES_ADMIN",
                            "Only Marcelo (an administrator, by JWT) records this decision")
    return "admin", None


async def _authorize_manager(
    db: AsyncSession, principal: ActorPrincipal, mission: ProjectMission, member_action: str | None,
) -> tuple[str, Any]:
    """Admin; the orchestrator with mission.orchestrate; or (when given) an
    active member of the mission with ``member_action``."""
    if principal.principal_type == "user":
        if not principal.is_admin:
            raise mission_error(403, "MISSION_ADMIN_ONLY", "Only an administrator acts on a mission in M0")
        return "admin", None
    if principal.principal_id == mission.orchestrator_agent_id:
        return await authorize_action(db, principal, "mission.orchestrate", project_id=mission.project_id)
    if member_action is not None and await _membership(db, mission.project_id, principal.principal_id):
        return await authorize_action(db, principal, member_action, project_id=mission.project_id)
    raise mission_error(403, "MISSION_ACTOR_NOT_ALLOWED", "This agent may not take this action on the mission")


async def _membership(db: AsyncSession, project_id: uuid.UUID, agent_id: uuid.UUID,
                      *, can_review: bool = False) -> ProjectAgentMembership | None:
    stmt = select(ProjectAgentMembership).where(
        ProjectAgentMembership.project_id == project_id,
        ProjectAgentMembership.agent_id == agent_id,
        ProjectAgentMembership.status == "active",
    )
    if can_review:
        stmt = stmt.where(ProjectAgentMembership.can_review.is_(True))
    today = utcnow().date()
    for membership in (await db.execute(stmt)).scalars():
        if (membership.valid_from is None or membership.valid_from <= today) and (
            membership.valid_to is None or membership.valid_to >= today
        ):
            return membership
    return None


async def _authorize_reviewer(db: AsyncSession, principal: ActorPrincipal, mission: ProjectMission) -> tuple[str, Any]:
    """§2.6: an agent (its own agt_), active can_review member of the mission,
    with mission.plan.review. People don't write opinions; Marcelo waives."""
    if principal.principal_type != "agent":
        raise mission_error(403, "REVIEW_REQUIRES_AGENT",
                            "Reviews and verifications are written by the reviewing agent with its own credential")
    if await _membership(db, mission.project_id, principal.principal_id, can_review=True) is None:
        raise mission_error(403, "REVIEWER_NOT_ELIGIBLE",
                            "The reviewer must be an active member of the mission with can_review")
    return await authorize_action(db, principal, "mission.plan.review", project_id=mission.project_id)


async def _current_version(
    db: AsyncSession, mission: ProjectMission, project_plan_id: uuid.UUID | None = None,
) -> tuple[ProjectPlan, MissionPlanVersion]:
    plan = await current_plan(db, mission.project_id)
    if plan is None:
        raise mission_error(409, "PLAN_DRAFT_MISSING", "No ProjectPlan version in draft for this mission")
    if project_plan_id is not None and project_plan_id != plan.id:
        raise mission_error(409, "PLAN_VERSION_NOT_CURRENT", "Records are written against the current plan version",
                            current_project_plan_id=str(plan.id))
    version = await db.get(MissionPlanVersion, plan.id)
    if version is None:
        raise mission_error(409, "PLAN_VERSION_NOT_REGISTERED",
                            "The newest draft plan has no recorded author; register it through POST /plans",
                            project_plan_id=str(plan.id))
    return plan, version


def _assert_not_planner(mission, version, principal: ActorPrincipal) -> None:
    if is_planner(mission, version, principal.principal_type, principal.principal_id):
        raise mission_error(409, "REVIEWER_IS_PLANNER",
                            "The plan's author and the mission's orchestrator cannot review or verify it")


async def _artifact_version(db: AsyncSession, artifact_version_id: uuid.UUID) -> ArtifactVersion:
    found = await db.get(ArtifactVersion, artifact_version_id)
    if found is None:
        raise mission_error(422, "ARTIFACT_VERSION_NOT_FOUND", "artifact_version_id is not an artifact version")
    return found


async def _item_in_mission(
    db: AsyncSession, mission: ProjectMission, item_id: uuid.UUID,
) -> tuple[MissionReviewItem, MissionPlanReview]:
    item = (await db.execute(
        select(MissionReviewItem).where(MissionReviewItem.id == item_id).with_for_update()
    )).scalar_one_or_none()
    review = await db.get(MissionPlanReview, item.review_id) if item is not None else None
    if item is None or review is None or review.mission_project_id != mission.project_id:
        raise mission_error(404, "REVIEW_ITEM_NOT_FOUND", "Review item not found in this mission")
    return item, review


# ---------------------------------------------------------------------------
# Plan versions
# ---------------------------------------------------------------------------
@router.post("/{project_id}/plans", response_model=MissionPlanVersionOut, status_code=status.HTTP_201_CREATED)
async def register_plan_version(
    project_id: uuid.UUID,
    payload: MissionPlanCreate,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
) -> MissionPlanVersionOut:
    """A new plan version supersedes the older drafts and, while planning,
    sends the pipeline back to draft_plan: the old version's records no longer count."""
    _project, mission = await _load(db, project_id, lock=True)
    source, delegation = await _authorize_manager(db, principal, mission, "mission.plan.submit")
    if mission.state not in ("draft", "planning"):
        raise mission_error(409, "MISSION_NOT_PLANNING", "A plan version is registered only in draft or planning",
                            state=mission.state)
    superseded = list((await db.execute(select(ProjectPlan).where(
        ProjectPlan.project_id == project_id, ProjectPlan.status == "draft",
    ))).scalars())
    for old in superseded:
        old.status = "superseded"
    plan = ProjectPlan(project_id=project_id, status="draft", **payload.model_dump())
    db.add(plan)
    await db.flush()
    version = MissionPlanVersion(project_plan_id=plan.id, mission_project_id=project_id,
                                 author_type=principal.principal_type, author_id=principal.principal_id,
                                 author_name=principal.display_name)
    db.add(version)
    from_stage = mission.planning_stage
    if mission.state == "planning" and from_stage != "draft_plan":
        mission.planning_stage = "draft_plan"
    mission.row_version += 1
    db.add(_audit(project_id, "mission_plan_version_registered", principal, source, delegation,
                  project_plan_id=str(plan.id), superseded=[str(p.id) for p in superseded],
                  from_stage=from_stage, planning_stage=mission.planning_stage))
    await db.commit()
    await db.refresh(plan)
    await db.refresh(version)
    return MissionPlanVersionOut(
        project_plan_id=plan.id, name=plan.name, status=plan.status, author_type=version.author_type,
        author_id=version.author_id, author_name=version.author_name, planning_stage=mission.planning_stage,
        created_at=version.created_at,
    )


# ---------------------------------------------------------------------------
# Reviews (P3 per layer, P5 cross) and their items
# ---------------------------------------------------------------------------
@router.post("/{project_id}/plan-reviews", response_model=PlanReviewOut, status_code=status.HTTP_201_CREATED)
async def record_plan_review(
    project_id: uuid.UUID,
    payload: PlanReviewCreate,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
) -> MissionPlanReview:
    _project, mission = await _load(db, project_id, lock=True)
    source, delegation = await _authorize_reviewer(db, principal, mission)
    _assert_planning(mission, STAGE_BY_REVIEW_KIND[payload.kind])
    plan, version = await _current_version(db, mission, payload.project_plan_id)
    _assert_not_planner(mission, version, principal)
    if payload.kind == "layer" and payload.layer not in (mission.required_review_layers or []):
        raise mission_error(422, "LAYER_NOT_REQUIRED", "This layer is not among the mission's required review layers",
                            layer=payload.layer, required=list(mission.required_review_layers or []))
    await _artifact_version(db, payload.artifact_version_id)
    review = MissionPlanReview(mission_project_id=project_id, project_plan_id=plan.id, kind=payload.kind,
                               layer=payload.layer, reviewer_agent_id=principal.principal_id,
                               artifact_version_id=payload.artifact_version_id, summary=payload.summary)
    db.add(review)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise mission_error(409, "REVIEW_ALREADY_RECORDED",
                            "This reviewer already recorded this review for this plan version") from None
    db.add(_audit(project_id, "mission_plan_review_recorded", principal, source, delegation,
                  review_id=str(review.id), project_plan_id=str(plan.id), kind=review.kind, layer=review.layer,
                  artifact_version_id=str(review.artifact_version_id)))
    await db.commit()
    await db.refresh(review)
    return review


@router.post("/{project_id}/plan-reviews/{review_id}/items", response_model=ReviewItemOut,
             status_code=status.HTTP_201_CREATED)
async def record_review_item(
    project_id: uuid.UUID,
    review_id: uuid.UUID,
    payload: ReviewItemCreate,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
) -> MissionReviewItem:
    _project, mission = await _load(db, project_id, lock=True)
    review = await db.get(MissionPlanReview, review_id)
    if review is None or review.mission_project_id != project_id:
        raise mission_error(404, "REVIEW_NOT_FOUND", "Review not found in this mission")
    source, delegation = await _authorize_reviewer(db, principal, mission)
    if review.reviewer_agent_id != principal.principal_id:
        raise mission_error(403, "NOT_REVIEW_AUTHOR", "Only the review's own reviewer adds items to it")
    _assert_planning(mission, STAGE_BY_REVIEW_KIND[review.kind])
    await _current_version(db, mission, review.project_plan_id)
    if not payload.text.strip():
        raise mission_error(422, "TEXT_REQUIRED", "A review item needs text")
    item = MissionReviewItem(review_id=review.id, text=payload.text,
                             needs_marcelo_decision=payload.needs_marcelo_decision)
    db.add(item)
    await db.flush()
    db.add(_audit(project_id, "mission_review_item_recorded", principal, source, delegation,
                  item_id=str(item.id), review_id=str(review.id),
                  needs_marcelo_decision=item.needs_marcelo_decision))
    await db.commit()
    await db.refresh(item)
    return item


@router.post("/{project_id}/review-items/{item_id}:dispose", response_model=ReviewItemOut)
async def dispose_review_item(
    project_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: ReviewItemDisposeIn,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
) -> MissionReviewItem:
    _project, mission = await _load(db, project_id, lock=True)
    source, delegation = await _authorize_manager(db, principal, mission, None)
    _assert_planning(mission, *DISPOSITION_STAGES)
    item, review = await _item_in_mission(db, mission, item_id)
    await _current_version(db, mission, review.project_plan_id)
    reason = payload.reason.strip()
    if not reason:
        raise mission_error(422, "REASON_REQUIRED", "A disposition needs a reason")
    if item.marcelo_decision is not None:
        raise mission_error(409, "ITEM_ALREADY_DECIDED", "Marcelo already decided this item")
    if payload.needs_marcelo_decision is False and item.needs_marcelo_decision:
        raise mission_error(409, "FLAG_CANNOT_BE_CLEARED", "An item flagged for Marcelo stays flagged")
    before = {"disposition": item.disposition, "needs_marcelo_decision": item.needs_marcelo_decision}
    item.disposition, item.disposition_reason = payload.disposition, reason
    item.disposed_by, item.disposed_at = principal.display_name, utcnow()
    if payload.needs_marcelo_decision:
        item.needs_marcelo_decision = True
    db.add(_audit(project_id, "mission_review_item_disposed", principal, source, delegation,
                  item_id=str(item.id), before=before, disposition=item.disposition, reason=reason,
                  needs_marcelo_decision=item.needs_marcelo_decision))
    await db.commit()
    await db.refresh(item)
    return item


@router.post("/{project_id}/review-items/{item_id}:decide", response_model=ReviewItemOut)
async def decide_review_item(
    project_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: ReviewItemDecideIn,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
) -> MissionReviewItem:
    source, delegation = _assert_marcelo(principal)
    _project, mission = await _load(db, project_id, lock=True)
    _assert_planning(mission, *DISPOSITION_STAGES)
    item, review = await _item_in_mission(db, mission, item_id)
    await _current_version(db, mission, review.project_plan_id)
    reason = payload.reason.strip()
    if not reason:
        raise mission_error(422, "REASON_REQUIRED", "Marcelo's decision needs a reason")
    if not item.needs_marcelo_decision:
        raise mission_error(409, "ITEM_NOT_FLAGGED", "This item was not flagged for Marcelo's decision")
    if item.marcelo_decision is not None:
        raise mission_error(409, "ITEM_ALREADY_DECIDED", "Marcelo already decided this item")
    item.marcelo_decision, item.marcelo_reason = payload.decision, reason
    item.marcelo_decided_by, item.marcelo_user_id = principal.display_name, principal.principal_id
    item.marcelo_decided_at = utcnow()
    db.add(_audit(project_id, "mission_review_item_decided", principal, source, delegation,
                  item_id=str(item.id), decision=item.marcelo_decision, reason=reason))
    await db.commit()
    await db.refresh(item)
    return item


@router.post("/{project_id}/review-waivers", response_model=ReviewWaiverOut, status_code=status.HTTP_201_CREATED)
async def waive_layer_review(
    project_id: uuid.UUID,
    payload: ReviewWaiverCreate,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
) -> MissionReviewWaiver:
    source, delegation = _assert_marcelo(principal)
    _project, mission = await _load(db, project_id, lock=True)
    _assert_planning(mission, "critical_review")
    plan, _version = await _current_version(db, mission, payload.project_plan_id)
    if payload.layer not in (mission.required_review_layers or []):
        raise mission_error(422, "LAYER_NOT_REQUIRED", "This layer is not among the mission's required review layers",
                            layer=payload.layer)
    reason = payload.reason.strip()
    if not reason:
        raise mission_error(422, "REASON_REQUIRED", "A waiver needs a reason")
    waiver = MissionReviewWaiver(mission_project_id=project_id, project_plan_id=plan.id, layer=payload.layer,
                                 reason=reason, decided_by=principal.display_name,
                                 decided_by_user_id=principal.principal_id)
    db.add(waiver)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise mission_error(409, "WAIVER_ALREADY_RECORDED", "This layer is already waived for this plan version") from None
    db.add(_audit(project_id, "mission_review_waived", principal, source, delegation,
                  waiver_id=str(waiver.id), project_plan_id=str(plan.id), layer=waiver.layer, reason=reason))
    await db.commit()
    await db.refresh(waiver)
    return waiver


# ---------------------------------------------------------------------------
# P7 verification and the dossier
# ---------------------------------------------------------------------------
@router.post("/{project_id}/plan-verifications", response_model=PlanVerificationOut,
             status_code=status.HTTP_201_CREATED)
async def record_plan_verification(
    project_id: uuid.UUID,
    payload: PlanVerificationCreate,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
) -> MissionPlanVerification:
    _project, mission = await _load(db, project_id, lock=True)
    source, delegation = await _authorize_reviewer(db, principal, mission)
    _assert_planning(mission, "application")
    plan, version = await _current_version(db, mission, payload.project_plan_id)
    _assert_not_planner(mission, version, principal)
    applied, minimum = required_sample_size(await plan_items(db, plan.id))
    sample = list(dict.fromkeys(payload.sampled_item_ids))
    invalid = [str(i) for i in sample if i not in applied]
    if invalid:
        raise mission_error(409, "SAMPLE_ITEM_INVALID",
                            f"Sampled items must be {'/'.join(APPLIED_DISPOSITIONS)} items of this plan version",
                            item_ids=invalid)
    if len(sample) < minimum:
        raise mission_error(422, "SAMPLE_TOO_SMALL", "The sample is smaller than required",
                            required_sample=minimum, applied_items=len(applied))
    verification = MissionPlanVerification(
        mission_project_id=project_id, project_plan_id=plan.id, verifier_agent_id=principal.principal_id,
        sampled_item_ids=sample, result=payload.result, notes=payload.notes,
    )
    db.add(verification)
    await db.flush()
    db.add(_audit(project_id, "mission_plan_verification_recorded", principal, source, delegation,
                  verification_id=str(verification.id), project_plan_id=str(plan.id), result=verification.result,
                  sampled_item_ids=[str(i) for i in sample]))
    await db.commit()
    await db.refresh(verification)
    return verification


def _checksum_hex(checksum: str | None) -> str | None:
    if not checksum:
        return None
    value = checksum.strip().lower()
    return value.removeprefix("sha256:")


@router.post("/{project_id}/dossier", response_model=DossierOut, status_code=status.HTTP_201_CREATED)
async def register_dossier(
    project_id: uuid.UUID,
    payload: DossierCreate,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
) -> MissionDossier:
    _project, mission = await _load(db, project_id, lock=True)
    source, delegation = await _authorize_manager(db, principal, mission, "mission.dossier.register")
    if mission.state != "verifying":
        raise mission_error(409, "MISSION_NOT_VERIFYING", "The dossier is registered while verifying",
                            state=mission.state)
    artifact_version = await _artifact_version(db, payload.artifact_version_id)
    file_sha256 = payload.file_sha256.lower()
    recorded = _checksum_hex(artifact_version.checksum)
    if recorded is not None and recorded != file_sha256:
        raise mission_error(409, "DOSSIER_HASH_MISMATCH",
                            "file_sha256 differs from the artifact version's recorded checksum")
    dossier = MissionDossier(mission_project_id=project_id, artifact_version_id=artifact_version.id,
                             file_sha256=file_sha256, registered_by_type=principal.principal_type,
                             registered_by_id=principal.principal_id, registered_by=principal.display_name)
    db.add(dossier)
    await db.flush()
    db.add(_audit(project_id, "mission_dossier_registered", principal, source, delegation,
                  dossier_id=str(dossier.id), artifact_version_id=str(artifact_version.id),
                  file_sha256=file_sha256))
    await db.commit()
    await db.refresh(dossier)
    return dossier


@router.get("/{project_id}/planning-records", response_model=PlanningRecordsOut)
async def get_planning_records(
    project_id: uuid.UUID,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
) -> PlanningRecordsOut:
    _project, mission = await _load(db, project_id)
    dossiers = list((await db.execute(select(MissionDossier).where(
        MissionDossier.mission_project_id == project_id).order_by(MissionDossier.created_at))).scalars())
    # The current draft; once baselined/approved, the newest registered version.
    plan = await current_plan(db, project_id) or (await db.execute(
        select(ProjectPlan).join(MissionPlanVersion, MissionPlanVersion.project_plan_id == ProjectPlan.id)
        .where(ProjectPlan.project_id == project_id)
        .order_by(ProjectPlan.created_at.desc(), ProjectPlan.id.desc()).limit(1)
    )).scalars().first()
    if plan is None:
        return PlanningRecordsOut(project_plan_id=None, author=None, reviews=[], items=[], waivers=[],
                                  verifications=[], dossiers=dossiers)
    version = await db.get(MissionPlanVersion, plan.id)
    author = None if version is None else MissionPlanVersionOut(
        project_plan_id=plan.id, name=plan.name, status=plan.status, author_type=version.author_type,
        author_id=version.author_id, author_name=version.author_name, planning_stage=mission.planning_stage,
        created_at=version.created_at,
    )

    async def rows(model, order):
        return list((await db.execute(
            select(model).where(model.project_plan_id == plan.id).order_by(order)
        )).scalars())

    return PlanningRecordsOut(
        project_plan_id=plan.id, author=author,
        reviews=await rows(MissionPlanReview, MissionPlanReview.created_at),
        items=await plan_items(db, plan.id),
        waivers=await rows(MissionReviewWaiver, MissionReviewWaiver.created_at),
        verifications=await rows(MissionPlanVerification, MissionPlanVerification.created_at),
        dossiers=dossiers,
    )
