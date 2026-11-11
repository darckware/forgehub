"""Isolated contract checks; never contact a machine or the shared browser."""
import asyncio
import importlib.util
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'host-bridge'))


def load_server(kind):
    path = ROOT / ('host-bridge/forgehub_messages_mcp.py' if kind == 'messages'
                   else 'backend/app/mcp/factory_server.py')
    spec = importlib.util.spec_from_file_location(f't12_{kind}', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('kind', ['messages', 'factory'])
def test_browser_capability_exposes_only_isolated_context(kind, monkeypatch):
    module = load_server(kind)

    def forbidden(*args, **kwargs):
        pytest.fail('Capability inventory must never inspect or launch the shared browser')

    monkeypatch.setattr(httpx, 'AsyncClient', forbidden)
    catalog = {tool.name for tool in asyncio.run(module.mcp.list_tools())}
    assert 'get_workspace_browser_capabilities' in catalog
    result = asyncio.run(module.get_workspace_browser_capabilities())
    assert result['supported'] is True
    assert result['isolated'] is True
    assert set(result['operations']) == {'open', 'read', 'navigate', 'close', 'fill', 'click', 'submit'}
    assert result['shared_authenticated_context'] is False
    assert 'arbitrary_javascript' in result['unsupported']
    assert 'cdp_url' not in result


@pytest.mark.parametrize('kind', ['messages', 'factory'])
@pytest.mark.parametrize('failure', ['timeout', 'disconnect', '502', '504', 'invalid_json'])
def test_lost_remote_ack_is_uncertain_and_never_retried(kind, failure, tmp_path, monkeypatch):
    module = load_server(kind)
    transport_module = module if kind == 'messages' else module.messages
    credential = tmp_path / 'credential'
    credential.write_text('agt_synthetic_t12')
    monkeypatch.setenv('FORGEHUB_AGENT_TOKEN_FILE', str(credential))
    seen = []

    def handle(request):
        seen.append(request)
        if failure == 'timeout':
            raise httpx.ReadTimeout('agt_secret_in_transport_error', request=request)
        if failure == 'disconnect':
            raise httpx.RemoteProtocolError('agt_secret_in_transport_error', request=request)
        if failure == 'invalid_json':
            return httpx.Response(200, text='agt_secret_in_response')
        return httpx.Response(int(failure), text='agt_secret_in_response')

    original = httpx.AsyncClient
    monkeypatch.setattr(transport_module.httpx, 'AsyncClient',
                        lambda **kw: original(**kw, transport=httpx.MockTransport(handle)))
    with pytest.raises(transport_module.ForgeHubError) as error:
        asyncio.run(module.run_remote_command(['machine'], 'true', 'Synthetic qualification', 42))
    assert 'UPSTREAM_UNCERTAIN' in str(error.value)
    assert 'reconcile' in str(error.value).lower()
    assert 'agt_secret' not in str(error.value)
    assert len(seen) == 1


@pytest.mark.parametrize('kind', ['messages', 'factory'])
def test_recovery_and_verified_learning_visible_in_each_catalog(kind):
    module = load_server(kind)
    names = {tool.name for tool in asyncio.run(module.mcp.list_tools())}
    assert {'get_task_context', 'propose_verified_learning'} <= names
