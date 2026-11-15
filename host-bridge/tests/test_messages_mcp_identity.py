"""MCP split Fase 2a: the Messages MCP sends the agent's own agt_ credential with every call."""
import asyncio
import importlib.util
from pathlib import Path

import httpx

PATH = Path(__file__).resolve().parents[1] / 'forgehub_messages_mcp.py'


def load():
    spec = importlib.util.spec_from_file_location('identity_messages_mcp', PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dispatch_file_wins_over_profile_token(tmp_path, monkeypatch):
    m = load()
    credential = tmp_path / 'run-token'
    credential.write_text('agt_from_file\n')
    monkeypatch.setenv('FORGEHUB_AGENT_TOKEN_FILE', str(credential))
    monkeypatch.setenv('FORGEHUB_AGENT_TOKEN', 'agt_from_env')
    assert m._identity_headers() == {'Authorization': 'Bearer agt_from_file'}


def test_profile_token_when_no_file(monkeypatch):
    m = load()
    monkeypatch.delenv('FORGEHUB_AGENT_TOKEN_FILE', raising=False)
    monkeypatch.delenv('XDG_FORGEHUB_AGENT_TOKEN_FILE', raising=False)
    monkeypatch.setenv('FORGEHUB_AGENT_TOKEN', 'agt_from_env')
    assert m._identity_headers() == {'Authorization': 'Bearer agt_from_env'}


def test_no_or_foreign_credential_sends_nothing(tmp_path, monkeypatch):
    m = load()
    missing = tmp_path / 'gone'
    monkeypatch.setenv('FORGEHUB_AGENT_TOKEN_FILE', str(missing))
    monkeypatch.setenv('FORGEHUB_AGENT_TOKEN', 'not-an-agent-token')
    assert m._identity_headers() == {}


def test_every_call_carries_both_tokens(monkeypatch):
    m = load()
    monkeypatch.delenv('FORGEHUB_AGENT_TOKEN_FILE', raising=False)
    monkeypatch.delenv('XDG_FORGEHUB_AGENT_TOKEN_FILE', raising=False)
    monkeypatch.setenv('FORGEHUB_AGENT_TOKEN', 'agt_me')
    monkeypatch.setenv('FORGEHUB_BRIDGE_TOKEN', 'bridge-secret')
    seen = {}

    def handler(request):
        seen.update(request.headers)
        return httpx.Response(200, json={'ok': True})

    real_client = httpx.AsyncClient

    def client(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(m.httpx, 'AsyncClient', client)
    assert asyncio.run(m._call('GET', '/api/v1/agents')) == {'ok': True}
    assert seen['authorization'] == 'Bearer agt_me'
    assert seen['x-bridge-token'] == 'bridge-secret'


def test_approval_requested_is_never_reported_as_done(monkeypatch):
    """MCP-023: a restart or query outside the agent's function comes back 202 APPROVAL_REQUESTED."""
    m = load()
    monkeypatch.setenv('FORGEHUB_BRIDGE_TOKEN', 'bridge-secret')
    body = {'detail': {'code': 'APPROVAL_REQUESTED', 'message': 'pedido #7 enviado para aprovação', 'message_number': 7}}
    real_client = httpx.AsyncClient

    def client(**kwargs):
        return real_client(transport=httpx.MockTransport(lambda r: httpx.Response(202, json=body)), **kwargs)

    monkeypatch.setattr(m.httpx, 'AsyncClient', client)
    try:
        asyncio.run(m._call('POST', '/api/v1/deploy/containers/x/restart'))
    except m.ForgeHubError as exc:
        assert 'pedido #7' in str(exc)
    else:
        raise AssertionError('an approval request must not read as success')
