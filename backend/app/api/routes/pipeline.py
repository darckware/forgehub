"""Pipeline domain routes.

Primary entity: ProjectPipeline (with nested PipelineStage). Secondary
entities (PipelineTemplate + its nested stages/required artifacts,
PipelineStageDependency, PipelineStageRequiredArtifact,
PipelineStageGate) get at least create/list, several get full CRUD
where reasonably scoped.

Business rules encoded here (see docs/SPEC.md section 6.2):
1. Every project must have an active pipeline -> enforced indirectly:
   creating a pipeline for a project that has none simply succeeds;
   we do not auto-create one (that's a project-domain concern), but we
   DO enforce rule 2 below so the invariant "at most one active" holds
   and a caller can always activate one.
2. Only one pipeline can be active per project -> enforced on create
   and on update (activating a pipeline deactivates other active ones
   for the same project).
3. Every stage must define order, status, and type -> enforced by
   required fields on PipelineStageCreate (name, stage_type,
   order_index, status all required/defaulted).
6/7. Stages may require mandatory artifacts; a stage cannot complete if
   mandatory artifacts are missing -> enforced in the stage status
   transition endpoint (advance/complete).
4/5/8. Stages may require approval/verification; cannot complete if
   mandatory gates are not approved -> enforced in the same transition
   endpoint.
9. Blocked stages must prevent dependent stages from advancing ->
   enforced in the same transition endpoint (checks dependency stage
   statuses before allowing a stage to move to "in_progress"/"completed").
10. Release approval allowed only when all required gates pass ->
   exposed via GET .../gates/check endpoint used before any
   release-readiness decision (Release domain, out of scope here, can
   call this check).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas.pipeline import (
    PipelineStageCreate,
    PipelineStageDependencyCreate,
    PipelineStageDependencyOut,
    PipelineStageGateCreate,
    PipelineStageGateOut,
    PipelineStageGateUpdate,
    PipelineStageOut,
    PipelineStageRequiredArtifactCreate,
    PipelineStageRequiredArtifactOut,
    PipelineStageRequiredArtifactUpdate,
    PipelineStageUpdate,
    PipelineTemplateCreate,
    PipelineTemplateOut,
    PipelineTemplateRequiredArtifactCreate,
    PipelineTemplateRequiredArtifactOut,
    PipelineTemplateStageCreate,
    PipelineTemplateStageOut,
    ProjectPipelineCreate,
    ProjectPipelineOut,
    ProjectPipelineUpdate,
)
from app.db.base import get_db
from app.db.models.governance import AuditEvent
from app.db.models.pipeline import (
    PipelineStage,
    PipelineStageDependency,
    PipelineStageGate,
    PipelineStageRequiredArtifact,
    PipelineTemplate,
    PipelineTemplateRequiredArtifact,
    PipelineTemplateStage,
    ProjectPipeline,
)

router = APIRouter(prefix="/api/v1/pipelines", tags=["pipelines"])

_TERMINAL_STAGE_STATUSES = {"completed", "skipped"}
_BLOCKING_STAGE_STATUSES = {"blocked", "failed"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_pipeline_or_404(db: AsyncSession, pipeline_id: uuid.UUID) -> ProjectPipeline:
    result = await db.execute(
        select(ProjectPipeline)
        .where(ProjectPipeline.id == pipeline_id)
        .options(
            selectinload(ProjectPipeline.stages).selectinload(PipelineStage.required_artifacts),
            selectinload(ProjectPipeline.stages).selectinload(PipelineStage.gates),
            selectinload(ProjectPipeline.stages).selectinload(PipelineStage.dependencies),
        )
    )
    pipeline = result.scalar_one_or_none()
    if pipeline is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")
    return pipeline


async def _get_stage_or_404(db: AsyncSession, stage_id: uuid.UUID) -> PipelineStage:
    result = await db.execute(
        select(PipelineStage)
        .where(PipelineStage.id == stage_id)
        .options(
            selectinload(PipelineStage.required_artifacts),
            selectinload(PipelineStage.gates),
            selectinload(PipelineStage.dependencies),
        )
    )
    stage = result.scalar_one_or_none()
    if stage is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage not found")
    return stage


async def _deactivate_other_active_pipelines(db: AsyncSession, project_id: uuid.UUID, exclude_id: uuid.UUID | None = None) -> None:
    """Rule 6.2.2: only one pipeline can be active per project."""
    stmt = select(ProjectPipeline).where(
        ProjectPipeline.project_id == project_id, ProjectPipeline.is_active.is_(True)
    )
    if exclude_id is not None:
        stmt = stmt.where(ProjectPipeline.id != exclude_id)
    result = await db.execute(stmt)
    for other in result.scalars().all():
        other.is_active = False


# ---------------------------------------------------------------------------
# PipelineTemplate (secondary entity -- full CRUD, reasonably scoped)
# ---------------------------------------------------------------------------


@router.post("/templates", response_model=PipelineTemplateOut, status_code=status.HTTP_201_CREATED)
async def create_template(payload: PipelineTemplateCreate, db: AsyncSession = Depends(get_db)) -> PipelineTemplate:
    existing = await db.execute(select(PipelineTemplate).where(PipelineTemplate.name == payload.name))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Template name already exists")
    template = PipelineTemplate(**payload.model_dump())
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


@router.get("/templates", response_model=list[PipelineTemplateOut])
async def list_templates(db: AsyncSession = Depends(get_db)) -> list[PipelineTemplate]:
    result = await db.execute(select(PipelineTemplate).order_by(PipelineTemplate.created_at))
    return list(result.scalars().all())


@router.get("/templates/{template_id}", response_model=PipelineTemplateOut)
async def get_template(template_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> PipelineTemplate:
    template = await db.get(PipelineTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return template


@router.patch("/templates/{template_id}", response_model=PipelineTemplateOut)
async def update_template(
    template_id: uuid.UUID, payload: PipelineTemplateCreate, db: AsyncSession = Depends(get_db)
) -> PipelineTemplate:
    template = await db.get(PipelineTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(template, field, value)
    await db.commit()
    await db.refresh(template)
    return template


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(template_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    template = await db.get(PipelineTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    await db.delete(template)
    await db.commit()


# ---------------------------------------------------------------------------
# PipelineTemplateStage (secondary -- create/list, plus get/delete)
# ---------------------------------------------------------------------------


@router.post(
    "/template-stages", response_model=PipelineTemplateStageOut, status_code=status.HTTP_201_CREATED
)
async def create_template_stage(
    payload: PipelineTemplateStageCreate, db: AsyncSession = Depends(get_db)
) -> PipelineTemplateStage:
    template = await db.get(PipelineTemplate, payload.template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    stage = PipelineTemplateStage(**payload.model_dump())
    db.add(stage)
    await db.commit()
    await db.refresh(stage)
    return stage


@router.get("/template-stages", response_model=list[PipelineTemplateStageOut])
async def list_template_stages(
    template_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db)
) -> list[PipelineTemplateStage]:
    stmt = select(PipelineTemplateStage).order_by(PipelineTemplateStage.order_index)
    if template_id is not None:
        stmt = stmt.where(PipelineTemplateStage.template_id == template_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.patch("/template-stages/{stage_id}", response_model=PipelineTemplateStageOut)
async def update_template_stage(
    stage_id: uuid.UUID,
    payload: PipelineTemplateStageCreate,
    db: AsyncSession = Depends(get_db),
) -> PipelineTemplateStage:
    stage = await db.get(PipelineTemplateStage, stage_id)
    if stage is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template stage not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(stage, field, value)
    await db.commit()
    await db.refresh(stage)
    return stage


@router.delete("/template-stages/{stage_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template_stage(stage_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    stage = await db.get(PipelineTemplateStage, stage_id)
    if stage is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template stage not found")
    await db.delete(stage)
    await db.commit()


# ---------------------------------------------------------------------------
# Import pipeline → template
# ---------------------------------------------------------------------------

from pydantic import BaseModel as _BaseModel


class ImportAsTemplatePayload(_BaseModel):
    pipeline_id: uuid.UUID
    name: str
    description: str | None = None


@router.post("/import-as-template", response_model=PipelineTemplateOut, status_code=status.HTTP_201_CREATED)
async def import_pipeline_as_template(
    payload: ImportAsTemplatePayload,
    db: AsyncSession = Depends(get_db),
) -> PipelineTemplate:
    """Create a new PipelineTemplate by copying the stages of an existing pipeline."""
    pipeline = await db.execute(
        select(ProjectPipeline)
        .where(ProjectPipeline.id == payload.pipeline_id)
        .options(selectinload(ProjectPipeline.stages))
    )
    pipeline_obj = pipeline.scalar_one_or_none()
    if pipeline_obj is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    existing = await db.execute(select(PipelineTemplate).where(PipelineTemplate.name == payload.name))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Template name already exists")

    template = PipelineTemplate(name=payload.name, description=payload.description)
    db.add(template)
    await db.flush()

    for stage in sorted(pipeline_obj.stages, key=lambda s: s.order_index):
        db.add(PipelineTemplateStage(
            template_id=template.id,
            name=stage.name,
            stage_type=stage.stage_type,
            order_index=stage.order_index,
            requires_approval=stage.requires_approval,
            requires_verification=stage.requires_verification,
        ))

    await db.commit()
    await db.refresh(template)
    return template


# ---------------------------------------------------------------------------
# PipelineTemplateRequiredArtifact (secondary -- create/list)
# ---------------------------------------------------------------------------


@router.post(
    "/template-required-artifacts",
    response_model=PipelineTemplateRequiredArtifactOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_template_required_artifact(
    payload: PipelineTemplateRequiredArtifactCreate, db: AsyncSession = Depends(get_db)
) -> PipelineTemplateRequiredArtifact:
    template_stage = await db.get(PipelineTemplateStage, payload.template_stage_id)
    if template_stage is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template stage not found")
    artifact = PipelineTemplateRequiredArtifact(**payload.model_dump())
    db.add(artifact)
    await db.commit()
    await db.refresh(artifact)
    return artifact


@router.get(
    "/template-required-artifacts", response_model=list[PipelineTemplateRequiredArtifactOut]
)
async def list_template_required_artifacts(
    template_stage_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db)
) -> list[PipelineTemplateRequiredArtifact]:
    stmt = select(PipelineTemplateRequiredArtifact)
    if template_stage_id is not None:
        stmt = stmt.where(PipelineTemplateRequiredArtifact.template_stage_id == template_stage_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# ProjectPipeline (PRIMARY ENTITY -- full CRUD with nested stages)
# ---------------------------------------------------------------------------


@router.post("", response_model=ProjectPipelineOut, status_code=status.HTTP_201_CREATED)
async def create_pipeline(payload: ProjectPipelineCreate, db: AsyncSession = Depends(get_db)) -> ProjectPipeline:
    data = payload.model_dump(exclude={"stages"})
    pipeline = ProjectPipeline(**data)
    db.add(pipeline)
    await db.flush()  # id available pre-commit (uuid default is python-side)

    # Build stages, keeping a name->id map for dependency resolution by
    # index within the same payload (dependencies reference other stage
    # ids; since stages are new here, depends_on_stage_ids must refer to
    # ids of ALREADY-EXISTING stages -- typically used when adding a
    # stage to an existing pipeline, not on initial creation).
    for stage_payload in payload.stages:
        stage = PipelineStage(
            pipeline_id=pipeline.id,
            **stage_payload.model_dump(
                exclude={"required_artifacts", "gates", "depends_on_stage_ids"}
            ),
        )
        db.add(stage)
        await db.flush()

        for artifact_payload in stage_payload.required_artifacts:
            db.add(
                PipelineStageRequiredArtifact(stage_id=stage.id, **artifact_payload.model_dump())
            )
        for gate_payload in stage_payload.gates:
            db.add(PipelineStageGate(stage_id=stage.id, **gate_payload.model_dump()))
        for dep_id in stage_payload.depends_on_stage_ids:
            db.add(PipelineStageDependency(stage_id=stage.id, depends_on_stage_id=dep_id))

    # Rule 6.2.2: only one active pipeline per project.
    if pipeline.is_active:
        await _deactivate_other_active_pipelines(db, pipeline.project_id, exclude_id=pipeline.id)

    await db.commit()
    return await _get_pipeline_or_404(db, pipeline.id)


@router.get("", response_model=list[ProjectPipelineOut])
async def list_pipelines(
    project_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db)
) -> list[ProjectPipeline]:
    stmt = select(ProjectPipeline).options(
        selectinload(ProjectPipeline.stages).selectinload(PipelineStage.required_artifacts),
        selectinload(ProjectPipeline.stages).selectinload(PipelineStage.gates),
        selectinload(ProjectPipeline.stages).selectinload(PipelineStage.dependencies),
    )
    if project_id is not None:
        stmt = stmt.where(ProjectPipeline.project_id == project_id)
    stmt = stmt.order_by(ProjectPipeline.created_at)
    result = await db.execute(stmt)
    return list(result.scalars().unique().all())


@router.get("/{pipeline_id}", response_model=ProjectPipelineOut)
async def get_pipeline(pipeline_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ProjectPipeline:
    return await _get_pipeline_or_404(db, pipeline_id)


@router.patch("/{pipeline_id}", response_model=ProjectPipelineOut)
async def update_pipeline(
    pipeline_id: uuid.UUID, payload: ProjectPipelineUpdate, db: AsyncSession = Depends(get_db)
) -> ProjectPipeline:
    pipeline = await _get_pipeline_or_404(db, pipeline_id)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(pipeline, field, value)

    # Rule 6.2.2: activating this pipeline deactivates other active ones
    # for the same project.
    if updates.get("is_active") is True:
        await _deactivate_other_active_pipelines(db, pipeline.project_id, exclude_id=pipeline.id)

    await db.commit()
    return await _get_pipeline_or_404(db, pipeline_id)


@router.delete("/{pipeline_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pipeline(pipeline_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    pipeline = await db.get(ProjectPipeline, pipeline_id)
    if pipeline is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")
    await db.delete(pipeline)
    await db.commit()


# ---------------------------------------------------------------------------
# PipelineStage (nested resource under a pipeline -- full CRUD)
# ---------------------------------------------------------------------------


@router.post(
    "/{pipeline_id}/stages", response_model=PipelineStageOut, status_code=status.HTTP_201_CREATED
)
async def create_stage(
    pipeline_id: uuid.UUID, payload: PipelineStageCreate, db: AsyncSession = Depends(get_db)
) -> PipelineStage:
    pipeline = await db.get(ProjectPipeline, pipeline_id)
    if pipeline is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")

    existing_order = await db.execute(
        select(PipelineStage).where(
            PipelineStage.pipeline_id == pipeline_id,
            PipelineStage.order_index == payload.order_index,
        )
    )
    if existing_order.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A stage with order_index={payload.order_index} already exists for this pipeline",
        )

    # Validate dependency stage ids belong to the same pipeline.
    for dep_id in payload.depends_on_stage_ids:
        dep_stage = await db.get(PipelineStage, dep_id)
        if dep_stage is None or dep_stage.pipeline_id != pipeline_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"depends_on_stage_id {dep_id} does not belong to this pipeline",
            )

    stage = PipelineStage(
        pipeline_id=pipeline_id,
        **payload.model_dump(exclude={"required_artifacts", "gates", "depends_on_stage_ids"}),
    )
    db.add(stage)
    await db.flush()

    for artifact_payload in payload.required_artifacts:
        db.add(PipelineStageRequiredArtifact(stage_id=stage.id, **artifact_payload.model_dump()))
    for gate_payload in payload.gates:
        db.add(PipelineStageGate(stage_id=stage.id, **gate_payload.model_dump()))
    for dep_id in payload.depends_on_stage_ids:
        db.add(PipelineStageDependency(stage_id=stage.id, depends_on_stage_id=dep_id))

    await db.commit()
    return await _get_stage_or_404(db, stage.id)


@router.get("/{pipeline_id}/stages", response_model=list[PipelineStageOut])
async def list_stages(pipeline_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[PipelineStage]:
    result = await db.execute(
        select(PipelineStage)
        .where(PipelineStage.pipeline_id == pipeline_id)
        .options(
            selectinload(PipelineStage.required_artifacts),
            selectinload(PipelineStage.gates),
            selectinload(PipelineStage.dependencies),
        )
        .order_by(PipelineStage.order_index)
    )
    return list(result.scalars().unique().all())


@router.get("/stages/{stage_id}", response_model=PipelineStageOut)
async def get_stage(stage_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> PipelineStage:
    return await _get_stage_or_404(db, stage_id)


@router.patch("/stages/{stage_id}", response_model=PipelineStageOut)
async def update_stage(
    stage_id: uuid.UUID, payload: PipelineStageUpdate, db: AsyncSession = Depends(get_db)
) -> PipelineStage:
    stage = await _get_stage_or_404(db, stage_id)
    updates = payload.model_dump(exclude_unset=True)

    new_status = updates.get("status")
    if new_status in ("in_progress", "completed"):
        await _enforce_stage_advance_rules(db, stage, target_status=new_status)

    for field, value in updates.items():
        setattr(stage, field, value)

    if new_status == "completed":
        db.add(
            AuditEvent(
                entity_type="pipeline_stage",
                entity_id=stage.id,
                event_type="stage_completed",
                actor="system",
                payload={"pipeline_id": str(stage.pipeline_id), "name": stage.name},
            )
        )

    await db.commit()
    return await _get_stage_or_404(db, stage_id)


@router.delete("/stages/{stage_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_stage(stage_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    stage = await db.get(PipelineStage, stage_id)
    if stage is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage not found")
    await db.delete(stage)
    await db.commit()


async def _enforce_stage_advance_rules(
    db: AsyncSession, stage: PipelineStage, target_status: str
) -> None:
    """Encodes SPEC 6.2.6-6.2.9 before allowing a stage to advance.

    - 9: a stage cannot move to in_progress/completed if any stage it
      depends on is not completed (and not skipped), or is blocked/failed.
    - 7: a stage cannot complete if mandatory required artifacts are not
      fulfilled.
    - 8: a stage cannot complete if mandatory gates are not approved.
    """
    # Rule 9: dependency check applies to both advancing into progress
    # and completing.
    for dependency in stage.dependencies:
        dep_stage = await db.get(PipelineStage, dependency.depends_on_stage_id)
        if dep_stage is None:
            continue
        if dep_stage.status in _BLOCKING_STAGE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Cannot advance stage '{stage.name}': dependency stage "
                    f"'{dep_stage.name}' is {dep_stage.status}"
                ),
            )
        if dep_stage.status not in _TERMINAL_STAGE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Cannot advance stage '{stage.name}': dependency stage "
                    f"'{dep_stage.name}' has not completed"
                ),
            )

    if target_status != "completed":
        return

    # Rule 7: mandatory required artifacts must be fulfilled.
    missing_artifacts = [
        a.artifact_type for a in stage.required_artifacts if a.is_mandatory and not a.is_fulfilled
    ]
    if missing_artifacts:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot complete stage '{stage.name}': missing mandatory artifacts {missing_artifacts}",
        )

    # Rule 8: mandatory gates must be approved.
    unapproved_gates = [
        g.name for g in stage.gates if g.is_mandatory and g.status != "approved"
    ]
    if unapproved_gates:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot complete stage '{stage.name}': unapproved mandatory gates {unapproved_gates}",
        )


# ---------------------------------------------------------------------------
# PipelineStageDependency (secondary -- create/list/delete)
# ---------------------------------------------------------------------------


@router.post(
    "/stages/{stage_id}/dependencies",
    response_model=PipelineStageDependencyOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_stage_dependency(
    stage_id: uuid.UUID, payload: PipelineStageDependencyCreate, db: AsyncSession = Depends(get_db)
) -> PipelineStageDependency:
    stage = await db.get(PipelineStage, stage_id)
    if stage is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage not found")
    if payload.depends_on_stage_id == stage_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A stage cannot depend on itself"
        )
    dep_stage = await db.get(PipelineStage, payload.depends_on_stage_id)
    if dep_stage is None or dep_stage.pipeline_id != stage.pipeline_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="depends_on_stage_id must belong to the same pipeline",
        )
    dependency = PipelineStageDependency(stage_id=stage_id, depends_on_stage_id=payload.depends_on_stage_id)
    db.add(dependency)
    await db.commit()
    await db.refresh(dependency)
    return dependency


@router.get("/stages/{stage_id}/dependencies", response_model=list[PipelineStageDependencyOut])
async def list_stage_dependencies(
    stage_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[PipelineStageDependency]:
    result = await db.execute(
        select(PipelineStageDependency).where(PipelineStageDependency.stage_id == stage_id)
    )
    return list(result.scalars().all())


@router.delete("/dependencies/{dependency_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_stage_dependency(dependency_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    dependency = await db.get(PipelineStageDependency, dependency_id)
    if dependency is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dependency not found")
    await db.delete(dependency)
    await db.commit()


# ---------------------------------------------------------------------------
# PipelineStageRequiredArtifact (secondary -- create/list/update)
# ---------------------------------------------------------------------------


@router.post(
    "/stages/{stage_id}/required-artifacts",
    response_model=PipelineStageRequiredArtifactOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_stage_required_artifact(
    stage_id: uuid.UUID, payload: PipelineStageRequiredArtifactCreate, db: AsyncSession = Depends(get_db)
) -> PipelineStageRequiredArtifact:
    stage = await db.get(PipelineStage, stage_id)
    if stage is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage not found")
    artifact = PipelineStageRequiredArtifact(stage_id=stage_id, **payload.model_dump())
    db.add(artifact)
    await db.commit()
    await db.refresh(artifact)
    return artifact


@router.get("/stages/{stage_id}/required-artifacts", response_model=list[PipelineStageRequiredArtifactOut])
async def list_stage_required_artifacts(
    stage_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[PipelineStageRequiredArtifact]:
    result = await db.execute(
        select(PipelineStageRequiredArtifact).where(PipelineStageRequiredArtifact.stage_id == stage_id)
    )
    return list(result.scalars().all())


@router.patch(
    "/required-artifacts/{artifact_id}", response_model=PipelineStageRequiredArtifactOut
)
async def update_stage_required_artifact(
    artifact_id: uuid.UUID, payload: PipelineStageRequiredArtifactUpdate, db: AsyncSession = Depends(get_db)
) -> PipelineStageRequiredArtifact:
    artifact = await db.get(PipelineStageRequiredArtifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Required artifact not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(artifact, field, value)
    await db.commit()
    await db.refresh(artifact)
    return artifact


# ---------------------------------------------------------------------------
# PipelineStageGate (secondary -- create/list/update)
# ---------------------------------------------------------------------------


@router.post(
    "/stages/{stage_id}/gates", response_model=PipelineStageGateOut, status_code=status.HTTP_201_CREATED
)
async def create_stage_gate(
    stage_id: uuid.UUID, payload: PipelineStageGateCreate, db: AsyncSession = Depends(get_db)
) -> PipelineStageGate:
    stage = await db.get(PipelineStage, stage_id)
    if stage is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage not found")
    gate = PipelineStageGate(stage_id=stage_id, **payload.model_dump())
    db.add(gate)
    await db.commit()
    await db.refresh(gate)
    return gate


@router.get("/stages/{stage_id}/gates", response_model=list[PipelineStageGateOut])
async def list_stage_gates(stage_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[PipelineStageGate]:
    result = await db.execute(select(PipelineStageGate).where(PipelineStageGate.stage_id == stage_id))
    return list(result.scalars().all())


@router.get("/gates", response_model=list[PipelineStageGateOut])
async def list_all_gates(db: AsyncSession = Depends(get_db)) -> list[PipelineStageGate]:
    """Flat list of all gates across all stages — used for comboboxes."""
    result = await db.execute(select(PipelineStageGate).order_by(PipelineStageGate.name))
    return list(result.scalars().all())


@router.get("/gates/{gate_id}", response_model=PipelineStageGateOut)
async def get_stage_gate(gate_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> PipelineStageGate:
    gate = await db.get(PipelineStageGate, gate_id)
    if gate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gate not found")
    return gate


@router.patch("/gates/{gate_id}", response_model=PipelineStageGateOut)
async def update_stage_gate(
    gate_id: uuid.UUID, payload: PipelineStageGateUpdate, db: AsyncSession = Depends(get_db)
) -> PipelineStageGate:
    gate = await db.get(PipelineStageGate, gate_id)
    if gate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gate not found")
    if payload.status not in {"pending", "approved", "rejected"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="status must be one of: pending, approved, rejected",
        )
    gate.status = payload.status
    if payload.approved_by is not None:
        gate.approved_by = payload.approved_by
    await db.commit()
    await db.refresh(gate)
    return gate


# ---------------------------------------------------------------------------
# Release-readiness helper (rule 6.2.10): all required gates must pass.
# ---------------------------------------------------------------------------


@router.get("/{pipeline_id}/gates-check")
async def check_all_gates_pass(pipeline_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    pipeline = await _get_pipeline_or_404(db, pipeline_id)
    failing: list[str] = []
    for pipeline_stage in pipeline.stages:
        for gate in pipeline_stage.gates:
            if gate.is_mandatory and gate.status != "approved":
                failing.append(f"{pipeline_stage.name}:{gate.name}")
    return {"pipeline_id": str(pipeline_id), "ready": not failing, "failing_gates": failing}
