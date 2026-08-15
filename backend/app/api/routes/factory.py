"""Software Factory cockpit routes.

Mounted at /api/v1/factory (this router owns its full prefix per the
foundation convention — main.py does not add any prefix).

This is an **aggregation-only domain**: it owns no table of its own, in the
same spirit as `foundation.py`/`system_control.py`, except that it reads the
database instead of the host bridge. Every value it returns already lives in
the product, system_scope, backlog, task and governance domains; the router's
only job is to reduce them to the five-phase state the cockpit renders.

Why the unit of a row is the *project* and not the product: a product is the
durable system, and every evolution of it becomes a project that carries the
description of what will be built. Phases 1 (Conception) and 2 (Designer/
System Map) are recorded at product level — `product_concepts` and
`system_blueprints` each hold a UNIQUE FK to `products` — so a project
inherits them from its product; phases 3-5 are project-scoped
(`project_scopes`, `planning_items`, `project_tasks`). The chain is
Product -> Project -> Planning -> Task.

The response is a Product -> Project tree rather than a flat project list,
which is what lets this one screen stand in for the old Products and
Projects pages (both left the sidebar on 2026-07-26): a product with no
project yet is still a row here, instead of being invisible until someone
creates a project for it.

Endpoints:
- GET /api/v1/factory/cockpit -> every product, its versions, and each of
  its projects with the five phases' state.
"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.factory import (
    AgentTelemetryHistoryPoint,
    AgentTelemetryOut,
    AgentTelemetryRow,
    CockpitOut,
    PhaseStatus,
    ProductCockpitRow,
    ProductVersionRow,
    ProjectCockpitRow,
)
from app.api.schemas.task import EXECUTION_TERMINAL_STATUSES
from app.db.base import get_db
from app.db.models.agent import Agent
from app.db.models.backlog import PlanningItem
from app.db.models.channel import ChatChannel
from app.db.models.demand import AgentDemand
from app.db.models.orchestration import ProjectAgentMembership
from app.db.models.pipeline import PipelineTemplate, ProjectPipeline
from app.db.models.product import Product, ProductVersion
from app.db.models.project import Project
from app.db.models.system_scope import (
    ProductConcept,
    ProjectScope,
    SystemBlueprint,
    SystemBlueprintRevision,
)
from app.db.models.task import ProjectTask, TaskAssignment, TaskExecution

router = APIRouter(prefix="/api/v1/factory", tags=["factory"])

# Telemetry history window (Pacote 5): 14-day sparkline, same span as
# DemandsStatsPanel.tsx's existing frontend pattern.
_TELEMETRY_HISTORY_DAYS = 14


# Mapping from each source domain's own status vocabulary to the cockpit's
# four-state traffic light. Kept as explicit dicts rather than heuristics so
# that a new status added to a source domain shows up as "pending" (the
# honest default for "we don't know") instead of being silently coerced into
# a green.
_CONCEPT_STATE = {
    "draft": "in_progress",
    "in_review": "in_progress",
    "approved": "approved",
    "rework": "blocked",
    "hold": "blocked",
    "rejected": "blocked",
    "superseded": "pending",
}

_BLUEPRINT_STATE = {
    "draft": "in_progress",
    "in_review": "in_progress",
    "approved": "approved",
    "superseded": "pending",
}

_SCOPE_STATE = {
    "draft": "in_progress",
    "in_review": "in_progress",
    "baselined": "approved",
    "superseded": "pending",
}

# Planning item statuses that count as "this planning group is finished".
_PLANNING_DONE = {"done"}
# ...and the ones that mean it will never be finished, so they must not drag
# the phase's progress down forever.
_PLANNING_CLOSED = {"done", "rejected", "cancelled"}

_TASK_DONE = {"done", "deployed"}
_TASK_CLOSED = {"done", "deployed", "cancelled"}
_TASK_BLOCKED = {"blocked"}


def _counted_state(total: int, done: int, blocked: bool = False) -> str:
    """Reduce a done/total pair to a phase state.

    An empty set is "pending", not "approved" — zero of zero tasks done does
    not mean the phase is done; it means nothing has been broken down yet.
    """
    if blocked:
        return "blocked"
    if total == 0:
        return "pending"
    if done >= total:
        return "approved"
    if done > 0:
        return "in_progress"
    return "in_progress"


@router.get("/cockpit", response_model=CockpitOut)
async def get_cockpit(db: AsyncSession = Depends(get_db)) -> CockpitOut:
    """Multi-project cockpit: the five phases' state per project.

    Reads only; it never advances a phase — approving one stays the
    responsibility of the domain that owns it, so the cockpit can't become a
    back door around the approval gates.
    """
    # --- every product, its versions, and its projects --------------------
    # Product is the root and the joins are outer: a product with no version
    # yet, or a version with no project, still has to appear -- this screen
    # replaced the Products/Projects pages, so anything it drops becomes
    # unreachable rather than merely unlisted.
    products = list(
        (await db.execute(select(Product).order_by(Product.name))).scalars().all()
    )
    product_ids = {product.id for product in products}

    version_rows = list(
        (
            await db.execute(
                select(ProductVersion).order_by(ProductVersion.product_id, ProductVersion.version)
            )
        )
        .scalars()
        .all()
    )
    versions_by_product: dict[uuid.UUID, list[ProductVersion]] = {}
    version_by_id: dict[uuid.UUID, ProductVersion] = {}
    for version in version_rows:
        versions_by_product.setdefault(version.product_id, []).append(version)
        version_by_id[version.id] = version

    rows = (
        await db.execute(
            select(Project, ProductVersion)
            .join(ProductVersion, Project.product_version_id == ProductVersion.id)
            .order_by(Project.name)
        )
    ).all()
    project_ids = [project.id for project, _ in rows]

    # --- phase 1: concept, per product -----------------------------------
    concepts: dict[uuid.UUID, str] = {}
    if product_ids:
        for product_id, status in (
            await db.execute(
                select(ProductConcept.product_id, ProductConcept.status).where(
                    ProductConcept.product_id.in_(product_ids)
                )
            )
        ).all():
            concepts[product_id] = status

    # --- phase 2a: blueprint current revision status, per product --------
    blueprints: dict[uuid.UUID, str] = {}
    if product_ids:
        for product_id, status in (
            await db.execute(
                select(SystemBlueprint.product_id, SystemBlueprintRevision.status)
                .join(
                    SystemBlueprintRevision,
                    SystemBlueprint.current_revision_id == SystemBlueprintRevision.id,
                )
                .where(SystemBlueprint.product_id.in_(product_ids))
            )
        ).all():
            blueprints[product_id] = status

    # --- phase 2b: project scope, latest revision per project ------------
    scopes: dict[uuid.UUID, str] = {}
    if project_ids:
        latest_scope = (
            select(
                ProjectScope.project_id,
                ProjectScope.status,
                func.row_number()
                .over(
                    partition_by=ProjectScope.project_id,
                    order_by=ProjectScope.revision.desc(),
                )
                .label("rn"),
            )
            .where(ProjectScope.project_id.in_(project_ids))
            .subquery()
        )
        for project_id, status in (
            await db.execute(
                select(latest_scope.c.project_id, latest_scope.c.status).where(
                    latest_scope.c.rn == 1
                )
            )
        ).all():
            scopes[project_id] = status

    # --- phase 3: planning groups per project ----------------------------
    planning_by_project: dict[uuid.UUID, dict[str, int]] = {}
    planning_to_project: dict[uuid.UUID, uuid.UUID] = {}
    if project_ids:
        for item_id, project_id, status in (
            await db.execute(
                select(PlanningItem.id, PlanningItem.project_id, PlanningItem.status).where(
                    PlanningItem.project_id.in_(project_ids)
                )
            )
        ).all():
            planning_to_project[item_id] = project_id
            counts = planning_by_project.setdefault(project_id, {"total": 0, "done": 0})
            # Rejected/cancelled groups leave the denominator: they are not
            # work waiting to be done.
            if status in _PLANNING_CLOSED and status not in _PLANNING_DONE:
                continue
            counts["total"] += 1
            if status in _PLANNING_DONE:
                counts["done"] += 1

    # --- phase 4: tasks, reached through their planning item -------------
    task_by_project: dict[uuid.UUID, dict[str, int]] = {}
    if planning_to_project:
        for planning_item_id, status, count in (
            await db.execute(
                select(
                    ProjectTask.planning_item_id,
                    ProjectTask.status,
                    func.count(ProjectTask.id),
                )
                .where(ProjectTask.planning_item_id.in_(planning_to_project.keys()))
                .group_by(ProjectTask.planning_item_id, ProjectTask.status)
            )
        ).all():
            project_id = planning_to_project[planning_item_id]
            counts = task_by_project.setdefault(
                project_id, {"total": 0, "done": 0, "blocked": 0}
            )
            if status in _TASK_CLOSED and status not in _TASK_DONE:
                continue
            counts["total"] += count
            if status in _TASK_DONE:
                counts["done"] += count
            if status in _TASK_BLOCKED:
                counts["blocked"] += count

    # --- cost: sum of TaskExecution.actual_cost, reached the same way as
    # phase 4 (task -> planning item -> project), Pacote 5 --------------
    cost_by_project: dict[uuid.UUID, float] = {}
    if planning_to_project:
        for planning_item_id, total_cost in (
            await db.execute(
                select(
                    ProjectTask.planning_item_id,
                    func.coalesce(func.sum(TaskExecution.actual_cost), 0),
                )
                .join(TaskExecution, TaskExecution.task_id == ProjectTask.id)
                .where(ProjectTask.planning_item_id.in_(planning_to_project.keys()))
                .group_by(ProjectTask.planning_item_id)
            )
        ).all():
            project_id = planning_to_project[planning_item_id]
            cost_by_project[project_id] = cost_by_project.get(project_id, 0) + float(total_cost)

    # --- team + channel (2026-08-05, Software Factory visibility fix):
    # surfaces ProjectAgentMembership/ChatChannel here so the Cockpit --
    # where Marcelo actually looks first -- can finally show whether a
    # project has agents/a room, instead of that being invisible outside
    # ProjectAutomationCard. Same "count per project" shape as the other
    # phase aggregates above, not a new pattern. -----------------------
    team_size_by_project: dict[uuid.UUID, int] = {}
    if project_ids:
        for project_id, count in (
            await db.execute(
                select(ProjectAgentMembership.project_id, func.count(ProjectAgentMembership.id))
                .where(ProjectAgentMembership.project_id.in_(project_ids), ProjectAgentMembership.status == "active")
                .group_by(ProjectAgentMembership.project_id)
            )
        ).all():
            team_size_by_project[project_id] = count

    # First (oldest) channel per project -- a project may in principle have
    # more than one (no UniqueConstraint on ChatChannel.project_id, see its
    # docstring), but the Cockpit only needs a single discoverable link.
    # Postgres has no min(uuid) aggregate, so this picks rn=1 per project
    # ordered by created_at, same row_number()-over-partition pattern the
    # phase-2 scope lookup above already uses.
    channel_by_project: dict[uuid.UUID, uuid.UUID] = {}
    if project_ids:
        first_channel = (
            select(
                ChatChannel.project_id,
                ChatChannel.id,
                func.row_number()
                .over(partition_by=ChatChannel.project_id, order_by=ChatChannel.created_at.asc())
                .label("rn"),
            )
            .where(ChatChannel.project_id.in_(project_ids))
            .subquery()
        )
        for project_id, channel_id in (
            await db.execute(
                select(first_channel.c.project_id, first_channel.c.id).where(first_channel.c.rn == 1)
            )
        ).all():
            channel_by_project[project_id] = channel_id

    # --- active pipeline + template name, per project (2026-08-15) -- same
    # "which development path is this project actually on" the Cockpit
    # otherwise has no way to show, since the Pipelines page isn't reachable
    # from the sidebar. Only the active pipeline (rule 6.2.2: at most one)
    # is relevant here; a project with none simply has no entry. -----------
    pipeline_by_project: dict[uuid.UUID, tuple[str, str | None]] = {}
    if project_ids:
        for project_id, pipeline_name, template_name in (
            await db.execute(
                select(ProjectPipeline.project_id, ProjectPipeline.name, PipelineTemplate.name)
                .outerjoin(PipelineTemplate, ProjectPipeline.template_id == PipelineTemplate.id)
                .where(ProjectPipeline.project_id.in_(project_ids), ProjectPipeline.is_active.is_(True))
            )
        ).all():
            pipeline_by_project[project_id] = (pipeline_name, template_name)

    # --- assemble ---------------------------------------------------------
    projects_by_product: dict[uuid.UUID, list[ProjectCockpitRow]] = {}
    for project, version in rows:
        product_id = version.product_id
        concept_status = concepts.get(product_id)
        blueprint_status = blueprints.get(product_id)
        scope_status = scopes.get(project.id)
        planning = planning_by_project.get(project.id, {"total": 0, "done": 0})
        tasks = task_by_project.get(project.id, {"total": 0, "done": 0, "blocked": 0})

        phase1 = PhaseStatus(
            key="conception",
            state=_CONCEPT_STATE.get(concept_status, "pending") if concept_status else "pending",
            detail=concept_status,
        )

        # Phase 2 is done only when both halves are: the product's blueprint is
        # approved *and* this project's scope delta is baselined. Either one
        # alone leaves the scope unsealed.
        if blueprint_status is None and scope_status is None:
            phase2_state = "pending"
        else:
            halves = [
                _BLUEPRINT_STATE.get(blueprint_status, "pending") if blueprint_status else "pending",
                _SCOPE_STATE.get(scope_status, "pending") if scope_status else "pending",
            ]
            if "blocked" in halves:
                phase2_state = "blocked"
            elif all(h == "approved" for h in halves):
                phase2_state = "approved"
            elif all(h == "pending" for h in halves):
                phase2_state = "pending"
            else:
                phase2_state = "in_progress"
        phase2 = PhaseStatus(
            key="designer",
            state=phase2_state,
            detail=" / ".join(
                filter(None, [blueprint_status and f"map: {blueprint_status}", scope_status and f"scope: {scope_status}"])
            )
            or None,
        )

        phase3 = PhaseStatus(
            key="procedures",
            state=_counted_state(planning["total"], planning["done"]),
            detail=None,
            total=planning["total"],
            done=planning["done"],
        )

        phase4 = PhaseStatus(
            key="execution",
            state=_counted_state(tasks["total"], tasks["done"], blocked=tasks["blocked"] > 0),
            detail=f"{tasks['blocked']} bloqueada(s)" if tasks["blocked"] else None,
            total=tasks["total"],
            done=tasks["done"],
        )

        # Phase 5 has no dedicated store yet (the quality gate/promotion
        # flow is the next one to be built), so it is derived from the
        # product version's own lifecycle rather than invented: a version
        # only reaches published after it has been released.
        phase5_state = {
            "planned": "pending",
            "in_development": "pending",
            "in_test": "in_progress",
            "published": "approved",
            "deprecated": "pending",
        }.get(version.status, "pending")
        phase5 = PhaseStatus(key="quality", state=phase5_state, detail=version.status)

        pipeline_name, pipeline_template_name = pipeline_by_project.get(project.id, (None, None))
        projects_by_product.setdefault(product_id, []).append(
            ProjectCockpitRow(
                project_id=project.id,
                project_name=project.name,
                project_status=project.status,
                project_description=project.description,
                version_id=version.id,
                version_number=version.version,
                version_status=version.status,
                phases=[phase1, phase2, phase3, phase4, phase5],
                planning_count=planning["total"],
                task_count=tasks["total"],
                total_cost=cost_by_project.get(project.id, 0),
                team_size=team_size_by_project.get(project.id, 0),
                channel_id=channel_by_project.get(project.id),
                project_type=project.project_type,
                pipeline_name=pipeline_name,
                pipeline_template_name=pipeline_template_name,
            )
        )

    return CockpitOut(
        products=[
            ProductCockpitRow(
                product_id=product.id,
                product_name=product.name,
                product_status=product.status,
                product_description=product.description,
                application_url=product.application_url,
                application_url_dev=product.application_url_dev,
                concept_status=concepts.get(product.id),
                versions=[
                    ProductVersionRow(
                        version_id=version.id,
                        version_number=version.version,
                        version_status=version.status,
                    )
                    for version in versions_by_product.get(product.id, [])
                ],
                projects=projects_by_product.get(product.id, []),
            )
            for product in products
        ]
    )


@router.get("/agent-telemetry", response_model=AgentTelemetryOut)
async def get_agent_telemetry(db: AsyncSession = Depends(get_db)) -> AgentTelemetryOut:
    """Per-agent execution + dispatch telemetry (Pacote 5).

    Read-only aggregation, same spirit as get_cockpit above. TaskExecution
    has no ORM relationship to Agent -- only to TaskAssignment
    (`assignment_id`, nullable), which itself points at Agent (`agent_id`,
    nullable) -- so every join here is an explicit query, not a
    relationship traversal. Executions and AgentDemand dispatches are two
    independent signals kept separate rather than merged into one number.
    An agent with no execution and no dispatch is simply absent from the
    response -- no fabricated zero row.
    """
    exec_status_rows = (
        await db.execute(
            select(
                TaskAssignment.agent_id,
                TaskExecution.status,
                func.count(TaskExecution.id),
                func.coalesce(func.sum(TaskExecution.actual_cost), 0),
            )
            .join(TaskAssignment, TaskAssignment.id == TaskExecution.assignment_id)
            .where(TaskAssignment.agent_id.is_not(None))
            .group_by(TaskAssignment.agent_id, TaskExecution.status)
        )
    ).all()

    duration_rows = (
        await db.execute(
            select(
                TaskAssignment.agent_id,
                func.avg(func.extract("epoch", TaskExecution.finished_at - TaskExecution.started_at)),
            )
            .join(TaskAssignment, TaskAssignment.id == TaskExecution.assignment_id)
            .where(
                TaskAssignment.agent_id.is_not(None),
                TaskExecution.status.in_(EXECUTION_TERMINAL_STATUSES),
                TaskExecution.started_at.is_not(None),
                TaskExecution.finished_at.is_not(None),
            )
            .group_by(TaskAssignment.agent_id)
        )
    ).all()
    avg_duration_by_agent = {agent_id: float(avg) for agent_id, avg in duration_rows if avg is not None}

    dispatch_rows = (
        await db.execute(
            select(AgentDemand.target_agent_id, AgentDemand.dispatch_status, func.count(AgentDemand.id))
            .where(AgentDemand.target_agent_id.is_not(None))
            .group_by(AgentDemand.target_agent_id, AgentDemand.dispatch_status)
        )
    ).all()

    cutoff = datetime.now(timezone.utc) - timedelta(days=_TELEMETRY_HISTORY_DAYS)
    history_rows = (
        await db.execute(
            select(
                TaskAssignment.agent_id,
                func.date(TaskExecution.created_at),
                func.count(TaskExecution.id),
            )
            .join(TaskAssignment, TaskAssignment.id == TaskExecution.assignment_id)
            .where(TaskAssignment.agent_id.is_not(None), TaskExecution.created_at >= cutoff)
            .group_by(TaskAssignment.agent_id, func.date(TaskExecution.created_at))
        )
    ).all()
    history_by_agent: dict[uuid.UUID, dict[str, int]] = {}
    for agent_id, day, count in history_rows:
        day_str = day.isoformat() if hasattr(day, "isoformat") else str(day)
        history_by_agent.setdefault(agent_id, {})[day_str] = count

    agent_ids = {row[0] for row in exec_status_rows} | {row[0] for row in dispatch_rows}
    if not agent_ids:
        return AgentTelemetryOut(agents=[])

    agent_names = {
        agent.id: agent.name
        for agent in (await db.execute(select(Agent).where(Agent.id.in_(agent_ids)))).scalars()
    }

    exec_by_agent: dict[uuid.UUID, dict[str, float]] = {}
    for agent_id, status, count, cost in exec_status_rows:
        bucket = exec_by_agent.setdefault(
            agent_id, {"total": 0, "successful": 0, "failed": 0, "other": 0, "cost": 0.0}
        )
        bucket["total"] += count
        bucket["cost"] += float(cost)
        if status in EXECUTION_TERMINAL_STATUSES:
            bucket["successful"] += count
        elif status == "failed":
            bucket["failed"] += count
        else:
            bucket["other"] += count

    dispatch_by_agent: dict[uuid.UUID, dict[str, int]] = {}
    for agent_id, dispatch_status, count in dispatch_rows:
        bucket = dispatch_by_agent.setdefault(agent_id, {"total": 0, "completed": 0, "failed": 0})
        bucket["total"] += count
        if dispatch_status == "completed":
            bucket["completed"] += count
        elif dispatch_status == "failed":
            bucket["failed"] += count

    rows: list[AgentTelemetryRow] = []
    for agent_id in agent_ids:
        name = agent_names.get(agent_id)
        if name is None:
            # Referenced by an execution/dispatch but the Agent row itself
            # is gone -- skip rather than show a blank/UUID name.
            continue
        execs = exec_by_agent.get(agent_id, {"total": 0, "successful": 0, "failed": 0, "other": 0, "cost": 0.0})
        dispatch = dispatch_by_agent.get(agent_id, {"total": 0, "completed": 0, "failed": 0})
        success_denominator = execs["successful"] + execs["failed"]
        dispatch_denominator = dispatch["completed"] + dispatch["failed"]
        history = [
            AgentTelemetryHistoryPoint(date=day, count=count)
            for day, count in sorted(history_by_agent.get(agent_id, {}).items())
        ]
        rows.append(
            AgentTelemetryRow(
                agent_id=agent_id,
                agent_name=name,
                executions_total=int(execs["total"]),
                executions_successful=int(execs["successful"]),
                executions_failed=int(execs["failed"]),
                executions_other=int(execs["other"]),
                success_rate=execs["successful"] / success_denominator if success_denominator else None,
                avg_duration_seconds=avg_duration_by_agent.get(agent_id),
                total_cost=execs["cost"],
                dispatch_total=dispatch["total"],
                dispatch_completed=dispatch["completed"],
                dispatch_failed=dispatch["failed"],
                dispatch_success_rate=dispatch["completed"] / dispatch_denominator if dispatch_denominator else None,
                history=history,
            )
        )

    rows.sort(key=lambda row: row.agent_name)
    return AgentTelemetryOut(agents=rows)
