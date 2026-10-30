"""Where a mission document may live, and its content hash (M0.2d).

Contract: docs/architecture/MCP_MISSION_TOOLS_SPEC.md §5.8. ``doc_path`` is
relative to the Docs tree (``/docs`` in the backend container, host
``/root/docs``) -- the same base ``DocLink.doc_path`` and the Docs page have
always used, so a document attached here also shows up on that page.

A project's documents live under its own folder, named by the project slug
(the convention system_scope.py already writes to):

- ``projects/<slug>/...`` for any project;
- ``missions/<slug>/...`` too for a mission (brief, dossier, phase documents;
  04 "Contexto da missão").

Refused (``DocPathRefused``, 422 ``DOC_PATH_NOT_ALLOWED`` at the route): an
absolute path, a ``..`` or empty/``.`` segment, a backslash or NUL, anything
outside those prefixes, a prefix folder that is itself a symlink, and a path
whose realpath leaves its prefix folder (a symlink escaping the root).
Pure functions, no database: unit-tested by tests_unit/test_mission_documents.py.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path, PurePosixPath

# The Docs tree (same mount as api/routes/docs.py's DOCS_ROOT). Read at call
# time by the route, so a test can point it at a temporary directory.
MISSION_DOCS_ROOT = Path("/docs")

# The mission brief and the validation dossier (04 "Contexto da missão",
# modelos/DOSSIE-DE-VALIDACAO.md): attaching one needs the documentation role.
BRIEF_DOSSIER_FILENAMES = frozenset({"brief.md", "dossie-de-validacao.md"})
BRIEF_ARTIFACT_TYPES = frozenset({"context_brief"})

_DRIVE = re.compile(r"^[A-Za-z]:")


class DocPathRefused(ValueError):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message


def project_slug(name: str) -> str:
    """Same slug system_scope.py uses for ``projects/<slug>/``."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "project"


def allowed_prefixes(project_name: str, project_type: str) -> list[str]:
    slug = project_slug(project_name)
    prefixes = [f"projects/{slug}/"]
    if project_type == "mission":
        prefixes.insert(0, f"missions/{slug}/")
    return prefixes


def check_doc_path(root: Path, doc_path: str, prefixes: list[str]) -> Path:
    """Return the real path of ``doc_path`` under ``root``, or raise DocPathRefused.

    The lexical checks run first (nothing on disk is touched for an absolute
    or ``..`` path); then the realpath of the prefix folder must be exactly
    that folder (no symlinked project folder pointing elsewhere) and the
    realpath of the document must stay inside it. Existence is the caller's
    check (404), not a path rule."""
    if not doc_path or "\x00" in doc_path or "\\" in doc_path:
        raise DocPathRefused("invalid_characters", "doc_path is empty or has a backslash/NUL")
    if doc_path.startswith(("/", "~")) or _DRIVE.match(doc_path):
        raise DocPathRefused("absolute", "doc_path must be relative to the Docs tree")
    parts = doc_path.split("/")
    if ".." in parts:
        raise DocPathRefused("parent_reference", "doc_path may not contain '..'")
    if any(part in ("", ".") for part in parts):
        raise DocPathRefused("not_normalized", "doc_path has an empty or '.' segment")
    prefix = next((p for p in prefixes if doc_path.startswith(p)), None)
    if prefix is None:
        raise DocPathRefused("outside_allowed_roots", "doc_path is outside this project's document folders")

    root_real = os.path.realpath(root)
    prefix_lexical = os.path.join(root_real, *PurePosixPath(prefix).parts)
    prefix_real = os.path.realpath(prefix_lexical)
    if prefix_real != prefix_lexical:
        raise DocPathRefused("symlink_escape", "The project's document folder is a symlink")
    target_real = os.path.realpath(os.path.join(root_real, *parts))
    if not target_real.startswith(prefix_real + os.sep):
        raise DocPathRefused("symlink_escape", "doc_path resolves outside the project's document folder")
    return Path(target_real)


def content_hash(path: Path) -> str:
    """sha256 (hex) of the document's bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_brief_or_dossier(doc_path: str, artifact_type: str | None) -> bool:
    return PurePosixPath(doc_path).name.lower() in BRIEF_DOSSIER_FILENAMES or (
        artifact_type is not None and artifact_type in BRIEF_ARTIFACT_TYPES
    )
