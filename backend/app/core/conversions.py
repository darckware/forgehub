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
from app.db.models.docs_area import DocsArea

DOCS_ROOT = Path("/docs")
VAULT_ROOT = Path("/vault")
# Whole host filesystem (docker-compose.yml bind mount) backing the
# user-configurable "áreas de criação" -- see resolve_area_root below and
# docs.py's own _area_root, which this mirrors.
HOST_ROOT = Path("/host-root")

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


async def resolve_area_root(db: AsyncSession, area_id: uuid.UUID) -> Path:
    """Resolves a docs_creation_areas row to its filesystem root, same as
    docs.py's own _area_root -- lets a demand's Documento conversion land
    in any registered área de criação, not just the original /root/docs
    mount (DOCS_ROOT)."""
    area = await db.get(DocsArea, area_id)
    if area is None:
        raise ConversionError("area_id must reference an existing creation area")
    return HOST_ROOT / area.host_path.lstrip("/")


async def convert_to_doc(*, path: str, content: str, root: Path | None = None) -> str:
    """Write `content` as a new (or overwritten) markdown file under `root`
    (defaults to /root/docs -- the same write path docs.py's own PUT /file
    uses; pass an área de criação's resolved root, see resolve_area_root,
    to write into a different area instead).

    `root` defaults to None (resolved to the module-level DOCS_ROOT inside
    the body) rather than `= DOCS_ROOT` directly -- a default *parameter*
    value is bound once at function-definition time, so tests that
    monkeypatch `conversions.DOCS_ROOT` to a tmp_path wouldn't be seen by
    an already-bound default; looking it up here every call keeps that
    working."""
    if root is None:
        root = DOCS_ROOT
    target = _resolve_or_raise(root, path)
    if target.suffix.lower() not in (".md", ".markdown", ".txt"):
        raise ConversionError("Doc path must end in .md, .markdown or .txt")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return path


async def copy_attachments_to_folder(
    *, attachments: list[tuple[str, Path]], dest_path: str, dest_root: Path | None = None
) -> list[str]:
    """Copies each (filename, already-resolved absolute source path)
    attachment into the same folder `dest_path` (a just-written doc) lives
    in under `dest_root` -- so a demand's attached files land next to its
    note instead of only the markdown body making it into Docs. `dest_root`
    only affects where the copy lands, e.g. an área de criação other than
    the original /root/docs mount. Missing source files are skipped rather
    than failing the whole conversion (an attachment row can outlive its
    file if something else already moved/deleted it).

    Sources arrive resolved, not as paths relative to some root this module
    assumes: attachments moved out of the Docs mount into their own
    (/messages, 2026-07-27) and legacy rows still live under the old one, so
    only the caller knows where a given attachment's bytes actually are. When
    this function did that resolution itself, the move would have made it
    silently skip every new attachment -- a conversion that quietly drops
    files rather than failing.

    `dest_root` defaults to None (resolved to DOCS_ROOT in the body), same
    late-binding reason as convert_to_doc's `root` param -- see its
    docstring."""
    if dest_root is None:
        dest_root = DOCS_ROOT
    dest_folder = _resolve_or_raise(dest_root, dest_path).parent
    copied: list[str] = []
    for filename, source in attachments:
        if source is None or not source.is_file():
            continue
        target = dest_folder / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        copied.append(str(target.relative_to(dest_root)))
    return copied


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
