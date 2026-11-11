"""The runner must execute the requested, traceable contract or refuse before starting."""
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_unknown_runtime_intent_is_not_silently_dropped():
    from runtime_contract import RuntimeIntent
    with pytest.raises(ValueError):
        RuntimeIntent.model_validate({'strategy': 'invented'})


def test_mandatory_skill_content_and_registry_version_are_verified(tmp_path):
    from runtime_contract import RuntimeIntent, prepare_runtime_contract
    skill=tmp_path/'example'/'SKILL.md'
    skill.parent.mkdir()
    skill.write_text('---\nname: example\nversion: 1.0.0\n---\nUse verified evidence.\n')
    intent=RuntimeIntent(skills=[{'name':'example','version':'1.0.0','required':True}])
    prompt, manifest=prepare_runtime_contract(intent, 'codex', 'Do the task', roots=[tmp_path])
    assert 'Use verified evidence.' in prompt
    assert manifest['skills'][0]['sha256']==hashlib.sha256(skill.read_bytes()).hexdigest()
    skill.write_text(skill.read_text().replace('1.0.0','2.0.0'))
    with pytest.raises(ValueError,match='version'):
        prepare_runtime_contract(intent,'codex','Do the task',roots=[tmp_path])


def test_missing_optional_skill_retains_reason_but_required_blocks(tmp_path):
    from runtime_contract import RuntimeIntent, prepare_runtime_contract
    _, manifest=prepare_runtime_contract(RuntimeIntent(skills=[{'name':'missing','version':'1','required':False}]),'codex','Task',roots=[tmp_path])
    assert manifest['unavailable_skills'][0]['name']=='missing'
    with pytest.raises(ValueError,match='missing'):
        prepare_runtime_contract(RuntimeIntent(skills=[{'name':'missing','version':'1'}]),'codex','Task',roots=[tmp_path])


def test_malformed_skill_metadata_is_a_safe_contract_refusal(tmp_path):
    from runtime_contract import RuntimeContractError, RuntimeIntent, prepare_runtime_contract
    skill = tmp_path/'broken'/'SKILL.md'
    skill.parent.mkdir()
    skill.write_text('---\nname: broken\nversion: [\n---\n')
    intent = RuntimeIntent(skills=[{'name':'broken','version':'1.0.0'}])
    with pytest.raises(RuntimeContractError, match='metadata'):
        prepare_runtime_contract(intent, 'codex', 'Task', roots=[tmp_path])


def test_missing_packaged_runtime_skill_is_a_safe_refusal(tmp_path, monkeypatch):
    import runtime_contract
    from runtime_contract import RuntimeContractError, RuntimeIntent
    monkeypatch.setattr(runtime_contract, 'RUNTIME_SKILLS', tmp_path)
    with pytest.raises(RuntimeContractError, match='packaged runtime skill'):
        runtime_contract.prepare_runtime_contract(RuntimeIntent(), 'codex', 'Task', roots=[])


def test_skill_symlink_cannot_escape_trusted_roots(tmp_path):
    from runtime_contract import RuntimeIntent, prepare_runtime_contract
    outside = tmp_path/'private'
    outside.write_text('SECRET')
    root = tmp_path/'skills'
    root.mkdir()
    (root/'escape').symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        prepare_runtime_contract(RuntimeIntent(skills=[{'name':'escape','version':'1'}]),'codex','Task',roots=[root])


def test_unsupported_strategy_is_explicit_and_single_has_no_children():
    from runtime_contract import RuntimeIntent, prepare_runtime_contract
    with pytest.raises(ValueError):
        RuntimeIntent(strategy='single',max_children=2)
    with pytest.raises(ValueError,match='unsupported'):
        prepare_runtime_contract(RuntimeIntent(strategy='delegate',max_children=2),'agy','Task')


def test_contract_hash_covers_context_and_skill_bytes(tmp_path):
    from runtime_contract import RuntimeIntent, prepare_runtime_contract
    intent=RuntimeIntent()
    _, first=prepare_runtime_contract(intent,'codex','Approved scope A',roots=[tmp_path])
    _, second=prepare_runtime_contract(intent,'codex','Approved scope B',roots=[tmp_path])
    assert first['input_sha256'] != second['input_sha256']


def test_agent_run_request_preserves_requested_strategy():
    import app
    req=app.AgentRunRequest(run_id='00000000-0000-0000-0000-000000000001',runtime_type='codex',project_path='/tmp',prompt='Task',runtime_intent={'version':'forge-runtime-intent/v1'})
    assert req.model_dump()['runtime_intent']['version']=='forge-runtime-intent/v1'


def test_native_contract_is_durable_before_process_launch(monkeypatch,tmp_path):
    import asyncio
    import app
    from types import SimpleNamespace
    monkeypatch.setattr(app,'BRIDGE_TOKEN','test-token')
    monkeypatch.setattr(app,'_agent_runs',{})
    persisted=[]
    monkeypatch.setattr(app,'_persist_agent_run',lambda run_id:persisted.append(dict(app._agent_runs[run_id])))
    monkeypatch.setattr(app,'resolve_runtime_executable',lambda *a,**k:'/bin/codex')
    monkeypatch.setattr(app,'runtime_version',lambda *a:'codex-cli 0.167.0')
    def spawn(*a,**kw):
        assert persisted[0]['runtime_contract']['runtime_version']=='codex-cli 0.167.0'
        assert persisted[0]['runtime_contract']['skills']
        assert 'forge-runtime-codex' in a[0][-1]
        return SimpleNamespace(pid=123)
    monkeypatch.setattr(app.subprocess,'Popen',spawn)
    monkeypatch.setattr(app.threading,'Thread',lambda **kw:SimpleNamespace(start=lambda:None))
    req=app.AgentRunRequest(run_id='00000000-0000-0000-0000-000000000002',runtime_type='codex',project_path=str(tmp_path),prompt='Task',runtime_intent={})
    result=asyncio.run(app.start_agent_run(req,'test-token'))
    assert result['runtime_contract']['sha256']==persisted[0]['runtime_contract']['sha256']


def test_contextual_route_refuses_missing_contract(monkeypatch):
    import asyncio
    import app
    from fastapi import HTTPException
    monkeypatch.setattr(app,'BRIDGE_TOKEN','test-token')
    req=app.AgentRunRequest(run_id='00000000-0000-0000-0000-000000000001',runtime_type='codex',project_path='/tmp',prompt='Task')
    with pytest.raises(HTTPException) as refused:
        asyncio.run(app.start_contextual_agent_run(req,'test-token'))
    assert refused.value.status_code==400


@pytest.mark.parametrize('strategy,mode,expected',[('single','execute','agents.enabled=false'),('delegate','plan','agents.max_concurrent_threads_per_session=2')])
def test_contextual_strategy_reaches_native_controls(monkeypatch,tmp_path,strategy,mode,expected):
    import asyncio
    import app
    from types import SimpleNamespace
    monkeypatch.setattr(app,'BRIDGE_TOKEN','test-token')
    monkeypatch.setattr(app,'_agent_runs',{})
    monkeypatch.setattr(app,'_persist_agent_run',lambda *_:None)
    monkeypatch.setattr(app,'resolve_runtime_executable',lambda *a,**kw:'/bin/codex')
    monkeypatch.setattr(app,'runtime_version',lambda *a:'codex-cli 0.167.0')
    import native_delegation
    monkeypatch.setattr(native_delegation,'discover_codex_mcp_names',lambda *a,**kw:{'forgevault'})
    monkeypatch.setattr(native_delegation,'verify_codex_mcp_disabled',lambda *a,**kw:True)
    commands=[]
    def spawn(command,**kwargs):
        commands.append(command)
        return SimpleNamespace(pid=123)
    monkeypatch.setattr(app.subprocess,'Popen',spawn)
    monkeypatch.setattr(app.threading,'Thread',lambda **kw:SimpleNamespace(start=lambda:None))
    req=app.AgentRunRequest(run_id='00000000-0000-0000-0000-000000000003',runtime_type='codex',project_path=str(tmp_path),prompt='Review',mode=mode,runtime_intent={'strategy':strategy,'max_children':2 if strategy=='delegate' else 0})
    result=asyncio.run(app.start_contextual_agent_run(req,'test-token'))
    assert expected in commands[0]
    assert result['runtime_contract']['native_strategy']['strategy']==strategy
    if strategy=='delegate':
        assert commands[0][commands[0].index('--sandbox')+1]=='read-only'
        assert '--dangerously-bypass-approvals-and-sandbox' not in commands[0]
        assert 'mcp_servers.forgevault.enabled=false' in commands[0]
        assert '--disable' in commands[0] and 'apps' in commands[0] and 'plugins' in commands[0]
        assert 'spawn_agent' in commands[0][-1]


def test_zero_exit_does_not_complete_delegation_without_native_child_proof(monkeypatch):
    import app
    from types import SimpleNamespace
    import native_delegation
    run={'runtime_contract':{'strategy':'delegate'}}
    monkeypatch.setattr(app,'_agent_runs',{'delegated':run})
    monkeypatch.setattr(app,'_persist_agent_run',lambda *_:None)
    monkeypatch.setattr(native_delegation,'read_delegation_trace',lambda *_:[])
    proc=SimpleNamespace(returncode=0,communicate=lambda **kw:('Root says complete',''),pid=123)
    app._monitor_agent_run('delegated',proc,30)
    assert run['status']=='stale'
    assert run['delegation']['status']=='uncertain'
    assert run['delegation']['accepted'] is False
