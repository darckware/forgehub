"""Shared helpers for browsing a folder of markdown docs as a file tree
and as an Obsidian-style link graph (notes = nodes, [[wikilinks]] = edges).

Used by both api/routes/vault.py (read-only Obsidian vault) and
api/routes/foundation_docs.py (read-write Foundation rules) so the two
domains don't duplicate the same tree-walk/graph-build logic.
"""

import re
from pathlib import Path

from pydantic import BaseModel

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")


class DocNode(BaseModel):
    name: str
    path: str
    type: str  # "file" | "dir"
    children: list["DocNode"] | None = None


class GraphNode(BaseModel):
    id: str
    label: str


class GraphEdge(BaseModel):
    source: str
    target: str


class DocGraph(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


def build_tree(
    dir_path: Path,
    rel: str = "",
    *,
    include_all_files: bool = False,
    keep_empty_dirs: bool = False,
) -> list[DocNode]:
    """Defaults preserve the original vault behavior (markdown-only, empty
    dirs hidden). The Docs area passes both flags: it manages arbitrary
    files (uploads, whiteboard images) and freshly created folders must be
    navigable before they have content."""
    nodes: list[DocNode] = []
    for entry in sorted(dir_path.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        if entry.name.startswith("."):
            continue
        rel_path = f"{rel}/{entry.name}" if rel else entry.name
        if entry.is_dir():
            children = build_tree(
                entry, rel_path, include_all_files=include_all_files, keep_empty_dirs=keep_empty_dirs
            )
            if children or keep_empty_dirs:
                nodes.append(DocNode(name=entry.name, path=rel_path, type="dir", children=children))
        elif include_all_files or entry.suffix.lower() == ".md":
            nodes.append(DocNode(name=entry.name, path=rel_path, type="file"))
    return nodes


def resolve_doc_path(root: Path, relative_path: str) -> Path | None:
    """Resolve a root-relative path; return None if it escapes root."""
    target = (root / relative_path).resolve()
    root_resolved = root.resolve()
    if root_resolved not in target.parents and target != root_resolved:
        return None
    return target


def build_graph(root: Path) -> DocGraph:
    """Walk every .md file under root and link notes that reference each
    other via [[wikilink]] syntax, resolved by note basename (Obsidian's
    own resolution rule: links refer to a unique note name, not a path)."""
    md_files = [
        p
        for p in root.rglob("*.md")
        if not any(part.startswith(".") for part in p.relative_to(root).parts)
    ]

    rel_by_path: dict[Path, str] = {}
    by_basename: dict[str, str] = {}
    for p in md_files:
        rel = str(p.relative_to(root)).replace("\\", "/")
        rel_by_path[p] = rel
        by_basename.setdefault(p.stem.lower(), rel)

    nodes = [GraphNode(id=rel, label=Path(rel).stem) for rel in rel_by_path.values()]

    edges: list[GraphEdge] = []
    seen: set[tuple[str, str]] = set()
    for p, rel in rel_by_path.items():
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in WIKILINK_RE.finditer(text):
            target_name = match.group(1).strip().lower().split("/")[-1]
            target_rel = by_basename.get(target_name)
            if not target_rel or target_rel == rel:
                continue
            key = tuple(sorted((rel, target_rel)))
            if key not in seen:
                seen.add(key)
                edges.append(GraphEdge(source=rel, target=target_rel))

    return DocGraph(nodes=nodes, edges=edges)
