import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

spec = importlib.util.spec_from_file_location('forgehub_vault_token', Path(__file__).resolve().parents[1] / 'forgehub_vault_token.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

SECRET_ID = '8c2f8555-56fa-4803-a3ef-10e5a615fe41'
FAKE_TOKEN = 'agt_' + 'x' * 32


@pytest.fixture(autouse=True)
def config(tmp_path, monkeypatch):
    root = tmp_path / 'profiles'
    (root / 'maia').mkdir(parents=True)
    (root / 'maia' / 'forgehub-vault.json').write_text(json.dumps({'secret_id': SECRET_ID}))
    monkeypatch.setattr(module, 'PROFILE_ROOT', root)
    monkeypatch.setattr(module, 'CREDENTIAL_ROOT', tmp_path / 'credentials')
    monkeypatch.setattr(module.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(stdout='fv_sa_' + 'x' * 32))
    module._cache.clear()
    yield
    module._cache.clear()


def response(payload):
    return io.BytesIO(json.dumps(payload).encode())


def test_fetches_only_the_configured_secret_and_caches_it(monkeypatch):
    calls = []
    def open_url(request, timeout):
        calls.append(request.full_url)
        return response({'resource': SECRET_ID, 'accessMode': 'REVEAL', 'credentials': {'value': FAKE_TOKEN}})
    monkeypatch.setattr(module.urllib.request, 'urlopen', open_url)
    assert module.get_agent_token('maia') == FAKE_TOKEN
    assert module.get_agent_token('maia') == FAKE_TOKEN
    assert len(calls) == 1
    assert SECRET_ID in calls[0]
    assert FAKE_TOKEN not in calls[0]


def test_refuses_a_mismatched_secret_and_unsupported_profile(monkeypatch):
    monkeypatch.setattr(module.urllib.request, 'urlopen', lambda *args, **kwargs: response({
        'resource': 'other', 'accessMode': 'REVEAL', 'credentials': {'value': FAKE_TOKEN},
    }))
    with pytest.raises(module.CredentialUnavailable):
        module.get_agent_token('maia')
    with pytest.raises(module.CredentialUnavailable):
        module.get_agent_token('unknown')


def test_vault_denial_does_not_leak_credentials(monkeypatch):
    def reject(request, timeout):
        raise HTTPError(request.full_url, 403, FAKE_TOKEN, {}, None)
    monkeypatch.setattr(module.urllib.request, 'urlopen', reject)
    with pytest.raises(module.CredentialUnavailable) as error:
        module.get_agent_token('maia')
    assert FAKE_TOKEN not in str(error.value)


def test_wrapper_passes_the_vault_value_in_environment_only(monkeypatch):
    monkeypatch.setattr(module, 'get_agent_token', lambda profile: FAKE_TOKEN)
    monkeypatch.setattr(module.sys, 'argv', ['wrapper', 'maia', 'mcp-server', '--stdio'])
    captured = {}
    def exec_process(command, args, env):
        captured.update(command=command, args=args, token=env['FORGEHUB_AGENT_TOKEN'])
    monkeypatch.setattr(module.os, 'execvpe', exec_process)
    module.main()
    assert captured == {'command': 'mcp-server', 'args': ['mcp-server', '--stdio'], 'token': FAKE_TOKEN}
    assert all(FAKE_TOKEN not in arg for arg in captured['args'])
