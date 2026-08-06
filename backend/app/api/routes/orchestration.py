"""Project-scoped agent orchestration and bounded CLI execution loops."""
import uuid
import re
from datetime import date, datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.orchestration import (
    AgentRuntimeProfileCreate,
    AgentRuntimeProfileOut,
    AgentRuntimeProfileUpdate,
    ForgeRouterVirtualModelOut,
    EligibleMembershipOut,
    ProjectAgentMembershipCreate,
    ProjectAgentMembershipOut,
    ProjectAgentMembershipUpdate,
    ProjectLoopPolicyCreate,
    ProjectLoopPolicyOut,
    ProjectLoopPolicyUpdate,
    TaskDispatchCreate,
    TaskDispatchOut,
    TaskExecutionReviewCreate,
    TaskExecutionReviewOut,
    TaskExecutionReviewUpdate,
)
from app.core.config import settings
from app.core.secrets import decrypt_secret
from app.db.base import get_db
from app.db.models.agent import Agent, AgentSkill, Skill, SubAgent, SubAgentSkill
from app.db.models.backlog import PlanningItem
from app.db.models.governance import AuditEvent
from app.db.models.orchestration import (
    AgentRuntimeProfile,
    ProjectAgentMembership,
    ProjectLoopPolicy,
    TaskExecutionReview,
)
from app.db.models.project import ChangeRequest, Project
from app.db.models.task import ProjectTask, TaskAssignment, TaskExecution, TaskRequiredSkill

router = APIRouter(prefix="/api/v1/orchestration", tags=["orchestration"])

FORGEROUTER_VIRTUAL_MODELS = (
    ("auto", "Classifica cada requisição e escolhe a rota adequada.", True),
    ("simple", "Trabalho utilitário curto, rápido e barato.", False),
    ("standard", "Chat, resumos e tool calls rotineiras.", False),
    ("complex", "Contexto longo e tarefas pesadas multi-etapa.", False),
    ("reasoning", "Planejamento, provas e diagnóstico profundo.", False),
    ("vision", "Requisições com imagens.", False),
    ("audio", "TTS e pós-processamento de transcrições.", False),
    ("code", "Geração e edição de código.", False),
)


@router.get("/forgerouter-models", response_model=list[ForgeRouterVirtualModelOut])
async def list_forgerouter_virtual_models() -> list[ForgeRouterVirtualModelOut]:
    return [
        ForgeRouterVirtualModelOut(
            id=f"forgerouter/{group}",
            routing_group=group,
            description=description,
            is_recommended_default=is_default,
        )
        for group, description, is_default in FORGEROUTER_VIRTUAL_MODELS
    ]


async def _get_or_404(db: AsyncSession, model, entity_id: uuid.UUID, label: str):
    entity = await db.get(model, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return entity


async def _task_project_id(db: AsyncSession, task: ProjectTask) -> uuid.UUID:
    if task.planning_item_id:
        item = await db.get(PlanningItem, task.planning_item_id)
        if item and item.project_id:
            return item.project_id
    if task.change_request_id:
        change = await db.get(ChangeRequest, task.change_request_id)
        if change:
            return change.project_id
    raise HTTPException(status_code=409, detail="Task cannot be resolved to a project")


def _profile_matches_membership(
    profile: AgentRuntimeProfile, membership: ProjectAgentMembership
) -> bool:
    return (
        profile.agent_id is not None
        and profile.agent_id == membership.agent_id
        or profile.sub_agent_id is not None
        and profile.sub_agent_id == membership.sub_agent_id
    )


async def _validate_membership_owner(
    db: AsyncSession, payload: ProjectAgentMembershipCreate
) -> None:
    if payload.agent_id:
        agent = await _get_or_404(db, Agent, payload.agent_id, "Agent")
        if payload.status == "active" and (not agent.is_active or agent.status != "active"):
            raise HTTPException(status_code=409, detail="Agent is not active")
    else:
        sub_agent = await _get_or_404(db, SubAgent, payload.sub_agent_id, "Sub-agent")
        if payload.status == "active" and (
            not sub_agent.is_active or sub_agent.status != "active"
        ):
            raise HTTPException(status_code=409, detail="Sub-agent is not active")


async def _validate_policy_links(
    db: AsyncSession,
    project_id: uuid.UUID,
    producer_membership_id: uuid.UUID,
    reviewer_membership_id: uuid.UUID,
    producer_runtime_profile_id: uuid.UUID,
    reviewer_runtime_profile_id: uuid.UUID,
) -> None:
    producer = await _get_or_404(
        db, ProjectAgentMembership, producer_membership_id, "Producer membership"
    )
    reviewer = await _get_or_404(
        db, ProjectAgentMembership, reviewer_membership_id, "Reviewer membership"
    )
    if producer.project_id != project_id or reviewer.project_id != project_id:
        raise HTTPException(status_code=422, detail="Loop memberships must belong to this project")
    if producer.status != "active" or reviewer.status != "active":
        raise HTTPException(status_code=409, detail="Loop memberships must be active")
    if not reviewer.can_review:
        raise HTTPException(status_code=422, detail="Reviewer membership must have can_review=true")

    producer_profile = await _get_or_404(
        db, AgentRuntimeProfile, producer_runtime_profile_id, "Producer runtime profile"
    )
    reviewer_profile = await _get_or_404(
        db, AgentRuntimeProfile, reviewer_runtime_profile_id, "Reviewer runtime profile"
    )
    if not _profile_matches_membership(producer_profile, producer):
        raise HTTPException(status_code=422, detail="Producer runtime profile belongs to another agent")
    if not _profile_matches_membership(reviewer_profile, reviewer):
        raise HTTPException(status_code=422, detail="Reviewer runtime profile belongs to another agent")
    if not producer_profile.is_active or not reviewer_profile.is_active:
        raise HTTPException(status_code=409, detail="Loop runtime profiles must be active")


# Runtime profiles ---------------------------------------------------------


@router.post("/runtime-profiles", response_model=AgentRuntimeProfileOut, status_code=201)
async def create_runtime_profile(
    payload: AgentRuntimeProfileCreate, db: AsyncSession = Depends(get_db)
) -> AgentRuntimeProfile:
    if payload.agent_id:
        await _get_or_404(db, Agent, payload.agent_id, "Agent")
    else:
        await _get_or_404(db, SubAgent, payload.sub_agent_id, "Sub-agent")

    if payload.is_default:
        owner_filter = (
            AgentRuntimeProfile.agent_id == payload.agent_id
            if payload.agent_id
            else AgentRuntimeProfile.sub_agent_id == payload.sub_agent_id
        )
        await db.execute(
            update(AgentRuntimeProfile)
            .where(
                owner_filter,
                AgentRuntimeProfile.runtime_type == payload.runtime_type,
                AgentRuntimeProfile.purpose == payload.purpose,
            )
            .values(is_default=False)
        )
    profile = AgentRuntimeProfile(**payload.model_dump())
    db.add(profile)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise HTTPException(
                status_code=409, detail="Runtime profile name already exists for this agent"
            ) from exc
        raise
    await db.refresh(profile)
    return profile


@router.get("/runtime-profiles", response_model=list[AgentRuntimeProfileOut])
async def list_runtime_profiles(
    agent_id: uuid.UUID | None = None,
    sub_agent_id: uuid.UUID | None = None,
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
) -> list[AgentRuntimeProfile]:
    stmt = select(AgentRuntimeProfile)
    if agent_id:
        stmt = stmt.where(AgentRuntimeProfile.agent_id == agent_id)
    if sub_agent_id:
        stmt = stmt.where(AgentRuntimeProfile.sub_agent_id == sub_agent_id)
    if active_only:
        stmt = stmt.where(AgentRuntimeProfile.is_active.is_(True))
    result = await db.execute(stmt.order_by(AgentRuntimeProfile.routing_group, AgentRuntimeProfile.name))
    return list(result.scalars().all())


@router.patch("/runtime-profiles/{profile_id}", response_model=AgentRuntimeProfileOut)
async def update_runtime_profile(
    profile_id: uuid.UUID,
    payload: AgentRuntimeProfileUpdate,
    db: AsyncSession = Depends(get_db),
) -> AgentRuntimeProfile:
    profile = await _get_or_404(db, AgentRuntimeProfile, profile_id, "Runtime profile")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(profile, field, value)
    await db.commit()
    await db.refresh(profile)
    return profile


# Project team -------------------------------------------------------------


@router.post(
    "/projects/{project_id}/memberships",
    response_model=ProjectAgentMembershipOut,
    status_code=201,
)
async def create_project_membership(
    project_id: uuid.UUID,
    payload: ProjectAgentMembershipCreate,
    db: AsyncSession = Depends(get_db),
) -> ProjectAgentMembership:
    await _get_or_404(db, Project, project_id, "Project")
    await _validate_membership_owner(db, payload)
    membership = ProjectAgentMembership(project_id=project_id, **payload.model_dump())
    db.add(membership)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise HTTPException(status_code=409, detail="Agent is already a member of this project") from exc
        raise
    await db.refresh(membership)
    return membership


@router.get(
    "/projects/{project_id}/memberships", response_model=list[ProjectAgentMembershipOut]
)
async def list_project_memberships(
    project_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[ProjectAgentMembership]:
    await _get_or_404(db, Project, project_id, "Project")
    result = await db.execute(
        select(ProjectAgentMembership)
        .where(ProjectAgentMembership.project_id == project_id)
        .order_by(ProjectAgentMembership.role, ProjectAgentMembership.created_at)
    )
    return list(result.scalars().all())


@router.get(
    "/agents/{agent_id}/memberships", response_model=list[ProjectAgentMembershipOut]
)
async def list_agent_memberships(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[ProjectAgentMembership]:
    """The inverse of list_project_memberships -- which projects is this
    agent actually on, and with what role (2026-08-05, Software Factory
    visibility fix: the agent detail page had no view of this at all)."""
    await _get_or_404(db, Agent, agent_id, "Agent")
    result = await db.execute(
        select(ProjectAgentMembership)
        .where(ProjectAgentMembership.agent_id == agent_id, ProjectAgentMembership.status == "active")
        .order_by(ProjectAgentMembership.created_at.desc())
    )
    return list(result.scalars().all())


@router.patch("/memberships/{membership_id}", response_model=ProjectAgentMembershipOut)
async def update_project_membership(
    membership_id: uuid.UUID,
    payload: ProjectAgentMembershipUpdate,
    db: AsyncSession = Depends(get_db),
) -> ProjectAgentMembership:
    membership = await _get_or_404(db, ProjectAgentMembership, membership_id, "Membership")
    data = payload.model_dump(exclude_unset=True)
    merged_from = data.get("valid_from", membership.valid_from)
    merged_to = data.get("valid_to", membership.valid_to)
    if merged_from and merged_to and merged_to < merged_from:
        raise HTTPException(status_code=422, detail="valid_to cannot be before valid_from")
    for field, value in data.items():
        setattr(membership, field, value)
    await db.commit()
    await db.refresh(membership)
    return membership


# Loop policies ------------------------------------------------------------


@router.post(
    "/projects/{project_id}/loop-policies", response_model=ProjectLoopPolicyOut, status_code=201
)
async def create_loop_policy(
    project_id: uuid.UUID,
    payload: ProjectLoopPolicyCreate,
    db: AsyncSession = Depends(get_db),
) -> ProjectLoopPolicy:
    await _get_or_404(db, Project, project_id, "Project")
    await _validate_policy_links(
        db,
        project_id,
        payload.producer_membership_id,
        payload.reviewer_membership_id,
        payload.producer_runtime_profile_id,
        payload.reviewer_runtime_profile_id,
    )
    policy = ProjectLoopPolicy(project_id=project_id, **payload.model_dump())
    db.add(policy)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise HTTPException(status_code=409, detail="Loop policy name already exists in this project") from exc
        raise
    await db.refresh(policy)
    return policy


@router.get(
    "/projects/{project_id}/loop-policies", response_model=list[ProjectLoopPolicyOut]
)
async def list_loop_policies(
    project_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[ProjectLoopPolicy]:
    await _get_or_404(db, Project, project_id, "Project")
    result = await db.execute(
        select(ProjectLoopPolicy)
        .where(ProjectLoopPolicy.project_id == project_id)
        .order_by(ProjectLoopPolicy.phase, ProjectLoopPolicy.name)
    )
    return list(result.scalars().all())


@router.patch("/loop-policies/{policy_id}", response_model=ProjectLoopPolicyOut)
async def update_loop_policy(
    policy_id: uuid.UUID,
    payload: ProjectLoopPolicyUpdate,
    db: AsyncSession = Depends(get_db),
) -> ProjectLoopPolicy:
    policy = await _get_or_404(db, ProjectLoopPolicy, policy_id, "Loop policy")
    data = payload.model_dump(exclude_unset=True)
    producer_membership_id = data.get("producer_membership_id", policy.producer_membership_id)
    reviewer_membership_id = data.get("reviewer_membership_id", policy.reviewer_membership_id)
    if producer_membership_id == reviewer_membership_id:
        raise HTTPException(status_code=422, detail="Producer and reviewer must be different")
    await _validate_policy_links(
        db,
        policy.project_id,
        producer_membership_id,
        reviewer_membership_id,
        data.get("producer_runtime_profile_id", policy.producer_runtime_profile_id),
        data.get("reviewer_runtime_profile_id", policy.reviewer_runtime_profile_id),
    )
    for field, value in data.items():
        setattr(policy, field, value)
    await db.commit()
    await db.refresh(policy)
    return policy


# Eligibility --------------------------------------------------------------


async def _member_skill_ids(db: AsyncSession, membership: ProjectAgentMembership) -> set[uuid.UUID]:
    if membership.agent_id:
        result = await db.execute(
            select(AgentSkill.skill_id)
            .join(Skill, Skill.id == AgentSkill.skill_id)
            .where(AgentSkill.agent_id == membership.agent_id, Skill.is_approved.is_(True))
        )
        return set(result.scalars().all())

    sub_agent = await db.get(SubAgent, membership.sub_agent_id)
    direct = await db.execute(
        select(SubAgentSkill.skill_id)
        .join(Skill, Skill.id == SubAgentSkill.skill_id)
        .where(SubAgentSkill.sub_agent_id == membership.sub_agent_id, Skill.is_approved.is_(True))
    )
    inherited = await db.execute(
        select(AgentSkill.skill_id)
        .join(Skill, Skill.id == AgentSkill.skill_id)
        .where(
            AgentSkill.agent_id == sub_agent.agent_id,
            AgentSkill.inheritable.is_(True),
            Skill.is_approved.is_(True),
        )
    )
    return set(direct.scalars().all()) | set(inherited.scalars().all())


@router.get("/tasks/{task_id}/eligible-memberships", response_model=list[EligibleMembershipOut])
async def list_eligible_memberships(
    task_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[EligibleMembershipOut]:
    task = await _get_or_404(db, ProjectTask, task_id, "Task")
    project_id = await _task_project_id(db, task)
    required = await db.execute(
        select(TaskRequiredSkill.skill_id).where(
            TaskRequiredSkill.task_id == task_id, TaskRequiredSkill.is_mandatory.is_(True)
        )
    )
    required_ids = set(required.scalars().all())
    members_result = await db.execute(
        select(ProjectAgentMembership).where(ProjectAgentMembership.project_id == project_id)
    )
    today = date.today()
    output: list[EligibleMembershipOut] = []
    for membership in members_result.scalars().all():
        reasons: list[str] = []
        if membership.status != "active":
            reasons.append(f"membership is {membership.status}")
        if membership.valid_from and membership.valid_from > today:
            reasons.append("membership is not active yet")
        if membership.valid_to and membership.valid_to < today:
            reasons.append("membership has expired")
        skill_ids = await _member_skill_ids(db, membership)
        missing = required_ids - skill_ids
        if missing:
            reasons.append("missing required skills: " + ", ".join(sorted(map(str, missing))))
        output.append(
            EligibleMembershipOut(
                membership=ProjectAgentMembershipOut.model_validate(membership),
                eligible=not reasons,
                reasons=reasons,
            )
        )
    return output


# Reviews ------------------------------------------------------------------


@router.post(
    "/executions/{execution_id}/reviews", response_model=TaskExecutionReviewOut, status_code=201
)
async def create_execution_review(
    execution_id: uuid.UUID,
    payload: TaskExecutionReviewCreate,
    db: AsyncSession = Depends(get_db),
) -> TaskExecutionReview:
    execution = await _get_or_404(db, TaskExecution, execution_id, "Execution")
    task = await _get_or_404(db, ProjectTask, execution.task_id, "Task")
    project_id = await _task_project_id(db, task)
    reviewer = await _get_or_404(
        db, ProjectAgentMembership, payload.reviewer_membership_id, "Reviewer membership"
    )
    if execution.assignment_id:
        assignment = await db.get(TaskAssignment, execution.assignment_id)
        if assignment and assignment.membership_id == reviewer.id:
            raise HTTPException(status_code=409, detail="Executor cannot review the same execution")
    if reviewer.project_id != project_id or reviewer.status != "active" or not reviewer.can_review:
        raise HTTPException(status_code=422, detail="Reviewer is not authorized for this project")
    review = TaskExecutionReview(execution_id=execution_id, **payload.model_dump())
    if review.status in {"approved", "changes_requested", "rejected"}:
        review.decided_at = datetime.now(timezone.utc)
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return review


@router.get(
    "/executions/{execution_id}/reviews", response_model=list[TaskExecutionReviewOut]
)
async def list_execution_reviews(
    execution_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[TaskExecutionReview]:
    await _get_or_404(db, TaskExecution, execution_id, "Execution")
    result = await db.execute(
        select(TaskExecutionReview)
        .where(TaskExecutionReview.execution_id == execution_id)
        .order_by(TaskExecutionReview.created_at)
    )
    return list(result.scalars().all())


@router.patch("/reviews/{review_id}", response_model=TaskExecutionReviewOut)
async def update_execution_review(
    review_id: uuid.UUID,
    payload: TaskExecutionReviewUpdate,
    db: AsyncSession = Depends(get_db),
) -> TaskExecutionReview:
    review = await _get_or_404(db, TaskExecutionReview, review_id, "Review")
    if review.status in {"approved", "rejected"}:
        raise HTTPException(status_code=409, detail="Final review decision is immutable")
    data = payload.model_dump(exclude_unset=True)
    merged_status = data.get("status", review.status)
    merged_feedback = data.get("feedback", review.feedback)
    if merged_status in {"approved", "changes_requested", "rejected"} and not merged_feedback:
        raise HTTPException(status_code=422, detail="feedback is required for a review decision")
    for field, value in data.items():
        setattr(review, field, value)
    if merged_status in {"approved", "changes_requested", "rejected"}:
        review.decided_at = datetime.now(timezone.utc)
        db.add(
            AuditEvent(
                entity_type="task_execution_review",
                entity_id=review.id,
                event_type=f"review_{merged_status}",
                actor=str(review.reviewer_membership_id),
                payload={"execution_id": str(review.execution_id), "score": review.score},
            )
        )
    await db.commit()
    await db.refresh(review)
    if merged_status == "approved":
        execution = await _get_or_404(db, TaskExecution, review.execution_id, "Execution")
        execution.status = "verified"
        task = await _get_or_404(db, ProjectTask, execution.task_id, "Task")
        task.status = "done"
        task.completed_at = datetime.now(timezone.utc)
        await db.commit()
    return review


def _bridge_headers() -> dict[str, str]:
    return {"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN}


def _build_task_prompt(task: ProjectTask, project: Project, addendum: str | None) -> str:
    source = (
        f"Planning Item {task.planning_item_id}"
        if task.planning_item_id
        else f"Change Request {task.change_request_id}"
    )
    text = f"""Execute the governed ForgeHub task below.

Project: {project.name} ({project.id})
Task: {task.title} ({task.id})
Source: {source}
Priority: {task.priority}

Description:
{task.description or 'No additional description.'}

Read AGENTS.md and project-local instructions before editing. Preserve unrelated
changes. Work only inside the project directory. Run relevant verification.
Do not deploy, approve gates, or claim tests passed unless you ran them.
End with a concise summary, changed files, verification, risks, and evidence.
"""
    if addendum:
        text += f"\nAdditional governed instructions:\n{addendum}\n"
    return text


@router.post("/tasks/{task_id}/dispatch", response_model=TaskDispatchOut, status_code=202)
async def dispatch_task(
    task_id: uuid.UUID,
    payload: TaskDispatchCreate,
    db: AsyncSession = Depends(get_db),
) -> TaskDispatchOut:
    raise HTTPException(
        status_code=410,
        detail=(
            "Legacy direct dispatch was retired by ER-RUN-01. Create and activate an "
            "ExecutionWave, build and issue an immutable Work Package, then use "
            "POST /api/v1/work-packages/{id}:dispatch."
        ),
    )


@router.post("/executions/{execution_id}/refresh", response_model=dict)
async def refresh_dispatched_execution(
    execution_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> dict:
    execution = await _get_or_404(db, TaskExecution, execution_id, "Execution")
    if execution.work_package_id:
        raise HTTPException(status_code=410, detail="Use :refresh-runtime for governed Work Package executions")
    if not execution.runtime_session_ref:
        raise HTTPException(status_code=409, detail="Execution has no CLI run reference")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{settings.CHAT_BRIDGE_URL}/v1/agent-runs/{execution.runtime_session_ref}",
                headers=_bridge_headers(),
            )
            response.raise_for_status()
            run = response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"CLI runner refresh failed: {exc}") from exc

    state = run.get("status")
    if state == "completed":
        execution.status = "completed"
        execution.finished_at = datetime.now(timezone.utc)
        execution.outcome_summary = (run.get("output") or "CLI run completed")[-4000:]
        execution.evidence_ref = f"forgehub://agent-runs/{execution.runtime_session_ref}"
    elif state in {"failed", "timed_out"}:
        execution.status = "failed"
        execution.finished_at = datetime.now(timezone.utc)
        execution.outcome_summary = (run.get("error") or f"CLI run {state}")[-4000:]
        execution.evidence_ref = f"forgehub://agent-runs/{execution.runtime_session_ref}"
    elif state == "running":
        execution.status = "running"
    await db.commit()
    return run


def _build_review_prompt(
    task: ProjectTask, execution: TaskExecution, policy: ProjectLoopPolicy
) -> str:
    return f"""Review the governed ForgeHub execution below. Work read-only.

Task: {task.title} ({task.id})
Task description: {task.description or 'No additional description.'}
Execution: {execution.id}, loop iteration {execution.loop_iteration}
Execution evidence: {execution.evidence_ref or 'No evidence reference'}
Execution summary:
{execution.outcome_summary or 'No summary recorded.'}

Inspect repository changes and verification evidence. Identify concrete defects,
missing acceptance coverage, security risks, and regressions. Do not edit files.
The minimum passing score is {policy.min_review_score}/100.

Finish with exactly these two lines:
FORGEHUB_SCORE: <integer 0-100>
FORGEHUB_DECISION: approved|changes_requested
"""


@router.post(
    "/executions/{execution_id}/dispatch-review",
    response_model=TaskExecutionReviewOut,
    status_code=202,
)
async def dispatch_execution_review(
    execution_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> TaskExecutionReview:
    execution = await _get_or_404(db, TaskExecution, execution_id, "Execution")
    if not execution.work_package_id:
        raise HTTPException(status_code=409, detail="Review dispatch requires a governed Work Package")
    if execution.status not in {"completed", "verified"}:
        raise HTTPException(status_code=409, detail="Execution must be completed before review")
    if not execution.loop_policy_id:
        raise HTTPException(status_code=409, detail="Execution has no loop policy")
    policy = await _get_or_404(db, ProjectLoopPolicy, execution.loop_policy_id, "Loop policy")
    task = await _get_or_404(db, ProjectTask, execution.task_id, "Task")
    project = await _get_or_404(db, Project, policy.project_id, "Project")
    if not project.working_directory_path:
        raise HTTPException(status_code=409, detail="Project has no working_directory_path")
    reviewer = await _get_or_404(
        db, ProjectAgentMembership, policy.reviewer_membership_id, "Reviewer membership"
    )
    profile = await _get_or_404(
        db, AgentRuntimeProfile, policy.reviewer_runtime_profile_id, "Reviewer runtime profile"
    )
    if reviewer.status != "active" or not reviewer.can_review or not profile.is_active:
        raise HTTPException(status_code=409, detail="Configured reviewer is not active")
    credential_agent_id = reviewer.agent_id
    if credential_agent_id is None and reviewer.sub_agent_id is not None:
        reviewer_sub_agent = await _get_or_404(db, SubAgent, reviewer.sub_agent_id, "Reviewer sub-agent")
        credential_agent_id = reviewer_sub_agent.agent_id
    credential_agent = await _get_or_404(db, Agent, credential_agent_id, "Reviewer credential agent")
    if not credential_agent.forgerouter_api_key_encrypted:
        raise HTTPException(status_code=409, detail="Reviewer has no ForgeRouter API key configured")
    try:
        reviewer_api_key = decrypt_secret(credential_agent.forgerouter_api_key_encrypted)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Reviewer credential cannot be decrypted") from exc
    if execution.assignment_id:
        assignment = await db.get(TaskAssignment, execution.assignment_id)
        if assignment and assignment.membership_id == reviewer.id:
            raise HTTPException(status_code=409, detail="Executor cannot review the same execution")

    existing = await db.execute(
        select(TaskExecutionReview).where(
            TaskExecutionReview.execution_id == execution.id,
            TaskExecutionReview.status.in_(["pending", "running"]),
        )
    )
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="Execution already has an active review")

    review = TaskExecutionReview(
        execution_id=execution.id,
        reviewer_membership_id=reviewer.id,
        runtime_profile_id=profile.id,
        status="running",
    )
    db.add(review)
    await db.flush()
    body = {
        "run_id": str(review.id),
        "runtime_type": profile.runtime_type,
        "project_path": project.working_directory_path,
        "prompt": _build_review_prompt(task, execution, policy),
        "model_ref": profile.model_ref,
        "mode": "plan",
        "max_seconds": 1800,
        "max_budget_usd": float(profile.max_budget_usd)
        if profile.max_budget_usd is not None
        else None,
        "api_key": reviewer_api_key,
        "work_package_hash": str(execution.work_package_id),
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{settings.CHAT_BRIDGE_URL}/v1/agent-runs",
                json=body,
                headers=_bridge_headers(),
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        review.status = "failed"
        review.feedback = f"Review dispatch failed: {exc}"
        await db.commit()
        raise HTTPException(status_code=502, detail=f"Review dispatch failed: {exc}") from exc
    review.runtime_session_ref = str(review.id)
    await db.commit()
    await db.refresh(review)
    return review


@router.post("/reviews/{review_id}/refresh", response_model=TaskExecutionReviewOut)
async def refresh_execution_review(
    review_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> TaskExecutionReview:
    review = await _get_or_404(db, TaskExecutionReview, review_id, "Review")
    if not review.runtime_session_ref:
        raise HTTPException(status_code=409, detail="Review has no CLI run reference")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{settings.CHAT_BRIDGE_URL}/v1/agent-runs/{review.runtime_session_ref}",
                headers=_bridge_headers(),
            )
            response.raise_for_status()
            run = response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Review refresh failed: {exc}") from exc

    if run.get("status") == "running":
        return review
    if run.get("status") != "completed":
        review.status = "failed"
        review.feedback = (run.get("error") or "Reviewer CLI failed")[-10000:]
        review.decided_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(review)
        return review

    output = run.get("output") or ""
    score_match = re.search(r"FORGEHUB_SCORE:\s*(\d{1,3})", output)
    decision_match = re.search(
        r"FORGEHUB_DECISION:\s*(approved|changes_requested)", output, re.IGNORECASE
    )
    score = min(100, int(score_match.group(1))) if score_match else None
    proposed = decision_match.group(1).lower() if decision_match else "changes_requested"
    execution = await _get_or_404(db, TaskExecution, review.execution_id, "Execution")
    policy = await _get_or_404(db, ProjectLoopPolicy, execution.loop_policy_id, "Loop policy")
    passes = score is not None and score >= policy.min_review_score and proposed == "approved"
    review.score = score
    review.feedback = output[-10000:]
    review.evidence_ref = f"forgehub://agent-runs/{review.runtime_session_ref}"
    review.decided_at = datetime.now(timezone.utc)
    review.status = (
        "pending"
        if policy.requires_human_approval
        else ("approved" if passes else "changes_requested")
    )
    await db.commit()
    await db.refresh(review)

    if review.status == "approved":
        execution.status = "verified"
        task = await _get_or_404(db, ProjectTask, execution.task_id, "Task")
        task.status = "done"
        task.completed_at = datetime.now(timezone.utc)
        await db.commit()
    return review
