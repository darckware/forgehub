"""Foundation governance docs browser + editor — read/write.

Browses and edits the markdown rule/policy/governance documents under
/root/.hermes/foundation (mounted read-write at /foundation-root) -- the
same tree-walking approach as vault.py's read-only Obsidian viewer, plus a
PUT endpoint to save edits back to disk and a [[wikilink]] graph mirroring
Obsidian's own graph view.

This is the actual rule set the Hermes agents operate under (governance/,
policies/, docs/, agents/, map/, vault/, continuity/, ... subdirectories)
-- writes (including delete) here change what agents are governed by, so
the path-traversal guard is load-bearing: every operation must resolve to
a path inside FOUNDATION_ROOT. File/folder creation, rename and upload are
allowed (2026-07-20, matching the Docs/Knowledge Base browsers' parity) --
there is still no additional approval gate here beyond the JWT-authenticated
ForgeHub session, so treat write access to this router as equivalent to
editing Foundation source directly.
"""

import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.markdown_docs import DocGraph, DocNode, build_graph, build_tree, resolve_doc_path

router = APIRouter(prefix="/api/v1/foundation-docs", tags=["foundation-docs"])

FOUNDATION_ROOT = Path("/foundation-root")

_MAX_UPLOAD_BYTES = 50 * 1024 * 1024


class FoundationDocOut(BaseModel):
    path: str
    content: str


class FoundationDocUpdateIn(BaseModel):
    content: str


class FoundationFolderIn(BaseModel):
    path: str


class FoundationRenameIn(BaseModel):
    path: str
    new_path: str


def _resolve_doc_path(relative_path: str) -> Path:
    target = resolve_doc_path(FOUNDATION_ROOT, relative_path)
    if target is None:
        raise HTTPException(status_code=400, detail="Invalid document path")
    if target.suffix.lower() != ".md":
        raise HTTPException(status_code=400, detail="Only markdown files can be read or edited")
    return target


def _resolve_any_path(relative_path: str) -> Path:
    """Unlike _resolve_doc_path, not restricted to .md -- backs
    upload/download/rename so non-markdown assets can live alongside
    governance docs."""
    target = resolve_doc_path(FOUNDATION_ROOT, relative_path)
    if target is None:
        raise HTTPException(status_code=400, detail="Invalid path")
    return target


@router.get("/tree", response_model=list[DocNode])
async def get_foundation_tree() -> list[DocNode]:
    if not FOUNDATION_ROOT.is_dir():
        raise HTTPException(status_code=404, detail="Foundation directory is not mounted")
    # keep_empty_dirs -- otherwise a folder just created via POST /folder
    # (necessarily empty until a doc is added to it) is invisible here.
    return build_tree(FOUNDATION_ROOT, keep_empty_dirs=True)


@router.get("/graph", response_model=DocGraph)
async def get_foundation_graph() -> DocGraph:
    if not FOUNDATION_ROOT.is_dir():
        raise HTTPException(status_code=404, detail="Foundation directory is not mounted")
    return build_graph(FOUNDATION_ROOT)


@router.get("/doc", response_model=FoundationDocOut)
async def get_foundation_doc(path: str = Query(...)) -> FoundationDocOut:
    target = _resolve_doc_path(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Document not found")
    return FoundationDocOut(path=path, content=target.read_text(encoding="utf-8", errors="replace"))


@router.put("/doc", response_model=FoundationDocOut)
async def update_foundation_doc(
    payload: FoundationDocUpdateIn, path: str = Query(...)
) -> FoundationDocOut:
    """Create or overwrite (parents auto-created) -- see module docstring
    on the 2026-07-20 decision to allow creating new governance docs here,
    not just editing existing ones."""
    target = _resolve_doc_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload.content, encoding="utf-8")
    return FoundationDocOut(path=path, content=payload.content)


@router.delete("/doc", status_code=204)
async def delete_foundation_doc(path: str = Query(...)) -> None:
    target = _resolve_doc_path(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Document not found")
    target.unlink()


@router.post("/folder", response_model=DocNode, status_code=201)
async def create_foundation_folder(payload: FoundationFolderIn) -> DocNode:
    target = _resolve_any_path(payload.path)
    target.mkdir(parents=True, exist_ok=True)
    return DocNode(name=target.name, path=payload.path, type="dir", children=[])


@router.post("/rename", response_model=DocNode)
async def rename_foundation_path(payload: FoundationRenameIn) -> DocNode:
    """Rename/move a doc or folder, mirroring vault.py's /rename."""
    source = _resolve_any_path(payload.path)
    dest = _resolve_any_path(payload.new_path)
    if not source.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    if dest.exists():
        raise HTTPException(status_code=409, detail="Destination already exists")
    if source.is_dir() and source.resolve() in (dest.resolve(), *dest.resolve().parents):
        raise HTTPException(status_code=400, detail="Cannot move a folder into itself")
    dest.parent.mkdir(parents=True, exist_ok=True)
    source.rename(dest)
    return DocNode(name=dest.name, path=payload.new_path, type="dir" if dest.is_dir() else "file")


@router.post("/upload", response_model=DocNode, status_code=201)
async def upload_foundation_file(
    folder: str = Form(default=""),
    file: UploadFile = File(...),
) -> DocNode:
    name = Path(file.filename or "").name
    if not name:
        raise HTTPException(status_code=400, detail="Missing filename")
    rel = f"{folder.strip('/')}/{name}" if folder.strip("/") else name
    target = _resolve_any_path(rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 50MB upload limit")
    target.write_bytes(content)
    return DocNode(name=name, path=rel, type="file")


@router.get("/download")
async def download_foundation_file(path: str = Query(min_length=1)) -> FileResponse:
    target = _resolve_any_path(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(target, filename=target.name)


@router.delete("/path", status_code=204)
async def delete_foundation_path(path: str = Query(min_length=1)) -> None:
    """Delete a doc, a folder (recursively), or any other file -- unlike
    DELETE /doc, not restricted to markdown. Backs the tree's hover
    delete icon."""
    target = _resolve_any_path(path)
    if target == FOUNDATION_ROOT.resolve():
        raise HTTPException(status_code=400, detail="Cannot delete the Foundation root")
    if target.is_dir():
        shutil.rmtree(target)
    elif target.is_file():
        target.unlink()
    else:
        raise HTTPException(status_code=404, detail="Path not found")
