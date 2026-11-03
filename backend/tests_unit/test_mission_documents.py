"""M0.2d document path rules (core/mission_documents.py, MCP_MISSION_TOOLS_SPEC.md §5.8).

Pure functions over a temporary directory, no database: run with
``pytest --noconftest``.
"""
import hashlib
import os

os.environ.setdefault("ENVIRONMENT", "test")

import pytest  # noqa: E402

from app.core.mission_documents import (  # noqa: E402
    DocPathRefused,
    allowed_prefixes,
    check_doc_path,
    content_hash,
    is_brief_or_dossier,
    project_slug,
)

PREFIXES = ["missions/m1/", "projects/m1/"]


@pytest.fixture
def root(tmp_path):
    docs = tmp_path / "docs"
    (docs / "missions/m1/sub").mkdir(parents=True)
    (docs / "projects/other").mkdir(parents=True)
    (docs / "missions/m1/ok.md").write_text("ok")
    (docs / "missions/m1/sub/deep.md").write_text("deep")
    (docs / "projects/other/x.md").write_text("x")
    (tmp_path / "secret.md").write_text("secret")
    return docs


def test_prefixes_and_slug():
    assert project_slug("Missão ForgeHub: M1!") == "miss-o-forgehub-m1"
    assert allowed_prefixes("Mission A", "mission") == ["missions/mission-a/", "projects/mission-a/"]
    assert allowed_prefixes("Fix A", "maintenance") == ["projects/fix-a/"]


def test_accepts_files_inside_the_prefix(root):
    assert check_doc_path(root, "missions/m1/ok.md", PREFIXES) == (root / "missions/m1/ok.md").resolve()
    assert check_doc_path(root, "missions/m1/sub/deep.md", PREFIXES).name == "deep.md"
    # A symlink that stays inside the prefix folder is fine.
    (root / "missions/m1/alias.md").symlink_to(root / "missions/m1/ok.md")
    assert check_doc_path(root, "missions/m1/alias.md", PREFIXES).name == "ok.md"
    # A path that doesn't exist yet passes the rules (the route answers 404).
    assert check_doc_path(root, "missions/m1/new.md", PREFIXES).name == "new.md"


@pytest.mark.parametrize(("doc_path", "reason"), [
    ("", "invalid_characters"),
    ("missions/m1/a\\b.md", "invalid_characters"),
    ("missions/m1/a\x00.md", "invalid_characters"),
    ("/etc/passwd", "absolute"),
    ("~/x.md", "absolute"),
    ("C:/x.md", "absolute"),
    ("missions/m1/../../secret.md", "parent_reference"),
    ("../secret.md", "parent_reference"),
    ("missions/m1/./ok.md", "not_normalized"),
    ("missions/m1//ok.md", "not_normalized"),
    ("missions/m1/", "not_normalized"),
    ("missions/m10/x.md", "outside_allowed_roots"),
    ("projects/other/x.md", "outside_allowed_roots"),
    ("docs/missions/m1/ok.md", "outside_allowed_roots"),
    ("missions/m1", "outside_allowed_roots"),
])
def test_refusals(root, doc_path, reason):
    with pytest.raises(DocPathRefused) as exc:
        check_doc_path(root, doc_path, PREFIXES)
    assert exc.value.reason == reason


def test_symlink_escapes_refused(root, tmp_path):
    (root / "missions/m1/leak.md").symlink_to(tmp_path / "secret.md")
    (root / "missions/m1/up").symlink_to(root / "projects/other")
    (root / "projects/m1").symlink_to(root / "projects/other")
    for doc_path in ("missions/m1/leak.md", "missions/m1/up/x.md", "projects/m1/x.md"):
        with pytest.raises(DocPathRefused) as exc:
            check_doc_path(root, doc_path, PREFIXES)
        assert exc.value.reason == "symlink_escape", doc_path


def test_content_hash_and_brief(root):
    assert content_hash(root / "missions/m1/ok.md") == hashlib.sha256(b"ok").hexdigest()
    assert is_brief_or_dossier("missions/m1/BRIEF.md", None)
    assert is_brief_or_dossier("missions/m1/dossie-de-validacao.md", None)
    assert is_brief_or_dossier("missions/m1/notes.md", "context_brief")
    assert not is_brief_or_dossier("missions/m1/notes.md", "reference_doc")
