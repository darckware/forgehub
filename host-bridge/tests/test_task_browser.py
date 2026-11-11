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

    return module.TaskBrowserBroker(tmp_path / 'browser.sqlite', cdp), calls


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
        b2 = type(b)(b.path, lost)
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
