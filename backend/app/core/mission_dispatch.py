"""Mission task dispatch: the run in flight and the allowlisted context (Plano Integrado M0.2c).

Contract: docs/architecture/MCP_MISSION_TOOLS_SPEC.md §0.4 (no second run),
§5.5-§5.7 and §6 (minimal dispatch context by allowlist).

- ``task_run_in_flight`` is the one answer to "does this task already have a
  run?": active, reserved, uncertain, or (missions) queued for later. Assign,
  dispatch and return all read it, so none of them can start or reshuffle work
  while a run may still be writing.
- ``build_mission_dispatch_context`` replaces the free composition of the
  dispatch body for mission tasks only. Every line comes from a listed source
  and each source is recorded in ``context_manifest`` as ``{source, id, hash}``
  (stored in the ``task.dispatched`` audit payload, no column). Nothing else is
  read: no other task's results, no Knowledge Base, Hindsight, memory files,
  personal (Maia) or client (Lara) data. Over 32 KiB is refused
  (``CONTEXT_TOO_LARGE``): the orchestrator splits the task, the builder never
  truncates.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import mission_documents
from app.core.demand_workflow import requires_reconciliation
from app.core.mission import mission_error
from app.db.models.agent import Agent
from app.db.models.artifact import ArtifactVersion, ArtifactVersionStatus
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.mission import MissionAcceptanceCriterion, MissionCriterionTask, ProjectMission
from app.db.models.orchestration import ProjectAgentMembership, TaskExecutionReview
from app.db.models.project import PlanBaselineItem, Project
from app.db.models.task import ProjectTask, TaskDependency, TaskExecution, TaskExecutionTarget

MISSION_CONTEXT_MAX_BYTES = 32 * 1024
OPEN_REVIEW_STATUSES = ("pending", "running")

# The evidence-format instruction every dispatch carries (§6 "constants
# already in use"); the completion-report contract is appended by
# demand.py's _execute_dispatch (core/completion_report.py).
EVIDENCE_INSTRUCTION = (
    "Ao concluir, declare a evidência numa linha própria no formato "
    "'EVIDENCE: <ref>', onde <ref> é um dos:\n"
    "- file:<caminho relativo ao projeto> (arquivo que você criou/alterou)\n"
    "- git:<sha> (commit que contém a mudança)\n"
    "- db:<entity_type>:<uuid> (registro real que você criou, ex: db:project:...)\n"
    "Sem essa linha, a execução fica pendente de verificação manual."
)
MISSION_REPORT_INSTRUCTION = (
    "Esta é uma tarefa de missão: relate a execução com a ferramenta MCP "
    "report_task_execution (status reported|failed|blocked, resumo e evidências). "
    "O relato não conclui a tarefa: ela só fecha depois da verificação da "
    "evidência e de uma revisão independente."
)

_OBJECTIVE_HEADING = re.compile(r"^(#{1,6})\s*(objetivo|objetivos|objective|objectives)\b", re.IGNORECASE)
_HEADING = re.compile(r"^(#{1,6})\s")


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()
    ).hexdigest()


# ---------------------------------------------------------------------------
# Run in flight (§0.4)
# ---------------------------------------------------------------------------
async def task_run_in_flight(db: AsyncSession, task_id: uuid.UUID, *, include_queued: bool = True) -> AgentDemand | None:
    """The task's demand that is running, reserved, of unknown outcome or
    (``include_queued``) waiting in the queue; None when a new run may start.

    A known failure or a completed run is over; an archived demand never runs."""
    rows = (await db.execute(
        select(AgentDemand)
        .where(AgentDemand.origin_type == "task", AgentDemand.origin_id == task_id)
        .where(or_(AgentDemand.status != "archived", AgentDemand.dispatch_status.in_(("dispatched", "running"))))
        .order_by(AgentDemand.created_at.desc())
    )).scalars().all()
    for demand in rows:
        if demand.dispatch_status in ("dispatched", "running"):
            return demand
        if demand.dispatch_status is None and demand.agent_run_id:
            return demand
        if requires_reconciliation(demand):
            return demand
        if include_queued and demand.dispatch_status is None and demand.status != "archived":
            return demand
    return None


def in_flight_error(demand: AgentDemand) -> Exception:
    state = "uncertain" if requires_reconciliation(demand) else (demand.dispatch_status or (
        "reserved" if demand.agent_run_id else "queued"))
    return mission_error(409, "TASK_RUN_IN_FLIGHT",
                         "The task already has a run that is active, reserved, queued or of unknown outcome",
                         demand_id=str(demand.id), demand_number=demand.number, run_state=state,
                         agent_run_id=demand.agent_run_id)


# ---------------------------------------------------------------------------
# Allowlisted context (§6)
# ---------------------------------------------------------------------------
@dataclass
class MissionDispatchContext:
    body: str
    manifest: list[dict[str, Any]] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.body.encode())


def _brief_file(location_uri: str) -> Path | None:
    """The brief's file inside the Docs tree, never outside it."""
    root = Path(mission_documents.MISSION_DOCS_ROOT)
    relative = location_uri.strip().lstrip("/")
    candidates = [relative] + ([relative[len("docs/"):]] if relative.startswith("docs/") else [])
    for candidate in candidates:
        path = (root / candidate).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            continue
        if path.is_file():
            return path
    return None


def objective_section(markdown: str) -> str | None:
    """The brief's objective section: from an Objetivo/Objective heading to the
    next heading of the same or a higher level. None when there is none."""
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        match = _OBJECTIVE_HEADING.match(line)
        if not match:
            continue
        level = len(match.group(1))
        section = []
        for following in lines[index + 1:]:
            heading = _HEADING.match(following)
            if heading and len(heading.group(1)) <= level:
                break
            section.append(following)
        text = "\n".join(section).strip()
        return text or None
    return None


async def _approved_brief(db: AsyncSession, mission: ProjectMission) -> ArtifactVersion | None:
    if mission.brief_artifact_id is None:
        return None
    return (await db.execute(
        select(ArtifactVersion)
        .where(ArtifactVersion.artifact_id == mission.brief_artifact_id,
               ArtifactVersion.status == ArtifactVersionStatus.FINAL)
        .order_by(ArtifactVersion.version_number.desc()).limit(1)
    )).scalar_one_or_none()


async def _correction_reason(db: AsyncSession, task_id: uuid.UUID) -> tuple[str, uuid.UUID, str] | None:
    """The open critique of this task: the latest changes_requested review, or
    the latest return-for-correction reason, whichever is newer."""
    review = (await db.execute(
        select(TaskExecutionReview)
        .join(TaskExecution, TaskExecution.id == TaskExecutionReview.execution_id)
        .where(TaskExecution.task_id == task_id, TaskExecutionReview.status == "changes_requested")
        .order_by(TaskExecutionReview.decided_at.desc().nulls_last(), TaskExecutionReview.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    returned = (await db.execute(
        select(AuditEvent)
        .where(AuditEvent.entity_type == "project_task", AuditEvent.entity_id == task_id,
               AuditEvent.event_type == "mission_task_returned")
        .order_by(AuditEvent.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    candidates = []
    if review is not None and review.feedback:
        candidates.append((review.decided_at or review.created_at, "review_feedback", review.id, review.feedback))
    if returned is not None and (returned.payload or {}).get("reason"):
        candidates.append((returned.created_at, "task_returned", returned.id, returned.payload["reason"]))
    if not candidates:
        return None
    _when, source, row_id, text = max(candidates, key=lambda c: c[0])
    return source, row_id, text


async def build_mission_dispatch_context(
    db: AsyncSession,
    task: ProjectTask,
    *,
    mission: ProjectMission,
    working_path: str | None,
    membership: ProjectAgentMembership | None,
    command_text: str | None = None,
) -> MissionDispatchContext:
    """The dispatch body of a mission task, built only from the §6 allowlist."""
    manifest: list[dict[str, Any]] = []
    parts: list[str] = []

    def note(source: str, row_id: Any, value: Any) -> None:
        manifest.append({"source": source, "id": str(row_id) if row_id is not None else None, "hash": _hash(value)})

    task_fields = {"number": task.number, "title": task.title, "description": task.description,
                   "plan_brief": task.plan_brief, "task_type": task.task_type, "priority": task.priority}
    note("project_task", task.id, task_fields)
    parts.append(f"Task #{task.number}: {task.title}")
    if task.description:
        parts.append(task.description)
    if task.plan_brief:
        parts.append(f"Plano/abordagem:\n{task.plan_brief}")
    parts.append(f"Tipo: {task.task_type} | Prioridade: {task.priority}")

    project = await db.get(Project, mission.project_id)
    mission_lines = [f"Missão: {project.name if project else mission.project_id}"]
    note("mission", mission.project_id, {"name": project.name if project else None})
    if mission.current_baseline_id is not None:
        item = (await db.execute(select(PlanBaselineItem).where(
            PlanBaselineItem.baseline_id == mission.current_baseline_id, PlanBaselineItem.task_id == task.id,
        ))).scalar_one_or_none()
        if item is not None:
            mission_lines.append(f"Baseline: {mission.current_baseline_id} (hash da tarefa {item.content_hash})")
            note("plan_baseline_item", item.id, item.content_hash)
    brief = await _approved_brief(db, mission)
    if brief is not None:
        path = _brief_file(brief.location_uri)
        objective = objective_section(path.read_text(encoding="utf-8", errors="replace")) if path else None
        if objective:
            mission_lines.append(f"Objetivo (brief aprovado, versão {brief.version_number}):\n{objective}")
        note("brief_objective", brief.id, objective)
    parts.append("\n".join(mission_lines))

    criteria = (await db.execute(
        select(MissionAcceptanceCriterion)
        .join(MissionCriterionTask, MissionCriterionTask.criterion_id == MissionAcceptanceCriterion.id)
        .where(MissionCriterionTask.task_id == task.id)
        .order_by(MissionAcceptanceCriterion.code)
    )).scalars().all()
    if criteria:
        lines = ["Critérios de aceite ligados a esta tarefa:"]
        for criterion in criteria:
            lines.append(f"- {criterion.code}: {criterion.statement} (verificação: {criterion.verification_method})")
            note("mission_acceptance_criterion", criterion.id,
                 [criterion.code, criterion.statement, criterion.verification_method])
        parts.append("\n".join(lines))

    predecessors = (await db.execute(
        select(ProjectTask)
        .join(TaskDependency, TaskDependency.depends_on_task_id == ProjectTask.id)
        .where(TaskDependency.task_id == task.id)
        .order_by(ProjectTask.number)
    )).scalars().all()
    if predecessors:
        lines = ["Tarefas predecessoras:"]
        for predecessor in predecessors:
            lines.append(f"- #{predecessor.number} {predecessor.title} ({predecessor.status})")
            note("task_dependency", predecessor.id, [predecessor.number, predecessor.title, predecessor.status])
        parts.append("\n".join(lines))

    execution_lines = []
    if membership is not None:
        execution_lines.append(f"Seu papel: {membership.role}")
        note("project_agent_membership", membership.id, membership.role)
    reviewer = (await db.execute(
        select(Agent.name, TaskExecutionReview.id)
        .join(ProjectAgentMembership, ProjectAgentMembership.id == TaskExecutionReview.reviewer_membership_id)
        .join(Agent, Agent.id == ProjectAgentMembership.agent_id)
        .join(TaskExecution, TaskExecution.id == TaskExecutionReview.execution_id)
        .where(TaskExecution.task_id == task.id, TaskExecutionReview.status.in_(OPEN_REVIEW_STATUSES))
        .order_by(TaskExecutionReview.created_at.desc()).limit(1)
    )).first()
    if reviewer is not None:
        execution_lines.append(f"Revisor: {reviewer[0]}")
        note("task_execution_review", reviewer[1], reviewer[0])
    if working_path:
        execution_lines.append(f"Diretório de trabalho: {working_path}")
        note("working_path", mission.project_id, working_path)
    targets = (await db.execute(
        select(TaskExecutionTarget).where(TaskExecutionTarget.task_id == task.id)
        .order_by(TaskExecutionTarget.kind, TaskExecutionTarget.target_key)
    )).scalars().all()
    for target in targets:
        execution_lines.append(f"Alvo declarado: {target.kind}:{target.target_key}")
        note("task_execution_target", target.id, [target.kind, target.target_key])
    if execution_lines:
        parts.append("\n".join(execution_lines))

    correction = await _correction_reason(db, task.id)
    if correction is not None:
        source, row_id, text = correction
        parts.append(f"Correção pedida:\n{text}")
        note(source, row_id, text)

    if command_text:
        parts.append(f"Instrução adicional:\n{command_text}")
        note("command_text", None, command_text)

    parts.append(EVIDENCE_INSTRUCTION)
    parts.append(MISSION_REPORT_INSTRUCTION)
    note("instructions", None, [EVIDENCE_INSTRUCTION, MISSION_REPORT_INSTRUCTION])

    context = MissionDispatchContext(body="\n\n".join(parts), manifest=manifest)
    if context.size > MISSION_CONTEXT_MAX_BYTES:
        raise mission_error(422, "CONTEXT_TOO_LARGE",
                            "The mission dispatch context exceeds 32 KiB; split the task",
                            size_bytes=context.size, limit_bytes=MISSION_CONTEXT_MAX_BYTES)
    return context
