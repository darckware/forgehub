"""Product domain routes: products, product_modules, product_versions,
releases.

Business rules implemented (SPEC.md section 6.1):
1. Every product must have a unique name -> DB unique constraint + 409 on
   IntegrityError in create_product.
2. Every product can have many modules -> POST/GET /api/v1/products/{id}/modules.
3. Every product must have at least one version -> create_product always
   creates an initial ProductVersion in the same DB transaction (either the
   caller-supplied `initial_version` payload or a "0.1.0 / planned"
   default). There is no endpoint to delete the last remaining version of
   a product (delete_version returns 422 if it is the only version left).
4. Published versions cannot be mutated directly -> update_version rejects
   (422) any update where the version's *current* status is "published".
   Transitioning a non-published version *into* "published" is allowed via
   the same endpoint.
5. Fixes for published versions must create patch/hotfix flows -> out of
   scope for this domain (belongs to Backlog/Planning domains); not
   implemented here (see model file docstring).
"""
import base64
import io
import json
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import delete, or_, select

from app.core.config import settings
from app.db.models.product import PRODUCT_STATUSES as VALID_PRODUCT_STATUSES
from app.api.schemas.product import (
    ProductCreate,
    ProductModuleCreate,
    ProductModuleOut,
    ProductModuleUpdate,
    ProductOut,
    ProductUpdate,
    ProductVersionCreate,
    ProductVersionOut,
    ProductVersionUpdate,
    ProductWithVersionsOut,
    ReleaseCreate,
    ReleaseOut,
    ReleaseUpdate,
    VALID_PRODUCT_VERSION_STATUSES,
    VALID_RELEASE_STATUSES,
)
from app.db.base import get_db
from app.db.models.product import Product, ProductModule, ProductVersion, Release
from app.db.models.project import (
    Project, ChangeRequest, ProjectStructureNode,
)
from app.db.models.backlog import PlanningItem
from app.db.models.task import ProjectTask, TaskExecution, TaskAssignment
from app.db.models.pipeline import ProjectPipeline, PipelineStage
from app.db.models.execution import ExecutionWave, ExecutionWorkPackage
from app.db.models.orchestration import ProjectLoopPolicy, TaskExecutionReview
from app.db.models.system_scope import ProjectScope, ProjectScopeItem


async def _bridge_request(method: str, path: str, **kwargs) -> dict:
    """Call the host-bridge. Returns parsed JSON on success, raises HTTPException on error."""
    url = f"{settings.CHAT_BRIDGE_URL}{path}"
    headers = {"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN}
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await getattr(client, method.lower())(url, headers=headers, **kwargs)
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Bridge error {resp.status_code}: {resp.text[:200]}",
        )
    return resp.json()

router = APIRouter(prefix="/api/v1/products", tags=["products"])


async def _get_product_or_404(db: AsyncSession, product_id: uuid.UUID) -> Product:
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


async def _get_version_or_404(db: AsyncSession, version_id: uuid.UUID) -> ProductVersion:
    version = await db.get(ProductVersion, version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product version not found")
    return version


# ---------------------------------------------------------------------------
# Product CRUD (primary entity)
# ---------------------------------------------------------------------------


@router.post("", response_model=ProductWithVersionsOut, status_code=status.HTTP_201_CREATED)
async def create_product(payload: ProductCreate, db: AsyncSession = Depends(get_db)) -> Product:
    if payload.status not in VALID_PRODUCT_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid product status '{payload.status}'",
        )
    product = Product(
        name=payload.name,
        description=payload.description,
        status=payload.status,
        application_url=payload.application_url,
        application_url_dev=payload.application_url_dev,
    )

    initial_version_payload = payload.initial_version or ProductVersionCreate(
        version="0.1.0", status="planned"
    )
    if initial_version_payload.status not in VALID_PRODUCT_VERSION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid version status '{initial_version_payload.status}'",
        )

    # Business rule 6.1.3: a product is never persisted without a version —
    # both rows are added to the same session/transaction.
    version = ProductVersion(
        product=product,
        version=initial_version_payload.version,
        status=initial_version_payload.status,
        release_notes=initial_version_payload.release_notes,
    )

    db.add(product)
    db.add(version)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A product with this name already exists"
        ) from None

    await db.refresh(product, attribute_names=["versions", "modules"])
    return product


@router.get("", response_model=list[ProductOut])
async def list_products(db: AsyncSession = Depends(get_db)) -> list[Product]:
    result = await db.execute(select(Product).order_by(Product.name))
    return list(result.scalars().all())


@router.get("/{product_id}", response_model=ProductWithVersionsOut)
async def get_product(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Product:
    result = await db.execute(
        select(Product)
        .where(Product.id == product_id)
        .options(selectinload(Product.versions), selectinload(Product.modules))
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.put("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: uuid.UUID, payload: ProductUpdate, db: AsyncSession = Depends(get_db)
) -> Product:
    product = await _get_product_or_404(db, product_id)

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A product with this name already exists"
        ) from None

    await db.refresh(product)
    return product


def _row_to_dict(obj) -> dict:
    """Serialize any SQLAlchemy mapped instance to a plain dict (columns only)."""
    from sqlalchemy import inspect as sa_inspect
    mapper = sa_inspect(type(obj))
    return {col.key: getattr(obj, col.key) for col in mapper.column_attrs}


def _json_default(obj):
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    try:
        from decimal import Decimal
        if isinstance(obj, Decimal):
            return float(obj)
    except ImportError:
        pass
    raise TypeError(f"Type {type(obj)} not JSON serializable")


# ---------------------------------------------------------------------------
# Product Backup  GET /api/v1/products/{id}/backup
# ---------------------------------------------------------------------------

@router.get("/{product_id}/backup")
async def backup_product(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Full snapshot of a product: all DB entities + project working-directory
    files. Returns a ZIP containing db.json and (optional) files/*.tar.gz.

    The backup is a self-contained snapshot: every row is serialized with its
    original UUID so it can be restored exactly via POST /api/v1/products/restore.
    """
    # --- 1. Load product + versions + modules --------------------------------
    result = await db.execute(
        select(Product)
        .where(Product.id == product_id)
        .options(selectinload(Product.versions), selectinload(Product.modules))
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    version_ids = [v.id for v in product.versions]

    # --- 2. Load projects linked to those versions ---------------------------
    projects_result = await db.execute(
        select(Project).where(Project.product_version_id.in_(version_ids))
    )
    projects = list(projects_result.scalars().all())
    project_ids = [p.id for p in projects]

    # --- 3. Load all downstream entities per project -------------------------
    def _load_list(rows):
        return [_row_to_dict(r) for r in rows]

    cr_result = await db.execute(
        select(ChangeRequest).where(ChangeRequest.project_id.in_(project_ids))
    )
    struct_result = await db.execute(
        select(ProjectStructureNode).where(ProjectStructureNode.project_id.in_(project_ids))
    )
    pipeline_result = await db.execute(
        select(ProjectPipeline).where(ProjectPipeline.project_id.in_(project_ids))
    )
    pipelines = list(pipeline_result.scalars().all())
    pipeline_ids = [p.id for p in pipelines]

    stage_result = await db.execute(
        select(PipelineStage).where(PipelineStage.pipeline_id.in_(pipeline_ids))
    )
    pi_result = await db.execute(
        select(PlanningItem).where(PlanningItem.project_id.in_(project_ids))
    )
    planning_items = list(pi_result.scalars().all())
    pi_ids = [p.id for p in planning_items]

    task_result = await db.execute(
        select(ProjectTask).where(ProjectTask.planning_item_id.in_(pi_ids))
    )
    tasks = list(task_result.scalars().all())
    task_ids = [t.id for t in tasks]

    exec_result = await db.execute(
        select(TaskExecution).where(TaskExecution.task_id.in_(task_ids))
    )
    assign_result = await db.execute(
        select(TaskAssignment).where(TaskAssignment.task_id.in_(task_ids))
    )

    # --- 4. Build the JSON payload -------------------------------------------
    db_data = {
        "format": "forgehub-product-backup",
        "schema_version": 2,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "product": _row_to_dict(product),
        "versions": [_row_to_dict(v) for v in product.versions],
        "modules": [_row_to_dict(m) for m in product.modules],
        "projects": [_row_to_dict(p) for p in projects],
        "change_requests": _load_list(cr_result.scalars().all()),
        "structure_nodes": _load_list(struct_result.scalars().all()),
        "pipelines": [_row_to_dict(p) for p in pipelines],
        "pipeline_stages": _load_list(stage_result.scalars().all()),
        "planning_items": [_row_to_dict(p) for p in planning_items],
        "tasks": [_row_to_dict(t) for t in tasks],
        "task_executions": _load_list(exec_result.scalars().all()),
        "task_assignments": _load_list(assign_result.scalars().all()),
    }

    db_json_bytes = json.dumps(db_data, default=_json_default, indent=2).encode()

    # --- 5. Archive project working directories via host-bridge --------------
    files_archives: dict[str, bytes] = {}
    for proj in projects:
        path = proj.working_directory_path
        if not path:
            continue
        try:
            bridge_resp = await _bridge_request("POST", "/v1/fs/tar", json={"path": path})
            raw = base64.b64decode(bridge_resp["archive_b64"])
            safe_name = str(proj.id)
            files_archives[safe_name] = raw
        except Exception:
            pass  # non-fatal: backup still includes DB data

    # --- 6. Pack into a ZIP --------------------------------------------------
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("db.json", db_json_bytes)
        for proj_id, raw in files_archives.items():
            zf.writestr(f"files/{proj_id}.tar.gz", raw)

    zip_buf.seek(0)
    fname = f"product-backup-{product.name.replace(' ', '_').lower()}.zip"
    return StreamingResponse(
        zip_buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ---------------------------------------------------------------------------
# Product Restore  POST /api/v1/products/restore
# ---------------------------------------------------------------------------

@router.post("/restore", status_code=status.HTTP_201_CREATED)
async def restore_product(
    file: UploadFile = File(...),
    restore_db: str = "true",
    restore_files: str = "true",
    db: AsyncSession = Depends(get_db),
):
    """Restore a product from a ZIP backup (produced by GET …/backup).

    All entities are upserted with their original UUIDs so the snapshot is
    reproduced exactly. If rows already exist (same UUID) they are updated
    to match the backup state.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    content = await file.read()
    zf = zipfile.ZipFile(io.BytesIO(content), "r")
    if "db.json" not in zf.namelist():
        raise HTTPException(status_code=400, detail="Invalid backup: db.json not found in ZIP")

    data = json.loads(zf.read("db.json"))
    if data.get("format") != "forgehub-product-backup":
        raise HTTPException(status_code=400, detail="Invalid backup format")

    def _uuids(d: dict) -> dict:
        """Convert string UUID values back to uuid.UUID objects for FK correctness."""
        out = {}
        for k, v in d.items():
            if isinstance(v, str):
                try:
                    out[k] = uuid.UUID(v)
                except ValueError:
                    out[k] = v
            else:
                out[k] = v
        return out

    async def _upsert(model_cls, rows: list[dict]):
        for row in rows:
            values = _uuids(row)
            values.pop("created_at", None)
            values.pop("updated_at", None)
            stmt = (
                pg_insert(model_cls.__table__)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=["id"],
                    set_={k: v for k, v in values.items() if k != "id"},
                )
            )
            await db.execute(stmt)

    do_db = restore_db.lower() not in ("false", "0", "no")
    do_files = restore_files.lower() not in ("false", "0", "no")

    if do_db:
        # Upsert in FK order: parents before children
        await _upsert(Product, [data["product"]])
        await _upsert(ProductVersion, data.get("versions", []))
        await _upsert(ProductModule, data.get("modules", []))
        await _upsert(Project, data.get("projects", []))
        await _upsert(ChangeRequest, data.get("change_requests", []))
        await _upsert(ProjectStructureNode, data.get("structure_nodes", []))
        await _upsert(ProjectPipeline, data.get("pipelines", []))
        await _upsert(PipelineStage, data.get("pipeline_stages", []))
        await _upsert(PlanningItem, data.get("planning_items", []))
        await _upsert(ProjectTask, data.get("tasks", []))
        await _upsert(TaskAssignment, data.get("task_assignments", []))
        await _upsert(TaskExecution, data.get("task_executions", []))

        try:
            await db.commit()
        except Exception as exc:
            await db.rollback()
            raise HTTPException(status_code=500, detail=f"Restore failed: {exc}") from exc

    if do_files:
        # Restore project files via host-bridge
        for proj in data.get("projects", []):
            path = proj.get("working_directory_path")
            proj_id = proj.get("id", "")
            archive_name = f"files/{proj_id}.tar.gz"
            if not path or archive_name not in zf.namelist():
                continue
            try:
                raw = zf.read(archive_name)
                b64 = base64.b64encode(raw).decode()
                parent = str(Path(path).parent)
                await _bridge_request("POST", "/v1/fs/untar", json={"path": parent, "archive_b64": b64})
            except Exception:
                pass  # non-fatal: DB was restored, files are best-effort

    zf.close()
    product_id = data["product"]["id"]
    return {"status": "ok", "product_id": product_id}


async def _clear_restrict_blocked_dependencies(db: AsyncSession, project_ids: list[uuid.UUID]) -> None:
    """Explicitly deletes rows that would otherwise RESTRICT-block a
    cascading product delete.

    A handful of FKs deep in the execution/governance domains are
    deliberately `ON DELETE RESTRICT` rather than CASCADE -- e.g.
    `execution_work_packages.execution_wave_id`, `project_scope_items
    .system_element_id`, `task_execution_reviews.reviewer_membership_id`
    -- so that an unrelated, incidental edit elsewhere in the app (someone
    removing one project member, or tidying up an old System Map element)
    can't silently orphan a delivery-commitment or audit record. That
    protection is correct for normal operation and must not be relaxed at
    the schema level.

    Deleting an entire product is a different, explicit "wipe everything
    under this product" action, so this clears exactly those
    RESTRICT-blocked rows first, in dependency order, before the product
    row itself is deleted -- everything else in the tree already cascades
    correctly via ON DELETE CASCADE once these are out of the way.
    """
    if not project_ids:
        return

    task_ids_subq = select(ProjectTask.id).where(or_(
        ProjectTask.planning_item_id.in_(select(PlanningItem.id).where(PlanningItem.project_id.in_(project_ids))),
        ProjectTask.change_request_id.in_(select(ChangeRequest.id).where(ChangeRequest.project_id.in_(project_ids))),
    ))

    # execution_work_packages RESTRICTs execution_waves/plan_baselines/task_assignments.
    await db.execute(delete(ExecutionWorkPackage).where(ExecutionWorkPackage.execution_wave_id.in_(
        select(ExecutionWave.id).where(ExecutionWave.project_id.in_(project_ids))
    )))
    # task_execution_reviews RESTRICTs project_agent_memberships.
    await db.execute(delete(TaskExecutionReview).where(TaskExecutionReview.execution_id.in_(
        select(TaskExecution.id).where(TaskExecution.task_id.in_(task_ids_subq))
    )))
    # project_loop_policies RESTRICTs project_agent_memberships.
    await db.execute(delete(ProjectLoopPolicy).where(ProjectLoopPolicy.project_id.in_(project_ids)))
    # project_scope_items RESTRICTs system_elements; project_scopes itself
    # RESTRICTs system_blueprint_revisions, so both must go before the
    # product's system_blueprints/system_elements are cascade-deleted.
    await db.execute(delete(ProjectScopeItem).where(ProjectScopeItem.project_scope_id.in_(
        select(ProjectScope.id).where(ProjectScope.project_id.in_(project_ids))
    )))
    await db.execute(delete(ProjectScope).where(ProjectScope.project_id.in_(project_ids)))


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    product = await _get_product_or_404(db, product_id)
    project_ids = list((await db.execute(
        select(Project.id)
        .join(ProductVersion, ProductVersion.id == Project.product_version_id)
        .where(ProductVersion.product_id == product_id)
    )).scalars())
    await _clear_restrict_blocked_dependencies(db, project_ids)
    await db.delete(product)
    await db.commit()


# ---------------------------------------------------------------------------
# ProductModule (nested under Product)
# ---------------------------------------------------------------------------


@router.post(
    "/{product_id}/modules", response_model=ProductModuleOut, status_code=status.HTTP_201_CREATED
)
async def create_product_module(
    product_id: uuid.UUID, payload: ProductModuleCreate, db: AsyncSession = Depends(get_db)
) -> ProductModule:
    await _get_product_or_404(db, product_id)

    module = ProductModule(product_id=product_id, name=payload.name, description=payload.description)
    db.add(module)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A module with this name already exists for this product",
        ) from None
    await db.refresh(module)
    return module


@router.get("/{product_id}/modules", response_model=list[ProductModuleOut])
async def list_product_modules(
    product_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[ProductModule]:
    await _get_product_or_404(db, product_id)
    result = await db.execute(
        select(ProductModule).where(ProductModule.product_id == product_id).order_by(ProductModule.name)
    )
    return list(result.scalars().all())


@router.put("/modules/{module_id}", response_model=ProductModuleOut)
async def update_product_module(
    module_id: uuid.UUID, payload: ProductModuleUpdate, db: AsyncSession = Depends(get_db)
) -> ProductModule:
    module = await db.get(ProductModule, module_id)
    if module is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product module not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(module, field, value)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A module with this name already exists for this product",
        ) from None
    await db.refresh(module)
    return module


@router.delete("/modules/{module_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product_module(module_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    module = await db.get(ProductModule, module_id)
    if module is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product module not found")
    await db.delete(module)
    await db.commit()


# ---------------------------------------------------------------------------
# ProductVersion (nested under Product)
# ---------------------------------------------------------------------------


@router.post(
    "/{product_id}/versions", response_model=ProductVersionOut, status_code=status.HTTP_201_CREATED
)
async def create_product_version(
    product_id: uuid.UUID, payload: ProductVersionCreate, db: AsyncSession = Depends(get_db)
) -> ProductVersion:
    await _get_product_or_404(db, product_id)

    if payload.status not in VALID_PRODUCT_VERSION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid version status '{payload.status}'",
        )

    version = ProductVersion(
        product_id=product_id,
        version=payload.version,
        status=payload.status,
        release_notes=payload.release_notes,
    )
    db.add(version)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This version string already exists for this product",
        ) from None
    await db.refresh(version)
    return version


@router.get("/{product_id}/versions", response_model=list[ProductVersionOut])
async def list_product_versions(
    product_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[ProductVersion]:
    await _get_product_or_404(db, product_id)
    result = await db.execute(
        select(ProductVersion)
        .where(ProductVersion.product_id == product_id)
        .order_by(ProductVersion.created_at)
    )
    return list(result.scalars().all())


@router.get("/versions", response_model=list[ProductVersionOut])
async def list_all_product_versions(db: AsyncSession = Depends(get_db)) -> list[ProductVersion]:
    """Flat list of all versions across all products — used for comboboxes."""
    result = await db.execute(select(ProductVersion).order_by(ProductVersion.created_at))
    return list(result.scalars().all())


@router.get("/versions/{version_id}", response_model=ProductVersionOut)
async def get_product_version(version_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ProductVersion:
    return await _get_version_or_404(db, version_id)


@router.put("/versions/{version_id}", response_model=ProductVersionOut)
async def update_product_version(
    version_id: uuid.UUID, payload: ProductVersionUpdate, db: AsyncSession = Depends(get_db)
) -> ProductVersion:
    version = await _get_version_or_404(db, version_id)

    # Business rule 6.1.4: published versions cannot be mutated directly.
    if version.status == "published":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Published versions cannot be mutated directly. Create a patch/hotfix flow instead.",
        )

    update_data = payload.model_dump(exclude_unset=True)
    if "status" in update_data and update_data["status"] not in VALID_PRODUCT_VERSION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid version status '{update_data['status']}'",
        )

    for field, value in update_data.items():
        setattr(version, field, value)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This version string already exists for this product",
        ) from None
    await db.refresh(version)
    return version


@router.post("/versions/{version_id}:publish", response_model=ProductVersionOut)
async def publish_product_version(version_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ProductVersion:
    """Dedicated publish action (Pacote 4, 2026-08-01) -- clearer than
    overloading the generic PUT, and it's the one place that gets to check
    "is everything actually finished" before flipping the switch. Idempotent
    if already published. Blocks (409 + the blocking list, same UX as
    dispatch_task's dependency gate) rather than force-completing unfinished
    work -- Marcelo: publishing should never invent completion that didn't
    happen.
    """
    version = await _get_version_or_404(db, version_id)
    if version.status == "published":
        return version

    projects = list((await db.execute(
        select(Project).where(Project.product_version_id == version_id)
    )).scalars())
    blocking: list[dict] = []
    task_count = 0
    for project in projects:
        tasks = list((await db.execute(
            select(ProjectTask)
            .join(PlanningItem, PlanningItem.id == ProjectTask.planning_item_id)
            .where(PlanningItem.project_id == project.id)
        )).scalars())
        task_count += len(tasks)
        for task in tasks:
            if task.status not in ("done", "deployed", "cancelled"):
                blocking.append({
                    "project_id": str(project.id), "project_name": project.name,
                    "task_id": str(task.id), "task_number": task.number,
                    "title": task.title, "status": task.status,
                })
    if task_count == 0:
        raise HTTPException(status_code=409, detail={
            "message": "This version needs at least one task before it can be published",
            "blocking": [],
        })
    if blocking:
        raise HTTPException(status_code=409, detail={
            "message": "This version has unfinished tasks and cannot be published yet",
            "blocking": blocking,
        })

    version.status = "published"
    for project in projects:
        project.status = "completed"
        # Also ensure all planning items are marked as done
        proj_planning_items = list((await db.execute(
            select(PlanningItem).where(PlanningItem.project_id == project.id)
        )).scalars())
        for pi in proj_planning_items:
            pi.status = "done"

    await db.commit()
    await db.refresh(version)
    return version


@router.delete("/versions/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product_version(version_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    version = await _get_version_or_404(db, version_id)

    if version.status == "published":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Published versions cannot be mutated directly.",
        )

    # Business rule 6.1.3: every product must have at least one version.
    result = await db.execute(
        select(ProductVersion.id).where(ProductVersion.product_id == version.product_id)
    )
    remaining_ids = result.scalars().all()
    if len(remaining_ids) <= 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Cannot delete the only remaining version of a product",
        )

    await db.delete(version)
    await db.commit()


# ---------------------------------------------------------------------------
# Release (secondary table, linked to a ProductVersion)
# ---------------------------------------------------------------------------


@router.post("/releases", response_model=ReleaseOut, status_code=status.HTTP_201_CREATED)
async def create_release(payload: ReleaseCreate, db: AsyncSession = Depends(get_db)) -> Release:
    await _get_version_or_404(db, payload.product_version_id)

    if payload.status not in VALID_RELEASE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid release status '{payload.status}'",
        )

    release = Release(
        product_version_id=payload.product_version_id,
        name=payload.name,
        status=payload.status,
        notes=payload.notes,
    )
    db.add(release)
    await db.commit()
    await db.refresh(release)
    return release


@router.get("/releases", response_model=list[ReleaseOut])
async def list_releases(db: AsyncSession = Depends(get_db)) -> list[Release]:
    result = await db.execute(select(Release).order_by(Release.created_at))
    return list(result.scalars().all())


@router.get("/releases/{release_id}", response_model=ReleaseOut)
async def get_release(release_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Release:
    release = await db.get(Release, release_id)
    if release is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Release not found")
    return release


@router.put("/releases/{release_id}", response_model=ReleaseOut)
async def update_release(
    release_id: uuid.UUID, payload: ReleaseUpdate, db: AsyncSession = Depends(get_db)
) -> Release:
    release = await db.get(Release, release_id)
    if release is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Release not found")

    update_data = payload.model_dump(exclude_unset=True)
    if "status" in update_data and update_data["status"] not in VALID_RELEASE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid release status '{update_data['status']}'",
        )

    for field, value in update_data.items():
        setattr(release, field, value)

    await db.commit()
    await db.refresh(release)
    return release


@router.delete("/releases/{release_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_release(release_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    release = await db.get(Release, release_id)
    if release is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Release not found")
    await db.delete(release)
    await db.commit()
