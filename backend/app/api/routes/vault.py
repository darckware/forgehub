"""Obsidian vault browser routes — read/write.

Obsidian itself is a desktop Electron app with no web server, so it can't
be embedded like ForgeRouter/Kanboard. This gives a view of the same vault
(mounted read-write at /vault, same volume as foundation.py's VAULT_DIR)
inside ForgeHub instead: a file tree of every .md note, an endpoint to
fetch/edit one note's raw content, and a [[wikilink]] graph mirroring
Obsidian's own graph view.

Editing here writes straight to the same files the desktop Obsidian app
reads -- if a note is open in both places at once, last write wins (no
locking). Obsidian itself reloads externally-changed files automatically,
so this mirrors editing the same file in two text editors, not a server
storage conflict.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.markdown_docs import DocGraph, DocNode, build_graph, build_tree, resolve_doc_path

router = APIRouter(prefix="/api/v1/vault", tags=["vault"])

VAULT_ROOT = Path("/vault")


class VaultNoteOut(BaseModel):
    path: str
    content: str


class VaultNoteUpdateIn(BaseModel):
    content: str


def _resolve_note_path(relative_path: str) -> Path:
    target = resolve_doc_path(VAULT_ROOT, relative_path)
    if target is None:
        raise HTTPException(status_code=400, detail="Invalid note path")
    if target.suffix.lower() != ".md":
        raise HTTPException(status_code=400, detail="Only markdown notes can be read or edited")
    return target


@router.get("/tree", response_model=list[DocNode])
async def get_vault_tree() -> list[DocNode]:
    if not VAULT_ROOT.is_dir():
        raise HTTPException(status_code=404, detail="Vault is not mounted")
    return build_tree(VAULT_ROOT)


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
