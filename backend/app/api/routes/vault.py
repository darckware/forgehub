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
