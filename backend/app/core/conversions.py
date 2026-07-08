"""Shared conversion helpers: turn arbitrary markdown content (an agent
demand's body, or an existing /root/docs note) into a real domain entity.

Reused by api/routes/demand.py (POST /demands/{id}/convert) and
api/routes/docs.py (POST /docs/convert) so both entry points ("demandas
ou anotações", per the request that created this) get the exact same
four targets with the exact same validated business rules -- task/
artifact creation delegates to the real route functions (create_task,
create_artifact) instead of re-implementing their invariants here.
"""
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.artifact import create_artifact
from app.api.routes.backlog import create_planning_item
from app.api.routes.task import create_task
from app.api.schemas.artifact import ArtifactCreate, ArtifactVersionCreate
from app.api.schemas.backlog import PlanningItemCreate
from app.api.schemas.task import ProjectTaskCreate
from app.core.markdown_docs import resolve_doc_path
from app.db.models.doc_link import DocLink

DOCS_ROOT = Path("/docs")
VAULT_ROOT = Path("/vault")

# project_id-scoped targets (planning_item/project_doc/quick_task) exist
# alongside the original four so a demand can become project work
# directly, not just a doc/task tied to something that must already exist.
CONVERT_TARGETS = (
    "task",
    "doc",
    "artifact",
    "knowledge_base",
    "planning_item",
    "project_doc",
    "quick_task",
)

DEFAULT_ITEM_TYPE = "documentation"


class ConversionError(Exception):
    """Raised for a target-specific validation failure; routes turn this
    into an HTTPException so both call sites report errors the same way."""


def _resolve_or_raise(root: Path, relative_path: str) -> Path:
    target = resolve_doc_path(root, relative_path)
    if target is None:
        raise ConversionError(f"Invalid path: {relative_path}")
    return target


async def convert_to_task(
    db: AsyncSession, *, title: str, content: str, planning_item_id: uuid.UUID
) -> tuple[uuid.UUID, str]:
    """A task must trace back to a planning item (core ForgeHub invariant)
    -- delegates to the real create_task route function so that rule (and
    every other one it enforces) applies here too, not a re-implementation
    that could drift out of sync."""
    payload = ProjectTaskCreate(
        planning_item_id=planning_item_id, title=title[:255], description=content
    )
    try:
        task = await create_task(payload, db)
    except HTTPException as exc:
        raise ConversionError(exc.detail) from exc
    return task.id, str(task.id)


async def convert_to_doc(*, path: str, content: str) -> str:
    """Write `content` as a new (or overwritten) markdown file under
    /root/docs -- the same write path docs.py's own PUT /file uses."""
    target = _resolve_or_raise(DOCS_ROOT, path)
    if target.suffix.lower() not in (".md", ".markdown", ".txt"):
        raise ConversionError("Doc path must end in .md, .markdown or .txt")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return path


async def convert_to_artifact(
    db: AsyncSession, *, name: str, content: str, artifact_type: str, doc_path: str
) -> tuple[uuid.UUID, str]:
    """Every artifact needs a real backing file (ForgeHub's audit-trail
    invariant), so this writes `content` to /root/docs first and points
    the artifact's initial version at that path, then delegates to the
    real create_artifact route function for the row itself."""
    written_path = await convert_to_doc(path=doc_path, content=content)
    payload = ArtifactCreate(
        name=name[:255],
        artifact_type=artifact_type,
        initial_version=ArtifactVersionCreate(location_uri=written_path),
    )
    try:
        artifact = await create_artifact(payload, db)
    except HTTPException as exc:
        raise ConversionError(exc.detail) from exc
    return artifact.id, str(artifact.id)


async def convert_to_knowledge_base(*, path: str, content: str) -> str:
    """Write `content` as a new (or overwritten) note in the Obsidian
    vault -- same primitive as vault.py's PUT /note (create-or-update)."""
    target = _resolve_or_raise(VAULT_ROOT, path)
    if target.suffix.lower() != ".md":
        raise ConversionError("Knowledge Base path must end in .md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return path


async def convert_to_planning_item(
    db: AsyncSession, *, title: str, content: str, project_id: uuid.UUID, item_type: str
) -> tuple[uuid.UUID, str]:
    """Drops the demand straight into a project's backlog (no task yet) --
    delegates to the real create_planning_item route function so project
    existence / item_type validation stays in one place."""
    payload = PlanningItemCreate(title=title[:255], description=content, item_type=item_type, project_id=project_id)
    try:
        item = await create_planning_item(payload, db)
    except HTTPException as exc:
        raise ConversionError(exc.detail) from exc
    return item.id, str(item.id)


async def convert_to_project_doc(
    db: AsyncSession, *, project_id: uuid.UUID, path: str, content: str
) -> str:
    """Writes the demand as a doc under /docs, then cross-links it to the
    project (doc_links) -- same insert docs.py's own POST /links does, but
    inlined here rather than imported to avoid a docs.py <-> conversions.py
    import cycle (docs.py already imports this module for its own /convert
    endpoint)."""
    written_path = await convert_to_doc(path=path, content=content)
    link = DocLink(doc_path=written_path, entity_type="project", entity_id=project_id)
    db.add(link)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConversionError("This doc is already linked to that project") from exc
    return written_path


async def convert_to_quick_task(
    db: AsyncSession, *, title: str, content: str, project_id: uuid.UUID, item_type: str
) -> tuple[uuid.UUID, str]:
    """The "task avulsa" shortcut: ForgeHub's core invariant requires every
    task to trace back to a planning item, so this creates a minimal one
    (title/content mirrored from the demand) and the task under it in one
    call, instead of making the user create both by hand."""
    planning_item_id, _ = await convert_to_planning_item(
        db, title=title, content=content, project_id=project_id, item_type=item_type
    )
    return await convert_to_task(db, title=title, content=content, planning_item_id=planning_item_id)
