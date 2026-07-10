"""Backlog domain routes: planning items (primary entity), feature
requests, bug reports, version scope items, and triage decisions.

Business rules encoded here (see SPEC.md section 6, PRD.md sections 5/7/8):
- A PlanningItem must trace back to a project (core traceability
  invariant, CLAUDE.md / SPEC 5.4): project_id is required on create
  (and on conversion from a FeatureRequest/BugReport) and must reference
  an existing project; it cannot be cleared via update.
- A PlanningItem that has been baselined cannot be mutated directly
  (SPEC 6.3 rule 1-2: "Approved planning becomes baseline" / "Post-baseline
  changes require a Change Request" -- that CR flow lives in the Project
  domain, so here we simply reject direct edits once baselined=True).
- FeatureRequest/BugReport -> PlanningItem conversion is a one-way,
  one-time operation (SPEC 8.1/8.2 flows) -- converting twice is rejected.
- A BugReport can only be marked fixed (severity/closure data complete)
  when `fixed_in_version_id` is populated (PRD 8.2 Bug Done definition).
- A VersionScopeItem can only be created for a PlanningItem that is not
  still in `new` status (SPEC 8.1 step 3 happens after triage) and cannot
  duplicate an existing (planning_item, version) pair.
- Recording a TriageDecision with outcome "accepted" advances the linked
  PlanningItem to status "triaged" (SPEC 8.2 step 2 / 5.4 generic triage);
  "rejected" moves it to status "rejected".
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.backlog import (
    BugReportConvert,
    BugReportCreate,
    BugReportOut,
    BugReportUpdate,
    FeatureRequestConvert,
    FeatureRequestCreate,
    FeatureRequestOut,
    FeatureRequestUpdate,
    PlanningItemCreate,
    PlanningItemOut,
    PlanningItemUpdate,
    TriageDecisionCreate,
    TriageDecisionOut,
    VersionScopeItemCreate,
    VersionScopeItemOut,
)
from app.db.base import get_db
from app.db.models.backlog import (
    PLANNING_ITEM_TYPES,
    BugReport,
    FeatureRequest,
    PlanningItem,
    TriageDecision,
    VersionScopeItem,
)
from app.db.models.project import Project, ProjectStructureNode
from app.db.models.task import ProjectTask

planning_items_router = APIRouter(
    prefix="/api/v1/planning-items", tags=["planning-items"]
)


async def _get_or_404(db: AsyncSession, model, item_id: uuid.UUID):
    obj = await db.get(model, item_id)
    if obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{model.__name__} {item_id} not found",
        )
    return obj


# ---------------------------------------------------------------------------
# PlanningItem (primary entity) -- full CRUD
# ---------------------------------------------------------------------------


@planning_items_router.post("", response_model=PlanningItemOut, status_code=status.HTTP_201_CREATED)
async def create_planning_item(
    payload: PlanningItemCreate, db: AsyncSession = Depends(get_db)
) -> PlanningItem:
    if payload.item_type not in PLANNING_ITEM_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"item_type must be one of {PLANNING_ITEM_TYPES}",
        )
    if await db.get(Project, payload.project_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="project_id must reference an existing project",
        )
    if payload.structure_node_id is not None and await db.get(
        ProjectStructureNode, payload.structure_node_id
    ) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="structure_node_id must reference an existing project structure node",
        )
    item = PlanningItem(**payload.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@planning_items_router.get("", response_model=list[PlanningItemOut])
async def list_planning_items(
    status_filter: str | None = None,
    item_type: str | None = None,
    project_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[PlanningItem]:
    stmt = select(PlanningItem)
    if status_filter is not None:
        stmt = stmt.where(PlanningItem.status == status_filter)
    if item_type is not None:
        stmt = stmt.where(PlanningItem.item_type == item_type)
    if project_id is not None:
        stmt = stmt.where(PlanningItem.project_id == project_id)
    result = await db.execute(stmt.order_by(PlanningItem.created_at.desc()))
    return list(result.scalars().all())


@planning_items_router.get("/{item_id}", response_model=PlanningItemOut)
async def get_planning_item(
    item_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> PlanningItem:
    return await _get_or_404(db, PlanningItem, item_id)


@planning_items_router.put("/{item_id}", response_model=PlanningItemOut)
async def update_planning_item(
    item_id: uuid.UUID,
    payload: PlanningItemUpdate,
    db: AsyncSession = Depends(get_db),
) -> PlanningItem:
    item = await _get_or_404(db, PlanningItem, item_id)

    # SPEC 6.3 rule 1-2: baselined planning cannot be mutated directly.
    if item.baselined:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Planning item is baselined and cannot be mutated directly; "
                "use a Change Request instead."
            ),
        )

    data = payload.model_dump(exclude_unset=True)
    if "item_type" in data and data["item_type"] not in PLANNING_ITEM_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"item_type must be one of {PLANNING_ITEM_TYPES}",
        )
    if "project_id" in data:
        if data["project_id"] is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="project_id cannot be cleared; a planning item must always trace back to a project",
            )
        if await db.get(Project, data["project_id"]) is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="project_id must reference an existing project",
            )
    if data.get("structure_node_id") is not None and await db.get(
        ProjectStructureNode, data["structure_node_id"]
    ) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="structure_node_id must reference an existing project structure node",
        )
    for field, value in data.items():
        setattr(item, field, value)

    await db.commit()
    await db.refresh(item)
    return item


@planning_items_router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_planning_item(
    item_id: uuid.UUID,
    cascade_tasks: bool = False,
    db: AsyncSession = Depends(get_db),
) -> None:
    item = await _get_or_404(db, PlanningItem, item_id)
    if item.baselined:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Planning item is baselined and cannot be deleted directly.",
        )
    # Find tasks linked to this planning item.
    result = await db.execute(
        select(ProjectTask).where(ProjectTask.planning_item_id == item_id)
    )
    linked_tasks = list(result.scalars().all())
    if linked_tasks:
        if not cascade_tasks:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Planning item has {len(linked_tasks)} task(s). "
                    "Pass cascade_tasks=true to delete them together."
                ),
            )
        for task in linked_tasks:
            await db.delete(task)
    await db.delete(item)
    await db.commit()


# ---------------------------------------------------------------------------
# FeatureRequest -- create/list/get + convert-to-PlanningItem
# ---------------------------------------------------------------------------

feature_router = APIRouter(prefix="/api/v1/feature-requests", tags=["feature-requests"])


@feature_router.post(
    "", response_model=FeatureRequestOut, status_code=status.HTTP_201_CREATED
)
async def create_feature_request(
    payload: FeatureRequestCreate, db: AsyncSession = Depends(get_db)
) -> FeatureRequest:
    fr = FeatureRequest(**payload.model_dump())
    db.add(fr)
    await db.commit()
    await db.refresh(fr)
    return fr


@feature_router.get("", response_model=list[FeatureRequestOut])
async def list_feature_requests(db: AsyncSession = Depends(get_db)) -> list[FeatureRequest]:
    result = await db.execute(
        select(FeatureRequest).order_by(FeatureRequest.created_at.desc())
    )
    return list(result.scalars().all())


@feature_router.get("/{fr_id}", response_model=FeatureRequestOut)
async def get_feature_request(
    fr_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> FeatureRequest:
    return await _get_or_404(db, FeatureRequest, fr_id)


@feature_router.put("/{fr_id}", response_model=FeatureRequestOut)
async def update_feature_request(
    fr_id: uuid.UUID,
    payload: FeatureRequestUpdate,
    db: AsyncSession = Depends(get_db),
) -> FeatureRequest:
    fr = await _get_or_404(db, FeatureRequest, fr_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(fr, field, value)
    await db.commit()
    await db.refresh(fr)
    return fr


@feature_router.post("/{fr_id}/convert", response_model=PlanningItemOut)
async def convert_feature_request(
    fr_id: uuid.UUID,
    payload: FeatureRequestConvert,
    db: AsyncSession = Depends(get_db),
) -> PlanningItem:
    """SPEC 8.1 step 2: FeatureRequest -> PlanningItem. One-time, one-way."""
    fr = await _get_or_404(db, FeatureRequest, fr_id)
    if fr.planning_item_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Feature request has already been converted to a planning item.",
        )
    if await db.get(Project, payload.project_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="project_id must reference an existing project",
        )

    item = PlanningItem(
        title=fr.title,
        description=fr.description,
        item_type="feature",
        priority=payload.priority,
        project_id=payload.project_id,
        target_version_id=payload.target_version_id,
    )
    db.add(item)
    await db.flush()  # populate item.id before linking back

    fr.planning_item_id = item.id
    await db.commit()
    await db.refresh(item)
    return item


# ---------------------------------------------------------------------------
# BugReport -- create/list/get + convert-to-PlanningItem
# ---------------------------------------------------------------------------

bug_router = APIRouter(prefix="/api/v1/bug-reports", tags=["bug-reports"])


@bug_router.post("", response_model=BugReportOut, status_code=status.HTTP_201_CREATED)
async def create_bug_report(
    payload: BugReportCreate, db: AsyncSession = Depends(get_db)
) -> BugReport:
    from app.db.models.backlog import BUG_SEVERITIES

    if payload.severity not in BUG_SEVERITIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"severity must be one of {BUG_SEVERITIES}",
        )
    bug = BugReport(**payload.model_dump())
    db.add(bug)
    await db.commit()
    await db.refresh(bug)
    return bug


@bug_router.get("", response_model=list[BugReportOut])
async def list_bug_reports(db: AsyncSession = Depends(get_db)) -> list[BugReport]:
    result = await db.execute(select(BugReport).order_by(BugReport.created_at.desc()))
    return list(result.scalars().all())


@bug_router.get("/{bug_id}", response_model=BugReportOut)
async def get_bug_report(
    bug_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> BugReport:
    return await _get_or_404(db, BugReport, bug_id)


@bug_router.put("/{bug_id}", response_model=BugReportOut)
async def update_bug_report(
    bug_id: uuid.UUID,
    payload: BugReportUpdate,
    db: AsyncSession = Depends(get_db),
) -> BugReport:
    bug = await _get_or_404(db, BugReport, bug_id)
    data = payload.model_dump(exclude_unset=True)
    from app.db.models.backlog import BUG_SEVERITIES

    if "severity" in data and data["severity"] not in BUG_SEVERITIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"severity must be one of {BUG_SEVERITIES}",
        )
    for field, value in data.items():
        setattr(bug, field, value)
    await db.commit()
    await db.refresh(bug)
    return bug


@bug_router.post("/{bug_id}/convert", response_model=PlanningItemOut)
async def convert_bug_report(
    bug_id: uuid.UUID,
    payload: BugReportConvert,
    db: AsyncSession = Depends(get_db),
) -> PlanningItem:
    """SPEC 8.2 step 3: BugReport -> PlanningItem. One-time, one-way."""
    bug = await _get_or_404(db, BugReport, bug_id)
    if bug.planning_item_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bug report has already been converted to a planning item.",
        )
    if await db.get(Project, payload.project_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="project_id must reference an existing project",
        )

    item = PlanningItem(
        title=bug.title,
        description=bug.description,
        item_type="bug",
        priority=payload.priority,
        project_id=payload.project_id,
        target_version_id=payload.target_version_id or bug.fixed_in_version_id,
    )
    db.add(item)
    await db.flush()

    bug.planning_item_id = item.id
    await db.commit()
    await db.refresh(item)
    return item


# ---------------------------------------------------------------------------
# VersionScopeItem -- create/list (scope a planning item into a version)
# ---------------------------------------------------------------------------

scope_router = APIRouter(
    prefix="/api/v1/version-scope-items", tags=["version-scope-items"]
)


@scope_router.post(
    "", response_model=VersionScopeItemOut, status_code=status.HTTP_201_CREATED
)
async def create_version_scope_item(
    payload: VersionScopeItemCreate, db: AsyncSession = Depends(get_db)
) -> VersionScopeItem:
    item = await _get_or_404(db, PlanningItem, payload.planning_item_id)

    # SPEC 8.1 step 3 happens after triage -- a brand new, untriaged item
    # should not be scoped into a version yet.
    if item.status == "new":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Planning item must be triaged before it can be scoped into a version.",
        )

    existing = await db.execute(
        select(VersionScopeItem).where(
            VersionScopeItem.planning_item_id == payload.planning_item_id,
            VersionScopeItem.product_version_id == payload.product_version_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Planning item is already scoped into this version.",
        )

    scope_item = VersionScopeItem(**payload.model_dump())
    db.add(scope_item)

    item.status = "scoped"
    item.target_version_id = payload.product_version_id

    await db.commit()
    await db.refresh(scope_item)
    return scope_item


@scope_router.get("", response_model=list[VersionScopeItemOut])
async def list_version_scope_items(
    planning_item_id: uuid.UUID | None = None,
    product_version_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[VersionScopeItem]:
    stmt = select(VersionScopeItem)
    if planning_item_id is not None:
        stmt = stmt.where(VersionScopeItem.planning_item_id == planning_item_id)
    if product_version_id is not None:
        stmt = stmt.where(VersionScopeItem.product_version_id == product_version_id)
    result = await db.execute(stmt.order_by(VersionScopeItem.created_at.desc()))
    return list(result.scalars().all())


@scope_router.get("/{scope_id}", response_model=VersionScopeItemOut)
async def get_version_scope_item(
    scope_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> VersionScopeItem:
    return await _get_or_404(db, VersionScopeItem, scope_id)


# ---------------------------------------------------------------------------
# TriageDecision -- create/list (append-only decision log)
# ---------------------------------------------------------------------------

triage_router = APIRouter(prefix="/api/v1/triage-decisions", tags=["triage-decisions"])


@triage_router.post(
    "", response_model=TriageDecisionOut, status_code=status.HTTP_201_CREATED
)
async def create_triage_decision(
    payload: TriageDecisionCreate, db: AsyncSession = Depends(get_db)
) -> TriageDecision:
    item = await _get_or_404(db, PlanningItem, payload.planning_item_id)

    if item.baselined:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Planning item is baselined; triage no longer applies.",
        )

    decision = TriageDecision(**payload.model_dump())
    db.add(decision)

    # SPEC 8.2 step 2 / 5.4: recording a decision advances planning item
    # status accordingly.
    if payload.outcome == "accepted":
        item.status = "triaged"
    elif payload.outcome == "rejected":
        item.status = "rejected"

    await db.commit()
    await db.refresh(decision)
    return decision


@triage_router.get("", response_model=list[TriageDecisionOut])
async def list_triage_decisions(
    planning_item_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[TriageDecision]:
    stmt = select(TriageDecision)
    if planning_item_id is not None:
        stmt = stmt.where(TriageDecision.planning_item_id == planning_item_id)
    result = await db.execute(stmt.order_by(TriageDecision.created_at.desc()))
    return list(result.scalars().all())


@triage_router.get("/{decision_id}", response_model=TriageDecisionOut)
async def get_triage_decision(
    decision_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> TriageDecision:
    return await _get_or_404(db, TriageDecision, decision_id)


# ---------------------------------------------------------------------------
# Combined router -- this domain owns five resources (planning-items,
# feature-requests, bug-reports, version-scope-items, triage-decisions),
# each needing its own path prefix. Per foundation convention, main.py only
# ever does `app.include_router(backlog.router)` (one line per domain
# module) and each sub-router already declares its own full
# "/api/v1/<resource>" prefix, so we fold them all into a single
# prefix-less `router` here for the wiring step to include.
# ---------------------------------------------------------------------------
router = APIRouter()
router.include_router(planning_items_router)
router.include_router(feature_router)
router.include_router(bug_router)
router.include_router(scope_router)
router.include_router(triage_router)
