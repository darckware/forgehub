"""ECO-039 Docker limits (Marcelo, 2026-11-13). Fixtures replace only docker commands."""
import importlib.util
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


p = load("eco039_prune", "prune_unused_docker_images.py")
v = load("eco039_verifier", "checklist_verifier.py")

NOW = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
OLD = NOW - timedelta(days=30)
RECENT = NOW - timedelta(days=2)


def image(image_id, refs, created=OLD, last_tag=None, unique=10**9, containers=0):
    return {"id": image_id, "refs": refs, "created": created, "last_tag": last_tag,
            "unique": unique, "containers": containers}


@pytest.mark.parametrize("text,expected", [("10.53GB", 10_530_000_000), ("131.1kB", 131_100), ("0B", 0), ("12.82GB (38%)", 12_820_000_000)])
def test_parse_size_uses_docker_decimal_units(text, expected):
    assert p.parse_size(text) == expected


def test_parse_time_handles_nanoseconds_and_zero():
    assert p.parse_time("0001-01-01T00:00:00Z") is None
    assert p.parse_time("2026-11-13T21:50:15.432048824Z") == datetime(2026, 11, 13, 21, 50, 15, 432048, tzinfo=timezone.utc)


def test_compose_image_refs_normalizes_latest(tmp_path):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services:\n  a:\n    image: forgehub-test-backend:local\n  b:\n    image: 'nginx'\n")
    assert p.compose_image_refs(compose) == {"forgehub-test-backend:local", "nginx:latest"}


def test_classify_protects_used_recent_and_test_env_images():
    images = {i["id"]: i for i in [
        image("used", ["a:1"]),
        image("stopped-container", ["b:1"], containers=1),
        image("release", ["forgehub-backend:fh-abc"], created=RECENT),
        image("rollback", ["registry/x:rollback-abc"], created=RECENT),
        image("retagged", ["old:base"], created=OLD, last_tag=RECENT),  # pulled/tagged for a deploy
        image("test-env", ["forgehub-test-tools:local"]),
        image("compose", ["nginx:1.27-alpine"]),
        image("old-release", ["forgehub-backend:fh-old"], created=OLD),
        image("newer", ["c:1"], created=OLD + timedelta(days=1)),
        image("oldest", [], created=OLD - timedelta(days=1)),
    ]}
    removable, protected = p.classify(images, {"used"}, NOW, {"nginx:1.27-alpine"})
    assert [i["id"] for i in removable] == ["oldest", "old-release", "newer"]
    assert {i["id"]: i["reason"] for i in protected} == {
        "release": "recent release tag", "rollback": "recent release tag",
        "retagged": "tagged in the last 7 days", "test-env": "ForgeHub test environment",
        "compose": "ForgeHub test environment"}


def test_measure_excludes_protected_bytes(monkeypatch):
    monkeypatch.setattr(p, "reclaimable_bytes", lambda: 12 * 10**9)
    monkeypatch.setattr(p, "inventory", lambda: {"r": image("r", ["forgehub-x:fh-1"], created=RECENT, unique=5 * 10**9),
                                                 "o": image("o", ["o:1"], unique=10**9)})
    monkeypatch.setattr(p, "used_image_ids", set)
    monkeypatch.setattr(p, "compose_image_refs", set)
    state = p.measure(NOW)
    assert (state["unused"], state["protected_bytes"]) == (7 * 10**9, 5 * 10**9)
    assert [i["id"] for i in state["removable"]] == ["o"]


def test_rm_timeout_is_logged_and_skipped(monkeypatch, capsys):
    states = iter([
        {"reclaimable": 12 * 10**9, "protected_bytes": 0, "unused": 12 * 10**9, "protected": [],
         "removable": [image("a", ["a:1"], unique=3 * 10**9)]},
        {"reclaimable": 12 * 10**9, "protected_bytes": 0, "unused": 12 * 10**9, "protected": [],
         "removable": [image("a", ["a:1"], unique=3 * 10**9)]},
    ])
    monkeypatch.setattr(p, "measure", lambda now=None: next(states))
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        raise subprocess.TimeoutExpired(args, kwargs.get("timeout"))
    monkeypatch.setattr(p.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["prune"])
    assert p.main() == 0
    out = capsys.readouterr().out
    assert calls == [["docker", "image", "rm", "a:1"]]  # explicit tag, no force
    assert "timed out" in out and "no removable image left" in out


def test_prune_script_has_no_forbidden_docker_arguments():
    text = (ROOT / "prune_unused_docker_images.py").read_text()
    import re
    assert not re.search(r'"(prune|volume|--force|-f|-a|--all)"', text)


def _df(build_cache):
    rows = [f'{{"Type":"Build Cache","Size":"{build_cache}","Reclaimable":"0B"}}',
            '{"Type":"Images","Size":"27GB","Reclaimable":"10.53GB (38%)"}']
    return subprocess.CompletedProcess([], 0, "\n".join(rows), "")


@pytest.mark.parametrize("build_cache,unused,expect_ok", [
    ("12.82GB", 0.64e9, True), ("15.5GB", 0.64e9, False), ("1GB", 10.2e9, False)])
def test_check_reports_sizes_against_limits(monkeypatch, tmp_path, build_cache, unused, expect_ok):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/create_trash_cleanup_task.sh").write_text("python3 -I prune_unused_docker_images.py\n")
    monkeypatch.setattr(v, "ATHOS", tmp_path)
    monkeypatch.setattr(v, "DOCKER_IMAGE_PRUNE_SCRIPT", ROOT / "prune_unused_docker_images.py")
    monkeypatch.setattr(v, "check_disk_cleanup", lambda: v.ok("baseline"))
    monkeypatch.setattr(v, "run", lambda args, **kw: _df(build_cache))
    fake = type("Prune", (), {"parse_size": staticmethod(p.parse_size), "measure": staticmethod(
        lambda: {"unused": int(unused), "reclaimable": 10_530_000_000, "protected_bytes": 1, "protected": [1]})})
    monkeypatch.setattr(v, "_docker_image_prune_module", lambda path: fake)
    result = v.check_disk_cleanup_v2()
    assert result.ok is expect_ok
    assert "build cache" in result.notes and "unused images" in result.notes


def test_check_fails_without_weekly_prune_step(monkeypatch, tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/create_trash_cleanup_task.sh").write_text("docker builder prune --all --force\n")
    monkeypatch.setattr(v, "ATHOS", tmp_path)
    monkeypatch.setattr(v, "DOCKER_IMAGE_PRUNE_SCRIPT", ROOT / "prune_unused_docker_images.py")
    monkeypatch.setattr(v, "check_disk_cleanup", lambda: v.ok("baseline"))
    result = v.check_disk_cleanup_v2()
    assert not result.ok and "lacks the unused-image prune step" in result.notes
