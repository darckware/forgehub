"""ForgeHub Knowledge Base routes — read/write.

ForgeHub is the primary interface for the collective Markdown Knowledge Base.
The complete host root is mounted read-write at /vault, exposing per-agent
inboxes and reviewed shared knowledge as a file tree, raw-note editor and
[[wikilink]] graph. Obsidian is an optional complementary desktop editor over
the same host files, not a separate source of truth.

Editing here writes straight to the same files the desktop Obsidian app
reads. If a note is open in ForgeHub and another editor at once, last write
wins (no locking), so concurrent edits require coordination.
"""

import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.markdown_docs import DocGraph, DocNode, build_graph, build_tree, resolve_doc_path

router = APIRouter(prefix="/api/v1/vault", tags=["vault"])

VAULT_ROOT = Path("/vault")

# Same limit as docs.py's upload -- whiteboard PNG exports and imported
# markdown files both flow through here.
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024


class VaultNoteOut(BaseModel):
    path: str
    content: str


class VaultNoteUpdateIn(BaseModel):
    content: str


class VaultFolderIn(BaseModel):
    path: str


class VaultRenameIn(BaseModel):
    path: str
    new_path: str


def _resolve_note_path(relative_path: str) -> Path:
    target = resolve_doc_path(VAULT_ROOT, relative_path)
    if target is None:
        raise HTTPException(status_code=400, detail="Invalid note path")
    if target.suffix.lower() != ".md":
        raise HTTPException(status_code=400, detail="Only markdown notes can be read or edited")
    return target


def _resolve_folder_path(relative_path: str) -> Path:
    target = resolve_doc_path(VAULT_ROOT, relative_path)
    if target is None:
        raise HTTPException(status_code=400, detail="Invalid folder path")
    return target


def _resolve_any_path(relative_path: str) -> Path:
    """Unlike _resolve_note_path, not restricted to .md -- backs
    upload/download/rename so whiteboard assets (PNG/.excalidraw) and
    arbitrary uploaded files can live alongside notes in the vault."""
    target = resolve_doc_path(VAULT_ROOT, relative_path)
    if target is None:
        raise HTTPException(status_code=400, detail="Invalid path")
    return target


@router.get("/tree", response_model=list[DocNode])
async def get_vault_tree() -> list[DocNode]:
    if not VAULT_ROOT.is_dir():
        raise HTTPException(status_code=404, detail="Vault is not mounted")
    # keep_empty_dirs -- otherwise a folder just created via POST /folder
    # (necessarily empty until a note is added to it) is invisible here,
    # making creation look like it silently failed.
    return build_tree(VAULT_ROOT, keep_empty_dirs=True)


@router.get("/graph", response_model=DocGraph)
async def get_vault_graph() -> DocGraph:
    if not VAULT_ROOT.is_dir():
        raise HTTPException(status_code=404, detail="Vault is not mounted")
    return build_graph(VAULT_ROOT)


@router.get("/note", response_model=VaultNoteOut)
async def get_vault_note(path: str = Query(...)) -> VaultNoteOut:
    target = _resolve_note_path(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Note not found")
    return VaultNoteOut(path=path, content=target.read_text(encoding="utf-8", errors="replace"))


@router.put("/note", response_model=VaultNoteOut)
async def update_vault_note(payload: VaultNoteUpdateIn, path: str = Query(...)) -> VaultNoteOut:
    """Create or overwrite. Creating is needed so content (an agent demand,
    a Docs note) can be promoted into a brand-new Knowledge Base entry, not
    just edit ones that already exist -- see api/routes/demand.py and
    docs.py's /convert."""
    target = _resolve_note_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload.content, encoding="utf-8")
    return VaultNoteOut(path=path, content=payload.content)


@router.delete("/note", status_code=204)
async def delete_vault_note(path: str = Query(...)) -> None:
    target = _resolve_note_path(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Note not found")
    target.unlink()


@router.post("/folder", response_model=DocNode, status_code=201)
async def create_vault_folder(payload: VaultFolderIn) -> DocNode:
    """Create an empty folder. Notes themselves can already be created via
    PUT /note (parents auto-created), but that only produces folders that
    contain a note -- this is for grouping structure ahead of content."""
    target = _resolve_folder_path(payload.path)
    target.mkdir(parents=True, exist_ok=True)
    return DocNode(name=target.name, path=payload.path, type="dir", children=[])


@router.post("/rename", response_model=DocNode)
async def rename_vault_path(payload: VaultRenameIn) -> DocNode:
    """Rename/move a note or folder, mirroring docs.py's /rename."""
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
async def upload_vault_file(
    folder: str = Form(default=""),
    file: UploadFile = File(...),
) -> DocNode:
    """Write an arbitrary file (whiteboard PNG/.excalidraw export, an
    imported .md note, etc.) into the vault -- unlike PUT /note, not
    restricted to markdown."""
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
async def download_vault_file(path: str = Query(min_length=1)) -> FileResponse:
    target = _resolve_any_path(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(target, filename=target.name)


@router.delete("/path", status_code=204)
async def delete_vault_path(path: str = Query(min_length=1)) -> None:
    """Delete a note, a folder (recursively), or any other file -- unlike
    DELETE /note, not restricted to markdown. Backs the tree's hover
    delete icon, which the UI confirms before calling."""
    target = _resolve_any_path(path)
    if target == VAULT_ROOT.resolve():
        raise HTTPException(status_code=400, detail="Cannot delete the vault root")
    if target.is_dir():
        shutil.rmtree(target)
    elif target.is_file():
        target.unlink()
    else:
        raise HTTPException(status_code=404, detail="Path not found")
