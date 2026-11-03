"""Mission planning records: the exit conditions that read them (M0.0b).

Contract: docs/architecture/MCP_MISSION_TOOLS_SPEC.md §2.6. `core/mission.py`
calls these from `planning_exit_conditions`/`transition_preconditions`; the
write routes are in `api/routes/mission_records.py`.

Only the current plan version's records count: the mission's newest
`ProjectPlan` in `draft`, which must have a `mission_plan_versions` row (its
author). The planners of a version are its author and the orchestrator; a
review or verification by either never counts, re-checked here at exit and
not only when written. Conditions from `critical_review` on are cumulative,
so a version swap mid-pipeline leaves nothing that passes on old records.
"""
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.mission import (
    MissionDossier,
    MissionPlanReview,
    MissionPlanVerification,
    MissionPlanVersion,
    MissionReviewItem,
    MissionReviewWaiver,
    ProjectMission,
)
from app.db.models.project import ProjectPlan
from app.db.models.task import ProjectTask, TaskExecutionTarget

RECORD_STAGES = ("critical_review", "consolidation", "cross_review", "decisions", "application")
APPLIED_DISPOSITIONS = ("accept", "adjust")
MIN_VERIFICATION_SAMPLE = 3


def _item(code: str, message: str, **context: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **context}


async def current_plan(db: AsyncSession, project_id: uuid.UUID) -> ProjectPlan | None:
    """The plan version under review: the mission's newest draft."""
    return (await db.execute(
        select(ProjectPlan)
        .where(ProjectPlan.project_id == project_id, ProjectPlan.status == "draft")
        .order_by(ProjectPlan.created_at.desc(), ProjectPlan.id.desc())
        .limit(1)
    )).scalars().first()


async def current_plan_version(
    db: AsyncSession, project_id: uuid.UUID
) -> tuple[ProjectPlan | None, MissionPlanVersion | None, list[dict[str, Any]]]:
    plan = await current_plan(db, project_id)
    if plan is None:
        return None, None, [_item("PLAN_DRAFT_MISSING", "No ProjectPlan version in draft for this mission")]
    version = await db.get(MissionPlanVersion, plan.id)
    if version is None:
        return plan, None, [_item(
            "PLAN_VERSION_NOT_REGISTERED",
            "The newest draft plan has no recorded author; register it through POST /missions/{id}/plans",
            project_plan_id=str(plan.id),
        )]
    return plan, version, []


def is_planner(mission: ProjectMission, version: MissionPlanVersion | None, principal_type: str,
               principal_id: uuid.UUID) -> bool:
    """§2.6: the plan version's author and the mission's orchestrator."""
    if principal_type == "agent" and principal_id == mission.orchestrator_agent_id:
        return True
    return version is not None and (version.author_type, version.author_id) == (principal_type, principal_id)


def environment_items(tasks: list[ProjectTask]) -> list[dict[str, Any]]:
    """P1: every mission task names the environment its work lands in."""
    return [
        _item("TASK_ENVIRONMENT_MISSING", "Task has no target_environment",
              task_id=str(t.id), task_number=t.number)
        for t in tasks if not t.target_environment
    ]


async def environment_prerequisite_items(db: AsyncSession, tasks: list[ProjectTask]) -> list[dict[str, Any]]:
    """P2: prerequisites recorded (an empty list is a recorded "none") and
    every publish target names the task's own environment."""
    unmet = [
        _item("TASK_ENVIRONMENT_PREREQUISITES_MISSING", "Task has no environment prerequisites recorded",
              task_id=str(t.id), task_number=t.number)
        for t in tasks if t.environment_prerequisites is None
    ]
    by_id = {t.id: t for t in tasks}
    if by_id:
        targets = (await db.execute(select(TaskExecutionTarget).where(
            TaskExecutionTarget.task_id.in_(list(by_id)), TaskExecutionTarget.kind == "publish",
        ))).scalars()
        for target in targets:
            task = by_id[target.task_id]
            environment = target.target_key.split(":", 1)[0]
            if environment != task.target_environment:
                unmet.append(_item(
                    "PUBLISH_TARGET_ENVIRONMENT_MISMATCH",
                    "A publish target names another environment than the task's target_environment",
                    task_id=str(task.id), task_number=task.number, target=f"publish:{target.target_key}",
                    target_environment=task.target_environment,
                ))
    return unmet


async def _reviews(db: AsyncSession, plan_id: uuid.UUID) -> list[MissionPlanReview]:
    return list((await db.execute(
        select(MissionPlanReview).where(MissionPlanReview.project_plan_id == plan_id)
        .order_by(MissionPlanReview.created_at)
    )).scalars())


async def plan_items(db: AsyncSession, plan_id: uuid.UUID) -> list[MissionReviewItem]:
    return list((await db.execute(
        select(MissionReviewItem)
        .join(MissionPlanReview, MissionPlanReview.id == MissionReviewItem.review_id)
        .where(MissionPlanReview.project_plan_id == plan_id)
        .order_by(MissionReviewItem.created_at)
    )).scalars())


def effective_disposition(item: MissionReviewItem) -> str | None:
    return item.marcelo_decision or item.disposition


def _valid_reviews(reviews: list[MissionPlanReview], mission: ProjectMission, version: MissionPlanVersion,
                   kind: str) -> list[MissionPlanReview]:
    return [r for r in reviews if r.kind == kind and not is_planner(mission, version, "agent", r.reviewer_agent_id)]


async def layer_review_items(db, mission, plan, version, reviews) -> list[dict[str, Any]]:
    """P3: one opinion per required layer by a non-planner, or Marcelo's waiver."""
    covered = {r.layer for r in _valid_reviews(reviews, mission, version, "layer")}
    waived = set((await db.execute(
        select(MissionReviewWaiver.layer).where(MissionReviewWaiver.project_plan_id == plan.id)
    )).scalars())
    return [
        _item("LAYER_REVIEW_MISSING", "Required layer has no opinion from a reviewer independent of the planner "
              "and no recorded decision by Marcelo", layer=layer)
        for layer in mission.required_review_layers or [] if layer not in covered | waived
    ]


def disposition_items(items: list[MissionReviewItem]) -> list[dict[str, Any]]:
    """P4: every item has a disposition and a reason."""
    unmet: list[dict[str, Any]] = []
    for item in items:
        if item.disposition is None:
            unmet.append(_item("ITEM_WITHOUT_DISPOSITION", "Review item has no disposition", item_id=str(item.id)))
        elif not (item.disposition_reason or "").strip():
            unmet.append(_item("ITEM_WITHOUT_REASON", "Review item's disposition has no reason", item_id=str(item.id)))
    return unmet


def cross_review_items(reviews, mission, version) -> list[dict[str, Any]]:
    """P5: two cross reviews by different non-planner reviewers on different layers."""
    cross = _valid_reviews(reviews, mission, version, "cross")
    if any(a.reviewer_agent_id != b.reviewer_agent_id and a.layer != b.layer for a in cross for b in cross):
        return []
    return [_item("CROSS_REVIEWS_INSUFFICIENT",
                  "Two cross reviews by different reviewers, on different layers, both independent of the planner",
                  valid_cross_reviews=len(cross))]


def flagged_items(items: list[MissionReviewItem]) -> list[dict[str, Any]]:
    """P6: no item flagged for Marcelo without his decision."""
    return [
        _item("FLAGGED_ITEM_UNDECIDED", "Review item flagged for Marcelo has no decision", item_id=str(item.id))
        for item in items if item.needs_marcelo_decision and item.marcelo_decision is None
    ]


def required_sample_size(items: list[MissionReviewItem]) -> tuple[set[uuid.UUID], int]:
    applied = {i.id for i in items if effective_disposition(i) in APPLIED_DISPOSITIONS}
    return applied, min(MIN_VERIFICATION_SAMPLE, len(applied))


async def verification_items(db, mission, plan, version, items) -> list[dict[str, Any]]:
    """P7: the version's latest verification, by a non-planner, confirmed on a valid sample."""
    latest = (await db.execute(
        select(MissionPlanVerification).where(MissionPlanVerification.project_plan_id == plan.id)
        .order_by(MissionPlanVerification.created_at.desc(), MissionPlanVerification.id.desc()).limit(1)
    )).scalars().first()
    if latest is None or is_planner(mission, version, "agent", latest.verifier_agent_id):
        return [_item("APPLICATION_VERIFICATION_MISSING",
                      "No sampled verification of the applied corrections by a verifier independent of the planner")]
    applied, minimum = required_sample_size(items)
    sample = set(latest.sampled_item_ids or [])
    if not sample <= applied or len(sample) < minimum:
        return [_item("APPLICATION_VERIFICATION_MISSING", "The latest verification's sample is no longer valid",
                      verification_id=str(latest.id), required_sample=minimum)]
    if latest.result != "confirmed":
        return [_item("APPLICATION_VERIFICATION_DISCREPANCIES",
                      "The latest verification found corrections missing from the text",
                      verification_id=str(latest.id))]
    return []


async def record_conditions(db: AsyncSession, mission: ProjectMission) -> list[dict[str, Any]]:
    """Cumulative record conditions for leaving the current stage (§2.6.3)."""
    stage = mission.planning_stage
    plan, version, unmet = await current_plan_version(db, mission.project_id)
    if plan is None or version is None:
        return unmet
    upto = RECORD_STAGES[: RECORD_STAGES.index(stage) + 1]
    reviews = await _reviews(db, plan.id)
    items = await plan_items(db, plan.id)
    unmet += await layer_review_items(db, mission, plan, version, reviews)
    if "consolidation" in upto:
        unmet += disposition_items(items)
    if stage == "cross_review" or ("decisions" in upto and mission.risk_level != "low"):
        unmet += cross_review_items(reviews, mission, version)
    if "decisions" in upto:
        unmet += flagged_items(items)
    if "application" in upto:
        unmet += await verification_items(db, mission, plan, version, items)
    return unmet


async def dossier_items(db: AsyncSession, mission: ProjectMission) -> list[dict[str, Any]]:
    """verifying -> awaiting_acceptance: a dossier registered during this verifying stay."""
    found = await db.scalar(select(MissionDossier.id).where(
        MissionDossier.mission_project_id == mission.project_id,
        MissionDossier.created_at >= mission.state_changed_at,
    ).limit(1))
    if found is None:
        return [_item("DOSSIER_MISSING", "No dossier artifact version registered during the current verifying stay")]
    return []
