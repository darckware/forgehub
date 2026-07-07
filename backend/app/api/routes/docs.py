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
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.markdown_docs import DocNode, build_tree, resolve_doc_path

router = APIRouter(prefix="/api/v1/docs", tags=["docs"])

DOCS_ROOT = Path("/docs")

# Editable inline in the page; everything else is upload/download-only.
_EDITABLE_SUFFIXES = {".md", ".markdown", ".txt"}
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


def _resolve_or_400(relative_path: str) -> Path:
    target = resolve_doc_path(DOCS_ROOT, relative_path)
    if target is None:
        raise HTTPException(status_code=400, detail="Invalid path")
    return target


def _require_editable(target: Path) -> None:
    if target.suffix.lower() not in _EDITABLE_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail="Only markdown/text files are edited inline -- use download/upload for binaries",
        )


@router.get("/tree", response_model=list[DocNode])
async def docs_tree() -> list[DocNode]:
    """Full /docs tree: every file type, empty folders included."""
    if not DOCS_ROOT.is_dir():
        return []
    return build_tree(DOCS_ROOT, include_all_files=True, keep_empty_dirs=True)


@router.get("/file", response_model=DocFileOut)
async def read_file(path: str = Query(min_length=1)) -> DocFileOut:
    target = _resolve_or_400(path)
    _require_editable(target)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return DocFileOut(path=path, content=target.read_text(encoding="utf-8", errors="replace"))


@router.put("/file", response_model=DocFileOut)
async def write_file(payload: DocFileWriteIn) -> DocFileOut:
    """Create or overwrite a markdown/text file (parents auto-created)."""
    target = _resolve_or_400(payload.path)
    _require_editable(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload.content, encoding="utf-8")
    return DocFileOut(path=payload.path, content=payload.content)


@router.delete("/file", status_code=204)
async def delete_path(path: str = Query(min_length=1)) -> None:
    """Delete a file, or a folder (recursively -- the UI confirms first)."""
    target = _resolve_or_400(path)
    if target == DOCS_ROOT.resolve():
        raise HTTPException(status_code=400, detail="Cannot delete the docs root")
    if target.is_dir():
        shutil.rmtree(target)
    elif target.is_file():
        target.unlink()
    else:
        raise HTTPException(status_code=404, detail="Path not found")


@router.post("/folder", response_model=DocNode, status_code=201)
async def create_folder(payload: DocFolderIn) -> DocNode:
    target = _resolve_or_400(payload.path)
    target.mkdir(parents=True, exist_ok=True)
    return DocNode(name=target.name, path=payload.path, type="dir", children=[])


@router.post("/rename", response_model=DocNode)
async def rename_path(payload: DocRenameIn) -> DocNode:
    """Rename/move a file or folder inside /docs."""
    source = _resolve_or_400(payload.path)
    dest = _resolve_or_400(payload.new_path)
    if not source.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    if dest.exists():
        raise HTTPException(status_code=409, detail="Destination already exists")
    dest.parent.mkdir(parents=True, exist_ok=True)
    source.rename(dest)
    return DocNode(
        name=dest.name, path=payload.new_path, type="dir" if dest.is_dir() else "file"
    )


@router.post("/upload", response_model=DocNode, status_code=201)
async def upload_file(
    folder: str = Form(default=""),
    file: UploadFile = File(...),
) -> DocNode:
    name = Path(file.filename or "").name
    if not name:
        raise HTTPException(status_code=400, detail="Missing filename")
    rel = f"{folder.strip('/')}/{name}" if folder.strip("/") else name
    target = _resolve_or_400(rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 50MB upload limit")
    target.write_bytes(content)
    return DocNode(name=name, path=rel, type="file")


@router.get("/download")
async def download_file(path: str = Query(min_length=1)) -> FileResponse:
    target = _resolve_or_400(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(target, filename=target.name)
