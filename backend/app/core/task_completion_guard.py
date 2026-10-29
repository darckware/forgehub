"""Global, prospective completion guard (Plano Integrado M0.6a).

Contract: docs/architecture/MCP_MISSION_TOOLS_SPEC.md §4.1 and "Integration
before `done` for mission tasks". Every *new* transition of any ProjectTask
(all projects, not only missions) to `done` or `deployed` goes through
`assert_task_completion_allowed`, whichever writer makes it:

- `PATCH /tasks/{id}` (and the MCP `update_task_status`, which calls it);
- `PATCH /orchestration/reviews/{id}` approving a review;
- `POST /orchestration/reviews/{id}/refresh` when the reviewer CLI approves;
- the governed task approval (`core/governed_approval.py`).

It requires, in this order (the first refusal is returned):
1. `deployed` only from `done`;
2. dependencies and subtasks done/deployed;
3. the latest TaskExecution (highest attempt) exists and is `verified`;
4. its `evidence_ref` is a typed `git:`/`file:`/`db:` ref that checks out now
   (`core/task_evidence.verify_evidence`; file/git on the host through the
   bridge, so an unreachable bridge is "not verified", never approved);
5. an `approved` TaskExecutionReview on that execution by an independent
   reviewer: another registered agent than the executor (resolved from the
   assignment, else from the dispatched AgentDemand), with an active,
   in-date membership that `can_review` in the task's project (or in a mission
   the project executes for);
6. a mission task can't be `deployed` until a
   production release row exists (`environment_releases` doesn't exist yet,
   so a mission always gets DEPLOYED_WITHOUT_RELEASE);
7. a mission task with `git:` evidence: the commit is integrated in the
   mission mainline (`develop`), checked by the bridge's is-ancestor probe.
   This check runs last, so COMPLETION_NOT_INTEGRATED means everything else
   already passed (the review-approval path relies on that).

Prospective: tasks already `done`/`deployed` are never reopened or
backfilled, and a PATCH repeating the current status is not a transition.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ActorPrincipal
from app.core.evidence_bridge import EvidenceUnverifiable, commit_is_integrated
from app.core.task_dependencies import blocking_task_dependencies
from app.core.task_evidence import _resolve_execution_project, verify_evidence
from app.db.models.agent import SubAgent
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.mission import MissionProjectLink
from app.db.models.orchestration import ProjectAgentMembership, TaskExecutionReview
from app.db.models.project import Project
from app.db.models.task import ProjectTask, TaskAssignment, TaskExecution

COMPLETION_TARGET_STATUSES = ("done", "deployed")
EVIDENCE_PREFIXES = ("git", "file", "db")
MISSION_MAINLINE = "develop"

COMPLETION_NO_EXECUTION = "COMPLETION_NO_EXECUTION"
COMPLETION_EXECUTION_NOT_VERIFIED = "COMPLETION_EXECUTION_NOT_VERIFIED"
COMPLETION_EVIDENCE_INVALID = "COMPLETION_EVIDENCE_INVALID"
COMPLETION_EVIDENCE_UNVERIFIED = "COMPLETION_EVIDENCE_UNVERIFIED"
COMPLETION_NO_INDEPENDENT_REVIEW = "COMPLETION_NO_INDEPENDENT_REVIEW"
COMPLETION_REVIEWER_IS_EXECUTOR = "COMPLETION_REVIEWER_IS_EXECUTOR"
COMPLETION_DEPENDENCIES_OPEN = "COMPLETION_DEPENDENCIES_OPEN"
COMPLETION_SUBTASKS_OPEN = "COMPLETION_SUBTASKS_OPEN"
COMPLETION_NOT_INTEGRATED = "COMPLETION_NOT_INTEGRATED"
DEPLOYED_REQUIRES_DONE = "DEPLOYED_REQUIRES_DONE"
DEPLOYED_WITHOUT_RELEASE = "DEPLOYED_WITHOUT_RELEASE"


class CompletionRefused(Exception):
    def __init__(self, code: str, message: str, **context: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.context = context

    def to_http(self) -> HTTPException:
        return HTTPException(409, detail={"code": self.code, "message": self.message, **self.context})


@dataclass(frozen=True)
class CompletionProof:
    execution_id: uuid.UUID
    evidence_ref: str
    review_id: uuid.UUID
    reviewer_agent_id: uuid.UUID
    executor_agent_id: uuid.UUID | None
    integrated_ref: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def as_payload(self) -> dict[str, Any]:
        proof = {
            "execution_id": str(self.execution_id),
            "evidence_ref": self.evidence_ref,
            "review_id": str(self.review_id),
            "reviewer_agent_id": str(self.reviewer_agent_id),
            "executor_agent_id": str(self.executor_agent_id) if self.executor_agent_id else None,
        }
        if self.integrated_ref:
            proof["integrated_ref"] = self.integrated_ref
        return proof


async def _agent_identity(
    db: AsyncSession, agent_id: uuid.UUID | None, sub_agent_id: uuid.UUID | None
) -> uuid.UUID | None:
    """Registered agent behind an agent/sub-agent pair: a sub-agent is its
    parent's identity (it can't review its parent's work, nor vice versa)."""
    if agent_id is not None:
        return agent_id
    if sub_agent_id is not None:
        sub_agent = await db.get(SubAgent, sub_agent_id)
        return sub_agent.agent_id if sub_agent else None
    return None


async def resolve_executor_agent_id(db: AsyncSession, execution: TaskExecution) -> uuid.UUID | None:
    """Who ran the execution: the assignment's agent, else the agent the
    Messages dispatch targeted (Messages dispatches leave assignment_id NULL)."""
    if execution.assignment_id is not None:
        assignment = await db.get(TaskAssignment, execution.assignment_id)
        if assignment is not None:
            identity = await _agent_identity(db, assignment.agent_id, assignment.sub_agent_id)
            if identity is not None:
                return identity
    return (await db.execute(
        select(AgentDemand.target_agent_id)
        .where(AgentDemand.task_execution_id == execution.id, AgentDemand.target_agent_id.is_not(None))
        .order_by(AgentDemand.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()


async def task_project(db: AsyncSession, task: ProjectTask) -> Project | None:
    from app.core.mission import project_id_for_task_source

    project_id = await project_id_for_task_source(db, task.planning_item_id, task.change_request_id)
    return await db.get(Project, project_id) if project_id else None


async def mission_project_ids_for(db: AsyncSession, project: Project) -> list[uuid.UUID]:
    """Missions this project belongs to: itself when it is a mission, plus
    every mission it executes for (mission_project_links)."""
    ids = [project.id] if project.project_type == "mission" else []
    ids += list((await db.execute(
        select(MissionProjectLink.mission_project_id)
        .where(MissionProjectLink.executor_project_id == project.id)
    )).scalars())
    return ids


def membership_review_problem(membership: ProjectAgentMembership, allowed_projects: set[uuid.UUID]) -> str | None:
    if membership.project_id not in allowed_projects:
        return "reviewer membership belongs to another project"
    if membership.status != "active":
        return f"reviewer membership is {membership.status}"
    if not membership.can_review:
        return "reviewer membership has no can_review"
    today = date.today()
    if membership.valid_from and membership.valid_from > today:
        return "reviewer membership is not valid yet"
    if membership.valid_to and membership.valid_to < today:
        return "reviewer membership has expired"
    return None


async def _independent_review(
    db: AsyncSession,
    execution: TaskExecution,
    executor_agent_id: uuid.UUID | None,
    allowed_projects: set[uuid.UUID],
) -> tuple[TaskExecutionReview, uuid.UUID]:
    reviews = list((await db.execute(
        select(TaskExecutionReview)
        .where(TaskExecutionReview.execution_id == execution.id, TaskExecutionReview.status == "approved")
        .order_by(TaskExecutionReview.decided_at.desc().nulls_last(), TaskExecutionReview.created_at.desc())
    )).scalars())
    if not reviews:
        raise CompletionRefused(
            COMPLETION_NO_INDEPENDENT_REVIEW,
            "Task cannot be completed: the latest execution has no approved review",
            execution_id=str(execution.id),
        )
    problems: list[str] = []
    self_reviewed = False
    for review in reviews:
        membership = await db.get(ProjectAgentMembership, review.reviewer_membership_id)
        if membership is None:
            problems.append("reviewer membership no longer exists")
            continue
        reviewer_agent_id = await _agent_identity(db, membership.agent_id, membership.sub_agent_id)
        if reviewer_agent_id is None:
            problems.append("reviewer membership has no registered agent")
            continue
        if executor_agent_id is not None and reviewer_agent_id == executor_agent_id:
            self_reviewed = True
            continue
        problem = membership_review_problem(membership, allowed_projects)
        if problem:
            problems.append(problem)
            continue
        return review, reviewer_agent_id
    if self_reviewed and not problems:
        raise CompletionRefused(
            COMPLETION_REVIEWER_IS_EXECUTOR,
            "Task cannot be completed: the approving reviewer is the agent that executed it",
            execution_id=str(execution.id),
        )
    raise CompletionRefused(
        COMPLETION_NO_INDEPENDENT_REVIEW,
        "Task cannot be completed: no approved review comes from an independent, authorized reviewer",
        execution_id=str(execution.id),
        reasons=problems + (["approving reviewer is the executor"] if self_reviewed else []),
    )


async def evaluate_task_completion(
    db: AsyncSession, task: ProjectTask, target_status: str
) -> CompletionProof:
    """Raises CompletionRefused or returns the proof. `task.status` must still
    be the persisted (pre-transition) status."""
    if target_status not in COMPLETION_TARGET_STATUSES:
        raise ValueError(f"not a completion status: {target_status!r}")
    if target_status == "deployed" and task.status != "done":
        raise CompletionRefused(
            DEPLOYED_REQUIRES_DONE,
            f"Task cannot be deployed: it must be done first (status={task.status})",
        )

    blocking = await blocking_task_dependencies(db, task.id)
    if blocking:
        raise CompletionRefused(
            COMPLETION_DEPENDENCIES_OPEN,
            "Task cannot be completed: it has unfinished dependencies",
            blocking=blocking,
        )
    open_subtasks = [
        {"task_id": str(sub_id), "task_number": number, "status": state}
        for sub_id, number, state in (await db.execute(
            select(ProjectTask.id, ProjectTask.number, ProjectTask.status)
            .where(ProjectTask.parent_task_id == task.id, ProjectTask.status.notin_(("done", "deployed")))
        )).all()
    ]
    if open_subtasks:
        raise CompletionRefused(
            COMPLETION_SUBTASKS_OPEN,
            "Task cannot be completed: it has subtasks that are not done",
            blocking=open_subtasks,
        )

    execution = (await db.execute(
        select(TaskExecution)
        .where(TaskExecution.task_id == task.id)
        .order_by(TaskExecution.attempt_number.desc())
        .limit(1)
    )).scalar_one_or_none()
    if execution is None:
        raise CompletionRefused(
            COMPLETION_NO_EXECUTION,
            "Task cannot be completed: it has no execution (register an execution with evidence and an independent review)",
        )
    if execution.status != "verified":
        raise CompletionRefused(
            COMPLETION_EXECUTION_NOT_VERIFIED,
            f"Task cannot be completed: latest execution (attempt {execution.attempt_number}) "
            f"is {execution.status!r}, not verified",
            execution_id=str(execution.id),
        )

    evidence_ref = (execution.evidence_ref or "").strip()
    prefix = evidence_ref.partition(":")[0] if ":" in evidence_ref else ""
    if prefix not in EVIDENCE_PREFIXES:
        raise CompletionRefused(
            COMPLETION_EVIDENCE_INVALID,
            "Task cannot be completed: evidence must be a git:, file: or db: reference",
            execution_id=str(execution.id), evidence_ref=evidence_ref or None,
        )
    ok, reason = await verify_evidence(db, execution)
    if ok is None:
        raise CompletionRefused(
            COMPLETION_EVIDENCE_UNVERIFIED,
            f"Task cannot be completed: evidence could not be verified ({reason})",
            execution_id=str(execution.id), evidence_ref=evidence_ref,
        )
    if not ok:
        raise CompletionRefused(
            COMPLETION_EVIDENCE_INVALID,
            f"Task cannot be completed: evidence did not check out ({reason})",
            execution_id=str(execution.id), evidence_ref=evidence_ref,
        )

    project = await task_project(db, task)
    if project is None:
        raise CompletionRefused(COMPLETION_NO_INDEPENDENT_REVIEW, "Task cannot be resolved to a project")
    mission_ids = await mission_project_ids_for(db, project)
    executor_agent_id = await resolve_executor_agent_id(db, execution)
    review, reviewer_agent_id = await _independent_review(
        db, execution, executor_agent_id, {project.id, *mission_ids}
    )

    if target_status == "deployed" and mission_ids:
        raise CompletionRefused(
            DEPLOYED_WITHOUT_RELEASE,
            "Mission task cannot be deployed without a production release row (environment_releases does not exist yet)",
        )

    integrated_ref: str | None = None
    if mission_ids and prefix == "git":
        repo_project = await _resolve_execution_project(db, execution)
        commit = evidence_ref.partition(":")[2].strip().lower()
        try:
            integrated, why = await commit_is_integrated(
                repo_project.working_directory_path if repo_project else "", commit, MISSION_MAINLINE
            )
        except EvidenceUnverifiable as exc:
            raise CompletionRefused(
                COMPLETION_EVIDENCE_UNVERIFIED,
                f"Mission task cannot be completed: integration could not be verified ({exc})",
                execution_id=str(execution.id), evidence_ref=evidence_ref,
            ) from exc
        if not integrated:
            raise CompletionRefused(
                COMPLETION_NOT_INTEGRATED,
                f"Mission task cannot be completed: commit is not integrated in {MISSION_MAINLINE} ({why})",
                execution_id=str(execution.id), evidence_ref=evidence_ref, mainline=MISSION_MAINLINE,
            )
        integrated_ref = MISSION_MAINLINE

    return CompletionProof(
        execution_id=execution.id,
        evidence_ref=evidence_ref,
        review_id=review.id,
        reviewer_agent_id=reviewer_agent_id,
        executor_agent_id=executor_agent_id,
        integrated_ref=integrated_ref,
    )


async def assert_task_completion_allowed(
    db: AsyncSession, task: ProjectTask, target_status: str, principal: ActorPrincipal | None = None
) -> CompletionProof:
    """§4.1's entry point: 409 `{code, message, ...}` when refused."""
    try:
        return await evaluate_task_completion(db, task, target_status)
    except CompletionRefused as exc:
        raise exc.to_http() from exc


def completion_audit_event(
    task: ProjectTask,
    target_status: str,
    principal: ActorPrincipal,
    proof: CompletionProof,
    *,
    via: str,
    extra: dict[str, Any] | None = None,
) -> AuditEvent:
    """`task_completed`/`task_deployed`, actor = the authenticated principal."""
    payload: dict[str, Any] = {
        "via": via,
        "principal_type": principal.principal_type,
        "principal_id": str(principal.principal_id),
        "proof": proof.as_payload(),
    }
    if task.planning_item_id:
        payload["planning_item_id"] = str(task.planning_item_id)
    if task.change_request_id:
        payload["change_request_id"] = str(task.change_request_id)
    if extra:
        payload.update(extra)
    return AuditEvent(
        entity_type="project_task",
        entity_id=task.id,
        event_type="task_deployed" if target_status == "deployed" else "task_completed",
        actor=principal.display_name,
        payload=payload,
    )


async def principal_from_authorization(db: AsyncSession, authorization: str | None) -> ActorPrincipal:
    """The authenticated principal behind a raw Authorization header (routes
    that read the header themselves, like PATCH /tasks)."""
    from fastapi.security import HTTPAuthorizationCredentials

    from app.core.deps import get_actor_principal

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Authentication required")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=authorization[7:].strip())
    return await get_actor_principal(credentials, db)


async def assert_principal_may_review(
    db: AsyncSession, principal: ActorPrincipal, membership: ProjectAgentMembership
) -> dict[str, Any] | None:
    """§4.1: an `agt_` caller only creates/decides reviews for its own
    membership; a human must be an admin, recording an agent's review
    (manual verification) -- returned as the `recorded_by` audit payload."""
    reviewer_agent_id = await _agent_identity(db, membership.agent_id, membership.sub_agent_id)
    if principal.principal_type == "agent":
        if reviewer_agent_id != principal.principal_id:
            raise HTTPException(403, "An agent can only create or decide reviews for its own membership")
        return None
    if not principal.is_admin:
        raise HTTPException(403, "Only an admin can record a review on behalf of an agent")
    if reviewer_agent_id is None:
        raise HTTPException(422, "reviewer_membership_id must belong to a registered agent")
    return {
        "recorded_by": principal.display_name,
        "recorded_by_id": str(principal.principal_id),
        "manual_verification": True,
        "reviewer_agent_id": str(reviewer_agent_id),
    }
