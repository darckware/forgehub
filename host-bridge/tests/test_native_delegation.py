"""Native review delegation must be bounded by runtime controls, not prose."""
import importlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def options(**changes):
    fields = dict(runtime='codex', max_children=2, mode='plan',
                  runtime_version='codex-cli 0.167.0', package_id='fixture-v1')
    return importlib.import_module('native_delegation').delegation_options(**(fields | changes))


def test_native_review_sets_runtime_limits_without_auth_or_model_changes():
    args, env, manifest = options()
    assert args[args.index('--sandbox') + 1] == 'read-only'
    configs = [args[i + 1] for i, value in enumerate(args) if value == '--config']
    assert 'agents.max_depth=1' in configs
    assert 'agents.max_concurrent_threads_per_session=2' in configs
    assert 'agents.enabled=true' in configs
    assert 'approval_policy="never"' in configs
    assert not env
    assert not any('model' in c or 'provider' in c for c in configs)
    assert manifest['write_policy'] == 'entire-session-read-only'
    assert manifest['result_authority'] == 'advisory-unverified'
    assert manifest['package_id'] == 'fixture-v1'
    assert manifest['max_depth'] == 1
    assert 'spawn_agent' in manifest['instructions']
    assert 'fixture-v1' in manifest['instructions']


@pytest.mark.parametrize('limit', [-1, 0, 4, True, 1.5, '2'])
def test_refuses_invalid_or_unbounded_child_limits(limit):
    with pytest.raises(ValueError, match='child limit'):
        options(max_children=limit)


@pytest.mark.parametrize('runtime', ['claude', 'agy', 'antigravity', 'hermes', 'unknown'])
def test_runtime_without_verified_hard_bound_is_explicitly_unsupported(runtime):
    with pytest.raises(ValueError, match='unsupported bounded native delegation'):
        options(runtime=runtime)


@pytest.mark.parametrize('mode', ['execute', 'write', 'unknown'])
def test_writable_parent_cannot_claim_readonly_worker_isolation(mode):
    with pytest.raises(ValueError, match='read-only plan'):
        options(mode=mode)


@pytest.mark.parametrize('version', ['', 'codex-cli 0.166.0', 'codex-cli 0.168.0'])
def test_unverified_native_version_fails_closed(version):
    with pytest.raises(ValueError, match='not qualified'):
        options(runtime_version=version)


def test_manifest_binds_role_package_and_limits_deterministically():
    _, _, first = options()
    assert first == options()[2]
    assert first['sha256'] != options(max_children=1)[2]['sha256']
    assert first['sha256'] != options(package_id='other-package')[2]['sha256']
    assert first['role'] == 'native-reviewer'
    assert json.loads(json.dumps(first)) == first


def test_delegated_codex_command_removes_inherited_mcp_apps_and_duplicate_sandbox(tmp_path):
    module = importlib.import_module('native_delegation')
    user = tmp_path/'config.toml'
    user.write_text('[mcp_servers.forgevault]\nurl="http://localhost"\n')
    project = tmp_path/'project'/'.codex'/'config.toml'
    project.parent.mkdir(parents=True)
    project.write_text('[mcp_servers.custom_read_write]\ncommand="tool"\n')
    original = ['codex','exec','--config','mcp_servers.forgehub={command="uv"}',
                '--sandbox','read-only','--dangerously-bypass-approvals-and-sandbox',
                '-C',str(tmp_path),'prompt']
    args, _, _ = options()
    command = module.secure_delegated_codex_command(original,[user,project],args,{'managed_remote'})
    assert command.count('--sandbox') == 1
    assert '--dangerously-bypass-approvals-and-sandbox' not in command
    forge_override = next(value for value in command if value.startswith('mcp_servers.forgehub='))
    assert forge_override == 'mcp_servers.forgehub={command="uv",enabled=false}'
    for name in ('forgevault','custom_read_write','managed_remote'):
        assert f'mcp_servers.{name}.enabled=false' in command
    assert command[command.index('--disable') + 1] == 'apps'
    assert command[command.index('--disable') + 3] == 'plugins'


def test_unparseable_inherited_codex_config_refuses_delegation(tmp_path):
    module = importlib.import_module('native_delegation')
    bad = tmp_path/'config.toml'
    bad.write_text('[mcp_servers.broken\n')
    args, _, _ = options()
    with pytest.raises(ValueError, match='safely inventoried'):
        module.secure_delegated_codex_command(['codex','exec','-C',str(tmp_path),'prompt'],[bad],args)


def test_codex_effective_mcp_probe_requires_every_server_disabled(tmp_path, monkeypatch):
    from types import SimpleNamespace
    module = importlib.import_module('native_delegation')
    command = ['codex','exec','--config','mcp_servers.forgehub={command="true",enabled=false}',
               '--config','mcp_servers.forgevault.enabled=false','-C',str(tmp_path),'prompt']
    monkeypatch.setattr(module.subprocess, 'run', lambda *a,**kw:SimpleNamespace(
        returncode=0,stdout='[{"name":"forgehub","enabled":false},{"name":"forgevault","enabled":false}]'))
    assert module.verify_codex_mcp_disabled('codex',tmp_path,{},command) is True
    monkeypatch.setattr(module.subprocess, 'run', lambda *a,**kw:SimpleNamespace(
        returncode=0,stdout='[{"name":"forgevault","enabled":true}]'))
    assert module.verify_codex_mcp_disabled('codex',tmp_path,{},command) is False


@pytest.mark.parametrize('package', ['', '../escape', 'line\nbreak', 'x' * 129])
def test_package_trace_is_bounded_and_not_an_instruction_channel(package):
    with pytest.raises(ValueError, match='package'):
        options(package_id=package)


@pytest.mark.parametrize('runtime,expected', [
    ('codex', ['--config', 'agents.enabled=false', '--config', 'features.multi_agent=false']),
    ('claude', ['--disallowedTools', 'Agent', 'Task']),
])
def test_single_strategy_disables_native_spawn_tools(runtime, expected):
    module = importlib.import_module('native_delegation')
    args, env, manifest = module.single_strategy_options(runtime)
    assert args == expected
    assert env == {}
    assert manifest['strategy'] == 'single'
    assert manifest['max_children'] == 0


@pytest.mark.parametrize('runtime', ['agy', 'antigravity', 'hermes'])
def test_single_strategy_refuses_unverified_runtime_controls(runtime):
    module = importlib.import_module('native_delegation')
    with pytest.raises(ValueError, match='unsupported native single strategy'):
        module.single_strategy_options(runtime)


def native_trace():
    return [
        {'type': 'response_item', 'payload': {'type': 'function_call', 'namespace': 'collaboration',
         'name': 'spawn_agent', 'call_id': 'spawn-1'}},
        {'type': 'response_item', 'payload': {'type': 'function_call_output', 'call_id': 'spawn-1',
         'output': '{"task_name":"/root/reviewer"}'}},
        {'type': 'response_item', 'payload': {'type': 'agent_message', 'author': '/root/reviewer',
         'content': [{'type': 'input_text', 'text': 'Message Type: FINAL_ANSWER\nPayload:\nreview findings'}],
         'internal_chat_message_metadata_passthrough': {'content_item_metadata': [
             {'provenance': {'type': 'tool', 'namespace': 'collaboration'}}]}}},
        {'type': 'event_msg', 'payload': {'type': 'task_complete'}},
    ]


def result(trace=None, **changes):
    fields = dict(exit_code=0, interrupted=False)
    return importlib.import_module('native_delegation').delegation_result(
        native_trace() if trace is None else trace, **(fields | changes))


def test_native_returned_report_remains_advisory_and_unaccepted():
    outcome = result()
    assert outcome['status'] == 'reports_returned'
    assert outcome['child_ids'] == ['/root/reviewer']
    assert outcome['accepted'] is False
    assert outcome['verified'] is False


def test_null_payload_in_rollout_is_treated_as_unproven():
    trace = [{'type': 'event_msg', 'payload': None}, {'type': 'response_item', 'payload': None}]
    assert result(trace)['status'] == 'uncertain'


@pytest.mark.parametrize('trace', [[], native_trace()[:2], native_trace()[:3]])
def test_exit_zero_without_spawn_report_and_parent_completion_is_uncertain(trace):
    assert result(trace)['status'] == 'uncertain'


def test_parent_prose_cannot_impersonate_a_native_child_report():
    trace = native_trace()
    del trace[2]['payload']['internal_chat_message_metadata_passthrough']
    assert result(trace)['status'] == 'uncertain'


@pytest.mark.parametrize('changes,status', [({'exit_code': 1}, 'failed'),
    ({'exit_code': None}, 'uncertain'), ({'interrupted': True}, 'uncertain')])
def test_interrupted_and_failed_process_never_claims_success(changes, status):
    assert result(**changes)['status'] == status


def test_failed_additional_spawn_cannot_hide_behind_one_returned_report():
    trace = native_trace() + [
        {'type': 'response_item', 'payload': {'type': 'function_call', 'namespace': 'collaboration',
         'name': 'spawn_agent', 'call_id': 'spawn-2'}},
        {'type': 'response_item', 'payload': {'type': 'function_call_output', 'call_id': 'spawn-2',
         'output': '{"error":"native concurrency limit"}'}},
    ]
    assert result(trace)['status'] == 'failed'


def test_unacknowledged_additional_spawn_remains_uncertain():
    trace = native_trace() + [
        {'type': 'response_item', 'payload': {'type': 'function_call', 'namespace': 'collaboration',
         'name': 'spawn_agent', 'call_id': 'spawn-2'}},
    ]
    assert result(trace)['status'] == 'uncertain'


def test_rollout_locator_binds_native_thread_id_and_limits_file_size(tmp_path):
    module=importlib.import_module('native_delegation')
    thread='00000000-0000-0000-0000-000000000001'
    rollout=tmp_path/f'rollout-2026-11-11-{thread}.jsonl'
    rollout.write_text('\n'.join(json.dumps(r) for r in native_trace()))
    stdout=json.dumps({'type':'thread.started','thread_id':thread})
    result=module.read_delegation_trace(stdout,root=tmp_path)
    assert module.delegation_result(result,exit_code=0)['status']=='reports_returned'
    assert module.read_delegation_trace(json.dumps({'type':'thread.started','thread_id':'../private'}),root=tmp_path)==[]
    assert module.read_delegation_trace(stdout,root=tmp_path,max_bytes=10)==[]


def test_native_trace_does_not_follow_outside_symlink(tmp_path):
    module = importlib.import_module('native_delegation')
    root = tmp_path/'sessions'
    root.mkdir()
    thread = '00000000-0000-0000-0000-000000000002'
    private = tmp_path/'private'
    private.write_text(json.dumps(native_trace()[0]))
    (root/f'rollout-{thread}.jsonl').symlink_to(private)
    assert module.read_delegation_trace(json.dumps({'type':'thread.started','thread_id':thread}),root=root)==[]
