"""Project domain routes.

Mounted at /api/v1/projects (this router owns its full prefix per the
foundation convention — main.py does not add any prefix).

Endpoints:
- Project:        full CRUD at /api/v1/projects[/{project_id}]
- ProjectPlan:    nested full CRUD at /api/v1/projects/{project_id}/plans[...]
                  plus POST .../plans/{plan_id}/approve
- PlanBaseline:   create+list at /api/v1/projects/{project_id}/baselines,
                  get at /api/v1/projects/baselines/{baseline_id}
- ChangeRequest:  create+list at /api/v1/projects/{project_id}/change-requests,
                  get+update at /api/v1/projects/change-requests/{cr_id}
- ProjectStructureNode: full CRUD at
                  /api/v1/projects/{project_id}/structure-nodes[...] and
                  /api/v1/projects/structure-nodes/{node_id}; is_locked
                  enforcement mirrors the Artifact domain (see
                  app/api/routes/artifact.py docstring).
- Project files:  generic file-manager browse/read/write/create/rename/
                  delete over the project's working_directory_path, at
                  /api/v1/projects/{project_id}/files[...] -- see the
                  "Project file browser" section near the bottom of this
                  module for why this proxies to the host chat bridge
                  rather than touching the filesystem directly.

Business rules encoded here (SPEC.md section 6.3 Planning Rules):
1. "Approved planning becomes baseline" -> a ProjectPlan must be in status
   "approved" before a PlanBaseline can be created from it; baselining
   flips the plan's status to "baselined".
2. "Post-baseline changes require a Change Request" -> once a ProjectPlan
   has at least one PlanBaseline, further direct edits to that plan's
   scope/cost/schedule fields are rejected (422) — the caller must instead
   register a ChangeRequest against the project.
3. ChangeRequest tracks scope/time/cost/feature/bug/agent/skill/
   architecture/security impact flags (modeled in the schema/model layer;
   enforced here only by requiring at least one impact flag to be set,
   otherwise the CR is meaningless noise).
"""
import fnmatch
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.project import (
    ChangeRequestCreate,
    ChangeRequestOut,
    ChangeRequestUpdate,
    ForgeRouterGlobalAuditOut,
    PlanBaselineCreate,
    PlanBaselineOut,
    ProjectCreate,
    ProjectFileContent,
    ProjectFileContentUpdate,
    ProjectFileCreate,
    ProjectFileEntry,
    ProjectFileListing,
    ProjectFileRename,
    ProjectForgeRouterConfigOut,
    ProjectForgeRouterStatusOut,
    ProjectForgeRouterToggle,
    ProjectOut,
    ProjectPlanCreate,
    ProjectPlanOut,
    ProjectPlanUpdate,
    ProjectStructureNodeCreate,
    ProjectStructureNodeOut,
    ProjectStructureNodeUpdate,
    ProjectUpdate,
)
from app.core.config import settings
from app.db.base import get_db
from app.db.models.project import (
    ChangeRequest,
    PlanBaseline,
    Project,
    ProjectForgeRouterConfig,
    ProjectPlan,
    ProjectStructureNode,
)

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


async def _get_project_or_404(db: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


async def _get_plan_or_404(db: AsyncSession, plan_id: uuid.UUID) -> ProjectPlan:
    plan = await db.get(ProjectPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project plan not found")
    return plan


async def _get_structure_node_or_404(
    db: AsyncSession, node_id: uuid.UUID
) -> ProjectStructureNode:
    node = await db.get(ProjectStructureNode, node_id)
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project structure node not found"
        )
    return node


def _assert_node_not_locked(node: ProjectStructureNode) -> None:
    """Advisory "do not touch" enforcement -- mirrors Artifact.is_locked
    (see app/api/routes/artifact.py docstring for the full rationale)."""
    if node.is_locked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Structure node is locked and cannot be modified; unlock it "
                'first via PATCH .../structure-nodes/{id} with {"is_locked": false}.'
            ),
        )


# ---------------------------------------------------------------------------
# Project CRUD
# ---------------------------------------------------------------------------
@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreate, db: AsyncSession = Depends(get_db)) -> Project:
    project = Project(**payload.model_dump())
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("", response_model=list[ProjectOut])
async def list_projects(db: AsyncSession = Depends(get_db)) -> list[Project]:
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    return list(result.scalars().all())


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Project:
    return await _get_project_or_404(db, project_id)


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: uuid.UUID, payload: ProjectUpdate, db: AsyncSession = Depends(get_db)
) -> Project:
    project = await _get_project_or_404(db, project_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    project = await _get_project_or_404(db, project_id)
    await db.delete(project)
    await db.commit()


# ---------------------------------------------------------------------------
# ProjectPlan CRUD (nested under a project)
# ---------------------------------------------------------------------------
@router.post(
    "/{project_id}/plans", response_model=ProjectPlanOut, status_code=status.HTTP_201_CREATED
)
async def create_project_plan(
    project_id: uuid.UUID, payload: ProjectPlanCreate, db: AsyncSession = Depends(get_db)
) -> ProjectPlan:
    await _get_project_or_404(db, project_id)
    plan = ProjectPlan(project_id=project_id, **payload.model_dump())
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan


@router.get("/{project_id}/plans", response_model=list[ProjectPlanOut])
async def list_project_plans(
    project_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[ProjectPlan]:
    await _get_project_or_404(db, project_id)
    result = await db.execute(
        select(ProjectPlan)
        .where(ProjectPlan.project_id == project_id)
        .order_by(ProjectPlan.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/plans/{plan_id}", response_model=ProjectPlanOut)
async def get_project_plan(plan_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ProjectPlan:
    return await _get_plan_or_404(db, plan_id)


@router.patch("/plans/{plan_id}", response_model=ProjectPlanOut)
async def update_project_plan(
    plan_id: uuid.UUID, payload: ProjectPlanUpdate, db: AsyncSession = Depends(get_db)
) -> ProjectPlan:
    plan = await _get_plan_or_404(db, plan_id)

    # Business rule 6.3.2: post-baseline changes require a Change Request.
    # Reject direct mutation of scope/schedule/cost fields once a baseline
    # exists for this plan. Status-only transitions (e.g. draft -> approved)
    # are still allowed since they don't rewrite frozen scope.
    mutating_fields = payload.model_dump(exclude_unset=True, exclude={"status"})
    if mutating_fields:
        existing_baseline = await db.execute(
            select(PlanBaseline).where(PlanBaseline.project_plan_id == plan_id).limit(1)
        )
        if existing_baseline.scalars().first() is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "This plan has already been baselined; register a "
                    "ChangeRequest instead of editing it directly."
                ),
            )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(plan, field, value)
    await db.commit()
    await db.refresh(plan)
    return plan


@router.post("/plans/{plan_id}/approve", response_model=ProjectPlanOut)
async def approve_project_plan(
    plan_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> ProjectPlan:
    """Mark a plan as approved -- the precondition for baselining it
    (SPEC.md 6.3.1: "Approved planning becomes baseline")."""
    plan = await _get_plan_or_404(db, plan_id)
    plan.status = "approved"
    plan.approved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(plan)
    return plan


@router.delete("/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_plan(plan_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    plan = await _get_plan_or_404(db, plan_id)
    await db.delete(plan)
    await db.commit()


# ---------------------------------------------------------------------------
# PlanBaseline (create + list; baselines are immutable once created)
# ---------------------------------------------------------------------------
@router.post(
    "/{project_id}/baselines",
    response_model=PlanBaselineOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_plan_baseline(
    project_id: uuid.UUID, payload: PlanBaselineCreate, db: AsyncSession = Depends(get_db)
) -> PlanBaseline:
    await _get_project_or_404(db, project_id)
    plan = await _get_plan_or_404(db, payload.project_plan_id)

    if plan.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="project_plan_id does not belong to this project",
        )

    # Business rule 6.3.1: "Approved planning becomes baseline" -- a plan
    # must be approved before it can be frozen into a baseline.
    if plan.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only an approved plan can be baselined (current status: "
            f"'{plan.status}')",
        )

    baseline = PlanBaseline(
        project_plan_id=plan.id,
        name=payload.name,
        scope_snapshot=plan.scope_summary,
        cost_snapshot=plan.estimated_cost,
        end_date_snapshot=plan.estimated_end_date,
        frozen_at=datetime.now(timezone.utc),
    )
    plan.status = "baselined"
    db.add(baseline)
    await db.commit()
    await db.refresh(baseline)
    return baseline


@router.get("/{project_id}/baselines", response_model=list[PlanBaselineOut])
async def list_plan_baselines(
    project_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[PlanBaseline]:
    await _get_project_or_404(db, project_id)
    result = await db.execute(
        select(PlanBaseline)
        .join(ProjectPlan, PlanBaseline.project_plan_id == ProjectPlan.id)
        .where(ProjectPlan.project_id == project_id)
        .order_by(PlanBaseline.frozen_at.desc())
    )
    return list(result.scalars().all())


@router.get("/baselines/{baseline_id}", response_model=PlanBaselineOut)
async def get_plan_baseline(
    baseline_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> PlanBaseline:
    baseline = await db.get(PlanBaseline, baseline_id)
    if baseline is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan baseline not found")
    return baseline


# ---------------------------------------------------------------------------
# ChangeRequest CRUD
# ---------------------------------------------------------------------------
@router.post(
    "/{project_id}/change-requests",
    response_model=ChangeRequestOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_change_request(
    project_id: uuid.UUID, payload: ChangeRequestCreate, db: AsyncSession = Depends(get_db)
) -> ChangeRequest:
    await _get_project_or_404(db, project_id)

    if payload.plan_baseline_id is not None:
        baseline = await db.get(PlanBaseline, payload.plan_baseline_id)
        if baseline is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="plan_baseline_id does not reference an existing baseline",
            )

    # Business rule 6.3.3: a Change Request must actually track some kind of
    # impact (scope/time/cost/feature/bug/agent/skill/architecture/security).
    # A CR with every flag false carries no governance signal.
    impact_flags = (
        payload.affects_scope,
        payload.affects_schedule,
        payload.affects_cost,
        payload.adds_features,
        payload.removes_features,
        payload.introduces_critical_bug_fix,
        payload.changes_agents,
        payload.changes_skills,
        payload.changes_architecture,
        payload.changes_security,
    )
    if not any(impact_flags):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "A ChangeRequest must declare at least one impact flag "
                "(scope, schedule, cost, features, bug fix, agents, "
                "skills, architecture, or security)."
            ),
        )

    change_request = ChangeRequest(project_id=project_id, **payload.model_dump())
    db.add(change_request)
    await db.commit()
    await db.refresh(change_request)
    return change_request


@router.get("/{project_id}/change-requests", response_model=list[ChangeRequestOut])
async def list_change_requests(
    project_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[ChangeRequest]:
    await _get_project_or_404(db, project_id)
    result = await db.execute(
        select(ChangeRequest)
        .where(ChangeRequest.project_id == project_id)
        .order_by(ChangeRequest.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/change-requests/{cr_id}", response_model=ChangeRequestOut)
async def get_change_request(
    cr_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> ChangeRequest:
    cr = await db.get(ChangeRequest, cr_id)
    if cr is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Change request not found")
    return cr


_CHANGE_REQUEST_IMPACT_FIELDS = (
    "affects_scope",
    "affects_schedule",
    "affects_cost",
    "adds_features",
    "removes_features",
    "introduces_critical_bug_fix",
    "changes_agents",
    "changes_skills",
    "changes_architecture",
    "changes_security",
)


@router.patch("/change-requests/{cr_id}", response_model=ChangeRequestOut)
async def update_change_request(
    cr_id: uuid.UUID, payload: ChangeRequestUpdate, db: AsyncSession = Depends(get_db)
) -> ChangeRequest:
    cr = await db.get(ChangeRequest, cr_id)
    if cr is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Change request not found")

    update_data = payload.model_dump(exclude_unset=True)
    status_update = update_data.pop("status", None)

    # Business rule 6.3.2 analog: once a decision has been recorded, a CR's
    # content is frozen -- only a fresh CR can supersede it, mirroring the
    # plan/baseline immutability rule. Status transitions are always
    # allowed (that's how a decision gets made in the first place).
    if update_data and cr.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"This change request has already been '{cr.status}'; its "
                "content can no longer be edited. Only a pending change "
                "request can be modified."
            ),
        )

    if "plan_baseline_id" in update_data and update_data["plan_baseline_id"] is not None:
        baseline = await db.get(PlanBaseline, update_data["plan_baseline_id"])
        if baseline is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="plan_baseline_id does not reference an existing baseline",
            )

    # Business rule 6.3.3: re-validate that the CR still declares at least
    # one impact flag once the update is merged in -- otherwise an edit
    # could silently clear every flag and leave a governance-meaningless CR.
    if any(field in update_data for field in _CHANGE_REQUEST_IMPACT_FIELDS):
        merged_flags = {field: update_data.get(field, getattr(cr, field)) for field in _CHANGE_REQUEST_IMPACT_FIELDS}
        if not any(merged_flags.values()):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "A ChangeRequest must declare at least one impact flag "
                    "(scope, schedule, cost, features, bug fix, agents, "
                    "skills, architecture, or security)."
                ),
            )

    for field, value in update_data.items():
        setattr(cr, field, value)

    if status_update is not None:
        cr.status = status_update
        if status_update in {"approved", "rejected"}:
            cr.decided_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(cr)
    return cr


@router.delete("/change-requests/{cr_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_change_request(
    cr_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> None:
    cr = await db.get(ChangeRequest, cr_id)
    if cr is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Change request not found")
    if cr.status == "applied":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An applied change request cannot be deleted.",
        )
    await db.delete(cr)
    await db.commit()


# ---------------------------------------------------------------------------
# ProjectStructureNode CRUD (nested under a project)
# ---------------------------------------------------------------------------
@router.post(
    "/{project_id}/structure-nodes",
    response_model=ProjectStructureNodeOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_structure_node(
    project_id: uuid.UUID,
    payload: ProjectStructureNodeCreate,
    db: AsyncSession = Depends(get_db),
) -> ProjectStructureNode:
    await _get_project_or_404(db, project_id)

    if payload.parent_node_id is not None:
        parent = await db.get(ProjectStructureNode, payload.parent_node_id)
        if parent is None or parent.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="parent_node_id must reference an existing node within the same project",
            )

    node = ProjectStructureNode(project_id=project_id, **payload.model_dump())
    db.add(node)
    await db.commit()
    await db.refresh(node)
    return node


@router.get("/{project_id}/structure-nodes", response_model=list[ProjectStructureNodeOut])
async def list_structure_nodes(
    project_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[ProjectStructureNode]:
    await _get_project_or_404(db, project_id)
    result = await db.execute(
        select(ProjectStructureNode)
        .where(ProjectStructureNode.project_id == project_id)
        .order_by(ProjectStructureNode.path, ProjectStructureNode.name)
    )
    return list(result.scalars().all())


@router.get("/structure-nodes/{node_id}", response_model=ProjectStructureNodeOut)
async def get_structure_node(
    node_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> ProjectStructureNode:
    return await _get_structure_node_or_404(db, node_id)


@router.patch("/structure-nodes/{node_id}", response_model=ProjectStructureNodeOut)
async def update_structure_node(
    node_id: uuid.UUID,
    payload: ProjectStructureNodeUpdate,
    db: AsyncSession = Depends(get_db),
) -> ProjectStructureNode:
    node = await _get_structure_node_or_404(db, node_id)

    update_data = payload.model_dump(exclude_unset=True)
    is_locking = update_data.get("is_locked") is True
    is_unlocking = update_data.get("is_locked") is False
    if node.is_locked and not is_unlocking:
        _assert_node_not_locked(node)

    if "parent_node_id" in update_data and update_data["parent_node_id"] is not None:
        parent = await db.get(ProjectStructureNode, update_data["parent_node_id"])
        if parent is None or parent.project_id != node.project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="parent_node_id must reference an existing node within the same project",
            )

    for field, value in update_data.items():
        setattr(node, field, value)
    await db.commit()
    await db.refresh(node)

    # Apply filesystem write-protection whenever is_locked changes and the
    # node has a path relative to the project's working directory.
    if (is_locking or is_unlocking) and node.path:
        project = await db.get(Project, node.project_id)
        if project and project.working_directory_path:
            import os as _os
            full_path = _os.path.join(project.working_directory_path, node.path)
            try:
                await _bridge_request(
                    "POST",
                    "/v1/fs/chmod",
                    json={"path": full_path, "lock": is_locking},
                )
            except Exception:
                # chmod failure is non-fatal: the DB record is already updated.
                # Log and continue so the UI doesn't show an error for a
                # missing or non-existent path.
                pass

    return node


@router.delete("/structure-nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_structure_node(
    node_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> None:
    node = await _get_structure_node_or_404(db, node_id)
    _assert_node_not_locked(node)
    await db.delete(node)
    await db.commit()


# ---------------------------------------------------------------------------
# Project file browser
#
# A project's working_directory_path is an arbitrary path on the HOST, not
# inside this container -- this container has no bind mount for it (unlike
# e.g. the Foundation docs root, which IS mounted, see
# api/routes/foundation_docs.py). So, same reasoning as the chat/terminal
# domains, every actual filesystem operation runs on the host via the chat
# bridge (host-bridge/app.py's /v1/fs/* routes) and this layer only adds the
# project-scoping the bridge itself doesn't do.
#
# Every path in the request/response bodies here is RELATIVE to the
# project's working_directory_path -- never an absolute host path -- so the
# browser never needs to know (or be able to escape) where the project
# actually lives on disk. _safe_join enforces that boundary with pure
# string manipulation (no local .resolve()/filesystem access: the path
# being validated doesn't exist in this container).
#
# A project's working_directory_path is routinely a real source checkout
# (e.g. ForgeHub's own pilot project points at this very repo), which means
# it can contain secret-bearing files like .env -- never expose those
# through this browser, even though it otherwise deliberately shows every
# file. _is_sensitive_path is checked both when listing (filtered out of
# the tree entirely) and on every read/write/rename/delete (rejected with
# 403), so a sensitive file can't be reached even if its exact path is
# guessed/typed directly against the API.
# ---------------------------------------------------------------------------

_SENSITIVE_FILENAME_PATTERNS = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.pfx",
    "*.p12",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "credentials.json",
    "*.credentials.json",
)


def _is_sensitive_path(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(name, pattern) for pattern in _SENSITIVE_FILENAME_PATTERNS)


def _assert_not_sensitive(path: str) -> None:
    if _is_sensitive_path(path):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This file looks like a credential/secret file and cannot be browsed, read, or edited here",
        )


def _bridge_headers() -> dict[str, str]:
    return {"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN}


def _get_working_dir_or_400(project: Project) -> str:
    if not project.working_directory_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project has no working_directory_path set -- set one before browsing files",
        )
    return project.working_directory_path


def _safe_join(root: str, relative: str) -> str:
    """Join a project-relative path onto its working_directory_path,
    rejecting any attempt to escape it via "..". Pure string/Path
    manipulation only -- see module docstring above for why this can't use
    Path.resolve() the way every other domain's path-escape guard does."""
    relative = (relative or "").strip().lstrip("/")
    parts = [p for p in relative.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid path")
    root = root.rstrip("/")
    return "/".join([root, *parts]) if parts else root


def _to_relative(root: str, absolute: str) -> str:
    root = root.rstrip("/")
    if absolute == root:
        return ""
    return absolute[len(root) + 1 :] if absolute.startswith(root + "/") else absolute


async def _bridge_request(method: str, path: str, **kwargs) -> dict:
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.request(
            method, f"{settings.CHAT_BRIDGE_URL}{path}", headers=_bridge_headers(), **kwargs
        )
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=f"Chat bridge: {resp.text[:500]}")
    return resp.json()


@router.get("/{project_id}/files", response_model=ProjectFileListing)
async def list_project_files(
    project_id: uuid.UUID, path: str = "", db: AsyncSession = Depends(get_db)
) -> ProjectFileListing:
    project = await _get_project_or_404(db, project_id)
    working_dir = _get_working_dir_or_400(project)
    abs_path = _safe_join(working_dir, path)
    data = await _bridge_request("GET", "/v1/fs/list", params={"path": abs_path})
    entries = [
        ProjectFileEntry(name=e["name"], path=_to_relative(working_dir, e["path"]), type=e["type"], size=e["size"])
        for e in data["entries"]
        if not _is_sensitive_path(e["name"])
    ]
    return ProjectFileListing(path=_to_relative(working_dir, data["path"]), entries=entries)


@router.get("/{project_id}/files/content", response_model=ProjectFileContent)
async def read_project_file(
    project_id: uuid.UUID, path: str, db: AsyncSession = Depends(get_db)
) -> ProjectFileContent:
    _assert_not_sensitive(path)
    project = await _get_project_or_404(db, project_id)
    working_dir = _get_working_dir_or_400(project)
    abs_path = _safe_join(working_dir, path)
    data = await _bridge_request("GET", "/v1/fs/read", params={"path": abs_path})
    return ProjectFileContent(path=path, content=data["content"])


@router.put("/{project_id}/files/content", response_model=ProjectFileContent)
async def write_project_file(
    project_id: uuid.UUID,
    path: str,
    payload: ProjectFileContentUpdate,
    db: AsyncSession = Depends(get_db),
) -> ProjectFileContent:
    _assert_not_sensitive(path)
    project = await _get_project_or_404(db, project_id)
    working_dir = _get_working_dir_or_400(project)
    abs_path = _safe_join(working_dir, path)
    await _bridge_request("PUT", "/v1/fs/write", json={"path": abs_path, "content": payload.content})
    return ProjectFileContent(path=path, content=payload.content)


@router.post(
    "/{project_id}/files/directory", response_model=ProjectFileEntry, status_code=status.HTTP_201_CREATED
)
async def create_project_directory(
    project_id: uuid.UUID, payload: ProjectFileCreate, db: AsyncSession = Depends(get_db)
) -> ProjectFileEntry:
    _assert_not_sensitive(payload.path)
    project = await _get_project_or_404(db, project_id)
    working_dir = _get_working_dir_or_400(project)
    abs_path = _safe_join(working_dir, payload.path)
    data = await _bridge_request("POST", "/v1/fs/mkdir", json={"path": abs_path})
    return ProjectFileEntry(name=data["name"], path=_to_relative(working_dir, data["path"]), type="dir")


@router.post("/{project_id}/files/new", response_model=ProjectFileEntry, status_code=status.HTTP_201_CREATED)
async def create_project_file(
    project_id: uuid.UUID, payload: ProjectFileCreate, db: AsyncSession = Depends(get_db)
) -> ProjectFileEntry:
    _assert_not_sensitive(payload.path)
    project = await _get_project_or_404(db, project_id)
    working_dir = _get_working_dir_or_400(project)
    abs_path = _safe_join(working_dir, payload.path)
    data = await _bridge_request("POST", "/v1/fs/create-file", json={"path": abs_path})
    return ProjectFileEntry(name=data["name"], path=_to_relative(working_dir, data["path"]), type="file", size=0)


@router.patch("/{project_id}/files", response_model=ProjectFileEntry)
async def rename_project_file(
    project_id: uuid.UUID, payload: ProjectFileRename, db: AsyncSession = Depends(get_db)
) -> ProjectFileEntry:
    _assert_not_sensitive(payload.path)
    _assert_not_sensitive(payload.new_path)
    project = await _get_project_or_404(db, project_id)
    working_dir = _get_working_dir_or_400(project)
    abs_path = _safe_join(working_dir, payload.path)
    abs_new_path = _safe_join(working_dir, payload.new_path)
    data = await _bridge_request("PATCH", "/v1/fs/rename", json={"path": abs_path, "new_path": abs_new_path})
    return ProjectFileEntry(name=data["name"], path=_to_relative(working_dir, data["path"]), type=data["type"])


@router.delete("/{project_id}/files", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_file(
    project_id: uuid.UUID,
    path: str,
    recursive: bool = False,
    db: AsyncSession = Depends(get_db),
) -> None:
    _assert_not_sensitive(path)
    project = await _get_project_or_404(db, project_id)
    working_dir = _get_working_dir_or_400(project)
    abs_path = _safe_join(working_dir, path)
    await _bridge_request("DELETE", "/v1/fs/delete", params={"path": abs_path, "recursive": recursive})


# ---------------------------------------------------------------------------
# Project ForgeRouter integration
# Routes: GET/PUT /{project_id}/forgerouter  (per-project toggle + status)
#         GET /forgerouter/audit              (global-config audit)
#         GET /{project_id}/forgerouter/live  (live filesystem status)
# ---------------------------------------------------------------------------

async def _get_or_create_fr_config(
    db: AsyncSession, project_id: uuid.UUID
) -> ProjectForgeRouterConfig:
    result = await db.execute(
        select(ProjectForgeRouterConfig).where(ProjectForgeRouterConfig.project_id == project_id)
    )
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = ProjectForgeRouterConfig(project_id=project_id)
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return cfg


@router.get("/forgerouter/audit", response_model=ForgeRouterGlobalAuditOut)
async def audit_global_forgerouter() -> ForgeRouterGlobalAuditOut:
    """Scan the host for any global ForgeRouter configurations left behind
    by older installs. Returns findings so the UI can warn and offer to clean."""
    data = await _bridge_request("GET", "/v1/forgerouter/global-audit")
    return ForgeRouterGlobalAuditOut(**data)


@router.get("/{project_id}/forgerouter", response_model=ProjectForgeRouterConfigOut)
async def get_project_forgerouter(
    project_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> ProjectForgeRouterConfig:
    """Return the stored ForgeRouter integration state for this project."""
    await _get_project_or_404(db, project_id)
    return await _get_or_create_fr_config(db, project_id)


@router.put("/{project_id}/forgerouter", response_model=ProjectForgeRouterConfigOut)
async def toggle_project_forgerouter(
    project_id: uuid.UUID,
    payload: ProjectForgeRouterToggle,
    db: AsyncSession = Depends(get_db),
) -> ProjectForgeRouterConfig:
    """Enable or disable ForgeRouter for this project.

    When enabled, config files are written inside the project's
    working_directory_path — never in global user directories.
    When disabled, those config files are removed.
    """
    project = await _get_project_or_404(db, project_id)
    if not project.working_directory_path:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Project has no working_directory_path — set it before configuring ForgeRouter.",
        )

    tools_to_apply = []
    if payload.enabled:
        if payload.claude:
            tools_to_apply.append("claude")
        if payload.codex:
            tools_to_apply.append("codex")
        if payload.antigravity:
            tools_to_apply.append("antigravity")
    else:
        tools_to_apply = ["claude", "codex", "antigravity"]

    await _bridge_request(
        "PUT",
        "/v1/project-forgerouter",
        json={
            "project_path": project.working_directory_path,
            "tools": tools_to_apply,
            "enabled": payload.enabled,
            "api_key": payload.api_key,
        },
    )

    cfg = await _get_or_create_fr_config(db, project_id)
    if payload.enabled:
        cfg.api_key = payload.api_key or cfg.api_key
        cfg.claude_enabled = payload.claude
        cfg.codex_enabled = payload.codex
        cfg.antigravity_enabled = payload.antigravity
    else:
        cfg.claude_enabled = False
        cfg.codex_enabled = False
        cfg.antigravity_enabled = False
    cfg.configured_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(cfg)
    return cfg


@router.get("/{project_id}/forgerouter/live", response_model=ProjectForgeRouterStatusOut)
async def get_project_forgerouter_live(
    project_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> ProjectForgeRouterStatusOut:
    """Check the actual config files on disk (live filesystem status),
    independent of the DB record."""
    project = await _get_project_or_404(db, project_id)
    if not project.working_directory_path:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Project has no working_directory_path.",
        )
    data = await _bridge_request(
        "GET",
        "/v1/project-forgerouter/status",
        params={"project_path": project.working_directory_path},
    )
    return ProjectForgeRouterStatusOut(**data)
