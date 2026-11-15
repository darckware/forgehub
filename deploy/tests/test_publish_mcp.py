"""deploy/publish_mcp.py: an immutable copy of one commit, switched atomically."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

SPEC = importlib.util.spec_from_file_location('publish_mcp', Path(__file__).parents[1] / 'publish_mcp.py')
m = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = m
SPEC.loader.exec_module(m)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    repo = tmp_path / 'repo'
    (repo / 'backend/app/mcp').mkdir(parents=True)
    (repo / 'host-bridge').mkdir()
    (repo / 'backend/app/mcp/factory_server.py').write_text('VERSION = 1\n')
    (repo / 'host-bridge/forgehub_messages_mcp.py').write_text('X = 1\n')
    (repo / 'host-bridge/app.py').write_text('SECRET_FREE = True\n')
    _git(repo, 'init', '-q')
    _git(repo, 'add', '.')
    _git(repo, '-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'one')
    monkeypatch.setattr(m, 'REPO', repo)
    monkeypatch.setattr(m, 'MCP_HOME', tmp_path / 'mcp')
    return repo


def test_publish_copies_only_mcp_paths_and_points_current(repo):
    result = m.publish('HEAD')
    current = m.MCP_HOME / 'current'
    assert os.readlink(current) == result['current']
    assert (current / 'backend/app/mcp/factory_server.py').read_text() == 'VERSION = 1\n'
    assert (current / 'host-bridge/forgehub_messages_mcp.py').is_file()
    assert not (current / 'host-bridge/app.py').exists()
    assert json.loads((current / 'release.json').read_text())['commit'] == _git(repo, 'rev-parse', 'HEAD')
    assert result['previous'] is None


def test_republish_switches_and_keeps_the_previous_copy(repo):
    first = m.publish('HEAD')
    (repo / 'backend/app/mcp/factory_server.py').write_text('VERSION = 2\n')
    _git(repo, '-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qam', 'two')
    second = m.publish('HEAD')
    assert second['previous'] == first['current']
    assert Path(first['current']).is_dir()
    assert (m.MCP_HOME / 'current/backend/app/mcp/factory_server.py').read_text() == 'VERSION = 2\n'
    assert m.status()['commit'] == _git(repo, 'rev-parse', 'HEAD')


def test_a_commit_that_does_not_compile_is_never_switched_to(repo):
    m.publish('HEAD')
    before = os.readlink(m.MCP_HOME / 'current')
    (repo / 'backend/app/mcp/factory_server.py').write_text('def broken(:\n')
    _git(repo, '-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qam', 'broken')
    with pytest.raises(Exception):
        m.publish('HEAD')
    assert os.readlink(m.MCP_HOME / 'current') == before


def test_unknown_commit_says_why(repo):
    with pytest.raises(SystemExit, match='git rev-parse failed'):
        m.publish('no-such-ref')
    assert not (m.MCP_HOME / 'current').exists()


def test_a_broken_helper_module_is_never_published(repo):
    (repo / 'backend/app/mcp/helper.py').write_text('def broken(:\n')
    _git(repo, 'add', '.')
    _git(repo, '-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'helper')
    with pytest.raises(SyntaxError):
        m.publish('HEAD')
    assert not (m.MCP_HOME / 'current').exists()
    assert not list((m.MCP_HOME / 'releases').glob('*.tmp'))
