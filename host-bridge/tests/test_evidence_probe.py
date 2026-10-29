"""evidence_probe.py: roots checked after realpath, symlinks out refused, no
file content in any answer, real git repositories (no git mocking)."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import evidence_probe  # noqa: E402

TOKEN = "t"
H = {"X-Bridge-Token": TOKEN}
SECRET_TEXT = "conteudo-que-nunca-sai-do-host"


def _check(token):
    if token != TOKEN:
        raise HTTPException(status_code=401)


def _git(repo: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.test",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.test"}
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, env=env).stdout.strip()


@pytest.fixture()
def layout(tmp_path: Path):
    root = tmp_path / "projects"
    repo = root / "app"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "develop")
    (repo / "README.md").write_text(SECRET_TEXT)
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "base")
    integrated = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "-b", "feature")
    (repo / "feature.txt").write_text(SECRET_TEXT)
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "feature")
    feature = _git(repo, "rev-parse", "HEAD")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text(SECRET_TEXT)
    app = FastAPI()
    app.include_router(evidence_probe.make_evidence_router(_check, roots=(str(root),)))
    return {"client": TestClient(app), "root": root, "repo": repo, "outside": outside,
            "integrated": integrated, "feature": feature}


def _verify(c, **body):
    return c.post("/v1/evidence/verify", json=body, headers=H)


def test_token_required(layout):
    r = layout["client"].post("/v1/evidence/verify", json={"kind": "file", "root": str(layout["repo"]), "ref": "README.md"})
    assert r.status_code == 401
    r = layout["client"].post("/v1/git/is-ancestor", json={"repo": str(layout["repo"]), "commit": layout["feature"], "ref": "develop"})
    assert r.status_code == 401


def test_file_exists_without_content(layout):
    r = _verify(layout["client"], kind="file", root=str(layout["repo"]), ref="README.md")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["exists"] is True and "modified_at" in body
    assert SECRET_TEXT not in r.text


def test_file_missing_and_stale(layout):
    c = layout["client"]
    assert _verify(c, kind="file", root=str(layout["repo"]), ref="nope.md").json()["ok"] is False
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    stale = _verify(c, kind="file", root=str(layout["repo"]), ref="README.md", since=future).json()
    assert stale["ok"] is False and stale["exists"] is True


def test_root_outside_allowed_refused(layout):
    r = _verify(layout["client"], kind="file", root=str(layout["outside"]), ref="secret.txt")
    assert r.status_code == 403
    assert SECRET_TEXT not in r.text
    r = _verify(layout["client"], kind="file", root="relative/path", ref="x")
    assert r.status_code == 400


def test_root_symlink_out_refused(layout):
    link = layout["root"] / "escape"
    link.symlink_to(layout["outside"], target_is_directory=True)
    r = _verify(layout["client"], kind="file", root=str(link), ref="secret.txt")
    assert r.status_code == 403
    assert SECRET_TEXT not in r.text


def test_file_symlink_out_and_traversal_refused(layout):
    (layout["repo"] / "leak.txt").symlink_to(layout["outside"] / "secret.txt")
    r = _verify(layout["client"], kind="file", root=str(layout["repo"]), ref="leak.txt")
    assert r.status_code == 403
    r = _verify(layout["client"], kind="file", root=str(layout["repo"]), ref="../../outside/secret.txt")
    assert r.status_code == 400
    r = _verify(layout["client"], kind="file", root=str(layout["repo"]), ref=str(layout["outside"] / "secret.txt"))
    assert r.status_code == 400
    for resp in (r,):
        assert SECRET_TEXT not in resp.text


def test_git_commit_known_unknown_and_malformed(layout):
    c = layout["client"]
    ok = _verify(c, kind="git", root=str(layout["repo"]), ref=layout["feature"]).json()
    assert ok["ok"] is True and ok["commit"] == layout["feature"]
    unknown = _verify(c, kind="git", root=str(layout["repo"]), ref="deadbeef" * 5).json()
    assert unknown["ok"] is False and unknown["exists"] is False
    assert _verify(c, kind="git", root=str(layout["repo"]), ref="HEAD~1").status_code == 400
    assert _verify(c, kind="git", root=str(layout["repo"]), ref="--output=/tmp/x").status_code == 400
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    stale = _verify(c, kind="git", root=str(layout["repo"]), ref=layout["feature"], since=future).json()
    assert stale["ok"] is False and stale["exists"] is True


def test_git_root_not_a_repo(layout):
    plain = layout["root"] / "plain"
    plain.mkdir()
    body = _verify(layout["client"], kind="git", root=str(plain), ref=layout["feature"]).json()
    assert body["ok"] is False


def test_is_ancestor(layout):
    c = layout["client"]
    repo = str(layout["repo"])
    yes = c.post("/v1/git/is-ancestor", json={"repo": repo, "commit": layout["integrated"], "ref": "develop"}, headers=H).json()
    assert yes["is_ancestor"] is True
    no = c.post("/v1/git/is-ancestor", json={"repo": repo, "commit": layout["feature"], "ref": "develop"}, headers=H).json()
    assert no["is_ancestor"] is False and no["commit_found"] is True and no["ref_found"] is True
    missing_ref = c.post("/v1/git/is-ancestor", json={"repo": repo, "commit": layout["feature"], "ref": "main"}, headers=H).json()
    assert missing_ref["is_ancestor"] is False and missing_ref["ref_found"] is False
    unknown = c.post("/v1/git/is-ancestor", json={"repo": repo, "commit": "deadbeef" * 5, "ref": "develop"}, headers=H).json()
    assert unknown["is_ancestor"] is False and unknown["commit_found"] is False


def test_is_ancestor_refuses_bad_input_and_outside_repo(layout):
    c = layout["client"]
    repo = str(layout["repo"])
    for ref in ("-develop", "develop..main", "develop^", "HEAD@{1}", "a:b"):
        r = c.post("/v1/git/is-ancestor", json={"repo": repo, "commit": layout["feature"], "ref": ref}, headers=H)
        assert r.status_code == 400, ref
    r = c.post("/v1/git/is-ancestor", json={"repo": repo, "commit": "not-a-sha!", "ref": "develop"}, headers=H)
    assert r.status_code == 400
    r = c.post("/v1/git/is-ancestor", json={"repo": str(layout["outside"]), "commit": layout["feature"], "ref": "develop"}, headers=H)
    assert r.status_code == 403
