"""Docs routes — the "área de criação" backing the Docs page.

Filesystem-backed like vault.py, but over /root/docs (mounted RW at
/docs): a personal working tree of markdown documents, uploads and
whiteboard assets, organized in folders and later cross-linked to
Planning entities (products/projects/tasks) via doc_links (phase 3).

Unlike the vault (markdown-only, mirror of Obsidian), this tree manages
arbitrary files: markdown is edited inline (GET/PUT /file), anything
else flows through /upload and /download. Every write resolves the
target through resolve_doc_path, so nothing can escape /docs.
"""
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.demand import ConvertIn, ConvertOut
from app.core import conversions
from app.core.markdown_docs import DocGraph, DocNode, build_graph, build_tree, resolve_doc_path
from app.db.base import get_db
from app.db.models.doc_link import DOC_LINK_ENTITY_TYPES, DocLink
from app.db.models.docs_area import DocsArea

router = APIRouter(prefix="/api/v1/docs", tags=["docs"])

# The original single-area mount -- doc_links and /convert (below) still
# assume this one area exclusively; they aren't yet area-aware (see that
# section's docstring for why).
DOCS_ROOT = Path("/docs")

# Whole host filesystem (see docker-compose.yml) backing the
# user-configurable "áreas de criação" (DocsArea rows, /areas endpoints
# below) -- any absolute host path can be registered as a browsable area.
HOST_ROOT = Path("/host-root")

# Editable inline in the page; everything else is upload/download-only.
# .excalidraw is UTF-8 JSON -- read as text so the Docs page can reopen a
# saved whiteboard scene without a dedicated endpoint.
_EDITABLE_SUFFIXES = {".md", ".markdown", ".txt", ".excalidraw"}
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024


class DocFileOut(BaseModel):
    path: str
    content: str


class DocFileWriteIn(BaseModel):
    path: str = Field(min_length=1)
    content: str


class DocFolderIn(BaseModel):
    path: str = Field(min_length=1)


class DocRenameIn(BaseModel):
    path: str = Field(min_length=1)
    new_path: str = Field(min_length=1)


def _resolve_or_400(root: Path, relative_path: str) -> Path:
    target = resolve_doc_path(root, relative_path)
    if target is None:
        raise HTTPException(status_code=400, detail="Invalid path")
    return target


def _require_editable(target: Path) -> None:
    if target.suffix.lower() not in _EDITABLE_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail="Only markdown/text files are edited inline -- use download/upload for binaries",
        )


# ---------------------------------------------------------------------------
# Áreas de criação: user-configurable roots for the file browser below.
# Any absolute host path (HOST_ROOT is the whole host filesystem, see
# docker-compose.yml). At least one area must always exist -- enforced on
# DELETE, not a DB constraint (needs a row count check).
# ---------------------------------------------------------------------------


class DocsAreaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    host_path: str


class DocsAreaCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    host_path: str = Field(min_length=1, max_length=1000)

    @field_validator("host_path")
    @classmethod
    def _check_absolute(cls, v: str) -> str:
        if not v.startswith("/"):
            raise ValueError("host_path must be an absolute path")
        return v.rstrip("/") or "/"


def _area_root(area: DocsArea) -> Path:
    return HOST_ROOT / area.host_path.lstrip("/")


async def _get_area_or_404(db: AsyncSession, area_id: uuid.UUID) -> DocsArea:
    area = (
        await db.execute(select(DocsArea).where(DocsArea.id == area_id))
    ).scalar_one_or_none()
    if area is None:
        raise HTTPException(status_code=404, detail="Area not found")
    return area


@router.get("/areas", response_model=list[DocsAreaOut])
async def list_areas(db: AsyncSession = Depends(get_db)) -> list[DocsArea]:
    result = await db.execute(select(DocsArea).order_by(DocsArea.created_at))
    return list(result.scalars().all())


@router.post("/areas", response_model=DocsAreaOut, status_code=201)
async def create_area(payload: DocsAreaCreate, db: AsyncSession = Depends(get_db)) -> DocsArea:
    host_root_resolved = HOST_ROOT.resolve()
    resolved = (HOST_ROOT / payload.host_path.lstrip("/")).resolve()
    if host_root_resolved != resolved and host_root_resolved not in resolved.parents:
        raise HTTPException(status_code=400, detail="Invalid host_path")
    # Self-service: create the folder if it doesn't exist yet, rather than
    # requiring the user to pre-create it on the host before registering.
    resolved.mkdir(parents=True, exist_ok=True)
    # Store the canonical host-side path (".." components collapsed, e.g.
    # "/root/../etc" -> "/etc") rather than the raw input, so the list/UI
    # always shows the real path.
    rel = resolved.relative_to(host_root_resolved)
    canonical_host_path = "/" if rel == Path(".") else f"/{rel}"
    area = DocsArea(name=payload.name, host_path=canonical_host_path)
    db.add(area)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="An area with this host_path already exists") from None
    await db.refresh(area)
    return area


@router.delete("/areas/{area_id}", status_code=204)
async def delete_area(area_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    """Removes the area from the list only -- never deletes the folder or
    its contents on the host."""
    area = await _get_area_or_404(db, area_id)
    total = (await db.execute(select(func.count()).select_from(DocsArea))).scalar_one()
    if total <= 1:
        raise HTTPException(status_code=400, detail="At least one area must always exist")
    await db.delete(area)
    await db.commit()


# ---------------------------------------------------------------------------
# File browser -- every endpoint below takes area_id and resolves against
# that area's own root (never DOCS_ROOT, which only backs doc_links/convert).
# ---------------------------------------------------------------------------


@router.get("/tree", response_model=list[DocNode])
async def docs_tree(area_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[DocNode]:
    """Full area tree: every file type, empty folders included."""
    area = await _get_area_or_404(db, area_id)
    root = _area_root(area)
    if not root.is_dir():
        return []
    return build_tree(root, include_all_files=True, keep_empty_dirs=True)


@router.get("/graph", response_model=DocGraph)
async def docs_graph(area_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> DocGraph:
    """[[wikilink]] graph across the area's markdown files, same shape as
    vault.py's /graph (build_graph is root-agnostic) -- backs the Docs
    page's "Grafo" view mode alongside "Nota"/"Mapa mental"."""
    area = await _get_area_or_404(db, area_id)
    root = _area_root(area)
    if not root.is_dir():
        return DocGraph(nodes=[], edges=[])
    return build_graph(root)


@router.get("/file", response_model=DocFileOut)
async def read_file(
    area_id: uuid.UUID, path: str = Query(min_length=1), db: AsyncSession = Depends(get_db)
) -> DocFileOut:
    area = await _get_area_or_404(db, area_id)
    target = _resolve_or_400(_area_root(area), path)
    _require_editable(target)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return DocFileOut(path=path, content=target.read_text(encoding="utf-8", errors="replace"))


class DocFileWriteWithAreaIn(DocFileWriteIn):
    area_id: uuid.UUID


@router.put("/file", response_model=DocFileOut)
async def write_file(payload: DocFileWriteWithAreaIn, db: AsyncSession = Depends(get_db)) -> DocFileOut:
    """Create or overwrite a markdown/text file (parents auto-created)."""
    area = await _get_area_or_404(db, payload.area_id)
    target = _resolve_or_400(_area_root(area), payload.path)
    _require_editable(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload.content, encoding="utf-8")
    return DocFileOut(path=payload.path, content=payload.content)


@router.delete("/file", status_code=204)
async def delete_path(
    area_id: uuid.UUID, path: str = Query(min_length=1), db: AsyncSession = Depends(get_db)
) -> None:
    """Delete a file, or a folder (recursively -- the UI confirms first)."""
    area = await _get_area_or_404(db, area_id)
    root = _area_root(area)
    target = _resolve_or_400(root, path)
    if target == root.resolve():
        raise HTTPException(status_code=400, detail="Cannot delete the area's root")
    if target.is_dir():
        shutil.rmtree(target)
    elif target.is_file():
        target.unlink()
    else:
        raise HTTPException(status_code=404, detail="Path not found")


class DocFolderWithAreaIn(DocFolderIn):
    area_id: uuid.UUID


@router.post("/folder", response_model=DocNode, status_code=201)
async def create_folder(payload: DocFolderWithAreaIn, db: AsyncSession = Depends(get_db)) -> DocNode:
    area = await _get_area_or_404(db, payload.area_id)
    target = _resolve_or_400(_area_root(area), payload.path)
    target.mkdir(parents=True, exist_ok=True)
    return DocNode(name=target.name, path=payload.path, type="dir", children=[])


class DocRenameWithAreaIn(DocRenameIn):
    area_id: uuid.UUID


@router.post("/rename", response_model=DocNode)
async def rename_path(payload: DocRenameWithAreaIn, db: AsyncSession = Depends(get_db)) -> DocNode:
    """Rename/move a file or folder inside the area (also backs
    drag-and-drop moves in the tree -- new_path is just a different
    parent folder with the same basename in that case)."""
    area = await _get_area_or_404(db, payload.area_id)
    root = _area_root(area)
    source = _resolve_or_400(root, payload.path)
    dest = _resolve_or_400(root, payload.new_path)
    if not source.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    if dest.exists():
        raise HTTPException(status_code=409, detail="Destination already exists")
    # dest.exists() above already catches a same-path no-op rename (source
    # exists, so an identical dest would too); this guards the other way a
    # move can corrupt the tree -- dropping a folder inside its own
    # descendant, which Path.rename doesn't detect on its own.
    if source.is_dir() and source.resolve() in (dest.resolve(), *dest.resolve().parents):
        raise HTTPException(status_code=400, detail="Cannot move a folder into itself")
    dest.parent.mkdir(parents=True, exist_ok=True)
    source.rename(dest)
    return DocNode(
        name=dest.name, path=payload.new_path, type="dir" if dest.is_dir() else "file"
    )


@router.post("/upload", response_model=DocNode, status_code=201)
async def upload_file(
    area_id: uuid.UUID = Form(...),
    folder: str = Form(default=""),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> DocNode:
    area = await _get_area_or_404(db, area_id)
    name = Path(file.filename or "").name
    if not name:
        raise HTTPException(status_code=400, detail="Missing filename")
    rel = f"{folder.strip('/')}/{name}" if folder.strip("/") else name
    target = _resolve_or_400(_area_root(area), rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 50MB upload limit")
    target.write_bytes(content)
    return DocNode(name=name, path=rel, type="file")


@router.get("/download")
async def download_file(
    area_id: uuid.UUID, path: str = Query(min_length=1), db: AsyncSession = Depends(get_db)
) -> FileResponse:
    area = await _get_area_or_404(db, area_id)
    target = _resolve_or_400(_area_root(area), path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(target, filename=target.name)


# ---------------------------------------------------------------------------
# Doc links: cross-references to Planning entities (doc_links table).
# The label lookup is raw SQL per entity type on purpose -- importing the
# other domains' model modules here would couple docs to every domain
# (same reason cross-domain FKs are string-form, see db/base.py docs).
# ---------------------------------------------------------------------------

_ENTITY_LABEL_SOURCE: dict[str, tuple[str, str]] = {
    "product": ("company.products", "name"),
    "product_version": ("company.product_versions", "version"),
    "project": ("company.projects", "name"),
    "pipeline": ("company.project_pipelines", "name"),
    "planning_item": ("company.planning_items", "title"),
    "task": ("company.project_tasks", "title"),
    "artifact": ("company.artifacts", "name"),
}


class DocLinkCreateIn(BaseModel):
    doc_path: str = Field(min_length=1, max_length=500)
    entity_type: str
    entity_id: uuid.UUID

    @field_validator("entity_type")
    @classmethod
    def _check_entity_type(cls, v: str) -> str:
        if v not in DOC_LINK_ENTITY_TYPES:
            raise ValueError(f"entity_type must be one of {DOC_LINK_ENTITY_TYPES}")
        return v


class DocLinkOut(BaseModel):
    id: uuid.UUID
    doc_path: str
    entity_type: str
    entity_id: uuid.UUID
    # Human label resolved at read time (product name, task title, ...);
    # None when the target row no longer exists (stale link).
    entity_label: str | None = None


async def _entity_label(db: AsyncSession, entity_type: str, entity_id: uuid.UUID) -> str | None:
    table, column = _ENTITY_LABEL_SOURCE[entity_type]
    result = await db.execute(
        text(f"SELECT {column} FROM {table} WHERE id = :id"), {"id": str(entity_id)}  # noqa: S608
    )
    value = result.scalar_one_or_none()
    return str(value) if value is not None else None


async def _link_out(db: AsyncSession, link: DocLink) -> DocLinkOut:
    return DocLinkOut(
        id=link.id,
        doc_path=link.doc_path,
        entity_type=link.entity_type,
        entity_id=link.entity_id,
        entity_label=await _entity_label(db, link.entity_type, link.entity_id),
    )


@router.get("/links", response_model=list[DocLinkOut])
async def list_doc_links(
    path: str = Query(min_length=1), db: AsyncSession = Depends(get_db)
) -> list[DocLinkOut]:
    result = await db.execute(
        select(DocLink).where(DocLink.doc_path == path).order_by(DocLink.entity_type)
    )
    return [await _link_out(db, link) for link in result.scalars().all()]


@router.get("/links/by-entity", response_model=list[DocLinkOut])
async def list_entity_docs(
    entity_type: str, entity_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[DocLinkOut]:
    """Docs linked to one Planning entity -- backs the "Docs" section on
    the detail screens (product/project/planning/task)."""
    if entity_type not in DOC_LINK_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown entity_type: {entity_type}")
    result = await db.execute(
        select(DocLink)
        .where(DocLink.entity_type == entity_type, DocLink.entity_id == entity_id)
        .order_by(DocLink.doc_path)
    )
    return [await _link_out(db, link) for link in result.scalars().all()]


@router.post("/links", response_model=DocLinkOut, status_code=201)
async def create_doc_link(
    payload: DocLinkCreateIn, db: AsyncSession = Depends(get_db)
) -> DocLinkOut:
    """Link a doc to a Planning entity. Both sides are validated: the doc
    must exist on disk and the entity row must exist."""
    target = _resolve_or_400(DOCS_ROOT, payload.doc_path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Doc file not found")
    label = await _entity_label(db, payload.entity_type, payload.entity_id)
    if label is None:
        raise HTTPException(status_code=404, detail=f"{payload.entity_type} not found")
    link = DocLink(
        doc_path=payload.doc_path,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
    )
    db.add(link)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="This link already exists") from None
    await db.refresh(link)
    return DocLinkOut(
        id=link.id,
        doc_path=link.doc_path,
        entity_type=link.entity_type,
        entity_id=link.entity_id,
        entity_label=label,
    )


@router.delete("/links/{link_id}", status_code=204)
async def delete_doc_link(link_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    link = (
        await db.execute(select(DocLink).where(DocLink.id == link_id))
    ).scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=404, detail="Link not found")
    await db.delete(link)
    await db.commit()


# ---------------------------------------------------------------------------
# Convert an existing doc/note into a Task, Artifact or Knowledge Base
# entry -- the "anotações também podem ser convertidas" half of the same
# feature that backs demand.py's /demands/{id}/convert (shared helpers in
# core/conversions.py). target=doc creates a *copy* at a new path (the
# source note is left alone) rather than colliding with the existing
# rename/move action already on the Docs page.
# ---------------------------------------------------------------------------


@router.post("/convert", response_model=ConvertOut)
async def convert_doc(payload: ConvertIn, db: AsyncSession = Depends(get_db)) -> ConvertOut:
    if not payload.source_path:
        raise HTTPException(status_code=400, detail="source_path is required")
    source = _resolve_or_400(DOCS_ROOT, payload.source_path)
    if not source.is_file():
        raise HTTPException(status_code=404, detail="Doc file not found")
    content = source.read_text(encoding="utf-8", errors="replace")
    title = payload.title or source.stem

    try:
        if payload.target == "task":
            if payload.planning_item_id is None:
                raise HTTPException(400, "planning_item_id is required for target=task")
            entity_id, reference = await conversions.convert_to_task(
                db, title=title, content=content, planning_item_id=payload.planning_item_id
            )
        elif payload.target == "doc":
            # A copy at a new location -- the source note is left as-is
            # (moving it is the existing rename/move action on this page).
            dest_path = payload.path or f"{title}.md"
            if dest_path == payload.source_path:
                raise HTTPException(400, "destination path must differ from the source note")
            reference = await conversions.convert_to_doc(path=dest_path, content=content)
            entity_id = None
        elif payload.target == "artifact":
            if not payload.artifact_type:
                raise HTTPException(400, "artifact_type is required for target=artifact")
            reference_path = payload.path or f"artefatos/{title}.md"
            entity_id, reference = await conversions.convert_to_artifact(
                db,
                name=title,
                content=content,
                artifact_type=payload.artifact_type,
                doc_path=reference_path,
            )
        else:  # knowledge_base
            if not payload.path:
                raise HTTPException(400, "path is required for target=knowledge_base")
            reference = await conversions.convert_to_knowledge_base(
                path=payload.path, content=content
            )
            entity_id = None
    except conversions.ConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ConvertOut(
        entity_type=payload.target,
        entity_id=str(entity_id) if entity_id else None,
        reference=reference,
    )
