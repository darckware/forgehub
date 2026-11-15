"""ECO-072: production switches match the versioned file; agents run the published MCP code."""
import importlib.util
import json
from pathlib import Path
import sys

SPEC = importlib.util.spec_from_file_location('rt_verifier', Path(__file__).parents[1] / 'checklist_verifier.py')
v = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = v
SPEC.loader.exec_module(v)

CURRENT = '/root/.forgehub/mcp/current/backend/app/mcp/factory_server.py'
CHECKOUT = '/root/project/forgehub/backend/app/mcp/factory_server.py'


def test_flags_match_ignoring_boolean_spelling():
    expected = v._parse_env('# comment\nA_ENABLED=true\nB_ENABLED=false\n')
    assert v.production_flag_findings(expected, ['A_ENABLED=True', 'B_ENABLED=0', 'PATH=/bin']) == []


def test_flags_report_a_switch_turned_off_or_missing():
    expected = v._parse_env('MESSAGE_ANALYSIS_ON_DEMAND_ENABLED=true\nMISSION_TOOLS_ENABLED=true\n')
    findings = v.production_flag_findings(expected, ['MESSAGE_ANALYSIS_ON_DEMAND_ENABLED=false'])
    assert findings == [
        'forgehub-backend: MESSAGE_ANALYSIS_ON_DEMAND_ENABLED=false (expected true)',
        'forgehub-backend: MISSION_TOOLS_ENABLED not set (expected true)',
    ]


def _profile(root: Path, name: str, args: list[str], wrapper: str | None = None) -> None:
    directory = root / 'profiles' / name
    directory.mkdir(parents=True)
    (directory / 'config.yaml').write_text(
        'mcp_servers:\n  forgehub:\n    command: /usr/bin/python3\n    args:\n'
        + ''.join(f'      - {a}\n' for a in args)
        + '  moodle:\n    command: node\n    args: [/root/project/moodle/mcp-server/src/index.ts]\n')
    if wrapper is not None:
        (directory / 'mcp').mkdir()
        (directory / 'mcp/forgehub.py').write_text(wrapper)


def _current(tmp_path: Path) -> Path:
    release = tmp_path / 'mcp/releases/abc'
    (release / 'backend/app/mcp').mkdir(parents=True)
    (release / 'backend/app/mcp/factory_server.py').write_text('')
    link = tmp_path / 'mcp/current'
    link.symlink_to(release)
    return link


def test_published_sources_pass(tmp_path):
    _profile(tmp_path, 'athos', ['/root/.hermes/scripts/forgehub_vault_token.py', 'athos', 'uv', 'run', CURRENT])
    _profile(tmp_path, 'maia', ['/root/.hermes/scripts/x.py', 'maia', 'uv', 'run', '/root/.hermes/profiles/maia/mcp/forgehub.py'],
             wrapper='ROOT = Path("/root/.forgehub/mcp/current/backend/app/mcp")\n')
    codex = tmp_path / 'config.toml'
    codex.write_text(f'[mcp_servers.forgehub]\ncommand = "uv"\nargs = ["run", "{CURRENT}"]\n')
    agy = tmp_path / 'mcp_config.json'
    agy.write_text(json.dumps({'mcpServers': {'forgehub_dispatched': {
        'command': 'uv', 'args': ['run', '/root/.forgehub/mcp/current/host-bridge/forgehub_messages_mcp.py']}}}))
    assert v.mcp_source_findings(tmp_path, codex, agy, _current(tmp_path)) == []


def test_checkout_pinned_release_and_missing_current_are_reported(tmp_path):
    _profile(tmp_path, 'athos', ['uv', 'run', CHECKOUT])
    _profile(tmp_path, 'maia', ['uv', 'run', '/root/.hermes/profiles/maia/mcp/forgehub.py'],
             wrapper='ROOT = Path("/root/.forgehub/releases/maia-group-buttons-8ddc9b7/backend/app/mcp")\n')
    agy = tmp_path / 'mcp_config.json'
    agy.write_text(json.dumps({'mcpServers': {'forgehub_dispatched': {
        'command': 'uv', 'args': ['run', '/root/project/forgehub/host-bridge/forgehub_messages_mcp.py']}}}))
    findings = v.mcp_source_findings(tmp_path, tmp_path / 'none.toml', agy, tmp_path / 'mcp/current')
    assert any('missing or incomplete' in f for f in findings)
    assert any(f.startswith("athos: MCP 'forgehub' runs " + CHECKOUT) for f in findings)
    assert any(f.startswith('maia: mcp/forgehub.py loads') for f in findings)
    assert any(f.startswith("agy: MCP 'forgehub_dispatched'") for f in findings)
    assert not any('moodle' in f for f in findings)


def test_maia_wrapper_must_load_from_current_not_merely_mention_it(tmp_path):
    _profile(tmp_path, 'maia', ['uv', 'run', '/root/.hermes/profiles/maia/mcp/forgehub.py'],
             wrapper='# moved to /root/.forgehub/mcp/current/ later\n'
                     'ROOT = Path("/root/.forgehub/releases/old/backend/app/mcp")\n')
    findings = v.mcp_source_findings(tmp_path, tmp_path / 'none.toml', tmp_path / 'none.json', _current(tmp_path))
    assert findings == ['maia: mcp/forgehub.py loads ForgeHub MCP code from outside ' + str(tmp_path / 'mcp/current')]
