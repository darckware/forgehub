import asyncio
import importlib
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def broker(tmp_path):
    module = importlib.import_module('task_browser')
    calls = []

    async def cdp(target, method, params=None):
        calls.append((target, method, params))
        if method == 'Target.createBrowserContext':
            return {'browserContextId': 'isolated-context'}
        if method == 'Target.createTarget':
            return {'targetId': 'isolated-page'}
        if method == 'Runtime.evaluate':
            return {'result': {'value': {'url': 'https://test.invalid/', 'title': 'Test', 'text': 'Untrusted'}}}
        return {}

    return module.TaskBrowserBroker(tmp_path / 'browser.sqlite', cdp,
                                    allowed_hosts={'test.invalid', 'other.invalid'}), calls


def test_context_never_uses_shared_target_and_replays_navigation(tmp_path):
    b, calls = broker(tmp_path)
    async def run():
        opened = await b.act('task:run', 'open-key', 'open')
        assert opened['status'] == 'completed'
        result = await b.act('task:run', 'navigate-key', 'navigate', 'https://test.invalid/')
        assert await b.act('task:run', 'navigate-key', 'navigate', 'https://test.invalid/') == result
        assert [m for _, m, _ in calls].count('Page.navigate') == 1
        assert calls[1][2]['browserContextId'] == 'isolated-context'
        assert all(target == 'isolated-page' for target, method, _ in calls if method.startswith(('Page.', 'Runtime.')))
        with pytest.raises(HTTPException) as error:
            await b.act('task:run', 'navigate-key', 'navigate', 'https://other.invalid/')
        assert error.value.status_code == 409
    asyncio.run(run())


def test_lost_navigation_ack_is_durable_uncertainty_not_repetition(tmp_path):
    b, calls = broker(tmp_path)
    async def run():
        await b.act('task:run', 'open', 'open')
        original = b.cdp
        async def lost(target, method, params=None):
            if method == 'Page.navigate':
                calls.append((target, method, params))
                raise TimeoutError('lost after effect')
            return await original(target, method, params)
        b.cdp = lost
        first = await b.act('task:run', 'navigate', 'navigate', 'https://test.invalid/')
        assert first['status'] == 'uncertain'
        b2 = type(b)(b.path, lost, allowed_hosts=b.allowed_hosts)
        assert await b2.act('task:run', 'navigate', 'navigate', 'https://test.invalid/') == first
        assert [m for _, m, _ in calls].count('Page.navigate') == 1
        assert (await b2.act('task:run', 'read', 'read'))['status'] == 'completed'
    asyncio.run(run())


def test_other_scope_and_closed_context_cannot_act(tmp_path):
    b, calls = broker(tmp_path)
    async def run():
        await b.act('task:run', 'open', 'open')
        with pytest.raises(HTTPException):
            await b.act('task:other-run', 'read', 'read')
        await b.act('task:run', 'close', 'close')
        before = len(calls)
        with pytest.raises(HTTPException):
            await b.act('task:run', 'late', 'navigate', 'https://test.invalid/')
        assert len(calls) == before
    asyncio.run(run())


def test_uncertainty_fences_fresh_navigation_until_read_reconciliation(tmp_path):
    b, calls = broker(tmp_path)
    async def run():
        await b.act('task:run', 'open', 'open')
        original = b.cdp
        async def lost(target, method, params=None):
            if method == 'Page.navigate':
                raise TimeoutError('lost')
            return await original(target, method, params)
        b.cdp = lost
        await b.act('task:run', 'navigate', 'navigate', 'https://test.invalid/')
        with pytest.raises(HTTPException):
            await b.act('task:run', 'fresh-key', 'navigate', 'https://test.invalid/')
        await b.act('task:run', 'reconcile', 'read')
        b.cdp = original
        with pytest.raises(HTTPException):
            await b.act('task:run', 'new-key', 'navigate', 'https://test.invalid/')
    asyncio.run(run())


def test_expiry_disposes_context_and_fences_commands(tmp_path, monkeypatch):
    b, calls = broker(tmp_path)
    async def run():
        await b.act('task:run', 'open', 'open')
        with b.connect() as db:
            db.execute('UPDATE sessions SET expires=0')
        await b.expire()
        assert calls[-1][1] == 'Target.disposeBrowserContext'
        with pytest.raises(HTTPException):
            await b.act('task:run', 'late', 'read')
    asyncio.run(run())


@pytest.mark.parametrize('action', ['fill', 'click', 'submit'])
def test_scoped_input_has_no_arbitrary_script_and_lost_ack_fences_repetition(tmp_path, action):
    b, calls = broker(tmp_path)
    async def run():
        await b.act('task:run', 'open', 'open')
        original = b.cdp
        async def lost(target, method, params=None):
            calls.append((target, method, params))
            raise TimeoutError('lost after site effect')
        b.cdp = lost
        result = await b.act('task:run', 'input-key', action, selector='#test', text='value' if action == 'fill' else None)
        assert result['status'] == 'uncertain'
        assert await b.act('task:run', 'input-key', action, selector='#test', text='value' if action == 'fill' else None) == result
        assert calls[-1][0] == 'isolated-page'
        assert calls[-1][1] == 'Runtime.evaluate'
        with pytest.raises(HTTPException):
            await b.act('task:run', 'repeat-with-new-key', action, selector='#test', text='value' if action == 'fill' else None)
        b.cdp = original
        await b.act('task:run', 'reconcile', 'read')
    asyncio.run(run())


def test_submission_ack_is_not_business_confirmation(tmp_path):
    b, calls = broker(tmp_path)
    async def run():
        await b.act('task:run', 'open', 'open')
        result = await b.act('task:run', 'submit', 'submit', selector='#form')
        assert result['status'] == 'uncertain'
        assert result['applied'] is True
        with pytest.raises(HTTPException):
            await b.act('task:run', 'another-submit', 'submit', selector='#form')
    asyncio.run(run())


def test_failed_read_cannot_release_uncertain_submission_fence(tmp_path):
    b, calls = broker(tmp_path)
    async def run():
        await b.act('task:run', 'open', 'open')
        await b.act('task:run', 'submit', 'submit', selector='#form')
        async def failed_read(*args):
            return {'exceptionDetails': {'text': 'Context destroyed'}}
        b.cdp = failed_read
        assert (await b.act('task:run', 'reconcile', 'read'))['status'] == 'uncertain'
        with pytest.raises(HTTPException):
            await b.act('task:run', 'fresh-submit', 'submit', selector='#form')
    asyncio.run(run())


def test_read_does_not_clear_submission_and_human_reconciles_exact_operation(tmp_path):
    b, calls = broker(tmp_path)
    async def run():
        await b.act('task:run', 'open', 'open')
        await b.act('task:run', 'submit', 'submit', selector='#form')
        await b.act('task:run', 'read-after-submit', 'read')
        with pytest.raises(HTTPException):
            await b.act('task:run', 'another-submit', 'submit', selector='#form')
        await b.control('task:run', 'human', 'take')
        with pytest.raises(HTTPException):
            await b.act('task:run', 'agent-navigation', 'navigate', 'https://test.invalid/')
        observed = await b.control('task:run', 'human', 'read')
        with pytest.raises(HTTPException):
            await b.control('task:run', 'human', 'confirm', operation_key='wrong', observation_hash=observed['observation_hash'])
        await b.control('task:run', 'human', 'confirm', operation_key='submit', observation_hash=observed['observation_hash'])
        await b.control('task:run', 'human', 'release')
        assert (await b.act('task:run', 'new-navigation', 'navigate', 'https://test.invalid/'))['status'] == 'completed'
    asyncio.run(run())


def test_human_takeover_survives_restart_and_changed_page_refuses_confirmation(tmp_path):
    b, calls = broker(tmp_path)
    async def run():
        await b.act('task:run', 'open', 'open')
        await b.act('task:run', 'submit', 'submit', selector='#form')
        await b.control('task:run', 'human', 'take')
        observed = await b.control('task:run', 'human', 'read')
        b2 = type(b)(b.path, b.cdp)
        with pytest.raises(HTTPException):
            await b2.act('task:run', 'read', 'read')
        async def changed(*args):
            return {'result': {'value': {'url': 'https://test.invalid/', 'title': 'Changed', 'text': 'New result'}}}
        b2.cdp = changed
        with pytest.raises(HTTPException):
            await b2.control('task:run', 'human', 'confirm', operation_key='submit', observation_hash=observed['observation_hash'])
    asyncio.run(run())


# --- SSRF policy (navigate) ---------------------------------------------------

def _fixed_resolver(*addresses):
    def resolve(host, port):
        return [(None, None, None, '', (address, 0)) for address in addresses]
    return resolve


@pytest.mark.parametrize('url', [
    'http://127.0.0.1/', 'http://localhost/', 'http://10.1.2.3/', 'http://172.16.0.5/', 'http://192.168.1.1/',
    'http://100.64.0.1/', 'http://100.127.255.254/', 'http://169.254.169.254/latest/meta-data/',
    'http://[::1]/', 'http://[fe80::1]/', 'http://[fd00::1]/', 'http://[::ffff:127.0.0.1]/', 'http://0.0.0.0/',
])
def test_navigation_refuses_internal_addresses(url):
    from task_browser import check_navigation_url
    with pytest.raises(HTTPException) as refused:
        check_navigation_url(url, frozenset(), _fixed_resolver('127.0.0.1'))
    assert refused.value.status_code in (403, 422)


@pytest.mark.parametrize('url', ['file:///etc/passwd', 'javascript:alert(1)', 'ftp://example.com/',
                                 'chrome://settings', 'https://user:pw@example.com/', 'https:///nohost'])
def test_navigation_refuses_other_schemes_and_credentials(url):
    from task_browser import check_navigation_url
    with pytest.raises(HTTPException) as refused:
        check_navigation_url(url, frozenset(), _fixed_resolver('93.184.216.34'))
    assert refused.value.status_code == 422


def test_hostname_resolving_to_any_private_address_is_refused():
    from task_browser import check_navigation_url
    with pytest.raises(HTTPException):
        check_navigation_url('https://rebind.example/', frozenset(), _fixed_resolver('93.184.216.34', '10.0.0.7'))
    check_navigation_url('https://public.example/', frozenset(), _fixed_resolver('93.184.216.34'))


def test_unresolvable_host_is_refused_and_allowlist_bypasses_resolution():
    from task_browser import check_navigation_url

    def fails(host, port):
        raise OSError('no such host')

    with pytest.raises(HTTPException):
        check_navigation_url('https://intranet.test/', frozenset(), fails)
    check_navigation_url('https://intranet.test/', frozenset({'intranet.test'}), fails)


def test_allowed_hosts_come_from_environment(monkeypatch):
    import task_browser
    monkeypatch.setenv('FORGEHUB_TASK_BROWSER_ALLOWED_HOSTS', ' Intranet.Test., portal.local ,')
    assert task_browser.allowed_hosts_from_env() == {'intranet.test', 'portal.local'}


def test_refused_navigation_records_nothing_and_sends_nothing(tmp_path):
    b, calls = broker(tmp_path)
    async def run():
        await b.act('task:run', 'open', 'open')
        before = len(calls)
        with pytest.raises(HTTPException):
            await b.act('task:run', 'nav-meta', 'navigate', 'http://169.254.169.254/')
        assert len(calls) == before
        with b.connect() as db:
            assert db.execute("SELECT count(*) FROM operations WHERE key='nav-meta'").fetchone()[0] == 0
            assert db.execute("SELECT fenced FROM sessions WHERE scope='task:run'").fetchone()[0] == 0
    asyncio.run(run())


# --- connections and restart recovery -----------------------------------------

def test_connections_are_closed(tmp_path):
    b, _calls = broker(tmp_path)
    with b.connect() as db:
        db.execute('SELECT 1')
    import sqlite3
    with pytest.raises(sqlite3.ProgrammingError):
        db.execute('SELECT 1')


def test_restart_stops_recorded_browser_and_closes_sessions(tmp_path):
    import signal
    b, _calls = broker(tmp_path)
    async def run():
        await b.act('task:run', 'open', 'open')
    asyncio.run(run())
    b.record_browser(4242, 9299)
    killed = []
    result = type(b)(b.path, b.cdp).recover_after_restart(
        9299, kill=lambda pid, sig: killed.append((pid, sig)),
        cmdline=lambda pid: '/usr/bin/chromium --headless=new --remote-debugging-port=9299')
    assert killed == [(4242, signal.SIGTERM)]
    assert result == {'terminated_pid': 4242, 'sessions_closed': 1}
    with b.connect() as db:
        assert db.execute('SELECT closed FROM sessions').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM browser').fetchone()[0] == 0


def test_restart_never_kills_a_reused_pid(tmp_path):
    b, _calls = broker(tmp_path)
    b.record_browser(4242, 9299)
    killed = []
    result = b.recover_after_restart(9299, kill=lambda pid, sig: killed.append(pid),
                                     cmdline=lambda pid: '/usr/sbin/sshd -D')
    assert killed == [] and result['terminated_pid'] is None


# --- feature switch -----------------------------------------------------------

def test_bridge_routes_absent_when_disabled(monkeypatch):
    monkeypatch.delenv('FORGEHUB_TASK_BROWSER_ENABLED', raising=False)
    import app
    paths = {getattr(route, 'path', '') for route in app.app.routes}
    assert not any(path.startswith('/v1/workspace-browser/task-context') for path in paths)
    if not app.TASK_BROWSER_ENABLED:
        assert app._task_browser_broker is None


def test_register_wires_routes_only_when_called(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import task_browser
    launched = []

    async def launch():
        launched.append(True)

    async def cdp(*args, **kwargs):
        return {}

    bare = FastAPI()
    assert TestClient(bare).post('/v1/workspace-browser/task-context', json={}).status_code == 404
    wired = FastAPI()
    task_browser.register_task_browser(wired, lambda token: None, launch, cdp, tmp_path / 's.sqlite')
    response = TestClient(wired).post('/v1/workspace-browser/task-context', json={
        'scope': 's', 'idempotency_key': 'k', 'action': 'navigate', 'url': 'http://127.0.0.1/'})
    assert response.status_code == 422 or response.status_code == 403
    assert launched == [True]
