"""remote_fs.py's scripts, run for real against a temp directory.

`ssh <target> <command>` hands <command> to the remote login shell; the tests
swap ssh for a local `sh -c`, so every script, quoting included, runs exactly
as it would on a server -- only the transport is faked.
"""

from __future__ import annotations

import sys
import tarfile
import io
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import remote_fs  # noqa: E402

TOKEN = "test-token"
HEADERS = {"X-Bridge-Token": TOKEN, "X-Ssh-Host": "srv.example", "X-Ssh-User": "deploy"}


def _check_token(token: str | None) -> None:
    if token != TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(remote_fs, "ssh_args", lambda target: ["sh", "-c"])
    monkeypatch.setattr(remote_fs, "_CONTROL_DIR", str(tmp_path / ".control"))
    app = FastAPI()
    app.include_router(remote_fs.make_remote_fs_router(_check_token, lambda raw: raw))
    return TestClient(app)


def test_rejects_missing_token_and_bad_target(client):
    assert client.get("/v1/remote-fs/list", headers={**HEADERS, "X-Bridge-Token": "no"}).status_code == 401
    bad_host = {**HEADERS, "X-Ssh-Host": "-oProxyCommand=evil"}
    assert client.get("/v1/remote-fs/list", headers=bad_host).status_code == 400
    assert client.get("/v1/remote-fs/list", headers={**HEADERS, "X-Ssh-User": "a b"}).status_code == 400


def test_list_sorts_dirs_first_and_reports_symlinks(client, tmp_path):
    (tmp_path / "b.txt").write_text("hello")
    (tmp_path / "A dir").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "b.txt")
    (tmp_path / "broken").symlink_to(tmp_path / "missing")

    res = client.get("/v1/remote-fs/list", params={"path": str(tmp_path)}, headers=HEADERS)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["path"] == str(tmp_path)
    assert body["parent"] == str(tmp_path.parent)
    names = [(e["name"], e["type"], e["is_symlink"]) for e in body["entries"] if not e["name"].startswith(".")]
    assert names == [("A dir", "dir", False), ("b.txt", "file", False), ("link", "file", True)]
    assert next(e for e in body["entries"] if e["name"] == "b.txt")["size"] == 5


def test_list_missing_dir_is_404(client, tmp_path):
    res = client.get("/v1/remote-fs/list", params={"path": str(tmp_path / "nope")}, headers=HEADERS)
    assert res.status_code == 404


def test_write_read_and_binary_refusal(client, tmp_path):
    target = tmp_path / "new" / "notes; rm -rf $HOME.txt"
    res = client.put("/v1/remote-fs/write", json={"path": str(target), "content": "olá\n"}, headers=HEADERS)
    assert res.status_code == 200, res.text
    assert target.read_text() == "olá\n"
    assert client.get("/v1/remote-fs/read", params={"path": str(target)}, headers=HEADERS).json()["content"] == "olá\n"

    (tmp_path / "bin").write_bytes(b"a\x00b")
    assert client.get("/v1/remote-fs/read", params={"path": str(tmp_path / "bin")}, headers=HEADERS).status_code == 415


def test_mkdir_create_rename_copy_delete(client, tmp_path):
    folder = tmp_path / "folder"
    assert client.post("/v1/remote-fs/mkdir", json={"path": str(folder)}, headers=HEADERS).status_code == 200
    assert client.post("/v1/remote-fs/mkdir", json={"path": str(folder)}, headers=HEADERS).status_code == 409

    file = folder / "a.txt"
    assert client.post("/v1/remote-fs/create-file", json={"path": str(file)}, headers=HEADERS).status_code == 200
    assert client.post("/v1/remote-fs/create-file", json={"path": str(file)}, headers=HEADERS).status_code == 409

    moved = tmp_path / "b.txt"
    res = client.patch("/v1/remote-fs/rename", json={"path": str(file), "new_path": str(moved)}, headers=HEADERS)
    assert res.status_code == 200 and res.json()["type"] == "file"
    assert moved.exists() and not file.exists()

    res = client.post("/v1/remote-fs/copy", json={"path": str(folder), "new_path": str(folder / "inner")}, headers=HEADERS)
    assert res.status_code == 400
    res = client.post("/v1/remote-fs/copy", json={"path": str(moved), "new_path": str(folder / "c.txt")}, headers=HEADERS)
    assert res.status_code == 200 and res.json()["name"] == "c.txt"

    res = client.delete("/v1/remote-fs/delete", params={"path": str(folder)}, headers=HEADERS)
    assert res.status_code == 400  # not empty, not recursive
    res = client.delete("/v1/remote-fs/delete", params={"path": str(folder), "recursive": True}, headers=HEADERS)
    assert res.status_code == 200 and not folder.exists()
    assert client.delete("/v1/remote-fs/delete", params={"path": str(folder)}, headers=HEADERS).status_code == 404


def test_search_substring_glob_and_skips(client, tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Report.PDF").write_text("x")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "report.pdf").write_text("x")

    res = client.get("/v1/remote-fs/search", params={"path": str(tmp_path), "q": "report"}, headers=HEADERS)
    assert res.status_code == 200, res.text
    assert [e["path"] for e in res.json()["entries"]] == [str(tmp_path / "src" / "Report.PDF")]
    assert res.json()["truncated"] is False

    res = client.get("/v1/remote-fs/search", params={"path": str(tmp_path), "q": "*.pdf"}, headers=HEADERS)
    assert len(res.json()["entries"]) == 1

    for i in range(3):
        (tmp_path / f"many{i}").write_text("x")
    res = client.get("/v1/remote-fs/search", params={"path": str(tmp_path), "q": "many", "limit": 2}, headers=HEADERS)
    assert len(res.json()["entries"]) == 2 and res.json()["truncated"] is True


def test_download_file_folder_and_selection(client, tmp_path):
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "x.txt").write_text("conteúdo")
    (tmp_path / "y.txt").write_text("y")

    res = client.get("/v1/remote-fs/download", params={"path": str(tmp_path / "y.txt")}, headers=HEADERS)
    assert res.status_code == 200 and res.content == b"y"
    assert 'filename="y.txt"' in res.headers["content-disposition"]

    res = client.get("/v1/remote-fs/download", params={"path": str(tmp_path / "d")}, headers=HEADERS)
    assert res.status_code == 200 and "d.tar.gz" in res.headers["content-disposition"]
    with tarfile.open(fileobj=io.BytesIO(res.content)) as tar:
        assert "d/x.txt" in tar.getnames()

    res = client.post(
        "/v1/remote-fs/download-zip",
        json={"paths": [str(tmp_path / "d"), str(tmp_path / "y.txt")], "name": "sel.zip"},
        headers=HEADERS,
    )
    assert res.status_code == 200 and "sel.tar.gz" in res.headers["content-disposition"]
    with tarfile.open(fileobj=io.BytesIO(res.content)) as tar:
        assert {"d/x.txt", "y.txt"} <= set(tar.getnames())

    assert client.get("/v1/remote-fs/download", params={"path": str(tmp_path / "zz")}, headers=HEADERS).status_code == 404


def test_upload_creates_parents_and_respects_overwrite(client, tmp_path):
    target = tmp_path / "site" / "css" / "app.css"
    res = client.put("/v1/remote-fs/upload", params={"path": str(target)}, content=b"body{}", headers=HEADERS)
    assert res.status_code == 200, res.text
    assert target.read_bytes() == b"body{}" and res.json()["size"] == 6
    assert not [p for p in target.parent.iterdir() if p.name.endswith(".part")]

    res = client.put("/v1/remote-fs/upload", params={"path": str(target)}, content=b"new", headers=HEADERS)
    assert res.status_code == 409
    res = client.put(
        "/v1/remote-fs/upload", params={"path": str(target), "overwrite": True}, content=b"new", headers=HEADERS
    )
    assert res.status_code == 200 and target.read_bytes() == b"new"


def test_ssh_failures_become_clear_messages():
    target = remote_fs.SshTarget(host="h", user="u", port=22, key=None)
    with pytest.raises(HTTPException) as exc:
        remote_fs.raise_for_exit(target, 255, "u@h: Permission denied (publickey,password).")
    assert exc.value.status_code == 502 and "key-based access" in exc.value.detail
    with pytest.raises(HTTPException) as exc:
        remote_fs.raise_for_exit(target, 255, "ssh: connect to host h port 22: Connection timed out")
    assert "Cannot reach u@h" in exc.value.detail
